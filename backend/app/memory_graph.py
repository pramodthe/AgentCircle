"""Who knows whom, why, and with what evidence — traversed in the database.

`agent_memory` holds *what was said* on one edge and never leaves it. This holds the far
weaker fact that an edge **exists**, plus the shared topic that formed it. That split is
the whole design:

    agent_memory   private   what Maya's agent told Kenji        never traversed
    memory_edges   shareable that Kenji and Maya talked, re: payments   traversed

So a second-hop result can say "Priya knows Maya, and both write about payments
infrastructure" without ever revealing a sentence from Priya and Maya's conversation. A
path is a much smaller disclosure than a transcript, and it is the part that is actually
useful for an introduction.

Traversal is `$graphLookup`, which needs only ordinary B-tree indexes — no Atlas Search
index, so this costs nothing against a tier's search-index quota.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.serializers import serialize
from app.social import pair_id

RELATIONS = ("INTERVIEWED", "CONNECTED", "MESSAGED")

# Two hops from you: your contacts, and theirs. Three would reach most of a small network
# and stop meaning anything.
MAX_DEPTH = 1


def utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryGraphStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.memory_edges.create_index(
            [("owner_id", ASCENDING), ("counterparty_id", ASCENDING)], unique=True
        )
        # $graphLookup connects counterparty_id -> owner_id, so owner_id carries the walk.
        self.db.memory_edges.create_index([("owner_id", ASCENDING), ("last_seen", DESCENDING)])
        self.db.memory_edges.create_index("counterparty_id")

    # ------------------------------------------------------------------ writing

    def record(
        self,
        *,
        owner_id: str,
        counterparty_id: str,
        rel: str,
        via: list[str] | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Note that a relationship exists, or strengthen one that already does."""
        if rel not in RELATIONS:
            raise ValueError(f"unknown relation: {rel}")
        if owner_id == counterparty_id:
            raise ValueError("an edge needs two different people")
        now = utcnow()
        # Evidence carries the chunk that justifies the shared topic, same rule as
        # everywhere else: a link nobody can trace is not worth storing.
        cited = [row for row in (evidence or []) if row.get("chunk_id")]
        self.db.memory_edges.update_one(
            {"owner_id": owner_id, "counterparty_id": counterparty_id},
            {
                "$set": {
                    "edge_id": pair_id(owner_id, counterparty_id),
                    "rel": rel,
                    "last_seen": now,
                },
                "$inc": {"strength": 1},
                "$addToSet": {
                    **({"via": {"$each": sorted(set(via))}} if via else {}),
                    **({"evidence": {"$each": cited}} if cited else {}),
                },
                "$setOnInsert": {"first_seen": now},
            },
            upsert=True,
        )
        return serialize(
            self.db.memory_edges.find_one(
                {"owner_id": owner_id, "counterparty_id": counterparty_id}
            )
        )

    def forget_user(self, user_id: str) -> int:
        return self.db.memory_edges.delete_many(
            {"$or": [{"owner_id": user_id}, {"counterparty_id": user_id}]}
        ).deleted_count

    # ------------------------------------------------------------------ reading

    def direct(self, owner_id: str) -> list[dict]:
        return serialize(
            list(self.db.memory_edges.find({"owner_id": owner_id}).sort("last_seen", DESCENDING))
        )

    def reachable(
        self,
        *,
        owner_id: str,
        allowed_ids: list[str],
        max_depth: int = MAX_DEPTH,
        limit: int = 20,
    ) -> list[dict]:
        """People two hops out, and the shared topic that connects them.

        `allowed_ids` is the set of members who may be walked through at all — callers
        pass the discoverable ones, so a member who opted out of being found is not a
        stepping stone either. It is applied inside `$graphLookup` via
        `restrictSearchWithMatch`, not filtered off the result, so an opted-out member is
        never loaded in the first place.

        Returns people and shared topics only. Never memory text — see the module note.
        """
        allowed = [uid for uid in allowed_ids if uid != owner_id]
        if not allowed:
            return []

        pipeline: list[dict[str, Any]] = [
            {"$match": {"owner_id": owner_id}},
            {
                "$graphLookup": {
                    "from": "memory_edges",
                    "startWith": "$counterparty_id",
                    "connectFromField": "counterparty_id",
                    "connectToField": "owner_id",
                    "as": "network",
                    "maxDepth": max(0, max_depth),
                    "depthField": "hops",
                    "restrictSearchWithMatch": {"owner_id": {"$in": allowed}},
                }
            },
        ]

        try:
            rows = list(self.db.memory_edges.aggregate(pipeline))
        except Exception:
            rows = self._reachable_fallback(owner_id=owner_id, allowed=set(allowed))

        known = {edge["counterparty_id"] for edge in self.db.memory_edges.find(
            {"owner_id": owner_id}, {"counterparty_id": 1}
        )}

        found: dict[str, dict[str, Any]] = {}
        for row in rows:
            first_hop = row.get("counterparty_id")
            for reached in row.get("network", []):
                candidate = reached.get("counterparty_id")
                # Not me, not someone I already know — those are not introductions.
                if not candidate or candidate == owner_id or candidate in known:
                    continue
                if reached.get("owner_id") not in allowed:
                    continue
                entry = found.setdefault(
                    candidate,
                    {
                        "user_id": candidate,
                        "hops": int(reached.get("hops", 0)) + 2,
                        "through": [],
                        "via": [],
                    },
                )
                if first_hop and first_hop not in entry["through"]:
                    entry["through"].append(first_hop)
                shared = set(row.get("via") or []) & set(reached.get("via") or [])
                entry["via"] = sorted(set(entry["via"]) | shared)
        return sorted(
            found.values(), key=lambda item: (-len(item["via"]), item["hops"])
        )[: max(1, limit)]

    def _reachable_fallback(self, *, owner_id: str, allowed: set[str]) -> list[dict]:
        """Same walk in Python, for a deployment where the aggregation is unavailable.

        Mirrors the atlas-or-scan shape used by AccountStore.search_chunks: degrade to a
        slower correct answer rather than an empty one.
        """
        rows = []
        for edge in self.db.memory_edges.find({"owner_id": owner_id}):
            network = [
                {**second, "hops": 0}
                for second in self.db.memory_edges.find(
                    {"owner_id": edge["counterparty_id"]}
                )
                if second.get("owner_id") in allowed
            ]
            rows.append({**edge, "network": network})
        return rows
