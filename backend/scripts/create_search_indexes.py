"""Create the Atlas Search and Atlas Vector Search indexes AgentCircle retrieval needs.

Three indexes, each doing a job the others cannot:

  persona_chunks_vector   semantic people search over what members actually wrote
  profiles_text           Atlas Search (Lucene) over declared profile fields, so a
                          query naming a place, a tool, or a job title matches even
                          when it is nowhere near the text semantically
  persona_media_vector    photo search, in its own multimodal embedding space

Discovery fuses the first two — see `app/search.py`. Photo search is deliberately a
separate surface: multimodal vectors are not comparable to text ones, so fusing them
would compare numbers that have no shared meaning.

IMPORTANT: a vector index is built for one embedding dimension. Switching provider
(local hash 128 -> voyage-3 1024) invalidates every stored vector *and* every vector
index. Re-embed, then run this with `--recreate`.

    uv run python -m scripts.create_search_indexes
    uv run python -m scripts.create_search_indexes --recreate
    uv run python -m scripts.create_search_indexes --status
"""

from __future__ import annotations

import argparse
import time

from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from app.embeddings import build_embedding_client
from app.media import MULTIMODAL_DIMENSIONS
from app.settings import get_settings


def vector_index(name: str, dimensions: int, filters: list[str]) -> SearchIndexModel:
    return SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": dimensions,
                    "similarity": "cosine",
                },
                *[{"type": "filter", "path": path} for path in filters],
            ]
        },
        name=name,
        type="vectorSearch",
    )


def profiles_text_index() -> SearchIndexModel:
    """Lucene index over the fields a member declares about themselves.

    `dynamic: false` on purpose — indexing everything would pull in theme settings and
    other presentation state, which must never influence who gets found.
    """
    string_field = {"type": "string", "analyzer": "lucene.standard"}
    return SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "display_name": string_field,
                    "headline": string_field,
                    "bio": string_field,
                    "role": string_field,
                    "organization": string_field,
                    "location": string_field,
                    "availability": string_field,
                    "skills": string_field,
                    "interests": string_field,
                    "looking_for": string_field,
                    "hobbies": string_field,
                    "likes": string_field,
                },
            }
        },
        name="profiles_text",
        type="search",
    )


def definitions(database, dimensions: int):
    """Highest-value first.

    Free and shared Atlas tiers cap the number of search indexes per cluster — some
    allow only one. Creating in priority order means a constrained cluster still gets
    the index the live product depends on, and the rest degrade to local scoring.
    """
    return [
        (
            database.persona_chunks,
            "persona_chunks_vector",
            vector_index(
                "persona_chunks_vector",
                dimensions,
                ["user_id", "source_id", "visibility", "space"],
            ),
        ),
        (database.profiles, "profiles_text", profiles_text_index()),
        (
            # Photo search. Last because it degrades to a local scan gracefully and
            # affects one surface, where the first two carry all of discovery.
            #
            # Its own dimension constant, not `dimensions`: photos are embedded by
            # voyage-multimodal-3.5 at 1024, which is a different space from the text
            # corpus even when the numbers happen to match. Passing the text dimension
            # here would build an index that silently returns nothing the day someone
            # moves text embeddings to 512.
            database.persona_media,
            "persona_media_vector",
            vector_index(
                "persona_media_vector",
                MULTIMODAL_DIMENSIONS,
                ["user_id", "space", "indexed"],
            ),
        ),
        (
            # Edge-scoped agent memory. Last on purpose, and genuinely optional: the
            # first three are exactly the free tier's quota, so this one only lands on a
            # cluster with room. Without it `AgentMemoryStore.recall` scores in Python
            # over one edge's rows — a small set by construction, since the filter is a
            # single relationship rather than the whole corpus.
            #
            # It is a separate collection rather than a `scope` field on persona_chunks
            # so that no existing query can return a memory by forgetting a filter. The
            # isolation boundary is worth an index slot far more than it is worth reusing
            # one.
            database.agent_memory,
            "agent_memory_vector",
            vector_index(
                "agent_memory_vector",
                dimensions,
                ["owner_id", "edge_id", "space"],
            ),
        ),
    ]


