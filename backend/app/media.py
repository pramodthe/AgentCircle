"""Photos as retrieval evidence, under the constraint that makes them safe to have.

Spec §9 is the whole design here: photo search **may** match on activity, setting and
context ("photos showing climbing", "the workshop I met them at") and **must not** offer
filtering on physical or demographic attributes. The underlying capability is identical
either way — a multimodal embedding will happily match "person with red hair" — so the
framing has to be enforced in code, not promised in a docstring. Four mechanisms:

1. **Opt-in.** `photo_search_enabled` defaults False. A member's face is not indexed
   because they uploaded an avatar.
2. **A caption is required.** The stored vector covers caption *and* image, so a photo is
   retrieved for what its owner says it shows. An uncaptioned photo is not searchable —
   the same rule the text layer already applies to uncited claims.
3. **Appearance queries are refused**, not scored. See `appearance_query_reason`.
4. **The caption is the evidence.** Results carry the owner's own words, so a match is
   always accountable to a human-readable claim rather than to raw pixel similarity.

Multimodal vectors live in their own `space()`, so they can never be compared against the
text corpus. That is the same guarantee `embeddings.py` makes across providers, and it is
what keeps a photo from ever ranking inside ordinary people search.
"""

from __future__ import annotations

import base64
import math
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from app.embeddings import EmbeddingError
from app.serializers import serialize

DEFAULT_MULTIMODAL_ENDPOINT = "https://api.voyageai.com/v1/multimodalembeddings"
MULTIMODAL_MODEL = "voyage-multimodal-3.5"
MULTIMODAL_DIMENSIONS = 1024
MEDIA_VECTOR_INDEX = "persona_media_vector"
MAX_RETRIES = 4
RETRY_BASE_SECONDS = 2.0

# Voyage accepts these as base64 data URLs. Anything else is rejected at upload rather
# than stored and silently skipped at embed time.
ALLOWED_MEDIA_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}

MAX_IMAGE_BYTES = 6 * 1024 * 1024
MIN_CAPTION_CHARACTERS = 12
MAX_CAPTION_CHARACTERS = 300
MAX_MEDIA_PER_USER = 24


class MediaError(ValueError):
    """A photo that cannot be accepted, with a reason a member can act on."""


# --------------------------------------------------------------- the §9 query guard

# Terms describing how a person looks or what group they belong to. A professional
# network has no legitimate "find me someone who looks like this" query, so these are
# refused outright rather than down-weighted — a ranking penalty is still a ranking.
#
# Deliberately excluded: gender words. "women in climate tech" is how professional
# communities actually talk about themselves, and refusing it would break a legitimate
# search to enforce a rule aimed at something else. That is a judgement call, and it is
# the reason this list is narrow and explicit rather than a general demographic filter.
APPEARANCE_TERMS = {
    # phenotype and race
    "asian", "black", "brown-skinned", "caucasian", "dark-skinned", "ethnicity",
    "hispanic", "indian-looking", "latino", "latina", "light-skinned", "middle-eastern",
    "mixed-race", "race", "racial", "white-looking",
    # hair, face, body
    "attractive", "bald", "beard", "beautiful", "blond", "blonde", "brunette", "chubby",
    "cute", "fat", "fit-looking", "good-looking", "handsome", "hot", "muscular",
    "overweight", "physique", "pretty", "redhead", "sexy", "skinny", "slim", "tall",
    "thin", "ugly",
    # apparent age
    "middle-aged", "old-looking", "young-looking", "youthful",
}

# "looks like", "appearance of" — an appearance frame turns even a neutral word into a
# phenotype query, so the frame is caught on its own.
APPEARANCE_FRAMES = (
    "looks like",
    "look like",
    "looking like",
    "appearance",
    "what they look",
    "who looks",
    "people who look",
)

_WORD = re.compile(r"[a-z][a-z-]*")


def appearance_query_reason(query: str) -> str | None:
    """Return why a photo query is refused, or None if it may run.

    Refusing is the feature. A query that describes a person's body, colouring, or
    apparent age is asking the network to screen people by how they look, which is the
    one thing this capability must not do — so it gets a reason, not results.
    """
    lowered = query.lower()
    for frame in APPEARANCE_FRAMES:
        if frame in lowered:
            return (
                "Photo search finds people by what they were doing, not by how they look. "
                "Try describing the activity, setting, or event instead."
            )
    hits = sorted(APPEARANCE_TERMS.intersection(_WORD.findall(lowered)))
    if hits:
        return (
            f"“{hits[0]}” describes how someone looks. Photo search matches activity and "
            "setting only — describe what the person was doing instead."
        )
    return None


