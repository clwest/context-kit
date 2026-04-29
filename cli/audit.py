"""context-kit `audit` subcommand: print a structured audit prompt.

Prints a predefined prompt that instructs an AI to perform a deep audit
of the current repository — stale docs, duplicated logic, dead code,
risky areas, runtime/doc inconsistencies — with prioritized findings
(P0 / P1 / P2) and a phased cleanup plan.

By default writes only to stdout. With ``--write``, also scaffold two
docs under ``docs/audit/`` (``AUDIT_V1.md`` and ``CLEANUP_PLAN.md``)
without overwriting existing files, then print:

  1. ``skipped`` / ``created`` per file
  2. an "appear unfilled" notice when an existing file still holds
     scaffold placeholder text
  3. a numbered Next steps block telling the user exactly what to do
  4. the audit prompt itself, so the user can copy it without a
     separate invocation
"""

from __future__ import annotations

import argparse
from pathlib import Path


AUDIT_PROMPT = """\
Stop explaining the project.

Before beginning, consider running `context-kit inspect` to build a system map. If inspect output is available, use it to ground your audit in real system structure instead of assumptions.

Act as a senior engineer performing a deep audit of this repository.

Your job is to identify:
- stale or misleading documentation
- duplicated logic or files
- dead code or unused modules
- risky patterns or fragile areas
- inconsistencies between declared state and actual runtime behavior
- system topology and subsystem boundaries (if available)

Be specific. Reference real files. Prioritize findings as P0 / P1 / P2 by impact.

Then propose a concrete cleanup plan with phases.

Report back as if you're updating a small project team. Keep it concise, specific, and action-oriented: what you checked, what you'd change or recommend, what remains open, and what you need from the team next."""


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


# (filename, scaffold content, "still unfilled" marker)
# The marker is a verbatim substring that only appears in the scaffold;
# if it's still in an existing file, the user hasn't filled it in yet.
_SCAFFOLD_FILES: tuple[tuple[str, str, str], ...] = (
    ("AUDIT_V1.md", AUDIT_V1_TEMPLATE, "Paste the output from `context-kit audit` here."),
    ("CLEANUP_PLAN.md", CLEANUP_PLAN_TEMPLATE, "Extract the phased cleanup plan from the audit."),
)


NEXT_STEPS = """\
Next steps:
  1. Run: context-kit audit
  2. Paste the audit output into docs/audit/AUDIT_V1.md
  3. Extract phases into docs/audit/CLEANUP_PLAN.md"""


def run_audit(args: argparse.Namespace) -> int:
    if getattr(args, "write", False):
        return _run_audit_write()
    print(AUDIT_PROMPT)
    return 0


def _run_audit_write() -> int:
    audit_dir = Path.cwd() / "docs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    skipped_unfilled = False
    for filename, content, marker in _SCAFFOLD_FILES:
        path = audit_dir / filename
        rel = path.relative_to(Path.cwd())
        if path.exists():
            print(f"  skipped    {rel} (already exists)")
            if marker in path.read_text(encoding="utf-8"):
                skipped_unfilled = True
            continue
        path.write_text(content, encoding="utf-8")
        print(f"  created    {rel}")

    print()
    if skipped_unfilled:
        print("Audit files exist but appear unfilled.")
        print()

    print(NEXT_STEPS)
    print()
    print("Audit prompt:")
    print()
    print(AUDIT_PROMPT)
    return 0
