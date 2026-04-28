"""context-kit `audit` subcommand: print a structured audit prompt.

Prints a predefined prompt that instructs an AI to perform a deep audit
of the current repository — stale docs, duplicated logic, dead code,
risky areas, runtime/doc inconsistencies — with prioritized findings
(P0 / P1 / P2) and a phased cleanup plan.

By default writes only to stdout. With ``--write``, also scaffolds two
empty docs under ``docs/audit/`` (``AUDIT_V1.md`` and
``CLEANUP_PLAN.md``) for the user to paste audit output and the phased
plan into. Existing files are never overwritten.
"""

from __future__ import annotations

import argparse
from pathlib import Path


AUDIT_PROMPT = """\
Stop explaining the project.

Act as a senior engineer performing a deep audit of this repository.

Your job is to identify:
- stale or misleading documentation
- duplicated logic or files
- dead code or unused modules
- risky patterns or fragile areas
- inconsistencies between declared state and actual runtime behavior

Be specific. Reference real files. Prioritize findings as P0 / P1 / P2 by impact.

Then propose a concrete cleanup plan with phases."""


AUDIT_V1_TEMPLATE = """\
# Audit V1

Paste the output from `context-kit audit` here.

## Metadata
- Date:
- Model:
- Notes:
"""


CLEANUP_PLAN_TEMPLATE = """\
# Cleanup Plan

Extract the phased cleanup plan from the audit.

## Phases
- Phase 1:
- Phase 2:
- Phase 3:
"""


_SCAFFOLD_FILES: tuple[tuple[str, str], ...] = (
    ("AUDIT_V1.md", AUDIT_V1_TEMPLATE),
    ("CLEANUP_PLAN.md", CLEANUP_PLAN_TEMPLATE),
)


def run_audit(args: argparse.Namespace) -> int:
    if getattr(args, "write", False):
        return _run_audit_write()
    print(AUDIT_PROMPT)
    return 0


def _run_audit_write() -> int:
    audit_dir = Path.cwd() / "docs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in _SCAFFOLD_FILES:
        path = audit_dir / filename
        rel = path.relative_to(Path.cwd())
        if path.exists():
            print(f"  skipped    {rel} (already exists)")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"  created    {rel}")
    return 0
