"""Deep research, and the gates that keep it from becoming a dossier machine.

Compiling public information about a real person is the most sensitive thing this
product does, so the gates are tested in the order they must fire: consent, then
protected attributes, then budget — each before a single search is issued.

No test reaches the network: `ExaClient` gets no key, and the synthesis path is
exercised with a scripted model.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.llm import ChatModelBundle
from app.research import (
    Brief,
    ExaClient,
    Finding,
    ResearchAgent,
    build_queries,
    corroborate,
    identity_anchors,
    protected_goal_reason,
    strip_contact_details,
)
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


def me(client, auth):
    return client.get("/api/auth/me", headers=auth).json()["user"]["_id"]


# ------------------------------------------------------------------------ consent


def test_research_is_opt_in_and_defaults_off(client) -> None:
    auth = register(client, "kenji@example.com", "Kenji")
    assert client.get("/api/community/settings", headers=auth).json()["research_enabled"] is False


def test_a_member_who_has_not_opted_in_cannot_be_researched(client) -> None:
    """The subject decides, not the asker. Being findable is not being profiled."""
    asker = register(client, "asker@example.com", "Asker")
    subject = register(client, "kenji@example.com", "Kenji")

    response = client.post(
        "/api/research",
        headers=asker,
        json={
            "subject_id": me(client, subject),
            "goal": "what infrastructure work have they shipped",
        },
    )
    assert response.status_code == 403
    assert "has not turned on deep research" in response.json()["detail"]


def test_you_cannot_research_yourself(client) -> None:
    auth = register(client, "solo@example.com", "Solo")
    response = client.post(
        "/api/research",
        headers=auth,
        json={"subject_id": me(client, auth), "goal": "what have I shipped publicly"},
    )
    assert response.status_code == 400


# ------------------------------------------------------- protected attributes


@pytest.mark.parametrize(
    "goal",
    [
        "what is their religion",
        "find out their ethnicity",
        "any criminal record or arrest",
        "what is their salary and compensation",
        "their political party and who they voted for",
        "any medical diagnosis or disability",
    ],
)
def test_protected_attribute_goals_are_refused(goal) -> None:
    assert protected_goal_reason(goal) is not None


@pytest.mark.parametrize(
    "goal",
    [
        "what infrastructure work have they shipped",
        "have they written about streaming systems",
        "what talks have they given on climate tech",
        "are they building anything in developer tools",
    ],
)
def test_professional_goals_run(goal) -> None:
    """Over-refusing would kill the feature the guard is meant to protect."""
    assert protected_goal_reason(goal) is None


def test_a_protected_goal_is_refused_before_any_search(client) -> None:
    asker = register(client, "asker@example.com", "Asker")
    subject = register(client, "kenji@example.com", "Kenji")
    client.patch("/api/community/settings", headers=subject, json={"research_enabled": True})

    response = client.post(
        "/api/research",
        headers=asker,
        json={"subject_id": me(client, subject), "goal": "what is their religion and ethnicity"},
    )
    assert response.status_code == 422
    assert "protected or private" in response.json()["detail"]
    assert client.get("/api/research", headers=asker).json() == [], "nothing may be stored"


# ----------------------------------------------------------------- grounding


class ScriptedStructured:
    def __init__(self, brief):
        self.brief = brief

    def invoke(self, _prompt):
        return self.brief


class ScriptedModel:
    def __init__(self, brief):
        self.brief = brief

    def with_structured_output(self, _schema):
        return ScriptedStructured(self.brief)


SOURCES = [
    {"url": "https://example.com/a", "title": "A", "author": "", "published": None,
     "snippet": "Kenji built the dispatch service."},
    {"url": "https://example.com/b", "title": "B", "author": "", "published": None,
     "snippet": "Talk on backpressure."},
]


def agent_with(brief) -> ResearchAgent:
    return ResearchAgent(
        chat=ChatModelBundle(model=ScriptedModel(brief), provider="t", model_name="t")
    )


def test_a_claim_citing_a_url_that_was_never_returned_is_dropped() -> None:
    """A model will cheerfully cite a URL it invented. That is fabrication, not a weak claim."""
    brief = Brief(
        summary="Builds dispatch systems.",
        findings=[
            Finding(claim="Built the dispatch service.", source_url="https://example.com/a"),
            Finding(claim="Won an award.", source_url="https://invented.example/nope"),
        ],
    )
    result = agent_with(brief).run(name="Kenji", goal="infrastructure work", sources=SOURCES)

    assert result["declined"] is False
    assert [f["source_url"] for f in result["findings"]] == ["https://example.com/a"]
    assert result["dropped_claims"] == 1


def test_a_brief_where_nothing_survives_grounding_becomes_a_decline() -> None:
    brief = Brief(
        summary="Impressive person.",
        findings=[Finding(claim="Did things.", source_url="https://invented.example/x")],
    )
    result = agent_with(brief).run(name="Kenji", goal="infrastructure work", sources=SOURCES)

    assert result["declined"] is True
    assert result["decline_kind"] == "ungrounded"
    assert result["findings"] == []


def test_no_sources_declines_rather_than_speculating() -> None:
    result = agent_with(Brief()).run(name="Nobody", goal="anything", sources=[])
    assert result["declined"] is True
    assert result["decline_kind"] == "no_results"


def test_without_a_model_the_sources_are_kept_but_never_characterised() -> None:
    """A templated summary of someone's public life is exactly the fabrication we refuse."""
    agent = ResearchAgent(chat=ChatModelBundle(model=None, provider="t", model_name="t"))
    result = agent.run(name="Kenji", goal="infrastructure work", sources=SOURCES)

    assert result["declined"] is True
    assert result["decline_kind"] == "no_model"
    assert len(result["sources"]) == 2, "what was found is still reported"
    assert result["summary"] == ""


