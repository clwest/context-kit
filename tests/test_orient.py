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


def _orient_args(project, *, short: bool = False):
    return argparse.Namespace(command="orient", project=str(project), short=short)


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


# ---------------------------------------------------------------------------
# SESSION_START discovery + orient inclusion
# ---------------------------------------------------------------------------


from cli.orient import _find_session_start_doc  # noqa: E402


class TestSessionStartDiscovery(unittest.TestCase):
    """The SESSION_START doc is project-owned and handwritten. Orient
    discovers it (suffix-first, then plain, then root) and includes it
    in the report above the long anchor previews. Absent → silently
    omitted so older projects still print the same report."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "ss-app"
        run_init(_init_args("SS App", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_init_scaffolds_session_start_doc(self):
        path = _find_session_start_doc(self.project)
        self.assertIsNotNone(path)
        # Suffix-first: the scaffolded file uses the APP_UPPER prefix.
        self.assertEqual(path.name, "SS_APP_SESSION_START.md")

    def test_orient_includes_session_start_section(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("## SESSION START INDEX", out)
        self.assertIn("SS_APP_SESSION_START.md", out)

    def test_source_of_truth_lists_session_start_first(self):
        _, out = _run_orient_capture(self.project)
        # When the doc is present, orient prints a "0." entry above
        # the numbered anchors so an agent reads the short index
        # before the long anchors.
        self.assertIn("0.", out)
        self.assertIn("project-owned session-start", out)

    def test_orient_silently_omits_section_when_doc_absent(self):
        path = _find_session_start_doc(self.project)
        self.assertIsNotNone(path)
        path.unlink()
        _, out = _run_orient_capture(self.project)
        # Section is omitted, not printed-with-(missing). Older
        # projects must still print a clean report unchanged.
        self.assertNotIn("## SESSION START INDEX", out)
        self.assertNotIn("project-owned session-start", out)


class TestSessionStartDiscoveryFallbacks(unittest.TestCase):
    """Discovery rules: ``docs/<APP>_SESSION_START.md`` →
    ``docs/SESSION_START.md`` → ``SESSION_START.md`` at root."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "p"
        self.project.mkdir()
        (self.project / "00-START-NEXT-SESSION.md").write_text("# Start\n")
        (self.project / "docs").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_plain_docs_session_start_is_discovered(self):
        path = self.project / "docs" / "SESSION_START.md"
        path.write_text("# Plain\n")
        self.assertEqual(_find_session_start_doc(self.project), path)

    def test_root_session_start_is_discovered(self):
        path = self.project / "SESSION_START.md"
        path.write_text("# Root\n")
        self.assertEqual(_find_session_start_doc(self.project), path)

    def test_suffixed_wins_over_plain(self):
        suffixed = self.project / "docs" / "MYAPP_SESSION_START.md"
        suffixed.write_text("# Suffixed\n")
        plain = self.project / "docs" / "SESSION_START.md"
        plain.write_text("# Plain\n")
        # Suffix-first: anchors share this convention.
        self.assertEqual(_find_session_start_doc(self.project), suffixed)


# ---------------------------------------------------------------------------
# Low-signal inventory framing
# ---------------------------------------------------------------------------


