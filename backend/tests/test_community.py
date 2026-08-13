import pytest

from app.accounts import AccountStore
from app.auth import hash_password
from app.community import (
    DEFAULT_COMMUNITY_SETTINGS,
    CommunityStore,
    infer_topics,
    rank_responders,
    safe_community_settings,
)
from app.community_agent import CommentDraft, CommunityCommenter
from app.embeddings import EmbeddingClient
from app.ingestion import ExtractedSource
from app.llm import ChatModelBundle
from app.mock_mongo import create_mock_client
from app.persona import PersonaBuilder
from app.settings import Settings

EMBEDDINGS = EmbeddingClient(provider="local", model="local", dimensions=128, api_key=None)


class FakeStructured:
    def __init__(self, result):
        self.result = result

    def invoke(self, _messages):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeModel:
    """Stands in for ChatOpenAI so tests never touch the network."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def with_structured_output(self, _schema):
        self.calls += 1
        return FakeStructured(self.result)


def build_world():
    client = create_mock_client()
    database = client["agentcircle-community-test"]
    accounts = AccountStore(database)
    accounts.ensure_indexes()
    community = CommunityStore(database)
    community.ensure_indexes()
    builder = PersonaBuilder(
        embeddings=EMBEDDINGS,
        chat=ChatModelBundle(model=None, provider="test", model_name="test-model"),
        settings=Settings(chunk_characters=400, chunk_overlap_characters=40),
    )
    return accounts, community, builder


def add_member(accounts, builder, email, name, text, *, settings=None):
    user = accounts.create_user(
        email=email, password_hash=hash_password("a good password"), display_name=name
    )
    source = ExtractedSource(title=f"{name}.txt", text=text, kind="upload", detail="seed")
    accounts.add_source(
        user_id=user["_id"],
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=builder.prepare_chunks(source),
    )
    if settings is not None:
        accounts.update_member_settings(user["_id"], safe_community_settings(settings))
    return user


OPEN = {"comment_enabled": True, "comment_topics": [], "review_before_publish": False}


# ------------------------------------------------------------------- settings


def test_community_settings_default_closed() -> None:
    assert DEFAULT_COMMUNITY_SETTINGS["comment_enabled"] is False
    assert DEFAULT_COMMUNITY_SETTINGS["review_before_publish"] is True


def test_settings_reject_unknown_topics() -> None:
    safe = safe_community_settings(
        {"comment_enabled": True, "comment_topics": ["design", "not_a_topic"]}
    )
    assert safe["comment_topics"] == ["design"]


def test_topic_inference_reads_the_post() -> None:
    topics = infer_topics("Hiring a backend engineer for our infrastructure team")
    assert "hiring" in topics
    assert "engineering" in topics


# ---------------------------------------------------------------- recruitment


def test_recruitment_prefers_relevant_personas_and_skips_opted_out() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    relevant = add_member(
        accounts, builder, "kenji@example.com", "Kenji",
        "Kenji builds distributed streaming infrastructure and real-time dispatch systems "
        "for energy grids. Deep experience with backpressure and exactly-once delivery.",
        settings=OPEN,
    )
    irrelevant = add_member(
        accounts, builder, "elena@example.com", "Elena",
        "Elena runs clinical operations for outpatient clinics and reviews nursing "
        "discharge workflows.",
        settings=OPEN,
    )
    opted_out = add_member(
        accounts, builder, "sofia@example.com", "Sofia",
        "Sofia builds distributed streaming infrastructure and evaluates real-time systems.",
        settings={"comment_enabled": False},
    )

    ranked = rank_responders(
        query_vector=EMBEDDINGS.embed(
            "How should we design backpressure in a real-time streaming system?"
        ),
        space=EMBEDDINGS.space(),
        chunks_by_user=accounts.chunks_by_user(
            exclude_user_id=author["_id"], space=EMBEDDINGS.space()
        ),
        reputation={},
        topics=[],
        settings_by_user={
            user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
            for user_id, row in accounts.all_member_settings().items()
        },
    )

    selected = [row["user_id"] for row in ranked]
    assert relevant["_id"] in selected
    assert opted_out["_id"] not in selected, "opted-out members must never be recruited"
    assert author["_id"] not in selected, "the author's own agent must not be recruited"
    if irrelevant["_id"] in selected:
        relevant_score = next(r for r in ranked if r["user_id"] == relevant["_id"])
        irrelevant_score = next(r for r in ranked if r["user_id"] == irrelevant["_id"])
        assert relevant_score["recruit_score"] > irrelevant_score["recruit_score"]


def test_topic_consent_filters_recruitment() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    add_member(
        accounts, builder, "design@example.com", "Dana",
        "Dana designs interfaces and builds design systems for early products.",
        settings={"comment_enabled": True, "comment_topics": ["design"]},
    )

    settings_by_user = {
        user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
        for user_id, row in accounts.all_member_settings().items()
    }
    common = {
        "query_vector": EMBEDDINGS.embed("interface design for a new product"),
        "space": EMBEDDINGS.space(),
        "chunks_by_user": accounts.chunks_by_user(
            exclude_user_id=author["_id"], space=EMBEDDINGS.space()
        ),
        "reputation": {},
        "settings_by_user": settings_by_user,
    }

    assert rank_responders(topics=["design"], **common), "matching topic should recruit"
    assert rank_responders(topics=["fundraising"], **common) == [], "non-matching topic must not"


def test_chunks_from_a_stale_embedding_space_are_not_recruited() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    add_member(
        accounts, builder, "kenji@example.com", "Kenji",
        "Kenji builds distributed streaming infrastructure.", settings=OPEN,
    )

    ranked = rank_responders(
        query_vector=[0.1] * 128,
        space="voyage:voyage-3:1024",
        chunks_by_user=accounts.chunks_by_user(exclude_user_id=author["_id"]),
        reputation={},
        topics=[],
        settings_by_user={
            user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
            for user_id, row in accounts.all_member_settings().items()
        },
    )
    assert ranked == []


def test_reputation_reorders_equally_relevant_responders() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    text = "Builds distributed streaming infrastructure and real-time dispatch systems."
    first = add_member(accounts, builder, "a@example.com", "Ana", text, settings=OPEN)
    second = add_member(accounts, builder, "b@example.com", "Ben", text, settings=OPEN)

    common = {
        "query_vector": EMBEDDINGS.embed("real-time streaming infrastructure"),
        "space": EMBEDDINGS.space(),
        "chunks_by_user": accounts.chunks_by_user(
            exclude_user_id=author["_id"], space=EMBEDDINGS.space()
        ),
        "topics": [],
        "settings_by_user": {
            user_id: {**DEFAULT_COMMUNITY_SETTINGS, **row}
            for user_id, row in accounts.all_member_settings().items()
        },
    }

    neutral = rank_responders(reputation={}, **common)
    assert {row["semantic_score"] for row in neutral} == {neutral[0]["semantic_score"]}

    weighted = rank_responders(
        reputation={first["_id"]: 0.1, second["_id"]: 1.0}, **common
    )
    assert weighted[0]["user_id"] == second["_id"], "better-voted agent should rank first"


def test_new_member_reputation_is_neutral_not_zero() -> None:
    _, community, _ = build_world()
    assert community.comment_reputation("nobody") == 0.5


# ------------------------------------------------------------------ commenter


def test_commenter_declines_when_no_model_is_configured() -> None:
    commenter = CommunityCommenter(ChatModelBundle(model=None, provider="t", model_name="t"))
    result = commenter.draft(
        post_title="Designing backpressure",
        post_body="How should we handle backpressure?",
        responder_name="Kenji",
        chunks=[{"_id": "c1", "text": "Kenji builds streaming systems.", "source_title": "cv"}],
    )
    assert result["declined"] is True
    assert result["runtime_mode"] == "deterministic_fallback"
    assert result["body"] == "", "a keyless agent must not invent an opinion"


def test_commenter_declines_without_grounding() -> None:
    commenter = CommunityCommenter(ChatModelBundle(model=None, provider="t", model_name="t"))
    result = commenter.draft(
        post_title="Anything", post_body="Any body", responder_name="Nobody", chunks=[]
    )
    assert result["declined"] is True
    assert result["runtime_mode"] == "no_grounding"


def test_commenter_keeps_only_resolvable_citations() -> None:
    model = FakeModel(
        CommentDraft(
            declined=False,
            body="Kenji has run exactly-once delivery at 400k events per minute.",
            chunk_indexes=[0, 99],
            offer="a walkthrough of the replay logic",
        )
    )
    commenter = CommunityCommenter(
        ChatModelBundle(model=model, provider="test", model_name="fake-model")
    )
    result = commenter.draft(
        post_title="Backpressure",
        post_body="How do we do this safely?",
        responder_name="Kenji",
        chunks=[
            {"_id": "c1", "text": "Exactly-once at 400k events/min.", "source_title": "cv"},
            {"_id": "c2", "text": "Cycles on weekends.", "source_title": "cv"},
        ],
    )

    assert result["declined"] is False
    assert [row["chunk_id"] for row in result["citations"]] == ["c1"]
    assert "Could help with" in result["body"]


def test_uncitable_answer_is_demoted_to_a_decline() -> None:
    model = FakeModel(
        CommentDraft(declined=False, body="Confident but unsourced claim.", chunk_indexes=[])
    )
    commenter = CommunityCommenter(
        ChatModelBundle(model=model, provider="test", model_name="fake-model")
    )
    result = commenter.draft(
        post_title="Backpressure",
        post_body="How?",
        responder_name="Kenji",
        chunks=[{"_id": "c1", "text": "Streaming systems.", "source_title": "cv"}],
    )
    assert result["declined"] is True, "an uncited claim must not reach the thread"


def test_commenter_survives_a_model_failure() -> None:
    commenter = CommunityCommenter(
        ChatModelBundle(model=FakeModel(RuntimeError("boom")), provider="t", model_name="m")
    )
    result = commenter.draft(
        post_title="X", post_body="Y", responder_name="Z",
        chunks=[{"_id": "c1", "text": "text", "source_title": "cv"}],
    )
    assert result["declined"] is True
    assert result["runtime_mode"] == "fallback_after_error"


# --------------------------------------------------------------- posts, votes


def test_declines_are_stored_and_become_context_gaps() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    responder = add_member(accounts, builder, "r@example.com", "Rae", "Rae bio.", settings=OPEN)
    post = community.create_post(
        author_id=author["_id"], title="A question", body="Body of the question here."
    )

    community.save_comment(
        post_id=post["_id"], responder_id=responder["_id"], body="", citations=[],
        declined=True, decline_reason="No grounded expertise", runtime_mode="live",
        model="m", recruit_score=0.3, published=False,
    )
    community.record_gap(
        user_id=responder["_id"], question="A question", source="community", post_id=post["_id"]
    )

    comments = community.list_comments(post["_id"])
    assert len(comments) == 1 and comments[0]["declined"] is True
    assert community.list_comments(post["_id"], include_declined=False) == []
    gaps = community.list_gaps(responder["_id"])
    assert len(gaps) == 1 and gaps[0]["question"] == "A question"


def test_recruiting_twice_updates_rather_than_duplicates() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    responder = add_member(accounts, builder, "r@example.com", "Rae", "Rae bio.", settings=OPEN)
    post = community.create_post(
        author_id=author["_id"], title="A question", body="Body of the question here."
    )

    for body in ("first answer", "second answer"):
        community.save_comment(
            post_id=post["_id"], responder_id=responder["_id"], body=body, citations=[],
            declined=False, decline_reason=None, runtime_mode="live", model="m",
            recruit_score=0.4, published=True,
        )

    comments = community.list_comments(post["_id"])
    assert len(comments) == 1
    assert comments[0]["body"] == "second answer"


def test_votes_are_recomputed_and_drive_reputation() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    voter = add_member(accounts, builder, "v@example.com", "Val", "Val bio.")
    responder = add_member(accounts, builder, "r@example.com", "Rae", "Rae bio.", settings=OPEN)
    post = community.create_post(
        author_id=author["_id"], title="A question", body="Body of the question here."
    )
    comment = community.save_comment(
        post_id=post["_id"], responder_id=responder["_id"], body="An answer", citations=[],
        declined=False, decline_reason=None, runtime_mode="live", model="m",
        recruit_score=0.4, published=True,
    )

    baseline = community.comment_reputation(responder["_id"])
    for value in (1, 1, -1):  # same voter changing their mind
        row = community.vote(comment_id=comment["_id"], voter_id=voter["_id"], value=value)
    assert row["score"] == -1, "re-voting must replace, not accumulate"
    assert community.comment_reputation(responder["_id"]) < baseline

    community.vote(comment_id=comment["_id"], voter_id=author["_id"], value=1)
    final = community.vote(comment_id=comment["_id"], voter_id=voter["_id"], value=0)
    assert final["score"] == 1 and final["up_votes"] == 1 and final["down_votes"] == 0


def test_you_cannot_vote_on_your_own_agents_comment() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    responder = add_member(accounts, builder, "r@example.com", "Rae", "Rae bio.", settings=OPEN)
    post = community.create_post(
        author_id=author["_id"], title="A question", body="Body of the question here."
    )
    comment = community.save_comment(
        post_id=post["_id"], responder_id=responder["_id"], body="An answer", citations=[],
        declined=False, decline_reason=None, runtime_mode="live", model="m",
        recruit_score=0.4, published=True,
    )

    with pytest.raises(PermissionError):
        community.vote(comment_id=comment["_id"], voter_id=responder["_id"], value=1)


def test_review_before_publish_holds_the_comment_until_its_member_releases_it() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    responder = add_member(
        accounts, builder, "r@example.com", "Rae", "Rae bio.",
        settings={"comment_enabled": True, "review_before_publish": True},
    )
    post = community.create_post(
        author_id=author["_id"], title="A question", body="Body of the question here."
    )
    community.save_comment(
        post_id=post["_id"], responder_id=responder["_id"], body="An answer", citations=[],
        declined=False, decline_reason=None, runtime_mode="live", model="m",
        recruit_score=0.4, published=False,
    )

    pending = community.list_pending_review(responder["_id"])
    assert len(pending) == 1
    released = community.publish_comment(pending[0]["_id"], responder["_id"])
    assert released["published"] is True
    assert community.list_pending_review(responder["_id"]) == []


def test_publish_requires_ownership() -> None:
    accounts, community, builder = build_world()
    author = add_member(accounts, builder, "author@example.com", "Author", "Author bio.")
    responder = add_member(accounts, builder, "r@example.com", "Rae", "Rae bio.", settings=OPEN)
    post = community.create_post(
        author_id=author["_id"], title="A question", body="Body of the question here."
    )
    comment = community.save_comment(
        post_id=post["_id"], responder_id=responder["_id"], body="An answer", citations=[],
        declined=False, decline_reason=None, runtime_mode="live", model="m",
        recruit_score=0.4, published=False,
    )

    assert community.publish_comment(comment["_id"], author["_id"]) is None
    assert community.publish_comment(comment["_id"], responder["_id"])["published"] is True
