"""Copy a database between MongoDB clusters.

Written for moving AgentCircle onto a cluster with free search-index slots: index
quota is per cluster, so a cluster shared with another project can leave no room for
the Atlas Search index the hybrid retrieval needs.

Copies documents only. Regular indexes are recreated by `ensure_indexes()` at app
startup; search indexes must be rebuilt with `scripts.create_search_indexes`, since
they are cluster-scoped and not part of collection data.

    uv run python -m scripts.migrate_cluster --source-uri ... --target-uri ... --dry-run
    uv run python -m scripts.migrate_cluster --source-uri ... --target-uri ...
"""

from __future__ import annotations

import argparse
import sys

from pymongo import MongoClient

BATCH = 500


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-uri", required=True)
    parser.add_argument("--target-uri", required=True)
    parser.add_argument("--source-db", default="context_grove")
    parser.add_argument("--target-db", default=None, help="defaults to --source-db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace collections that already hold documents in the target",
    )
    args = parser.parse_args()

    target_db_name = args.target_db or args.source_db
    source = MongoClient(args.source_uri, serverSelectionTimeoutMS=15000)[args.source_db]
    target_client = MongoClient(args.target_uri, serverSelectionTimeoutMS=15000)
    target = target_client[target_db_name]

    names = sorted(source.list_collection_names())
    print(f"{args.source_db} -> {target_db_name}: {len(names)} collection(s)")

    occupied = [
        name for name in names if target[name].estimated_document_count() > 0
    ]
    if occupied and not args.force and not args.dry_run:
        print(
            f"\nTarget already has documents in: {', '.join(occupied)}\n"
            "Re-run with --force to replace them, or pick an empty target database."
        )
        sys.exit(1)

    copied = 0
    for name in names:
        rows = list(source[name].find({}))
        if not rows:
            print(f"  {name:24} empty, skipped")
            continue
        if args.dry_run:
            print(f"  {name:24} would copy {len(rows)}")
            copied += len(rows)
            continue
        target[name].delete_many({})
        for start in range(0, len(rows), BATCH):
            target[name].insert_many(rows[start : start + BATCH])
        copied += len(rows)
        print(f"  {name:24} {len(rows)} docs")

    verb = "would copy" if args.dry_run else "copied"
    print(f"\n{verb} {copied} documents")

    if not args.dry_run:
        # Count what actually landed rather than trusting the write path. This is a
        # one-shot move of the only copy of the data, and "insert_many did not raise"
        # is a weaker claim than "the target holds what the source holds".
        print("\nverifying:")
        mismatched = []
        for name in names:
            want = source[name].count_documents({})
            got = target[name].count_documents({})
            flag = "ok" if want == got else "MISMATCH"
            if want != got:
                mismatched.append((name, want, got))
            if want or got:
                print(f"  {name:24} source {want:>6,}  target {got:>6,}  {flag}")
        if mismatched:
            print("\nFAILED — do not repoint MONGODB_URI:")
            for name, want, got in mismatched:
                print(f"  {name}: expected {want}, found {got}")
            target_client.close()
            sys.exit(1)
        print("\nall collections match.")
        print(
            "Next: point MONGODB_URI at the target, then\n"
            "  uv run python -m scripts.create_search_indexes --wait 300\n"
            "Keep the source cluster intact until the app has run against the target."
        )
    target_client.close()


if __name__ == "__main__":
    main()
