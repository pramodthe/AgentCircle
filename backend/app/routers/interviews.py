from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.agent_memory import memories_from_interview
from app.auth import CurrentUser
from app.dependencies import (
    AccountsDependency,
    AgentMemoryDependency,
    CommunityDependency,
    EmbeddingsDependency,
    InterviewsDependency,
    MemoryGraphDependency,
)
from app.interview import (
    DEFAULT_INTERVIEW_SETTINGS,
    MAX_QUESTIONS,
    QUESTION_PRESETS,
    safe_interview_settings,
)
from app.schemas import InterviewCreate, InterviewSettingsUpdate

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


@router.get("/presets")
def presets() -> dict:
    return {"presets": QUESTION_PRESETS, "max_questions": MAX_QUESTIONS}


@router.get("/settings")
def get_settings_(user: CurrentUser, accounts: AccountsDependency) -> dict:
    stored = accounts.get_member_settings(user["_id"])
    return {
        **DEFAULT_INTERVIEW_SETTINGS,
        **{k: stored[k] for k in DEFAULT_INTERVIEW_SETTINGS if k in stored},
    }


@router.patch("/settings")
def update_settings_(
    payload: InterviewSettingsUpdate, user: CurrentUser, accounts: AccountsDependency
) -> dict:
    # Merge onto stored, for the same reason as community settings: sanitising a bare
    # patch resets every field it did not mention, so toggling one consent silently
    # revokes the others.
    stored = accounts.get_member_settings(user["_id"])
    current = {**DEFAULT_INTERVIEW_SETTINGS, **{
        key: stored[key] for key in DEFAULT_INTERVIEW_SETTINGS if key in stored
    }}
    safe = safe_interview_settings({**current, **payload.model_dump(exclude_unset=True)})
    accounts.update_member_settings(user["_id"], safe)
    return safe


def _remember_exchange(*, memory, embeddings, asker_id, subject_id, goal, rows) -> None:
    """Write both sides' memory of a finished interview.

    Failing to remember must not fail the interview — the answers are already correct
    and stored. One embedding request for the whole batch, never one per memory.
    """
    pending = memories_from_interview(
        asker_id=asker_id, subject_id=subject_id, goal=goal, rows=rows
    )
    if not pending:
        return
    try:
        vectors = embeddings.embed_batch([row["text"] for row in pending])
        space = embeddings.space()
        memory.remember_many(
            [
                {**row, "embedding": vector, "space": space}
                for row, vector in zip(pending, vectors, strict=True)
            ]
        )
    except Exception:  # noqa: BLE001 - memory is an enhancement, not the answer
        return


def _record_relationship(*, graph, asker_id: str, subject_id: str, rows) -> None:
    """Record that these two interacted, and the evidence behind it.

    `via` is deliberately left to the caller of the graph rather than guessed here — an
    invented shared topic would be exactly the manufactured link the evidence rule exists
    to prevent. Only citations that actually resolved are passed through.
    """
    evidence = [
        {"chunk_id": c.get("chunk_id"), "source_title": c.get("source_title")}
        for row in rows
        for c in (row.get("citations") or [])
        if c.get("chunk_id")
    ]
    try:
        graph.record(
            owner_id=asker_id,
            counterparty_id=subject_id,
            rel="INTERVIEWED",
            evidence=evidence[:5],
        )
        graph.record(
            owner_id=subject_id,
            counterparty_id=asker_id,
            rel="INTERVIEWED",
            evidence=evidence[:5],
        )
    except Exception:  # noqa: BLE001 - the interview already succeeded
        return