# ------------------------------------------------------------------ hygiene


def test_contact_details_are_stripped() -> None:
    """Spec §9: agents never share contact details, whatever the source contained."""
    dirty = "Reach Kenji at kenji@example.com or +1 (555) 010-9999 about the project."
    clean = strip_contact_details(dirty)
    assert "kenji@example.com" not in clean
    assert "555" not in clean
    assert "about the project" in clean


def test_queries_are_bounded_and_anchored_on_the_name() -> None:
    """A model that writes its own queries can be talked into researching something else."""
    queries = build_queries(
        name="Kenji Tanaka", headline="Infrastructure engineer", organization="GridPilot",
        goal="what have they shipped",
    )
    assert len(queries) <= 4
    assert all('"Kenji Tanaka"' in q for q in queries)


def test_without_a_key_the_surface_reports_itself_off(client) -> None:
    assert ExaClient(api_key=None).available is False
    assert ExaClient(api_key=None).search("anything") == {"results": [], "cost": 0.0}
    assert client.get("/api/research/status").json()["available"] is False


def test_a_brief_is_private_to_whoever_asked_for_it(client) -> None:
    asker = register(client, "asker@example.com", "Asker")
    other = register(client, "nosy@example.com", "Nosy")
    subject = register(client, "kenji@example.com", "Kenji")
    client.patch("/api/community/settings", headers=subject, json={"research_enabled": True})

    # No Exa key in tests, so the request is refused at the availability gate — which is
    # itself the point: nothing is stored, so there is nothing for anyone else to read.
    response = client.post(
        "/api/research",
        headers=asker,
        json={"subject_id": me(client, subject), "goal": "what have they shipped"},
    )
    assert response.status_code == 503
    assert client.get("/api/research", headers=other).json() == []


# ------------------------------------------------------- identity, not just citations

KENJI_PROFILE = {
    "organization": "GridPilot",
    "location": "Oakland",
    "role": "Infrastructure engineer",
    "headline": "Infrastructure engineer at GridPilot — energy systems",
}

