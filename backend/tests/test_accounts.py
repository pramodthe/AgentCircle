import pytest

from app.accounts import AccountStore, slugify_handle
from app.auth import create_access_token, decode_access_token, hash_password, verify_password
from app.embeddings import EmbeddingClient
from app.ingestion import ExtractedSource, chunk_text, extract_html, normalize_url
from app.llm import ChatModelBundle
from app.mock_mongo import create_mock_client
from app.persona import PersonaBuilder
from app.settings import Settings


def build_accounts() -> AccountStore:
    client = create_mock_client()
    accounts = AccountStore(client["agentcircle-accounts-test"])
    accounts.ensure_indexes()
    return accounts


def build_builder() -> PersonaBuilder:
    settings = Settings(chunk_characters=300, chunk_overlap_characters=40)
    return PersonaBuilder(
        embeddings=EmbeddingClient(
            provider="local", model="local", dimensions=128, api_key=None
        ),
        chat=ChatModelBundle(model=None, provider="test", model_name="test-model"),
        settings=settings,
    )


def register(accounts: AccountStore, email: str, name: str) -> dict:
    return accounts.create_user(
        email=email, password_hash=hash_password("correct horse battery"), display_name=name
    )


# ----------------------------------------------------------------------- auth


def test_password_hash_round_trips_and_rejects_wrong_password() -> None:
    digest = hash_password("correct horse battery")
    assert digest != "correct horse battery"
    assert verify_password("correct horse battery", digest)
    assert not verify_password("wrong password", digest)


def test_password_longer_than_bcrypt_limit_is_rejected_not_truncated() -> None:
    with pytest.raises(ValueError):
        hash_password("a" * 73)


def test_access_token_round_trips_and_rejects_tampering() -> None:
    token = create_access_token("user-123")
    assert decode_access_token(token) == "user-123"
    assert decode_access_token(token + "x") is None
    assert decode_access_token("not-a-token") is None


# -------------------------------------------------------------------- accounts


def test_email_is_normalized_and_handles_stay_unique() -> None:
    accounts = build_accounts()
    first = register(accounts, "Alex@Example.com ", "Alex Morgan")
    second = register(accounts, "alex2@example.com", "Alex Morgan")

    assert first["email"] == "alex@example.com"
    assert accounts.get_user_by_email("ALEX@EXAMPLE.COM")["_id"] == first["_id"]
    assert first["handle"] == "alex_morgan"
    assert second["handle"] != first["handle"]


def test_reserved_handles_are_not_allocated() -> None:
    accounts = build_accounts()
    user = register(accounts, "admin@example.com", "admin")
    assert user["handle"] not in {"admin", "settings", "login"}


def test_public_user_never_exposes_password_hash() -> None:
    accounts = build_accounts()
    user = register(accounts, "alex@example.com", "Alex Morgan")
    public = accounts.public_user(user)
    assert "password_hash" not in public
    assert public["email"] == "alex@example.com"


def test_profile_update_ignores_unknown_fields() -> None:
    accounts = build_accounts()
    user = register(accounts, "alex@example.com", "Alex Morgan")

    profile = accounts.update_profile(
        user["_id"],
        {
            "headline": "Founder, onboarding tools",
            "interests": ["climbing", "b2b saas"],
            "reliability": 1.0,
            "is_admin": True,
        },
    )

    assert profile["headline"] == "Founder, onboarding tools"
    assert profile["interests"] == ["climbing", "b2b saas"]
    assert "reliability" not in profile
    assert "is_admin" not in profile


def test_slugify_handle_strips_unsafe_characters() -> None:
    assert slugify_handle("Alex Morgan!!") == "alex_morgan"
    assert slugify_handle("  ***  ") == ""


# ------------------------------------------------------------------- ingestion


def test_chunking_covers_all_text_and_respects_size() -> None:
    text = "\n\n".join(f"Paragraph {index} about onboarding." for index in range(40))
    chunks = chunk_text(text, size=300, overlap=40)

    assert len(chunks) > 1
    assert all(len(chunk) <= 300 for chunk in chunks)
    assert "Paragraph 0" in chunks[0]
    assert "Paragraph 39" in chunks[-1]


