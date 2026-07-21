"""Fetch upstream CSVs and store them as immutable, dated snapshots.

Snapshot layout:

    data/snapshots/<YYYY-MM-DD>/<source>.csv
    data/snapshots/<YYYY-MM-DD>/manifest.json

The manifest records url, retrieved_at, sha256, and byte size for every file,
so any downstream number can be traced back to the exact bytes it came from.
Snapshots are never overwritten: re-running on the same day is a no-op unless
--force is passed.
"""

import hashlib
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

from .sources import SAVANT_SOURCES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"

USER_AGENT = "defensive-ten/0.1 (personal research project)"


def _get(url: str, retries: int = 3) -> bytes:
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001 - retry any transport error
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def snapshot_today(force: bool = False) -> Path:
    """Fetch all Savant sources into today's snapshot directory."""
    today = date.today().isoformat()
    snap = SNAPSHOT_DIR / today
    manifest_path = snap / "manifest.json"
    if manifest_path.exists() and not force:
        print(f"snapshot {today} already exists, skipping (use --force to refetch)")
        return snap

    snap.mkdir(parents=True, exist_ok=True)
    manifest = {"snapshot_date": today, "files": {}}
    for name, (url, desc) in SAVANT_SOURCES.items():
        body = _get(url)
        if body.lstrip()[:9].lower() == b"<!doctype":
            raise RuntimeError(f"{name}: got HTML instead of CSV — endpoint drifted: {url}")
        out = snap / f"{name}.csv"
        out.write_bytes(body)
        manifest["files"][name] = {
            "url": url,
            "description": desc,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
        }
        print(f"  {name}: {len(body):,} bytes")
        time.sleep(1)  # be polite to Savant
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"snapshot written: {snap}")
    return snap


def list_snapshots() -> list[str]:
    if not SNAPSHOT_DIR.exists():
        return []
    return sorted(p.name for p in SNAPSHOT_DIR.iterdir() if (p / "manifest.json").exists())


def find_snapshot_near(target: date, tolerance_days: int = 2) -> str | None:
    """Closest snapshot date within +/- tolerance of target, else None."""
    best, best_gap = None, None
    for name in list_snapshots():
        d = date.fromisoformat(name)
        gap = abs((d - target).days)
        if gap <= tolerance_days and (best_gap is None or gap < best_gap):
            best, best_gap = name, gap
    return best


if __name__ == "__main__":
    snapshot_today(force="--force" in sys.argv)
