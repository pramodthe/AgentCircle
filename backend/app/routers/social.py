from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status

from app.auth import CurrentUser
from app.dependencies import (
    AccountsDependency,
    ConnectionsDependency,
    EmbeddingsDependency,
    FeedDependency,
    InterviewsDependency,
    PersonaBuilderDependency,
    ProfileMediaDependency,
)
from app.ingestion import ExtractedSource
from app.media import MediaError
from app.profile_media import public_profile_media
from app.schemas import (
    ConnectionRequest,
    ConnectionRespond,
    PostCreateFeed,
    PostDraftRequest,
    ReactionCreate,
)
from app.social import (
    build_agent_post,
    episodic_title,
    pair_id,
    should_ingest,
    story_is_active,
)

router = APIRouter(prefix="/api/social", tags=["social"])


def _people(accounts, user_ids: list[str], profile_media=None) -> dict[str, dict]:
    users = accounts.users_by_id(user_ids)
    profiles = accounts.profiles_by_id(user_ids)
    # One batched read for the whole page. A per-row lookup here is how a feed of forty
    # posts turns into forty round trips.
    images = profile_media.for_users(list(users)) if profile_media else {}
    return {
        user_id: {
            "user_id": user_id,
            "display_name": user["display_name"],
            "handle": user["handle"],
            "headline": (profiles.get(user_id) or {}).get("headline", ""),
            "accent": ((profiles.get(user_id) or {}).get("theme") or {}).get("accent", "violet"),
            **public_profile_media(images.get(user_id)),
        }
        for user_id, user in users.items()
    }


