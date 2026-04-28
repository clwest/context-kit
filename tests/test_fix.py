"""Tests for the context-kit `fix` subcommand.

Each test scaffolds a ``docs/audit/`` workspace into a temp cwd, runs
``fix`` against it, and asserts on stdout + exit code. Sequential and
self-cleaning. The command is read-only by contract — these tests do
not need to verify "no files modified" because the implementation has
no write paths.
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

from cli.fix import run_fix  # noqa: E402
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

FILLED_PLAN_HEADINGS = """\
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
- Enforce handoff-per-release
"""

FILLED_PLAN_BULLETS = """\
# Cleanup Plan

Filled in from the audit.

## Phases

- Phase 1 — Tell the truth
  - Run: python3 context_kit.py inventory --write
  - Update: 00-START-NEXT-SESSION.md
- Phase 2 — Fix references
  - Replace stale skill paths in CLAUDE.md
- Phase 3 — Process guardrails
  - Add inventory --check to CI
"""


def _fix_args(phase: int | None = None, next_step: bool = False) -> argparse.Namespace:
    return argparse.Namespace(command="fix", phase=phase, next_step=next_step)


def _run_fix_capture(**kwargs) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_fix(_fix_args(**kwargs))
    return rc, buf.getvalue()


def _seed_workspace(tmpdir: Path, *, audit_v1: str, plan: str) -> None:
    audit_dir = tmpdir / "docs" / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "AUDIT_V1.md").write_text(audit_v1, encoding="utf-8")
    (audit_dir / "CLEANUP_PLAN.md").write_text(plan, encoding="utf-8")


class _CwdSandbox(unittest.TestCase):
    """Base TestCase that runs each test inside a clean temp cwd."""

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


class TestFixValidation(_CwdSandbox):
    def test_missing_audit_dir_exits_one(self):
        rc, out = _run_fix_capture()
        self.assertEqual(rc, 1)
        self.assertIn("not initialized or not filled", out)
        self.assertIn("context-kit audit --write", out)

    def test_only_audit_v1_present_exits_one(self):
        audit_dir = self.tmpdir / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        (audit_dir / "AUDIT_V1.md").write_text(FILLED_AUDIT_V1, encoding="utf-8")
        rc, out = _run_fix_capture()
        self.assertEqual(rc, 1)
        self.assertIn("not initialized or not filled", out)

    def test_scaffold_audit_v1_exits_one(self):
        _seed_workspace(
            self.tmpdir,
            audit_v1=AUDIT_V1_TEMPLATE,  # still carries the scaffold marker
            plan=FILLED_PLAN_HEADINGS,
        )
        rc, out = _run_fix_capture()
        self.assertEqual(rc, 1)
        self.assertIn("not initialized or not filled", out)

    def test_scaffold_cleanup_plan_exits_one(self):
        _seed_workspace(
            self.tmpdir,
            audit_v1=FILLED_AUDIT_V1,
            plan=CLEANUP_PLAN_TEMPLATE,  # still carries the scaffold marker
        )
        rc, out = _run_fix_capture()
        self.assertEqual(rc, 1)
        self.assertIn("not initialized or not filled", out)

    def test_filled_but_unparseable_plan_exits_one(self):
        _seed_workspace(
            self.tmpdir,
            audit_v1=FILLED_AUDIT_V1,
            plan="# Cleanup Plan\n\nNo phases here, just prose.\n",
        )
        rc, out = _run_fix_capture()
        self.assertEqual(rc, 1)
        self.assertIn("no phases parsed", out)


# ---------------------------------------------------------------------------
# Full-plan rendering
# ---------------------------------------------------------------------------


class TestFixFullPlan(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN_HEADINGS)

    def test_returns_zero(self):
        rc, _ = _run_fix_capture()
        self.assertEqual(rc, 0)

    def test_includes_header(self):
        _, out = _run_fix_capture()
        self.assertIn("=== CONTEXT-KIT FIX PLAN ===", out)

    def test_lists_all_three_phases_with_titles(self):
        _, out = _run_fix_capture()
        self.assertIn("Phase 1 — Tell the truth", out)
        self.assertIn("Phase 2 — Fix references", out)
        self.assertIn("Phase 3 — Process guardrails", out)

    def test_includes_steps_under_phases(self):
        _, out = _run_fix_capture()
        self.assertIn("Run: python3 context_kit.py inventory --write", out)
        self.assertIn("Replace stale skill paths in CLAUDE.md", out)
        self.assertIn("Add inventory --check to CI", out)


class TestFixFullPlanBulletShape(_CwdSandbox):
    """Same assertions, but the source plan uses the bulleted shape
    instead of H3 headings — proves the parser handles both."""

    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN_BULLETS)

    def test_bullet_shape_renders_three_phases(self):
        rc, out = _run_fix_capture()
        self.assertEqual(rc, 0)
        self.assertIn("Phase 1 — Tell the truth", out)
        self.assertIn("Phase 2 — Fix references", out)
        self.assertIn("Phase 3 — Process guardrails", out)

    def test_bullet_shape_collects_indented_steps(self):
        _, out = _run_fix_capture()
        self.assertIn("Run: python3 context_kit.py inventory --write", out)
        self.assertIn("Replace stale skill paths in CLAUDE.md", out)


# ---------------------------------------------------------------------------
# --phase filtering
# ---------------------------------------------------------------------------


class TestFixPhaseFilter(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN_HEADINGS)

    def test_phase_2_prints_only_phase_2(self):
        rc, out = _run_fix_capture(phase=2)
        self.assertEqual(rc, 0)
        self.assertIn("Phase 2 — Fix references", out)
        self.assertIn("Replace stale skill paths in CLAUDE.md", out)
        # Other phases must not leak through.
        self.assertNotIn("Phase 1 — Tell the truth", out)
        self.assertNotIn("Phase 3 — Process guardrails", out)
        # And the all-phases header must be absent.
        self.assertNotIn("=== CONTEXT-KIT FIX PLAN ===", out)

    def test_unknown_phase_exits_one(self):
        rc, out = _run_fix_capture(phase=7)
        self.assertEqual(rc, 1)
        self.assertIn("phase 7 not found", out)
        self.assertIn("available: 1, 2, 3", out)


# ---------------------------------------------------------------------------
# --next
# ---------------------------------------------------------------------------


class TestFixNextStep(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_workspace(self.tmpdir, audit_v1=FILLED_AUDIT_V1, plan=FILLED_PLAN_HEADINGS)

    def test_next_prints_first_step_of_first_phase(self):
        rc, out = _run_fix_capture(next_step=True)
        self.assertEqual(rc, 0)
        self.assertIn("Run: python3 context_kit.py inventory --write", out)
        # Header / phase titles / later steps must not leak.
        self.assertNotIn("=== CONTEXT-KIT FIX PLAN ===", out)
        self.assertNotIn("Phase 1 —", out)
        self.assertNotIn("Replace stale skill paths in CLAUDE.md", out)

    def test_next_skips_empty_phases_to_find_first_step(self):
        plan = (
            "## Phases\n\n"
            "### Phase 1 — Empty stub\n\n"
            "### Phase 2 — Real work\n"
            "- Do the thing\n"
        )
        # Re-seed in place.
        (self.tmpdir / "docs" / "audit" / "CLEANUP_PLAN.md").write_text(plan, encoding="utf-8")
        rc, out = _run_fix_capture(next_step=True)
        self.assertEqual(rc, 0)
        self.assertIn("Do the thing", out)


if __name__ == "__main__":
    unittest.main()
