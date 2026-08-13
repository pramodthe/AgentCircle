"""Agent Community — posts answered by other members' agents.

The point of this surface is that it is alive at low member count: a post gets real
responses because agents answer, and each agent is grounded in a real person you can
reach. That only works if the comments are worth reading, which is why the two rules
below are enforced here rather than left to a prompt.

  Recruitment is bounded.  Every comment is an LLM call, so fan-out is the dominant
  cost of the product. Responders are selected by semantic fit against their own
  persona chunks, filtered by consent, and capped.

  Declining is a first-class outcome.  An agent with no grounding in the topic returns
  `declined: true` and is stored that way. Agents that stay silent are what make the
  ones that speak worth reading, and each decline is demand signal for the gap
  detector: someone wanted an answer this persona could not give.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.database import Database

from app.embeddings import cosine_similarity
from app.outcomes import NEUTRAL_TRUST
from app.serializers import serialize

# Consent is per-topic. An agent speaks publicly under a real person's name, so this
# defaults closed for anything the member has not opted into.
COMMENT_TOPICS = (
    "product",
    "engineering",
    "design",
    "hiring",
    "fundraising",
    "go_to_market",
    "research",
    "operations",
)

DEFAULT_COMMUNITY_SETTINGS = {
    "comment_enabled": False,
    "comment_topics": [],
    "review_before_publish": True,
    # Opt-out, not opt-in: being findable is why people join, but someone between
    # jobs needs a way to stop appearing without deleting their account.
    "discoverable": True,
    # Opt-IN, unlike `discoverable`, and the asymmetry is deliberate (spec §9). Being
    # searchable for what you wrote is the deal you signed up for; having your face and
    # your weekends indexed is a separate decision that has to be made on purpose.
    "photo_search_enabled": False,
    # Opt-in too. Anyone can search a name; an agent that fans out across sources and
    # assembles a dossier is a different act, and the subject gets to refuse it.
    "research_enabled": False,
}

MAX_RESPONDERS = 6
# Below this the persona simply is not about the topic; generating anyway produces the
# generic encouragement that kills a community like this.
MIN_RECRUIT_SCORE = 0.12

# Words that carry no signal about what was actually being asked.
QUESTION_FILLER = {
    "a", "about", "actually", "an", "and", "any", "anything", "are", "at", "be", "been",
    "can", "could", "did", "do", "does", "doing", "for", "from", "get", "had", "has",
    "have", "how", "i", "in", "is", "it", "just", "kind", "like", "me", "much", "my",
    "of", "on", "or", "really", "s", "so", "some", "that", "the", "their", "them",
    "there", "they", "this", "to", "up", "was", "we", "were", "what", "when", "where",
    "which", "who", "why", "will", "with", "would", "you", "your",
}

TOPIC_HINTS = {
    "product": ("product", "roadmap", "onboarding", "activation", "user", "feature"),
    "engineering": ("engineer", "backend", "infrastructure", "system", "api", "database"),
    "design": ("design", "interface", "typography", "brand", "ux", "prototype"),
    "hiring": ("hiring", "recruit", "candidate", "interview", "team"),
    "fundraising": ("fundrais", "investor", "seed", "valuation", "pitch"),
    "go_to_market": ("go-to-market", "sales", "marketing", "growth", "pricing", "customer"),
    "research": ("research", "evaluation", "citation", "evidence", "benchmark", "study"),
    "operations": ("operations", "workflow", "process", "clinical", "logistics", "supply"),
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def infer_topics(text: str) -> list[str]:
    """Cheap topic tags used for consent filtering before any model call."""
    lowered = text.lower()
    return [
        topic for topic, hints in TOPIC_HINTS.items() if any(hint in lowered for hint in hints)
    ]


def safe_community_settings(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    topics = payload.get("comment_topics")
    return {
        "comment_enabled": bool(payload.get("comment_enabled", False)),
        "comment_topics": (
            [topic for topic in topics if topic in COMMENT_TOPICS][: len(COMMENT_TOPICS)]
            if isinstance(topics, list)
            else []
        ),
        "review_before_publish": bool(payload.get("review_before_publish", True)),
        "discoverable": bool(payload.get("discoverable", True)),
        "photo_search_enabled": bool(payload.get("photo_search_enabled", False)),
        "research_enabled": bool(payload.get("research_enabled", False)),
    }


class CommunityStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.community_posts.create_index([("created_at", DESCENDING)])
        self.db.community_posts.create_index([("author_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.community_comments.create_index(
            [("post_id", ASCENDING), ("created_at", ASCENDING)]
        )
        # One comment per responder per post: re-running recruitment updates rather
        # than stacking duplicate opinions from the same agent.
        self.db.community_comments.create_index(
            [("post_id", ASCENDING), ("responder_id", ASCENDING)], unique=True
        )
        self.db.community_comments.create_index([("responder_id", ASCENDING)])
        self.db.comment_votes.create_index(
            [("comment_id", ASCENDING), ("voter_id", ASCENDING)], unique=True
        )
        self.db.context_gaps.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])

    # -------------------------------------------------------------------- posts

    def create_post(
        self, *, author_id: str, title: str, body: str, topics: list[str] | None = None
    ) -> dict:
        now = utcnow()
        post_id = f"post_{uuid4().hex[:16]}"
        document = {
            "_id": post_id,
            "author_id": author_id,
            "title": title.strip()[:200],
            "body": body.strip()[:6000],
            "topics": topics if topics is not None else infer_topics(f"{title} {body}"),
            "comment_count": 0,
            "declined_count": 0,
            "recruited_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.db.community_posts.insert_one(document)
        return serialize(document)

    def get_post(self, post_id: str) -> dict | None:
        return serialize(self.db.community_posts.find_one({"_id": post_id}))

    def list_posts(self, *, limit: int = 30) -> list[dict]:
        return serialize(
            list(
                self.db.community_posts.find({})
                .sort("created_at", DESCENDING)
                .limit(max(1, min(limit, 100)))
            )
        )

    def mark_recruited(self, post_id: str, *, commented: int, declined: int) -> dict | None:
        return serialize(
            self.db.community_posts.find_one_and_update(
                {"_id": post_id},
                {
                    "$set": {
                        "recruited_at": utcnow(),
                        "comment_count": commented,
                        "declined_count": declined,
                        "updated_at": utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        )

    # ----------------------------------------------------------------- comments

    def save_comment(
        self,
        *,
        post_id: str,
        responder_id: str,
        body: str,
        citations: list[dict[str, Any]],
        declined: bool,
        decline_reason: str | None,
        runtime_mode: str,
        model: str | None,
        recruit_score: float,
        published: bool,
    ) -> dict:
        now = utcnow()
        comment_id = f"cmt_{post_id}_{responder_id}"
        document = {
            "_id": comment_id,
            "post_id": post_id,
            "responder_id": responder_id,
            "body": body[:2400],
            "citations": citations,
            "declined": declined,
            "decline_reason": decline_reason,
            "runtime_mode": runtime_mode,
            "model": model,
            "recruit_score": round(recruit_score, 4),
            "published": published,
            "score": 0,
            "up_votes": 0,
            "down_votes": 0,
            "updated_at": now,
        }
        self.db.community_comments.update_one(
            {"_id": comment_id},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        return serialize(self.db.community_comments.find_one({"_id": comment_id}))

    def list_comments(self, post_id: str, *, include_declined: bool = True) -> list[dict]:
        query: dict[str, Any] = {"post_id": post_id}
        if not include_declined:
            query["declined"] = False
        rows = list(self.db.community_comments.find(query))
        # Answers first, best-voted first; declines are kept but sink to the bottom.
        rows.sort(key=lambda row: (row.get("declined", False), -row.get("score", 0)))
        return serialize(rows)

    def publish_comment(self, comment_id: str, responder_id: str) -> dict | None:
        return serialize(
            self.db.community_comments.find_one_and_update(
                {"_id": comment_id, "responder_id": responder_id},
                {"$set": {"published": True, "updated_at": utcnow()}},
                return_document=ReturnDocument.AFTER,
            )
        )

    def list_pending_review(self, responder_id: str) -> list[dict]:
        return serialize(
            list(
                self.db.community_comments.find(
                    {"responder_id": responder_id, "published": False, "declined": False}
                ).sort("created_at", DESCENDING)
            )
        )

    # -------------------------------------------------------------------- votes

    def vote(self, *, comment_id: str, voter_id: str, value: int) -> dict | None:
        """Record a vote and recompute the comment's tally.

        Recomputed from the vote documents rather than incremented, so changing a vote
        cannot drift the total.
        """
        if value not in (-1, 0, 1):
            raise ValueError("vote must be -1, 0, or 1")
        comment = self.db.community_comments.find_one({"_id": comment_id})
        if comment is None:
            return None
        if comment["responder_id"] == voter_id:
            raise PermissionError("You cannot vote on your own agent's comment")

        if value == 0:
            self.db.comment_votes.delete_one({"comment_id": comment_id, "voter_id": voter_id})
        else:
            self.db.comment_votes.update_one(
                {"comment_id": comment_id, "voter_id": voter_id},
                {"$set": {"value": value, "updated_at": utcnow()}},
                upsert=True,
            )

        votes = list(self.db.comment_votes.find({"comment_id": comment_id}))
        up = sum(1 for row in votes if row["value"] > 0)
        down = sum(1 for row in votes if row["value"] < 0)
        return serialize(
            self.db.community_comments.find_one_and_update(
                {"_id": comment_id},
                {
                    "$set": {
                        "up_votes": up,
                        "down_votes": down,
                        "score": up - down,
                        "updated_at": utcnow(),
                    }
                },
                return_document=ReturnDocument.AFTER,
            )
        )

    def my_votes(self, voter_id: str, post_id: str) -> dict[str, int]:
        comment_ids = [
            row["_id"] for row in self.db.community_comments.find({"post_id": post_id}, {"_id": 1})
        ]
        rows = self.db.comment_votes.find(
            {"voter_id": voter_id, "comment_id": {"$in": comment_ids}}
        )
        return {row["comment_id"]: row["value"] for row in rows}

    # --------------------------------------------------------------- reputation

    def comment_reputation(self, responder_id: str) -> float:
        """How much this member's agent has been worth reading, as a 0..1 multiplier.

        New members sit at the neutral 0.5 rather than at zero — otherwise nobody
        without history could ever be recruited, and the community could not grow.
        """
        rows = list(
            self.db.community_comments.find(
                {"responder_id": responder_id, "declined": False},
                {"score": 1},
            )
        )
        if not rows:
            return 0.5
        total = sum(row.get("score", 0) for row in rows)
        average = total / len(rows)
        # Squash to 0..1 with 0 net votes landing at neutral.
        return round(max(0.05, min(1.0, 0.5 + average / 6)), 4)

    # ------------------------------------------------------------ context gaps

    def record_gap(
        self, *, user_id: str, question: str, source: str, post_id: str | None = None
    ) -> dict:
        """A question this member's agent could not answer. Demand signal, not an error."""
        now = utcnow()
        document = {
            "_id": f"gap_{uuid4().hex[:16]}",
            "user_id": user_id,
            "question": question[:400],
            "source": source,
            "post_id": post_id,
            "resolved": False,
            "created_at": now,
        }
        self.db.context_gaps.insert_one(document)
        return serialize(document)

    def list_gaps(self, user_id: str, *, limit: int = 20) -> list[dict]:
        return serialize(
            list(
                self.db.context_gaps.find({"user_id": user_id, "resolved": False})
                .sort("created_at", DESCENDING)
                .limit(limit)
            )
        )

    def gap_demand(self, user_id: str, *, limit: int = 8) -> list[dict]:
        """What people keep asking that this member's persona cannot answer.

        Grouped by a normalized form of the question so "what have you shipped?" and
        "What have you shipped" count as the same demand rather than two separate
        one-offs. The count is the point: one person asking is noise, five asking is a
        hole in the profile worth filling.
        """
        buckets: dict[str, dict[str, Any]] = {}
        for row in self.db.context_gaps.find({"user_id": user_id, "resolved": False}):
            key = normalize_question(row["question"])
            bucket = buckets.setdefault(
                key,
                {
                    "key": key,
                    "question": row["question"],
                    "count": 0,
                    "sources": set(),
                    "ids": [],
                    "last_asked": row["created_at"],
                },
            )
            bucket["count"] += 1
            bucket["sources"].add(row.get("source", "unknown"))
            bucket["ids"].append(row["_id"])
            if row["created_at"] > bucket["last_asked"]:
                bucket["last_asked"] = row["created_at"]

        rows = [
            {**bucket, "sources": sorted(bucket["sources"])} for bucket in buckets.values()
        ]
        rows.sort(key=lambda row: (-row["count"], -row["last_asked"].timestamp()))
        return serialize(rows[:limit])

    def resolve_gaps(self, user_id: str, gap_ids: list[str]) -> int:
        """Mark gaps answered. Scoped to the owner so nobody can clear someone else's."""
        result = self.db.context_gaps.update_many(
            {"_id": {"$in": gap_ids}, "user_id": user_id},
            {"$set": {"resolved": True, "resolved_at": utcnow()}},
        )
        return result.modified_count


