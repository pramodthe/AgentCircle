"""Snapshot every collection to local disk, so losing the cluster is not losing the data.

The cluster this runs against was provisioned by someone else and can disappear without
notice. A snapshot turns that from an outage into an errand: create a new cluster, run
`scripts.restore`, recreate the search indexes.

Uses `bson.json_util`, not plain `json`, because the interesting fields are not
JSON-native — `datetime`, and the photo bytes in `media_blobs`, which are BSON `Binary`.
A plain `json.dumps` would either throw or silently mangle them, and a backup that
quietly drops your photos is worse than no backup because you find out later.

    uv run python -m scripts.backup
    uv run python -m scripts.backup --out ../snapshots --label pre-migration
"""

from __future__ import annotations

import argparse
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from bson import json_util
from pymongo import MongoClient

from app.settings import get_settings

DEFAULT_OUT = Path(__file__).resolve().parents[2] / "snapshots"

RESTORE_README = """# AgentCircle snapshot — {name}

Taken from `{host}`, database `{db}`.

This folder is self-contained. You do not need the AgentCircle repo to restore it — only
Python with `pymongo` installed.

## Restore onto any MongoDB cluster

    pip install pymongo
    python restore.py . --target-uri "mongodb+srv://user:pass@your-cluster.mongodb.net/"

It refuses to write into a database that already holds documents unless you pass
`--force`, and it verifies every collection count after writing. Add `--dry-run` to see
what it would do first.

## Then

1. Point the app's `MONGODB_URI` at the new cluster.
2. Rebuild the Atlas search indexes — they are cluster state, not collection data, so
   they never travel with a snapshot:
   `uv run python -m scripts.create_search_indexes --uri "<new-uri>" --wait 300`
3. Start the API and check `/health` reports the same `embeddings.space` as
   `manifest.json` below. A different space means the stored vectors will not match and
   retrieval returns nothing.

## What is in here

`manifest.json` lists every collection and its document count. Each `.json.gz` is one
collection, one JSON document per line, encoded with MongoDB Extended JSON — so
datetimes and binary data (the photos in `media_blobs`) survive the round trip intact.
"""


def safe_host(uri: str) -> str:
    """The cluster hostname with credentials stripped.

    The manifest is a file on disk that outlives the run and may well get copied around;
    it records *which* cluster this came from and never how to open it.
    """
    try:
        netloc = urlsplit(uri).netloc
        return netloc.rsplit("@", 1)[-1] or "unknown"
    except ValueError:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=None, help="defaults to MONGODB_URI")
    parser.add_argument("--db", default=None, help="defaults to MONGODB_DATABASE")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--label", default="", help="suffix for the snapshot directory")
    args = parser.parse_args()

    settings = get_settings()
    uri = args.uri or settings.mongodb_uri
    db_name = args.db or settings.mongodb_database

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"{stamp}-{args.label}" if args.label else stamp
    out_dir = Path(args.out) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    db = MongoClient(uri, serverSelectionTimeoutMS=15000)[db_name]
    collections = sorted(db.list_collection_names())

    manifest: dict = {
        "created_at": datetime.now(UTC).isoformat(),
        "source_host": safe_host(uri),
        "database": db_name,
        # Vectors are only comparable within the space that produced them, so a restore
        # into a differently-configured app is a real hazard. Record it.
        "embedding_space": f"{settings.embedding_provider}:{settings.embedding_model}"
        f":{settings.embedding_dimensions}",
        "collections": {},
    }

    total = 0
    print(f"{db_name} @ {manifest['source_host']} -> {out_dir}")
    for coll in collections:
        rows = list(db[coll].find({}))
        if not rows:
            print(f"  {coll:24} empty, skipped")
            continue
        path = out_dir / f"{coll}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json_util.dumps(row) + "\n")
        manifest["collections"][coll] = len(rows)
        total += len(rows)
        print(f"  {coll:24} {len(rows):>6,} docs  {path.stat().st_size / 1024:>8,.0f} KB")

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Make the folder self-sufficient. A snapshot that can only be restored by someone
    # who still has this repo checked out is not a backup, it is a coupling — and the
    # scenario this exists for is the one where things have already gone wrong.
    restore_src = Path(__file__).with_name("restore.py")
    if restore_src.exists():
        (out_dir / "restore.py").write_text(restore_src.read_text())
    (out_dir / "RESTORE.md").write_text(
        RESTORE_README.format(name=name, host=manifest["source_host"], db=db_name)
    )

    size = sum(f.stat().st_size for f in out_dir.iterdir()) / 1024 / 1024
    print(f"\n{total:,} documents in {len(manifest['collections'])} collections, {size:.1f} MB")
    print(f"snapshot: {out_dir}")
    print(f"\nRestore with:\n  uv run python -m scripts.restore {out_dir} --target-uri <uri>")


if __name__ == "__main__":
    main()