def test_oversized_paragraph_is_split_rather_than_dropped() -> None:
    chunks = chunk_text("x" * 1000, size=200, overlap=20)
    assert chunks
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_html_extraction_drops_scripts_and_navigation() -> None:
    title, text = extract_html(
        "<html><head><title>Alex</title></head><body>"
        "<nav>Home About</nav><script>alert(1)</script>"
        "<p>Builds onboarding tools for B2B teams.</p></body></html>"
    )
    assert title == "Alex"
    assert "onboarding tools" in text
    assert "alert" not in text
    assert "Home About" not in text


def test_url_normalization_adds_scheme_and_rejects_junk() -> None:
    from app.ingestion import IngestionError

    assert normalize_url("example.com/alex") == "https://example.com/alex"
    with pytest.raises(IngestionError):
        normalize_url("   ")


# --------------------------------------------------------------------- persona


def test_persona_build_stores_chunks_and_reports_missing_fields() -> None:
    accounts = build_accounts()
    builder = build_builder()
    user = register(accounts, "alex@example.com", "Alex Morgan")
    source = ExtractedSource(
        title="alex-resume.pdf",
        text="\n\n".join(
            [
                "Alex Morgan is a founder building onboarding tools for B2B SaaS teams.",
                "Previously led product at a developer tools company in San Francisco.",
                "Interested in climbing, typography, and early-stage go-to-market.",
            ]
        ),
        kind="upload",
        detail="alex-resume.pdf",
    )

    chunks = builder.prepare_chunks(source)
    stored = accounts.add_source(
        user_id=user["_id"],
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=chunks,
    )
    persona = builder.extract(
        chunks=accounts.list_chunks(user["_id"], with_embedding=False),
        extras={"headline": "Founder", "skills": ["onboarding"]},
    )
    saved = accounts.save_persona(user["_id"], persona)

    assert stored["chunk_count"] == len(chunks)
    assert saved["extraction_mode"] == "heuristic"
    assert saved["headline"] == "Founder"
    assert [item["value"] for item in saved["skills"]] == ["onboarding"]
    # No model configured, so nothing was extracted for these — and the persona says so
    # rather than inventing values.
    assert "interests" in saved["coverage"]["missing"]
    assert saved["coverage"]["score"] < 1.0


def test_persona_search_never_returns_another_users_chunks() -> None:
    accounts = build_accounts()
    builder = build_builder()
    alex = register(accounts, "alex@example.com", "Alex Morgan")
    priya = register(accounts, "priya@example.com", "Priya Raman")

    for user_id, text in (
        (alex["_id"], "Alex builds onboarding analytics for B2B SaaS teams."),
        (priya["_id"], "Priya runs clinical operations at a healthcare startup."),
    ):
        source = ExtractedSource(title="bio.txt", text=text, kind="upload", detail="bio.txt")
        accounts.add_source(
            user_id=user_id,
            title=source.title,
            kind=source.kind,
            detail=source.detail,
            text=source.text,
            chunks=builder.prepare_chunks(source),
        )

    query_vector = builder.embeddings.embed("clinical operations healthcare")
    results = accounts.search_chunks(
        user_id=alex["_id"], query_vector=query_vector, space=builder.embeddings.space()
    )

    assert results, "expected Alex's own chunks to be returned"
    assert all(row["user_id"] == alex["_id"] for row in results)
    assert all("Priya" not in row["text"] for row in results)


def test_chunks_from_a_different_embedding_space_are_ignored() -> None:
    accounts = build_accounts()
    builder = build_builder()
    user = register(accounts, "alex@example.com", "Alex Morgan")
    source = ExtractedSource(
        title="bio.txt", text="Alex builds onboarding tools.", kind="upload", detail="bio.txt"
    )
    accounts.add_source(
        user_id=user["_id"],
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=builder.prepare_chunks(source),
    )

    stale = accounts.search_chunks(
        user_id=user["_id"],
        query_vector=[0.1] * 128,
        space="voyage:voyage-3:1024",
    )
    assert stale == []