def existing(collection, name: str) -> dict | None:
    try:
        for index in collection.list_search_indexes():
            if index.get("name") == name:
                return index
    except Exception:
        return None
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recreate", action="store_true", help="drop and rebuild indexes that already exist"
    )
    parser.add_argument("--status", action="store_true", help="report index state and exit")
    parser.add_argument(
        "--wait", type=int, default=0, help="seconds to wait for indexes to become queryable"
    )
    parser.add_argument(
        "--only",
        action="append",
        help="restrict to named indexes (repeatable); useful on tiers with a low index cap",
    )
    parser.add_argument(
        "--drop", action="append", help="drop a named index and exit (frees a quota slot)"
    )
    parser.add_argument(
        "--uri",
        default=None,
        help="target a cluster other than MONGODB_URI, for building indexes on a new "
        "cluster before pointing the app at it",
    )
    parser.add_argument("--db", default=None, help="defaults to MONGODB_DATABASE")
    args = parser.parse_args()

    settings = get_settings()
    embeddings = build_embedding_client(settings)
    described = embeddings.describe()
    dimensions = embeddings.dimensions

    print(f"Embedding space: {described['space']} ({dimensions} dims)")
    if not described["semantic"]:
        print(
            "  Warning: this is the local hash fallback, not a real embedding model. "
            "Indexes built now will need --recreate after configuring Voyage or OpenAI."
        )

    client = MongoClient(args.uri or settings.mongodb_uri, serverSelectionTimeoutMS=8000)
    database = client[args.db or settings.mongodb_database]

    planned = definitions(database, dimensions)

    if args.drop:
        for collection, name, _ in planned:
            if name in args.drop and existing(collection, name):
                collection.drop_search_index(name)
                print(f"  {collection.name}.{name}: dropped")
        client.close()
        return

    if args.only:
        planned = [entry for entry in planned if entry[1] in args.only]

    blocked: list[str] = []
    for collection, name, model in planned:
        current = existing(collection, name)
        if args.status:
            state = current.get("status") if current else "MISSING"
            print(f"  {collection.name}.{name}: {state}")
            continue
        if current and not args.recreate:
            print(f"  {collection.name}.{name}: already exists ({current.get('status')})")
            continue
        if current and args.recreate:
            collection.drop_search_index(name)
            print(f"  {collection.name}.{name}: dropped")
            # Atlas rejects a create that races the drop.
            time.sleep(5)
        try:
            collection.create_search_indexes(models=[model])
            print(f"  {collection.name}.{name}: creating")
        except Exception as exc:
            message = str(exc)
            if "maximum number of FTS indexes" in message:
                blocked.append(f"{collection.name}.{name}")
                print(f"  {collection.name}.{name}: BLOCKED — cluster index quota reached")
            else:
                print(f"  {collection.name}.{name}: FAILED — {message[:140]}")

    if blocked:
        print(
            "\nThis cluster cannot hold every index. Retrieval for "
            f"{', '.join(blocked)} will fall back to local scoring, which the API "
            "reports at GET /api/discover/status. Free a slot with --drop <name>, "
            "or upgrade the tier."
        )

    # Only wait on what this run actually attempted — reporting on indexes we
    # deliberately skipped would read as a failure.
    watched = [entry for entry in planned if entry[1] not in blocked]
    if args.wait and not args.status and watched:
        deadline = time.time() + args.wait
        print(f"Waiting up to {args.wait}s for indexes to become queryable…")
        states: dict[str, str | None] = {}
        while time.time() < deadline:
            states = {
                f"{collection.name}.{name}": (existing(collection, name) or {}).get("status")
                for collection, name, _ in watched
            }
            if all(state == "READY" for state in states.values()):
                print(f"READY: {', '.join(states)}")
                break
            time.sleep(5)
        else:
            print(f"Still building: {states}")

    client.close()


if __name__ == "__main__":
    main()
