"""Tests for the context-kit `audit` subcommand.

The command is a static prompt printer — no project state, no flags.
These tests assert that it runs cleanly and that the printed prompt
covers the key phrases the AI is meant to act on.
"""

from __future__ import annotations

import argparse
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.audit import run_audit  # noqa: E402


def _run_audit_capture() -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_audit(argparse.Namespace(command="audit"))
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


if __name__ == "__main__":
    unittest.main()
