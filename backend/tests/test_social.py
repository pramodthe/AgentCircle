import pytest

from app.mock_mongo import create_mock_client
from app.social import (
    MIN_INGEST_CHARACTERS,
    ConnectionStore,
    FeedStore,
    build_agent_post,
    pair_id,
    should_ingest,
)


def stores():
    db = create_mock_client()["social-test"]
    connections, feed = ConnectionStore(db), FeedStore(db)
    connections.ensure_indexes()
    feed.ensure_indexes()
    return connections, feed


# ----------------------------------------------------------------- connections


def test_pair_id_is_order_independent() -> None:
    assert pair_id("b", "a") == pair_id("a", "b") == "a:b"


def test_request_accept_flow() -> None:
    connections, _ = stores()
    row = connections.request(requester_id="ada", recipient_id="bo", source="discovery")
    assert row["status"] == "pending"
    assert row["source"] == "discovery"

    accepted = connections.respond(pair=row["_id"], recipient_id="bo", accept=True)
    assert accepted["status"] == "accepted"
    assert connections.connected_ids("ada") == ["bo"]
    assert connections.connected_ids("bo") == ["ada"]


def test_ignoring_a_request_does_not_connect() -> None:
    connections, _ = stores()
    row = connections.request(requester_id="ada", recipient_id="bo")
    connections.respond(pair=row["_id"], recipient_id="bo", accept=False)
    assert connections.connected_ids("ada") == []
    assert connections.status_between("ada", "bo")["status"] == "ignored"


def test_only_the_recipient_can_answer_a_request() -> None:
    connections, _ = stores()
    row = connections.request(requester_id="ada", recipient_id="bo")
    with pytest.raises(PermissionError):
        connections.respond(pair=row["_id"], recipient_id="ada", accept=True)


def test_only_the_requester_can_withdraw() -> None:
    connections, _ = stores()
    row = connections.request(requester_id="ada", recipient_id="bo")
    with pytest.raises(PermissionError):
        connections.withdraw(pair=row["_id"], requester_id="bo")
    assert connections.withdraw(pair=row["_id"], requester_id="ada")["status"] == "withdrawn"


def test_crossing_requests_become_a_connection() -> None:
    """Two people reaching for each other is a connection, not a conflict."""
    connections, _ = stores()
    connections.request(requester_id="ada", recipient_id="bo")
    row = connections.request(requester_id="bo", recipient_id="ada")

    assert row["status"] == "accepted"
    assert connections.connected_ids("ada") == ["bo"]


def test_you_cannot_connect_with_yourself() -> None:
    connections, _ = stores()
    with pytest.raises(PermissionError):
        connections.request(requester_id="ada", recipient_id="ada")


def test_unknown_source_is_rejected() -> None:
    connections, _ = stores()
    with pytest.raises(ValueError):
        connections.request(requester_id="ada", recipient_id="bo", source="telepathy")


def test_repeat_request_does_not_duplicate() -> None:
    connections, _ = stores()
    connections.request(requester_id="ada", recipient_id="bo")
    connections.request(requester_id="ada", recipient_id="bo")
    assert len(connections.pending_for("bo")["incoming"]) == 1


def test_provenance_counts_show_what_produced_connections() -> None:
    connections, _ = stores()
    for other, source in [("bo", "discovery"), ("cy", "interview"), ("di", "discovery")]:
        row = connections.request(requester_id="ada", recipient_id=other, source=source)
        connections.respond(pair=row["_id"], recipient_id=other, accept=True)

    assert connections.provenance_counts("ada") == {"discovery": 2, "interview": 1}


def test_pending_separates_incoming_from_outgoing() -> None:
    connections, _ = stores()
    connections.request(requester_id="ada", recipient_id="bo")
    connections.request(requester_id="cy", recipient_id="ada")

    pending = connections.pending_for("ada")
    assert [row["recipient_id"] for row in pending["outgoing"]] == ["bo"]
    assert [row["requester_id"] for row in pending["incoming"]] == ["cy"]


# ------------------------------------------------------------------------ feed


def test_short_posts_are_not_ingested_into_retrieval() -> None:
    """Indexing 'congrats!' teaches the agent nothing and pollutes retrieval."""
    assert should_ingest("congrats!") is False
    assert should_ingest("x" * MIN_INGEST_CHARACTERS) is True


def test_feed_puts_connections_first_then_the_wider_network() -> None:
    _, feed = stores()
    feed.create(author_id="stranger", body="a stranger post")
    feed.create(author_id="friend", body="a friend post")

    posts = feed.list_feed(viewer_id="ada", connected_ids=["friend"])
    assert posts[0]["author_id"] == "friend", "connections rank above strangers"
    assert {p["author_id"] for p in posts} == {"friend", "stranger"}, (
        "a young network still shows the wider network rather than looking empty"
    )


def test_feed_preserves_story_presentation() -> None:
    _, feed = stores()
    story = feed.create(author_id="ada", body="A quick launch update", presentation="story")

    assert story["presentation"] == "story"


def test_reactions_are_recounted_not_incremented() -> None:
    _, feed = stores()
    post = feed.create(author_id="ada", body="a post")

    feed.react(post_id=post["_id"], user_id="bo", reaction="like")
    row = feed.react(post_id=post["_id"], user_id="bo", reaction="insightful")
    assert row["reaction_counts"] == {"insightful": 1}, "changing a reaction must replace it"

    feed.react(post_id=post["_id"], user_id="cy", reaction="insightful")
    row = feed.react(post_id=post["_id"], user_id="bo", reaction=None)
    assert row["reaction_counts"] == {"insightful": 1}