# ------------------------------------------------------------------- the embedder


@dataclass
class MultimodalEmbedder:
    """Voyage multimodal embeddings, or an honest `unavailable` when there is no key.

    There is no local fallback on purpose. A hashed stand-in cannot look at an image, so
    a keyless "photo search" would return confident nonsense — worse than saying it is off.
    """

    api_key: str | None
    timeout: float = 30.0
    # Either door serves voyage-multimodal-3.5; verified identical vectors from both.
    endpoint: str = DEFAULT_MULTIMODAL_ENDPOINT

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def space(self) -> str:
        return f"voyage:{MULTIMODAL_MODEL}:{MULTIMODAL_DIMENSIONS}"

    def describe(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "model": MULTIMODAL_MODEL if self.available else None,
            "dimensions": MULTIMODAL_DIMENSIONS,
            "space": self.space(),
        }

    def embed_photo(self, *, caption: str, image: bytes, media_type: str) -> list[float]:
        """Embed caption and image together, so the caption anchors what this matches."""
        encoded = base64.b64encode(image).decode("ascii")
        return self._request(
            {
                "content": [
                    {"type": "text", "text": caption},
                    {"type": "image_base64", "image_base64": f"data:{media_type};base64,{encoded}"},
                ]
            },
            input_type="document",
        )

    def embed_query(self, query: str) -> list[float]:
        return self._request({"content": [{"type": "text", "text": query}]}, input_type="query")

    def _request(self, item: dict, *, input_type: str) -> list[float]:
        if not self.available:
            raise EmbeddingError("Multimodal embeddings need a Voyage API key")
        payload = {
            "inputs": [item],
            "model": MULTIMODAL_MODEL,
            "input_type": input_type,
            "truncation": True,
        }
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.post(
                    self.endpoint,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
                if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_SECONDS * (2**attempt))
                    continue
                response.raise_for_status()
                rows = response.json().get("data", [])
                if not rows:
                    raise EmbeddingError("Voyage returned no multimodal embedding")
                return rows[0]["embedding"]
            except httpx.HTTPError as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if attempt < MAX_RETRIES - 1 and (status is None or status >= 500):
                    time.sleep(RETRY_BASE_SECONDS * (2**attempt))
                    continue
                raise EmbeddingError(f"multimodal embedding request failed: {exc}") from exc
        raise EmbeddingError(
            f"multimodal embedding failed after {MAX_RETRIES} attempts: {last_error}"
        )


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


# ---------------------------------------------------------------------- the store


def utcnow() -> datetime:
    return datetime.now(UTC)


def validate_photo(*, caption: str, image: bytes, media_type: str) -> str:
    """Reject at the door rather than storing something that can never be searched."""
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise MediaError(
            f"{media_type or 'That file type'} is not supported. Use PNG, JPEG, WebP, or GIF."
        )
    if not image:
        raise MediaError("That file was empty.")
    if len(image) > MAX_IMAGE_BYTES:
        raise MediaError(f"Photos must be under {MAX_IMAGE_BYTES // (1024 * 1024)}MB.")
    cleaned = " ".join(caption.split())[:MAX_CAPTION_CHARACTERS]
    if len(cleaned) < MIN_CAPTION_CHARACTERS:
        # Not bureaucracy: the caption is what the photo gets matched on, and it is the
        # evidence shown to whoever finds it.
        raise MediaError(
            "Add a caption describing what is happening in the photo — it is what your "
            "photo gets found for."
        )
    return cleaned


