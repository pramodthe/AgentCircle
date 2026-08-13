from fastapi import APIRouter, HTTPException, Request, status

from app.auth import CurrentUser
from app.community import (
    DEFAULT_COMMUNITY_SETTINGS,
    rank_responders,
    safe_community_settings,
    summarize_question,
)
from app.dependencies import AccountsDependency, CommunityDependency, EmbeddingsDependency
from app.schemas import CommunitySettingsUpdate, GapResolve, PostCreate, VoteCreate

router = APIRouter(prefix="/api/community", tags=["community"])


def _decorate(comments: list[dict], accounts) -> list[dict]:
    """Attach the human behind each agent comment — the point is that they're reachable."""
    responder_ids = sorted({row["responder_id"] for row in comments})
    users = accounts.users_by_id(responder_ids)
    profiles = accounts.profiles_by_id(responder_ids)
    for row in comments:
        responder = users.get(row["responder_id"])
        profile = profiles.get(row["responder_id"]) or {}
        row["responder"] = (
            {
                "user_id": row["responder_id"],
                "display_name": responder.get("display_name") if responder else "Unknown",
                "handle": responder.get("handle") if responder else None,
                "headline": profile.get("headline", ""),
            }
            if responder
            else None
        )
    return comments


def _current_settings(accounts, user_id: str) -> dict:
    """`None` means never configured, so it must not override the default.

    Keying on `in stored` treated a stored `None` as a real value, and
    `safe_community_settings` then coerced it with `bool()`. For the one opt-*out*
    field that inverts the member's intent: `discoverable` is None for several accounts,
    and `bool(None)` is False, so saving any unrelated setting would have silently
    removed them from search. `undiscoverable_ids()` only matches an explicit False,
    which is why they are still findable today and why this never surfaced.
    """
    stored = accounts.get_member_settings(user_id)
    return {**DEFAULT_COMMUNITY_SETTINGS, **{
        key: stored[key]
        for key in DEFAULT_COMMUNITY_SETTINGS
        if stored.get(key) is not None
    }}


@router.get("/settings")
def get_settings(user: CurrentUser, accounts: AccountsDependency) -> dict:
    return _current_settings(accounts, user["_id"])


@router.patch("/settings")
def update_settings(
    payload: CommunitySettingsUpdate, user: CurrentUser, accounts: AccountsDependency
) -> dict:
    """Merge onto what is stored. A PATCH must not reset fields it did not mention.

    `safe_community_settings` rebuilds every key from defaults, which is right for
    sanitising but wrong for a partial update: sanitising the raw patch alone silently
    set every unmentioned field back to its default. Turning on research switched photo
    sharing off, and — worse — forced `discoverable` back to True, quietly re-exposing a
    member who had opted out. The UI happened to send the whole object, so only direct
    API callers hit it.
    """
    merged = {
        **_current_settings(accounts, user["_id"]),
        **payload.model_dump(exclude_unset=True),
    }
    safe = safe_community_settings(merged)
    accounts.update_member_settings(user["_id"], safe)
    return safe


@router.get("/posts")
def list_posts(
    user: CurrentUser, community: CommunityDependency, accounts: AccountsDependency
) -> list[dict]:
    posts = community.list_posts()
    authors = accounts.users_by_id(sorted({post["author_id"] for post in posts}))
    for post in posts:
        author = authors.get(post["author_id"])
        post["author"] = (
            {"display_name": author["display_name"], "handle": author["handle"]}
            if author
            else None
        )
    return posts


@router.post("/posts", status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreate, user: CurrentUser, community: CommunityDependency
) -> dict:
    return community.create_post(
        author_id=user["_id"], title=payload.title, body=payload.body, topics=payload.topics
    )


@router.get("/posts/{post_id}")
def get_thread(
    post_id: str,
    request: Request,
    user: CurrentUser,
    community: CommunityDependency,
    accounts: AccountsDependency,
) -> dict:
    post = community.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    author = accounts.users_by_id([post["author_id"]]).get(post["author_id"])
    post["author"] = (
        {"display_name": author["display_name"], "handle": author["handle"]} if author else None
    )
    comments = _decorate(community.list_comments(post_id), accounts)
    outcomes = request.app.state.outcomes
    # Keyed by responder so the UI can show what the asker already reported, and
    # what their agent currently thinks of each responder.
    recorded = outcomes.outcomes_for_context(user["_id"], post_id)
    trust = {
        row["responder_id"]: outcomes.effective_trust(user["_id"], row["responder_id"])
        for row in comments
        if row["responder_id"] != user["_id"]
    }
    return {
        "post": post,
        "comments": comments,
        "my_votes": community.my_votes(user["_id"], post_id),
        "my_outcomes": recorded,
        "trust": trust,
    }


