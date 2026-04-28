"""Tests for the context-kit `exec` subcommand.

Each test scaffolds a ``docs/audit/`` workspace into a temp cwd, runs
``exec`` against it, and asserts on stdout + exit code. The validation
gates and parser are reused from ``cli.fix`` (same workspace contract,
same markdown grammar), so these tests focus on the prompt-rendering
surface that's unique to ``exec``.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.exec import run_exec  # noqa: E402
from cli.audit import AUDIT_V1_TEMPLATE, CLEANUP_PLAN_TEMPLATE  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FILLED_AUDIT_V1 = """\
# Audit V1

P0 finding: stale start-here doc.
P1 finding: skill-path drift in 4 docs.

## Metadata
- Date: 2026-04-28
- Model: Claude Opus 4.7
- Notes: First real audit
"""

FILLED_PLAN = """\
# Cleanup Plan

Filled in from the audit.

## Phases

### Phase 1 — Tell the truth
- Run: python3 context_kit.py inventory --write
- Update: 00-START-NEXT-SESSION.md
- Write: SESSION_013 handoff

### Phase 2 — Fix references
- Replace stale skill paths in CLAUDE.md
- Update inventory subcommand table

### Phase 3 — Process guardrails
- Add inventory --check to CI
"""


def _exec_args(phase: int | None = None, next_step: bool = False) -> argparse.Namespace:
    return argparse.Namespace(command="exec", phase=phase, next_step=next_step)


def _run_exec_capture(**kwargs) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_exec(_exec_args(**kwargs))
    return rc, buf.getvalue()


def _seed_workspace(tmpdir: Path, *, audit_v1: str, plan: str) -> None:
    audit_dir = tmpdir / "docs" / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "AUDIT_V1.md").write_text(audit_v1, encoding="utf-8")
    (audit_dir / "CLEANUP_PLAN.md").write_text(plan, encoding="utf-8")


class _CwdSandbox(unittest.TestCase):
    """Each test runs inside a clean temp cwd."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self._prev_cwd = Path.cwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Validation: workspace not ready
# ---------------------------------------------------------------------------


class TestExecValidation(_CwdSandbox):
    def test_missing_audit_dir_exits_one(self):
        rc, out = _run_exec_capture()
        self.assertEqual(rc, 1)
        self.assertIn("not initialized or not filled", out)
        self.assertIn("context-kit audit --write", out)

    def test_scaffold_only_workspace_exits_one(self):
        # Both files exist but still carry their scaffold marker
        # substrings, so the workspace isn't filled.
        _seed_workspace(
            self.tmpdir,
            audit_v1=AUDIT_V1_TEMPLATE,
            plan=CLEANUP_PLAN_TEMPLATE,
        )
        rc, out = _run_exec_capture()
        self.assertEqual(rc, 1)
        self.assertIn("not initialized or not filled", out)


# ---------------------------------------------------------------------------
# Full prompt
# ---------------------------------------------------------------------------


class TestExecFullPrompt(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN)

    def test_returns_zero(self):
        rc, _ = _run_exec_capture()
        self.assertEqual(rc, 0)

    def test_includes_all_required_sections(self):
        _, out = _run_exec_capture()
        self.assertIn("=== CONTEXT-KIT EXEC PROMPT ===", out)
        self.assertIn("Goal:", out)
        self.assertIn("Context:", out)
        self.assertIn("Instructions:", out)
        self.assertIn("Phase tasks:", out)
        self.assertIn("Constraints:", out)
        self.assertIn("Output expectations:", out)

    def test_full_plan_renders_all_three_phases_with_steps(self):
        _, out = _run_exec_capture()
        self.assertIn("Phase 1 — Tell the truth", out)
        self.assertIn("Phase 2 — Fix references", out)
        self.assertIn("Phase 3 — Process guardrails", out)
        self.assertIn("Run: python3 context_kit.py inventory --write", out)
        self.assertIn("Replace stale skill paths in CLAUDE.md", out)
        self.assertIn("Add inventory --check to CI", out)

    def test_full_plan_goal_names_full_execution(self):
        _, out = _run_exec_capture()
        # The full-plan goal must say something explicit about running
        # the whole plan, not just one phase.
        goal_line = next(line for line in out.splitlines() if "phased cleanup plan in full" in line)
        self.assertIn("full", goal_line.lower())

    def test_context_section_references_audit_workspace(self):
        _, out = _run_exec_capture()
        self.assertIn("docs/audit/AUDIT_V1.md", out)
        self.assertIn("docs/audit/CLEANUP_PLAN.md", out)


