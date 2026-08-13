"""Profile images are presentation. The tests that matter are the ones about reach.

`media.py` photos are evidence and are consent-gated under spec §9. `profile_media.py`
images are decoration. They share a blob collection and nothing else, and every test
here exists to keep it that way.
"""

from __future__ import annotations

import pytest

from app.accounts import AccountStore, declared_profile_text
from app.media import MediaError
from app.mock_mongo import create_mock_client
from app.profile_media import ProfileMediaStore, public_profile_media

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def store() -> ProfileMediaStore:
    media = ProfileMediaStore(create_mock_client()["profile-media-test"])
    media.ensure_indexes()
    return media


def test_uploading_an_avatar_twice_leaves_one_row_and_one_blob() -> None:
    """Deterministic ids, like src_declared_{user_id} — no orphaned blobs."""
    media = store()
    first = media.set(user_id="ada", kind="avatar", image=PNG, media_type="image/png")
    second = media.set(user_id="ada", kind="avatar", image=PNG + b"x", media_type="image/png")

    assert first["_id"] == second["_id"]
    assert media.db.profile_media.count_documents({"user_id": "ada"}) == 1
    assert media.db.media_blobs.count_documents({"user_id": "ada"}) == 1


def test_avatar_and_cover_are_separate_slots() -> None:
    media = store()
    media.set(user_id="ada", kind="avatar", image=PNG, media_type="image/png")
    media.set(user_id="ada", kind="cover", image=PNG, media_type="image/png")

    rows = media.for_users(["ada"])["ada"]
    assert set(rows) == {"avatar", "cover"}


def test_a_profile_image_is_never_embedded() -> None:
    """The whole reason this is a separate collection from persona_media."""
    media = store()
    row = media.set(user_id="ada", kind="avatar", image=PNG, media_type="image/png")

    stored = media.db.profile_media.find_one({"_id": row["_id"]})
    assert "embedding" not in stored
    assert "space" not in stored
    # And it is not in the collection any search reads.
    assert media.db.persona_media.count_documents({}) == 0


def test_a_profile_image_never_becomes_retrievable_text() -> None:
    """The same guarantee `theme` has: decoration must not buy reach.

    If an image id or its AI flag reached declared_profile_text it would be embedded on
    the next profile save, and uploading a picture would start changing who finds you.
    """
    accounts = AccountStore(create_mock_client()["profile-media-reach"])
    accounts.ensure_indexes()
    user = accounts.create_user(
        email="ada@example.com", password_hash="x", display_name="Ada Lovelace"
    )
    accounts.update_profile(user["_id"], {"headline": "Systems engineer"})

    profile = accounts.get_profile(user["_id"])
    enriched = {
        **profile,
        **public_profile_media({"avatar": {"_id": "pm_avatar_ada", "ai_generated": True}}),
    }
    text = declared_profile_text(enriched).lower()

    assert "pm_avatar_ada" not in text
    assert "ai_generated" not in text
    assert "avatar" not in text


def test_an_unsupported_file_type_is_refused_at_the_door() -> None:
    media = store()
    with pytest.raises(MediaError):
        media.set(user_id="ada", kind="avatar", image=PNG, media_type="application/pdf")


def test_an_unknown_slot_is_refused() -> None:
    """Only two slots. Anything else is a persona photo and belongs under §9."""
    media = store()
    with pytest.raises(MediaError):
        media.set(user_id="ada", kind="banner", image=PNG, media_type="image/png")


def test_an_empty_file_is_refused() -> None:
    media = store()
    with pytest.raises(MediaError):
        media.set(user_id="ada", kind="avatar", image=b"", media_type="image/png")


def test_a_member_cannot_delete_another_members_image() -> None:
    media = store()
    media.set(user_id="ada", kind="avatar", image=PNG, media_type="image/png")

    assert media.delete("mallory", "avatar") is False
    assert media.get("ada", "avatar") is not None


def test_deleting_removes_the_bytes_too() -> None:
    """A blob left behind is a photo a member believes they deleted."""
    media = store()
    media.set(user_id="ada", kind="avatar", image=PNG, media_type="image/png")

    assert media.delete("ada", "avatar") is True
    assert media.db.media_blobs.count_documents({"user_id": "ada"}) == 0


def test_absent_slots_are_explicit_nulls() -> None:
    """A missing key would let a card render the previous row's avatar."""
    public = public_profile_media(None)
    assert public == {
        "avatar_media_id": None,
        "avatar_ai_generated": False,
        "cover_media_id": None,
        "cover_ai_generated": False,
    }


def test_an_ai_generated_image_is_kept_labelled() -> None:
    """Allowed, but never silently — an unlabelled generated portrait presented as a
    photograph is the same fabricated visual claim as the stock photos this replaced."""
    media = store()
    row = media.set(
        user_id="ada", kind="avatar", image=PNG, media_type="image/png", ai_generated=True
    )
    assert row["ai_generated"] is True
    assert public_profile_media(media.for_users(["ada"])["ada"])["avatar_ai_generated"] is True