@router.post("/posts/{post_id}/recruit")
def recruit_agents(
    post_id: str,
    request: Request,
    user: CurrentUser,
    community: CommunityDependency,
    accounts: AccountsDependency,
    embeddings: EmbeddingsDependency,
) -> dict:
    """Ask relevant members' agents to weigh in.

    Only the author may trigger this: every recruited agent is an LLM call, so the
    fan-out must not be something any reader can set off repeatedly.
    """
    post = community.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post["author_id"] != user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can ask agents to respond",
        )

    space = embeddings.space()
    query_vector = embeddings.embed(f"{post['title']}\n\n{post['body']}")
    # Ranking runs in the database over an indexed set where Atlas Search is
    # available, instead of pulling every member's chunks into the API.
    chunks_by_user = accounts.search_chunks_global(
        query_vector=query_vector,
        space=space,
        exclude_user_id=user["_id"],
        atlas=request.app.state.people_search._atlas_vector_ok,
    )
    settings_by_user = {
        user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
        for user_id, row in accounts.all_member_settings().items()
    }
    reputation = {
        user_id: community.comment_reputation(user_id) for user_id in chunks_by_user
    }
    # What this author learned from actually meeting these people, plus a weak,
    # reliability-weighted signal from what everyone else learned.
    outcomes = request.app.state.outcomes
    trust = outcomes.trust_map(user["_id"], list(chunks_by_user))

    selected = rank_responders(
        query_vector=query_vector,
        space=space,
        chunks_by_user=chunks_by_user,
        reputation=reputation,
        topics=post.get("topics", []),
        settings_by_user=settings_by_user,
        trust=trust,
        confidence_multiplier=outcomes.confidence_multiplier(user["_id"]),
    )
    if not selected:
        return {
            "post": post,
            "recruited": 0,
            "commented": 0,
            "declined": 0,
            "reason": (
                "No member's agent has both the grounded expertise and the consent "
                "settings to answer this post."
            ),
        }

    commenter = request.app.state.community_commenter
    users = accounts.users_by_id([row["user_id"] for row in selected])
    question = summarize_question(post["title"], post["body"])
    commented = declined = 0

    for candidate in selected:
        responder_id = candidate["user_id"]
        responder = users.get(responder_id) or {}
        member_settings = settings_by_user.get(responder_id, DEFAULT_COMMUNITY_SETTINGS)
        ranked_chunks = sorted(
            chunks_by_user[responder_id],
            key=lambda chunk: chunk["_id"] != candidate["best_chunk_id"],
        )
        draft = commenter.draft(
            post_title=post["title"],
            post_body=post["body"],
            responder_name=responder.get("display_name", "this member"),
            chunks=ranked_chunks,
        )
        community.save_comment(
            post_id=post_id,
            responder_id=responder_id,
            body=draft["body"],
            citations=draft["citations"],
            declined=draft["declined"],
            decline_reason=draft["decline_reason"],
            runtime_mode=draft["runtime_mode"],
            model=draft["model"],
            recruit_score=candidate["recruit_score"],
            # An answer waits for its member when review-before-publish is on.
            published=not draft["declined"]
            and not member_settings.get("review_before_publish", True),
        )
        if draft["declined"]:
            declined += 1
            community.record_gap(
                user_id=responder_id, question=question, source="community", post_id=post_id
            )
        else:
            commented += 1

    updated = community.mark_recruited(post_id, commented=commented, declined=declined)
    return {
        "post": updated,
        "recruited": len(selected),
        "commented": commented,
        "declined": declined,
    }


@router.post("/comments/{comment_id}/vote")
def vote(
    comment_id: str,
    payload: VoteCreate,
    user: CurrentUser,
    community: CommunityDependency,
) -> dict:
    try:
        row = community.vote(comment_id=comment_id, voter_id=user["_id"], value=payload.value)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return row


@router.get("/pending")
def pending_review(user: CurrentUser, community: CommunityDependency) -> list[dict]:
    return community.list_pending_review(user["_id"])


@router.post("/comments/{comment_id}/publish")
def publish(comment_id: str, user: CurrentUser, community: CommunityDependency) -> dict:
    row = community.publish_comment(comment_id, user["_id"])
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found, or it is not yours to publish",
        )
    return row


@router.get("/gaps")
def gaps(user: CurrentUser, community: CommunityDependency) -> list[dict]:
    """Questions this member's agent could not answer. Demand signal for the persona."""
    return community.list_gaps(user["_id"])


@router.get("/gaps/demand")
def gap_demand(user: CurrentUser, community: CommunityDependency) -> dict:
    """What people keep asking that this persona can't answer, ranked by how often.

    The network telling a member what is missing from their own profile. One person
    asking is noise; five asking the same thing is a hole worth filling.
    """
    rows = community.gap_demand(user["_id"])
    return {
        "demand": rows,
        "total_unanswered": sum(row["count"] for row in rows),
    }


@router.post("/gaps/resolve")
def resolve_gaps(
    payload: GapResolve, user: CurrentUser, community: CommunityDependency
) -> dict:
    resolved = community.resolve_gaps(user["_id"], payload.gap_ids)
    return {"resolved": resolved}
