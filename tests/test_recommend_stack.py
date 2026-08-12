"""Tests for the context-kit `recommend-stack` subcommand.

Tests are written first (per the design discussion's agreement). They
cover the 8 MVP rules, the engine (priority + cap + fallback +
case-insensitivity), output formats, the 4 named scenarios, and seed
integration (Tech stack auto-fill when missing, no-touch when present).
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.bootstrap import run_init  # noqa: E402
from cli.recommend_stack import (  # noqa: E402
    FALLBACK_RECOMMENDATION,
    RULES,
    Rule,
    recommend,
    run_recommend_stack,
)
from cli.seed import run_seed  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rec_args(idea, json_=False):
    return argparse.Namespace(
        command="recommend-stack",
        idea=str(idea),
        json=json_,
    )


def _seed_args(idea, project, force=False, dry_run=False):
    return argparse.Namespace(
        command="seed",
        idea=str(idea),
        project=str(project),
        force=force,
        dry_run=dry_run,
    )


def _capture(args, runner) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = runner(args)
    return rc, buf.getvalue()


def _init_args(name, target):
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=False,
        force=False,
        quiet=True,
    )


def _scaffold(tmpdir: Path, name: str = "Stack App") -> Path:
    project = tmpdir / "stack-app"
    run_init(_init_args(name, project))
    return project


def _rule_by_name(name: str) -> Rule:
    for r in RULES:
        if r.name == name:
            return r
    raise KeyError(f"no rule named {name!r}")


# ---------------------------------------------------------------------------
# Per-rule tests (8 rules × 2 = 16)
# ---------------------------------------------------------------------------


class TestMedicationRemindersRule(unittest.TestCase):
    def test_matches_medication_text(self):
        idea = "## What\n\nApp to remind my dad to take his Parkinson's medication."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "medication-reminders")  # type: ignore

    def test_does_not_match_unrelated_text(self):
        idea = "## What\n\nA dashboard for tracking my landscaping business."
        result = recommend(idea)
        primary_name = result.primary.name if result.primary else None
        self.assertNotEqual(primary_name, "medication-reminders")


class TestMobilePersonalTrackingRule(unittest.TestCase):
    def test_matches_kids_fitness(self):
        idea = "## What\n\nAn app for my kids to track daily fitness habits."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "mobile-personal-tracking")  # type: ignore

    def test_does_not_match_landing_page(self):
        idea = "## What\n\nA landing page for my consulting business."
        result = recommend(idea)
        primary_name = result.primary.name if result.primary else None
        self.assertNotEqual(primary_name, "mobile-personal-tracking")


class TestBusinessDashboardRule(unittest.TestCase):
    def test_matches_inventory_dashboard(self):
        idea = "## What\n\nA dashboard for my business to track inventory and customers."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "business-dashboard")  # type: ignore

    def test_does_not_match_script(self):
        idea = "## What\n\nA Python script to rename my downloaded files."
        result = recommend(idea)
        primary_name = result.primary.name if result.primary else None
        self.assertNotEqual(primary_name, "business-dashboard")


class TestContentWebsiteRule(unittest.TestCase):
    def test_matches_landing_page(self):
        idea = "## What\n\nA landing page for my new SaaS product."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "content-website")  # type: ignore

    def test_does_not_match_medication_app(self):
        idea = "## What\n\nA mobile app to remind users to take their medication."
        result = recommend(idea)
        primary_name = result.primary.name if result.primary else None
        self.assertNotEqual(primary_name, "content-website")


class TestLocalAutomationRule(unittest.TestCase):
    def test_matches_file_organizer(self):
        idea = "## What\n\nA script to rename and organize all my downloaded photos."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "local-automation")  # type: ignore

    def test_does_not_match_business_dashboard(self):
        idea = "## What\n\nA dashboard for my online store sales and customers."
        result = recommend(idea)
        primary_name = result.primary.name if result.primary else None
        self.assertNotEqual(primary_name, "local-automation")


class TestWebApiRule(unittest.TestCase):
    def test_matches_backend_service(self):
        idea = "## What\n\nA backend service exposing a REST API for my mobile app."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "web-api")  # type: ignore

    def test_does_not_match_landing_page(self):
        idea = "## What\n\nA marketing site for my consulting practice."
        result = recommend(idea)
        primary_name = result.primary.name if result.primary else None
        self.assertNotEqual(primary_name, "web-api")


class TestPrivacySensitiveModifier(unittest.TestCase):
    def test_appears_in_also_detected_when_medical_signal_present(self):
        idea = "## What\n\nA medication tracker for personal medical use."
        result = recommend(idea)
        names = [m.rule.name for m in result.also_detected]
        self.assertIn("privacy-sensitive", names)

    def test_does_not_appear_for_landing_page(self):
        idea = "## What\n\nA marketing site for my coffee shop."
        result = recommend(idea)
        names = [m.rule.name for m in result.also_detected]
        self.assertNotIn("privacy-sensitive", names)


class TestSimpleMvpModifier(unittest.TestCase):
    def test_appears_in_also_detected_when_mvp_signal_present(self):
        idea = "## What\n\nJust a simple weekend prototype to track my reading habits."
        result = recommend(idea)
        names = [m.rule.name for m in result.also_detected]
        self.assertIn("simple-mvp", names)

    def test_does_not_appear_when_no_mvp_signal(self):
        idea = "## What\n\nA full-featured medication tracker for chronic illness patients."
        result = recommend(idea)
        names = [m.rule.name for m in result.also_detected]
        self.assertNotIn("simple-mvp", names)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class TestEngineFallback(unittest.TestCase):
    def test_no_matches_returns_fallback(self):
        idea = "## What\n\nQuantum entanglement holiday cards with biodegradable glitter."
        result = recommend(idea)
        self.assertIsNone(result.primary)
        self.assertIs(result.recommendation, FALLBACK_RECOMMENDATION)

    def test_modifier_only_match_uses_fallback_for_recommendation(self):
        # "private" matches privacy-sensitive (modifier) but no primary rule.
        idea = "## What\n\nA private little something."
        result = recommend(idea)
        self.assertIsNone(result.primary)
        self.assertIs(result.recommendation, FALLBACK_RECOMMENDATION)


class TestEnginePriority(unittest.TestCase):
    def test_higher_priority_wins_as_primary(self):
        # medication-reminders (priority 10) should beat business-dashboard (priority 8)
        idea = "## What\n\nA dashboard to manage my medication reminders for the elderly."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "medication-reminders")  # type: ignore

    def test_modifiers_never_win_as_primary(self):
        # privacy-sensitive (priority 5) should not beat web-api (priority 7) when both match
        idea = "## What\n\nA backend API for storing private personal medical journal entries."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertNotIn(
            result.primary.name,  # type: ignore
            ("privacy-sensitive", "simple-mvp"),
        )


class TestEngineCapping(unittest.TestCase):
    def test_also_detected_capped_at_three(self):
        idea = (
            "## What\n\n"
            "A simple private prototype to track my medication, "
            "scripts to rename files, a dashboard to view it all, "
            "with an API for syncing later."
        )
        result = recommend(idea)
        self.assertLessEqual(len(result.also_detected), 3)


class TestEngineMatching(unittest.TestCase):
    def test_case_insensitive(self):
        idea = "## What\n\nA Mobile App That Tracks DAILY Medication Doses."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "medication-reminders")  # type: ignore

    def test_substring_matches_within_word(self):
        # "medications" should still trigger "medication" signal
        idea = "## What\n\nApp to keep track of all medications."
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "medication-reminders")  # type: ignore


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


class TestHumanOutput(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.idea = self.tmpdir / "idea.md"
        self.idea.write_text(
            "# Med Reminder\n\n## What\n\nApp to remind users to take medication.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_includes_all_expected_sections(self):
        rc, out = _capture(_rec_args(self.idea), run_recommend_stack)
        self.assertEqual(rc, 0)
        for header in (
            "Recommended v0 stack",
            "Why this stack fits",
            "What NOT to add yet",
            "Risks",
            "When to upgrade",
        ):
            self.assertIn(header, out, f"missing section: {header}")

    def test_includes_humble_footer(self):
        _, out = _capture(_rec_args(self.idea), run_recommend_stack)
        self.assertIn("opinionated", out.lower())

    def test_no_match_uses_fallback_in_output(self):
        idea = self.tmpdir / "weird.md"
        idea.write_text(
            "# X\n\n## What\n\nQuantum entanglement holiday cards.\n",
            encoding="utf-8",
        )
        rc, out = _capture(_rec_args(idea), run_recommend_stack)
        self.assertEqual(rc, 0)
        self.assertIn("Python CLI", out)


class TestJsonOutput(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.idea = self.tmpdir / "idea.md"
        self.idea.write_text(
            "# Med\n\n## What\n\nMedication reminder app for personal use.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_json_is_valid_and_has_expected_keys(self):
        rc, out = _capture(_rec_args(self.idea, json_=True), run_recommend_stack)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        for key in ("schema_version", "primary", "also_detected", "recommendation"):
            self.assertIn(key, data, f"missing key: {key}")


# ---------------------------------------------------------------------------
# Seed integration
# ---------------------------------------------------------------------------


class TestSeedIntegration(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = _scaffold(self.tmpdir)
        self.idea = self.tmpdir / "idea.md"

    def tearDown(self):
        self._tmp.cleanup()

    def _read_build_plan(self) -> str:
        return (self.project / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")

    def test_tech_stack_present_seed_does_not_auto_suggest(self):
        self.idea.write_text(
            "# X\n\n## What\n\nMedication reminder.\n\n## Tech stack\n\nFlutter, dart.\n",
            encoding="utf-8",
        )
        _capture(_seed_args(self.idea, self.project), run_seed)
        body = self._read_build_plan()
        self.assertIn("Flutter", body)
        # Auto-suggestion marker should NOT appear when user provided their own stack.
        self.assertNotIn("auto-suggested by `context-kit recommend-stack`", body)

    def test_tech_stack_missing_seed_auto_fills_from_recommendation(self):
        self.idea.write_text(
            "# X\n\n## What\n\nApp to remind users to take their daily medication.\n",
            encoding="utf-8",
        )
        _capture(_seed_args(self.idea, self.project), run_seed)
        body = self._read_build_plan()
        self.assertIn("Auto-suggested by `context-kit recommend-stack`", body)
        self.assertIn("Expo", body)  # medication-reminders -> Expo

    def test_tech_stack_missing_no_match_seed_falls_back(self):
        self.idea.write_text(
            "# X\n\n## What\n\nQuantum entanglement holiday cards.\n",
            encoding="utf-8",
        )
        _capture(_seed_args(self.idea, self.project), run_seed)
        body = self._read_build_plan()
        self.assertIn("Auto-suggested by `context-kit recommend-stack`", body)
        self.assertIn("Python CLI", body)


# ---------------------------------------------------------------------------
# Scenario tests (the 4 named in the design)
# ---------------------------------------------------------------------------


class TestScenarios(unittest.TestCase):
    def test_medication_reminder_app(self):
        idea = (
            "# Med Tracker\n\n## What\n\n"
            "An app to help my dad remember to take his Parkinson's medication. "
            "He has tremors so the buttons need to be big. iPhone for now."
        )
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "medication-reminders")  # type: ignore
        # Accessibility focus is present in the recommendation.
        joined = " ".join(result.recommendation.why)
        self.assertTrue(
            "accessibility" in joined.lower() or "tap target" in joined.lower(),
            f"medication-reminders should mention accessibility/tap targets: {joined!r}",
        )

    def test_kids_fitness_app(self):
        idea = (
            "# Kids Fit\n\n## What\n\n"
            "An app for my two kids to track their daily fitness habits — "
            "steps, water, push-ups. Maybe a streak."
        )
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "mobile-personal-tracking")  # type: ignore

    def test_business_dashboard(self):
        idea = (
            "# Landscaping\n\n## What\n\n"
            "A dashboard for my landscaping business to track jobs, customers, "
            "and invoices. I'm the only user for now."
        )
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "business-dashboard")  # type: ignore

    def test_simple_automation_script(self):
        idea = (
            "# Photo Organizer\n\n## What\n\n"
            "A script to rename and organize all my downloaded photos by date taken."
        )
        result = recommend(idea)
        self.assertIsNotNone(result.primary)
        self.assertEqual(result.primary.name, "local-automation")  # type: ignore


# ---------------------------------------------------------------------------
# Tone — practical not scary on medical/privacy
# ---------------------------------------------------------------------------


class TestToneOnPrivacyLanguage(unittest.TestCase):
    def test_medication_recommendation_uses_practical_privacy_framing(self):
        rule = _rule_by_name("medication-reminders")
        joined = " ".join(rule.recommendation.risks)
        # The agreed practical framing must appear (not scary).
        self.assertIn("personal local-only", joined.lower())
        self.assertIn("talk to a lawyer", joined.lower())


if __name__ == "__main__":
    unittest.main()
