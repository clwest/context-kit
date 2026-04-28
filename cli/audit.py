"""context-kit `audit` subcommand: print a structured audit prompt.

Prints a predefined prompt that instructs an AI to perform a deep audit
of the current repository — stale docs, duplicated logic, dead code,
risky areas, runtime/doc inconsistencies — with prioritized findings
(P0 / P1 / P2) and a phased cleanup plan.

The command writes only to stdout. Pipe or paste the output into your
agent as a kickoff message.
"""

from __future__ import annotations

import argparse


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


def run_audit(args: argparse.Namespace) -> int:
    print(AUDIT_PROMPT)
    return 0
