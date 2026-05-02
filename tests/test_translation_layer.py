"""Tests for the TRANSLATION_LAYER.md scaffold + orient/doctor wiring.

Mirrors ``test_behavior_layer.py``'s shape:

* ``bootstrap`` creates the doc with required sections, generic
  personas, translation modes, truth-preservation language, and a
  same-truth-different-explanation example.
* ``orient`` includes the doc when present and silently omits it
  when absent.
* ``orient --short`` references the doc by filename without dumping
  full content.
* Discovery follows precedence: suffixed > plain > root.
* Discovery does not collide with PIPELINE.md / BEHAVIOR_LAYER.md.
* ``doctor`` warns when stakeholder / multi-audience indicators
  exist and the doc is missing, OK when present, skipped on
  trivial repos. Warnings never raise the exit code.
* The pattern README lists the new template.
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
from cli.doctor import (  # noqa: E402
    _exit_code,
    _has_translation_layer_doc,
    _project_has_translation_indicators,
    check_translation_layer_doc,
    run_all_checks,
)
from cli.orient import (  # noqa: E402
    _find_behavior_layer_doc,
    _find_pipeline_doc,
    _find_translation_layer_doc,
    run_orient,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    return argparse.Namespace(
        command="orient",
        project=str(project),
        short=short,
    )


def _run_orient(project: Path, *, short: bool = False) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_orient(_orient_args(project, short=short))
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# Bootstrap creates TRANSLATION_LAYER.md with the load-bearing sections
# ---------------------------------------------------------------------------


class TestBootstrapCreatesTranslationLayerDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "translation-app"
        run_init(_init_args("Translation App", self.project))
        self.doc_path = self.project / "docs" / "TRANSLATION_APP_TRANSLATION_LAYER.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_doc_is_scaffolded(self):
        self.assertTrue(self.doc_path.is_file())

    def test_required_headings_exist(self):
        text = self.doc_path.read_text(encoding="utf-8")
        for heading in (
            "## Purpose",
            "## Source of Truth Inputs",
            "## Personas / Audiences",
            "## Translation Modes",
            "## Truth Preservation Rules",
            "## Live Chat Mode",
            "## Example: Same Truth, Different Explanation",
            "## What Each Person Needs Next",
            "## Last Verified",
        ):
            self.assertIn(heading, text, f"missing heading: {heading}")

    def test_core_rule_phrasing_exists(self):
        text = self.doc_path.read_text(encoding="utf-8")
        # The load-bearing rule must appear verbatim — agents grep
        # for this phrase to confirm the contract.
        self.assertIn(
            "Same truth \u2192 different explanation layer \u2192 zero distortion.",
            text,
        )

    def test_truth_preservation_language_exists(self):
        text = self.doc_path.read_text(encoding="utf-8")
        # The "may reframe / must not invent" pair is the contract.
        # Both halves must be present, not just one. Tolerate
        # markdown formatting (bold/italics) between the words by
        # asserting the structural words separately.
        lowered = text.lower()
        self.assertIn("reframe", lowered)
        # Allow markdown bold/italic between the contract phrases:
        # "**may** reframe" and "**must not** invent" both need to
        # match without false-rejecting on "**".
        import re as _re
        self.assertRegex(lowered, _re.compile(r"may[^a-z\n]{1,80}reframe"))
        self.assertRegex(lowered, _re.compile(r"must not[^a-z\n]{1,80}invent"))
        # The explicit list of what cannot be invented:
        for forbidden in (
            "progress",
            "test results",
            "business impact",
            "features",
            "customer value",
            "decisions",
        ):
            self.assertIn(forbidden, text.lower(),
                          f"truth-preservation list missing: {forbidden}")

    def test_generic_personas_exist(self):
        text = self.doc_path.read_text(encoding="utf-8").lower()
        # The four generic personas must appear so users see real
        # starting points, not abstract slots.
        self.assertIn("builder", text)
        self.assertIn("operator", text)
        self.assertIn("executive", text)
        self.assertIn("tester", text)

    def test_translation_modes_exist(self):
        text = self.doc_path.read_text(encoding="utf-8").lower()
        for mode in (
            "technical summary",
            "business impact",
            "executive brief",
            "qa",
            "what should this person do next",
        ):
            self.assertIn(mode, text, f"translation mode missing: {mode}")

    def test_same_truth_example_exists(self):
        text = self.doc_path.read_text(encoding="utf-8")
        # The example must demonstrate the same fact rendered for
        # multiple audiences. Look for the audience labels in the
        # example body.
        self.assertIn("## Example: Same Truth, Different Explanation", text)
        # The example uses concrete persona translations — at least
        # three of the four must be present in the example body.
        example_idx = text.index("## Example: Same Truth, Different Explanation")
        next_h2 = text.find("\n## ", example_idx + 1)
        example_body = text[example_idx:next_h2 if next_h2 != -1 else None].lower()
        for persona in ("builder", "operator", "executive", "tester"):
            self.assertIn(persona, example_body,
                          f"example missing translation for: {persona}")


# ---------------------------------------------------------------------------
# Orient discovery + section
# ---------------------------------------------------------------------------


class TestOrientIncludesTranslationLayer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "tl-app"
        run_init(_init_args("TL App", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_discovery_finds_scaffolded_doc(self):
        path = _find_translation_layer_doc(self.project)
        self.assertIsNotNone(path)
        self.assertEqual(path.name, "TL_APP_TRANSLATION_LAYER.md")

    def test_orient_includes_translation_layer_section(self):
        _, out = _run_orient(self.project)
        self.assertIn("## TRANSLATION LAYER", out)
        self.assertIn("TL_APP_TRANSLATION_LAYER.md", out)

    def test_source_of_truth_lists_translation_layer_at_5(self):
        _, out = _run_orient(self.project)
        # Position 5 in source-of-truth (after BEHAVIOR_LAYER, before
        # DO_NOTS). The numbering renumbers DO_NOTS to 6 and the
        # handoff line to 7.
        self.assertIn("## SOURCE OF TRUTH", out)
        # Look for the "5." line and verify it's the translation layer.
        sot_block = out.split("## SOURCE OF TRUTH", 1)[1].split("\n\n", 1)[0]
        line5 = next(
            (ln for ln in sot_block.splitlines() if ln.strip().startswith("5.")),
            "",
        )
        self.assertIn("TRANSLATION_LAYER", line5)

    def test_orient_renumbers_do_nots_to_6_and_handoff_to_7(self):
        # Make sure ordering wasn't broken — DO_NOTS is now 6, the
        # handoff/start line is 7. The strict "wins on conflict"
        # framing for inventory should still print on a normal repo.
        _, out = _run_orient(self.project)
        sot_block = out.split("## SOURCE OF TRUTH", 1)[1].split("\n\n", 1)[0]
        lines = [ln for ln in sot_block.splitlines() if ln.strip().startswith(("5.", "6.", "7."))]
        self.assertEqual(len(lines), 3, f"expected 3 numbered lines 5/6/7, got: {lines}")
        self.assertIn("TRANSLATION_LAYER", lines[0])
        self.assertIn("DO_NOTS", lines[1])
        self.assertIn("handoff", lines[2].lower())


class TestOrientGracefullyOmitsWhenAbsent(unittest.TestCase):
    """Older projects without the new template must still get a clean
    orient report — section silently omitted, no (missing) line."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "no-tl"
        run_init(_init_args("No TL", self.project))
        # Delete the scaffolded translation layer so we simulate an
        # older project predating this template.
        path = _find_translation_layer_doc(self.project)
        self.assertIsNotNone(path)
        path.unlink()

    def tearDown(self):
        self._tmp.cleanup()

    def test_orient_does_not_emit_translation_layer_section(self):
        _, out = _run_orient(self.project)
        self.assertNotIn("## TRANSLATION LAYER", out)

    def test_source_of_truth_still_lists_position_5_as_optional(self):
        # When the doc is absent, the source-of-truth ordering still
        # advertises position 5 — but as an optional placeholder, not
        # a discovered file.
        _, out = _run_orient(self.project)
        sot_block = out.split("## SOURCE OF TRUTH", 1)[1].split("\n\n", 1)[0]
        line5 = next(
            (ln for ln in sot_block.splitlines() if ln.strip().startswith("5.")),
            "",
        )
        self.assertIn("TRANSLATION_LAYER", line5)
        self.assertIn("optional", line5.lower())


