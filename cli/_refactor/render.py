"""Output formatters for ``context-kit refactor track``.

Two formats in v1: ``text`` (the default human-readable report) and
``json`` (a stable, parseable object). Both are deterministic — given
the same ``TrackResult`` they produce byte-identical output.
"""

from __future__ import annotations

import json
from typing import Any

from cli._refactor.track import TrackResult


def render_text(result: TrackResult) -> str:
    """Render the human-readable report."""
    lines: list[str] = []
    src_name = str(result.source.path)
    lines.append(f"Refactor Progress — {src_name}")
    lines.append("=" * 70)
    lines.append("")

    if not result.source.exists:
        lines.append(f"  source file not found: {src_name}")
        lines.append("")
        if result.warnings:
            _append_warnings(lines, result.warnings)
        return "\n".join(lines) + "\n"

    # Headline numbers.
    lines.append(f"  Detector       {result.detector_name}")
    lines.append(f"  Source         {src_name}     {result.source.item_count} items")
    lines.append(
        f"  Baseline                                   {result.baseline_count} items"
        f"  ({result.baseline_source})"
    )
    pct_str = f"{result.pct_complete:5.1f}%"
    lines.append(
        f"  Migrated                                   {result.migrated_count} items   ({pct_str})"
    )
    remaining_pct = 100.0 - result.pct_complete if result.baseline_count else 0.0
    lines.append(
        f"  Remaining                                  {result.remaining_count} items   ({remaining_pct:5.1f}%)"
    )
    lines.append("")

    # Migrated by destination — every sibling that has items.
    siblings_with_items = [s for s in result.siblings if s.item_count > 0]
    if siblings_with_items:
        lines.append("Items by destination (current state)")
        for s in siblings_with_items:
            lines.append(f"  {s.path.name:40s} {s.item_count:5d}")
        lines.append("")

    # Largest remaining domains.
    if result.largest_remaining:
        header = (
            "Top remaining domains  (from plan)"
            if result.plan and result.plan.per_destination
            else "Largest siblings  (no plan provided)"
        )
        lines.append(header)
        denom = result.remaining_count if result.remaining_count > 0 else 1
        cumulative = 0
        for name, count in result.largest_remaining:
            pct = count / denom * 100.0
            cumulative += count
            lines.append(f"  {name:40s} {count:5d}   ({pct:5.1f}%)")
        if (
            result.plan
            and result.plan.per_destination
            and len(result.largest_remaining) > 1
        ):
            cum_pct = cumulative / denom * 100.0
            lines.append(f"  {'─' * 38}")
            lines.append(
                f"  {'top-' + str(len(result.largest_remaining)) + ' cumulative':40s} "
                f"{cumulative:5d}   ({cum_pct:5.1f}%)"
            )
        lines.append("")

    # Forecast.
    if result.avg_per_pr and result.avg_per_pr > 0:
        lines.append("Forecast")
        lines.append(f"  Avg items per PR (input)               {result.avg_per_pr}")
        if result.estimated_prs_remaining is not None:
            lines.append(
                f"  Estimated PRs remaining                {result.estimated_prs_remaining}"
            )
        lines.append("")

    # Notes.
    notes: list[str] = []
    if result.baseline_source == "flag":
        notes.append(
            f"Baseline of {result.baseline_count} supplied via --baseline-count"
        )
    elif result.baseline_source == "plan":
        notes.append(
            f"Baseline of {result.baseline_count} read from plan: "
            f"{result.plan.path if result.plan else '?'}"
        )
    elif result.baseline_source == "computed":
        notes.append(
            f"Baseline of {result.baseline_count} computed as "
            "(current source + current siblings); pass --baseline-count "
            "for an authoritative starting count"
        )

    if result.plan and result.plan.path:
        notes.append(f"Plan source: {result.plan.path}")

    if notes:
        lines.append("Notes")
        for n in notes:
            lines.append(f"  • {n}")
        lines.append("")

    if result.warnings:
        _append_warnings(lines, result.warnings)

    return "\n".join(lines) + "\n"


def _append_warnings(lines: list[str], warnings: list[str]) -> None:
    lines.append("Warnings")
    for w in warnings:
        lines.append(f"  ! {w}")
    lines.append("")


def render_json(result: TrackResult) -> str:
    """Render a stable JSON object. Sorted keys for determinism."""
    obj: dict[str, Any] = {
        "source": {
            "path": str(result.source.path),
            "exists": result.source.exists,
            "item_count": result.source.item_count,
            "parse_error": result.source.parse_error,
        },
        "detector": result.detector_name,
        "siblings": [
            {
                "path": str(s.path),
                "name": s.path.name,
                "exists": s.exists,
                "item_count": s.item_count,
                "parse_error": s.parse_error,
            }
            for s in result.siblings
        ],
        "plan": (
            {
                "path": str(result.plan.path) if result.plan.path else None,
                "total_expected": result.plan.total_expected,
                "per_destination": dict(result.plan.per_destination),
            }
            if result.plan is not None
            else None
        ),
        "baseline_count": result.baseline_count,
        "baseline_source": result.baseline_source,
        "migrated_count": result.migrated_count,
        "remaining_count": result.remaining_count,
        "pct_complete": round(result.pct_complete, 4),
        "largest_remaining": [
            {"destination": d, "remaining": c}
            for d, c in result.largest_remaining
        ],
        "avg_per_pr": result.avg_per_pr,
        "estimated_prs_remaining": result.estimated_prs_remaining,
        "warnings": list(result.warnings),
    }
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"
