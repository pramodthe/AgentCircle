from fastapi import APIRouter, Request, status

from app.auth import CurrentUser
from app.dependencies import (
    AccountsDependency,
    OutcomesDependency,
    ProfileMediaDependency,
)
from app.profile_media import public_profile_media
from app.schemas import DiscoverySearch

router = APIRouter(prefix="/api/discover", tags=["discovery"])


@router.post("", status_code=status.HTTP_200_OK)
def discover(
    payload: DiscoverySearch,
    request: Request,
    user: CurrentUser,
    accounts: AccountsDependency,
    outcomes: OutcomesDependency,
    profile_media: ProfileMediaDependency,
) -> dict:
    """Natural-language people search.

    Every number returned is computed: hybrid retrieval fused by reciprocal rank,
    weighted by what this member actually learned from meeting people before.
    """
    search = request.app.state.people_search
    viewer_id = user["_id"]

    # Pull the candidate universe once. A member without a profile document, or who
    # has opted out of discovery, is never a candidate — filtered here rather than
    # after ranking so an undiscoverable member cannot leak through a scoring change.
    hidden = accounts.undiscoverable_ids()
    profile_rows = {
        row["_id"]: row
        for row in search.db.profiles.find({"_id": {"$ne": viewer_id}})
        if row["_id"] not in hidden
    }
    persona_rows = {
        row["_id"]: row
        for row in search.db.personas.find({"_id": {"$in": list(profile_rows)}})
    }
    trust = outcomes.trust_map(viewer_id, list(profile_rows))

    result = search.search(
        query=payload.query,
        viewer_id=viewer_id,
        profiles=profile_rows,
        personas=persona_rows,
        trust=trust,
        limit=payload.limit,
        min_match_percent=payload.min_match_percent,
    )

    users = accounts.users_by_id([row["user_id"] for row in result["matches"]])
    # A profile whose user record is gone is a deleted account, not a match. Drop it
    # rather than returning a nameless result the UI has to paper over.
    result["matches"] = [row for row in result["matches"] if row["user_id"] in users]

    # Presentation images for the page, batched. These influence nothing about ranking —
    # they are read after `search()` has returned, precisely so a photo cannot become a
    # retrieval surface.
    images = profile_media.for_users([row["user_id"] for row in result["matches"]])

    for row in result["matches"]:
        member = users.get(row["user_id"])
        profile = profile_rows.get(row["user_id"], {})
        persona = persona_rows.get(row["user_id"], {})
        row["member"] = (
            {
                "user_id": row["user_id"],
                "display_name": member["display_name"],
                "handle": member["handle"],
                **public_profile_media(images.get(row["user_id"])),
            }
            if member
            else None
        )
        row["headline"] = profile.get("headline", "")
        row["location"] = profile.get("location", "")
        row["skills"] = profile.get("skills", [])[:6]
        row["interests"] = profile.get("interests", [])[:6]
        row["looking_for"] = profile.get("looking_for", [])[:4]
        row["persona_summary"] = persona.get("summary", "")[:400]
        row["trust_detail"] = outcomes.effective_trust(viewer_id, row["user_id"])

    return {"query": payload.query, **result}


@router.get("/status")
def retrieval_status(request: Request, user: CurrentUser) -> dict:
    """Which retrieval path is actually live, so the UI never implies more than it has."""
    search = request.app.state.people_search
    return {
        "atlas_vector": search._atlas_vector_ok,
        "atlas_text": search._atlas_text_ok,
        "atlas_enabled": search.atlas_enabled,
        "embeddings": search.embeddings.describe(),
        "rerank": search.reranker.describe() if search.reranker else {"enabled": False},
    }