def rank_responders(
    *,
    query_vector: list[float],
    space: str,
    chunks_by_user: dict[str, list[dict[str, Any]]],
    reputation: dict[str, float],
    topics: list[str],
    settings_by_user: dict[str, dict[str, Any]],
    trust: dict[str, float] | None = None,
    confidence_multiplier: float = 1.0,
    limit: int = MAX_RESPONDERS,
) -> list[dict[str, Any]]:
    """Pick which agents get asked to comment.

    Semantic fit is measured against a member's *best* persona chunk rather than their
    average: a specialist whose single relevant chunk is a strong match should beat a
    generalist who is vaguely near the topic everywhere.

    Three multipliers on top of that fit, each earning its place:
      reputation — has this agent's past commenting been worth reading;
      trust      — what the asker (and, weakly, the network) learned from actually
                   meeting this person, which is what makes the loop close;
      confidence — damping when the asker's *own* agent has been over-promising.

    Trust is a multiplier rather than an additive term on purpose: it should be able
    to demote someone the asker has had a bad experience with, without ever promoting
    an irrelevant person into the thread.
    """
    trust = trust or {}
    ranked: list[dict[str, Any]] = []
    for user_id, chunks in chunks_by_user.items():
        settings = settings_by_user.get(user_id) or DEFAULT_COMMUNITY_SETTINGS
        if not settings.get("comment_enabled"):
            continue
        allowed = settings.get("comment_topics") or []
        # An untagged post is open to anyone who opted in at all; a tagged post
        # requires an overlapping opt-in.
        if topics and allowed and not set(topics) & set(allowed):
            continue

        best: dict[str, Any] | None = None
        best_score = 0.0
        for chunk in chunks:
            if chunk.get("space") != space:
                continue
            # Atlas Vector Search already scored and ranked these; only recompute when
            # the caller handed us raw chunks (local fallback, tests).
            if "score" in chunk:
                score = float(chunk["score"])
            elif chunk.get("embedding"):
                score = cosine_similarity(query_vector, chunk["embedding"])
            else:
                continue
            if score > best_score:
                best_score = score
                best = chunk
        if best is None or best_score < MIN_RECRUIT_SCORE:
            continue

        weight = reputation.get(user_id, 0.5)
        trust_value = trust.get(user_id, NEUTRAL_TRUST)
        reputation_factor = 0.5 + weight / 2
        # Trust demotes; it never promotes. Neutral leaves the score untouched, a bad
        # history pulls it down, and a good history is *not* allowed to push someone
        # above people who know the topic better. Expertise is what makes a comment
        # worth reading; how much you like someone is not.
        trust_factor = min(1.0, 0.55 + trust_value * 0.9)
        ranked.append(
            {
                "user_id": user_id,
                "semantic_score": round(best_score, 4),
                "reputation": weight,
                "trust": round(trust_value, 4),
                "recruit_score": round(
                    best_score * reputation_factor * trust_factor * confidence_multiplier, 4
                ),
                "best_chunk_id": best["_id"],
            }
        )

    ranked.sort(key=lambda row: row["recruit_score"], reverse=True)
    return ranked[: max(1, limit)]


def normalize_topics(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [value for value in values if value in COMMENT_TOPICS]


def normalize_question(question: str) -> str:
    """Collapse near-duplicate questions so repeated demand is counted as repeated.

    Punctuation, casing, and filler words differ every time the same thing is asked;
    what matters is the content words.
    """
    tokens = re.findall(r"[a-z0-9]+", question.lower())
    meaningful = [token for token in tokens if token not in QUESTION_FILLER]
    return " ".join(sorted(set(meaningful)))[:200]


def summarize_question(title: str, body: str) -> str:
    """A short form of the post, used as the recorded question for a decline."""
    text = f"{title}. {body}".strip()
    text = re.sub(r"\s+", " ", text)
    return text[:300]
