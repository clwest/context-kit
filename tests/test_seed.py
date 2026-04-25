"""Tests for the context-kit `seed` subcommand.

Tests are written first (per the design discussion's agreement). They
cover: idea-file parsing, validation, all 5 file renderers, dry-run,
idempotent re-run, --force, error cases, and the post-run output.

Each renderer test scaffolds a real project into a temp directory so
we exercise the same code path users will hit. A fixed timestamp
override (CONTEXT_KIT_SEED_TIMESTAMP) makes idempotency assertions
exact rather than fuzzy.
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
from cli.seed import (  # noqa: E402
    END_MARKER,
    SCHEMA_VERSION,
    START_MARKER,
    parse_idea,
    run_seed,
    validate_sections,
)


FIXED_TS = "2026-04-25T12:00:00+00:00"


def _init_args(name, target):
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=False,
        force=False,
        quiet=True,
    )


def _seed_args(idea, project=None, force=False, dry_run=False):
    return argparse.Namespace(
        command="seed",
        idea=str(idea),
        project=str(project) if project is not None else None,
        force=force,
        dry_run=dry_run,
    )


def _capture(args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_seed(args)
    return rc, buf.getvalue()


def _scaffold(tmpdir: Path, name: str = "Idea App") -> Path:
    project = tmpdir / "idea-app"
    run_init(_init_args(name, project))
    return project


_FULL_IDEA = """\
# Project Idea

## What are we building?

A small tool that watches a directory for new files and auto-tags them.

## Who is it for?

Developers who do reference dumps and lose track of where things landed.

## Problem

File trees rot. Things land somewhere and the location does not survive
the next session.

## Core features

- Watch path
- Tag files based on content
- Surface a small dashboard

## Tech stack

Python 3.11, Watchdog, FastAPI, SQLite.

## First milestone

Watch a single directory and emit JSON tags to stdout.

## What not to build yet

UI. Auth. Multi-user. Cloud.

## Open questions

- Real-time vs batched tagging?
- Local-only or sync to cloud later?
"""


_MINIMAL_IDEA = """\
# Smol

## What

A thing that does the thing.
"""


_IDEA_WITH_UNKNOWN = """\
# Project Idea

## What are we building?

A demo.

## Inspiration

The way `make` works.

## Risks

