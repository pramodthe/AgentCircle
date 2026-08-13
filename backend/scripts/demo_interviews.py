"""Run the real InterviewAgent path between seeded members.

Interviews look inhabited in a demo because they went through the same job the API
uses: retrieve, `InterviewAgent.run`, verdict, then store. Grounded answers or
unanswered rows — never invented biography. Questions are embedded in one batch (C3).
Seeding is a script, never a boot path (C4).
"""

from __future__ import annotations

from typing import Any

from app.accounts import AccountStore
from app.agent_memory import AgentMemoryStore
from app.community import CommunityStore
from app.interview import (
    DEFAULT_INTERVIEW_SETTINGS,
    QUESTION_PRESETS,
    InterviewAgent,
    InterviewStore,
    safe_interview_settings,
)
from app.memory_graph import MemoryGraphStore
from app.routers.interviews import _record_relationship, _remember_exchange

# Keyed by email so the parent seed can run this after catalog accounts exist.
# Missing emails are skipped at runtime rather than failing the rest of the network.
INTERVIEW_PLAN: tuple[dict[str, str], ...] = (
    {
        "asker": "maya@example.com",
        "subject": "kenji@example.com",
        "preset": "hiring",
        "goal": "Could Kenji's systems background help Lumen's trial pipeline?",
    },
    {
        "asker": "maya@example.com",
        "subject": "anika@example.com",
        "preset": "founders",
        "goal": "Is Horizon a fit for a climate-adjacent intro?",
    },
    {
        "asker": "sofia@example.com",
        "subject": "marcus@example.com",
        "preset": "collaboration",
        "goal": "Shared evaluation / faithfulness work",
    },
    {
        "asker": "priya@example.com",
        "subject": "soren@example.com",
        "preset": "collaboration",
        "goal": "Empty-state / first-run design",
    },
    {
        "asker": "elena@example.com",
        "subject": "james@example.com",
        "preset": "feedback",
        "goal": "Bedside workflow pressure-test",
    },
    {
        "asker": "leo@example.com",
        "subject": "maya@example.com",
        "preset": "founders",
        "goal": "Activation instrumentation vs Lumen's first session",
    },
    {
        "asker": "kenji@example.com",
        "subject": "sofia@example.com",
        "preset": "collaboration",
        "goal": "Production systems meeting evaluation / faithfulness work",
    },
    {
        "asker": "sofia@example.com",
        "subject": "priya@example.com",
        "preset": "feedback",
        "goal": "Empty-state design pressure-test for eval-heavy products",
    },
)


def _subject_settings(accounts: AccountStore, user_id: str) -> dict[str, Any]:
    stored = accounts.get_member_settings(user_id)
    return {**DEFAULT_INTERVIEW_SETTINGS, **safe_interview_settings(stored)}


def _pair_exists(database, *, asker_id: str, subject_id: str) -> bool:
    return (
        database.interviews.find_one(
            {"asker_id": asker_id, "subject_id": subject_id}, {"_id": 1}
        )
        is not None
    )


def _run_one(
    *,
    interview_id: str,
    subject: dict,
    questions: list[str],
    goal: str,
    settings: dict,
    agent: InterviewAgent,
    accounts: AccountStore,
    community: CommunityStore,
    embeddings,
    interviews: InterviewStore,
    memory: AgentMemoryStore,
    graph: MemoryGraphStore,
    asker_id: str,
    atlas: bool,
) -> None:
    """Same sequence as `routers.interviews._run_interview_job`."""
    try:
        space = embeddings.space()
        question_vectors = embeddings.embed_batch(questions)
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


def seed_interviews(
    *,
    database,
    accounts: AccountStore,
    community: CommunityStore,
    embeddings,
    interviews: InterviewStore,
    agent: InterviewAgent,
    memory: AgentMemoryStore,
    graph: MemoryGraphStore,
    atlas: bool = False,
) -> dict[str, int]:
    ran = 0
    skipped = 0
    failed = 0
    answered_rows = 0

    for spec in INTERVIEW_PLAN:
        asker_email = spec["asker"]
        subject_email = spec["subject"]
        label = f"{asker_email} → {subject_email}"
        asker = accounts.get_user_by_email(asker_email)
        subject = accounts.get_user_by_email(subject_email)
        if asker is None or subject is None:
            skipped += 1
            missing = asker_email if asker is None else subject_email
            print(f"skip     {label}  (missing {missing})")
            continue
        if asker["_id"] == subject["_id"]:
            skipped += 1
            print(f"skip     {label}  (cannot interview yourself)")
            continue
        settings = _subject_settings(accounts, subject["_id"])
        if not settings.get("interview_enabled"):
            skipped += 1
            print(f"skip     {label}  (interviews disabled)")
            continue
        if _pair_exists(database, asker_id=asker["_id"], subject_id=subject["_id"]):
            skipped += 1
            print(f"skip     {label}  (already exists)")
            continue
        questions = list(QUESTION_PRESETS.get(spec["preset"]) or [])
        if not questions:
            skipped += 1
            print(f"skip     {label}  (unknown preset {spec['preset']})")
            continue

        pending_id = None
        try:
            pending = interviews.create_pending(
                asker_id=asker["_id"],
                subject_id=subject["_id"],
                goal=spec["goal"],
                questions=questions,
            )
            pending_id = pending["_id"]
            _run_one(
                interview_id=pending_id,
                subject=subject,
                questions=questions,
                goal=spec["goal"],
                settings=settings,
                agent=agent,
                accounts=accounts,
                community=community,
                embeddings=embeddings,
                interviews=interviews,
                memory=memory,
                graph=graph,
                asker_id=asker["_id"],
                atlas=atlas,
            )
        except Exception as exc:  # noqa: BLE001 - one interview must not abort the seed
            if pending_id is not None:
                interviews.fail(pending_id, f"{type(exc).__name__}: {exc}")
            failed += 1
            print(f"fail     {label}  {type(exc).__name__}: {exc}")
            continue

        row = database.interviews.find_one({"_id": pending_id}) or {}
        if row.get("status") == "failed":
            failed += 1
            print(f"fail     {label}  {row.get('error') or 'failed'}")
            continue

        ran += 1
        answered = int(row.get("answered_count") or 0)
        total = int(row.get("question_count") or len(questions))
        answered_rows += answered
        kind = (row.get("verdict") or {}).get("recommendation") or ""
        extra = f"  {kind}" if kind else ""
        print(f"interview {label}  {answered}/{total} answered{extra}")

    print(f"Interviews  {ran} ran  {skipped} skipped  {failed} failed")
    return {
        "ran": ran,
        "skipped": skipped,
        "failed": failed,
        "answered_rows": answered_rows,
    }
