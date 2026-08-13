"""Cross-encoder reranking over the fused candidate set.

Reciprocal rank fusion deliberately throws away score magnitude — it only asks how
near the top of its own list a candidate appeared. That is the right way to combine
two retrievers whose scores are not comparable, but it has a real cost: a candidate
that is a *dominant* match on one retriever gets no credit for how dominant it was.

Observed in this codebase: a post scored 0.9163 against a query while the next best
chunk scored 0.72, and its author still ranked third, because two other people showed
up in both retrievers at middling positions. Fusion was working as designed and the
answer was still wrong.

A reranker fixes exactly that. It reads the query and the candidate text together
rather than comparing two independently-produced embeddings, so it can tell "this
passage actually answers the question" from "this passage is about the same topic".
It is expensive per document, which is why it runs over the ~20 survivors of retrieval
rather than the corpus.

Without a key this is a no-op that says so, rather than silently changing nothing.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Set from settings at construction: either door serves rerank-2.5.
DEFAULT_RERANK_URL = "https://api.voyageai.com/v1/rerank"
DEFAULT_TOP_K = 20
# Reranking one document is meaningless and still costs a request.
MIN_DOCUMENTS = 2

MAX_RETRIES = 3
RETRY_BASE_SECONDS = 1.5

# Statuses that mean "this will never work": a bad key, a wrong model, a malformed
# request. Only these disable reranking for the process.
#
# The distinction is the whole point. An earlier version treated *any* HTTPError as
# permanent, so a single 429 — which is routine, since embeddings and reranking share
# one account and one per-minute quota — silently downgraded every later search for the
# lifetime of the process. It was observed live: match_percent went from a meaningful
# 99/75/75 spread back to a useless 99/98/98 cluster between two consecutive queries,
# with nothing in the log to say why. Rate limits are expected, not exceptional; the
# embedding client already knew that and this did not.
PERMANENT_STATUSES = {400, 401, 403, 404, 422}


class Reranker:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "rerank-2.5",
        timeout: float = 30.0,
        enabled: bool = True,
        endpoint: str = DEFAULT_RERANK_URL,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.model = model
        self.timeout = timeout
        self.enabled = enabled and bool(api_key)
        self._failed = False

    def describe(self) -> dict:
        return {
            "enabled": self.available,
            "model": self.model if self.available else None,
            "degraded": self._failed,
        }

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        """Honour Retry-After when the provider sends it; back off otherwise."""
        header = response.headers.get("retry-after")
        if header:
            try:
                return min(30.0, max(1.0, float(header)))
            except ValueError:
                pass
        return min(30.0, RETRY_BASE_SECONDS * (2**attempt))

    @property
    def available(self) -> bool:
        return self.enabled and not self._failed

    def rank(
        self, query: str, documents: list[str], *, top_k: int = DEFAULT_TOP_K
    ) -> list[float] | None:
        """Return a relevance score per document, aligned to the input order.

        Returns None when reranking did not run, so the caller can report the real
        retrieval path instead of implying a rerank happened.
        """
        if not self.available or len(documents) < MIN_DOCUMENTS:
            return None
        if not any(doc.strip() for doc in documents):
            return None

        payload = {
            "model": self.model,
            "query": query,
            "documents": [doc[:8000] or " " for doc in documents],
            "top_k": min(top_k, len(documents)),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        body = None
        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.post(
                    self.endpoint, json=payload, headers=headers, timeout=self.timeout
                )
                if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    time.sleep(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                body = response.json()
                break
            except httpx.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in PERMANENT_STATUSES:
                    # A wrong key or model will fail identically forever. Stop paying a
                    # round trip per search to rediscover that, and say so once.
                    logger.warning(
                        "reranking disabled for this process: %s returned %s", self.model, status
                    )
                    self._failed = True
                    return None
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_SECONDS * (2**attempt))
                    continue
                # Transient and still failing: skip this one search, stay enabled.
                logger.warning("reranking skipped for one query: %s", exc)
                return None

        if body is None:
            logger.warning("reranking skipped for one query after %s attempts", MAX_RETRIES)
            return None

        scores = [0.0] * len(documents)
        for row in body.get("data", []):
            index = row.get("index")
            if isinstance(index, int) and 0 <= index < len(documents):
                scores[index] = float(row.get("relevance_score", 0.0))
        return scores


def build_reranker(settings) -> Reranker:
    from app.embeddings import voyage_route

    base, key = voyage_route(settings)
    return Reranker(
        api_key=key,
        model=settings.rerank_model,
        enabled=settings.rerank_enabled,
        endpoint=f"{base}/rerank",
    )
