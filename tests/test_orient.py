"""Tests for the context-kit `orient` subcommand.

Each test scaffolds a real project into a temp directory, runs `orient`
against it, and asserts on the captured stdout. Sequential and self-cleaning.
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.bootstrap import run_init  # noqa: E402
from cli.orient import run_orient  # noqa: E402


def _init_args(name, target):
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=False,
        force=False,
        quiet=True,
    )


def _orient_args(project):
    return argparse.Namespace(command="orient", project=str(project))


def _run_orient_capture(project: Path) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_orient(_orient_args(project))
    return rc, buf.getvalue()


class TestOrientInScaffoldedProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "orient-app"
        run_init(_init_args("Orient App", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_zero(self):
        rc, _ = _run_orient_capture(self.project)
        self.assertEqual(rc, 0)

    def test_includes_required_sections(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("# context-kit orient", out)
        self.assertIn("## SOURCE OF TRUTH", out)
        self.assertIn("## START HERE", out)
        self.assertIn("## ANCHORS", out)
        self.assertIn("## LATEST HANDOFF", out)
        self.assertIn("## WHAT TO DO NOW", out)

    def test_discovers_anchor_doc_paths(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("docs/ORIENT_APP_WHAT_IT_IS.md", out)
        self.assertIn("docs/ORIENT_APP_INVENTORY.md", out)

    def test_finds_bootstrap_handoff(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("SESSION_001_BOOTSTRAP.md", out)

    def test_runtime_wins_rule_is_stated(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("inventory is right", out.lower().replace("inventory wins", "inventory is right"))


class TestOrientOutsideAContextKitProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_two_with_helpful_message(self):
        empty = self.tmpdir / "empty"
        empty.mkdir()
        rc, out = _run_orient_capture(empty)
        self.assertEqual(rc, 2)
        self.assertIn("doesn't look like a context-kit project", out)


class TestOrientHandlesMissingHandoffs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "no-handoffs"
        run_init(_init_args("No Handoffs", self.project))
        # Remove the bootstrap handoff to simulate a session-zero state.
        for p in (self.project / "docs" / "handoffs").glob("*.md"):
            p.unlink()

    def tearDown(self):
        self._tmp.cleanup()

    def test_does_not_crash(self):
        rc, out = _run_orient_capture(self.project)
        self.assertEqual(rc, 0)
        self.assertIn("(none yet)", out)


if __name__ == "__main__":
    unittest.main()