# ------------------------------------------------------------------ connections


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def request_connection(
    payload: ConnectionRequest,
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
) -> dict:
    if accounts.get_user(payload.recipient_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    try:
        return connections.request(
            requester_id=user["_id"],
            recipient_id=payload.recipient_id,
            note=payload.note or "",
            source=payload.source,
            context_id=payload.context_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/connections/{other_id}")
def connection_status(
    other_id: str,
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
) -> dict:
    if accounts.get_user(other_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return connections.status_between(user["_id"], other_id) or {"status": "none"}


@router.post("/connections/{other_id}/respond")
def respond_connection(
    other_id: str,
    payload: ConnectionRespond,
    user: CurrentUser,
    connections: ConnectionsDependency,
) -> dict:
    try:
        row = connections.respond(
            pair=pair_id(user["_id"], other_id),
            recipient_id=user["_id"],
            accept=payload.accept,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No pending request from that member"
        )
    return row


@router.post("/connections/{other_id}/withdraw")
def withdraw_connection(
    other_id: str, user: CurrentUser, connections: ConnectionsDependency
) -> dict:
    try:
        row = connections.withdraw(pair=pair_id(user["_id"], other_id), requester_id=user["_id"])
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending request")
    return row


@router.get("/connections")
def list_connections(
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
    profile_media: ProfileMediaDependency,
) -> dict:
    accepted = connections.connections_for(user["_id"])
    pending = connections.pending_for(user["_id"])
    ids = sorted(
        {member for row in accepted for member in row["members"]}
        | {row["requester_id"] for row in pending["incoming"]}
        | {row["recipient_id"] for row in pending["outgoing"]}
    )
    people = _people(accounts, ids, profile_media)

    for row in accepted:
        other = next(m for m in row["members"] if m != user["_id"])
        row["member"] = people.get(other)
    for row in pending["incoming"]:
        row["member"] = people.get(row["requester_id"])
    for row in pending["outgoing"]:
        row["member"] = people.get(row["recipient_id"])

    return {
        "accepted": accepted,
        "incoming": pending["incoming"],
        "outgoing": pending["outgoing"],
        # Which parts of the product actually produced connections.
        "provenance": connections.provenance_counts(user["_id"]),
    }


# ------------------------------------------------------------------------ feed


@router.get("/feed")
def read_feed(
    user: CurrentUser,
    accounts: AccountsDependency,
    connections: ConnectionsDependency,
    feed: FeedDependency,
    profile_media: ProfileMediaDependency,
) -> dict:
    connected = connections.connected_ids(user["_id"])
    posts = feed.list_feed(viewer_id=user["_id"], connected_ids=connected)
    people = _people(accounts, sorted({post["author_id"] for post in posts}), profile_media)
    reactions = feed.my_reactions(user["_id"], [post["_id"] for post in posts])
    for post in posts:
        post["author"] = people.get(post["author_id"])
        post["from_connection"] = post["author_id"] in connected
        # The expiry rule belongs to the server. A client deciding for itself when a
        # story is stale means two clients disagree about what is on screen.
        post["story_active"] = story_is_active(post)
    return {"posts": posts, "my_reactions": reactions, "connection_count": len(connected)}


@router.post("/feed", status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreateFeed,
    request: Request,
    user: CurrentUser,
    accounts: AccountsDependency,
    embeddings: EmbeddingsDependency,
    builder: PersonaBuilderDependency,
    feed: FeedDependency,
    profile_media: ProfileMediaDependency,
) -> dict:
    """Post to the feed, and fold substantial posts into the author's persona.

    This is the mechanism that makes the feed context intake rather than decoration:
    what you write today is retrievable evidence about you tomorrow, and an agent can
    cite it. Short posts are skipped — indexing "congrats!" teaches nothing and
    pollutes retrieval.

    A story takes the same path under a different `kind`. It is filed as `episodic`
    with its date in the title, because a dated episode and a standing claim are not
    the same statement about a person, and an agent that flattens the two reports last
    Tuesday as a permanent trait. The card expires from the strip; the memory does not,
    and the composer says that before you post rather than after.
    """
    is_story = payload.presentation == "story"
    image_media_id = payload.image_media_id
    image_media_type = None
    if image_media_id:
        owned = feed.feed_media_owned(image_media_id)
        if owned is None or owned.get("user_id") != user["_id"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Attach an image you just uploaded from this composer.",
            )
        image_media_type = owned.get("media_type")

    post = feed.create(
        author_id=user["_id"],
        body=payload.body,
        kind="human",
        presentation=payload.presentation,
        image_media_id=image_media_id,
        image_media_type=image_media_type,
        location=payload.location,
    )

    if should_ingest(post["body"], payload.presentation):
        source = ExtractedSource(
            title=(
                episodic_title(post["created_at"])
                if is_story
                else f"Post · {post['created_at'][:10]}"
            ),
            text=post["body"],
            kind="episodic" if is_story else "post",
            detail=post["_id"],
        )
        chunks = builder.prepare_chunks(source)
        if chunks:
            accounts.add_source(
                user_id=user["_id"],
                title=source.title,
                kind=source.kind,
                detail=source.detail,
                text=source.text,
                chunks=chunks,
            )
            feed.mark_ingested(post["_id"], len(chunks))
            post["ingested"] = True
            post["ingested_chunks"] = len(chunks)

    post["author"] = _people(accounts, [user["_id"]], profile_media).get(user["_id"])
    post["story_active"] = story_is_active(post)
    return post


@router.post("/feed/media", status_code=status.HTTP_201_CREATED)
async def upload_feed_media(
    user: CurrentUser,
    feed: FeedDependency,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "post",
) -> dict:
    """Upload a composer Photo or Clip. Presentation only — never searchable."""
    if kind not in ("post", "clip"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="kind must be post or clip",
        )
    data = await file.read()
    try:
        media_id, media_type = feed.save_feed_media(
            user_id=user["_id"],
            data=data,
            media_type=file.content_type or "",
            kind=kind,  # type: ignore[arg-type]
        )
    except MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return {
        "_id": media_id,
        "media_type": media_type,
        "kind": kind,
        "url": f"/api/social/feed/media/{media_id}/raw",
    }


@router.get("/feed/media/{media_id}/raw")
def get_feed_media(media_id: str, feed: FeedDependency) -> Response:
    blob = feed.feed_blob(media_id)
    if blob is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return Response(
        content=blob["bytes"],
        media_type=blob.get("media_type", "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/feed/draft")
def draft_feed_post(
    payload: PostDraftRequest,
    request: Request,
    user: CurrentUser,
    accounts: AccountsDependency,
) -> dict:
    """Agent helps write a post. Draft only — the member still has to hit Post.

    Same approval-gate rule as everywhere else: the model never publishes.
    """
    chat = request.app.state.chat
    notes = payload.notes.strip()
    profile = accounts.get_profile(user["_id"]) or {}
    persona = accounts.get_persona(user["_id"]) or {}
    context_bits = [
        user.get("display_name") or "",
        profile.get("headline") or "",
        persona.get("summary") or "",
    ]
    context = " · ".join(bit for bit in context_bits if bit)

    if not chat.configured or chat.model is None:
        polished = notes if notes.endswith((".", "!", "?")) else f"{notes}."
        return {
            "body": polished[:4000],
            "runtime_mode": "deterministic_fallback",
            "model": None,
        }

    prompt = (
        "You help a member draft a short social update for a professional builders "
        "network. Rewrite their rough notes into one clear post in their voice. "
        "Keep it under 80 words. No hashtags, no emojis unless they used one, no "
        "invented facts. Return only the post text.\n\n"
        f"Member context: {context or 'builder'}\n"
        f"Rough notes:\n{notes}"
    )
    try:
        result = chat.model.invoke(prompt)
        body = (getattr(result, "content", None) or str(result)).strip()
        if not body:
            raise RuntimeError("empty draft")
        return {
            "body": body[:4000],
            "runtime_mode": "live",
            "model": chat.model_name,
        }
    except Exception:
        polished = notes if notes.endswith((".", "!", "?")) else f"{notes}."
        return {
            "body": polished[:4000],
            "runtime_mode": "fallback_after_error",
            "model": chat.model_name,
        }


@router.post("/feed/story", status_code=status.HTTP_201_CREATED)
async def create_story(
    user: CurrentUser,
    accounts: AccountsDependency,
    builder: PersonaBuilderDependency,
    feed: FeedDependency,
    profile_media: ProfileMediaDependency,
    file: Annotated[UploadFile, File()],
    caption: Annotated[str, Form()] = "",
) -> dict:
    """Create a story from an uploaded image — this is what Create story does.

    Image-first, like the strip in the product UI. The photo is presentation only
    (never searchable under §9). An optional caption can still become episodic memory
    when it clears the story ingest floor.
    """
    data = await file.read()
    try:
        media_id, media_type = feed.save_story_image(
            user_id=user["_id"],
            image=data,
            media_type=file.content_type or "",
        )
    except MediaError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    body = (caption or "").strip() or "Shared a story"
    post = feed.create(
        author_id=user["_id"],
        body=body,
        kind="human",
        presentation="story",
        image_media_id=media_id,
        image_media_type=media_type,
    )

    if should_ingest(post["body"], "story"):
        source = ExtractedSource(
            title=episodic_title(post["created_at"]),
            text=post["body"],
            kind="episodic",
            detail=post["_id"],
        )
        chunks = builder.prepare_chunks(source)
        if chunks:
            accounts.add_source(
                user_id=user["_id"],
                title=source.title,
                kind=source.kind,
                detail=source.detail,
                text=source.text,
                chunks=chunks,
            )
            feed.mark_ingested(post["_id"], len(chunks))
            post["ingested"] = True
            post["ingested_chunks"] = len(chunks)

    post["author"] = _people(accounts, [user["_id"]], profile_media).get(user["_id"])
    post["story_active"] = True
    return post


@router.get("/feed/story/{media_id}/raw")
def get_story_image(media_id: str, feed: FeedDependency) -> Response:
    """Serve a story photo. Same bytes path as feed media; kept for older clients."""
    return get_feed_media(media_id, feed)


@router.post("/feed/agent", status_code=status.HTTP_201_CREATED)
def create_agent_post(
    request: Request,
    user: CurrentUser,
    accounts: AccountsDependency,
    feed: FeedDependency,
    interviews: InterviewsDependency,
    profile_media: ProfileMediaDependency,
) -> dict:
    """Let this member's agent report what it actually did.

    Composed from stored activity, never generated — the whole value of an agent post
    is that it reports real events, and a model asked to write it would embellish.
    """
    community = request.app.state.community
    gaps = community.list_gaps(user["_id"], limit=10)
    ran = [row for row in interviews.list_for_asker(user["_id"], limit=10)]

    draft = build_agent_post(
        display_name=user["display_name"], gaps=gaps, interviews=ran
    )
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Your agent has nothing to report yet. It posts about questions it "
                "couldn't answer and interviews it ran."
            ),
        )

    post = feed.create(
        author_id=user["_id"], body=draft["body"], kind="agent", evidence=draft["evidence"]
    )
    post["author"] = _people(accounts, [user["_id"]], profile_media).get(user["_id"])
    return post


@router.post("/feed/{post_id}/react")
def react(
    post_id: str, payload: ReactionCreate, user: CurrentUser, feed: FeedDependency
) -> dict:
    try:
        row = feed.react(post_id=post_id, user_id=user["_id"], reaction=payload.reaction)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return row
