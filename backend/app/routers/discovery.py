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

# Retrieval pool used when a filter is active. Large enough to cover the whole member
# universe at prototype scale, so filtering cannot lose someone who genuinely matches.
# If this product ever outgrows a single-digit-thousand membership, the filter belongs
# inside the `$vectorSearch` / `$search` stages as a pre-filter instead.
FILTERED_POOL = 400


def _matches_location(profile: dict, wanted: str) -> bool:
    """Substring, case-insensitive, in either direction.

    Members write a location freehand — "San Francisco", "San Francisco, CA", "SF Bay
    Area" — so an equality test would drop most of a city on a trailing state code.
    Matching in both directions lets a stored "SF" answer a "SF Bay Area" filter and
    vice versa. It is deliberately generous: this narrows a ranked list a human is
    about to read, so a false positive costs a glance and a false negative costs the
    introduction the feature exists to make.
    """
    stored = (profile.get("location") or "").casefold().strip()
    if not stored:
        return False
    wanted = wanted.casefold().strip()
    return wanted in stored or stored in wanted


def _matches_goal(profile: dict, wanted: str) -> bool:
    """A goal filter tests `looking_for`, which is what the member said they want.

    Not `headline` or `interests`: those describe what someone *does*, and matching a
    goal against them is how "wants design feedback" starts returning every designer.
    """
    wanted = wanted.casefold().strip()
    return any(
        wanted in (item or "").casefold() for item in profile.get("looking_for", [])
    )


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

    # Narrowing filters live here, beside the discoverability filter and before
    # ranking, for the same reason: a member excluded by a filter must not be able to
    # reappear because a scoring change moved them up the list.
    if payload.location:
        profile_rows = {
            uid: row
            for uid, row in profile_rows.items()
            if _matches_location(row, payload.location)
        }
    if payload.goal:
        profile_rows = {
            uid: row
            for uid, row in profile_rows.items()
            if _matches_goal(row, payload.goal)
        }
    if payload.evidence_only:
        # Evidence is a chunk, not a filled-in field. Asking persona_chunks directly
        # means the filter cannot be satisfied by a profile someone merely typed into.
        grounded = set(
            search.db.persona_chunks.distinct(
                "user_id", {"user_id": {"$in": list(profile_rows)}}
            )
        )
        profile_rows = {
            uid: row for uid, row in profile_rows.items() if uid in grounded
        }

    persona_rows = {
        row["_id"]: row
        for row in search.db.personas.find({"_id": {"$in": list(profile_rows)}})
    }
    trust = outcomes.trust_map(viewer_id, list(profile_rows))

    filtered = bool(payload.location or payload.goal or payload.evidence_only)

    result = search.search(
        query=payload.query,
        viewer_id=viewer_id,
        profiles=profile_rows,
        personas=persona_rows,
        trust=trust,
        limit=payload.limit,
        min_match_percent=payload.min_match_percent,
        # Retrieval picks its pool from the whole index, and only then does the profile
        # map above exclude anyone. With a narrow filter that ordering silently loses
        # people: the four members actually in Denver can all sit below a default pool
        # drawn from everyone, and the search returns nothing while the filter looks
        # like it "found no one in Denver". Widening the pool when a filter is active
        # keeps the filter a *narrowing* of real results rather than a second cutoff.
        pool=FILTERED_POOL if filtered else 60,
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

    return {
        "query": payload.query,
        **result,
        # What the filters did, reported rather than implied. `candidates` is how many
        # members survived filtering, so a UI can distinguish "nobody in Denver" from
        # "eleven people in Denver, none relevant to this query" — two different
        # answers that otherwise both render as an empty list.
        "filters": {
            "location": payload.location,
            "goal": payload.goal,
            "evidence_only": payload.evidence_only,
            "candidates": len(profile_rows),
        },
    }


@router.get("/facets")
def discovery_facets(
    request: Request, user: CurrentUser, accounts: AccountsDependency
) -> dict:
    """The filter values that actually exist on discoverable profiles.

    Built from live data rather than a hard-coded list so the UI can never offer a
    city or a goal that returns nobody — an empty result the member cannot tell from
    a broken search.
    """
    search = request.app.state.people_search
    hidden = accounts.undiscoverable_ids()
    viewer_id = user["_id"]

    locations: dict[str, int] = {}
    goals: dict[str, int] = {}
    for row in search.db.profiles.find({"_id": {"$ne": viewer_id}}):
        if row["_id"] in hidden:
            continue
        location = (row.get("location") or "").strip()
        if location:
            locations[location] = locations.get(location, 0) + 1
        for goal in row.get("looking_for", []):
            goal = (goal or "").strip()
            if goal:
                goals[goal] = goals.get(goal, 0) + 1

    return {
        "locations": [
            {"value": value, "count": count}
            for value, count in sorted(locations.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "goals": [
            {"value": value, "count": count}
            for value, count in sorted(goals.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


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
