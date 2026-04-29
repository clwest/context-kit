"""context-kit ``refactor`` command group.

v1 ships a single subcommand:

    context-kit refactor track SOURCE [--detector ...] [--plan ...] ...

Read-only. Deterministic. AST + filesystem only. Always exits 0
unless the source path is invalid (in which case 2).

Future siblings (deferred): ``refactor extract``, ``refactor verify``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cli._refactor.detectors import DETECTORS
from cli._refactor.plan_parser import autodiscover_plan
from cli._refactor.render import render_json, render_text
from cli._refactor.track import compute_track


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """Register the ``refactor`` group on the top-level parser."""
    refactor = sub.add_parser(
        "refactor",
        help="Read-only helpers for multi-PR module-extraction refactors",
        description=(
            "Tools for tracking and (later) executing module-extraction "
            "refactors — splitting a monolith file into sibling modules "
            "across many PRs. v1 ships only the `track` subcommand."
        ),
    )
    refactor_sub = refactor.add_subparsers(
        dest="refactor_command",
        required=True,
        metavar="SUBCOMMAND",
    )

    # refactor track
    track = refactor_sub.add_parser(
        "track",
        help="Report progress on a multi-PR module-extraction refactor",
        description=(
            "Read SOURCE plus its sibling destination files, and print a "
            "deterministic progress report: total / migrated / remaining "
            "item counts, percentage complete, the largest remaining "
            "domains (when a plan file is provided), and an estimated "
            "PR count. Read-only. AST + filesystem only."
        ),
    )
    track.add_argument(
        "source",
        help="Path to the monolith source file (e.g. core/tasks.py).",
    )
    track.add_argument(
        "--siblings",
        default=None,
        metavar="GLOB",
        help=(
            "Glob for sibling destination files. Default derives from "
            "source: 'tasks.py' → 'tasks_*.py' in the same directory."
        ),
    )
    track.add_argument(
        "--detector",
        default="function",
        choices=sorted(DETECTORS),
        help="What counts as a migratable item (default: function).",
    )
    track.add_argument(
        "--plan",
        default=None,
        metavar="PATH",
        help=(
            "Phase-0-style migration plan markdown file with per-destination "
            "counts. If omitted, context-kit auto-discovers under "
            "docs/refactors/. Pass an empty string to disable autodiscovery."
        ),
    )
    track.add_argument(
        "--baseline-count",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Item count before the refactor started. If omitted, falls back "
            "to the plan's total or to (current source + current siblings)."
        ),
    )
    track.add_argument(
        "--avg-per-pr",
        type=int,
        default=10,
        metavar="N",
        help="Historical avg items moved per PR; used for ETA (default: 10).",
    )
    track.add_argument(
        "--top",
        type=int,
        default=5,
        metavar="N",
        help="Show top N largest remaining domains (default: 5).",
    )
    track.add_argument(
        "--format",
        default="text",
        choices=("text", "json"),
        help="Output format (default: text).",
    )


def run_refactor(args: argparse.Namespace) -> int:
    """Dispatch to the ``track`` subcommand."""
    if args.refactor_command == "track":
        return _run_track(args)
    # argparse already enforces required=True; defensive fallback.
    return 2


def _run_track(args: argparse.Namespace) -> int:
    source = Path(args.source)
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()
    else:
        source = source.resolve()

    if not source.exists():
        # Render a result anyway so JSON consumers see a structured
        # answer instead of a stack trace; text consumers see a clean
        # one-line message.
        pass

    plan_path: Path | None = None
    if args.plan is None:
        plan_path = autodiscover_plan(source)
    elif args.plan == "":
        plan_path = None
    else:
        p = Path(args.plan)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        else:
            p = p.resolve()
        plan_path = p if p.exists() else p  # parse_plan handles missing

    result = compute_track(
        source=source,
        detector_name=args.detector,
        siblings_pattern=args.siblings,
        plan_path=plan_path,
        baseline_count=args.baseline_count,
        avg_per_pr=args.avg_per_pr,
        top_n=args.top,
    )

    if args.format == "json":
        print(render_json(result), end="")
    else:
        print(render_text(result), end="")

    # Source missing is the only "user error" that warrants exit 2;
    # everything else is advisory. This keeps the command pipeable
    # even when a sibling parse fails — the warning shows up in the
    # output, but the report still rendered.
    if not source.exists():
        return 2
    return 0
