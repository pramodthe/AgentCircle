"""Run the real community recruitment path over seeded threads.

Posts already in `community_posts` get grounded agent comments (or recorded declines)
the same way `POST /api/community/posts/{id}/recruit` does. When a draft is not
declined and the member has review-before-publish on, this script then calls
`publish_comment` as that member — the approval gate, not the model publishing.

Idempotent: a post that already has comments is left alone.
"""

from __future__ import annotations

from app.accounts import AccountStore
from app.community import (
    DEFAULT_COMMUNITY_SETTINGS,
    CommunityStore,
    rank_responders,
    summarize_question,
)
from app.community_agent import CommunityCommenter
from app.outcomes import OutcomeStore


def seed_community_agents(
    *,
    database,
    accounts: AccountStore,
    community: CommunityStore,
    embeddings,
    commenter: CommunityCommenter,
    atlas: bool = False,
) -> dict[str, int]:
    posts = list(database.community_posts.find({}))
    outcomes = OutcomeStore(database)
    totals = {"posts": len(posts), "commented": 0, "declined": 0, "skipped": 0}

    for post in posts:
        post_id = post["_id"]
        title = (post.get("title") or "").strip() or "(untitled)"
        label = title[:53] + "..." if len(title) > 56 else title
        if database.community_comments.find_one({"post_id": post_id}, {"_id": 1}):
            totals["skipped"] += 1
            print(f"  {label}  skipped (already has comments)")
            continue

        commented, declined = _recruit_post(
            post,
            accounts=accounts,
            community=community,
            embeddings=embeddings,
            commenter=commenter,
            outcomes=outcomes,
            atlas=atlas,
        )
        totals["commented"] += commented
        totals["declined"] += declined
        print(f"  {label}  commented={commented}  declined={declined}")

    return totals


def _recruit_post(
    post: dict,
    *,
    accounts: AccountStore,
    community: CommunityStore,
    embeddings,
    commenter: CommunityCommenter,
    outcomes: OutcomeStore,
    atlas: bool,
) -> tuple[int, int]:
    """One post through the same path as `recruit_agents`. Returns (commented, declined)."""
    post_id = post["_id"]
    author_id = post["author_id"]
    title = post.get("title") or ""
    body = post.get("body") or ""

    space = embeddings.space()
    query_vector = embeddings.embed(f"{title}\n\n{body}")
    chunks_by_user = accounts.search_chunks_global(
        query_vector=query_vector,
        space=space,
        exclude_user_id=author_id,
        atlas=atlas,
    )
    settings_by_user = {
        user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
        for user_id, row in accounts.all_member_settings().items()
    }
    reputation = {user_id: community.comment_reputation(user_id) for user_id in chunks_by_user}
    trust = outcomes.trust_map(author_id, list(chunks_by_user))

    selected = rank_responders(
        query_vector=query_vector,
        space=space,
        chunks_by_user=chunks_by_user,
        reputation=reputation,
        topics=post.get("topics", []),
        settings_by_user=settings_by_user,
        trust=trust,
        confidence_multiplier=outcomes.confidence_multiplier(author_id),
    )
    if not selected:
        return 0, 0

    users = accounts.users_by_id([row["user_id"] for row in selected])
    question = summarize_question(title, body)
    commented = declined = 0

    for candidate in selected:
        responder_id = candidate["user_id"]
        responder = users.get(responder_id) or {}
        member_settings = settings_by_user.get(responder_id, DEFAULT_COMMUNITY_SETTINGS)
        review_before_publish = member_settings.get("review_before_publish", True)
        ranked_chunks = sorted(
            chunks_by_user[responder_id],
            key=lambda chunk: chunk["_id"] != candidate["best_chunk_id"],
        )
        draft = commenter.draft(
            post_title=title,
            post_body=body,
            responder_name=responder.get("display_name", "this member"),
            chunks=ranked_chunks,
        )
        comment = community.save_comment(
            post_id=post_id,
            responder_id=responder_id,
            body=draft["body"],
            citations=draft["citations"],
            declined=draft["declined"],
            decline_reason=draft["decline_reason"],
            runtime_mode=draft["runtime_mode"],
            model=draft["model"],
            recruit_score=candidate["recruit_score"],
            published=not draft["declined"] and not review_before_publish,
        )
        if draft["declined"]:
            declined += 1
            community.record_gap(
                user_id=responder_id, question=question, source="community", post_id=post_id
            )
        else:
            commented += 1
            # Seed acts as the member approving — the model never publishes.
            if review_before_publish:
                community.publish_comment(comment["_id"], responder_id)

    community.mark_recruited(post_id, commented=commented, declined=declined)
    return commented, declined
