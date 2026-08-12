"""context-kit `fix` subcommand: turn audit output into actionable steps.

Reads ``docs/audit/AUDIT_V1.md`` and ``docs/audit/CLEANUP_PLAN.md`` (the
audit workspace seeded by ``context-kit audit --write``), parses the
phased cleanup plan into phases + steps, and prints a structured
execution plan to stdout.

Read-only by design: never modifies files, never invokes an AI, never
executes any of the steps it prints.

Validation:

- If either file is missing, or either file still carries its scaffold
  placeholder text (i.e. the user hasn't filled it in yet), the command
  exits 1 with a one-line error pointing at the right next move.
- If the plan is filled in but no phases parse out of it, the command
  exits 1 with a hint about the expected shape.

Phase grammar — supports two markdown shapes the user is likely to
write:

1. H1–H6 heading per phase:

       ### Phase 1 — Tell the truth
       - Run: ...
       - Update: ...

2. Top-level bullet per phase, with indented sub-bullets per step:

       - Phase 1 — Tell the truth
         - Run: ...
         - Update: ...

In both shapes, every bullet (regardless of indentation) between two
phase boundaries belongs to the preceding phase.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path


_AUDIT_DIR = Path("docs/audit")
_AUDIT_V1 = "AUDIT_V1.md"
_CLEANUP_PLAN = "CLEANUP_PLAN.md"

# Verbatim substrings from the audit-write scaffold; if either marker is
# still present, the corresponding file hasn't been filled in.
_UNFILLED_MARKERS = {
    _AUDIT_V1: "Paste the output from `context-kit audit` here.",
    _CLEANUP_PLAN: "Extract the phased cleanup plan from the audit.",
}

_NOT_INITIALIZED = (
    "Audit workspace not initialized or not filled. "
    "Run context-kit audit --write and paste audit results first."
)

# A phase line: heading-style ("### Phase 1 — title") or top-level
# bullet ("- Phase 1: title"). Capture the number and the trailing
# title (anything after a separator: `:`, `—`, `–`, or `-`).
_PHASE_HEADING_RE = re.compile(
    r"^\s*#{1,6}\s*Phase\s+(\d+)\b\s*[:\-—–]?\s*(.*?)\s*$",
    re.IGNORECASE,
)
_PHASE_BULLET_RE = re.compile(
    r"^\s*[-*+]\s+Phase\s+(\d+)\b\s*[:\-—–]?\s*(.*?)\s*$",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")


@dataclass
class Phase:
    number: int
    title: str
    steps: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_fix(args: argparse.Namespace) -> int:
    audit_dir = Path.cwd() / _AUDIT_DIR
    v1 = audit_dir / _AUDIT_V1
    plan = audit_dir / _CLEANUP_PLAN

    if not _workspace_ready(v1, plan):
        print(_NOT_INITIALIZED)
        return 1

    phases = _parse_phases(plan.read_text(encoding="utf-8"))
    if not phases:
        print(
            "context-kit: no phases parsed from "
            f"{(_AUDIT_DIR / _CLEANUP_PLAN).as_posix()}. Expected `### Phase N` headings "
            "or `- Phase N` bullets."
        )
        return 1

    if getattr(args, "next_step", False):
        return _print_next(phases)
    if getattr(args, "phase", None) is not None:
        return _print_phase(phases, args.phase)
    return _print_full_plan(phases)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _workspace_ready(v1: Path, plan: Path) -> bool:
    for path, marker_key in ((v1, _AUDIT_V1), (plan, _CLEANUP_PLAN)):
        if not path.is_file():
            return False
        if _UNFILLED_MARKERS[marker_key] in path.read_text(encoding="utf-8"):
            return False
    return True


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_phases(text: str) -> list[Phase]:
    """Walk the plan line-by-line. A phase boundary is any line matching
    the heading regex OR the top-level-bullet regex. Every bullet between
    two boundaries (regardless of indentation) is a step of the preceding
    phase. Bullets before the first phase boundary are ignored."""
    phases: list[Phase] = []
    current: Phase | None = None

    for raw in text.splitlines():
        phase_match = _PHASE_HEADING_RE.match(raw) or _PHASE_BULLET_RE.match(raw)
        if phase_match:
            number = int(phase_match.group(1))
            title = phase_match.group(2).strip()
            current = Phase(number=number, title=title)
            phases.append(current)
            continue

        if current is None:
            continue

        bullet_match = _BULLET_RE.match(raw)
        if bullet_match:
            current.steps.append(bullet_match.group(1))

    return phases


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_phase_block(phase: Phase) -> str:
    header = f"Phase {phase.number}"
    if phase.title:
        header += f" — {phase.title}"
    lines = [header]
    for step in phase.steps:
        lines.append(f"- {step}")
    return "\n".join(lines)


def _print_full_plan(phases: list[Phase]) -> int:
    print("=== CONTEXT-KIT FIX PLAN ===")
    print()
    for i, phase in enumerate(phases):
        print(_render_phase_block(phase))
        if i != len(phases) - 1:
            print()
    return 0


def _print_phase(phases: list[Phase], number: int) -> int:
    for phase in phases:
        if phase.number == number:
            print(_render_phase_block(phase))
            return 0
    available = ", ".join(str(p.number) for p in phases)
    print(f"context-kit: phase {number} not found (available: {available}).")
    return 1


def _print_next(phases: list[Phase]) -> int:
    for phase in phases:
        if phase.steps:
            print(phase.steps[0])
            return 0
    print("context-kit: no steps found in any phase.")
    return 1