Unknown.
"""


def _setup_fixed_ts():
    os.environ["CONTEXT_KIT_SEED_TIMESTAMP"] = FIXED_TS


def _teardown_fixed_ts():
    os.environ.pop("CONTEXT_KIT_SEED_TIMESTAMP", None)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParseIdea(unittest.TestCase):
    def test_parses_canonical_sections(self):
        sections = parse_idea(_FULL_IDEA)
        self.assertEqual(sections["_title"], "Project Idea")
        self.assertIn("auto-tags", sections["what"])
        self.assertIn("Developers", sections["who"])
        self.assertIn("File trees rot", sections["problem"])
        self.assertIn("Watch path", sections["features"])
        self.assertIn("Python 3.11", sections["stack"])
        self.assertIn("Watch a single directory", sections["milestone"])
        self.assertIn("UI", sections["non_goals"])
        self.assertIn("Real-time", sections["questions"])
        self.assertEqual(sections["_unknown"], [])

    def test_tolerates_heading_variations(self):
        idea = (
            "# X\n\n"
            "## What it is\n\nA tool.\n\n"
            "## Audience\n\nUsers.\n\n"
            "## The Problem\n\nDrift.\n\n"
            "## Non-goals\n\nUI.\n\n"
            "## Questions\n\nMaybe?\n"
        )
        s = parse_idea(idea)
        self.assertEqual(s["what"], "A tool.")
        self.assertEqual(s["who"], "Users.")
        self.assertEqual(s["problem"], "Drift.")
        self.assertEqual(s["non_goals"], "UI.")
        self.assertEqual(s["questions"], "Maybe?")

    def test_strips_trailing_punctuation_from_headings(self):
        # "## What are we building?" matches "what" via punctuation strip.
        s = parse_idea("# X\n\n## What are we building?\n\nThings.\n")
        self.assertEqual(s["what"], "Things.")

    def test_unknown_headings_preserved_in_order(self):
        s = parse_idea(_IDEA_WITH_UNKNOWN)
        self.assertEqual(s["what"], "A demo.")
        labels = [label for label, _ in s["_unknown"]]
        self.assertEqual(labels, ["Inspiration", "Risks"])
        self.assertEqual(s["_unknown"][0][1], "The way `make` works.")

    def test_present_but_empty_section_is_empty_string(self):
        idea = "# X\n\n## What\n\nThing.\n\n## Open questions\n\n"
        s = parse_idea(idea)
        self.assertEqual(s.get("questions", "MISSING"), "")

    def test_missing_optional_sections_are_absent(self):
        s = parse_idea(_MINIMAL_IDEA)
        self.assertEqual(s["what"], "A thing that does the thing.")
        self.assertNotIn("who", s)
        self.assertNotIn("questions", s)

    def test_minimal_idea_extracts_title(self):
        s = parse_idea(_MINIMAL_IDEA)
        self.assertEqual(s["_title"], "Smol")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateSections(unittest.TestCase):
    def test_full_idea_passes_with_no_warnings(self):
        s = parse_idea(_FULL_IDEA)
        errors, warnings = validate_sections(s)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_missing_required_what_raises_error(self):
        s = parse_idea("# X\n\n## Who\n\nUsers.\n")
        errors, _ = validate_sections(s)
        self.assertTrue(any("what" in e.lower() for e in errors))

    def test_present_but_empty_what_is_an_error(self):
        s = parse_idea("# X\n\n## What\n\n")
        errors, _ = validate_sections(s)
        self.assertTrue(any("what" in e.lower() for e in errors))

    def test_missing_optional_warns(self):
        s = parse_idea(_MINIMAL_IDEA)
        _, warnings = validate_sections(s)
        # Several optional sections are missing; expect at least one warning.
        self.assertTrue(len(warnings) >= 1)
        # Required `what` is present, so no error related to it.
        self.assertTrue(all("what" not in w.lower() for w in warnings))

    def test_present_but_empty_optional_silent(self):
        idea = (
            "# X\n\n"
            "## What\n\nA thing.\n\n"
            "## Open questions\n\n"  # heading present, no body
        )
        s = parse_idea(idea)
        _, warnings = validate_sections(s)
        self.assertTrue(all("questions" not in w.lower() for w in warnings))

    def test_unknown_headings_emit_info_warning(self):
        s = parse_idea(_IDEA_WITH_UNKNOWN)
        _, warnings = validate_sections(s)
        joined = " ".join(warnings)
        self.assertIn("Inspiration", joined)
        self.assertIn("Risks", joined)


# ---------------------------------------------------------------------------
# End-to-end seed runs
# ---------------------------------------------------------------------------


class _SeedTestBase(unittest.TestCase):
    def setUp(self):
        _setup_fixed_ts()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = _scaffold(self.tmpdir)
        self.idea = self.tmpdir / "idea.md"
        self.idea.write_text(_FULL_IDEA, encoding="utf-8")

    def tearDown(self):
        _teardown_fixed_ts()
        self._tmp.cleanup()


class TestSeedWritesFiveTargets(_SeedTestBase):
    def test_what_it_is_block_present(self):
        rc, _ = _capture(_seed_args(self.idea, self.project))
        self.assertEqual(rc, 0)
        wii = self.project / "docs" / "IDEA_APP_WHAT_IT_IS.md"
        body = wii.read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)
        self.assertIn(END_MARKER, body)
        self.assertIn("auto-tags", body)
        self.assertIn(f"Schema version: {SCHEMA_VERSION}", body)

    def test_what_it_is_preserves_content_outside_markers(self):
        wii = self.project / "docs" / "IDEA_APP_WHAT_IT_IS.md"
        # Read scaffolded content; append a human note to the END.
        original = wii.read_text(encoding="utf-8")
        wii.write_text(original + "\n## My Notes\n\nKeep me.\n", encoding="utf-8")
        _capture(_seed_args(self.idea, self.project))
        body = wii.read_text(encoding="utf-8")
        self.assertIn("My Notes", body)
        self.assertIn("Keep me.", body)

    def test_start_here_block_present(self):
        _capture(_seed_args(self.idea, self.project))
        body = (self.project / "00-START-NEXT-SESSION.md").read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)
        self.assertIn("Watch a single directory", body)  # milestone
        self.assertIn("Real-time", body)  # questions

    def test_start_here_state_transitions_scaffold_to_seeded(self):
        path = self.project / "00-START-NEXT-SESSION.md"
        # init produces state: scaffold
        self.assertIn("state: scaffold", path.read_text(encoding="utf-8"))
        _capture(_seed_args(self.idea, self.project))
        body = path.read_text(encoding="utf-8")
        self.assertIn("state: seeded", body)
        self.assertNotIn("state: scaffold", body)

    def test_start_here_refuses_when_state_not_scaffold(self):
        path = self.project / "00-START-NEXT-SESSION.md"
        # Simulate a session-end handoff having been written: state moves off scaffold.
        body = path.read_text(encoding="utf-8")
        body = body.replace("state: scaffold", "state: active")
        path.write_text(body, encoding="utf-8")
        rc, out = _capture(_seed_args(self.idea, self.project))
        # Other targets still write; only 00-START refuses without --force.
        self.assertEqual(rc, 0)
        self.assertIn("00-START-NEXT-SESSION.md", out)
        self.assertIn("skipped", out.lower())
        self.assertNotIn(START_MARKER, path.read_text(encoding="utf-8"))

    def test_start_here_force_overrides_state_check(self):
        path = self.project / "00-START-NEXT-SESSION.md"
        body = path.read_text(encoding="utf-8").replace("state: scaffold", "state: active")
        path.write_text(body, encoding="utf-8")
        _capture(_seed_args(self.idea, self.project, force=True))
        self.assertIn(START_MARKER, path.read_text(encoding="utf-8"))

    def test_session_001_handoff_written_on_first_run(self):
        _capture(_seed_args(self.idea, self.project))
        h = self.project / "docs" / "handoffs" / "SESSION_001_IDEA_BOOTSTRAP.md"
        self.assertTrue(h.is_file())
        body = h.read_text(encoding="utf-8")
        self.assertIn("Idea Bootstrap", body)
        self.assertIn("idea.md", body)

    def test_session_001_handoff_refuses_overwrite(self):
        _capture(_seed_args(self.idea, self.project))
        h = self.project / "docs" / "handoffs" / "SESSION_001_IDEA_BOOTSTRAP.md"
        h.write_text("HUMAN EDIT", encoding="utf-8")
        _capture(_seed_args(self.idea, self.project))
        self.assertEqual(h.read_text(encoding="utf-8"), "HUMAN EDIT")

    def test_session_001_handoff_force_overwrites(self):
        _capture(_seed_args(self.idea, self.project))
        h = self.project / "docs" / "handoffs" / "SESSION_001_IDEA_BOOTSTRAP.md"
        h.write_text("HUMAN EDIT", encoding="utf-8")
        _capture(_seed_args(self.idea, self.project, force=True))
        self.assertNotEqual(h.read_text(encoding="utf-8"), "HUMAN EDIT")

    def test_product_topic_created(self):
        _capture(_seed_args(self.idea, self.project))
        p = self.project / "docs" / "topics" / "product.md"
        self.assertTrue(p.is_file())
        body = p.read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)
        self.assertIn("auto-tags", body)
        self.assertIn("Developers", body)

    def test_build_plan_created_with_all_sections(self):
        _capture(_seed_args(self.idea, self.project))
        bp = self.project / "docs" / "BUILD_PLAN.md"
        self.assertTrue(bp.is_file())
        body = bp.read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)
        self.assertIn("Watch a single directory", body)  # milestone
        self.assertIn("Watch path", body)  # features
        self.assertIn("Python 3.11", body)  # stack
        self.assertIn("UI", body)  # non_goals
        self.assertIn("Real-time", body)  # questions

    def test_build_plan_human_section_preserved_after_reseed(self):
        _capture(_seed_args(self.idea, self.project))
        bp = self.project / "docs" / "BUILD_PLAN.md"
        body = bp.read_text(encoding="utf-8")
        # The seeded file includes an Implementation notes section AFTER the markers.
        self.assertIn("Implementation notes", body)
        # Edit it.
        body = body.replace(
            "*(your notes go here. This section survives re-seed.)*",
            "I changed this and it should survive."
        )
        bp.write_text(body, encoding="utf-8")
        # Re-seed.
        _capture(_seed_args(self.idea, self.project))
        new_body = bp.read_text(encoding="utf-8")
        self.assertIn("I changed this and it should survive.", new_body)


class TestSeedIdempotency(_SeedTestBase):
    def test_re_seed_produces_identical_files(self):
        # Run twice with fixed timestamp; outputs should be byte-identical.
        _capture(_seed_args(self.idea, self.project))
        snapshot = {
            p.relative_to(self.project): p.read_bytes()
            for p in self.project.rglob("*.md")
            if p.is_file()
        }
        # Need --force on 00-START because state is now seeded.
        _capture(_seed_args(self.idea, self.project, force=True))
        for rel, data in snapshot.items():
            after = (self.project / rel).read_bytes()
            self.assertEqual(after, data, f"file changed on re-seed: {rel}")


class TestSeedUnknownHeadings(_SeedTestBase):
    def test_unknown_headings_land_in_other_notes(self):
        self.idea.write_text(_IDEA_WITH_UNKNOWN, encoding="utf-8")
        rc, out = _capture(_seed_args(self.idea, self.project))
        self.assertEqual(rc, 0)
        bp = self.project / "docs" / "BUILD_PLAN.md"
        body = bp.read_text(encoding="utf-8")
        self.assertIn("Other notes", body)
        self.assertIn("Inspiration", body)
        self.assertIn("Risks", body)
        # And the user is informed.
        self.assertIn("Inspiration", out)


class TestSeedDryRun(_SeedTestBase):
    def test_dry_run_writes_nothing(self):
        wii = self.project / "docs" / "IDEA_APP_WHAT_IT_IS.md"
        before = wii.read_bytes()
        rc, out = _capture(_seed_args(self.idea, self.project, dry_run=True))
        self.assertEqual(rc, 0)
        # File is unchanged
        self.assertEqual(wii.read_bytes(), before)
        # Build plan is NOT created
        self.assertFalse((self.project / "docs" / "BUILD_PLAN.md").exists())
        # Handoff is NOT created
        self.assertFalse(
            (self.project / "docs" / "handoffs" / "SESSION_001_IDEA_BOOTSTRAP.md").exists()
        )

    def test_dry_run_prints_summary(self):
        rc, out = _capture(_seed_args(self.idea, self.project, dry_run=True))
        self.assertEqual(rc, 0)
        # Lists what would change
        self.assertIn("BUILD_PLAN.md", out)
        self.assertIn("would", out.lower())


class TestSeedPostRunOutput(_SeedTestBase):
    def test_prints_next_commands(self):
        _, out = _capture(_seed_args(self.idea, self.project))
        # Suggested next commands appear in output
        self.assertIn("inventory --write", out)
        self.assertIn("orient", out)
        self.assertIn("claude", out)


class TestSeedErrors(unittest.TestCase):
    def setUp(self):
        _setup_fixed_ts()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        _teardown_fixed_ts()
        self._tmp.cleanup()

    def test_missing_idea_file_returns_2(self):
        project = _scaffold(self.tmpdir)
        rc, out = _capture(_seed_args(self.tmpdir / "nope.md", project))
        self.assertEqual(rc, 2)
        self.assertIn("not found", out.lower())

    def test_missing_required_what_returns_2(self):
        project = _scaffold(self.tmpdir)
        idea = self.tmpdir / "idea.md"
        idea.write_text("# X\n\n## Who\n\nPeople.\n", encoding="utf-8")
        rc, out = _capture(_seed_args(idea, project))
        self.assertEqual(rc, 2)
        self.assertIn("what", out.lower())

    def test_not_a_context_kit_project_returns_2(self):
        project = self.tmpdir / "not-a-project"
        project.mkdir()
        idea = self.tmpdir / "idea.md"
        idea.write_text(_FULL_IDEA, encoding="utf-8")
        rc, out = _capture(_seed_args(idea, project))
        self.assertEqual(rc, 2)
        self.assertIn("init", out.lower())


class TestSeedIntegration(_SeedTestBase):
    def test_full_happy_path_writes_all_five_targets(self):
        rc, _ = _capture(_seed_args(self.idea, self.project))
        self.assertEqual(rc, 0)
        expected = [
            self.project / "docs" / "IDEA_APP_WHAT_IT_IS.md",
            self.project / "00-START-NEXT-SESSION.md",
            self.project / "docs" / "handoffs" / "SESSION_001_IDEA_BOOTSTRAP.md",
            self.project / "docs" / "topics" / "product.md",
            self.project / "docs" / "BUILD_PLAN.md",
        ]
        for p in expected:
            self.assertTrue(p.is_file(), f"missing: {p.relative_to(self.project)}")


if __name__ == "__main__":
    unittest.main()
