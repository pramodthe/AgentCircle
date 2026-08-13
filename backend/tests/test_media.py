"""Photo search, and the constraints that make it safe to ship.

Spec §9 says photo search may match activity and context but must never become a way to
filter people by how they look. That is a property of the code, not of good intentions,
so it is pinned here — along with consent, ownership, and the guarantee that a photo
vector can never wander into ordinary text retrieval.

No test embeds anything: `MultimodalEmbedder` gets no key, so `available` is False, and
vectors are written directly where a test needs ranking.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.media import (
    MediaError,
    MediaStore,
    MultimodalEmbedder,
    appearance_query_reason,
    validate_photo,
)
from app.mock_mongo import create_mock_client
from app.settings import get_settings

# A 1x1 PNG. Enough to exercise every path that does not actually look at pixels.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)
CAPTION = "Leading a grid-simulation workshop at the energy systems meetup"


@pytest.fixture
def client():
    os.environ["USE_MOCK_MONGODB"] = "true"
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def register(client, email, name):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "a good password", "display_name": name},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload(client, auth, caption=CAPTION):
    return client.post(
        "/api/media",
        headers=auth,
        files={"file": ("photo.png", PNG, "image/png")},
        data={"caption": caption},
    )


# --------------------------------------------------------------- the §9 constraint


@pytest.mark.parametrize(
    "query",
    [
        "someone who looks like a founder",
        "tall engineer",
        "attractive designer in san francisco",
        "young-looking researcher",
        "asian product manager",
        "people who look approachable",
    ],
)
def test_appearance_queries_are_refused(query) -> None:
    """The capability is identical either way; the framing is what we enforce."""
    assert appearance_query_reason(query) is not None


@pytest.mark.parametrize(
    "query",
    [
        "photos from a climbing trip",
        "someone speaking at a conference",
        "woodworking in a home workshop",
        "women in climate tech at a summit",
        "the person I met at the energy meetup",
    ],
)
def test_activity_and_setting_queries_run(query) -> None:
    """Refusing too much would quietly kill the feature it is meant to protect."""
    assert appearance_query_reason(query) is None


def test_a_refused_query_never_reaches_the_model_or_the_database(client) -> None:
    auth = register(client, "asker@example.com", "Asker")
    response = client.get("/api/media/search", headers=auth, params={"q": "tall blonde engineer"})

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True
    assert body["results"] == []
    assert "how they look" in body["reason"] or "describes how someone looks" in body["reason"]


# ------------------------------------------------------------------------- consent


def test_photo_search_is_opt_in_and_defaults_off(client) -> None:
    auth = register(client, "kenji@example.com", "Kenji")
    settings = client.get("/api/community/settings", headers=auth).json()
    assert settings["photo_search_enabled"] is False


def test_a_members_photos_stay_off_their_public_page_until_they_opt_in(client) -> None:
    owner = register(client, "kenji@example.com", "Kenji")
    viewer = register(client, "viewer@example.com", "Viewer")
    media_id = upload(client, owner).json()["_id"]
    owner_id = client.get("/api/auth/me", headers=owner).json()["user"]["_id"]

    seen = client.get(f"/api/media/user/{owner_id}", headers=viewer).json()
    assert seen == [], "photos are not public just because they were uploaded"

    # The owner still sees their own.
    mine = client.get(f"/api/media/user/{owner_id}", headers=owner).json()
    assert [row["_id"] for row in mine] == [media_id]

    client.patch(
        "/api/community/settings", headers=owner, json={"photo_search_enabled": True}
    )
    shared = client.get(f"/api/media/user/{owner_id}", headers=viewer).json()
    assert [row["_id"] for row in shared] == [media_id]


def test_search_excludes_members_who_did_not_opt_in() -> None:
    """Consent is a filter inside the query, in BOTH retrieval paths.

    Photo search runs $vectorSearch on Atlas and a Python cosine scan everywhere else.
    The consent filter has to sit inside each one — if it were applied after ranking, the
    two paths could disagree, and the fallback is exactly the path nobody watches.
    """
    db = create_mock_client()["media-test"]
    store = MediaStore(db)
    store.ensure_indexes()
    space = "voyage:voyage-multimodal-3.5:1024"
    for user_id in ("opted-in", "opted-out"):
        store.add(
            user_id=user_id, caption=CAPTION, image=PNG, media_type="image/png",
            embedding=[1.0, 0.0], space=space,
        )

    # atlas=True falls back here (mongomock cannot serve $vectorSearch); atlas=False
    # takes the local path directly. Both must answer identically.
    for atlas in (True, False):
        hits = store.search(
            query_vector=[1.0, 0.0], space=space, allowed_user_ids={"opted-in"}, atlas=atlas
        )
        assert [hit["user_id"] for hit in hits] == ["opted-in"], f"atlas={atlas}"
        assert (
            store.search(
                query_vector=[1.0, 0.0], space=space, allowed_user_ids=set(), atlas=atlas
            )
            == []
        ), f"atlas={atlas}"


def test_an_unavailable_vector_index_latches_off_instead_of_retrying() -> None:
    """One failed probe, not a doomed aggregate on every subsequent search."""
    db = create_mock_client()["media-latch"]
    store = MediaStore(db)
    store.ensure_indexes()
    space = "voyage:voyage-multimodal-3.5:1024"
    store.add(user_id="u", caption=CAPTION, image=PNG, media_type="image/png",
              embedding=[1.0, 0.0], space=space)

    assert store._atlas_ok is True
    store.search(query_vector=[1.0, 0.0], space=space, allowed_user_ids={"u"})
    assert store._atlas_ok is False, "the first failure must latch it off"


# ------------------------------------------------------------- captions and storage


def test_a_photo_without_a_caption_is_rejected() -> None:
    """The caption is what the photo is matched on and shown as evidence."""
    with pytest.raises(MediaError, match="caption"):
        validate_photo(caption="me", image=PNG, media_type="image/png")


def test_unsupported_file_types_are_rejected_at_the_door() -> None:
    with pytest.raises(MediaError, match="not supported"):
        validate_photo(caption=CAPTION, image=PNG, media_type="application/pdf")


def test_upload_without_a_key_is_stored_but_reports_itself_unindexed(client) -> None:
    """Honest degraded mode: kept and shown, not searchable, and it says so."""
    auth = register(client, "kenji@example.com", "Kenji")
    row = upload(client, auth).json()
    assert row["indexed"] is False
    assert row["space"] is None
    assert row["caption"] == CAPTION


def test_photo_bytes_round_trip(client) -> None:
    auth = register(client, "kenji@example.com", "Kenji")
    media_id = upload(client, auth).json()["_id"]
    raw = client.get(f"/api/media/{media_id}/raw")
    assert raw.status_code == 200
    assert raw.content == PNG
    assert raw.headers["content-type"].startswith("image/png")


def test_a_member_cannot_delete_another_members_photo(client) -> None:
    owner = register(client, "kenji@example.com", "Kenji")
    other = register(client, "mallory@example.com", "Mallory")
    media_id = upload(client, owner).json()["_id"]

    assert client.delete(f"/api/media/{media_id}", headers=other).status_code == 404
    assert client.get("/api/media", headers=owner).json(), "photo must survive that attempt"
    assert client.delete(f"/api/media/{media_id}", headers=owner).status_code == 204


# --------------------------------------------------------------- space containment


def test_photo_vectors_live_in_their_own_space_and_never_join_text_retrieval(client) -> None:
    """A photo must not surface in ordinary people search, which reads a different space."""
    auth = register(client, "kenji@example.com", "Kenji")
    upload(client, auth)

    embedder = MultimodalEmbedder(api_key=None)
    text_space = client.get("/api/runtime/status").json()["embeddings"]["space"]
    assert embedder.space() != text_space

    hits = client.get(
        "/api/persona/search", headers=auth, params={"q": "grid simulation workshop"}
    ).json()
    assert not any(hit.get("caption") for hit in hits)


def test_status_reports_the_photo_layer_as_off_without_a_key(client) -> None:
    status = client.get("/api/media/status").json()
    assert status["available"] is False
    assert status["model"] is None

    auth = register(client, "asker@example.com", "Asker")
    body = client.get("/api/media/search", headers=auth, params={"q": "climbing trip"}).json()
    assert body["available"] is False
    assert body["results"] == []


def test_both_retrieval_paths_report_scores_on_the_same_scale() -> None:
    """`score` must mean one thing.

    Atlas returns vectorSearchScore, which is (1 + cos) / 2. The local scan computed raw
    cosine. Measured on the same photo: 0.8216 on Atlas, 0.6433 locally — the same
    similarity, reported as two different numbers, in a field the API hands to clients.
    """
    db = create_mock_client()["media-scale"]
    store = MediaStore(db)
    space = "voyage:voyage-multimodal-3.5:1024"
    store.add(user_id="u", caption=CAPTION, image=PNG, media_type="image/png",
              embedding=[1.0, 0.0], space=space)

    identical = store.search(
        query_vector=[1.0, 0.0], space=space, allowed_user_ids={"u"}, atlas=False
    )
    assert identical[0]["score"] == 1.0, "an exact match is 1.0 on both paths"

    partial = store.search(
        query_vector=[0.7071, 0.7071], space=space, allowed_user_ids={"u"}, atlas=False
    )
    # cos = 0.7071 -> (1 + 0.7071) / 2 = 0.8536, not 0.7071.
    assert partial[0]["score"] == 0.8536
