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


if __name__ == "__main__":
    unittest.main()