class MediaStore:
    """Photo metadata and vectors in `persona_media`; bytes in `media_blobs`.

    Split on purpose: every search reads metadata, and almost none of them want a
    multi-megabyte blob riding along in the same document.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        # Optimistic, then latched off by the first failure. Photo search is a small
        # enough surface that probing at startup would cost more than it saves.
        self._atlas_ok = True

    def ensure_indexes(self) -> None:
        self.db.persona_media.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        self.db.persona_media.create_index([("space", ASCENDING)])

    def add(
        self,
        *,
        user_id: str,
        caption: str,
        image: bytes,
        media_type: str,
        embedding: list[float] | None,
        space: str,
    ) -> dict:
        if self.count(user_id) >= MAX_MEDIA_PER_USER:
            raise MediaError(f"You can keep up to {MAX_MEDIA_PER_USER} photos.")
        media_id = f"med_{uuid4().hex[:20]}"
        now = utcnow()
        self.db.media_blobs.insert_one(
            {"_id": media_id, "user_id": user_id, "media_type": media_type, "bytes": image}
        )
        self.db.persona_media.insert_one(
            {
                "_id": media_id,
                "user_id": user_id,
                "caption": caption,
                "media_type": media_type,
                "size_bytes": len(image),
                # A photo with no vector is stored and shown but never retrieved, and
                # says so, rather than looking indexed while being invisible.
                "embedding": embedding,
                "space": space if embedding else None,
                "indexed": embedding is not None,
                "created_at": now,
                "updated_at": now,
            }
        )
        return self.get(user_id, media_id)

    def count(self, user_id: str) -> int:
        return self.db.persona_media.count_documents({"user_id": user_id})

    def get(self, user_id: str, media_id: str) -> dict | None:
        row = self.db.persona_media.find_one(
            {"_id": media_id, "user_id": user_id}, {"embedding": 0}
        )
        return serialize(row) if row else None

    def blob(self, media_id: str) -> dict | None:
        return self.db.media_blobs.find_one({"_id": media_id})

    def list_for_user(self, user_id: str) -> list[dict]:
        rows = self.db.persona_media.find({"user_id": user_id}, {"embedding": 0}).sort(
            "created_at", DESCENDING
        )
        return serialize(list(rows))

    def delete(self, user_id: str, media_id: str) -> bool:
        result = self.db.persona_media.delete_one({"_id": media_id, "user_id": user_id})
        if result.deleted_count == 0:
            return False
        self.db.media_blobs.delete_one({"_id": media_id})
        return True

    def search(
        self,
        *,
        query_vector: list[float],
        space: str,
        allowed_user_ids: set[str],
        limit: int = 12,
        atlas: bool = True,
    ) -> list[dict]:
        """Rank consenting members' photos by similarity to the query.

        `allowed_user_ids` is a **filter inside the query**, in both the Atlas and local
        paths, rather than a post-ranking pass. That placement is the consent guarantee:
        no scoring change can leak a member who never opted in, because a non-consenting
        member's photos are never candidates in the first place.
        """
        if not allowed_user_ids:
            return []
        if atlas and self._atlas_ok:
            hits = self._search_atlas(query_vector, space, allowed_user_ids, limit)
            if hits is not None:
                return hits
        return self._search_local(query_vector, space, allowed_user_ids, limit)

    def _search_atlas(
        self, query_vector: list[float], space: str, allowed: set[str], limit: int
    ) -> list[dict] | None:
        """$vectorSearch over `persona_media_vector`. None when it did not run."""
        pipeline = [
            {
                "$vectorSearch": {
                    "index": MEDIA_VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(limit * 10, 100),
                    "limit": limit,
                    "filter": {
                        "user_id": {"$in": sorted(allowed)},
                        "space": space,
                        "indexed": True,
                    },
                }
            },
            {"$project": {"embedding": 0, "score": {"$meta": "vectorSearchScore"}}},
        ]
        try:
            rows = list(self.db.persona_media.aggregate(pipeline))
        except Exception:
            # Broad on purpose, and latched, matching PeopleSearch. A missing or
            # still-building index is a normal state on a fresh cluster, and mongomock
            # rejects $vectorSearch outright — neither is worth failing a search over.
            # Latching means one probe, not a doomed aggregate on every later query.
            self._atlas_ok = False
            return None
        return [
            {**serialize(row), "score": round(float(row.get("score", 0.0)), 4)} for row in rows
        ]

    def _search_local(
        self, query_vector: list[float], space: str, allowed: set[str], limit: int
    ) -> list[dict]:
        """Full scan with cosine in Python. Correct, and fine at prototype scale only.

        Scores are rescaled to Atlas's `vectorSearchScore` convention — `(1 + cos) / 2`,
        so 0 means opposite and 1 means identical. Without this the same photo scores
        0.6433 here and 0.8216 on Atlas, and `score` would silently mean two different
        things depending on which path happened to serve the query.
        """
        rows = self.db.persona_media.find(
            {"user_id": {"$in": sorted(allowed)}, "space": space, "indexed": True}
        )
        scored = []
        for row in rows:
            raw = cosine(query_vector, row.get("embedding") or [])
            if raw <= 0:
                continue
            row.pop("embedding", None)
            scored.append({**serialize(row), "score": round((1.0 + raw) / 2.0, 4)})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]
