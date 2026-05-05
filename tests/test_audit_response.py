"""Tests for the ``context-kit audit-response`` command."""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.bootstrap import run_init  # noqa: E402
from cli.audit_response import run_audit_response  # noqa: E402


def _init_args(name: str, target: Path) -> argparse.Namespace:
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=False,
        force=False,
        quiet=True,
    )


def _audit_response_args(
    input_path: Path,
    output_path: Path | None = None,
    *,
    project: Path | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="audit-response",
        project=str(project) if project is not None else None,
        input=str(input_path),
        output=str(output_path) if output_path is not None else None,
    )


class TestAuditResponseCommand(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "audit-response-app"
        self.other_project = self.tmpdir / "other-audit-response-app"
        run_init(_init_args("Audit Response App", self.project))
        run_init(_init_args("Other Audit Response App", self.other_project))
        self._prev_cwd = Path.cwd()
        os.chdir(self.project)

    def tearDown(self):
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()

    def test_generates_output_file(self):
        response_path = self.tmpdir / "response.txt"
        response_path.write_text(
            "context-kit uses a runtime anchor (regenerable; wins on conflict).\n"
            "It has a version history feature.\n"
            "It can be applied to a chatbot.\n"
            "The inventory is hand-edited.\n",
            encoding="utf-8",
        )
        output_path = self.tmpdir / "audit.md"

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_audit_response(_audit_response_args(response_path, output_path))

        self.assertEqual(rc, 0)
        self.assertTrue(output_path.is_file())
        report = output_path.read_text(encoding="utf-8")
        self.assertIn("# context-kit response audit", report)
        self.assertIn("runtime anchor (regenerable; wins on conflict)", report)
        self.assertIn("grounded", report)
        self.assertIn("unsupported", report)
        self.assertIn("speculative", report)
        self.assertIn("contradicted", report)
        self.assertIn("## Summary", report)
        self.assertIn("## Claims", report)
        self.assertIn("## Orientation Used", report)
        self.assertIn("context-kit orient", buf.getvalue())

    def test_classifies_grounded_unsupported_speculative_and_contradicted(self):
        response_path = self.tmpdir / "response.txt"
        response_path.write_text(
            "The inventory is a runtime anchor (regenerable; wins on conflict).\n"
            "It has a version history feature.\n"
            "It can be applied to a chatbot.\n"
            "The inventory is hand-edited.\n",
            encoding="utf-8",
        )
        output_path = self.tmpdir / "audit.md"

        with redirect_stdout(io.StringIO()):
            rc = run_audit_response(_audit_response_args(response_path, output_path))

        self.assertEqual(rc, 0)
        report = output_path.read_text(encoding="utf-8")
        self.assertIn("| total claims | grounded | unsupported | speculative | contradicted |", report)
        self.assertIn("| 4 | 1 | 1 | 1 | 1 |", report)
        self.assertIn("| The inventory is a runtime anchor (regenerable; wins on conflict). | grounded |", report)
        self.assertIn("| It has a version history feature. | unsupported |", report)
        self.assertIn("| It can be applied to a chatbot. | speculative |", report)
        self.assertIn("| The inventory is hand-edited. | contradicted |", report)

    def test_project_flag_uses_target_orientation(self):
        response_path = Path("response.txt")
        response_path.write_text("It has a version history feature.\n", encoding="utf-8")
        output_path = Path("audit.md")

        with redirect_stdout(io.StringIO()):
            rc = run_audit_response(
                _audit_response_args(response_path, output_path, project=self.other_project)
            )

        self.assertEqual(rc, 0)
        report = output_path.read_text(encoding="utf-8")
        self.assertIn("Other Audit Response App", report)
        self.assertIn("docs/OTHER_AUDIT_RESPONSE_APP_WHAT_IT_IS.md", report)
        self.assertNotIn("docs/AUDIT_RESPONSE_APP_WHAT_IT_IS.md", report)

    def test_omitted_project_preserves_current_cwd_behavior(self):
        prev_cwd = Path.cwd()
        os.chdir(self.project)
        try:
            response_path = Path("response.txt")
            response_path.write_text("It has a version history feature.\n", encoding="utf-8")
            output_path = Path("audit.md")

            with redirect_stdout(io.StringIO()):
                rc = run_audit_response(_audit_response_args(response_path, output_path))
        finally:
            os.chdir(prev_cwd)

        self.assertEqual(rc, 0)
        report = output_path.read_text(encoding="utf-8")
        self.assertIn("Audit Response App", report)
        self.assertIn("docs/AUDIT_RESPONSE_APP_WHAT_IT_IS.md", report)

    def test_invalid_project_returns_clear_error(self):
        response_path = Path("response.txt")
        response_path.write_text("It has a version history feature.\n", encoding="utf-8")
        stderr = io.StringIO()
        bad_project = self.tmpdir / "missing-project"
        with redirect_stderr(stderr):
            rc = run_audit_response(_audit_response_args(response_path, project=bad_project))

        self.assertEqual(rc, 2)
        self.assertIn("error: --project path does not exist", stderr.getvalue())
