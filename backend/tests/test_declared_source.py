"""What a member types about themselves has to be findable, and only that.

The profile editor tells members these fields are what their agent can be found for.
These tests hold that promise to the wall from both sides: the declared fields must reach
retrieval, and the theme fields sitting right next to them must not.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.accounts import declared_profile_text
from app.settings import get_settings


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


PROFILE = {
    "headline": "Infrastructure engineer working on grid balancing",
    "role": "Infrastructure engineer",
    "organization": "GridPilot",
    "location": "Oakland",
    "skills": ["distributed systems", "real-time dispatch"],
    "looking_for": ["senior backend engineers"],
    "hobbies": ["cycling"],
}


def test_saving_a_profile_makes_its_claims_retrievable(client) -> None:
    auth = register(client, "kenji@example.com", "Kenji Tanaka")

    response = client.patch("/api/profile", headers=auth, json=PROFILE)
    assert response.status_code == 200, response.text
    assert response.json()["retrieval_synced"] is True

    hits = client.get(
        "/api/persona/search", headers=auth, params={"q": "real-time dispatch"}
    ).json()
    assert hits, "a member who says what they do must be findable for it"
    assert any("real-time dispatch" in hit["text"] for hit in hits)


def test_editing_a_profile_replaces_rather_than_accumulates(client) -> None:
    """Twelve saves must leave one source, and the stale claims must be gone."""
    auth = register(client, "kenji@example.com", "Kenji Tanaka")
    client.patch("/api/profile", headers=auth, json=PROFILE)
    client.patch("/api/profile", headers=auth, json={**PROFILE, "skills": ["ceramics"]})
    client.patch("/api/profile", headers=auth, json={**PROFILE, "skills": ["beekeeping"]})

    sources = client.get("/api/persona/sources", headers=auth).json()
    declared = [source for source in sources if source["kind"] == "declared"]
    assert len(declared) == 1, "each save must replace the last, not stack up"

    hits = client.get("/api/persona/search", headers=auth, params={"q": "ceramics"}).json()
    assert not any("ceramics" in hit["text"] for hit in hits), "removed claims must not linger"


def test_theme_edits_never_become_retrievable(client) -> None:
    """The field next door is presentation. It must not buy reach."""
    auth = register(client, "kenji@example.com", "Kenji Tanaka")
    client.patch("/api/profile", headers=auth, json=PROFILE)

    client.patch(
        "/api/profile",
        headers=auth,
        json={"theme": {"accent": "gold", "background": "kubernetes machine learning"}},
    )
    hits = client.get(
        "/api/persona/search", headers=auth, params={"q": "kubernetes machine learning"}
    ).json()
    assert not any("kubernetes" in hit["text"] for hit in hits)


def test_a_nearly_empty_profile_gets_no_chunk(client) -> None:
    auth = register(client, "new@example.com", "New Member")
    response = client.patch("/api/profile", headers=auth, json={"skills": ["python"]})
    assert response.status_code == 200

    sources = client.get("/api/persona/sources", headers=auth).json()
    assert not [s for s in sources if s["kind"] == "declared"], (
        "a two-word profile should not add noise to everyone else's searches"
    )


def test_declared_text_reads_as_prose_and_omits_theme() -> None:
    text = declared_profile_text(
        {**PROFILE, "display_name": "Kenji Tanaka", "theme": {"accent": "gold"}}
    )
    assert "Kenji Tanaka is an Infrastructure engineer at GridPilot." in text
    assert "Based in Oakland." in text
    assert "Skills: distributed systems, real-time dispatch." in text
    assert "gold" not in text