class TestOrientLowSignalInventoryFraming(unittest.TestCase):
    """When the inventory carries the LOW-SIGNAL marker, orient must
    not present it as the runtime-truth anchor. Counts that are zero
    by detector design must not be presented as authoritative."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "p"
        self.project.mkdir()
        (self.project / "00-START-NEXT-SESSION.md").write_text("# Start\n")
        (self.project / "docs").mkdir()
        (self.project / "docs" / "FF_WHAT_IT_IS.md").write_text("# What\n")
        # Render an actual inventory body via collect+render so the
        # marker is the real one, not a hand-crafted string.
        from cli.inventory import (  # noqa: E402
            END_MARKER,
            START_MARKER,
            collect_inventory,
            render_block_body,
        )
        inv = collect_inventory(self.project)
        body = render_block_body(inv)
        (self.project / "docs" / "FF_INVENTORY.md").write_text(
            f"---\ntitle: 'inv'\n---\n\n{START_MARKER}\n{body}\n{END_MARKER}\n"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_source_of_truth_uses_low_signal_framing(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("LOW-SIGNAL", out)
        # The strict "wins on conflict" framing must NOT appear when
        # the inventory is low-signal — that line is what mislead
        # agents into trusting zero counts.
        self.assertNotIn("the inventory is right", out)

    def test_emits_actionable_low_signal_note(self):
        _, out = _run_orient_capture(self.project)
        self.assertIn("Verify counts directly", out)


# ---------------------------------------------------------------------------
# orient --short
# ---------------------------------------------------------------------------


class TestOrientShortMode(unittest.TestCase):
    """`--short` is the cheap re-orientation path: source-of-truth
    order, session-start doc filename, latest handoff filename,
    next-task pointer, doctor warning summary. No anchor previews."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "short-app"
        run_init(_init_args("Short App", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_zero(self):
        rc, _ = _run_orient_capture(self.project)
        rc_short, _ = _run_orient_capture_short(self.project)
        self.assertEqual(rc, 0)
        self.assertEqual(rc_short, 0)

    def test_emits_short_header(self):
        _, out = _run_orient_capture_short(self.project)
        self.assertIn("# context-kit orient (short)", out)

    def test_includes_required_sections(self):
        _, out = _run_orient_capture_short(self.project)
        self.assertIn("## SOURCE OF TRUTH", out)
        # Latest handoff is the auto-scaffolded SESSION_001_BOOTSTRAP.
        self.assertIn("## LATEST HANDOFF", out)
        self.assertIn("SESSION_001_BOOTSTRAP.md", out)
        self.assertIn("## DOCTOR", out)
        # Session-start was scaffolded by init.
        self.assertIn("## SESSION START INDEX", out)

    def test_omits_long_anchor_previews(self):
        # The full report has anchor preview blocks. Short mode
        # must not.
        _, out_short = _run_orient_capture_short(self.project)
        _, out_full = _run_orient_capture(self.project)
        self.assertIn("## ANCHORS", out_full)
        self.assertNotIn("## ANCHORS", out_short)
        self.assertNotIn("## START HERE — 00-START-NEXT-SESSION.md", out_short)

    def test_doctor_summary_counts_appear(self):
        _, out = _run_orient_capture_short(self.project)
        # Format: "  N blocking, N warnings, N ok, N skipped"
        import re as _re
        self.assertTrue(
            _re.search(r"\d+ blocking, \d+ warnings, \d+ ok, \d+ skipped", out),
            f"missing doctor summary line in:\n{out}",
        )

    def test_short_mode_does_not_break_when_session_start_absent(self):
        # Older projects without the SESSION_START scaffold must
        # still get a clean short report (section omitted, not (missing)).
        path = self.project / "docs" / "SHORT_APP_SESSION_START.md"
        if path.is_file():
            path.unlink()
        rc, out = _run_orient_capture_short(self.project)
        self.assertEqual(rc, 0)
        self.assertNotIn("## SESSION START INDEX", out)


def _run_orient_capture_short(project: Path) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_orient(_orient_args(project, short=True))
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# Backward compatibility — older projects predating the new sections
# ---------------------------------------------------------------------------


class TestBackwardCompatNoNewDocs(unittest.TestCase):
    """A project that was scaffolded before SESSION_START / behavior /
    pipeline / do_nots templates existed must still get a clean orient
    report. New sections silently omit when their docs are absent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "old"
        self.project.mkdir()
        # Bare-bones project: just the absolute load-bearing pieces
        # — start-here doc + the two-doc anchors.
        (self.project / "00-START-NEXT-SESSION.md").write_text("# Start\n")
        (self.project / "docs").mkdir()
        (self.project / "docs" / "OLD_WHAT_IT_IS.md").write_text("# What\n")
        (self.project / "docs" / "OLD_INVENTORY.md").write_text("# Inv\n")
        (self.project / "docs" / "handoffs").mkdir()
        (self.project / "docs" / "handoffs" / "SESSION_001_BOOTSTRAP.md").write_text("# 1\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_full_report_still_works(self):
        rc, out = _run_orient_capture(self.project)
        self.assertEqual(rc, 0)
        self.assertIn("## SOURCE OF TRUTH", out)
        # New sections silently omit.
        self.assertNotIn("## SESSION START INDEX", out)
        self.assertNotIn("## PIPELINE", out)
        self.assertNotIn("## BEHAVIOR LAYER", out)

    def test_short_mode_still_works(self):
        rc, out = _run_orient_capture_short(self.project)
        self.assertEqual(rc, 0)
        self.assertNotIn("## SESSION START INDEX", out)
        # Latest handoff still surfaces.
        self.assertIn("SESSION_001_BOOTSTRAP.md", out)


# ---------------------------------------------------------------------------
# Doctor warnings remain non-blocking through doctor itself
# ---------------------------------------------------------------------------


class TestNewWarningsAreNeverBlocking(unittest.TestCase):
    """All four orientation-drift checks (next-task consistency,
    handoff numbering, adopt placeholders, stale generic actions)
    must surface as warnings. Doctor's exit code stays 0 even when
    every one of them fires together."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "noisy"
        self.project.mkdir()
        (self.project / "docs" / "handoffs").mkdir(parents=True)
        (self.project / "docs" / "handoffs" / "SESSION_001_BOOTSTRAP.md").write_text("# 1\n")
        # Trigger every new check at once:
        adopt_block = (
            "<!-- context-kit:adopt:start -->\n"
            "## What's next\n\nContinue SESSION_010 work\n\n"
            "## Next actions\n- Confirm backend/frontend boundaries\n"
            "<!-- context-kit:adopt:end -->\n"
        )
        # 1) handwritten next-task disagrees with managed
        # 2) handoff gap (next 010 vs latest 001)
        # 3) adopt placeholder
        # 4) stale generic action ("Confirm backend/frontend boundaries")
        body = (
            "# Title\n\n" + adopt_block
            + "\n## Next session priorities\n\nPolish demo flow\n"
            + "\nProject summary: [adopt: please describe]\n"
        )
        (self.project / "00-START-NEXT-SESSION.md").write_text(body)

    def tearDown(self):
        self._tmp.cleanup()

    def test_doctor_exit_code_is_zero_with_all_new_warnings(self):
        from cli.doctor import _exit_code, run_all_checks  # noqa: E402
        results = run_all_checks(self.project)
        # Every new check should fire warning, never blocking.
        new_check_ids = {
            "next_task_consistency",
            "handoff_numbering",
            "adopt_placeholders",
            "stale_generic_actions",
        }
        new_results = [r for r in results if r.id in new_check_ids]
        self.assertEqual(len(new_results), 4)
        for r in new_results:
            self.assertNotEqual(r.status, "blocking", f"{r.id} should never block")
        self.assertEqual(_exit_code(results), 0)


if __name__ == "__main__":
    unittest.main()
