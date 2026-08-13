from app.accounts import AccountStore
from app.auth import hash_password
from app.mock_mongo import create_mock_client


def store_with_member():
    accounts = AccountStore(create_mock_client()["theme-test"])
    accounts.ensure_indexes()
    user = accounts.create_user(
        email="ada@example.com", password_hash=hash_password("a good password"),
        display_name="Ada",
    )
    return accounts, user["_id"]


def test_profile_edits_persist_after_onboarding() -> None:
    """PATCH /api/profile existed all along; nothing called it until the editor."""
    accounts, uid = store_with_member()
    accounts.update_profile(uid, {"headline": "First try", "bio": "v1"})
    updated = accounts.update_profile(uid, {"headline": "Corrected", "bio": "v2"})

    assert updated["headline"] == "Corrected"
    assert updated["bio"] == "v2"
    assert accounts.get_profile(uid)["headline"] == "Corrected"


def test_display_name_edit_propagates_to_the_user_record() -> None:
    accounts, uid = store_with_member()
    accounts.update_profile(uid, {"display_name": "Ada Lovelace"})
    assert accounts.get_user(uid)["display_name"] == "Ada Lovelace"


def test_theme_is_stored_but_only_whitelisted_keys_survive() -> None:
    accounts, uid = store_with_member()
    profile = accounts.update_profile(
        uid,
        {"theme": {
            "accent": "coral",
            "layout": "retro",
            "font": '"Courier New", monospace',
            "onerror": "alert(1)",
            "position": "fixed",
        }},
    )
    assert profile["theme"]["accent"] == "coral"
    assert profile["theme"]["layout"] == "retro"
    assert "onerror" not in profile["theme"], "arbitrary style keys must not persist"
    assert "position" not in profile["theme"]


def test_theme_never_reaches_the_retrieval_layer() -> None:
    """Restyling a page must not change who gets found, or theming is an SEO surface."""
    from app.embeddings import EmbeddingClient
    from app.ingestion import ExtractedSource
    from app.llm import ChatModelBundle
    from app.persona import PersonaBuilder
    from app.settings import Settings

    accounts, uid = store_with_member()
    embeddings = EmbeddingClient(provider="local", model="local", dimensions=128, api_key=None)
    builder = PersonaBuilder(
        embeddings=embeddings,
        chat=ChatModelBundle(model=None, provider="t", model_name="t"),
        settings=Settings(chunk_characters=400, chunk_overlap_characters=40),
    )
    source = ExtractedSource(
        title="bio.txt", text="Ada builds analytical engines.", kind="upload", detail="x"
    )
    accounts.add_source(
        user_id=uid, title=source.title, kind=source.kind, detail=source.detail,
        text=source.text, chunks=builder.prepare_chunks(source),
    )

    before = [c["text"] for c in accounts.list_chunks(uid, with_embedding=False)]
    accounts.update_profile(
        uid, {"theme": {"accent": "gold", "background": "distributed streaming kubernetes"}}
    )
    after = [c["text"] for c in accounts.list_chunks(uid, with_embedding=False)]

    assert before == after, "theme must not add retrievable text"
    # Even a theme value stuffed with keywords is absent from what gets searched.
    assert not any("kubernetes" in text for text in after)