# ---------------------------------------------------------------------------
# --phase filtering
# ---------------------------------------------------------------------------


class TestExecPhaseFilter(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN)

    def test_phase_2_renders_only_phase_2(self):
        rc, out = _run_exec_capture(phase=2)
        self.assertEqual(rc, 0)
        self.assertIn("Phase 2 — Fix references", out)
        self.assertIn("Replace stale skill paths in CLAUDE.md", out)
        # Other phases must not leak through.
        self.assertNotIn("Phase 1 — Tell the truth", out)
        self.assertNotIn("Phase 3 — Process guardrails", out)
        self.assertNotIn("inventory --write", out)

    def test_phase_filter_keeps_prompt_scaffolding(self):
        # Even when scoped to a single phase, the prompt should still
        # include all six sections.
        _, out = _run_exec_capture(phase=2)
        self.assertIn("=== CONTEXT-KIT EXEC PROMPT ===", out)
        self.assertIn("Goal:", out)
        self.assertIn("Context:", out)
        self.assertIn("Instructions:", out)
        self.assertIn("Phase tasks:", out)
        self.assertIn("Constraints:", out)
        self.assertIn("Output expectations:", out)

    def test_phase_filter_goal_names_single_phase(self):
        _, out = _run_exec_capture(phase=2)
        self.assertIn("Execute Phase 2", out)
        self.assertIn("Do not start", out)  # explicit anti-scope-creep

    def test_unknown_phase_exits_one(self):
        rc, out = _run_exec_capture(phase=9)
        self.assertEqual(rc, 1)
        self.assertIn("phase 9 not found", out)
        self.assertIn("available: 1, 2, 3", out)


# ---------------------------------------------------------------------------
# --next single-step prompt
# ---------------------------------------------------------------------------


class TestExecNextStep(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN)

    def test_next_returns_zero(self):
        rc, _ = _run_exec_capture(next_step=True)
        self.assertEqual(rc, 0)

    def test_next_renders_only_first_step(self):
        _, out = _run_exec_capture(next_step=True)
        self.assertIn("Run: python3 context_kit.py inventory --write", out)
        # No other steps must leak.
        self.assertNotIn("00-START-NEXT-SESSION.md", out)
        self.assertNotIn("SESSION_013 handoff", out)
        self.assertNotIn("Phase 2", out)
        self.assertNotIn("Phase 3", out)

    def test_next_uses_single_step_framing_in_goal(self):
        _, out = _run_exec_capture(next_step=True)
        self.assertIn("Execute exactly one task", out)
        self.assertIn("Stop after this single", out)

    def test_next_uses_single_step_output_expectations(self):
        _, out = _run_exec_capture(next_step=True)
        # Single-step variant of the output-expectations block fires.
        self.assertIn("This invocation requested a single step.", out)
        # The "ready for the next ... invocation" wording, allowing the
        # `context-kit exec --next` literal to wrap onto its own line.
        self.assertIn("ready for the next", out)
        self.assertIn("`context-kit exec --next`", out)
        self.assertIn("invocation", out)

    def test_next_skips_empty_phases_to_find_a_step(self):
        plan = (
            "## Phases\n\n"
            "### Phase 1 — Empty stub\n\n"
            "### Phase 2 — Real work\n"
            "- Do the thing\n"
        )
        (self.tmpdir / "docs" / "audit" / "CLEANUP_PLAN.md").write_text(plan, encoding="utf-8")
        rc, out = _run_exec_capture(next_step=True)
        self.assertEqual(rc, 0)
        self.assertIn("Do the thing", out)
        self.assertIn("Phase 2", out)


if __name__ == "__main__":
    unittest.main()
