"""Reranker resilience.

The reranker is the difference between match_percent meaning something and
clustering uselessly at 99/98/98, so how it fails matters as much as how it works.
"""

import httpx

from app.rerank import Reranker


class _Resp:
    def __init__(self, status, headers=None, payload=None):
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload or {"data": []}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)


def test_a_rate_limit_does_not_permanently_disable_reranking(monkeypatch) -> None:
    """A 429 is routine, not fatal.

    Embeddings and reranking share one Voyage account and one per-minute quota, so 429s
    happen under normal load. Treating one as permanent silently downgraded every later
    search for the life of the process — observed as match_percent collapsing from a
    meaningful 99/75/75 spread back to a useless 99/98/98 cluster mid-session.
    """
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _Resp(429, headers={"retry-after": "0"})
        return _Resp(200, payload={"data": [
            {"index": 0, "relevance_score": 0.9},
            {"index": 1, "relevance_score": 0.1},
        ]})

    monkeypatch.setattr(httpx, "post", fake_post)
    reranker = Reranker(api_key="k", model="rerank-2.5")

    scores = reranker.rank("q", ["alpha", "beta"])
    assert scores == [0.9, 0.1], "it should retry past the rate limit"
    assert reranker.available is True, "a 429 must never disable reranking"
    assert len(calls) == 2


def test_an_exhausted_transient_failure_skips_one_query_but_stays_enabled(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Resp(503))
    reranker = Reranker(api_key="k")

    assert reranker.rank("q", ["alpha", "beta"]) is None
    assert reranker.available is True, "a bad gateway is the provider's problem, not ours"


def test_a_bad_key_disables_reranking_for_the_process(monkeypatch) -> None:
    """The one case where giving up is right: 401 will fail identically forever."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return _Resp(401)

    monkeypatch.setattr(httpx, "post", fake_post)
    reranker = Reranker(api_key="wrong")

    assert reranker.rank("q", ["alpha", "beta"]) is None
    assert reranker.available is False
    assert reranker.describe()["degraded"] is True
    # And it stops paying a round trip per search to rediscover that.
    assert reranker.rank("q", ["alpha", "beta"]) is None
    assert len(calls) == 1


def test_search_distinguishes_a_disabled_reranker_from_a_skipped_query() -> None:
    """Reporting a rate-limited query as "off" sends you hunting for a broken key."""
    from app.search import PeopleSearch

    search = PeopleSearch.__new__(PeopleSearch)

    search.reranker = None
    assert search._rerank_status(False) == "off"

    disabled = Reranker(api_key=None)
    search.reranker = disabled
    assert search._rerank_status(False) == "off", "no key is a configuration fact"

    live = Reranker(api_key="k", model="rerank-2.5")
    search.reranker = live
    assert search._rerank_status(True) == "rerank-2.5"
    assert search._rerank_status(False) == "skipped", (
        "enabled but did not run for this query — transient, not configuration"
    )
