"""Tests for the context-kit `verify` subcommand."""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.verify import END_MARKER, START_MARKER, run_verify  # noqa: E402


def _args(project: Path, *, json_: bool = False, write: bool = False) -> argparse.Namespace:
    return argparse.Namespace(command="verify", path=str(project), json=json_, write=write)


def _capture(args: argparse.Namespace) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_verify(args)
    return rc, buf.getvalue()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class VerifyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestVerifyJsonSchema(VerifyTestCase):
    def test_json_shape(self):
        _write(self.project / "README.md", "# Project\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(sorted(data.keys()), ["findings", "generated_at", "repo", "summary"])
        self.assertIn("total", data["summary"])
        self.assertIn("by_status", data["summary"])
        self.assertIsInstance(data["findings"], list)
        if data["findings"]:
            finding = data["findings"][0]
            for key in ("id", "title", "status", "category", "evidence", "details", "recommendation"):
                self.assertIn(key, finding)


class TestVerifyDjangoSettings(VerifyTestCase):
    def test_reports_conflict_when_docs_and_runtime_disagree(self):
        _write(self.project / ".env", "DJANGO_SETTINGS_MODULE=proj.settings\n")
        _write(
            self.project / "manage.py",
            'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "other.settings")\n',
        )
        _write(
            self.project / "core" / "asgi.py",
            'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "other.settings")\n',
        )
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("Django settings module", out)
        self.assertIn("proj.settings", out)
        self.assertIn("other.settings", out)


class TestVerifyDocCounts(VerifyTestCase):
    def test_docs_only_count_claim(self):
        _write(self.project / "README.md", "We have 74 agents and a small team.\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("DOC_ONLY", out)
        self.assertIn("Agents count claims", out)
        self.assertIn("74", out)

    def test_conflicting_count_claims(self):
        _write(self.project / "README.md", "We have 74 agents.\n")
        _write(self.project / "docs" / "NOTES.md", "Actually we have 75 agents.\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("74", out)
        self.assertIn("75", out)

    def test_verification_report_is_ignored_as_input(self):
        _write(self.project / "README.md", "We have 74 agents.\n")
        _write(self.project / "docs" / "verification" / "VERIFY_REPORT.md", "Actually we have 75 agents.\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("DOC_ONLY", out)
        self.assertIn("74", out)
        self.assertNotIn("75", out)
        self.assertNotIn("docs/verification/VERIFY_REPORT.md", out)


class TestVerifyTrackedArtifacts(VerifyTestCase):
    def test_detects_tracked_generated_artifact(self):
        subprocess.run(["git", "init"], cwd=self.project, check=True, capture_output=True, text=True)
        _write(self.project / "frontend" / "dist" / "bundle.js", "console.log('hi');\n")
        subprocess.run(["git", "add", "frontend/dist/bundle.js"], cwd=self.project, check=True, capture_output=True, text=True)

        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("Tracked generated artifacts", out)
        self.assertIn("frontend/dist/bundle.js", out)


class TestVerifyWriteMode(VerifyTestCase):
    def test_write_preserves_human_content_around_managed_block(self):
        report = self.project / "docs" / "verification" / "VERIFY_REPORT.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "# Human Notes\n\nKeep this.\n\n"
            f"{START_MARKER}\nold block\n{END_MARKER}\n\n"
            "# Footer\n",
            encoding="utf-8",
        )
        _write(self.project / "README.md", "We have 74 agents.\n")
        rc, _ = _capture(_args(self.project, write=True))
        self.assertEqual(rc, 0)
        body = report.read_text(encoding="utf-8")
        self.assertIn("# Human Notes", body)
        self.assertIn("Keep this.", body)
        self.assertIn("# Footer", body)
        self.assertIn(START_MARKER, body)
        self.assertIn(END_MARKER, body)
        self.assertNotIn("old block", body)
        self.assertIn("Verification Report", body)


if __name__ == "__main__":
    unittest.main()
