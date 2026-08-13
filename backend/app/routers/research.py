"""Deep research (F7): a sourced brief on one member, on request.

Every gate resolves before a single search is issued — consent, protected attributes,
then budget. A refused request costs nothing and says why, rather than returning an empty
brief the asker would read as "nothing found".
"""

import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from app.auth import CurrentUser
from app.dependencies import AccountsDependency, ResearchDependency
from app.research import (
    ResearchAgent,
    build_queries,
    corroborate,
    identity_anchors,
    protected_goal_reason,
    utcnow,
)
from app.schemas import ResearchCreate
from app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/status")
def research_status(request: Request) -> dict:
    return request.app.state.exa.describe()


def _run(
    app, brief_id: str, *, name: str, goal: str, queries: list[str], anchors: set[str]
) -> None:
    """The background job. Every failure lands on the brief, never in a void."""
    exa = app.state.exa
    store = app.state.research
    try:
        seen: set[str] = set()
        sources: list[dict] = []
        cost = 0.0
        for query in queries:
            batch = exa.search(query)
            cost += batch["cost"]
            for row in batch["results"]:
                if row["url"] not in seen:
                    seen.add(row["url"])
                    sources.append(row)
        # Identity before synthesis. A citation that resolves is not the same as a
        # source that is about this person, and a common name makes that gap wide.
        confirmed, unconfirmed = corroborate(sources, anchors)
        result = ResearchAgent(chat=app.state.chat).run(
            name=name, goal=goal, sources=confirmed, unconfirmed=unconfirmed
        )
        store.complete(brief_id, result=result, cost=cost, queries=queries)
    except Exception as exc:  # noqa: BLE001 - a background failure with no trace is
        # indistinguishable from one still running.
        logger.exception("research job failed")
        store.fail(brief_id, str(exc))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_research(
    payload: ResearchCreate,
    request: Request,
    background: BackgroundTasks,
    user: CurrentUser,
    accounts: AccountsDependency,
    research: ResearchDependency,
) -> dict:
    if payload.subject_id == user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Research is for looking someone else up.",
        )
    subject = accounts.get_user(payload.subject_id)
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # 1. Consent. The subject decides whether they can be profiled, and the default is no.
    settings_row = accounts.get_member_settings(payload.subject_id)
    if not settings_row.get("research_enabled"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"{subject['display_name']} has not turned on deep research. "
                "You can still interview their agent."
            ),
        )

    # 2. Protected attributes, refused before any search is issued.
    refusal = protected_goal_reason(payload.goal)
    if refusal:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=refusal)

    # 3. Budget. The funnel in the spec is a cost gate; this is where it bites.
    app_settings = get_settings()
    spent = research.spend_since(user["_id"], utcnow() - timedelta(days=1))
    if spent >= app_settings.research_daily_budget_usd:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You have used today's research budget (${spent:.2f} of "
                f"${app_settings.research_daily_budget_usd:.2f}). It resets in 24 hours."
            ),
        )

    if not request.app.state.exa.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Deep research needs an Exa API key. It is off right now.",
        )

    profile = accounts.get_profile(payload.subject_id) or {}
    queries = build_queries(
        name=subject["display_name"],
        headline=profile.get("headline", ""),
        organization=profile.get("organization", ""),
        goal=payload.goal,
    )
    brief = research.create_pending(
        asker_id=user["_id"], subject_id=payload.subject_id, goal=payload.goal
    )
    background.add_task(
        _run,
        request.app,
        brief["_id"],
        name=subject["display_name"],
        goal=payload.goal,
        queries=queries,
        anchors=identity_anchors(
            profile=profile,
            name=subject["display_name"],
            handle=subject.get("handle", ""),
        ),
    )
    return brief


@router.get("")
def list_briefs(user: CurrentUser, research: ResearchDependency) -> list[dict]:
    return research.list_for_asker(user["_id"])


@router.get("/{brief_id}")
def get_brief(brief_id: str, user: CurrentUser, research: ResearchDependency) -> dict:
    # Filtered on asker_id inside the store: a brief is private to whoever asked.
    brief = research.get(brief_id, user["_id"])
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brief not found")
    return brief
