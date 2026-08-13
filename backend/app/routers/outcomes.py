from fastapi import APIRouter, HTTPException, Request, status

from app.auth import CurrentUser
from app.dependencies import AccountsDependency, OutcomesDependency
from app.outcomes import OUTCOME_LABELS
from app.schemas import OutcomeCreate

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


@router.get("/labels")
def labels() -> dict:
    """What a member can report, and what each report implies."""
    return {
        label: {"score": spec["score"], "weight": spec["weight"]}
        for label, spec in OUTCOME_LABELS.items()
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def record_outcome(
    payload: OutcomeCreate,
    request: Request,
    user: CurrentUser,
    outcomes: OutcomesDependency,
    accounts: AccountsDependency,
) -> dict:
    """Report what actually happened. This is what makes the next ranking different."""
    if accounts.get_user(payload.subject_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    predicted = payload.predicted_score
    # Prefer the score the agent actually predicted over anything the client sends,
    # so calibration measures the agent rather than the caller.
    if payload.context == "community":
        comment = request.app.state.community.db.community_comments.find_one(
            {"post_id": payload.context_id, "responder_id": payload.subject_id}
        )
        if comment is not None:
            predicted = comment.get("recruit_score")

    try:
        outcome = outcomes.record(
            reporter_id=user["_id"],
            subject_id=payload.subject_id,
            label=payload.label,
            context=payload.context,
            context_id=payload.context_id,
            predicted_score=predicted,
            note=payload.note,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return {
        "outcome": outcome,
        "trust": outcomes.effective_trust(user["_id"], payload.subject_id),
        "calibration": outcomes.calibration(user["_id"]),
    }


@router.get("")
def my_outcomes(
    user: CurrentUser, outcomes: OutcomesDependency, accounts: AccountsDependency
) -> list[dict]:
    rows = outcomes.list_for_reporter(user["_id"])
    subjects = accounts.users_by_id(sorted({row["subject_id"] for row in rows}))
    for row in rows:
        subject = subjects.get(row["subject_id"])
        row["subject"] = (
            {"display_name": subject["display_name"], "handle": subject["handle"]}
            if subject
            else None
        )
    return rows


@router.get("/calibration")
def my_calibration(user: CurrentUser, outcomes: OutcomesDependency) -> dict:
    """How well this member's own agent has been predicting matches."""
    record = outcomes.calibration(user["_id"])
    bias = record["bias"]
    if record["samples"] < 3:
        summary = "Not enough recorded outcomes yet to tell how well your agent predicts."
    elif bias > 0.15:
        summary = (
            "Your agent has been over-promising — it rates matches higher than they turn "
            "out. Its scores are being damped until that closes."
        )
    elif bias < -0.15:
        summary = "Your agent has been under-selling matches that turned out well."
    else:
        summary = "Your agent's predictions have been tracking reality closely."
    return {**record, "summary": summary}


@router.get("/trust/{subject_id}")
def trust_breakdown(
    subject_id: str,
    user: CurrentUser,
    outcomes: OutcomesDependency,
    accounts: AccountsDependency,
) -> dict:
    """Why your agent currently rates this person the way it does."""
    if accounts.get_user(subject_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return outcomes.effective_trust(user["_id"], subject_id)
