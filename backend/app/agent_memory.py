"""What an agent remembers about one relationship, and nothing about any other.

An agent that remembers conversations is more useful than one that starts cold every
time. It is also, immediately, a disclosure risk: if Kenji's agent recalls what Maya's
agent told it while Kenji is talking to Priya, the product has leaked a private exchange
between two other people through a third.

So memory is stored **on the edge**, not on the member. The key is `pair_id(owner,
counterparty)` — the same order-independent identifier connections and direct messages
already use — and retrieval filters on `(owner_id, edge_id)` *inside the query*, not by
discarding rows afterwards. Post-filtering is how this kind of leak happens: one forgotten
branch and the data is already out of the database.

Two things follow from that and are load-bearing:

  * Edge memory is never merged into the persona. The persona is what discovery, the
    community commenter and third-party interviews all read from, so anything that
    reaches it is effectively public to the network. Memory that must stay between two
    people therefore never goes there.
  * A memory derived from a cited answer keeps that citation. When the chunk behind it is
    deleted the memory goes too, for the same reason a persona item does — a claim whose
    evidence is gone is exactly the uncited assertion the rest of the product refuses to
    publish.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.embeddings import cosine_similarity
from app.serializers import serialize
from app.social import pair_id

# What a memory can be about. Kept small on purpose: each kind is written by exactly one
# call site, so an unexpected value means a bug rather than a new feature.
KINDS = ("interview_asked", "interview_answered", "message", "outcome")


def utcnow() -> datetime:
    return datetime.now(UTC)


class AgentMemoryStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        # The compound index leads with the two fields every read filters on, so the
        # isolation boundary is also the access path.
        self.db.agent_memory.create_index(
            [("owner_id", ASCENDING), ("edge_id", ASCENDING), ("created_at", DESCENDING)]
        )
        self.db.agent_memory.create_index([("owner_id", ASCENDING), ("space", ASCENDING)])
        self.db.agent_memory.create_index("chunk_id")

    # ------------------------------------------------------------------ writing

    def remember(
        self,
        *,
        owner_id: str,
        counterparty_id: str,
        kind: str,
        text: str,
        embedding: list[float],
        space: str,
        chunk_id: str | None = None,
        source_title: str | None = None,
    ) -> dict:
        """Record one thing the owner's agent now knows about this relationship."""
        if kind not in KINDS:
            raise ValueError(f"unknown memory kind: {kind}")
        text = text.strip()
        if not text:
            raise ValueError("a memory needs text")
        now = utcnow()
        document = {
            "_id": f"mem_{uuid4().hex[:20]}",
            "owner_id": owner_id,
            "counterparty_id": counterparty_id,
            "edge_id": pair_id(owner_id, counterparty_id),
            "kind": kind,
            "text": text[:2000],
            "embedding": embedding,
            "space": space,
            "chunk_id": chunk_id,
            "source_title": source_title,
            "created_at": now,
        }
        self.db.agent_memory.insert_one(document)
        return serialize(document)

    def remember_many(self, rows: list[dict[str, Any]]) -> int:
        """Bulk write. Callers embed in one batch — see the no-embedding-in-a-loop rule."""
        written = 0
        for row in rows:
            try:
                self.remember(**row)
                written += 1
            except ValueError:
                continue
        return written

    # ------------------------------------------------------------------ reading

    def recall(
        self,
        *,
        owner_id: str,
        counterparty_id: str,
        query_vector: list[float],
        space: str,
        limit: int = 3,
        atlas: bool = False,
    ) -> list[dict]:
        """The owner's memory of this one relationship. Never any other.

        `owner_id` and `edge_id` are both applied as filters in the query itself. A caller
        cannot widen this by passing a different limit or forgetting a check downstream.
        """
        edge_id = pair_id(owner_id, counterparty_id)
        query = {"owner_id": owner_id, "edge_id": edge_id, "space": space}

        if atlas:
            try:
                return serialize(
                    list(
                        self.db.agent_memory.aggregate(
                            [
                                {
                                    "$vectorSearch": {
                                        "index": "agent_memory_vector",
                                        "path": "embedding",
                                        "queryVector": query_vector,
                                        "numCandidates": max(50, limit * 10),
                                        "limit": max(1, limit),
                                        "filter": query,
                                    }
                                },
                                {"$project": {"embedding": 0}},
                                {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                            ]
                        )
                    )
                )
            except Exception:
                # Same shape as AccountStore.search_chunks: an unavailable index falls
                # back to a scored scan rather than returning an empty result set.
                pass

        scored: list[dict] = []
        for row in self.db.agent_memory.find(query):
            row["score"] = round(cosine_similarity(query_vector, row.get("embedding", [])), 4)
            row.pop("embedding", None)
            scored.append(row)
        scored.sort(key=lambda item: item["score"], reverse=True)
        return serialize(scored[: max(1, limit)])

    def timeline(self, *, owner_id: str, counterparty_id: str, limit: int = 20) -> list[dict]:
        """Everything remembered about one relationship, newest first. Owner only."""
        return serialize(
            list(
                self.db.agent_memory.find(
                    {"owner_id": owner_id, "edge_id": pair_id(owner_id, counterparty_id)},
                    {"embedding": 0},
                )
                .sort("created_at", DESCENDING)
                .limit(max(1, limit))
            )
        )

    def counterparties(self, owner_id: str) -> list[dict]:
        """Who this agent has memory of, and how much — for the owner's own review."""
        return serialize(
            list(
                self.db.agent_memory.aggregate(
                    [
                        {"$match": {"owner_id": owner_id}},
                        {
                            "$group": {
                                "_id": "$counterparty_id",
                                "count": {"$sum": 1},
                                "last_seen": {"$max": "$created_at"},
                                "kinds": {"$addToSet": "$kind"},
                            }
                        },
                        {"$sort": {"last_seen": -1}},
                    ]
                )
            )
        )

    # ------------------------------------------------------------------ removal

    def forget_chunks(self, chunk_ids: set[str]) -> int:
        """Drop memories whose supporting chunk is gone."""
        if not chunk_ids:
            return 0
        return self.db.agent_memory.delete_many(
            {"chunk_id": {"$in": list(chunk_ids)}}
        ).deleted_count

    def forget_user(self, user_id: str) -> int:
        """Everything this member's agent remembered, and everything remembered of them."""
        return self.db.agent_memory.delete_many(
            {"$or": [{"owner_id": user_id}, {"counterparty_id": user_id}]}
        ).deleted_count


def memories_from_interview(
    *,
    asker_id: str,
    subject_id: str,
    goal: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Turn a finished interview into memory for *both* sides of the edge.

    Each party remembers their own view of the same exchange: the asker remembers what
    they learned, the subject remembers what they were asked. They are separate documents
    with separate owners, so neither can read the other's.

    Only answered rows become memory. A decline is already recorded as a context gap, and
    turning "they had nothing on this" into a remembered claim would invert its meaning.
    """
    pending: list[dict[str, Any]] = []
    for row in rows:
        question = str(row.get("question") or "").strip()
        if not question:
            continue

        if row.get("answered") and str(row.get("answer") or "").strip():
            citation = (row.get("citations") or [{}])[0]
            pending.append(
                {
                    "owner_id": asker_id,
                    "counterparty_id": subject_id,
                    "kind": "interview_asked",
                    "text": f"I asked: {question}\nTheir agent answered: {row['answer']}",
                    "chunk_id": citation.get("chunk_id"),
                    "source_title": citation.get("source_title"),
                }
            )

        # The subject remembers being asked whether or not their agent could answer —
        # that is the demand signal, and it is theirs to see.
        pending.append(
            {
                "owner_id": subject_id,
                "counterparty_id": asker_id,
                "kind": "interview_answered",
                "text": (
                    f"They asked: {question}"
                    + (f"\nMy agent answered: {row['answer']}" if row.get("answered") else "")
                    + (f"\n(Their goal: {goal})" if goal else "")
                ),
            }
        )
    return pending
