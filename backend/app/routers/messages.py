from fastapi import APIRouter, HTTPException, status

from app.auth import CurrentUser
from app.dependencies import (
    AccountsDependency,
    ConnectionsDependency,
    MessagesDependency,
    ProfileMediaDependency,
)
from app.profile_media import public_profile_media
from app.routers.social import _people
from app.schemas import DirectMessageCreate
from app.social import pair_id

router = APIRouter(prefix="/api/messages", tags=["messages"])


def _require_member(user_id: str, other_id: str, accounts, connections) -> None:
    if accounts.get_user(other_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    relationship = connections.status_between(user_id, other_id)
    if not relationship or relationship.get("status") != "accepted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can message this member after you are connected",
        )


def _member(accounts, profile_media, member_id: str) -> dict:
    return _people(accounts, [member_id], profile_media).get(
        member_id,
        {
            "user_id": member_id,
            "display_name": "Member",
            "handle": "",
            "headline": "",
            "accent": "violet",
            **public_profile_media(None),
        },
    )


@router.get("")
def list_conversations(
    user: CurrentUser,
    accounts: AccountsDependency,
    messages: MessagesDependency,
    profile_media: ProfileMediaDependency,
) -> list[dict]:
    rows = messages.list_conversations(user["_id"])
    for row in rows:
        row["member"] = _member(accounts, profile_media, row["member_id"])
    return rows


@router.get("/{other_id}")
def read_thread(
    other_id: str,
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
    messages: MessagesDependency,
    profile_media: ProfileMediaDependency,
) -> dict:
    _require_member(user["_id"], other_id, accounts, connections)
    messages.mark_read(user_id=user["_id"], other_id=other_id)
    return {
        "conversation_id": pair_id(user["_id"], other_id),
        "member": _member(accounts, profile_media, other_id),
        "messages": messages.thread(user_id=user["_id"], other_id=other_id),
    }


@router.post("/{other_id}", status_code=status.HTTP_201_CREATED)
def send_message(
    other_id: str,
    payload: DirectMessageCreate,
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
    messages: MessagesDependency,
) -> dict:
    _require_member(user["_id"], other_id, accounts, connections)
    try:
        return messages.send(sender_id=user["_id"], recipient_id=other_id, body=payload.body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/{other_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_thread_read(
    other_id: str,
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
    messages: MessagesDependency,
) -> None:
    _require_member(user["_id"], other_id, accounts, connections)
    messages.mark_read(user_id=user["_id"], other_id=other_id)
