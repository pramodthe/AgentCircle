from app.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingClient,
    cosine_similarity,
    embed_text,
)


def test_embedding_is_deterministic_and_normalized() -> None:
    first = embed_text("market research and source verification")
    second = embed_text("market research and source verification")
    assert first == second
    assert len(first) == EMBEDDING_DIMENSIONS
    assert round(cosine_similarity(first, first), 8) == 1.0


def test_related_text_is_closer_than_unrelated_text() -> None:
    goal = embed_text("research market signals and verify sources")
    related = embed_text("market research source verification")
    unrelated = embed_text("design animated character illustrations")
    assert cosine_similarity(goal, related) > cosine_similarity(goal, unrelated)


def test_mongodb_and_voyage_share_one_vector_space() -> None:
    """Switching billing to an Atlas org must not strand a single stored vector.

    `ai.mongodb.com` serves the same Voyage models, so the space is named after the
    model's origin rather than the billing route. If these two ever diverge, every
    embedding already in `persona_chunks` silently stops matching and retrieval returns
    nothing — the exact failure the `space` filter exists to make loud.
    """
    voyage = EmbeddingClient(
        provider="voyage", model="voyage-4-large", dimensions=1024, api_key="k"
    )
    mongodb = EmbeddingClient(
        provider="mongodb", model="voyage-4-large", dimensions=1024, api_key="k"
    )

    assert voyage.space() == mongodb.space()
    assert mongodb.space() == "voyage:voyage-4-series:1024"
    # describe() still reports the truth about which door served the request.
    assert mongodb.describe()["provider"] == "mongodb"
    assert mongodb.describe()["semantic"] is True


def test_the_mongodb_provider_uses_the_atlas_endpoint() -> None:
    from app.embeddings import PROVIDER_ENDPOINTS

    assert PROVIDER_ENDPOINTS["mongodb"] == "https://ai.mongodb.com/v1/embeddings"


def test_a_keyless_mongodb_provider_degrades_to_local_and_says_so() -> None:
    client = EmbeddingClient(
        provider="mongodb", model="voyage-4-large", dimensions=1024, api_key=None
    )
    assert client.provider == "local"
    assert client.describe()["degraded"] is True
    assert client.describe()["semantic"] is False