# ---------------------------------------------------------------------------
# orient --short references doc by filename, not body
# ---------------------------------------------------------------------------


class TestOrientShortReferencesTranslationLayer(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "tl-short"
        run_init(_init_args("TL Short", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_short_emits_filename(self):
        _, out = _run_orient(self.project, short=True)
        self.assertIn("## TRANSLATION LAYER", out)
        self.assertIn("TL_SHORT_TRANSLATION_LAYER.md", out)

    def test_short_does_not_dump_full_content(self):
        _, out = _run_orient(self.project, short=True)
        # The full doc has these section headers; --short must NOT
        # include them (otherwise it's no longer short).
        self.assertNotIn("## Truth Preservation Rules", out)
        self.assertNotIn("## Example: Same Truth, Different Explanation", out)
        self.assertNotIn("## Personas / Audiences", out)

    def test_short_omits_section_when_doc_absent(self):
        # Older project: no template. Short report must not print
        # "## TRANSLATION LAYER" at all.
        path = _find_translation_layer_doc(self.project)
        self.assertIsNotNone(path)
        path.unlink()
        _, out = _run_orient(self.project, short=True)
        self.assertNotIn("## TRANSLATION LAYER", out)


# ---------------------------------------------------------------------------
# Discovery precedence
# ---------------------------------------------------------------------------


class TestDiscoveryPrecedence(unittest.TestCase):
    """Order: suffixed (docs/<APP>_TRANSLATION_LAYER.md) > plain
    (docs/TRANSLATION_LAYER.md) > root (TRANSLATION_LAYER.md)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "p"
        self.project.mkdir()
        (self.project / "docs").mkdir()
        # Minimal "looks like a CK project" — start-here doc only.
        (self.project / "00-START-NEXT-SESSION.md").write_text("# Start\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_root_only(self):
        path = self.project / "TRANSLATION_LAYER.md"
        path.write_text("# Root\n")
        self.assertEqual(_find_translation_layer_doc(self.project), path)

    def test_plain_docs_wins_over_root(self):
        plain = self.project / "docs" / "TRANSLATION_LAYER.md"
        plain.write_text("# Plain\n")
        root = self.project / "TRANSLATION_LAYER.md"
        root.write_text("# Root\n")
        self.assertEqual(_find_translation_layer_doc(self.project), plain)

    def test_suffixed_wins_over_plain(self):
        suffixed = self.project / "docs" / "MYAPP_TRANSLATION_LAYER.md"
        suffixed.write_text("# Suffixed\n")
        plain = self.project / "docs" / "TRANSLATION_LAYER.md"
        plain.write_text("# Plain\n")
        self.assertEqual(_find_translation_layer_doc(self.project), suffixed)


class TestDoesNotCollideWithPipelineOrBehaviorLayer(unittest.TestCase):
    """The translation-layer glob must not match PIPELINE / BEHAVIOR_LAYER
    files, and vice versa."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "p"
        self.project.mkdir()
        (self.project / "docs").mkdir()
        (self.project / "00-START-NEXT-SESSION.md").write_text("# Start\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_pipeline_doc_does_not_match_translation_layer(self):
        # PIPELINE.md present, no translation layer file.
        (self.project / "docs" / "MYAPP_PIPELINE.md").write_text("# pipeline\n")
        self.assertIsNone(_find_translation_layer_doc(self.project))

    def test_behavior_layer_doc_does_not_match_translation_layer(self):
        (self.project / "docs" / "MYAPP_BEHAVIOR_LAYER.md").write_text("# bl\n")
        self.assertIsNone(_find_translation_layer_doc(self.project))

    def test_translation_layer_doc_does_not_match_pipeline_or_behavior(self):
        (self.project / "docs" / "MYAPP_TRANSLATION_LAYER.md").write_text("# tl\n")
        self.assertIsNone(_find_pipeline_doc(self.project))
        self.assertIsNone(_find_behavior_layer_doc(self.project))


# ---------------------------------------------------------------------------
# Doctor: check_translation_layer_doc
# ---------------------------------------------------------------------------


class TestDoctorWarning(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ok_when_doc_is_present(self):
        project = self.tmpdir / "ok"
        run_init(_init_args("OK", project))
        # The init scaffold creates the translation layer doc by
        # default → check should be ok.
        result = check_translation_layer_doc(project)
        self.assertEqual(result.status, "ok")

    def test_skipped_for_trivial_repo(self):
        # A bare repo with nothing but a README is not multi-audience.
        project = self.tmpdir / "trivial"
        project.mkdir()
        (project / "README.md").write_text("# trivial\n")
        result = check_translation_layer_doc(project)
        self.assertEqual(result.status, "skipped")

    def test_warns_when_indicators_present_and_doc_missing(self):
        # Multi-audience signals: filenames containing two distinct
        # role tokens. Doc absent → warning.
        project = self.tmpdir / "stakeholder-app"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "STAKEHOLDER_NOTES.md").write_text("# s\n")
        (project / "docs" / "EXECUTIVE_BRIEF.md").write_text("# e\n")
        (project / "docs" / "TESTER_CHECKLIST.md").write_text("# t\n")
        result = check_translation_layer_doc(project)
        self.assertEqual(result.status, "warning")
        self.assertIn("TRANSLATION_LAYER", result.detail)
        self.assertTrue(result.fix)

    def test_warns_when_behavior_layer_plus_many_handoffs_and_doc_missing(self):
        # Trigger #2: 3+ handoffs + a BEHAVIOR_LAYER doc → multi-session
        # product with persona-bearing output. Doc absent → warning.
        project = self.tmpdir / "ll"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "BEHAVIOR_LAYER.md").write_text("# bl\n")
        (project / "docs" / "handoffs").mkdir()
        for n in (1, 2, 3, 4):
            (project / "docs" / "handoffs" / f"SESSION_{n:03d}_FOO.md").write_text(f"# s{n}\n")
        result = check_translation_layer_doc(project)
        self.assertEqual(result.status, "warning")

    def test_warning_is_never_blocking(self):
        # Trigger the warning AND nothing else; doctor exit code must
        # stay 0.
        project = self.tmpdir / "noisy"
        project.mkdir()
        (project / "docs").mkdir()
        (project / "docs" / "STAKEHOLDER_NOTES.md").write_text("# s\n")
        (project / "docs" / "PERSONA_GUIDE.md").write_text("# p\n")
        results = run_all_checks(project)
        rc = _exit_code(results)
        # Find the translation-layer result; warn but never block.
        tl_results = [r for r in results if r.id == "translation_layer_doc"]
        self.assertEqual(len(tl_results), 1)
        self.assertEqual(tl_results[0].status, "warning")
        self.assertEqual(rc, 0)


class TestIndicatorHelpers(unittest.TestCase):
    """Direct coverage of the indicator helper so the threshold logic
    is testable without spinning up a doctor run for every shape."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_single_role_token_does_not_trigger(self):
        # One token alone is not enough — that's a generic README
        # mention, not a multi-audience signal.
        project = self.tmpdir / "p"
        project.mkdir()
        (project / "STAKEHOLDER.md").write_text("# s\n")
        triggered, _ = _project_has_translation_indicators(project)
        self.assertFalse(triggered)

    def test_two_distinct_tokens_trigger(self):
        project = self.tmpdir / "p"
        project.mkdir()
        (project / "STAKEHOLDER.md").write_text("# s\n")
        (project / "EXECUTIVE.md").write_text("# e\n")
        triggered, reasons = _project_has_translation_indicators(project)
        self.assertTrue(triggered)
        self.assertTrue(reasons)

    def test_two_handoffs_alone_do_not_trigger(self):
        # Below the handoff threshold (3+); should not fire on its own.
        project = self.tmpdir / "p"
        project.mkdir()
        (project / "docs" / "handoffs").mkdir(parents=True)
        for n in (1, 2):
            (project / "docs" / "handoffs" / f"SESSION_{n:03d}_FOO.md").write_text("# s\n")
        triggered, _ = _project_has_translation_indicators(project)
        self.assertFalse(triggered)


# ---------------------------------------------------------------------------
# Pattern README lists the new template
# ---------------------------------------------------------------------------


class TestPatternReadmeListsTemplate(unittest.TestCase):
    """The pattern README is the discovery surface for the template
    files. The new translation-layer template must be listed there
    (and ship to generated projects via the docs-pattern materialization)."""

    def test_pattern_readme_mentions_translation_layer_template(self):
        readme = REPO_ROOT / "cli" / "_pattern" / "README.md"
        text = readme.read_text(encoding="utf-8")
        self.assertIn("PLATFORM_TRANSLATION_LAYER.template.md", text)

    def test_template_file_exists_in_source(self):
        template = REPO_ROOT / "cli" / "_pattern" / "templates" / "PLATFORM_TRANSLATION_LAYER.template.md"
        self.assertTrue(template.is_file())


# ---------------------------------------------------------------------------
# has_doc helper symmetry — doctor and orient discovery agree
# ---------------------------------------------------------------------------


class TestDoctorAndOrientAgreeOnDiscovery(unittest.TestCase):
    """Doctor inlines the discovery rule (to avoid importing orient).
    The two implementations must agree on every shape so a doc that
    orient finds is also a doc doctor reports as present."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "p"
        self.project.mkdir()
        (self.project / "docs").mkdir()
        (self.project / "00-START-NEXT-SESSION.md").write_text("# Start\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_root_doc(self):
        (self.project / "TRANSLATION_LAYER.md").write_text("# r\n")
        self.assertIsNotNone(_find_translation_layer_doc(self.project))
        self.assertTrue(_has_translation_layer_doc(self.project))

    def test_plain_docs_doc(self):
        (self.project / "docs" / "TRANSLATION_LAYER.md").write_text("# p\n")
        self.assertIsNotNone(_find_translation_layer_doc(self.project))
        self.assertTrue(_has_translation_layer_doc(self.project))

    def test_suffixed_doc(self):
        (self.project / "docs" / "APP_TRANSLATION_LAYER.md").write_text("# s\n")
        self.assertIsNotNone(_find_translation_layer_doc(self.project))
        self.assertTrue(_has_translation_layer_doc(self.project))

    def test_no_doc(self):
        self.assertIsNone(_find_translation_layer_doc(self.project))
        self.assertFalse(_has_translation_layer_doc(self.project))


# ---------------------------------------------------------------------------
# `context-kit translation-init` static-prompt command
# ---------------------------------------------------------------------------


from cli.translation_init import (  # noqa: E402
    TRANSLATION_INIT_PROMPT,
    run_translation_init,
)


class TestTranslationInitCommand(unittest.TestCase):
    """`translation-init` is a static-prompt printer (same shape as
    ``audit``). It must:
    - exit 0
    - print a non-empty prompt to stdout
    - never mutate files
    - cover the five steps the AI is supposed to follow
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_command(self) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_translation_init(argparse.Namespace(command="translation-init"))
        return rc, buf.getvalue()

    def test_returns_zero(self):
        rc, _ = self._run_command()
        self.assertEqual(rc, 0)

    def test_prints_non_empty_prompt(self):
        _, out = self._run_command()
        self.assertGreater(len(out.strip()), 200)

    def test_prompt_module_constant_matches_output(self):
        _, out = self._run_command()
        # The module exports the prompt as a constant for re-use by
        # downstream tools / docs. The CLI must print it verbatim.
        self.assertIn(TRANSLATION_INIT_PROMPT.strip(), out)

    def test_prompt_includes_all_five_steps(self):
        _, out = self._run_command()
        self.assertIn("Step 1 — Read source-of-truth", out)
        self.assertIn("Step 2 — Interview the user", out)
        self.assertIn("Step 3 — Write the populated doc", out)
        self.assertIn("Step 4 — Verify zero invention", out)
        self.assertIn("Step 5 — Confirm and switch persona", out)

    def test_prompt_carries_load_bearing_rules(self):
        _, out = self._run_command()
        # Core rule must appear so the AI can't lose it across the
        # five-step recipe.
        self.assertIn("same truth \u2192 different explanation", out.lower())
        # The refusal clause must appear (added in the safety pass).
        self.assertIn("refuse or fall back to a neutral", out.lower())
        # The "do not overwrite hand-edited" guard must appear.
        self.assertIn("do **not** overwrite", out)

    def test_prompt_lists_required_headings_to_preserve(self):
        _, out = self._run_command()
        # The doc has 9 required headings (Live Chat Mode added in
        # the chat-mode pass); the recipe must name each so the AI
        # doesn't drop any when populating.
        for heading in (
            "## Purpose",
            "## Source of Truth Inputs",
            "## Personas / Audiences",
            "## Translation Modes",
            "## Truth Preservation Rules",
            "## Live Chat Mode",
            "## Example: Same Truth, Different Explanation",
            "## What Each Person Needs Next",
            "## Last Verified",
        ):
            self.assertIn(heading, out)

    def test_prompt_names_concrete_invention_categories(self):
        _, out = self._run_command()
        # The "watch for these" list — verifies Step 4 is specific
        # enough to be actionable.
        for category in (
            "Invented progress",
            "Invented business impact",
            "Invented customer value",
            "Invented decisions",
        ):
            self.assertIn(category, out)

    def test_prompt_instructs_persona_switch_at_end(self):
        _, out = self._run_command()
        self.assertIn(
            "Which persona should I operate as for the rest of this",
            out,
        )

    def test_command_does_not_mutate_files(self):
        # Drop a fake project tree and confirm no files appear / change.
        project = self.tmpdir / "p"
        project.mkdir()
        (project / "00-START-NEXT-SESSION.md").write_text("# Start\n")
        before = {
            p.relative_to(project): p.stat().st_mtime_ns
            for p in project.rglob("*") if p.is_file()
        }
        # Run from inside the project dir; command is read-only.
        cwd = Path.cwd()
        try:
            import os
            os.chdir(project)
            self._run_command()
        finally:
            os.chdir(cwd)
        after = {
            p.relative_to(project): p.stat().st_mtime_ns
            for p in project.rglob("*") if p.is_file()
        }
        self.assertEqual(before, after)


class TestTranslationInitInParser(unittest.TestCase):
    """The command must be registered on the top-level parser so
    ``python3 context_kit.py translation-init`` dispatches correctly."""

    def test_parser_registers_command(self):
        from context_kit import build_parser  # noqa: E402
        parser = build_parser()
        # Walk the subparsers to confirm registration.
        subparsers_action = next(
            (a for a in parser._actions
             if isinstance(a, argparse._SubParsersAction)),
            None,
        )
        self.assertIsNotNone(subparsers_action)
        self.assertIn("translation-init", subparsers_action.choices)

    def test_help_describes_population_workflow(self):
        from context_kit import build_parser  # noqa: E402
        parser = build_parser()
        subparsers_action = next(
            a for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)
        )
        sub = subparsers_action.choices["translation-init"]
        # Description must convey "populate the doc / interview the
        # user / read-only" so users find it from --help.
        desc = (sub.description or "").lower()
        self.assertIn("populated", desc)
        self.assertIn("interview", desc)
        self.assertIn("read-only", desc)


# ---------------------------------------------------------------------------
# Live Chat Mode — the runtime contract for non-technical personas
# ---------------------------------------------------------------------------


class TestScaffoldHasLiveChatMode(unittest.TestCase):
    """The scaffolded TRANSLATION_LAYER doc must include a Live Chat
    Mode section so non-technical personas (Jessica, an executive,
    etc.) get a real runtime contract — not just artifact-translation
    rules. Without this, the assistant might still slip into jargon
    mid-conversation because the doc only governs written output."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "chat-app"
        run_init(_init_args("Chat App", self.project))
        self.doc_path = self.project / "docs" / "CHAT_APP_TRANSLATION_LAYER.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_scaffold_has_live_chat_mode_heading(self):
        text = self.doc_path.read_text(encoding="utf-8")
        self.assertIn("## Live Chat Mode", text)

    def test_scaffold_explains_chat_vs_doc_distinction(self):
        text = self.doc_path.read_text(encoding="utf-8")
        # Anchor: the section must explicitly position itself as
        # *stricter than* the artifact-translation rules above.
        self.assertIn("Stricter contract", text) if False else self.assertRegex(
            text.lower(), r"stricter contract|stricter contract than doc translation",
        )

    def test_scaffold_has_trigger_section(self):
        text = self.doc_path.read_text(encoding="utf-8")
        self.assertIn("### Trigger", text)
        # Default trigger phrase must be present so users see the
        # convention.
        self.assertIn('"Hi, I\'m', text)

    def test_scaffold_has_universal_rules(self):
        text = self.doc_path.read_text(encoding="utf-8")
        self.assertIn("### Universal rules", text)
        self.assertIn("Refusal rule", text)
        # Refusal example phrasing — the literal sentence the
        # assistant should fall back to. Must appear so the AI can
        # cite it verbatim instead of paraphrasing.
        self.assertIn(
            "I can't answer that cleanly without using technical words",
            text,
        )

    def test_scaffold_has_per_persona_contracts_section(self):
        text = self.doc_path.read_text(encoding="utf-8")
        self.assertIn("### Per-persona contracts", text)
        # Skippable for technical personas — the section must
        # explicitly say so so populators don't write empty blocks.
        self.assertIn("Skip silently for technical", text)

    def test_scaffold_has_substitutions_table(self):
        text = self.doc_path.read_text(encoding="utf-8")
        # The substitutions table is the load-bearing example —
        # without it, an AI populating real personas has nothing
        # to model the Markdown shape on.
        self.assertIn("| Avoid | Use instead |", text)
        # Minimum coverage of the most common jargon words.
        for token in ("backend", "frontend", "commit", "deploy", "migration"):
            self.assertIn(token, text.lower())

    def test_scaffold_has_grounding_rule(self):
        text = self.doc_path.read_text(encoding="utf-8")
        # Chat mode changes vocabulary; it must NOT change facts.
        # The section must restate this rule so a populator doesn't
        # accidentally drop the truth-preservation contract when
        # writing chat-mode blocks.
        self.assertIn("**Grounding**", text)
        self.assertIn("trace to source-of-truth", text)


class TestPatternTemplateHasLiveChatMode(unittest.TestCase):
    """The compact pattern template under cli/_pattern/templates/
    must mirror the scaffold so adopters who copy the template
    instead of running init still get the chat-mode contract."""

    def test_template_has_live_chat_mode_heading(self):
        template = REPO_ROOT / "cli" / "_pattern" / "templates" / "PLATFORM_TRANSLATION_LAYER.template.md"
        text = template.read_text(encoding="utf-8")
        self.assertIn("## Live Chat Mode", text)

    def test_template_has_refusal_rule(self):
        template = REPO_ROOT / "cli" / "_pattern" / "templates" / "PLATFORM_TRANSLATION_LAYER.template.md"
        text = template.read_text(encoding="utf-8")
        self.assertIn(
            "I can't answer that cleanly without using technical words",
            text,
        )

    def test_template_has_substitutions_table(self):
        template = REPO_ROOT / "cli" / "_pattern" / "templates" / "PLATFORM_TRANSLATION_LAYER.template.md"
        text = template.read_text(encoding="utf-8")
        self.assertIn("| Avoid | Use instead |", text)


class TestTranslationInitRecipeCoversChatMode(unittest.TestCase):
    """The translation-init recipe must teach the AI to interview
    the user about non-technical personas, write a chat-mode block
    for each, and flip into chat mode when the user picks one."""

    def _run_command(self) -> str:
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_translation_init(argparse.Namespace(command="translation-init"))
        return buf.getvalue()

    def test_recipe_asks_about_non_technical_personas(self):
        out = self._run_command()
        # Step 2 Q6 must exist and explicitly call out non-technical
        # personas. "Live chat mode" is the section title; "non-
        # technical" is the threshold.
        self.assertIn("Live chat mode", out)
        self.assertIn("non-technical", out.lower())

    def test_recipe_asks_for_substitutions(self):
        out = self._run_command()
        # The interview must collect both prohibited words and their
        # substitutions, otherwise the populator can't write a real
        # Avoid/Use-instead table.
        self.assertIn("never say", out.lower())
        # Substitution example pattern: 'backend → "the system"'
        self.assertIn("'the system'", out)

    def test_recipe_asks_for_trigger_phrase(self):
        out = self._run_command()
        # Trigger phrase question — must mention the default.
        self.assertIn("trigger phrase", out.lower())
        self.assertIn("Hi, I'm", out)

    def test_recipe_instructs_writing_chat_mode_section(self):
        out = self._run_command()
        # Step 3 must point at the Live Chat Mode body and tell the
        # AI to write per-persona blocks for non-technical personas
        # and skip technical ones silently. The skip-technical
        # phrase may wrap across lines or carry markdown bold —
        # match across whitespace.
        self.assertIn("`## Live Chat Mode`", out)
        import re as _re
        self.assertRegex(
            out, _re.compile(r"Skip technical personas\s+silently", _re.IGNORECASE),
        )

    def test_recipe_instructs_flipping_into_chat_mode_on_persona_pick(self):
        out = self._run_command()
        # Step 5 must teach the AI to flip into chat mode when the
        # chosen persona has a chat-mode block, vs. just operating
        # in their translation mode otherwise.
        self.assertIn("flip into live chat mode", out)
        self.assertIn("If the chosen persona has no chat-mode block", out)

    def test_recipe_preserves_universal_rules(self):
        out = self._run_command()
        # The recipe must not let the AI re-write the universal
        # rules; they're load-bearing and must come through verbatim.
        self.assertIn("Preserve the universal rules", out)


class TestSkillTeachesChatModeFlip(unittest.TestCase):
    """The bundled skill is what Claude reads on session start.
    Without an explicit chat-mode flip rule there, an AI loaded
    from the skill won't know to honor the contract when a persona
    is named — the doc-level contract is meaningless if the agent
    never reads it as a runtime instruction."""

    def setUp(self):
        self.skill = REPO_ROOT / "cli" / "_skills" / "context-kit" / "SKILL.md"
        self.text = self.skill.read_text(encoding="utf-8")

    def test_skill_has_live_chat_mode_section(self):
        self.assertIn("## Live chat mode for non-technical personas", self.text)

    def test_skill_explains_activation_triggers(self):
        # The agent must know how to recognize activation:
        # "Hi, I'm <persona>" or "operate as <persona>".
        self.assertIn('"Hi, I\'m Jessica"', self.text)
        self.assertIn('"operate as <persona>"', self.text)

    def test_skill_lists_runtime_obligations(self):
        # When active, the agent has 5 obligations (prohibitions,
        # substitutions, refusal rule, restate persona, stay in
        # character). All must be named so a fresh agent can't miss
        # one.
        for obligation in (
            "Honor every prohibition",
            "Apply every substitution",
            "Use the refusal rule",
            "Restate the active persona",
            "Stay in character",
        ):
            self.assertIn(obligation, self.text)

    def test_skill_preserves_truth_rule_in_chat_mode(self):
        # Chat mode changes vocabulary, never facts. Must be
        # explicit in the skill so an agent doesn't think
        # "plain language" gives them license to soften / invent.
        self.assertIn("Truth Preservation Rules still apply", self.text)
        self.assertIn("Chat mode changes\nvocabulary and format, never facts", self.text)

    def test_skill_handles_technical_personas(self):
        # Builders / engineers don't need the flip — the skill
        # must say so explicitly so the agent doesn't refuse to
        # use code blocks when Chris asks a code question. The
        # "no chat-mode block" phrase appears with markdown italics
        # around "no" and may wrap across lines.
        import re as _re
        self.assertRegex(
            self.text,
            _re.compile(r"no\*?\s+chat-mode block", _re.IGNORECASE),
        )


if __name__ == "__main__":
    unittest.main()
