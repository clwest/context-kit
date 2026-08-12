"""Tests for the context-kit `handoff write` subcommand.

Covers:
- Frontmatter re-stamp (`last_revised:` set; `covers_sessions:` bumped when present).
- `last_revised:` is inserted after `generated:` when missing.
- Anchor doc set discovery (which globs match, which don't).
- Docs without frontmatter / without anchor fields are skipped.
- Calibration drift detection finds and matches handoff subsections.
- Calibration drift detection flags missing TRUST_CALIBRATION entries.
- ``--dry-run`` prints would-be changes without writing files.
- Idempotency (running twice doesn't change the file the second time
  after the first restamp lands).
- Missing handoff returns non-zero exit code.
- `--date` overrides the handoff frontmatter date.
- Non-integer session arg returns non-zero exit code.
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

from cli.handoff import (  # noqa: E402
    _bump_covers_sessions,
    _extract_calibration_entries,
    _fuzzy_tokens,
    _set_or_insert_field,
    _split_frontmatter,
    audit_calibration_promotion,
    extract_handoff_date,
    find_handoff_for_session,
    restamp_anchor_docs,
    run_handoff_write,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _args(session, project, *, date=None, dry_run=False):
    return argparse.Namespace(
        command="handoff",
        handoff_action="write",
        session=str(session),
        project=str(project),
        date=date,
        dry_run=dry_run,
    )


def _capture(args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_handoff_write(args)
    return rc, buf.getvalue()


_ANCHOR_WHAT_IT_IS = """\
---
title: "Demo — What It Is"
status: populated
generated: 2026-01-01
last_revised: 2026-01-10 (SESSION 100)
covers_sessions: "1-100"
---

# Demo — What It Is

Body text here.
"""

_ANCHOR_PIPELINE = """\
---
title: "Demo — Pipeline"
status: stub
generated: 2026-01-01
---

# Demo — Pipeline

Body text here.
"""

_ANCHOR_NO_FRONTMATTER = """\
# Demo — Behavior Layer

This file has no frontmatter at all.
"""

_ANCHOR_UNRELATED_FRONTMATTER = """\
---
title: "Demo — Translation Layer"
tags: ["unrelated"]
---

# Translation Layer

No anchor fields.
"""

_HANDOFF_158 = """\
---
title: "Session 158 — Whatever"
date: 2026-05-15
status: complete
session: 158
---

# Session 158

## TL;DR

Some prose.

## Calibration moments worth carrying

### 1. AI overstated shipped before operator viewed the output

Some prose.

### 2. Avatar voice quality varies operationally

More prose.

## What's next

Etc.
"""

_TRUST_CAL_WITH_ONE_MATCH = """\
---
title: "Trust Calibration Log"
---

# Trust Calibration Log

## 2026-05-15 — AI confidently wrong (deliverable framing): "shipped" before operator review

- **Context:** ...
- **Lesson:** ...

## 2026-04-01 — Some older entry

