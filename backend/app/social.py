"""Connections and the feed.

The feed is the reason this product is a social network rather than a search tool. Its
job is **context intake**: what people write about what they are doing is the richest,
freshest signal about them, and unlike a resume it accrues without anyone being asked
to maintain it. So a post is not stored and forgotten — it is chunked, embedded, and
added to the author's persona, which means tomorrow's discovery query can find someone
because of what they posted today, and an agent can cite that post as evidence.

A post that never feeds retrieval would be decoration. That is the line this module
exists to hold.

Connections carry provenance — whether they came from discovery, an interview, a
community thread, or a direct request — because "how did these two people find each
other" is exactly the signal that tells you which part of the product actually works.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from app.serializers import serialize

CONNECTION_SOURCES = ("discovery", "interview", "community", "direct", "feed")
CONNECTION_STATES = ("pending", "accepted", "ignored", "withdrawn")

REACTIONS = ("like", "insightful", "same")

MAX_POST_CHARACTERS = 4000
# Posts shorter than this are pleasantries — indexing them pollutes retrieval with
# "congrats!" and teaches the agent nothing about the author.
MIN_INGEST_CHARACTERS = 120
# Stories clear a lower bar because of what they are, not to be lenient. A post is a
# standing claim and needs enough text to be worth retrieving; a story is one dated
# episode — "shipped the replay path after three weeks of backpressure bugs" is 70
# characters and is exactly the kind of thing an agent should be able to recall. The
# floor still sits well above "congrats!", which is what MIN_INGEST_CHARACTERS is for.
MIN_STORY_INGEST_CHARACTERS = 60
# How long a story stays in the story strip. The *card* is what expires; the memory it
# became does not, and the composer says so before you post. See `story_is_active`.
STORY_ACTIVE_HOURS = 24

ALLOWED_CLIP_TYPES = {
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}
MAX_CLIP_BYTES = 20 * 1024 * 1024


def utcnow() -> datetime:
    return datetime.now(UTC)


def _validate_clip(*, data: bytes, media_type: str) -> None:
    from app.media import MediaError

    if media_type not in ALLOWED_CLIP_TYPES:
        raise MediaError(
            f"{media_type or 'That file type'} is not supported for clips. Use MP4, WebM, or MOV."
        )
    if not data:
        raise MediaError("That file was empty.")
    if len(data) > MAX_CLIP_BYTES:
        raise MediaError(f"Clips must be under {MAX_CLIP_BYTES // (1024 * 1024)}MB.")


def pair_id(left: str, right: str) -> str:
    """Canonical, order-independent id so a pair can only have one connection."""
    return ":".join(sorted((left, right)))


class ConnectionStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.connections.create_index(
            [("members", ASCENDING), ("status", ASCENDING), ("updated_at", DESCENDING)]
        )
        self.db.connections.create_index([("requester_id", ASCENDING)])
        self.db.connections.create_index([("recipient_id", ASCENDING), ("status", ASCENDING)])

    def request(
        self,
        *,
        requester_id: str,
        recipient_id: str,
        note: str = "",
        source: str = "direct",
        context_id: str | None = None,
    ) -> dict:
        if requester_id == recipient_id:
            raise PermissionError("You cannot connect with yourself")
        if source not in CONNECTION_SOURCES:
            raise ValueError(f"Unknown connection source: {source}")

        now = utcnow()
        key = pair_id(requester_id, recipient_id)
        existing = self.db.connections.find_one({"_id": key})

        if existing:
            if existing["status"] == "accepted":
                return serialize(existing)
            # A pending request from the other side becomes an acceptance rather than a
            # second, competing request — two people reaching for each other is a
            # connection, not a conflict.
            if existing["status"] == "pending" and existing["recipient_id"] == requester_id:
                return self.respond(
                    pair=key, recipient_id=requester_id, accept=True
                )
            if existing["status"] == "pending":
                return serialize(existing)

        document = {
            "_id": key,
            "members": sorted((requester_id, recipient_id)),
            "requester_id": requester_id,
            "recipient_id": recipient_id,
            "status": "pending",
            "note": note[:400],
            "source": source,
            "context_id": context_id,
            "updated_at": now,
        }
        self.db.connections.update_one(
            {"_id": key}, {"$set": document, "$setOnInsert": {"created_at": now}}, upsert=True
        )
        return serialize(self.db.connections.find_one({"_id": key}))

    def respond(self, *, pair: str, recipient_id: str, accept: bool) -> dict | None:
        """Only the recipient of a pending request may answer it."""
        row = self.db.connections.find_one({"_id": pair})
        if row is None or row["status"] != "pending":
            return None
        if row["recipient_id"] != recipient_id:
            raise PermissionError("Only the person who received the request can answer it")
        now = utcnow()
        return serialize(
            self.db.connections.find_one_and_update(
                {"_id": pair},
                {
                    "$set": {
                        "status": "accepted" if accept else "ignored",
                        "responded_at": now,
                        "updated_at": now,
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        )

    def withdraw(self, *, pair: str, requester_id: str) -> dict | None:
        row = self.db.connections.find_one({"_id": pair})
        if row is None or row["status"] != "pending":
            return None
        if row["requester_id"] != requester_id:
            raise PermissionError("Only the requester can withdraw a request")
        return serialize(
            self.db.connections.find_one_and_update(
                {"_id": pair},
                {"$set": {"status": "withdrawn", "updated_at": utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
        )

    def status_between(self, user_id: str, other_id: str) -> dict | None:
        return serialize(self.db.connections.find_one({"_id": pair_id(user_id, other_id)}))

    def connections_for(self, user_id: str) -> list[dict]:
        return serialize(
            list(
                self.db.connections.find({"members": user_id, "status": "accepted"}).sort(
                    "updated_at", DESCENDING
                )
            )
        )

    def connected_ids(self, user_id: str) -> list[str]:
        rows = self.db.connections.find(
            {"members": user_id, "status": "accepted"}, {"members": 1}
        )
        return [
            member
            for row in rows
            for member in row["members"]
            if member != user_id
        ]

    def pending_for(self, user_id: str) -> dict[str, list[dict]]:
        incoming = list(
            self.db.connections.find({"recipient_id": user_id, "status": "pending"}).sort(
                "updated_at", DESCENDING
            )
        )
        outgoing = list(
            self.db.connections.find({"requester_id": user_id, "status": "pending"}).sort(
                "updated_at", DESCENDING
            )
        )
        return {"incoming": serialize(incoming), "outgoing": serialize(outgoing)}

    def provenance_counts(self, user_id: str) -> dict[str, int]:
        """Which parts of the product actually produced connections."""
        counts: dict[str, int] = {}
        for row in self.db.connections.find({"members": user_id, "status": "accepted"}):
            source = row.get("source", "direct")
            counts[source] = counts.get(source, 0) + 1
        return counts


class FeedStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.feed_posts.create_index([("created_at", DESCENDING)])
        self.db.feed_posts.create_index([("author_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.feed_reactions.create_index(
            [("post_id", ASCENDING), ("user_id", ASCENDING)], unique=True
        )

    def create(
        self,
        *,
        author_id: str,
        body: str,
        kind: Literal["human", "agent"] = "human",
        presentation: Literal["post", "story"] = "post",
        evidence: list[dict[str, Any]] | None = None,
        ingested: bool = False,
        image_media_id: str | None = None,
        image_media_type: str | None = None,
        location: str | None = None,
    ) -> dict:
        now = utcnow()
        document = {
            "_id": f"fp_{uuid4().hex[:16]}",
            "author_id": author_id,
            "body": body.strip()[:MAX_POST_CHARACTERS],
            "kind": kind,
            "presentation": presentation,
            # Agent posts carry what they were derived from, so a reader can check the
            # claim rather than take the agent's word for it.
            "evidence": evidence or [],
            "ingested": ingested,
            "reaction_counts": {},
            "created_at": now,
            "updated_at": now,
        }
        # Feed attachments are presentation only — never persona_media / §9 search.
        if image_media_id:
            document["image_media_id"] = image_media_id
            document["image_media_type"] = image_media_type or "image/jpeg"
        if location:
            document["location"] = location.strip()[:80]
        self.db.feed_posts.insert_one(document)
        return serialize(document)

    def save_feed_media(
        self,
        *,
        user_id: str,
        data: bytes,
        media_type: str,
        kind: Literal["story", "post", "clip"] = "post",
    ) -> tuple[str, str]:
        """Store a feed attachment as presentation bytes — never searchable.

        Stories, post photos and clips share one blob path under `fm_*` / `sm_*`,
        kept out of persona_media so §9 photo search cannot see them.
        """
        from app.profile_media import validate_profile_photo

        if kind == "clip":
            _validate_clip(data=data, media_type=media_type)
        else:
            validate_profile_photo(image=data, media_type=media_type)

        prefix = "sm" if kind == "story" else "fm"
        media_id = f"{prefix}_{uuid4().hex[:16]}"
        self.db.media_blobs.replace_one(
            {"_id": media_id},
            {
                "_id": media_id,
                "user_id": user_id,
                "media_type": media_type,
                "bytes": data,
                "kind": kind,
            },
            upsert=True,
        )
        self.db.feed_media.replace_one(
            {"_id": media_id},
            {
                "_id": media_id,
                "user_id": user_id,
                "media_type": media_type,
                "kind": kind,
                "size_bytes": len(data),
                "created_at": utcnow(),
            },
            upsert=True,
        )
        # Keep the older story_media collection in sync so existing story routes still
        # resolve while the feed_media table becomes the one door for all attachments.
        if kind == "story":
            self.db.story_media.replace_one(
                {"_id": media_id},
                {
                    "_id": media_id,
                    "user_id": user_id,
                    "media_type": media_type,
                    "size_bytes": len(data),
                    "created_at": utcnow(),
                },
                upsert=True,
            )
        return media_id, media_type

    def save_story_image(
        self, *, user_id: str, image: bytes, media_type: str
    ) -> tuple[str, str]:
        return self.save_feed_media(
            user_id=user_id, data=image, media_type=media_type, kind="story"
        )

    def feed_media_owned(self, media_id: str) -> dict | None:
        if not (media_id.startswith("sm_") or media_id.startswith("fm_")):
            return None
        row = self.db.feed_media.find_one({"_id": media_id})
        if row is None:
            row = self.db.story_media.find_one({"_id": media_id})
        return serialize(row) if row else None

    def story_image_owned(self, media_id: str) -> dict | None:
        return self.feed_media_owned(media_id)

    def feed_blob(self, media_id: str) -> dict | None:
        if self.feed_media_owned(media_id) is None:
            return None
        return self.db.media_blobs.find_one({"_id": media_id})

    def story_blob(self, media_id: str) -> dict | None:
        return self.feed_blob(media_id)

    def mark_ingested(self, post_id: str, chunk_count: int) -> None:
        self.db.feed_posts.update_one(
            {"_id": post_id},
            {"$set": {"ingested": True, "ingested_chunks": chunk_count, "updated_at": utcnow()}},
        )

    def list_feed(
        self, *, viewer_id: str, connected_ids: list[str], limit: int = 40
    ) -> list[dict]:
        """Connections first, then the wider network.

        A young network with only connection posts is empty, so the rest of the
        network is still shown — just after the people you actually know.
        """
        rows = list(
            self.db.feed_posts.find({}).sort("created_at", DESCENDING).limit(max(1, limit) * 2)
        )
        circle = set(connected_ids) | {viewer_id}
        rows.sort(
            key=lambda row: (row["author_id"] not in circle, -row["created_at"].timestamp())
        )
        return serialize(rows[:limit])

    def get(self, post_id: str) -> dict | None:
        return serialize(self.db.feed_posts.find_one({"_id": post_id}))

    def react(self, *, post_id: str, user_id: str, reaction: str | None) -> dict | None:
        if reaction is not None and reaction not in REACTIONS:
            raise ValueError(f"Unknown reaction: {reaction}")
        if self.db.feed_posts.find_one({"_id": post_id}) is None:
            return None

        if reaction is None:
            self.db.feed_reactions.delete_one({"post_id": post_id, "user_id": user_id})
        else:
            self.db.feed_reactions.update_one(
                {"post_id": post_id, "user_id": user_id},
                {"$set": {"reaction": reaction, "updated_at": utcnow()}},
                upsert=True,
            )

        # Recount rather than increment so changing a reaction cannot drift the total.
        counts: dict[str, int] = {}
        for row in self.db.feed_reactions.find({"post_id": post_id}):
            counts[row["reaction"]] = counts.get(row["reaction"], 0) + 1
        return serialize(
            self.db.feed_posts.find_one_and_update(
                {"_id": post_id},
                {"$set": {"reaction_counts": counts, "updated_at": utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
        )

    def my_reactions(self, user_id: str, post_ids: list[str]) -> dict[str, str]:
        rows = self.db.feed_reactions.find(
            {"user_id": user_id, "post_id": {"$in": post_ids}}
        )
        return {row["post_id"]: row["reaction"] for row in rows}


def should_ingest(body: str, presentation: str = "post") -> bool:
    """Whether a post is substantial enough to become retrievable context."""
    floor = MIN_STORY_INGEST_CHARACTERS if presentation == "story" else MIN_INGEST_CHARACTERS
    return len(body.strip()) >= floor


def episodic_title(created_at: datetime | str) -> str:
    """What a story is filed under: an episode with a date on it.

    Stories are ingested as `kind="episodic"` rather than `kind="post"` because the two
    are different claims about a person. A post says what someone knows; a story says
    what happened to them on a day. Keeping the date in the title is what lets a cited
    answer read "in August they shipped…" instead of stating an episode as a standing
    fact — an agent that forgets *when* turns a bad week into a permanent trait.
    """
    stamp = created_at if isinstance(created_at, str) else created_at.isoformat()
    return f"Story · {stamp[:10]}"


def story_is_active(post: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Whether a story still belongs in the story strip.

    Only the card is ephemeral. The post stays in the feed and the episodic memory it
    became stays in the persona — a story that vanished from retrieval would make the
    agent's account of someone's year depend on when you asked.
    """
    if post.get("presentation") != "story":
        return False
    created = post.get("created_at")
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    if not isinstance(created, datetime):
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (now or utcnow()) - created < timedelta(hours=STORY_ACTIVE_HOURS)


