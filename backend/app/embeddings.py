"""Embedding providers.

Vectors from different providers live in different spaces, so a document is only
comparable to another document embedded by the same provider and model. Every stored
vector therefore carries the `space()` string that produced it, and retrieval filters
on it — a provider switch degrades to "no results" rather than to silent nonsense.

The `local` provider is a deterministic hashed bag-of-tokens. It needs no network and
keeps tests and keyless development working, but it is not semantically meaningful:
it matches shared vocabulary, not shared meaning. Configure `voyage` or `openai` for
anything a user will see.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Iterable
from functools import lru_cache
from typing import Literal

import httpx

from app.settings import Settings, get_settings

LOCAL_EMBEDDING_DIMENSIONS = 128

# Free and low tiers meter embeddings per minute, so a bulk re-embed will hit 429.
MAX_RETRIES = 6
RETRY_BASE_SECONDS = 2.0

# Retained for the local provider and for callers that predate multi-provider support.
EMBEDDING_DIMENSIONS = LOCAL_EMBEDDING_DIMENSIONS

PROVIDER_ENDPOINTS = {
    "voyage": "https://api.voyageai.com/v1/embeddings",
    # MongoDB's own front door onto the same Voyage models, billed through an Atlas org
    # rather than a separate Voyage account. Same request and response shape, which is
    # why it needs no code beyond the URL and the key.
    "mongodb": "https://ai.mongodb.com/v1/embeddings",
    "openai": "https://api.openai.com/v1/embeddings",
}

# Providers that are different doors onto the same models, and therefore the same vector
# space. Keeping them one space is what lets you switch billing without re-embedding a
# corpus — see `_space_provider`.
VOYAGE_COMPATIBLE = {"voyage", "mongodb"}

# Both doors serve the same three Voyage APIs — /embeddings, /rerank and
# /multimodalembeddings — verified live against each. Routing them all through one door
# matters for more than tidiness: they share a per-minute quota *per account*, so leaving
# rerank and multimodal on Voyage while embeddings moved to MongoDB meant ordinary search
# traffic was starving the reranker. Measured: six searches in ten seconds was enough.
VOYAGE_BASE_URLS = {
    "voyage": "https://api.voyageai.com/v1",
    "mongodb": "https://ai.mongodb.com/v1",
}


def voyage_route(settings) -> tuple[str, str | None]:
    """Base URL and key for Voyage-family calls, following EMBEDDING_PROVIDER.

    One knob rather than three: pointing the app at MongoDB moves embeddings, reranking
    and photo search together, so quota is spent from one place.
    """
    if settings.embedding_provider == "mongodb" and settings.mongodb_ai_api_key:
        return VOYAGE_BASE_URLS["mongodb"], settings.mongodb_ai_api_key.get_secret_value()
    key = settings.voyage_api_key.get_secret_value() if settings.voyage_api_key else None
    return VOYAGE_BASE_URLS["voyage"], key

TOKEN_ALIASES = {
    "citation": "verification",
    "citations": "verification",
    "evidence": "verification",
    "sourced": "verification",
    "sources": "verification",
    "source": "verification",
    "verified": "verification",
    "verify": "verification",
    "signals": "trend",
    "signal": "trend",
    "scanning": "trend",
    "systems": "architecture",
    "system": "architecture",
}


class EmbeddingError(RuntimeError):
    """Raised when a configured remote provider cannot produce an embedding.

    Deliberately not caught into a local-provider fallback: mixing embedding spaces
    inside one collection corrupts every subsequent similarity comparison.
    """


def embed_text_local(text: str) -> list[float]:
    vector = [0.0] * LOCAL_EMBEDDING_DIMENSIONS
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for raw_token in tokens:
        token = TOKEN_ALIASES.get(raw_token, raw_token)
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % LOCAL_EMBEDDING_DIMENSIONS
        vector[bucket] += 1.0 + min(len(token), 12) / 12.0

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


class EmbeddingClient:
    def __init__(
        self,
        *,
        provider: Literal["voyage", "openai", "local"],
        model: str,
        dimensions: int,
        api_key: str | None,
        timeout: float = 30.0,
    ) -> None:
        # A remote provider without a key is a misconfiguration, not a hard failure:
        # degrade to local so the app still boots, and say so via describe().
        self.configured_provider = provider
        self.provider = provider if (provider == "local" or api_key) else "local"
        self.model = model if self.provider != "local" else "local-hash-v1"
        self.dimensions = (
            dimensions if self.provider != "local" else LOCAL_EMBEDDING_DIMENSIONS
        )
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        """Honour Retry-After when the provider sends it; back off otherwise."""
        header = response.headers.get("retry-after")
        if header:
            try:
                return min(60.0, max(1.0, float(header)))
            except ValueError:
                pass
        return min(60.0, RETRY_BASE_SECONDS * (2**attempt))

    def space(self) -> str:
        """Identity of the vector space. Stored beside every vector."""
        return f"{self._space_provider()}:{self._space_model()}:{self.dimensions}"

    def _space_provider(self) -> str:
        """Which providers count as the *same* space.

        `voyage` and `mongodb` are two doors onto one set of models: MongoDB serves
        Voyage embeddings through `ai.mongodb.com`, so a vector written through either
        is the same vector. Naming the space after the model's origin rather than the
        billing route means switching between them costs nothing — without this, moving
        billing to an Atlas org would strand every stored vector in an orphaned space
        and silently return no results until the whole corpus was re-embedded.
        """
        return "voyage" if self.provider in VOYAGE_COMPATIBLE else self.provider

    def _space_model(self) -> str:
        """Which models count as the *same* space.

        Voyage 4 models are trained to share an embedding space, so a vector written
        by voyage-4 stays comparable to one written by voyage-4-large. Keying the
        space on the series lets you move up or down the series for cost or quality
        without a pointless re-embed of the whole corpus.

        Dimensions stay in the key regardless: a 512-dim embedding is not comparable
        to a 1024-dim one even from the same model.
        """
        if self.provider in VOYAGE_COMPATIBLE and self.model.startswith("voyage-4"):
            return "voyage-4-series"
        return self.model

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "space": self.space(),
            "degraded": self.provider != self.configured_provider,
            "semantic": self.provider != "local",
        }

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        items = [text if text.strip() else " " for text in texts]
        if not items:
            return []
        if self.provider == "local":
            return [embed_text_local(text) for text in items]
        if self.provider in VOYAGE_COMPATIBLE:
            return self._embed_remote(
                items,
                payload={"model": self.model, "input": items, "input_type": "document"},
            )
        return self._embed_remote(
            items,
            payload={"model": self.model, "input": items, "dimensions": self.dimensions},
        )

    def _embed_remote(self, items: list[str], *, payload: dict) -> list[list[float]]:
        url = PROVIDER_ENDPOINTS[self.provider]
        body: dict | None = None
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=self.timeout,
                )
                # Rate limits are expected, not exceptional: embedding providers meter
                # by requests-per-minute, and a bulk re-embed will hit that ceiling on
                # any low tier. Back off rather than abandoning a half-migrated corpus.
                if response.status_code == 429 and attempt < MAX_RETRIES - 1:
                    time.sleep(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                body = response.json()
                break
            except httpx.HTTPError as exc:
                last_error = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # Retry transient failures only; a 401/403/422 will never succeed.
                if attempt < MAX_RETRIES - 1 and (status is None or status >= 500):
                    time.sleep(RETRY_BASE_SECONDS * (2**attempt))
                    continue
                raise EmbeddingError(
                    f"{self.provider} embedding request failed: {exc}"
                ) from exc

        if body is None:
            raise EmbeddingError(
                f"{self.provider} embedding request failed after {MAX_RETRIES} attempts: "
                f"{last_error}"
            )

        rows = sorted(body.get("data", []), key=lambda row: row.get("index", 0))
        vectors = [row["embedding"] for row in rows]
        if len(vectors) != len(items):
            raise EmbeddingError(
                f"{self.provider} returned {len(vectors)} embeddings for {len(items)} inputs"
            )
        return vectors


def build_embedding_client(settings: Settings | None = None) -> EmbeddingClient:
    settings = settings or get_settings()
    keys = {
        "voyage": settings.voyage_api_key,
        "mongodb": settings.mongodb_ai_api_key,
        "openai": settings.openai_api_key,
        "local": None,
    }
    secret = keys.get(settings.embedding_provider)
    return EmbeddingClient(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=secret.get_secret_value() if secret else None,
    )


@lru_cache
def get_embedding_client() -> EmbeddingClient:
    return build_embedding_client()


def embed_text(text: str) -> list[float]:
    """Embed with the process-wide configured client."""
    return get_embedding_client().embed(text)


def embed_texts(texts: Iterable[str]) -> list[list[float]]:
    return get_embedding_client().embed_batch(texts)
