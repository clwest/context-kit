"""Tests for the PIPELINE.md runtime flow map.

Covers:
- bootstrap creates ``docs/<APP>_PIPELINE.md`` by default
- ``orient`` includes the pipeline section when the doc is present
- ``orient`` does not crash and silently omits the pipeline section
  when the doc is absent (older repos)
- the SOURCE OF TRUTH listing in ``orient`` references PIPELINE.md
- ``doctor`` warns when the project has LLM/agent/task indicators
  but no PIPELINE.md
- ``doctor`` is silent (skipped) when there are no indicators
- ``doctor`` is OK when PIPELINE.md is present
- the generated PIPELINE.md contains every required heading
- the DO_NOTS optional anchor is discovered when present
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
    _has_pipeline_doc,
    _project_has_pipeline_indicators,
    check_pipeline_doc,
)
from cli.orient import (  # noqa: E402
    _find_do_nots_doc,
    _find_pipeline_doc,
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
# Bootstrap creates PIPELINE.md
# ---------------------------------------------------------------------------


class TestBootstrapCreatesPipelineDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "pipeline-app"
        run_init(_init_args("Pipeline App", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_pipeline_doc_exists(self):
        path = self.project / "docs" / "PIPELINE_APP_PIPELINE.md"
        self.assertTrue(
            path.is_file(),
            f"expected scaffolded pipeline doc at {path}, got {sorted((self.project / 'docs').iterdir())}",
        )

    def test_pipeline_doc_has_required_headings(self):
        path = self.project / "docs" / "PIPELINE_APP_PIPELINE.md"
        text = path.read_text(encoding="utf-8")
        required = [
            "## Purpose",
            "## Request / Execution Paths",
            "## Guard Coverage Matrix",
            "## State Surfaces",
            "## Allow-lists / Drop Zones",
            "## Retrieval / Matching Paths",
            "## Post-Processing / Scrub Stack",
            "## Operational Hazards",
            "## Drift Surfaces",
            "## Decision Authority",
            "## Last Verified",
        ]
        missing = [h for h in required if h not in text]
        self.assertEqual(missing, [], f"missing required headings: {missing}")

    def test_drift_surfaces_section_lists_failure_paths(self):
        path = self.project / "docs" / "PIPELINE_APP_PIPELINE.md"
        text = path.read_text(encoding="utf-8")
        drift_block = text.split("## Drift Surfaces", 1)[1].split("## ", 1)[0]
        # Six failure-path categories listed in the spec must all appear.
        for needle in (
            "Alternate entry points",
            "retrieval",
            "Allow-lists",
            "External schedulers",
            "delegator",
            "import-order",
        ):
            self.assertIn(
                needle, drift_block,
                f"expected drift surfaces to mention {needle!r}",
            )
        # The "must either … or be explicitly marked" rule must be present.
        self.assertIn("Guard Coverage Matrix", drift_block)
        self.assertIn("external / unmanaged", drift_block)

    def test_decision_authority_section_states_llm_boundary(self):
        path = self.project / "docs" / "PIPELINE_APP_PIPELINE.md"
        text = path.read_text(encoding="utf-8")
        decision_block = text.split("## Decision Authority", 1)[1].split("## ", 1)[0]
        # Must distinguish deterministic backend vs LLM.
        self.assertIn("Deterministic", decision_block)
        self.assertIn("LLM", decision_block)
        # The three "must never" forbidden actions.
        for forbidden in ("pricing", "eligibility", "commitments"):
            self.assertIn(forbidden, decision_block)
        # The three "may only" allowed actions.
        for allowed in ("explain", "guide", "rephrase"):
            self.assertIn(allowed, decision_block)

    def test_cross_reference_to_inventory_present(self):
        path = self.project / "docs" / "PIPELINE_APP_PIPELINE.md"
        text = path.read_text(encoding="utf-8")
        # The cross-reference note inside Request / Execution Paths.
        paths_block = text.split("## Request / Execution Paths", 1)[1].split("## ", 1)[0]
        self.assertIn("INVENTORY.md", paths_block)
        # All three listed kinds must appear so the guidance is actionable.
        self.assertIn("LLM", paths_block)
        self.assertIn("agent", paths_block.lower())
        self.assertIn("task queue", paths_block.lower())
        # Explicitly framed as guidance only — no enforcement.
        self.assertIn("uidance only", paths_block)  # tolerates "Guidance" / "guidance"

    def test_pipeline_doc_substitutes_placeholders(self):
        path = self.project / "docs" / "PIPELINE_APP_PIPELINE.md"
        text = path.read_text(encoding="utf-8")
        # Placeholders should be substituted, not left as raw braces.
        self.assertNotIn("{{APP_TITLE}}", text)
        self.assertNotIn("{{APP_UPPER}}", text)
        self.assertIn("Pipeline App", text)


# ---------------------------------------------------------------------------
# Orient includes PIPELINE when present
# ---------------------------------------------------------------------------


class TestOrientIncludesPipelineWhenPresent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "with-pipeline"
        run_init(_init_args("With Pipeline", self.project))

    def tearDown(self):
        self._tmp.cleanup()

    def test_orient_emits_pipeline_section(self):
        rc, out = _run_orient(self.project)
        self.assertEqual(rc, 0)
        self.assertIn("## PIPELINE", out)
        self.assertIn("WITH_PIPELINE_PIPELINE.md", out)

    def test_source_of_truth_lists_pipeline(self):
        _, out = _run_orient(self.project)
        # The SOURCE OF TRUTH listing should mention the discovered
        # pipeline doc as item 4 (after WHAT_IT_IS + INVENTORY).
        sot = out.split("## SOURCE OF TRUTH", 1)[1].split("##", 1)[0]
        self.assertIn("WITH_PIPELINE_PIPELINE.md", sot)
        self.assertIn("runtime flow map", sot)


# ---------------------------------------------------------------------------
# Orient is graceful when PIPELINE is absent (back-compat)
# ---------------------------------------------------------------------------


class TestOrientGracefulWithoutPipelineDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "no-pipeline"
        run_init(_init_args("No Pipeline", self.project))
        # Simulate an older project: remove the scaffolded pipeline doc.
        (self.project / "docs" / "NO_PIPELINE_PIPELINE.md").unlink()

    def tearDown(self):
        self._tmp.cleanup()

    def test_orient_does_not_crash(self):
        rc, _ = _run_orient(self.project)
        self.assertEqual(rc, 0)

    def test_orient_does_not_emit_pipeline_section(self):
        _, out = _run_orient(self.project)
        # No PIPELINE preview block when the doc is absent.
        self.assertNotIn("## PIPELINE — ", out)

    def test_source_of_truth_falls_back_to_placeholder(self):
        _, out = _run_orient(self.project)
        sot = out.split("## SOURCE OF TRUTH", 1)[1].split("##", 1)[0]
        # Listing still references PIPELINE.md as a recommended slot,
        # but flagged as optional rather than discovered.
        self.assertIn("docs/<APP>_PIPELINE.md", sot)
        self.assertIn("optional", sot.lower())


# ---------------------------------------------------------------------------
# Pipeline-doc discovery
# ---------------------------------------------------------------------------


class TestFindPipelineDocFallbacks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_when_absent(self):
        self.assertIsNone(_find_pipeline_doc(self.project))

    def test_finds_suffixed_doc_under_docs(self):
        docs = self.project / "docs"
        docs.mkdir()
        path = docs / "MY_APP_PIPELINE.md"
        path.write_text("# pipeline\n", encoding="utf-8")
        self.assertEqual(_find_pipeline_doc(self.project), path)

    def test_finds_plain_pipeline_under_docs(self):
        docs = self.project / "docs"
        docs.mkdir()
        path = docs / "PIPELINE.md"
        path.write_text("# pipeline\n", encoding="utf-8")
        self.assertEqual(_find_pipeline_doc(self.project), path)

    def test_finds_root_pipeline_md(self):
        path = self.project / "PIPELINE.md"
        path.write_text("# pipeline\n", encoding="utf-8")
        self.assertEqual(_find_pipeline_doc(self.project), path)

    def test_suffixed_wins_over_plain(self):
        docs = self.project / "docs"
        docs.mkdir()
        plain = docs / "PIPELINE.md"
        plain.write_text("# plain\n", encoding="utf-8")
        suffixed = docs / "MY_APP_PIPELINE.md"
        suffixed.write_text("# suffixed\n", encoding="utf-8")
        self.assertEqual(_find_pipeline_doc(self.project), suffixed)


# ---------------------------------------------------------------------------
# DO_NOTS discovery (optional anchor)
# ---------------------------------------------------------------------------


class TestFindDoNotsDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_none_when_absent(self):
        self.assertIsNone(_find_do_nots_doc(self.project))

    def test_orient_includes_do_nots_when_present(self):
        run_init(_init_args("With Donts", self.project / "with-donts"))
        project = self.project / "with-donts"
        do_nots = project / "docs" / "DO_NOTS.md"
        do_nots.write_text(
            "# Don't do these\n\n- Don't bypass guards.\n",
            encoding="utf-8",
        )
        _, out = _run_orient(project)
        self.assertIn("## DO NOTS", out)
        self.assertIn("DO_NOTS.md", out)


# ---------------------------------------------------------------------------
# Doctor: warns on missing PIPELINE.md when LLM/agent/task indicators present
# ---------------------------------------------------------------------------


class TestDoctorPipelineCheck(unittest.TestCase):
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

    def test_ok_when_pipeline_doc_present(self):
        project = self.tmpdir / "ok-app"
        run_init(_init_args("Ok App", project))
        # Init scaffolds OK_APP_PIPELINE.md by default.
        result = check_pipeline_doc(project)
        self.assertEqual(result.status, "ok")
        self.assertIn("present", result.detail.lower())

    def test_skipped_when_no_indicators(self):
        project = self.tmpdir / "no-indicators"
        project.mkdir()
        # Bare project, no manifests, no telltale filenames.
        (project / "README.md").write_text("# nothing to see here\n", encoding="utf-8")
        result = check_pipeline_doc(project)
        self.assertEqual(result.status, "skipped")

    def test_warns_on_openai_dep_without_pipeline_doc(self):
        project = self.tmpdir / "openai-app"
        self._make_pyproject_with_dep(project, "openai")
        result = check_pipeline_doc(project)
        self.assertEqual(result.status, "warning")
        self.assertIn("PIPELINE.md missing", result.detail)
        self.assertIn("bypass drift", result.detail)

    def test_warns_on_celery_dep_without_pipeline_doc(self):
        project = self.tmpdir / "celery-app"
        self._make_pyproject_with_dep(project, "celery")
        result = check_pipeline_doc(project)
        self.assertEqual(result.status, "warning")

    def test_warns_on_filename_indicator_without_pipeline_doc(self):
        project = self.tmpdir / "agents-app"
        project.mkdir()
        (project / "src").mkdir()
        (project / "src" / "agents.py").write_text(
            "# stub\n", encoding="utf-8"
        )
        result = check_pipeline_doc(project)
        self.assertEqual(result.status, "warning")

    def test_warning_is_never_blocking(self):
        project = self.tmpdir / "warning-only"
        self._make_pyproject_with_dep(project, "anthropic")
        result = check_pipeline_doc(project)
        self.assertNotEqual(result.status, "blocking")


# ---------------------------------------------------------------------------
# Indicator-detection unit tests (probes the internals)
# ---------------------------------------------------------------------------


class TestPipelineIndicators(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_detects_openai_in_pyproject(self):
        (self.project / "pyproject.toml").write_text(
            '[project]\ndependencies = ["openai==1.0.0"]\n',
            encoding="utf-8",
        )
        self.assertTrue(_project_has_pipeline_indicators(self.project))

    def test_detects_langchain_in_requirements(self):
        (self.project / "requirements.txt").write_text(
            "langchain==0.3.0\nrequests\n",
            encoding="utf-8",
        )
        self.assertTrue(_project_has_pipeline_indicators(self.project))

    def test_detects_anthropic_sdk_in_package_json(self):
        (self.project / "package.json").write_text(
            '{"dependencies": {"@anthropic-ai/sdk": "^0.20.0"}}',
            encoding="utf-8",
        )
        self.assertTrue(_project_has_pipeline_indicators(self.project))

    def test_no_indicators_for_plain_python_project(self):
        (self.project / "pyproject.toml").write_text(
            '[project]\ndependencies = ["requests", "pytest"]\n',
            encoding="utf-8",
        )
        self.assertFalse(_project_has_pipeline_indicators(self.project))

    def test_filename_token_under_subdir(self):
        sub = self.project / "src" / "ai"
        sub.mkdir(parents=True)
        (sub / "agent_runner.py").write_text("# stub\n", encoding="utf-8")
        self.assertTrue(_project_has_pipeline_indicators(self.project))

    def test_skips_node_modules(self):
        node = self.project / "node_modules" / "celery"
        node.mkdir(parents=True)
        (node / "index.js").write_text("module.exports = {}\n", encoding="utf-8")
        # Filename includes 'celery' but lives under node_modules — must be skipped.
        # Also no manifest → no indicator at all.
        self.assertFalse(_project_has_pipeline_indicators(self.project))


# ---------------------------------------------------------------------------
# _has_pipeline_doc parity with orient discovery
# ---------------------------------------------------------------------------


class TestHasPipelineDoc(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_false_when_absent(self):
        self.assertFalse(_has_pipeline_doc(self.project))

    def test_true_for_suffixed(self):
        docs = self.project / "docs"
        docs.mkdir()
        (docs / "X_PIPELINE.md").write_text("#\n", encoding="utf-8")
        self.assertTrue(_has_pipeline_doc(self.project))

    def test_true_for_plain_under_docs(self):
        docs = self.project / "docs"
        docs.mkdir()
        (docs / "PIPELINE.md").write_text("#\n", encoding="utf-8")
        self.assertTrue(_has_pipeline_doc(self.project))

    def test_true_for_root_pipeline_md(self):
        (self.project / "PIPELINE.md").write_text("#\n", encoding="utf-8")
        self.assertTrue(_has_pipeline_doc(self.project))


if __name__ == "__main__":
    unittest.main()
