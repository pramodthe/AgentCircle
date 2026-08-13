"""Direct messages between accepted connections."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.serializers import serialize
from app.social import pair_id

MAX_MESSAGE_CHARACTERS = 2000


def utcnow() -> datetime:
    return datetime.now(UTC)


class MessageStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.direct_messages.create_index(
            [("conversation_id", ASCENDING), ("created_at", ASCENDING)]
        )
        self.db.direct_messages.create_index(
            [("participants", ASCENDING), ("created_at", DESCENDING)]
        )
        self.db.direct_messages.create_index(
            [("recipient_id", ASCENDING), ("read_at", ASCENDING)]
        )

    def send(self, *, sender_id: str, recipient_id: str, body: str) -> dict:
        clean = body.strip()
        if not clean:
            raise ValueError("Message cannot be empty")
        if len(clean) > MAX_MESSAGE_CHARACTERS:
            raise ValueError(f"Message must be {MAX_MESSAGE_CHARACTERS} characters or fewer")

        now = utcnow()
        conversation_id = pair_id(sender_id, recipient_id)
        sequence = self.db.direct_messages.count_documents({"conversation_id": conversation_id})
        previous = self.db.direct_messages.find_one(
            {"conversation_id": conversation_id},
            sort=[("created_at", DESCENDING)],
        )
        if previous:
            previous_at = previous["created_at"]
            if previous_at.tzinfo is None:
                previous_at = previous_at.replace(tzinfo=UTC)
            if now <= previous_at:
                now = previous_at + timedelta(microseconds=1)
        document = {
            "_id": f"dm_{uuid4().hex[:16]}",
            "conversation_id": conversation_id,
            "sequence": sequence,
            "participants": sorted((sender_id, recipient_id)),
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "body": clean,
            "created_at": now,
            "read_at": None,
        }
        self.db.direct_messages.insert_one(document)
        return serialize(document)

    def list_conversations(self, user_id: str) -> list[dict]:
        rows = list(
            self.db.direct_messages.find({"participants": user_id}).sort(
                "created_at", DESCENDING
            )
        )
        rows.sort(key=lambda row: (row.get("sequence", 0), row["created_at"]), reverse=True)
        conversations: dict[str, dict] = {}
        for row in rows:
            conversation_id = row["conversation_id"]
            if conversation_id in conversations:
                continue
            member_id = next(
                participant for participant in row["participants"] if participant != user_id
            )
            unread_count = self.db.direct_messages.count_documents(
                {
                    "conversation_id": conversation_id,
                    "recipient_id": user_id,
                    "read_at": None,
                }
            )
            conversations[conversation_id] = {
                "conversation_id": conversation_id,
                "member_id": member_id,
                "last_message": serialize(row),
                "unread_count": unread_count,
                "updated_at": row["created_at"],
            }
        return list(conversations.values())

    def thread(self, *, user_id: str, other_id: str, limit: int = 100) -> list[dict]:
        rows = list(
            self.db.direct_messages.find(
                {"conversation_id": pair_id(user_id, other_id)}
            )
            .sort("sequence", ASCENDING)
            .limit(limit)
        )
        return serialize(rows)

    def mark_read(self, *, user_id: str, other_id: str) -> None:
        self.db.direct_messages.update_many(
            {
                "conversation_id": pair_id(user_id, other_id),
                "recipient_id": user_id,
                "read_at": None,
            },
            {"$set": {"read_at": utcnow()}},
        )
