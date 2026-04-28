"""Tests for the context-kit `audit` subcommand.

Two surfaces:
- Default mode prints a static prompt to stdout (no flags, no fs writes).
- ``--write`` mode scaffolds ``docs/audit/`` with two empty docs and is
  idempotent (never overwrites).
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

from cli.audit import run_audit  # noqa: E402


def _audit_args(write: bool = False) -> argparse.Namespace:
    return argparse.Namespace(command="audit", write=write)


def _run_audit_capture(write: bool = False) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_audit(_audit_args(write=write))
    return rc, buf.getvalue()


class TestAuditPromptOutput(unittest.TestCase):
    def test_returns_zero(self):
        rc, _ = _run_audit_capture()
        self.assertEqual(rc, 0)

    def test_prints_non_empty_output(self):
        _, out = _run_audit_capture()
        self.assertTrue(out.strip(), "audit should print a non-empty prompt")

    def test_includes_role_and_task_framing(self):
        _, out = _run_audit_capture()
        lower = out.lower()
        self.assertIn("stop explaining", lower)
        self.assertIn("senior engineer", lower)
        self.assertIn("deep audit", lower)

    def test_lists_audit_dimensions(self):
        _, out = _run_audit_capture()
        lower = out.lower()
        self.assertIn("stale", lower)
        self.assertIn("duplicated", lower)
        self.assertIn("dead code", lower)
        self.assertIn("risky", lower)
        self.assertIn("inconsistencies", lower)

    def test_requires_prioritization_and_phased_plan(self):
        _, out = _run_audit_capture()
        self.assertIn("P0", out)
        self.assertIn("P1", out)
        self.assertIn("P2", out)
        self.assertIn("phases", out.lower())


class TestAuditWriteScaffolding(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self._prev_cwd = Path.cwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()

    def test_returns_zero(self):
        rc, _ = _run_audit_capture(write=True)
        self.assertEqual(rc, 0)

    def test_creates_audit_directory(self):
        _run_audit_capture(write=True)
        self.assertTrue((self.tmpdir / "docs" / "audit").is_dir())

    def test_creates_both_scaffold_files(self):
        _run_audit_capture(write=True)
        audit_dir = self.tmpdir / "docs" / "audit"
        self.assertTrue((audit_dir / "AUDIT_V1.md").is_file())
        self.assertTrue((audit_dir / "CLEANUP_PLAN.md").is_file())

    def test_scaffold_file_contents_have_expected_headings(self):
        _run_audit_capture(write=True)
        audit_dir = self.tmpdir / "docs" / "audit"
        v1 = (audit_dir / "AUDIT_V1.md").read_text(encoding="utf-8")
        plan = (audit_dir / "CLEANUP_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("# Audit V1", v1)
        self.assertIn("## Metadata", v1)
        self.assertIn("# Cleanup Plan", plan)
        self.assertIn("## Phases", plan)
        self.assertIn("Phase 1:", plan)

    def test_does_not_overwrite_existing_files(self):
        audit_dir = self.tmpdir / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        v1_path = audit_dir / "AUDIT_V1.md"
        plan_path = audit_dir / "CLEANUP_PLAN.md"
        v1_path.write_text("# user-edited content; do not clobber\n", encoding="utf-8")
        plan_path.write_text("# user-edited plan\n", encoding="utf-8")

        rc, out = _run_audit_capture(write=True)

        self.assertEqual(rc, 0)
        self.assertEqual(v1_path.read_text(encoding="utf-8"), "# user-edited content; do not clobber\n")
        self.assertEqual(plan_path.read_text(encoding="utf-8"), "# user-edited plan\n")
        self.assertIn("skipped", out)

    def test_partial_existing_only_writes_missing_file(self):
        audit_dir = self.tmpdir / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        v1_path = audit_dir / "AUDIT_V1.md"
        v1_path.write_text("# pre-existing\n", encoding="utf-8")

        _run_audit_capture(write=True)

        self.assertEqual(v1_path.read_text(encoding="utf-8"), "# pre-existing\n")
        plan_path = audit_dir / "CLEANUP_PLAN.md"
        self.assertTrue(plan_path.is_file())
        self.assertIn("# Cleanup Plan", plan_path.read_text(encoding="utf-8"))


class TestAuditWriteUX(unittest.TestCase):
    """UX assertions on the --write output: next steps, prompt embedding,
    and the 'appear unfilled' notice for stale-scaffold cases."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self._prev_cwd = Path.cwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()

    def test_write_output_includes_next_steps_block(self):
        _, out = _run_audit_capture(write=True)
        self.assertIn("Next steps:", out)
        self.assertIn("Run: context-kit audit", out)
        self.assertIn("Paste the audit output into docs/audit/AUDIT_V1.md", out)
        self.assertIn("Extract phases into docs/audit/CLEANUP_PLAN.md", out)

    def test_write_output_embeds_audit_prompt(self):
        _, out = _run_audit_capture(write=True)
        # Prompt header + recognizable phrases from AUDIT_PROMPT itself.
        self.assertIn("Audit prompt:", out)
        self.assertIn("Stop explaining the project", out)
        self.assertIn("senior engineer", out.lower())
        self.assertIn("P0", out)
        self.assertIn("P1", out)
        self.assertIn("P2", out)

    def test_skipped_scaffold_files_report_appear_unfilled(self):
        audit_dir = self.tmpdir / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        # Pre-seed both files with the verbatim scaffold content -> still
        # carry their unfilled markers.
        from cli.audit import AUDIT_V1_TEMPLATE, CLEANUP_PLAN_TEMPLATE
        (audit_dir / "AUDIT_V1.md").write_text(AUDIT_V1_TEMPLATE, encoding="utf-8")
        (audit_dir / "CLEANUP_PLAN.md").write_text(CLEANUP_PLAN_TEMPLATE, encoding="utf-8")

        _, out = _run_audit_capture(write=True)
        self.assertIn("skipped", out)
        self.assertIn("Audit files exist but appear unfilled.", out)

    def test_filled_existing_files_do_not_report_appear_unfilled(self):
        audit_dir = self.tmpdir / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        # Real user content; the scaffold marker substrings are gone.
        (audit_dir / "AUDIT_V1.md").write_text(
            "# Audit V1\n\nP0 finding: foo bar\n", encoding="utf-8"
        )
        (audit_dir / "CLEANUP_PLAN.md").write_text(
            "# Cleanup Plan\n\n- Phase 1: ship the thing\n", encoding="utf-8"
        )

        _, out = _run_audit_capture(write=True)
        self.assertIn("skipped", out)
        self.assertNotIn("appear unfilled", out)

    def test_freshly_created_files_do_not_report_appear_unfilled(self):
        # Even though the just-written scaffold contains the marker, the
        # 'appear unfilled' notice is reserved for *pre-existing* files
        # that the user hasn't filled in yet.
        _, out = _run_audit_capture(write=True)
        self.assertIn("created", out)
        self.assertNotIn("appear unfilled", out)


if __name__ == "__main__":
    unittest.main()