def _run_interview_job(
    *,
    interview_id: str,
    subject: dict,
    questions: list[str],
    goal: str,
    settings: dict,
    agent,
    accounts,
    community,
    embeddings,
    interviews,
    memory,
    graph,
    asker_id: str,
    atlas: bool,
) -> None:
    """The actual agent work, run after the response has been sent.

    Anything raised here is recorded on the interview rather than lost: a background
    failure with no trace is indistinguishable from one still running.
    """
    try:
        space = embeddings.space()
        # One embedding request for every question — see the note in the caller.
        question_vectors = embeddings.embed_batch(questions)
        # The subject's own evidence, plus anything their agent already remembers about
        # this particular asker. `recall` filters on the edge inside the query, so a prior
        # conversation with anyone else cannot reach this prompt.
        chunks_per_question = []
        for vector in question_vectors:
            grounding = accounts.search_chunks(
                user_id=subject["_id"],
                query_vector=vector,
                space=space,
                limit=3,
                atlas=atlas,
            )
            remembered = memory.recall(
                owner_id=subject["_id"],
                counterparty_id=asker_id,
                query_vector=vector,
                space=space,
                limit=2,
                atlas=atlas,
            )
            # Memory is offered as evidence in the same shape as a chunk, so it goes
            # through the agent's existing citation check rather than around it.
            chunks_per_question.append(
                grounding
                + [
                    {
                        "_id": row["_id"],
                        "text": row["text"],
                        "source_title": "your earlier conversation with them",
                        "source_id": row["edge_id"],
                    }
                    for row in remembered
                ]
            )

        result = agent.run(
            questions=questions,
            subject_name=subject["display_name"],
            chunks_per_question=chunks_per_question,
            settings=settings,
        )
        verdict = agent.verdict(
            goal=goal,
            subject_name=subject["display_name"],
            rows=result["rows"],
            offer=result["offer"],
        )

        for row in result["rows"]:
            if row["decline_kind"] == "not_in_profile":
                community.record_gap(
                    user_id=subject["_id"], question=row["question"], source="interview"
                )

        # The relationship itself is recorded separately from what was said: the edge is
        # shareable (it explains an introduction), the memory is not.
        _record_relationship(
            graph=graph,
            asker_id=asker_id,
            subject_id=subject["_id"],
            rows=result["rows"],
        )

        _remember_exchange(
            memory=memory,
            embeddings=embeddings,
            asker_id=asker_id,
            subject_id=subject["_id"],
            goal=goal,
            rows=result["rows"],
        )

        interviews.complete(
            interview_id,
            rows=result["rows"],
            verdict=verdict,
            offer=result["offer"],
            runtime_mode=result["runtime_mode"],
            model=agent.chat.model_name if agent.chat.configured else None,
        )
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
        interviews.fail(interview_id, f"{type(exc).__name__}: {exc}")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def run_interview(
    payload: InterviewCreate,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser,
    accounts: AccountsDependency,
    community: CommunityDependency,
    embeddings: EmbeddingsDependency,
    interviews: InterviewsDependency,
    memory: AgentMemoryDependency,
    graph: MemoryGraphDependency,
) -> dict:
    """Start an interview and return immediately.

    The agent work takes tens of seconds — two model calls plus retrieval — and making
    someone watch a spinner for that is the difference between a tool they use and one
    they try once. The caller gets an id straight away and polls for the result.
    """
    subject = accounts.get_user(payload.subject_id)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if subject["_id"] == user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot interview your own agent",
        )

    settings = {
        **DEFAULT_INTERVIEW_SETTINGS,
        **accounts.get_member_settings(subject["_id"]),
    }
    if not settings.get("interview_enabled"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{subject['display_name']} has not enabled agent interviews. "
                "You can still reach out directly."
            ),
        )

    questions = [q.strip() for q in payload.questions if q.strip()][:MAX_QUESTIONS]
    if not questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ask at least one question"
        )

    pending = interviews.create_pending(
        asker_id=user["_id"],
        subject_id=subject["_id"],
        goal=payload.goal,
        questions=questions,
    )
    # Retrieval is per question — a question about hiring and one about hobbies need
    # different parts of the same profile — but every question is embedded in ONE
    # request. Providers meter by request count, so N sequential calls hit the rate
    # limit and wait out the backoff: 63.6s for four questions versus 0.40s batched.
    background.add_task(
        _run_interview_job,
        interview_id=pending["_id"],
        subject=subject,
        questions=questions,
        goal=payload.goal,
        settings=settings,
        agent=request.app.state.interview_agent,
        accounts=accounts,
        community=community,
        embeddings=embeddings,
        interviews=interviews,
        memory=memory,
        graph=graph,
        asker_id=user["_id"],
        atlas=request.app.state.people_search._atlas_vector_ok,
    )
    pending["subject"] = {
        "user_id": subject["_id"],
        "display_name": subject["display_name"],
        "handle": subject["handle"],
    }
    return pending


@router.get("")
def list_interviews(
    user: CurrentUser, accounts: AccountsDependency, interviews: InterviewsDependency
) -> list[dict]:
    rows = interviews.list_for_asker(user["_id"])
    subjects = accounts.users_by_id(sorted({row["subject_id"] for row in rows}))
    for row in rows:
        subject = subjects.get(row["subject_id"])
        row["subject"] = (
            {
                "user_id": row["subject_id"],
                "display_name": subject["display_name"],
                "handle": subject["handle"],
            }
            if subject
            else None
        )
    return rows


@router.get("/{interview_id}")
def get_interview(
    interview_id: str,
    user: CurrentUser,
    accounts: AccountsDependency,
    interviews: InterviewsDependency,
) -> dict:
    row = interviews.get(interview_id, user["_id"])
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    subject = accounts.get_user(row["subject_id"])
    row["subject"] = (
        {
            "user_id": row["subject_id"],
            "display_name": subject["display_name"],
            "handle": subject["handle"],
        }
        if subject
        else None
    )
    return row


@router.get("/network/paths")
def network_paths(
    user: CurrentUser,
    accounts: AccountsDependency,
    graph: MemoryGraphDependency,
    limit: int = 10,
) -> dict:
    """People two hops away, and the path that reaches them.

    `discoverable` is opt-out and is applied *before* traversal, so a member who turned it
    off is not walked through either — being a stepping stone is still being findable.

    Returns identities and shared topics only. Nothing from `agent_memory` is reachable
    from here; that stays on its edge.
    """
    blocked = accounts.undiscoverable_ids()
    allowed = [
        row["_id"]
        for row in accounts.db.users.find({}, {"_id": 1})
        if row["_id"] not in blocked
    ]
    reached = graph.reachable(
        owner_id=user["_id"], allowed_ids=allowed, limit=min(max(1, limit), 25)
    )
    members = {
        row["_id"]: row
        for row in accounts.db.users.find(
            {"_id": {"$in": [item["user_id"] for item in reached]}}
        )
    }
    return {
        "paths": [
            {
                **item,
                "member": accounts.public_member(members[item["user_id"]]),
                "through": [
                    accounts.public_member(members[uid])
                    for uid in item["through"]
                    if uid in members
                ],
            }
            for item in reached
            if item["user_id"] in members
        ]
    }