- **Context:** Different date, shouldn't match.
"""


class FrontmatterHelpersTest(unittest.TestCase):
    def test_split_and_join_roundtrip(self):
        text = "---\nfoo: 1\nbar: 2\n---\nBody\n"
        fm, body = _split_frontmatter(text)
        self.assertEqual(fm, "foo: 1\nbar: 2")
        self.assertEqual(body, "Body\n")

    def test_split_no_frontmatter(self):
        fm, body = _split_frontmatter("# title only\n")
        self.assertIsNone(fm)
        self.assertEqual(body, "# title only\n")

    def test_set_or_insert_existing_field(self):
        fm = "title: T\ngenerated: 2026-01-01\nlast_revised: 2026-01-05\n"
        new, prev = _set_or_insert_field(
            fm, field="last_revised", new_value="2026-05-15 (SESSION 99)",
            insert_after="generated",
        )
        self.assertEqual(prev, "2026-01-05")
        self.assertIn("last_revised: 2026-05-15 (SESSION 99)", new)
        # No duplicates
        self.assertEqual(new.count("last_revised:"), 1)

    def test_set_or_insert_inserts_after_anchor(self):
        fm = "title: T\ngenerated: 2026-01-01\n"
        new, prev = _set_or_insert_field(
            fm, field="last_revised", new_value="2026-05-15 (SESSION 99)",
            insert_after="generated",
        )
        self.assertIsNone(prev)
        # Inserted right after generated:
        lines = new.splitlines()
        gen_idx = next(i for i, line in enumerate(lines) if line.startswith("generated:"))
        self.assertTrue(lines[gen_idx + 1].startswith("last_revised: 2026-05-15"))

    def test_set_or_insert_appends_when_anchor_missing(self):
        fm = "title: T\nstatus: foo\n"
        new, prev = _set_or_insert_field(
            fm, field="last_revised", new_value="2026-05-15 (SESSION 99)",
            insert_after="generated",
        )
        self.assertIsNone(prev)
        self.assertTrue(new.endswith("last_revised: 2026-05-15 (SESSION 99)"))

    def test_bump_covers_sessions(self):
        fm = 'covers_sessions: "1-100"\n'
        new, before, after = _bump_covers_sessions(fm, session=158)
        self.assertEqual(before, "1-100")
        self.assertEqual(after, "1-158")
        self.assertIn('covers_sessions: "1-158"', new)

    def test_bump_covers_sessions_no_change_when_already_high_enough(self):
        # If current upper bound exceeds session, we still set it to session.
        # (Treat operator's input as authoritative.)
        fm = 'covers_sessions: "1-200"\n'
        _new, before, after = _bump_covers_sessions(fm, session=158)
        self.assertEqual(before, "1-200")
        self.assertEqual(after, "1-158")

    def test_bump_covers_sessions_absent(self):
        fm = "title: T\n"
        new, before, after = _bump_covers_sessions(fm, session=158)
        self.assertEqual(new, fm)
        self.assertIsNone(before)
        self.assertIsNone(after)


class RestampDiscoveryTest(unittest.TestCase):
    def test_discovers_matching_globs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            docs = project / "docs"
            _write(docs / "DEMO_WHAT_IT_IS.md", _ANCHOR_WHAT_IT_IS)
            _write(docs / "DEMO_PIPELINE.md", _ANCHOR_PIPELINE)
            _write(docs / "DEMO_SESSION_START.md", _ANCHOR_PIPELINE)
            _write(docs / "RANDOM_DOC.md", "# random")
            _write(docs / "DEMO_INVENTORY.md", "# inventory should be skipped")

            results = restamp_anchor_docs(
                project, session=159, date="2026-05-15", dry_run=True
            )
            names = sorted(r.path.name for r in results)
            self.assertEqual(
                names,
                ["DEMO_PIPELINE.md", "DEMO_SESSION_START.md", "DEMO_WHAT_IT_IS.md"],
            )

    def test_no_docs_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.assertEqual(
                restamp_anchor_docs(project, session=1, date="2026-01-01", dry_run=True),
                [],
            )


class RestampSemanticsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        self.docs = self.project / "docs"
        _write(self.docs / "DEMO_WHAT_IT_IS.md", _ANCHOR_WHAT_IT_IS)
        _write(self.docs / "DEMO_PIPELINE.md", _ANCHOR_PIPELINE)
        _write(self.docs / "DEMO_BEHAVIOR_LAYER.md", _ANCHOR_NO_FRONTMATTER)
        _write(self.docs / "DEMO_TRANSLATION_LAYER.md", _ANCHOR_UNRELATED_FRONTMATTER)

    def tearDown(self):
        self.tmp.cleanup()

    def test_restamps_what_it_is_updates_last_revised_and_covers(self):
        results = restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=False
        )
        what = self.project / "docs" / "DEMO_WHAT_IT_IS.md"
        text = what.read_text(encoding="utf-8")
        self.assertIn("last_revised: 2026-05-15 (SESSION 158)", text)
        self.assertIn('covers_sessions: "1-158"', text)
        action = next(r for r in results if r.path.name == "DEMO_WHAT_IT_IS.md")
        self.assertEqual(action.action, "restamped")
        self.assertEqual(action.last_revised_before, "2026-01-10 (SESSION 100)")
        self.assertEqual(action.covers_before, "1-100")

    def test_restamps_pipeline_inserts_last_revised_after_generated(self):
        # Pipeline doc has `generated:` but no `last_revised:`; the field
        # should be inserted, not appended.
        restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=False
        )
        text = (self.project / "docs" / "DEMO_PIPELINE.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        gen_idx = next(i for i, line in enumerate(lines) if line.startswith("generated:"))
        self.assertTrue(lines[gen_idx + 1].startswith("last_revised: 2026-05-15"))

    def test_skips_no_frontmatter(self):
        results = restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=False
        )
        beh = next(r for r in results if r.path.name == "DEMO_BEHAVIOR_LAYER.md")
        self.assertEqual(beh.action, "skipped (no frontmatter)")
        text = (self.project / "docs" / "DEMO_BEHAVIOR_LAYER.md").read_text(encoding="utf-8")
        self.assertEqual(text, _ANCHOR_NO_FRONTMATTER)

    def test_skips_frontmatter_without_anchor_fields(self):
        results = restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=False
        )
        trans = next(r for r in results if r.path.name == "DEMO_TRANSLATION_LAYER.md")
        self.assertEqual(trans.action, "skipped (no anchor fields)")

    def test_dry_run_does_not_write(self):
        before = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=True
        )
        after = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_idempotent_when_already_current(self):
        restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=False
        )
        once = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        results = restamp_anchor_docs(
            self.project, session=158, date="2026-05-15", dry_run=False
        )
        twice = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        self.assertEqual(once, twice)
        what_result = next(r for r in results if r.path.name == "DEMO_WHAT_IT_IS.md")
        self.assertEqual(what_result.action, "unchanged")


class CalibrationExtractionTest(unittest.TestCase):
    def test_extracts_two_subsections(self):
        entries = _extract_calibration_entries(_HANDOFF_158)
        self.assertEqual(len(entries), 2)
        self.assertEqual(
            entries[0].heading,
            "1. AI overstated shipped before operator viewed the output",
        )

    def test_accepts_ai_notes_heading(self):
        text = (
            "## AI Notes\n\n"
            "### thing one\n\nprose\n\n"
            "### thing two\n\nprose\n"
        )
        entries = _extract_calibration_entries(text)
        self.assertEqual([e.heading for e in entries], ["thing one", "thing two"])

    def test_returns_empty_when_no_section(self):
        self.assertEqual(_extract_calibration_entries("## Some other section\n### x\n"), [])

    def test_fuzzy_tokens_drops_stopwords_and_digits(self):
        tokens = _fuzzy_tokens("1. AI overstated shipped before operator viewed the output")
        self.assertIn("overstated", tokens)
        self.assertIn("shipped", tokens)
        self.assertNotIn("ai", tokens)
        self.assertNotIn("the", tokens)
        self.assertNotIn("1", tokens)


class CalibrationPromotionAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        _write(
            self.project / "docs" / "handoffs" / "SESSION_158_DEMO.md",
            _HANDOFF_158,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_matched_and_missing(self):
        _write(self.project / "docs" / "TRUST_CALIBRATION.md", _TRUST_CAL_WITH_ONE_MATCH)
        handoff = self.project / "docs" / "handoffs" / "SESSION_158_DEMO.md"
        entries = audit_calibration_promotion(
            self.project, handoff_path=handoff, handoff_date="2026-05-15"
        )
        self.assertEqual(len(entries), 2)
        matched = [e for e in entries if e.matched]
        missing = [e for e in entries if not e.matched]
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(missing), 1)
        self.assertIn("shipped", matched[0].heading.lower())
        self.assertIn("voice", missing[0].heading.lower())

    def test_no_trust_calibration_means_all_missing(self):
        handoff = self.project / "docs" / "handoffs" / "SESSION_158_DEMO.md"
        entries = audit_calibration_promotion(
            self.project, handoff_path=handoff, handoff_date="2026-05-15"
        )
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(not e.matched for e in entries))

    def test_different_date_does_not_match(self):
        # TRUST_CALIBRATION entry exists but on a different date; should miss.
        wrong_date = _TRUST_CAL_WITH_ONE_MATCH.replace("2026-05-15", "2026-05-14", 1)
        _write(self.project / "docs" / "TRUST_CALIBRATION.md", wrong_date)
        handoff = self.project / "docs" / "handoffs" / "SESSION_158_DEMO.md"
        entries = audit_calibration_promotion(
            self.project, handoff_path=handoff, handoff_date="2026-05-15"
        )
        # First entry was matching by content, but date is wrong now.
        self.assertTrue(all(not e.matched for e in entries))


class HandoffDiscoveryTest(unittest.TestCase):
    def test_finds_session_with_3_digit_pad(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs" / "handoffs" / "SESSION_158_DEMO.md", "x")
            found = find_handoff_for_session(project, 158)
            self.assertIsNotNone(found)
            self.assertEqual(found.name, "SESSION_158_DEMO.md")

    def test_finds_legacy_unpadded(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            _write(project / "docs" / "handoffs" / "SESSION_5_OLD.md", "x")
            self.assertEqual(find_handoff_for_session(project, 5).name, "SESSION_5_OLD.md")

    def test_missing_handoff_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_handoff_for_session(Path(tmp), 99))

    def test_extract_handoff_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "h.md"
            handoff.write_text(_HANDOFF_158, encoding="utf-8")
            self.assertEqual(extract_handoff_date(handoff), "2026-05-15")

    def test_extract_handoff_date_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            handoff = Path(tmp) / "h.md"
            handoff.write_text("# no frontmatter\n", encoding="utf-8")
            self.assertIsNone(extract_handoff_date(handoff))


class RunEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        _write(self.project / "docs" / "DEMO_WHAT_IT_IS.md", _ANCHOR_WHAT_IT_IS)
        _write(self.project / "docs" / "DEMO_PIPELINE.md", _ANCHOR_PIPELINE)
        _write(
            self.project / "docs" / "handoffs" / "SESSION_158_DEMO.md",
            _HANDOFF_158,
        )
        _write(self.project / "docs" / "TRUST_CALIBRATION.md", _TRUST_CAL_WITH_ONE_MATCH)

    def tearDown(self):
        self.tmp.cleanup()

    def test_runs_clean_with_calibration_warnings(self):
        rc, out = _capture(_args(158, self.project))
        self.assertEqual(rc, 0)
        self.assertIn("restamp", out)
        self.assertIn("DEMO_WHAT_IT_IS.md", out)
        self.assertIn("✓ promoted", out)
        self.assertIn("⚠ MISSING", out)
        # Verify file got rewritten on disk.
        text = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        self.assertIn("last_revised: 2026-05-15 (SESSION 158)", text)

    def test_dry_run_emits_would_prefix_and_no_writes(self):
        before = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        rc, out = _capture(_args(158, self.project, dry_run=True))
        self.assertEqual(rc, 0)
        self.assertIn("would restamp", out)
        after = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        self.assertEqual(before, after)

    def test_date_override(self):
        rc, _out = _capture(_args(158, self.project, date="2026-12-31"))
        self.assertEqual(rc, 0)
        text = (self.project / "docs" / "DEMO_WHAT_IT_IS.md").read_text(encoding="utf-8")
        self.assertIn("last_revised: 2026-12-31 (SESSION 158)", text)

    def test_bad_date_format(self):
        rc, out = _capture(_args(158, self.project, date="not-a-date"))
        self.assertEqual(rc, 2)
        self.assertIn("YYYY-MM-DD", out)

    def test_missing_handoff(self):
        rc, out = _capture(_args(999, self.project))
        self.assertEqual(rc, 2)
        self.assertIn("no handoff for SESSION 999", out)

    def test_non_integer_session(self):
        rc, out = _capture(_args("foo", self.project))
        self.assertEqual(rc, 2)
        self.assertIn("must be an integer", out)


if __name__ == "__main__":
    unittest.main()
