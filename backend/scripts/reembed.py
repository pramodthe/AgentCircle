"""Re-embed every stored vector into the currently configured embedding space.

Required whenever the embedding provider or model changes. Vectors from different
providers are not comparable, and retrieval filters on `space`, so without this a
provider switch silently returns nothing rather than returning nonsense — safe, but
also completely broken until you run this.

Order matters:

    1. set EMBEDDING_PROVIDER / VOYAGE_API_KEY in .env
    2. uv run python -m scripts.reembed
    3. uv run python -m scripts.create_search_indexes --recreate --wait 300
    4. set ENABLE_ATLAS_VECTOR_SEARCH=true

Doing (3) before (2) builds an index at the new dimension over old vectors, which
Atlas rejects. Doing (4) first just means the app falls back until the index is ready.

    uv run python -m scripts.reembed --dry-run
"""

from __future__ import annotations

import argparse

from pymongo import MongoClient

from app.embeddings import build_embedding_client
from app.settings import get_settings

BATCH = 64


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report work without writing")
    parser.add_argument(
        "--batch", type=int, default=BATCH, help="texts per embedding request"
    )
    args = parser.parse_args()

    settings = get_settings()
    embeddings = build_embedding_client(settings)
    described = embeddings.describe()
    target_space = embeddings.space()

    print(f"Target space: {target_space} ({embeddings.dimensions} dims)")
    if described["degraded"]:
        print(
            f"  Warning: EMBEDDING_PROVIDER={settings.embedding_provider} is configured but "
            "no API key was found, so this fell back to the local hash provider. "
            "Set the key before re-embedding, or you will just rewrite the fallback vectors."
        )
    if not described["semantic"]:
        print("  Note: local hash provider — not semantically meaningful.")

    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    database = client[settings.mongodb_database]

    stale = database.persona_chunks.count_documents({"space": {"$ne": target_space}})
    current = database.persona_chunks.count_documents({"space": target_space})
    print(f"persona_chunks: {stale} to re-embed, {current} already current")

    if args.dry_run:
        spaces = database.persona_chunks.distinct("space")
        print(f"  spaces present: {spaces}")
        client.close()
        return

    rewritten = 0
    while True:
        batch = list(
            database.persona_chunks.find({"space": {"$ne": target_space}}).limit(args.batch)
        )
        if not batch:
            break
        vectors = embeddings.embed_batch([row["text"] for row in batch])
        for row, vector in zip(batch, vectors, strict=True):
            database.persona_chunks.update_one(
                {"_id": row["_id"]},
                {"$set": {"embedding": vector, "space": target_space}},
            )
        rewritten += len(batch)
        print(f"  {rewritten}/{stale}", end="\r", flush=True)

    print(f"persona_chunks: re-embedded {rewritten}                    ")

    # Legacy demo-domain vectors. Kept in sync so the old workflow does not break,
    # though it runs on local cosine unless ENABLE_ATLAS_VECTOR_SEARCH is set.
    # Batched: one request per document would exhaust a per-minute rate limit long
    # before the corpus was finished.
    memories = list(database.memories.find({}))
    if memories:
        vectors = embeddings.embed_batch([row.get("content", "") for row in memories])
        for row, vector in zip(memories, vectors, strict=True):
            database.memories.update_one(
                {"_id": row["_id"]}, {"$set": {"embedding": vector, "space": target_space}}
            )
            database.context_vectors.update_one(
                {"kind": "memory", "entity_id": row["_id"]},
                {"$set": {"embedding": vector, "space": target_space}},
            )

    agents = list(database.agents.find({}))
    if agents:
        texts = [
            " ".join(
                [row.get("role", ""), row.get("bio", "")]
                + [item["name"] for item in row.get("capabilities", [])]
            )
            for row in agents
        ]
        vectors = embeddings.embed_batch(texts)
        for row, vector in zip(agents, vectors, strict=True):
            database.agents.update_one(
                {"_id": row["_id"]}, {"$set": {"capability_embedding": vector}}
            )
            database.context_vectors.update_one(
                {"kind": "agent", "entity_id": row["_id"]},
                {"$set": {"embedding": vector, "space": target_space}},
            )
    print(f"legacy vectors: re-embedded {len(memories)} memories, {len(agents)} agents")

    print("\nNext: uv run python -m scripts.create_search_indexes --recreate --wait 300")
    client.close()


if __name__ == "__main__":
    main()
