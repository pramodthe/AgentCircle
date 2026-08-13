
import httpx

from app.community import CommunityStore, normalize_question
from app.embeddings import EmbeddingClient
from app.mock_mongo import create_mock_client
from app.rerank import Reranker
from app.search import PeopleSearch

# --------------------------------------------------------------------- rerank


class _Resp:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.headers: dict = {}

    def json(self) -> dict:
        return {"data": []}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


def test_reranker_without_a_key_is_a_no_op_that_says_so() -> None:
    r = Reranker(api_key=None)
    assert r.available is False
    assert r.describe()["enabled"] is False
    assert r.rank("query", ["a", "b"]) is None


def test_reranker_skips_trivial_candidate_sets() -> None:
    r = Reranker(api_key="fake")
    assert r.rank("query", ["only one"]) is None, "one document cannot be reranked"
    assert r.rank("query", []) is None


def test_a_failed_rerank_disables_itself_rather_than_retrying_every_search(
    monkeypatch,
) -> None:
    """Permanent auth failures latch off; must stay offline (no live Voyage call)."""

    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp(401))
    r = Reranker(api_key="definitely-not-valid", timeout=5.0)
    assert r.available is True
    assert r.rank("query", ["alpha document", "beta document"]) is None
    assert r.available is False, "one permanent failure should stop retrying every search"
    assert r.describe()["degraded"] is True


def test_search_reports_rerank_off_when_it_did_not_run() -> None:
    db = create_mock_client()["phase6-test"]
    db.profiles.insert_many([
        {"_id": "u1", "headline": "streaming engineer", "skills": ["kafka"]},
        {"_id": "u2", "headline": "clinical operations", "skills": ["nursing"]},
    ])
    embeddings = EmbeddingClient(provider="local", model="local", dimensions=128, api_key=None)
    search = PeopleSearch(
        db, embeddings=embeddings, atlas_enabled=False, reranker=Reranker(api_key=None)
    )

    result = search.search(
        query="streaming and kafka pipelines",
        viewer_id="viewer",
        profiles={r["_id"]: r for r in db.profiles.find({})},
        personas={},
    )
    assert result["retrieval"]["rerank"] == "off"


# ----------------------------------------------------------------- gap demand


def test_normalize_question_collapses_near_duplicates() -> None:
    a = normalize_question("What have you shipped?")
    b = normalize_question("what have you SHIPPED")
    c = normalize_question("So, what have you actually shipped?")
    assert a == b == c, "casing, punctuation and filler must not split demand"
    assert a != normalize_question("What are your hobbies?")


def test_gap_demand_ranks_by_how_often_something_is_asked() -> None:
    community = CommunityStore(create_mock_client()["phase6-gaps"])
    community.ensure_indexes()

    for _ in range(3):
        community.record_gap(user_id="u1", question="What have you shipped?", source="interview")
    community.record_gap(user_id="u1", question="what have you shipped", source="community")
    community.record_gap(user_id="u1", question="What are your rates?", source="interview")

    demand = community.gap_demand("u1")
    assert demand[0]["count"] == 4, "the same question asked four ways is one demand of 4"
    assert set(demand[0]["sources"]) == {"interview", "community"}
    assert demand[1]["count"] == 1


def test_resolving_gaps_is_scoped_to_the_owner() -> None:
    community = CommunityStore(create_mock_client()["phase6-resolve"])
    community.ensure_indexes()
    question = "What have you shipped?"
    mine = community.record_gap(user_id="u1", question=question, source="interview")
    theirs = community.record_gap(user_id="u2", question=question, source="interview")

    assert community.resolve_gaps("u1", [mine["_id"], theirs["_id"]]) == 1, (
        "must not clear another member's gaps"
    )
    assert community.gap_demand("u1") == []
    assert len(community.gap_demand("u2")) == 1


def test_resolved_gaps_leave_the_demand_list() -> None:
    community = CommunityStore(create_mock_client()["phase6-resolve-2"])
    community.ensure_indexes()
    rows = [
        community.record_gap(user_id="u1", question=f"Question {i}?", source="community")
        for i in range(3)
    ]
    assert len(community.gap_demand("u1")) == 3
    community.resolve_gaps("u1", [rows[0]["_id"], rows[1]["_id"]])
    assert len(community.gap_demand("u1")) == 1
