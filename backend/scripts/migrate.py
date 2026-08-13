"""One command to move AgentCircle onto a different MongoDB account.

For the case this project has been living with all along: the cluster belongs to someone
else and could disappear. Everything needed to come back up is already on disk in
`snapshots/`; this drives the whole sequence so nobody has to remember it under pressure.

    uv run python -m scripts.migrate --target-uri "mongodb+srv://user:pass@new.mongodb.net/"

It will, in order:
  1. take a fresh snapshot if the current cluster still answers (skipped if it does not)
  2. restore the newest snapshot into the target, verifying every collection count
  3. build the three Atlas search indexes and wait until they are queryable
  4. print the one line of .env to change (or change it with --write-env)

Each step is the same script you would run by hand, invoked as a subprocess, so this
orchestrator cannot drift from the behaviour those scripts were verified with.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_ROOT = REPO_ROOT / "snapshots"


def run(step: str, args: list[str]) -> bool:
    print(f"\n{'=' * 62}\n{step}\n{'=' * 62}")
    result = subprocess.run([sys.executable, "-m", *args], cwd=Path(__file__).resolve().parents[1])
    return result.returncode == 0


def newest_snapshot() -> Path | None:
    if not SNAPSHOT_ROOT.exists():
        return None
    dirs = [d for d in SNAPSHOT_ROOT.iterdir() if d.is_dir() and (d / "manifest.json").exists()]
    return max(dirs, key=lambda d: d.name) if dirs else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-uri", required=True, help="the new cluster")
    parser.add_argument("--target-db", default=None, help="defaults to the snapshot's database")
    parser.add_argument("--snapshot", default=None, help="defaults to the newest local snapshot")
    parser.add_argument(
        "--skip-backup", action="store_true", help="do not try to snapshot the old cluster first"
    )
    parser.add_argument(
        "--write-env", action="store_true", help="rewrite MONGODB_URI in .env when it succeeds"
    )
    args = parser.parse_args()

    # 1. A fresh snapshot if the old cluster is still reachable. Best effort on purpose:
    #    the whole point of this script is the case where it is already gone.
    if not args.skip_backup:
        backup_ok = run(
            "1/4  Snapshot the current cluster",
            ["scripts.backup", "--label", "premigration"],
        )
        if not backup_ok:
            print("\n  ! could not snapshot the current cluster — it may already be gone.")
            print("    Continuing with the newest snapshot already on disk.")
    else:
        print("1/4  Snapshot skipped (--skip-backup)")

    snapshot = Path(args.snapshot) if args.snapshot else newest_snapshot()
    if snapshot is None:
        print(f"\nNo snapshot found in {SNAPSHOT_ROOT}. Nothing to migrate from.")
        sys.exit(1)
    print(f"\nUsing snapshot: {snapshot}")

    # 2. Restore. This is the step that must not be wrong, and it verifies itself.
    restore = ["scripts.restore", str(snapshot), "--target-uri", args.target_uri]
    if args.target_db:
        restore += ["--target-db", args.target_db]
    if not run("2/4  Restore into the new cluster", restore):
        print("\nRestore failed. The old cluster and your snapshots are untouched.")
        sys.exit(1)

    # 3. Search indexes are cluster-scoped state, not collection data, so they never
    #    travel with a snapshot and always have to be rebuilt.
    if not run(
        "3/4  Build the Atlas search indexes",
        ["scripts.create_search_indexes", "--uri", args.target_uri, "--wait", "300"],
    ):
        print("\n  ! indexes did not all build. The app still runs — retrieval falls back")
        print("    to local scoring and reports which path served each query.")

    print(f"\n{'=' * 62}\n4/4  Point the app at the new cluster\n{'=' * 62}")
    masked = re.sub(r"://([^:]+):[^@]+@", r"://\1:••••@", args.target_uri)
    if args.write_env:
        env_path = REPO_ROOT / ".env"
        text = env_path.read_text()
        text = re.sub(
            r"^MONGODB_URI=.*$",
            f"MONGODB_URI={args.target_uri}",
            text,
            count=1,
            flags=re.M,
        )
        env_path.write_text(text)
        print(f"  .env updated -> {masked}")
    else:
        print(f"  Set this in .env:\n    MONGODB_URI={masked}")
        print("  (re-run with --write-env to have this script do it)")
    print("\n  Then restart the API and check /health reports status ok.")
    print("  Old cluster and snapshots are untouched — nothing here deletes anything.")


if __name__ == "__main__":
    main()