# Verbatim from a live run: a search for a member named "Kenji Tanaka" returned genuine,
# correctly cited sources about a DIFFERENT, real Kenji Tanaka. Every URL was real, so
# every claim passed the citation check.
NAMESAKE_SOURCES = [
    {"url": "https://hc34.hotchips.org/assets/kenji_tanaka.pdf", "title": "VTA-NIC poster",
     "author": "", "published": None,
     "snippet": "Kenji Tanaka, NTT — deep learning inference serving on a NIC."},
    {"url": "https://www.jstage.jst.go.jp/article/pjsai/JSAI2025/x.pdf", "title": "Streaming GPU",
     "author": "", "published": None,
     "snippet": "Kenji Tanaka co-authored an event-driven streaming GPU computing system."},
]
REAL_SOURCE = {
    "url": "https://gridpilot.example/blog/dispatch", "title": "Dispatch at GridPilot",
    "author": "", "published": None,
    "snippet": "Kenji Tanaka on building the real-time dispatch service at GridPilot in Oakland.",
}


def test_anchors_come_only_from_what_the_member_declared() -> None:
    anchors = identity_anchors(profile=KENJI_PROFILE, name="Kenji Tanaka", handle="kenji_tanaka")
    assert "gridpilot" in anchors
    assert "oakland" in anchors
    # Generic job words identify nobody and would confirm any namesake.
    assert "engineer" not in anchors
    assert "systems" not in anchors
    # And nothing derived from the name: a page containing it is why we are here.
    assert "kenji_tanaka" not in anchors
    assert "tanaka" not in anchors


def test_sources_about_a_namesake_are_never_confirmed() -> None:
    """Citation-checking is not identity-checking. This is the gap that produced a
    confident brief about a stranger, with every URL genuine."""
    anchors = identity_anchors(profile=KENJI_PROFILE, name="Kenji Tanaka", handle="kenji_tanaka")
    confirmed, unconfirmed = corroborate([*NAMESAKE_SOURCES, REAL_SOURCE], anchors)

    assert [s["url"] for s in confirmed] == [REAL_SOURCE["url"]]
    assert len(unconfirmed) == 2
    assert "gridpilot" in confirmed[0]["matched_on"]


def test_a_brief_with_only_namesake_sources_declines_rather_than_guessing() -> None:
    anchors = identity_anchors(profile=KENJI_PROFILE, name="Kenji Tanaka", handle="kenji_tanaka")
    confirmed, unconfirmed = corroborate(NAMESAKE_SOURCES, anchors)
    assert confirmed == []

    result = agent_with(Brief()).run(
        name="Kenji Tanaka", goal="infrastructure work",
        sources=confirmed, unconfirmed=unconfirmed,
    )
    assert result["declined"] is True
    assert result["decline_kind"] == "unconfirmed_identity"
    assert result["findings"] == []
    # `sources` means "confirmed to be this member" in every status, so it stays empty.
    assert result["sources"] == []
    assert len(result["unconfirmed_sources"]) == 2, "shown, but never as this member's"


def test_a_member_with_nothing_declared_can_confirm_nothing() -> None:
    """No anchors means no way to tell them from a namesake, so nothing is confirmed."""
    confirmed, unconfirmed = corroborate(NAMESAKE_SOURCES, identity_anchors(profile={}))
    assert confirmed == []
    assert len(unconfirmed) == 2


def test_topic_words_are_not_identity_anchors() -> None:
    """The subtler half of the same bug.

    Narrowing to "does a source mention anything from their profile" was not enough:
    "infrastructure" and "energy" came from the headline and confirmed five papers by
    the *same* wrong Kenji Tanaka, who also works on energy infrastructure. Field
    overlap is the most likely kind of collision, so only entity fields anchor.
    """
    anchors = identity_anchors(
        profile=KENJI_PROFILE, name="Kenji Tanaka", handle="kenji_tanaka"
    )
    assert anchors == {"gridpilot", "oakland"}
    assert "infrastructure" not in anchors
    assert "energy" not in anchors


def test_a_namesake_in_the_same_field_is_still_rejected() -> None:
    same_field = {
        "url": "https://jstage.jst.go.jp/article/x.pdf",
        "title": "Streaming GPU computing",
        "author": "",
        "published": None,
        "snippet": "Kenji Tanaka on energy-efficient infrastructure for AI inference.",
    }
    anchors = identity_anchors(profile=KENJI_PROFILE, name="Kenji Tanaka", handle="kenji_tanaka")
    confirmed, unconfirmed = corroborate([same_field], anchors)

    assert confirmed == [], "shared subject matter is not shared identity"
    assert len(unconfirmed) == 1
