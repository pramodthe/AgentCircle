"""Load a snapshot into any cluster. The other half of `scripts.backup`.

Deliberately refuses to write into a database that already holds documents unless told
twice. Restore is the operation you reach for when things have already gone wrong, which
is exactly when an accidental overwrite of the wrong target is most likely.

    uv run python -m scripts.restore ../snapshots/20260812T190000Z --target-uri <uri>
    uv run python -m scripts.restore <dir> --target-uri <uri> --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from bson import json_util
from pymongo import MongoClient

BATCH = 500


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="directory produced by scripts.backup")
    parser.add_argument("--target-uri", required=True)
    parser.add_argument("--target-db", default=None, help="defaults to the snapshot's database")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="replace collections that already hold documents"
    )
    args = parser.parse_args()

    snapshot = Path(args.snapshot)
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.exists():
        print(f"No manifest.json in {snapshot} — is that a snapshot directory?")
        sys.exit(1)
    manifest = json.loads(manifest_path.read_text())

    db_name = args.target_db or manifest["database"]
    client = MongoClient(args.target_uri, serverSelectionTimeoutMS=15000)
    target = client[db_name]

    print(f"snapshot {snapshot.name}")
    print(f"  taken   {manifest['created_at']} from {manifest['source_host']}")
    print(f"  vectors {manifest['embedding_space']}")
    print(f"  into    {db_name}\n")

    expected: dict[str, int] = manifest["collections"]
    occupied = [name for name in expected if target[name].estimated_document_count() > 0]
    if occupied and not args.force and not args.dry_run:
        print(
            f"Target already holds documents in: {', '.join(sorted(occupied))}\n"
            "Re-run with --force to replace them, or restore into an empty database."
        )
        sys.exit(1)

    restored = 0
    for name, count in sorted(expected.items()):
        path = snapshot / f"{name}.json.gz"
        if not path.exists():
            print(f"  {name:24} MISSING from snapshot")
            continue
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows = [json_util.loads(line) for line in handle if line.strip()]
        if args.dry_run:
            print(f"  {name:24} would restore {len(rows):>6,}  (manifest says {count:,})")
            restored += len(rows)
            continue
        target[name].delete_many({})
        for start in range(0, len(rows), BATCH):
            target[name].insert_many(rows[start : start + BATCH])
        restored += len(rows)
        print(f"  {name:24} {len(rows):>6,} docs")

    verb = "would restore" if args.dry_run else "restored"
    print(f"\n{verb} {restored:,} documents")

    if not args.dry_run:
        # Same reasoning as the migration script: confirm what landed rather than trust
        # that the writes did not raise.
        print("\nverifying:")
        bad = []
        for name, count in sorted(expected.items()):
            got = target[name].count_documents({})
            if got != count:
                bad.append((name, count, got))
            print(f"  {name:24} expected {count:>6,}  found {got:>6,}"
                  f"  {'ok' if got == count else 'MISMATCH'}")
        if bad:
            print("\nFAILED:")
            for name, want, got in bad:
                print(f"  {name}: expected {want}, found {got}")
            client.close()
            sys.exit(1)
        print("\nall collections match.")
        print(
            "Next:\n"
            "  1. point MONGODB_URI at this cluster\n"
            "  2. uv run python -m scripts.create_search_indexes --wait 300\n"
            "  3. start the API and check /health reports the embedding space above"
        )
    client.close()


if __name__ == "__main__":
    main()
