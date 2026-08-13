from app.accounts import AccountStore
from app.auth import hash_password
from app.community import CommunityStore, safe_community_settings
from app.community_agent import CommunityCommenter
from app.embeddings import build_embedding_client
from app.ingestion import ExtractedSource
from app.llm import build_chat_model
from app.mock_mongo import create_mock_client
from app.persona import PersonaBuilder
from app.settings import get_settings
from scripts.demo_community import seed_community_agents

COMMENT_ON = safe_community_settings(
    {"comment_enabled": True, "comment_topics": ["engineering"], "review_before_publish": True}
)


def _world():
    settings = get_settings()
    database = create_mock_client()["demo-community"]
    accounts = AccountStore(database)
    community = CommunityStore(database)
    accounts.ensure_indexes()
    community.ensure_indexes()
    embeddings = build_embedding_client(settings)
    chat = build_chat_model(settings)
    builder = PersonaBuilder(embeddings=embeddings, chat=chat, settings=settings)
    commenter = CommunityCommenter(chat)
    return database, accounts, community, embeddings, builder, commenter


def _add_member(accounts, builder, password_hash, email, name, text, *, settings=None):
    user = accounts.create_user(email=email, password_hash=password_hash, display_name=name)
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
        accounts.update_member_settings(user["_id"], settings)
    return user


def test_seed_community_agents_writes_declines_and_is_idempotent() -> None:
    database, accounts, community, embeddings, builder, commenter = _world()
    password_hash = hash_password("agentcircle")

    author = _add_member(
        accounts, builder, password_hash,
        "author@example.com", "Ada",
        "Ada writes product notes and convenes the engineering discussion.",
    )
    _add_member(
        accounts, builder, password_hash,
        "kenji@example.com", "Kenji",
        "Kenji builds distributed streaming infrastructure and real-time dispatch "
        "systems. Deep experience with backpressure and backend database design.",
        settings=COMMENT_ON,
    )
    _add_member(
        accounts, builder, password_hash,
        "priya@example.com", "Priya",
        "Priya designs backend APIs and infrastructure for engineering teams "
        "shipping streaming systems.",
        settings=COMMENT_ON,
    )

    post = community.create_post(
        author_id=author["_id"],
        title="How should we design backpressure in a real-time streaming system?",
        body=(
            "We need backend infrastructure advice on backpressure and exactly-once "
            "delivery for our engineering team."
        ),
    )

    summary = seed_community_agents(
        database=database,
        accounts=accounts,
        community=community,
        embeddings=embeddings,
        commenter=commenter,
        atlas=False,
    )

    comments = list(database.community_comments.find({"post_id": post["_id"]}))
    assert comments, "recruitment should write a comment per selected agent"
    assert summary["posts"] == 1
    assert summary["skipped"] == 0
    assert summary["declined"] == len(comments)
    assert summary["commented"] == 0
    assert all(row["declined"] is True for row in comments)
    assert all(row["runtime_mode"] == "deterministic_fallback" for row in comments)
    assert all(row["responder_id"] != author["_id"] for row in comments)

    stored = community.get_post(post["_id"])
    assert stored["recruited_at"] is not None
    assert stored["declined_count"] == len(comments)

    again = seed_community_agents(
        database=database,
        accounts=accounts,
        community=community,
        embeddings=embeddings,
        commenter=commenter,
        atlas=False,
    )
    assert again["skipped"] == 1
    assert again["commented"] == 0
    assert again["declined"] == 0
    assert database.community_comments.count_documents({"post_id": post["_id"]}) == len(comments)
