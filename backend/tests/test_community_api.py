"""Route-level tests for the community flow, with a scripted model.

The commenter is swapped for a fake so the answered path is exercised without a
network call. Everything else — auth, consent filtering, recruitment ranking,
persistence — is the real code.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.community import safe_community_settings
from app.community_agent import CommentDraft
from app.settings import get_settings

RESUMES = {
    "kenji": (
        "Kenji Tanaka builds distributed streaming infrastructure and real-time dispatch "
        "systems.\n\nOwns the exactly-once delivery path handling 400k events per minute "
        "and wrote the backpressure and replay logic the on-call rotation depends on."
    ),
    "elena": (
        "Elena Rossi runs clinical operations for outpatient clinics.\n\nFifteen years in "
        "healthcare operations; reviews discharge workflows and care coordination."
    ),
}


class ScriptedStructured:
    def __init__(self, draft):
        self.draft = draft

    def invoke(self, _messages):
        return self.draft


class ScriptedModel:
    def __init__(self, draft):
        self.draft = draft

    def with_structured_output(self, _schema):
        return ScriptedStructured(self.draft)


@pytest.fixture
def client():
    os.environ["USE_MOCK_MONGODB"] = "true"
    # JWT_SECRET comes from conftest — the startup guard rejects short secrets.
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


def onboard(client, auth, key):
    client.post(
        "/api/persona/sources/upload",
        headers=auth,
        files={"file": (f"{key}.txt", RESUMES[key].encode(), "text/plain")},
    )
    client.post("/api/persona/build", headers=auth)


def test_recruitment_produces_a_cited_comment_and_respects_consent(client) -> None:
    author_auth = register(client, "author@example.com", "Ada Author")
    kenji_auth = register(client, "kenji@example.com", "Kenji Tanaka")
    elena_auth = register(client, "elena@example.com", "Elena Rossi")
    onboard(client, kenji_auth, "kenji")
    onboard(client, elena_auth, "elena")

    # Kenji opts in and publishes immediately; Elena stays opted out.
    client.patch(
        "/api/community/settings",
        headers=kenji_auth,
        json={"comment_enabled": True, "review_before_publish": False},
    )

    post = client.post(
        "/api/community/posts",
        headers=author_auth,
        json={
            "title": "How should we handle backpressure in a real-time pipeline?",
            "body": (
                "Moving from nightly batch to streaming. Worried about what happens when "
                "the consumer falls behind, and about keeping exactly-once guarantees."
            ),
        },
    ).json()

    client.app.state.community_commenter.chat = type(
        client.app.state.community_commenter.chat
    )(
        model=ScriptedModel(
            CommentDraft(
                declined=False,
                body="Kenji has run exactly-once delivery at 400k events per minute.",
                chunk_indexes=[0],
                offer="a walkthrough of the replay logic",
            )
        ),
        provider="test",
        model_name="scripted",
    )

    result = client.post(
        f"/api/community/posts/{post['_id']}/recruit", headers=author_auth
    ).json()
    assert result["commented"] == 1
    assert result["declined"] == 0

    thread = client.get(f"/api/community/posts/{post['_id']}", headers=author_auth).json()
    comments = thread["comments"]
    assert len(comments) == 1

    comment = comments[0]
    assert comment["declined"] is False
    assert comment["published"] is True
    assert comment["citations"], "an answered comment must carry citations"
    assert comment["citations"][0]["source_title"] == "kenji.txt"
    assert comment["responder"]["display_name"] == "Kenji Tanaka"
    assert "Could help with" in comment["body"]

    # Elena never opted in, so her agent was never invoked.
    assert all(row["responder"]["display_name"] != "Elena Rossi" for row in comments)


def test_review_mode_keeps_a_comment_unpublished_until_released(client) -> None:
    author_auth = register(client, "author@example.com", "Ada Author")
    kenji_auth = register(client, "kenji@example.com", "Kenji Tanaka")
    onboard(client, kenji_auth, "kenji")
    client.patch(
        "/api/community/settings",
        headers=kenji_auth,
        json={"comment_enabled": True, "review_before_publish": True},
    )

    post = client.post(
        "/api/community/posts",
        headers=author_auth,
        json={
            "title": "How should we handle backpressure in a real-time pipeline?",
            "body": "Moving from batch to streaming and worried about consumer lag.",
        },
    ).json()

    client.app.state.community_commenter.chat = type(
        client.app.state.community_commenter.chat
    )(
        model=ScriptedModel(
            CommentDraft(declined=False, body="A grounded answer.", chunk_indexes=[0])
        ),
        provider="test",
        model_name="scripted",
    )
    client.post(f"/api/community/posts/{post['_id']}/recruit", headers=author_auth)

    pending = client.get("/api/community/pending", headers=kenji_auth).json()
    assert len(pending) == 1
    assert pending[0]["published"] is False

    released = client.post(
        f"/api/community/comments/{pending[0]['_id']}/publish", headers=kenji_auth
    )
    assert released.status_code == 200
    assert released.json()["published"] is True
    assert client.get("/api/community/pending", headers=kenji_auth).json() == []


def test_community_endpoints_require_authentication(client) -> None:
    assert client.get("/api/community/posts").status_code == 401
    assert client.get("/api/community/settings").status_code == 401
    created = client.post(
        "/api/community/posts", json={"title": "x" * 10, "body": "y" * 30}
    )
    assert created.status_code == 401


def test_a_patch_never_resets_settings_it_did_not_mention(client) -> None:
    """Found in an E2E run: turning on research silently switched photo sharing off.

    `safe_community_settings` rebuilds every key from defaults — correct for sanitising,
    wrong for a partial update. The worst case was `discoverable`, which defaults True:
    a member who had opted out of search was silently opted back in the moment they
    changed any other setting.
    """
    auth = register(client, "kenji@example.com", "Kenji")

    client.patch(
        "/api/community/settings",
        headers=auth,
        json={"photo_search_enabled": True, "discoverable": False, "comment_enabled": True},
    )
    after = client.patch(
        "/api/community/settings", headers=auth, json={"research_enabled": True}
    ).json()

    assert after["research_enabled"] is True
    assert after["photo_search_enabled"] is True, "an unmentioned consent must survive"
    assert after["comment_enabled"] is True
    assert after["discoverable"] is False, "opting out of search must not silently undo"

    # And it is what a fresh read returns, not just the response body.
    assert client.get("/api/community/settings", headers=auth).json() == after


def test_a_patch_never_resets_interview_settings_it_did_not_mention(client) -> None:
    auth = register(client, "kenji@example.com", "Kenji")
    client.patch(
        "/api/interviews/settings",
        headers=auth,
        json={"interview_enabled": True, "disclose_personal": True},
    )
    after = client.patch(
        "/api/interviews/settings", headers=auth, json={"interview_topics": ["hiring"]}
    ).json()

    assert after["interview_topics"] == ["hiring"]
    assert after["interview_enabled"] is True
    assert after["disclose_personal"] is True


def test_an_unset_setting_never_opts_a_member_out_of_search() -> None:
    """`None` means never configured. Coercing it with bool() inverts opt-out fields.

    Several seeded accounts store `discoverable: None`. They are findable, because
    `undiscoverable_ids()` matches only an explicit False — but the settings PATCH
    rebuilt every key through `bool()`, so saving an unrelated toggle would have
    silently removed them from search.
    """
    from app.routers.community import _current_settings

    class Stub:
        @staticmethod
        def get_member_settings(_user_id):
            return {"discoverable": None, "photo_search_enabled": None, "comment_enabled": True}

    current = _current_settings(Stub(), "ada")
    assert current["discoverable"] is True, "unset must fall back to the opt-out default"
    assert current["photo_search_enabled"] is False, "unset opt-in stays off"
    assert current["comment_enabled"] is True, "a real stored value still wins"

    # And the full round trip a PATCH performs must preserve it.
    merged = {**current, "research_enabled": True}
    assert safe_community_settings(merged)["discoverable"] is True


def test_an_explicit_opt_out_still_survives_an_unrelated_save() -> None:
    from app.routers.community import _current_settings

    class Stub:
        @staticmethod
        def get_member_settings(_user_id):
            return {"discoverable": False}

    merged = {**_current_settings(Stub(), "ada"), "research_enabled": True}
    assert safe_community_settings(merged)["discoverable"] is False