def test_unknown_reaction_is_rejected() -> None:
    _, feed = stores()
    post = feed.create(author_id="ada", body="a post")
    with pytest.raises(ValueError):
        feed.react(post_id=post["_id"], user_id="bo", reaction="downvote")


def test_reacting_to_a_missing_post_returns_none() -> None:
    _, feed = stores()
    assert feed.react(post_id="nope", user_id="bo", reaction="like") is None


def test_my_reactions_are_scoped_to_the_viewer() -> None:
    _, feed = stores()
    post = feed.create(author_id="ada", body="a post")
    feed.react(post_id=post["_id"], user_id="bo", reaction="like")

    assert feed.my_reactions("bo", [post["_id"]]) == {post["_id"]: "like"}
    assert feed.my_reactions("cy", [post["_id"]]) == {}


# ----------------------------------------------------------------- agent posts


def test_agent_post_is_none_without_activity() -> None:
    assert build_agent_post(display_name="Ada", gaps=[], interviews=[]) is None


def test_agent_post_reports_only_what_the_records_support() -> None:
    draft = build_agent_post(
        display_name="Ada",
        gaps=[
            {"_id": "g1", "question": "What's your on-call rotation like?"},
            {"_id": "g2", "question": "Do you do fractional work?"},
        ],
        interviews=[
            {
                "_id": "i1",
                "goal": "find a cofounder",
                "answered_count": 2,
                "question_count": 3,
            }
        ],
    )

    assert "2 questions it couldn't answer" in draft["body"]
    assert "1 agent interview" in draft["body"]
    assert "answering 2 of 3 questions" in draft["body"]
    # Every claim carries the record it came from.
    assert {e["kind"] for e in draft["evidence"]} == {"gap", "interview"}
    assert len(draft["evidence"]) == 3


def test_agent_post_does_not_double_terminal_punctuation() -> None:
    """Clauses often end by quoting a question; "…looking for?." reads as slop."""
    draft = build_agent_post(
        display_name="Ada",
        gaps=[{"_id": "g1", "question": "What kind of role are you looking for?"}],
        interviews=[],
    )
    assert "?." not in draft["body"]
    assert draft["body"].endswith("?")


def test_agent_post_pluralizes_a_single_gap_correctly() -> None:
    draft = build_agent_post(
        display_name="Ada", gaps=[{"_id": "g1", "question": "One question?"}], interviews=[]
    )
    assert "1 question it couldn't answer" in draft["body"]
    assert "questions it couldn't" not in draft["body"]


def test_a_story_becomes_episodic_memory_at_a_lower_floor_than_a_post() -> None:
    """A dated episode is worth recalling at a length a standing claim is not."""
    from app.social import MIN_INGEST_CHARACTERS, should_ingest

    episode = "Shipped the replay path after three weeks of backpressure bugs."
    assert len(episode) < MIN_INGEST_CHARACTERS
    assert should_ingest(episode, "story")
    assert not should_ingest(episode, "post")

    # The floor still sits above pleasantries, which is what it is for.
    assert not should_ingest("congrats!", "story")


def test_a_story_is_filed_as_a_dated_episode_not_a_standing_claim() -> None:
    from app.social import episodic_title

    assert episodic_title("2026-08-13T03:32:33+00:00") == "Story · 2026-08-13"


def test_only_the_story_card_expires_never_the_memory() -> None:
    """The strip empties after a day; the post and its persona chunks do not."""
    from datetime import UTC, datetime, timedelta

    from app.social import STORY_ACTIVE_HOURS, story_is_active

    _, feed = stores()
    story = feed.create(author_id="ada", body="A launch update", presentation="story")
    assert story_is_active(story)

    feed.db.feed_posts.update_one(
        {"_id": story["_id"]},
        {"$set": {"created_at": datetime.now(UTC) - timedelta(hours=STORY_ACTIVE_HOURS + 1)}},
    )
    stale = feed.db.feed_posts.find_one({"_id": story["_id"]})
    assert not story_is_active(stale)
    # Still a post in the feed — expiry is presentation, not deletion.
    assert stale["body"] == "A launch update"


def test_an_ordinary_post_is_never_treated_as_an_active_story() -> None:
    from app.social import story_is_active

    _, feed = stores()
    assert not story_is_active(feed.create(author_id="ada", body="a post"))


def test_story_image_is_stored_as_presentation_not_persona_media() -> None:
    """Create story uploads a photo that never becomes searchable persona evidence."""
    from app.media import MediaError

    _, feed = stores()
    # Minimal valid JPEG-ish bytes aren't required — validate checks type + non-empty.
    media_id, media_type = feed.save_story_image(
        user_id="ada",
        image=b"\xff\xd8\xfffakejpeg",
        media_type="image/jpeg",
    )
    assert media_id.startswith("sm_")
    assert media_type == "image/jpeg"
    assert feed.story_image_owned(media_id)["user_id"] == "ada"
    assert feed.story_blob(media_id)["bytes"] == b"\xff\xd8\xfffakejpeg"
    # Persona photo ids must not resolve through the story path.
    assert feed.story_blob("pm_avatar_ada") is None

    story = feed.create(
        author_id="ada",
        body="Shared a story",
        presentation="story",
        image_media_id=media_id,
        image_media_type=media_type,
    )
    assert story["image_media_id"] == media_id
    assert story["presentation"] == "story"

    try:
        feed.save_story_image(user_id="ada", image=b"", media_type="image/jpeg")
        raise AssertionError("empty image should fail")
    except MediaError:
        pass
