"""Tests for the context-kit `orient` subcommand.

Each test scaffolds a real project into a temp directory, runs `orient`
against it, and asserts on the captured stdout. Sequential and self-cleaning.
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

from cli.bootstrap import run_init  # noqa: E402
from cli.orient import run_orient, _latest_numbered_handoff  # noqa: E402


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


class TestLatestHandoffSelection(unittest.TestCase):
    """Direct coverage of the numbered-session selection rule.

    Drives ``_latest_numbered_handoff`` against a constructed
    ``handoffs/`` directory rather than spinning up a full project,
    so each scenario is unambiguous about which files are present.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.handoffs_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _touch(self, name: str, mtime: float | None = None) -> Path:
        path = self.handoffs_dir / name
        path.write_text(f"# {name}\n", encoding="utf-8")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_returns_none_when_directory_is_empty(self):
        self.assertIsNone(_latest_numbered_handoff(self.handoffs_dir))

    def test_session_roadmap_is_ignored(self):
        # ROADMAP isn't a numbered session; old code lex-sorted it as
        # the "latest" because 'R' > '0'-'9'. New code must skip it.
        self._touch("SESSION_ROADMAP_DISCONNECTED_FIXES.md")
        numbered = self._touch("SESSION_001_BOOTSTRAP.md")
        latest = _latest_numbered_handoff(self.handoffs_dir)
        self.assertEqual(latest, numbered)

    def test_only_non_numbered_files_returns_none(self):
        # ROADMAP + NOTES + RFC — none match SESSION_<digits>_*.md.
        self._touch("SESSION_ROADMAP_PLAN.md")
        self._touch("SESSION_NOTES_AD_HOC.md")
        self._touch("SESSION_RFC_OUTLINE.md")
        self.assertIsNone(_latest_numbered_handoff(self.handoffs_dir))

    def test_four_digit_session_beats_three_digit(self):
        # The unified-donkey-betz bug: ASCII '9' > '1', so under
        # lex-sort SESSION_999_* wins. Numeric sort must pick 1098.
        self._touch("SESSION_999_STOCK_INTELLIGENCE_HUB.md")
        winner = self._touch("SESSION_1098_WRAP_CANARY_GREEN.md")
        latest = _latest_numbered_handoff(self.handoffs_dir)
        self.assertEqual(latest, winner)

    def test_same_session_number_uses_newest_mtime(self):
        # Sessions often produce a wrap + addendum pair under the
        # same session number. Tiebreak picks the most-recent mtime.
        older = self._touch(
            "SESSION_1098_WRAP_CANARY_GREEN.md",
            mtime=1_700_000_000.0,
        )
        newer = self._touch(
            "SESSION_1098_ADDENDUM_2_TIER1_AND_BFULL.md",
            mtime=1_700_000_500.0,
        )
        latest = _latest_numbered_handoff(self.handoffs_dir)
        self.assertEqual(latest, newer)
        self.assertNotEqual(latest, older)

    def test_higher_session_number_wins_over_newer_mtime(self):
        # mtime is a tiebreaker for *equal* session numbers, not an
        # override. A freshly-touched older session must lose to a
        # higher-numbered older file.
        self._touch("SESSION_500_OLD.md", mtime=1_700_001_000.0)
        winner = self._touch("SESSION_1100_NEW.md", mtime=1_700_000_000.0)
        latest = _latest_numbered_handoff(self.handoffs_dir)
        self.assertEqual(latest, winner)


class TestOrientPicksLatestNumberedHandoffEndToEnd(unittest.TestCase):
    """Same selection rule, end-to-end through ``run_orient``: confirm
    the printed report names the right file when the directory mixes
    numbered handoffs, a roadmap, and the auto-scaffolded
    SESSION_001_BOOTSTRAP.md."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "orient-mixed"
        run_init(_init_args("Orient Mixed", self.project))
        handoffs = self.project / "docs" / "handoffs"
        # Add a stale ROADMAP and a four-digit session ahead of the
        # auto-scaffolded SESSION_001_BOOTSTRAP.md.
        (handoffs / "SESSION_ROADMAP_LEGACY_PLAN.md").write_text(
            "# stale roadmap\n", encoding="utf-8",
        )
        (handoffs / "SESSION_1100_LATEST.md").write_text(
            "# the actually latest one\n", encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_orient_picks_session_1100_not_roadmap_or_999(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("SESSION_1100_LATEST.md", out)
        self.assertNotIn("SESSION_ROADMAP_LEGACY_PLAN.md", out)


if __name__ == "__main__":
    unittest.main()
