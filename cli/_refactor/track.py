"""Orchestration for ``context-kit refactor track``.

Pulls together file scans + plan data into a ``TrackResult`` that
the renderer turns into text or JSON. Pure: no IO outside what the
underlying scan / plan functions do.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from cli._refactor.detectors import get_detector
from cli._refactor.plan_parser import PlanData, parse_plan
from cli._refactor.scan import FileScan, resolve_siblings, scan_file


@dataclass
class TrackResult:
    """Computed snapshot. The single object the renderer consumes."""

    source: FileScan
    siblings: list[FileScan]
    detector_name: str
    plan: PlanData | None
    baseline_count: int
    baseline_source: str  # one of: "flag", "plan", "computed"
    migrated_count: int
    remaining_count: int
    pct_complete: float
    largest_remaining: list[tuple[str, int]] = field(default_factory=list)
    avg_per_pr: int = 0
    estimated_prs_remaining: int | None = None
    warnings: list[str] = field(default_factory=list)


def compute_track(
    source: Path,
    *,
    detector_name: str,
    siblings_pattern: str | None,
    plan_path: Path | None,
    baseline_count: int | None,
    avg_per_pr: int,
    top_n: int,
) -> TrackResult:
    """Run the full algorithm. See README for the priority chain."""
    detector = get_detector(detector_name)

    source_scan = scan_file(source, detector)
    sibling_paths = resolve_siblings(source, siblings_pattern)
    siblings = [scan_file(p, detector) for p in sibling_paths]

    plan: PlanData | None = None
    if plan_path is not None:
        plan = parse_plan(plan_path)

    warnings: list[str] = []

    if not source_scan.exists:
        warnings.append(f"source file does not exist: {source}")
    if source_scan.parse_error:
        warnings.append(f"source parse error: {source_scan.parse_error}")
    for s in siblings:
        if s.parse_error:
            warnings.append(f"{s.path.name}: {s.parse_error}")

    sibling_total = sum(s.item_count for s in siblings)

    # Baseline resolution: explicit flag > plan total > computed.
    # When we have to fall back to computed, warn loudly: the baseline
    # only counts what's currently on disk, so progress will be
    # underreported until the user supplies --baseline-count.
    if baseline_count is not None:
        baseline = baseline_count
        baseline_source = "flag"
    elif plan and plan.total_expected is not None:
        baseline = plan.total_expected
        baseline_source = "plan"
    else:
        baseline = source_scan.item_count + sibling_total
        baseline_source = "computed"
        warnings.append(
            "baseline inferred from current files; progress may be "
            "underreported. Use --baseline-count for accurate "
            "historical progress."
        )

    migrated = max(0, baseline - source_scan.item_count)
    remaining = source_scan.item_count
    pct = (migrated / baseline * 100.0) if baseline > 0 else 0.0

    # Largest remaining domains.
    largest_remaining: list[tuple[str, int]] = []
    if plan and plan.per_destination:
        # Filter out destinations that already have at least their
        # expected count of items present (those are "done"). We treat
        # a destination as remaining-relevant only when its sibling
        # file either doesn't exist yet or has fewer items than the
        # plan expects.
        sibling_counts_by_name = {s.path.name: s.item_count for s in siblings}
        candidates: list[tuple[str, int]] = []
        for dest, expected in plan.per_destination.items():
            present = sibling_counts_by_name.get(dest, 0)
            if present >= expected:
                continue
            candidates.append((dest, expected - present))
        candidates.sort(key=lambda kv: kv[1], reverse=True)
        largest_remaining = candidates[:top_n]
    elif siblings:
        # No plan → fall back to listing siblings by current size as a
        # rough proxy (descending). Caller can ignore this if not useful.
        ordered = sorted(
            ((s.path.name, s.item_count) for s in siblings if s.item_count),
            key=lambda kv: kv[1],
            reverse=True,
        )
        largest_remaining = ordered[:top_n]

    estimated_prs: int | None = None
    if avg_per_pr and avg_per_pr > 0 and remaining > 0:
        estimated_prs = math.ceil(remaining / avg_per_pr)
    elif avg_per_pr and avg_per_pr > 0 and remaining == 0:
        estimated_prs = 0

    return TrackResult(
        source=source_scan,
        siblings=siblings,
        detector_name=detector_name,
        plan=plan,
        baseline_count=baseline,
        baseline_source=baseline_source,
        migrated_count=migrated,
        remaining_count=remaining,
        pct_complete=pct,
        largest_remaining=largest_remaining,
        avg_per_pr=avg_per_pr,
        estimated_prs_remaining=estimated_prs,
        warnings=warnings,
    )
