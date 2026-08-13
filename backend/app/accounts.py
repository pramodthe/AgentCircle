"""Accounts, profiles, and persona storage for real multi-user AgentCircle.

Separate from `AgentCircleStore`, which still serves the original single-user demo
domain (agents, tasks, intro requests). Both wrap the same Database; this one owns
everything keyed by a real signed-in user.

Every method here takes `user_id` explicitly and filters on it. Callers get that ID
from the auth dependency, never from a request body.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from app.embeddings import cosine_similarity
from app.persona import prune_persona
from app.serializers import serialize

HANDLE_PATTERN = re.compile(r"[^a-z0-9_]+")
RESERVED_HANDLES = {
    "admin", "api", "agent", "agents", "about", "auth", "community", "discover",
    "explore", "feed", "help", "home", "login", "logout", "me", "messages",
    "network", "new", "onboarding", "profile", "register", "search", "settings",
    "signup", "support", "system", "user", "users",
}

PROFILE_TEXT_FIELDS = {
    "display_name": 80,
    "headline": 160,
    "bio": 2000,
    "location": 120,
    "pronouns": 40,
    "organization": 120,
    "role": 120,
    "website": 300,
    "availability": 120,
}
PROFILE_LIST_FIELDS = {
    "skills": 25,
    "interests": 25,
    "looking_for": 10,
    "likes": 25,
    "dislikes": 25,
    "hobbies": 25,
}
DECLARED_SOURCE_TITLE = "What you said about yourself"

# The profile fields that are claims, in the order they read best as prose. `theme` is
# deliberately absent and must stay absent — see the note on PROFILE_THEME_FIELDS.
DECLARED_LIST_FIELDS = (
    ("skills", "Skills"),
    ("interests", "Interested in"),
    ("looking_for", "Looking for"),
    ("likes", "Likes"),
    ("dislikes", "Dislikes"),
    ("hobbies", "Outside work"),
)


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def declared_profile_text(profile: dict[str, Any]) -> str:
    """Render the self-declared half of a profile as plain prose for embedding.

    Labelled lines rather than bare keywords: the text is retrieved and shown as evidence
    to a person, so it has to read like a sentence someone wrote, not a form dump.
    """
    lines: list[str] = []
    name = str(profile.get("display_name") or "").strip()
    role = str(profile.get("role") or "").strip()
    org = str(profile.get("organization") or "").strip()
    if role and org:
        lines.append(f"{name or 'They'} is {_article(role)} {role} at {org}.".strip())
    elif role:
        lines.append(f"{name or 'They'} is {_article(role)} {role}.".strip())
    elif org:
        lines.append(f"{name or 'They'} works at {org}.".strip())
    for key in ("headline", "bio"):
        value = str(profile.get(key) or "").strip()
        if value:
            lines.append(value)
    location = str(profile.get("location") or "").strip()
    if location:
        lines.append(f"Based in {location}.")
    availability = str(profile.get("availability") or "").strip()
    if availability:
        lines.append(f"Availability: {availability}.")
    for key, label in DECLARED_LIST_FIELDS:
        values = [str(item).strip() for item in profile.get(key) or [] if str(item).strip()]
        if values:
            lines.append(f"{label}: {', '.join(values)}.")
    return "\n".join(lines)


# MySpace-style page customization. Stored as opaque presentation state; the agent
# layer never reads it, so a user restyling their page cannot influence retrieval.
PROFILE_THEME_FIELDS = {
    "accent": 24,
    "background": 400,
    "font": 60,
    "layout": 40,
    "song_url": 300,
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def slugify_handle(value: str) -> str:
    handle = HANDLE_PATTERN.sub("", value.strip().lower().replace(" ", "_"))
    return handle.strip("_")[:24]


class AccountStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------ indexes

    def ensure_indexes(self) -> None:
        self.db.users.create_index("email", unique=True)
        self.db.users.create_index("handle", unique=True)
        self.db.users.create_index([("created_at", DESCENDING)])
        self.db.persona_sources.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        self.db.persona_chunks.create_index(
            [("user_id", ASCENDING), ("source_id", ASCENDING), ("ordinal", ASCENDING)]
        )
        self.db.persona_chunks.create_index([("user_id", ASCENDING), ("space", ASCENDING)])
        self.db.persona_chunks.create_index("space")
        self.db.personas.create_index([("updated_at", DESCENDING)])
        self.db.member_settings.create_index([("updated_at", DESCENDING)])

    # -------------------------------------------------------------------- users

    def create_user(
        self,
        *,
        email: str,
        password_hash: str,
        display_name: str,
        handle: str | None = None,
    ) -> dict:
        now = utcnow()
        email = normalize_email(email)
        user_id = uuid4().hex
        document = {
            "_id": user_id,
            "email": email,
            "password_hash": password_hash,
            "display_name": display_name.strip()[:80] or email.split("@")[0],
            "handle": self.allocate_handle(handle or display_name or email.split("@")[0]),
            "onboarding_complete": False,
            "created_at": now,
            "updated_at": now,
        }
        self.db.users.insert_one(document)
        self.db.profiles.insert_one(
            {
                "_id": user_id,
                "user_id": user_id,
                "display_name": document["display_name"],
                "headline": "",
                "bio": "",
                "skills": [],
                "interests": [],
                "looking_for": [],
                "likes": [],
                "dislikes": [],
                "hobbies": [],
                "theme": {"accent": "violet", "layout": "classic"},
                "created_at": now,
                "updated_at": now,
            }
        )
        return document

    def allocate_handle(self, preferred: str) -> str:
        base = slugify_handle(preferred) or f"member{uuid4().hex[:6]}"
        if base in RESERVED_HANDLES:
            base = f"{base}_1"
        candidate = base
        suffix = 1
        while self.db.users.count_documents({"handle": candidate}, limit=1):
            suffix += 1
            candidate = f"{base}{suffix}"[:24]
        return candidate

    def get_user(self, user_id: str) -> dict | None:
        return self.db.users.find_one({"_id": user_id})

    def get_user_by_email(self, email: str) -> dict | None:
        return self.db.users.find_one({"email": normalize_email(email)})

    def get_user_by_handle(self, handle: str) -> dict | None:
        return self.db.users.find_one({"handle": handle.strip().lower()})

    def mark_onboarding_complete(self, user_id: str) -> dict | None:
        return self.db.users.find_one_and_update(
            {"_id": user_id},
            {"$set": {"onboarding_complete": True, "updated_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )

    @staticmethod
    def public_user(user: dict | None) -> dict | None:
        """The signed-in member's own record. Strips credentials, keeps their own email.

        Only ever return this to the account it belongs to. For anybody else use
        `public_member` — this one still carries contact details.
        """
        if not user:
            return None
        safe = {key: value for key, value in user.items() if key != "password_hash"}
        return serialize(safe)

    @staticmethod
    def public_member(user: dict | None) -> dict | None:
        """One member as seen by anyone else: a name, a handle, and nothing to harvest.

        An allowlist rather than a denylist, because the failure mode of the denylist is
        silent — `public_user` was serving `email` to unauthenticated callers on every
        profile page simply because nobody had added it to the strip list. A field added
        to `users` later cannot leak through this.
        """
        if not user:
            return None
        return {
            "_id": str(user["_id"]),
            "display_name": user.get("display_name", ""),
            "handle": user.get("handle", ""),
        }

    # ----------------------------------------------------------------- profiles

    def get_profile(self, user_id: str) -> dict | None:
        return serialize(self.db.profiles.find_one({"_id": user_id}))

    def update_profile(self, user_id: str, payload: dict[str, Any]) -> dict:
        fields: dict[str, Any] = {}
        for key, limit in PROFILE_TEXT_FIELDS.items():
            value = payload.get(key)
            if isinstance(value, str):
                fields[key] = value.strip()[:limit]
        for key, limit in PROFILE_LIST_FIELDS.items():
            value = payload.get(key)
            if isinstance(value, list):
                fields[key] = [
                    str(item).strip()[:80] for item in value if str(item).strip()
                ][:limit]
        theme = payload.get("theme")
        if isinstance(theme, dict):
            fields["theme"] = {
                key: str(theme[key]).strip()[:limit]
                for key, limit in PROFILE_THEME_FIELDS.items()
                if isinstance(theme.get(key), str) and theme[key].strip()
            }
        if not fields:
            return self.get_profile(user_id) or {}
        fields["updated_at"] = utcnow()
        profile = self.db.profiles.find_one_and_update(
            {"_id": user_id},
            {"$set": fields, "$setOnInsert": {"user_id": user_id, "created_at": utcnow()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        # display_name lives on both documents; the user document is what auth reads.
        if "display_name" in fields:
            self.db.users.update_one(
                {"_id": user_id},
                {"$set": {"display_name": fields["display_name"], "updated_at": utcnow()}},
            )
        return serialize(profile)

    # ---------------------------------------------------------- persona sources

    def replace_declared_source(
        self,
        *,
        user_id: str,
        text: str,
        chunks: list[dict[str, Any]],
    ) -> dict | None:
        """Re-derive the one source that holds what a member typed about themselves.

        Everything a member writes in the profile editor is a claim about themselves, and
        the editor says so. Without this, those fields would be display-only while
        retrieval kept answering from uploaded documents alone — so a member could state
        exactly what they want to be found for and never be found for it.

        Deterministic `_id` keyed on the user: saving the profile twelve times leaves one
        source, not twelve, and the previous chunks go with it.
        """
        source_id = f"src_declared_{user_id}"
        self.db.persona_chunks.delete_many({"user_id": user_id, "source_id": source_id})
        if not chunks:
            self.db.persona_sources.delete_one({"_id": source_id})
            return None
        now = utcnow()
        source = {
            "_id": source_id,
            "user_id": user_id,
            "title": DECLARED_SOURCE_TITLE,
            "kind": "declared",
            "detail": "Kept in step with your profile",
            "characters": len(text),
            "chunk_count": len(chunks),
            "preview": text[:400],
            "updated_at": now,
        }
        self.db.persona_sources.update_one(
            {"_id": source_id},
            {"$set": source, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        self.db.persona_chunks.insert_many(
            [
                {
                    "_id": f"chk_{uuid4().hex[:20]}",
                    "user_id": user_id,
                    "source_id": source_id,
                    "source_title": DECLARED_SOURCE_TITLE,
                    "text": chunk["text"],
                    "ordinal": chunk["ordinal"],
                    "characters": chunk["characters"],
                    "embedding": chunk["embedding"],
                    "space": chunk["space"],
                    "visibility": "private",
                    "created_at": now,
                    "updated_at": now,
                }
                for chunk in chunks
            ]
        )
        return serialize(self.db.persona_sources.find_one({"_id": source_id}))

    def add_source(
        self,
        *,
        user_id: str,
        title: str,
        kind: str,
        detail: str,
        text: str,
        chunks: list[dict[str, Any]],
    ) -> dict:
        now = utcnow()
        source_id = f"src_{uuid4().hex[:16]}"
        source = {
            "_id": source_id,
            "user_id": user_id,
            "title": title[:200],
            "kind": kind,
            "detail": detail[:400],
            "characters": len(text),
            "chunk_count": len(chunks),
            "preview": text[:400],
            "created_at": now,
            "updated_at": now,
        }
        self.db.persona_sources.insert_one(source)
        if chunks:
            self.db.persona_chunks.insert_many(
                [
                    {
                        "_id": f"chk_{uuid4().hex[:20]}",
                        "user_id": user_id,
                        "source_id": source_id,
                        "source_title": source["title"],
                        "text": chunk["text"],
                        "ordinal": chunk["ordinal"],
                        "characters": chunk["characters"],
                        "embedding": chunk["embedding"],
                        "space": chunk["space"],
                        "visibility": "private",
                        "created_at": now,
                        "updated_at": now,
                    }
                    for chunk in chunks
                ]
            )
        return serialize(source)

    def list_sources(self, user_id: str) -> list[dict]:
        return serialize(
            list(self.db.persona_sources.find({"user_id": user_id}).sort("created_at", 1))
        )

    def chunk_ids_for_source(self, user_id: str, source_id: str) -> set[str]:
        """The chunks a source owns, for callers that must prune what cited them."""
        return {
            row["_id"]
            for row in self.db.persona_chunks.find(
                {"user_id": user_id, "source_id": source_id}, {"_id": 1}
            )
        }

    def delete_source(self, user_id: str, source_id: str) -> bool:
        result = self.db.persona_sources.delete_one({"_id": source_id, "user_id": user_id})
        if result.deleted_count == 0:
            return False
        removed = {
            row["_id"]
            for row in self.db.persona_chunks.find(
                {"user_id": user_id, "source_id": source_id}, {"_id": 1}
            )
        }
        self.db.persona_chunks.delete_many({"user_id": user_id, "source_id": source_id})
        # The persona now cites chunks that no longer exist. Since extraction is
        # incremental, nothing else would ever remove them.
        persona = self.db.personas.find_one({"_id": user_id})
        if persona and removed:
            pruned = prune_persona(persona, removed)
            extracted = [
                sid for sid in (persona.get("extracted_source_ids") or []) if sid != source_id
            ]
            pruned["extracted_source_ids"] = extracted
            self.db.personas.update_one({"_id": user_id}, {"$set": pruned})
        return True

    def list_chunks(self, user_id: str, *, with_embedding: bool = True) -> list[dict]:
        projection = None if with_embedding else {"embedding": 0}
        return list(
            self.db.persona_chunks.find({"user_id": user_id}, projection).sort(
                [("source_id", ASCENDING), ("ordinal", ASCENDING)]
            )
        )

    def search_chunks(
        self,
        *,
        user_id: str,
        query_vector: list[float],
        space: str,
        limit: int = 6,
        atlas: bool = False,
    ) -> list[dict]:
        """Retrieve a user's own persona chunks for grounded answers.

        Filtered by embedding space so vectors written under a previous provider are
        ignored rather than compared across incompatible spaces.
        """
        if atlas:
            try:
                return serialize(
                    list(
                        self.db.persona_chunks.aggregate(
                            [
                                {
                                    "$vectorSearch": {
                                        "index": "persona_chunks_vector",
                                        "path": "embedding",
                                        "queryVector": query_vector,
                                        "numCandidates": max(50, limit * 10),
                                        "limit": max(1, limit),
                                        "filter": {"user_id": user_id, "space": space},
                                    }
                                },
                                {
                                    "$project": {
                                        "embedding": 0,
                                    }
                                },
                                {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                            ]
                        )
                    )
                )
            except Exception:
                pass

        rows = list(self.db.persona_chunks.find({"user_id": user_id, "space": space}))
        scored: list[dict] = []
        for row in rows:
            row["score"] = round(cosine_similarity(query_vector, row.get("embedding", [])), 4)
            row.pop("embedding", None)
            scored.append(row)
        scored.sort(key=lambda item: item["score"], reverse=True)
        return serialize(scored[: max(1, limit)])

    def chunks_by_user(
        self, *, exclude_user_id: str | None = None, space: str | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Every member's persona chunks, grouped by owner. Full scan.

        Only correct at prototype scale, and only used where the caller genuinely
        needs every chunk. For query-driven retrieval use `search_chunks_global`,
        which pushes the work into Atlas Vector Search instead.
        """
        query: dict[str, Any] = {}
        if exclude_user_id:
            query["user_id"] = {"$ne": exclude_user_id}
        if space:
            query["space"] = space
        grouped: dict[str, list[dict[str, Any]]] = {}
        for chunk in self.db.persona_chunks.find(query):
            grouped.setdefault(chunk["user_id"], []).append(chunk)
        return grouped

    def search_chunks_global(
        self,
        *,
        query_vector: list[float],
        space: str,
        exclude_user_id: str | None = None,
        pool: int = 80,
        atlas: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """Retrieve the most relevant chunks across all members, grouped by owner.

        Prefers `$vectorSearch` so the ranking runs in the database over an indexed
        set rather than pulling every chunk into the API. Falls back to a scored scan
        when the index is absent, which keeps free-tier and offline development working.
        """
        candidate_filter: dict[str, Any] = {"space": space}
        if exclude_user_id:
            candidate_filter["user_id"] = {"$ne": exclude_user_id}

        rows: list[dict[str, Any]] | None = None
        if atlas:
            try:
                rows = list(
                    self.db.persona_chunks.aggregate(
                        [
                            {
                                "$vectorSearch": {
                                    "index": "persona_chunks_vector",
                                    "path": "embedding",
                                    "queryVector": query_vector,
                                    "numCandidates": max(100, pool * 10),
                                    "limit": pool,
                                    "filter": candidate_filter,
                                }
                            },
                            {
                                "$project": {
                                    "user_id": 1,
                                    "text": 1,
                                    "source_id": 1,
                                    "source_title": 1,
                                    "ordinal": 1,
                                    "space": 1,
                                    "score": {"$meta": "vectorSearchScore"},
                                }
                            },
                        ]
                    )
                )
            except Exception:
                rows = None

        if rows is None:
            rows = []
            for chunk in self.db.persona_chunks.find(candidate_filter):
                chunk["score"] = cosine_similarity(query_vector, chunk.get("embedding", []))
                chunk.pop("embedding", None)
                rows.append(chunk)
            rows.sort(key=lambda row: row["score"], reverse=True)
            rows = rows[:pool]

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["user_id"], []).append(row)
        return grouped

    def users_by_id(self, user_ids: list[str]) -> dict[str, dict]:
        rows = self.db.users.find({"_id": {"$in": user_ids}})
        return {row["_id"]: self.public_member(row) for row in rows}

    def profiles_by_id(self, user_ids: list[str]) -> dict[str, dict]:
        rows = self.db.profiles.find({"_id": {"$in": user_ids}})
        return {row["_id"]: serialize(row) for row in rows}

    # -------------------------------------------------------- member settings

    def get_member_settings(self, user_id: str) -> dict:
        return self.db.member_settings.find_one({"_id": user_id}) or {}

    def undiscoverable_ids(self) -> set[str]:
        """Members who have opted out of being surfaced in search.

        Opt-*out* rather than opt-in: a network nobody can be found in is not a
        network, and being listed is the reason people join. But someone between jobs,
        or who joined only to answer questions, needs a way to stop appearing without
        deleting their account.
        """
        rows = self.db.member_settings.find({"discoverable": False}, {"_id": 1})
        return {row["_id"] for row in rows}

    def photo_search_opted_in_ids(self) -> set[str]:
        """Members who turned photo search on. Opt-in, so absence means no."""
        rows = self.db.member_settings.find({"photo_search_enabled": True}, {"_id": 1})
        return {row["_id"] for row in rows}

    def update_member_settings(self, user_id: str, patch: dict[str, Any]) -> dict:
        now = utcnow()
        self.db.member_settings.update_one(
            {"_id": user_id},
            {"$set": {**patch, "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return serialize(self.db.member_settings.find_one({"_id": user_id}))

    def all_member_settings(self) -> dict[str, dict]:
        return {row["_id"]: row for row in self.db.member_settings.find({})}

    # ---------------------------------------------------------------- personas

    def save_persona(self, user_id: str, persona: dict[str, Any]) -> dict:
        now = utcnow()
        document = {**persona, "user_id": user_id, "updated_at": now}
        self.db.personas.update_one(
            {"_id": user_id},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return serialize(self.db.personas.find_one({"_id": user_id}))

    def get_persona(self, user_id: str) -> dict | None:
        return serialize(self.db.personas.find_one({"_id": user_id}))

    # -------------------------------------------------------------- onboarding

    def onboarding_state(self, user_id: str) -> dict:
        user = self.get_user(user_id) or {}
        profile = self.get_profile(user_id) or {}
        sources = self.list_sources(user_id)
        persona = self.get_persona(user_id)
        steps = {
            "account": True,
            "profile": bool(profile.get("headline") or profile.get("bio")),
            "sources": len(sources) > 0,
            "extras": bool(
                profile.get("interests") or profile.get("hobbies") or profile.get("looking_for")
            ),
            "persona": bool(persona),
        }
        return {
            "complete": bool(user.get("onboarding_complete")) or all(steps.values()),
            "steps": steps,
            "source_count": len(sources),
            "coverage": (persona or {}).get("coverage", {"missing": [], "score": 0.0}),
        }
