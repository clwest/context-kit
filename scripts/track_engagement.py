#!/usr/bin/env python3
"""Snapshot PyPI + GitHub engagement metrics to metrics/engagement.csv.

GitHub's traffic API only retains 14 days of data, so we must snapshot
ourselves to build a history. PyPI's BigQuery-backed stats keep longer
but we capture them alongside for a single timeline.

Run manually:
    python3 scripts/track_engagement.py

Or schedule daily (macOS launchd / cron / GitHub Actions).

Requires:
    - `gh` CLI authenticated with `repo` scope (for traffic endpoints)
    - Python 3.8+ (stdlib only)
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PYPI_PACKAGE = "contextkit-ai"
GH_REPO = "clwest/context-kit"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "metrics" / "engagement.csv"

FIELDS = [
    "snapshot_at",
    "pypi_last_day",
    "pypi_last_week",
    "pypi_last_month",
    "gh_views_14d",
    "gh_unique_visitors_14d",
    "gh_clones_14d",
    "gh_unique_cloners_14d",
    "gh_stars",
    "gh_forks",
    "gh_watchers",
    "gh_open_issues",
    "top_referrer",
]


def fetch_pypi() -> dict:
    url = f"https://pypistats.org/api/packages/{PYPI_PACKAGE}/recent"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.load(r)["data"]
    return {
        "pypi_last_day": data.get("last_day", 0),
        "pypi_last_week": data.get("last_week", 0),
        "pypi_last_month": data.get("last_month", 0),
    }


def gh_api(path: str):
    out = subprocess.run(
        ["gh", "api", path],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def fetch_github() -> dict:
    views: dict = gh_api(f"repos/{GH_REPO}/traffic/views")
    clones: dict = gh_api(f"repos/{GH_REPO}/traffic/clones")
    refs: list = gh_api(f"repos/{GH_REPO}/traffic/popular/referrers")
    repo: dict = gh_api(f"repos/{GH_REPO}")
    top = refs[0]["referrer"] if refs else ""
    return {
        "gh_views_14d": views.get("count", 0),
        "gh_unique_visitors_14d": views.get("uniques", 0),
        "gh_clones_14d": clones.get("count", 0),
        "gh_unique_cloners_14d": clones.get("uniques", 0),
        "gh_stars": repo.get("stargazers_count", 0),
        "gh_forks": repo.get("forks_count", 0),
        "gh_watchers": repo.get("subscribers_count", 0),
        "gh_open_issues": repo.get("open_issues_count", 0),
        "top_referrer": top,
    }


NUMERIC_FIELDS = [f for f in FIELDS if f not in ("snapshot_at", "top_referrer")]


def last_row() -> dict | None:
    if not OUT.exists():
        return None
    with OUT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows[-1] if rows else None


def render_diff(prev: dict | None, curr: dict) -> str:
    if not prev:
        return "(no previous snapshot — this is your baseline)"
    lines = [f"vs last snapshot at {prev.get('snapshot_at', '?')}:"]
    changed = False
    for k in NUMERIC_FIELDS:
        try:
            old = int(prev.get(k, 0) or 0)
            new = int(curr.get(k, 0) or 0)
        except ValueError:
            continue
        delta = new - old
        if delta == 0:
            continue
        changed = True
        sign = "+" if delta > 0 else ""
        lines.append(f"  {k}: {old} -> {new} ({sign}{delta})")
    old_ref = prev.get("top_referrer", "")
    new_ref = curr.get("top_referrer", "")
    if old_ref != new_ref:
        changed = True
        lines.append(f"  top_referrer: {old_ref!r} -> {new_ref!r}")
    if not changed:
        lines.append("  (no change)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--diff", action="store_true",
                    help="Show change vs the previous snapshot")
    ap.add_argument("--no-write", action="store_true",
                    help="Fetch and print but do not append a row")
    args = ap.parse_args()

    prev = last_row() if args.diff else None

    row = {"snapshot_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        row.update(fetch_pypi())
    except Exception as e:
        print(f"pypi fetch failed: {e}", file=sys.stderr)
    try:
        row.update(fetch_github())
    except Exception as e:
        print(f"github fetch failed: {e}", file=sys.stderr)

    if not args.no_write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        new_file = not OUT.exists()
        with OUT.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new_file:
                w.writeheader()
            w.writerow(row)
        print(f"wrote snapshot to {OUT.relative_to(ROOT)}")
    else:
        print("(--no-write set; not appending)")

    for k in FIELDS:
        if k in row:
            print(f"  {k}: {row[k]}")

    if args.diff:
        print()
        print(render_diff(prev, row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