def test_deleting_a_source_removes_its_chunks() -> None:
    accounts = build_accounts()
    builder = build_builder()
    user = register(accounts, "alex@example.com", "Alex Morgan")
    source = ExtractedSource(
        title="bio.txt", text="Alex builds onboarding tools.", kind="upload", detail="bio.txt"
    )
    stored = accounts.add_source(
        user_id=user["_id"],
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=builder.prepare_chunks(source),
    )

    assert accounts.list_chunks(user["_id"])
    assert accounts.delete_source(user["_id"], stored["_id"]) is True
    assert accounts.list_chunks(user["_id"]) == []
    assert accounts.delete_source(user["_id"], stored["_id"]) is False


def test_a_user_cannot_delete_another_users_source() -> None:
    accounts = build_accounts()
    builder = build_builder()
    alex = register(accounts, "alex@example.com", "Alex Morgan")
    priya = register(accounts, "priya@example.com", "Priya Raman")
    source = ExtractedSource(
        title="bio.txt", text="Alex builds onboarding tools.", kind="upload", detail="bio.txt"
    )
    stored = accounts.add_source(
        user_id=alex["_id"],
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=builder.prepare_chunks(source),
    )

    assert accounts.delete_source(priya["_id"], stored["_id"]) is False
    assert accounts.list_chunks(alex["_id"])


def test_onboarding_state_tracks_progress() -> None:
    accounts = build_accounts()
    builder = build_builder()
    user = register(accounts, "alex@example.com", "Alex Morgan")

    initial = accounts.onboarding_state(user["_id"])
    assert initial["complete"] is False
    assert initial["steps"]["sources"] is False

    accounts.update_profile(
        user["_id"], {"headline": "Founder", "interests": ["climbing"]}
    )
    source = ExtractedSource(
        title="bio.txt", text="Alex builds onboarding tools.", kind="upload", detail="bio.txt"
    )
    accounts.add_source(
        user_id=user["_id"],
        title=source.title,
        kind=source.kind,
        detail=source.detail,
        text=source.text,
        chunks=builder.prepare_chunks(source),
    )
    accounts.save_persona(
        user["_id"],
        builder.extract(chunks=accounts.list_chunks(user["_id"], with_embedding=False)),
    )

    final = accounts.onboarding_state(user["_id"])
    assert final["steps"] == {
        "account": True,
        "profile": True,
        "sources": True,
        "extras": True,
        "persona": True,
    }
    assert final["complete"] is True


def test_a_members_email_never_reaches_another_member() -> None:
    """`public_user` keeps the owner's own email; everyone else must get `public_member`.

    Found by reading a live photo-search response: `/api/profile/{handle}` takes no auth
    at all and was returning `email` for every member, so the whole directory was
    harvestable by anyone who could reach the API.
    """
    accounts = AccountStore(create_mock_client()["leak-test"])
    accounts.ensure_indexes()
    user = accounts.create_user(
        email="kenji@example.com",
        password_hash=hash_password("a good password"),
        display_name="Kenji Tanaka",
    )

    mine = accounts.public_user(user)
    assert mine["email"] == "kenji@example.com", "your own record still shows your email"

    theirs = accounts.public_member(user)
    assert set(theirs) == {"_id", "display_name", "handle"}
    assert "email" not in theirs
    assert "password_hash" not in theirs


def test_public_member_is_an_allowlist_so_new_fields_cannot_leak() -> None:
    """A denylist is what let `email` through; a field added later must not repeat it."""
    accounts = AccountStore(create_mock_client()["leak-test-2"])
    accounts.ensure_indexes()
    user = accounts.create_user(
        email="ada@example.com",
        password_hash=hash_password("a good password"),
        display_name="Ada",
    )
    accounts.db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"phone_number": "+1 555 0100", "reset_token": "secret"}},
    )
    stored = accounts.get_user(user["_id"])

    assert "phone_number" not in accounts.public_member(stored)
    assert "reset_token" not in accounts.public_member(stored)
