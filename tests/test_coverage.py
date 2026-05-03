"""Tests for the context-kit `coverage` subcommand."""

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

from cli.coverage import run_coverage  # noqa: E402


def _args(project: Path, *, json_out: bool = False, scope: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(command="coverage", path=str(project), json=json_out, scope=scope)


def _run(project: Path, *, json_out: bool = False, scope: str | None = None) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_coverage(_args(project, json_out=json_out, scope=scope))
    return rc, buf.getvalue()


def _write(path: Path, content: str = "x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


class _GitRepo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()
        subprocess.run(["git", "init"], cwd=self.project, check=True, capture_output=True, text=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _add_all(self) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True, capture_output=True, text=True)


class TestCoverageJsonShape(_GitRepo):
    def test_json_shape(self):
        _write(self.project / "core" / "app.py", "print('hi')\n")
        _write(self.project / "docs" / "guide.md", "# guide\n")
        _write(self.project / "tests" / "test_app.py", "def test_ok(): pass\n")
        _write(self.project / ".env.example", "X=1\n")
        _write(self.project / "dist" / "bundle.js", "console.log(1)\n")
        _write(self.project / "misc" / "odd.txt", "mystery\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], None)
        self.assertIn("summary", data)
        self.assertIn("by_classification", data)
        self.assertIn("by_top_directory", data)
        self.assertIn("unclassified_hot_files", data)
        self.assertEqual(set(data["by_classification"].keys()), {
            "runtime/source",
            "docs-active",
            "docs-historical",
            "tests",
            "generated/artifact",
            "config/deployment",
            "unknown",
        })
        self.assertGreaterEqual(data["summary"]["total_files"], 6)
        self.assertGreater(data["summary"]["unknown_files"], 0)

    def test_classes_are_reported(self):
        _write(self.project / "core" / "app.py", "print('hi')\n")
        _write(self.project / "docs" / "guide.md", "# guide\n")
        _write(self.project / "docs" / "archive" / "old.md", "# old\n")
        _write(self.project / "tests" / "test_app.py", "def test_ok(): pass\n")
        _write(self.project / ".env.example", "X=1\n")
        _write(self.project / "dist" / "bundle.js", "console.log(1)\n")
        _write(self.project / "misc" / "odd.txt", "mystery\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        by_class = data["by_classification"]
        self.assertEqual(by_class["runtime/source"]["files"], 1)
        self.assertEqual(by_class["docs-active"]["files"], 1)
        self.assertEqual(by_class["docs-historical"]["files"], 1)
        self.assertEqual(by_class["tests"]["files"], 1)
        self.assertEqual(by_class["config/deployment"]["files"], 1)
        self.assertEqual(by_class["generated/artifact"]["files"], 1)
        self.assertEqual(by_class["unknown"]["files"], 1)
        self.assertTrue(data["by_top_directory"])
        self.assertTrue(data["unclassified_hot_files"])


class TestCoverageScope(_GitRepo):
    def setUp(self):
        super().setUp()
        _write(self.project / "core" / "app.py", "print('hi')\n")
        _write(self.project / "docs" / "guide.md", "# guide\n")
        _write(self.project / "tests" / "test_app.py", "def test_ok(): pass\n")
        _write(self.project / "misc" / "odd.txt", "mystery\n")
        self._add_all()

    def test_scope_narrows_coverage(self):
        rc, out = _run(self.project, json_out=True, scope="core")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], "core")
        self.assertEqual(data["summary"]["total_files"], 1)
        self.assertEqual(data["by_classification"]["runtime/source"]["files"], 1)

    def test_invalid_scope_errors_clearly(self):
        rc, out = _run(self.project, scope="bogus")
        self.assertEqual(rc, 2)
        self.assertIn("unknown coverage scope", out.lower())


if __name__ == "__main__":
    unittest.main()