def build_agent_post(
    *, display_name: str, gaps: list[dict[str, Any]], interviews: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Compose an agent post from what actually happened, not from a model.

    Deliberately templated over stored activity rather than generated. The value of an
    agent post is that it reports real events — how many questions it could not answer,
    how many interviews it ran — and a model asked to write that would embellish it.
    Nothing here can say anything the counts do not support.
    """
    if not gaps and not interviews:
        return None

    parts: list[str] = []
    evidence: list[dict[str, Any]] = []

    if gaps:
        questions = [gap["question"] for gap in gaps[:3]]
        parts.append(
            f"{display_name}'s agent was asked {len(gaps)} question"
            f"{'' if len(gaps) == 1 else 's'} it couldn't answer this week"
            + (f", including: {questions[0]}" if questions else "")
        )
        evidence.extend(
            {"kind": "gap", "id": gap["_id"], "detail": gap["question"]} for gap in gaps[:3]
        )

    if interviews:
        answered = sum(row.get("answered_count", 0) for row in interviews)
        asked = sum(row.get("question_count", 0) for row in interviews)
        parts.append(
            f"It ran {len(interviews)} agent interview"
            f"{'' if len(interviews) == 1 else 's'}, answering {answered} of {asked} questions"
            " from its own documents"
        )
        evidence.extend(
            {"kind": "interview", "id": row["_id"], "detail": row.get("goal", "")}
            for row in interviews[:3]
        )

    return {"body": _join_sentences(parts), "evidence": evidence}


def _join_sentences(parts: list[str]) -> str:
    """Join clauses without doubling terminal punctuation.

    A clause often ends by quoting a question, so naively appending "." produces
    "…what are you looking for?." — small, but it reads as machine-written slop in
    exactly the surface that is trying to look considered.
    """
    sentences = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        sentences.append(text if text[-1] in ".?!" else f"{text}.")
    return " ".join(sentences)
