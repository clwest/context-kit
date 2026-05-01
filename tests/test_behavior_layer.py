"""Tests for the BEHAVIOR_LAYER.md scaffold + orient/doctor wiring.

Mirrors ``test_pipeline.py``'s shape: bootstrap creates the doc,
``orient`` includes it when present and gracefully omits it when
absent, ``doctor`` warns when indicators are present but the doc is
missing.

Doc-content tests verify that the scaffolded BEHAVIOR_LAYER.md
contains the load-bearing sections this feature was added for:
voice/tone, UI source-of-truth contract, constraint preservation,
decision authority, GOOD/BAD examples, and small-model guidance.
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
    _has_behavior_layer_doc,
    _project_has_behavior_indicators,
    check_behavior_layer_doc,
)
from cli.orient import (  # noqa: E402
    _find_behavior_layer_doc,
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


def _orient_args(project):
    return argparse.Namespace(command="orient", project=str(project))


def _run_orient(project: Path) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_orient(_orient_args(project))
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# Bootstrap creates BEHAVIOR_LAYER.md
# ---------------------------------------------------------------------------


class TestBootstrapCreatesBehaviorLayerDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "behavior-app"
        run_init(_init_args("Behavior App", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_behavior_layer_doc_exists(self):
        path = self.project / "docs" / "BEHAVIOR_APP_BEHAVIOR_LAYER.md"
        self.assertTrue(
            path.is_file(),
            f"expected scaffolded behavior-layer doc at {path}",
        )

    def test_behavior_layer_doc_substitutes_placeholders(self):
        path = self.project / "docs" / "BEHAVIOR_APP_BEHAVIOR_LAYER.md"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("{{APP_TITLE}}", text)
        self.assertNotIn("{{APP_UPPER}}", text)
        self.assertIn("Behavior App", text)


# ---------------------------------------------------------------------------
# Required content sections (template-content tests)
# ---------------------------------------------------------------------------


class TestBehaviorLayerRequiredSections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = Path(cls._tmp.name) / "content-app"
        run_init(_init_args("Content App", cls.project))
        cls.text = (
            cls.project / "docs" / "CONTENT_APP_BEHAVIOR_LAYER.md"
        ).read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_has_voice_and_tone_section(self):
        self.assertIn("## Voice / Tone Contract", self.text)
        # Persona / required / forbidden phrasing structure must be present.
        self.assertIn("Persona", self.text)
        self.assertIn("Required phrasings", self.text)
        self.assertIn("Forbidden phrasings", self.text)

    def test_has_ui_source_of_truth_section(self):
        self.assertIn("## UI / Source-of-Truth Contract", self.text)
        # The "do not repeat rendered data in prose" rule must be there
        # as a load-bearing rule the docs were created for.
        block = self.text.split(
            "## UI / Source-of-Truth Contract", 1
        )[1].split("\n## ", 1)[0]
        self.assertIn("do not repeat rendered data in prose", block.lower())
        # Authoritative-surface table must exist (LLM may / must not).
        self.assertIn("LLM may", block)
        self.assertIn("LLM must not", block)

    def test_has_constraint_preservation_section(self):
        self.assertIn("## Constraint Preservation Across Turns", self.text)
        block = self.text.split(
            "## Constraint Preservation Across Turns", 1
        )[1].split("\n## ", 1)[0]
        # The structured-state-vs-conversation-history rule.
        self.assertIn("structured state", block.lower())
        self.assertIn("conversation history", block.lower())

    def test_has_decision_authority_section(self):
        self.assertIn("## Decision Authority Boundary", self.text)
        block = self.text.split(
            "## Decision Authority Boundary", 1
        )[1].split("\n## ", 1)[0]
        # Forbidden / allowed contract must be explicit.
        for forbidden in ("pricing", "eligibility", "commitments"):
            self.assertIn(forbidden, block)
        for allowed in ("explain", "guide", "rephrase"):
            self.assertIn(allowed, block)

    def test_has_good_bad_examples_section(self):
        self.assertIn("GOOD / BAD Examples", self.text)
        # Concrete GOOD/BAD pairs must appear (we use ✅ / ❌ markers
        # plus the literal words).
        examples_block = self.text.split(
            "GOOD / BAD Examples", 1
        )[1].split("\n## ", 1)[0]
        self.assertIn("✅", examples_block)
        self.assertIn("❌", examples_block)
        # The doc must include all four representative rules from the
        # template (constraint, restate, decision authority, persona).
        self.assertIn("respect prior constraints", examples_block)
        self.assertIn("do not restate rendered data", examples_block)
        self.assertIn("decision authority", examples_block.lower())
        self.assertIn("persona", examples_block.lower())

    def test_has_small_model_guidance(self):
        self.assertIn("## Small-Model Behavior Note", self.text)
        block = self.text.split(
            "## Small-Model Behavior Note", 1
        )[1].split("\n## ", 1)[0]
        # The two key guidance items: negative directives are weak,
        # post-generation checks are required for load-bearing rules.
        self.assertIn("Negative directives", block)
        self.assertIn("post-generation check", block)

    def test_has_last_verified(self):
        self.assertIn("## Last Verified", self.text)


# ---------------------------------------------------------------------------
# Orient includes BEHAVIOR_LAYER when present
# ---------------------------------------------------------------------------


class TestOrientIncludesBehaviorLayerWhenPresent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "with-behavior"
        run_init(_init_args("With Behavior", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_orient_emits_behavior_layer_section(self):
        rc, out = _run_orient(self.project)
        self.assertEqual(rc, 0)
        self.assertIn("## BEHAVIOR LAYER", out)
        self.assertIn("WITH_BEHAVIOR_BEHAVIOR_LAYER.md", out)

    def test_source_of_truth_lists_behavior_layer_as_position_4(self):
        _, out = _run_orient(self.project)
        sot = out.split("## SOURCE OF TRUTH", 1)[1].split("##", 1)[0]
        self.assertIn("WITH_BEHAVIOR_BEHAVIOR_LAYER.md", sot)
        self.assertIn("behavior layer", sot.lower())
        # The 6-item ordering must place BEHAVIOR_LAYER between PIPELINE
        # and DO_NOTS. Lines parsed and indexed by leading number.
        ordered = [
            line.strip() for line in sot.splitlines()
            if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6."))
        ]
        # Position 3 → PIPELINE, 4 → BEHAVIOR_LAYER, 5 → DO_NOTS.
        self.assertIn("PIPELINE", ordered[2])
        self.assertIn("BEHAVIOR_LAYER", ordered[3])
        self.assertIn("DO_NOTS", ordered[4])
        self.assertIn("handoff", ordered[5].lower())


# ---------------------------------------------------------------------------
# Orient is graceful when BEHAVIOR_LAYER is absent (back-compat)
# ---------------------------------------------------------------------------


class TestOrientGracefulWithoutBehaviorLayerDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "no-behavior"
        run_init(_init_args("No Behavior", self.project))
        # Simulate an older project: remove the scaffolded behavior doc.
        (self.project / "docs" / "NO_BEHAVIOR_BEHAVIOR_LAYER.md").unlink()

    def tearDown(self):
        self._tmp.cleanup()

    def test_orient_does_not_crash(self):
        rc, _ = _run_orient(self.project)
        self.assertEqual(rc, 0)

    def test_orient_does_not_emit_behavior_section(self):
        _, out = _run_orient(self.project)
        self.assertNotIn("## BEHAVIOR LAYER — ", out)

    def test_source_of_truth_falls_back_to_placeholder(self):
        _, out = _run_orient(self.project)
        sot = out.split("## SOURCE OF TRUTH", 1)[1].split("##", 1)[0]
        # Placeholder line for behavior layer with optional flag.
        self.assertIn("docs/<APP>_BEHAVIOR_LAYER.md", sot)
        self.assertIn("optional", sot.lower())


# ---------------------------------------------------------------------------
# _find_behavior_layer_doc fallbacks
# ---------------------------------------------------------------------------


class TestFindBehaviorLayerDocFallbacks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_when_absent(self):
        self.assertIsNone(_find_behavior_layer_doc(self.project))

    def test_finds_suffixed_doc_under_docs(self):
        docs = self.project / "docs"
        docs.mkdir()
        path = docs / "MY_APP_BEHAVIOR_LAYER.md"
        path.write_text("# behavior\n", encoding="utf-8")
        self.assertEqual(_find_behavior_layer_doc(self.project), path)

    def test_finds_plain_under_docs(self):
        docs = self.project / "docs"
        docs.mkdir()
        path = docs / "BEHAVIOR_LAYER.md"
        path.write_text("# behavior\n", encoding="utf-8")
        self.assertEqual(_find_behavior_layer_doc(self.project), path)

    def test_finds_root_behavior_layer_md(self):
        path = self.project / "BEHAVIOR_LAYER.md"
        path.write_text("# behavior\n", encoding="utf-8")
        self.assertEqual(_find_behavior_layer_doc(self.project), path)

    def test_does_not_collide_with_pipeline_glob(self):
        # The pipeline doc uses *_PIPELINE.md; behavior uses
        # *_BEHAVIOR_LAYER.md. Both must coexist without collision.
        docs = self.project / "docs"
        docs.mkdir()
        pipeline = docs / "MY_APP_PIPELINE.md"
        pipeline.write_text("# pipeline\n", encoding="utf-8")
        behavior = docs / "MY_APP_BEHAVIOR_LAYER.md"
        behavior.write_text("# behavior\n", encoding="utf-8")
        # _find_behavior_layer_doc must pick the behavior file, not
        # accidentally pick up the pipeline file via a stray suffix glob.
        self.assertEqual(_find_behavior_layer_doc(self.project), behavior)


# ---------------------------------------------------------------------------
# Doctor: behavior-layer check
# ---------------------------------------------------------------------------


class TestDoctorBehaviorLayerCheck(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_pyproject_with_dep(self, project: Path, dep_token: str) -> None:
        project.mkdir(parents=True, exist_ok=True)
        (project / "pyproject.toml").write_text(
            f'[project]\nname = "x"\ndependencies = ["{dep_token}>=1.0"]\n',
            encoding="utf-8",
        )

    def _make_package_json_with_deps(self, project: Path, *deps: str) -> None:
        project.mkdir(parents=True, exist_ok=True)
        dep_lines = ", ".join(f'"{d}": "^1.0.0"' for d in deps)
        (project / "package.json").write_text(
            '{"dependencies": {' + dep_lines + '}}',
            encoding="utf-8",
        )

    def test_ok_when_behavior_layer_doc_present(self):
        project = self.tmpdir / "ok-app"
        run_init(_init_args("Ok App", project))
        # Init scaffolds OK_APP_BEHAVIOR_LAYER.md by default.
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "ok")
        self.assertIn("present", result.detail.lower())

    def test_skipped_when_no_indicators(self):
        project = self.tmpdir / "no-indicators"
        project.mkdir()
        (project / "README.md").write_text("# nothing\n", encoding="utf-8")
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "skipped")

    def test_warns_on_llm_dep_without_behavior_doc(self):
        # LLM dep alone fires the warning: pipeline indicators are a
        # subset of behavior indicators.
        project = self.tmpdir / "llm-only"
        self._make_pyproject_with_dep(project, "openai")
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "warning")
        self.assertIn("BEHAVIOR_LAYER.md missing", result.detail)
        self.assertIn("voice", result.detail.lower())

    def test_warns_on_chat_filename_indicator(self):
        project = self.tmpdir / "chat-app"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "chat_handler.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "warning")

    def test_warns_on_persona_filename_indicator(self):
        project = self.tmpdir / "persona-app"
        project.mkdir()
        (project / "personas.py").write_text("# stub\n", encoding="utf-8")
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "warning")

    def test_warns_on_voice_filename_indicator(self):
        project = self.tmpdir / "voice-app"
        project.mkdir()
        (project / "voice_runner.py").write_text("# stub\n", encoding="utf-8")
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "warning")

    def test_warns_on_ui_paired_with_llm(self):
        # React + openai in the same package.json should fire.
        project = self.tmpdir / "ui-llm"
        self._make_package_json_with_deps(project, "react", "openai")
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "warning")

    def test_skipped_for_plain_react_app(self):
        # React alone (no LLM, no chat/persona filenames) does NOT fire.
        project = self.tmpdir / "plain-react"
        self._make_package_json_with_deps(project, "react", "react-dom")
        result = check_behavior_layer_doc(project)
        self.assertEqual(result.status, "skipped")

    def test_warning_is_never_blocking(self):
        project = self.tmpdir / "warning-only"
        self._make_pyproject_with_dep(project, "anthropic")
        result = check_behavior_layer_doc(project)
        self.assertNotEqual(result.status, "blocking")


# ---------------------------------------------------------------------------
# Indicator-detection unit tests
# ---------------------------------------------------------------------------


class TestBehaviorIndicators(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_llm_dep_alone_triggers(self):
        (self.project / "pyproject.toml").write_text(
            '[project]\ndependencies = ["openai==1.0"]\n',
            encoding="utf-8",
        )
        self.assertTrue(_project_has_behavior_indicators(self.project))

    def test_chat_filename_token_triggers(self):
        sub = self.project / "src"
        sub.mkdir()
        (sub / "chat.py").write_text("# stub\n", encoding="utf-8")
        self.assertTrue(_project_has_behavior_indicators(self.project))

    def test_persona_filename_token_triggers(self):
        (self.project / "persona_loader.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        self.assertTrue(_project_has_behavior_indicators(self.project))

    def test_ui_alone_does_not_trigger(self):
        (self.project / "package.json").write_text(
            '{"dependencies": {"react": "^18.0.0"}}',
            encoding="utf-8",
        )
        self.assertFalse(_project_has_behavior_indicators(self.project))

    def test_ui_plus_llm_triggers(self):
        (self.project / "package.json").write_text(
            '{"dependencies": {"react": "^18.0.0", "openai": "^4.0.0"}}',
            encoding="utf-8",
        )
        self.assertTrue(_project_has_behavior_indicators(self.project))

    def test_skips_node_modules(self):
        node = self.project / "node_modules" / "chat-lib"
        node.mkdir(parents=True)
        (node / "index.js").write_text("//\n", encoding="utf-8")
        # filename includes 'chat' but lives under node_modules — must skip
        self.assertFalse(_project_has_behavior_indicators(self.project))


# ---------------------------------------------------------------------------
# _has_behavior_layer_doc parity
# ---------------------------------------------------------------------------


class TestHasBehaviorLayerDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_false_when_absent(self):
        self.assertFalse(_has_behavior_layer_doc(self.project))

    def test_true_for_suffixed(self):
        docs = self.project / "docs"
        docs.mkdir()
        (docs / "X_BEHAVIOR_LAYER.md").write_text("#\n", encoding="utf-8")
        self.assertTrue(_has_behavior_layer_doc(self.project))

    def test_true_for_plain_under_docs(self):
        docs = self.project / "docs"
        docs.mkdir()
        (docs / "BEHAVIOR_LAYER.md").write_text("#\n", encoding="utf-8")
        self.assertTrue(_has_behavior_layer_doc(self.project))

    def test_true_for_root(self):
        (self.project / "BEHAVIOR_LAYER.md").write_text("#\n", encoding="utf-8")
        self.assertTrue(_has_behavior_layer_doc(self.project))


if __name__ == "__main__":
    unittest.main()
