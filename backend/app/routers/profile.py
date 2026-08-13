import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.accounts import declared_profile_text
from app.auth import CurrentUser
from app.dependencies import (
    AccountsDependency,
    PersonaBuilderDependency,
    ProfileMediaDependency,
)
from app.embeddings import EmbeddingError
from app.ingestion import ExtractedSource
from app.media import MediaError
from app.profile_media import PROFILE_MEDIA_KINDS, public_profile_media
from app.schemas import ProfileUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])

# Below this a profile has too little in it to be worth a retrievable chunk; embedding
# "Skills: python." would only add noise to everyone else's searches.
MIN_DECLARED_CHARACTERS = 80


@router.get("")
def get_my_profile(
    user: CurrentUser, accounts: AccountsDependency, profile_media: ProfileMediaDependency
) -> dict:
    return {
        **(accounts.get_profile(user["_id"]) or {}),
        **public_profile_media(profile_media.for_users([user["_id"]]).get(user["_id"])),
    }


@router.patch("")
def update_my_profile(
    payload: ProfileUpdate,
    user: CurrentUser,
    accounts: AccountsDependency,
    builder: PersonaBuilderDependency,
) -> dict:
    # exclude_unset keeps a PATCH from blanking fields the client did not send.
    profile = accounts.update_profile(user["_id"], payload.model_dump(exclude_unset=True))

    # The editor tells members these fields are what their agent can be found for, so the
    # save has to make that true. Reported back rather than assumed: if the embedding
    # provider is down the profile is still saved, and the UI says it isn't searchable yet
    # instead of quietly implying it is.
    text = declared_profile_text(profile)
    synced = True
    if len(text) < MIN_DECLARED_CHARACTERS:
        accounts.replace_declared_source(user_id=user["_id"], text="", chunks=[])
    else:
        try:
            chunks = builder.prepare_chunks(
                ExtractedSource(title="", kind="declared", detail="", text=text)
            )
            accounts.replace_declared_source(user_id=user["_id"], text=text, chunks=chunks)
        except EmbeddingError:
            logger.warning("profile saved but not indexed for %s", user["_id"], exc_info=True)
            synced = False
    return {**profile, "retrieval_synced": synced}


# ------------------------------------------------------------------ profile images
#
# Presentation only. These never reach `declared_profile_text`, are never embedded, and
# are not reachable from any search endpoint — the same rule `theme` follows. Uploading
# a photo must not change who finds you, or the image becomes a ranking surface.


@router.post("/photo", status_code=status.HTTP_201_CREATED)
async def upload_profile_photo(
    user: CurrentUser,
    profile_media: ProfileMediaDependency,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    ai_generated: Annotated[bool, Form()] = False,
) -> dict:
    if kind not in PROFILE_MEDIA_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {', '.join(PROFILE_MEDIA_KINDS)}",
        )
    data = await file.read()
    try:
        return profile_media.set(
            user_id=user["_id"],
            kind=kind,
            image=data,
            media_type=file.content_type or "",
            ai_generated=ai_generated,
        )
    except MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete("/photo/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_photo(
    kind: str, user: CurrentUser, profile_media: ProfileMediaDependency
) -> None:
    if not profile_media.delete(user["_id"], kind):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No image there")


@router.get("/photo/{media_id}/raw")
def get_profile_photo_bytes(media_id: str, profile_media: ProfileMediaDependency) -> Response:
    """Unauthenticated on purpose: an avatar renders on a public profile page.

    Scoped to `profile_media` ids so this can never serve a persona photo, which is
    consent-gated and belongs to a different surface entirely.
    """
    if profile_media.get_by_id(media_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    blob = profile_media.blob(media_id)
    if blob is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return Response(
        content=blob["bytes"],
        media_type=blob.get("media_type", "image/jpeg"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{handle}")
def get_public_profile(
    handle: str, accounts: AccountsDependency, profile_media: ProfileMediaDependency
) -> dict:
    owner = accounts.get_user_by_handle(handle)
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    user_id = owner["_id"]
    persona = accounts.get_persona(user_id) or {}
    return {
        # public_member, not public_user: this route takes no auth at all, so anything
        # it returns is world-readable.
        "user": accounts.public_member(owner),
        "profile": {
            **(accounts.get_profile(user_id) or {}),
            **public_profile_media(profile_media.for_users([user_id]).get(user_id)),
        },
        # Public view exposes the persona summary only. Raw source chunks stay private.
        "persona": {
            "headline": persona.get("headline", ""),
            "summary": persona.get("summary", ""),
            "skills": [item["value"] for item in persona.get("skills", [])],
            "interests": [item["value"] for item in persona.get("interests", [])],
            "looking_for": [item["value"] for item in persona.get("looking_for", [])],
        },
    }
