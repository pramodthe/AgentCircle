"""Photo upload, serving, and the photo-search surface.

The safety constraint from spec §9 is enforced here in the order that matters: consent is
resolved before ranking, and an appearance query is refused before a vector is ever
computed — so a refused query costs nothing and cannot be partially answered.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.auth import CurrentUser, OptionalUser
from app.dependencies import (
    AccountsDependency,
    MediaDependency,
    MultimodalDependency,
)
from app.embeddings import EmbeddingError
from app.media import MediaError, appearance_query_reason, validate_photo
from app.settings import get_settings

router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/status")
def media_status(multimodal: MultimodalDependency) -> dict:
    """What the photo layer can actually do right now, stated plainly."""
    return multimodal.describe()


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    user: CurrentUser,
    media: MediaDependency,
    multimodal: MultimodalDependency,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str, Form()],
) -> dict:
    data = await file.read()
    try:
        cleaned = validate_photo(
            caption=caption, image=data, media_type=file.content_type or ""
        )
    except MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # A photo that cannot be embedded is still kept and shown — it just isn't searchable,
    # and the row says so rather than looking indexed while being invisible.
    embedding = None
    if multimodal.available:
        try:
            embedding = multimodal.embed_photo(
                caption=cleaned, image=data, media_type=file.content_type or "image/jpeg"
            )
        except EmbeddingError:
            embedding = None

    try:
        return media.add(
            user_id=user["_id"],
            caption=cleaned,
            image=data,
            media_type=file.content_type or "image/jpeg",
            embedding=embedding,
            space=multimodal.space(),
        )
    except MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.get("")
def list_my_photos(user: CurrentUser, media: MediaDependency) -> list[dict]:
    return media.list_for_user(user["_id"])


@router.get("/user/{user_id}")
def list_member_photos(
    user_id: str, media: MediaDependency, accounts: AccountsDependency, viewer: OptionalUser
) -> list[dict]:
    """Photos on a member's public page.

    Gated on the same opt-in as search: a member who has not turned photo sharing on does
    not get a photo grid on their profile just because someone found the URL. Their own
    page still shows them their photos.
    """
    if viewer and viewer["_id"] == user_id:
        return media.list_for_user(user_id)
    if user_id not in accounts.photo_search_opted_in_ids():
        return []
    return media.list_for_user(user_id)


@router.get("/{media_id}/raw")
def get_photo_bytes(media_id: str, media: MediaDependency) -> Response:
    blob = media.blob(media_id)
    if blob is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    return Response(
        content=blob["bytes"],
        media_type=blob.get("media_type", "image/jpeg"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(media_id: str, user: CurrentUser, media: MediaDependency) -> None:
    if not media.delete(user["_id"], media_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")


@router.get("/search")
def search_photos(
    q: str,
    user: CurrentUser,
    media: MediaDependency,
    accounts: AccountsDependency,
    multimodal: MultimodalDependency,
    limit: int = 12,
) -> dict:
    query = q.strip()
    if len(query) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query is too short"
        )

    # Refused before anything is computed. This is the §9 constraint, and it is a first
    # class answer — the caller gets told why, not an empty result set that reads as
    # "nobody matched".
    refusal = appearance_query_reason(query)
    if refusal:
        return {"refused": True, "reason": refusal, "results": []}

    if not multimodal.available:
        return {
            "refused": False,
            "reason": "Photo search needs a Voyage API key. It is off right now.",
            "available": False,
            "results": [],
        }

    # Consent first, then ranking. Filtering after scoring would mean a scoring change
    # could leak someone who never opted in.
    allowed = accounts.photo_search_opted_in_ids()
    allowed.discard(user["_id"])
    if not allowed:
        return {"refused": False, "results": [], "available": True}

    try:
        vector = multimodal.embed_query(query)
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    hits = media.search(
        query_vector=vector,
        space=multimodal.space(),
        allowed_user_ids=allowed,
        limit=min(max(1, limit), 24),
        # Same rule as people search: mongomock cannot serve $vectorSearch, and probing
        # a real cluster is the only honest way to know an index is queryable.
        atlas=not get_settings().use_mock_mongodb,
    )
    owners = {row["user_id"] for row in hits}
    people = {uid: accounts.get_user(uid) for uid in owners}
    results = [
        {
            **hit,
            "member": accounts.public_member(people[hit["user_id"]]),
        }
        for hit in hits
        # A photo whose owner no longer has an account is not a match.
        if people.get(hit["user_id"])
    ]
    return {"refused": False, "available": True, "results": results}
