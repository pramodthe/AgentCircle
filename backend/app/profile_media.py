"""Avatars and cover images: the presentation half of a profile.

Deliberately a separate module from `media.py`, which owns *searchable* photos. The
two look alike — both are images a member uploaded, both keep their bytes in
`media_blobs` — and they are governed by opposite rules:

  `persona_media` is **evidence**. A photo there is embedded, requires a caption
  because the caption is what it gets matched on, and is only ever retrievable after
  the member opts in. Spec §9 constrains the whole surface.

  `profile_media` is **decoration**. It is never embedded, never indexed, never
  reachable from any search endpoint, and contributes nothing to `declared_profile_text`.
  It is the same rule `theme` follows: restyling a page must not influence who gets
  found, or customization quietly becomes an SEO surface.

Keeping them in one collection would mean one wrong `$vectorSearch` filter away from an
avatar being retrievable by appearance, which is precisely what §9 exists to prevent.
The separation is the enforcement.

Why this exists at all: the UI previously rendered five hard-coded stock photographs as
member identity — a story card labelled "Kenji" showed a stranger, and search results
carried photographs of unrelated people as their covers. On a product whose entire claim
is that what you see about someone is grounded in what they supplied, an unrelated
photograph presented as a person is a fabricated visual claim. A member's own photo, or
nothing, are the only honest options.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING
from pymongo.database import Database

from app.media import ALLOWED_MEDIA_TYPES, MAX_IMAGE_BYTES, MediaError
from app.serializers import serialize

# An avatar and a cover are the only two slots. Anything else is a persona photo and
# belongs in `media.py`, under the constraint that governs searchable images.
PROFILE_MEDIA_KINDS = ("avatar", "cover")


def utcnow() -> datetime:
    return datetime.now(UTC)


def validate_profile_photo(*, image: bytes, media_type: str) -> None:
    """No caption requirement here — a decorative image is not evidence of anything.

    `media.py` demands a caption because a searchable photo has to be accountable to a
    human-readable claim. An avatar makes no claim, is retrievable by nobody, and asking
    someone to describe their own face to upload it would be both pointless and, given
    what §9 is about, faintly grim.
    """
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise MediaError(
            f"{media_type or 'That file type'} is not supported. Use PNG, JPEG, WebP, or GIF."
        )
    if not image:
        raise MediaError("That file was empty.")
    if len(image) > MAX_IMAGE_BYTES:
        raise MediaError(f"Images must be under {MAX_IMAGE_BYTES // (1024 * 1024)}MB.")


def public_profile_media(rows: dict[str, Any] | None) -> dict[str, Any]:
    """The presentation fields a member's card carries, for any viewer.

    Ids rather than URLs so the client builds them the same way it does for persona
    photos, and so the shape does not encode a hostname. Absent slots are explicit
    `None` — a missing key would let a caller render a stale avatar from a previous row.
    """
    rows = rows or {}
    public: dict[str, Any] = {}
    for kind in PROFILE_MEDIA_KINDS:
        row = rows.get(kind)
        public[f"{kind}_media_id"] = row["_id"] if row else None
        public[f"{kind}_ai_generated"] = bool(row.get("ai_generated")) if row else False
    return public


class ProfileMediaStore:
    """One document per (member, slot), so re-uploading replaces rather than accumulates."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def ensure_indexes(self) -> None:
        self.db.profile_media.create_index([("user_id", ASCENDING)])

    @staticmethod
    def _id_for(user_id: str, kind: str) -> str:
        # Deterministic, like `src_declared_{user_id}`: N uploads leave one row, so a
        # member changing their avatar four times does not leave three orphaned blobs.
        return f"pm_{kind}_{user_id}"

    def set(
        self,
        *,
        user_id: str,
        kind: str,
        image: bytes,
        media_type: str,
        ai_generated: bool = False,
    ) -> dict:
        if kind not in PROFILE_MEDIA_KINDS:
            raise MediaError(f"Unknown image slot: {kind}")
        validate_profile_photo(image=image, media_type=media_type)

        media_id = self._id_for(user_id, kind)
        now = utcnow()
        self.db.media_blobs.replace_one(
            {"_id": media_id},
            {"_id": media_id, "user_id": user_id, "media_type": media_type, "bytes": image},
            upsert=True,
        )
        document = {
            "_id": media_id,
            "user_id": user_id,
            "kind": kind,
            "media_type": media_type,
            "size_bytes": len(image),
            # Carried so the UI can label it. An AI-generated portrait presented as a
            # photograph is the same fabricated visual claim as the stock photos this
            # replaced — the difference is only that the member chose it, so the answer
            # is to say so rather than to forbid it.
            "ai_generated": bool(ai_generated),
            "created_at": now,
            "updated_at": now,
        }
        self.db.profile_media.replace_one({"_id": media_id}, document, upsert=True)
        return serialize(document)

    def get(self, user_id: str, kind: str) -> dict | None:
        return serialize(self.db.profile_media.find_one({"_id": self._id_for(user_id, kind)}))

    def get_by_id(self, media_id: str) -> dict | None:
        """Used to prove an id belongs to this collection before serving its bytes.

        `media_blobs` is shared with consent-gated persona photos, so the raw route
        checks membership here first rather than reading the blob directly.
        """
        return serialize(self.db.profile_media.find_one({"_id": media_id}))

    def for_users(self, user_ids: list[str]) -> dict[str, dict[str, Any]]:
        """`{user_id: {"avatar": {...}, "cover": {...}}}` for a batch of members.

        Batched because the feed and discovery both need this for every row on the page,
        and a per-row query is the shape that turns one screen into forty round trips.
        """
        found: dict[str, dict[str, Any]] = {}
        if not user_ids:
            return found
        for row in self.db.profile_media.find({"user_id": {"$in": user_ids}}):
            found.setdefault(row["user_id"], {})[row["kind"]] = serialize(row)
        return found

    def delete(self, user_id: str, kind: str) -> bool:
        media_id = self._id_for(user_id, kind)
        result = self.db.profile_media.delete_one({"_id": media_id, "user_id": user_id})
        if result.deleted_count:
            self.db.media_blobs.delete_one({"_id": media_id, "user_id": user_id})
            return True
        return False

    def blob(self, media_id: str) -> dict | None:
        return self.db.media_blobs.find_one({"_id": media_id})
