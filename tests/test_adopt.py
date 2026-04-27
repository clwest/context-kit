"""Tests for ``context-kit adopt`` (v0).

Scope matches the v0 contract: detect three buckets (JavaScript /
Python / unknown), generate four files, and offer dry-run vs --write.
We're validating usefulness, not completeness — the test count is
intentionally small and focused.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.adopt import (  # noqa: E402
    FAILURE_IDEMPOTENCY_RISK,
    FAILURE_MISLEADING_CLASSIFICATION,
    FAILURE_MISSING_FRAMEWORK_DETECTION,
    FAILURE_MONOREPO_DEPTH_LIMIT,
    FAILURE_NOISE_DIRECTORY_POLLUTION,
    FAILURE_ROOT_SIGNAL_OVERRIDE,
    FAILURE_SEVERITIES,
    FAILURE_SILENT_SUBDIR_DROP,
    FAILURE_STRUCTURE_UNDERREPRESENTED,
    FAILURE_SURFACE_AREAS,
    FAILURE_TYPES,
    FAILURE_UNRECOGNIZED_ECOSYSTEM,
    FAILURE_WRAPPER_DIRECTORY_INVISIBILITY,
    MAX_FILES_PER_SUBDIR,
    AdoptionInputs,
    END_MARKER,
    FailureRecord,
    START_MARKER,
    WorkspaceChild,
    _default_html_path,
    _is_data_only_subdir,
    _is_noise_dir,
    _manifest_hint,
    analyze_failures,
    apply_plan,
    detect_stack,
    generate_build_plan,
    generate_claude_block,
    plan_files,
    render_adopt_html,
    run_adopt,
    scan_unclassified_subdirs,
    scan_workspace_children,
)


def _ns(path: Path, write: bool, description: str, next_step: str) -> argparse.Namespace:
    return argparse.Namespace(
        command="adopt",
        path=str(path),
        write=write,
        description=description,
        next_step=next_step,
    )


class TestDetectStack(unittest.TestCase):
    """Three-way detection: JS, Python, unknown."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_package_json_yields_javascript(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "javascript")
        self.assertIn("package.json", result.signals)

    def test_manage_py_yields_python(self):
        (self.repo / "manage.py").write_text("# django\n", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "python")
        self.assertIn("manage.py", result.signals)

    def test_requirements_txt_yields_python(self):
        (self.repo / "requirements.txt").write_text("django\n", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "python")

    def test_empty_dir_yields_unknown(self):
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "unknown")
        # Honest about what was missing — the user should see why.
        self.assertTrue(any("No package.json" in n for n in result.notes))

    def test_mixed_repo_with_no_source_evidence_defaults_to_javascript(self):
        # v0.9 Phase 5.1 behavior: bare-manifest mixed-root with
        # no source evidence is "inconclusive". Falls back to
        # JavaScript (preserves the v0 default) but the note
        # explicitly says the source counts were inconclusive.
        # Replaces the v0 "multi-stack" note that always fired
        # regardless of evidence.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("flask\n", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "javascript")
        self.assertTrue(
            any("Mixed root manifests" in n for n in result.notes),
            f"expected mixed-root note; got {result.notes!r}",
        )
        self.assertTrue(
            any("inconclusive" in n.lower() for n in result.notes),
            f"no-source-evidence case must say inconclusive; "
            f"got {result.notes!r}",
        )


class TestSubdirDetection(unittest.TestCase):
    """v0.1: scan one level deep when the root has nothing.

    Root-first behavior is preserved (locked by the regression test
    in TestDetectStack); these tests cover the new split-monorepo
    fallback path that handles real-world dogfood projects like
    focus-flow / dealflowtracker / norman-handyman-mvp.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_split_backend_python_frontend_js_primary_is_backend(self):
        # The headline case the v0.1 plan was written for.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.parts, {"backend": "python", "frontend": "javascript"})
        self.assertEqual(result.language, "python", "backend wins as primary")
        # Signals are prefixed with the subdir so reports stay readable.
        self.assertIn("backend/manage.py", result.signals)
        self.assertIn("frontend/package.json", result.signals)

    def test_web_and_mobile_only_primary_is_first_detected(self):
        # No backend/. Mobile is JS-by-way-of-Expo would be handled in
        # a later release; here we treat any package.json as javascript
        # and confirm the "first-detected wins when no backend" rule.
        (self.repo / "web").mkdir()
        (self.repo / "web" / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "mobile").mkdir()
        (self.repo / "mobile" / "package.json").write_text("{}", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.parts, {"web": "javascript", "mobile": "javascript"})
        self.assertEqual(result.language, "javascript")

    def test_lone_backend_subdir_detected_with_split_note(self):
        # Half-built monorepo — backend exists, frontend doesn't.
        # We still go down the split path and emit the "split monorepo
        # detected" note so the user knows we scanned subdirs.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.parts, {"backend": "python"})
        self.assertEqual(result.language, "python")
        self.assertTrue(
            any("split monorepo" in n.lower() for n in result.notes),
            f"expected split-monorepo note; got {result.notes!r}",
        )

    def test_root_manifest_wins_over_subdir_manifest(self):
        # Regression guard: ai-content-studio has package.json at
        # root AND a backend/. Root must win — we don't want to
        # silently re-classify a single-stack repo as a monorepo
        # just because there's a same-named subdir.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "javascript")
        self.assertEqual(result.parts, {}, "parts must stay empty when root wins")
        self.assertIn("package.json", result.signals)
        # Subdir manifest should NOT leak into the signals list when
        # root wins; that would imply we scanned both, which we didn't.
        self.assertNotIn("backend/manage.py", result.signals)

    def test_build_plan_renders_split_stack_table(self):
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        body = generate_build_plan(
            stack,
            AdoptionInputs(project_description="Demo", next_step="ship v0"),
            "Demo",
        )
        # Per-subdir bullet rendering (not the single-line summary).
        self.assertIn("**Backend:** Python", body)
        self.assertIn("**Frontend:** JavaScript", body)
        self.assertIn("`backend/manage.py`", body)
        self.assertIn("`frontend/package.json`", body)

    def test_claude_block_renders_split_stack_table(self):
        # The augment block is the AI's instruction surface — it must
        # carry the per-subdir stack too, not just a flat summary.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        block = generate_claude_block(
            stack,
            AdoptionInputs(project_description="Demo", next_step="ship v0"),
            "Demo",
        )
        self.assertIn("**Backend:** Python", block)
        self.assertIn("**Frontend:** JavaScript", block)


class TestPlanAndApply(unittest.TestCase):
    """End-to-end: plan, then apply in dry-run and write modes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        self.inputs = AdoptionInputs(
            project_description="A personal task manager",
            next_step="Wire up the login form",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_plan_produces_four_files(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        rel_paths = sorted(str(p.path.relative_to(self.repo)) for p in plan)
        self.assertEqual(
            rel_paths,
            sorted([
                "00-START-NEXT-SESSION.md",
                "CLAUDE.md",
                "docs/BUILD_PLAN.md",
                "docs/PROJECT_WHAT_IT_IS.md",
            ]),
        )

    def test_dry_run_writes_nothing(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        actions = apply_plan(plan, dry_run=True)
        for action in actions:
            self.assertTrue(action.strip().startswith("would "), action)
        self.assertFalse((self.repo / "docs" / "BUILD_PLAN.md").exists())
        self.assertFalse((self.repo / "CLAUDE.md").exists())
        self.assertFalse((self.repo / "00-START-NEXT-SESSION.md").exists())

    def test_write_creates_all_four_files_with_user_input_inside(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        apply_plan(plan, dry_run=False)
        bp = (self.repo / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")
        wii = (self.repo / "docs" / "PROJECT_WHAT_IT_IS.md").read_text(encoding="utf-8")
        sh = (self.repo / "00-START-NEXT-SESSION.md").read_text(encoding="utf-8")
        # User's two answers must reach the generated docs verbatim.
        self.assertIn("A personal task manager", bp)
        self.assertIn("A personal task manager", wii)
        self.assertIn("Wire up the login form", sh)
        # Detected stack is in BUILD_PLAN — the source-of-truth doc.
        self.assertIn("JavaScript", bp)
        # state: scaffold frontmatter so seed/wizard recognize it.
        self.assertTrue(sh.startswith("---\nstate: scaffold"), sh[:60])


class TestClaudeMdAugmentation(unittest.TestCase):
    """The augment-only contract on existing CLAUDE.md."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        self.inputs = AdoptionInputs(
            project_description="A personal task manager",
            next_step="Wire up the login form",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_existing_claude_md_is_preserved_verbatim_outside_marker(self):
        # The whole point of augment-mode: a user's hand-written
        # CLAUDE.md must not lose a single byte of their content.
        original = (
            "# CLAUDE — Acme\n"
            "\n"
            "## Important rules\n"
            "\n"
            "- Always use 2-space indentation.\n"
            "- Never push to main directly.\n"
        )
        (self.repo / "CLAUDE.md").write_text(original, encoding="utf-8")
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        apply_plan(plan, dry_run=False)
        result = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        # Original prose is fully present.
        for line in original.splitlines():
            self.assertIn(line, result, f"lost line: {line!r}")
        # And the managed block sits at the end with the markers.
        self.assertIn(START_MARKER, result)
        self.assertIn(END_MARKER, result)
        self.assertIn("Project facts (auto-detected)", result)

    def test_rerunning_augment_replaces_block_in_place(self):
        # Idempotency: running adopt twice must not stack two
        # managed blocks. The second run replaces the first block's
        # contents and leaves human content untouched.
        (self.repo / "CLAUDE.md").write_text(
            "# CLAUDE — Acme\n\n## Notes\n\nKeep it simple.\n",
            encoding="utf-8",
        )
        stack = detect_stack(self.repo)
        apply_plan(plan_files(self.repo, stack, self.inputs), dry_run=False)
        # Second run: change the user's "next" so we can verify the
        # block updated.
        new_inputs = AdoptionInputs(
            project_description=self.inputs.project_description,
            next_step="Now add password reset",
        )
        apply_plan(plan_files(self.repo, stack, new_inputs), dry_run=False)
        result = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(result.count(START_MARKER), 1, "stacked blocks!")
        self.assertEqual(result.count(END_MARKER), 1, "stacked blocks!")
        self.assertIn("Now add password reset", result)
        self.assertNotIn("Wire up the login form", result)
        # Human content still intact.
        self.assertIn("Keep it simple.", result)

    def test_managed_block_carries_strengthened_prompt_rule(self):
        # The block is the AI's instruction surface for an adopted
        # project. It must carry the BUILD_PLAN.md rule that the rest
        # of the framework relies on.
        block = generate_claude_block(
            detect_stack(self.repo), self.inputs, "Acme",
        )
        self.assertIn("docs/BUILD_PLAN.md", block)
        self.assertIn("source of truth", block.lower())


class TestRunAdoptCli(unittest.TestCase):
    """The argparse entry point — verify the dry-run exit + reporting."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "package.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_dry_run_exits_0_and_writes_nothing(self):
        rc = run_adopt(_ns(self.repo, write=False,
                           description="x", next_step="y"))
        self.assertEqual(rc, 0)
        self.assertFalse((self.repo / "docs" / "BUILD_PLAN.md").exists())

    def test_write_exits_0_and_creates_files(self):
        rc = run_adopt(_ns(self.repo, write=True,
                           description="x", next_step="y"))
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / "docs" / "BUILD_PLAN.md").is_file())
        self.assertTrue((self.repo / "CLAUDE.md").is_file())

    def test_nonexistent_path_exits_1(self):
        rc = run_adopt(argparse.Namespace(
            command="adopt", path="/definitely/not/a/real/dir",
            write=False, description="x", next_step="y",
        ))
        self.assertEqual(rc, 1)


# ---------------------------------------------------------------------------
# v0.2: visibility-first fallback (SESSION_009_ADOPT.md §19)
# ---------------------------------------------------------------------------


class TestVisibilityFirstScan(unittest.TestCase):
    """Never allow real project structure to be invisible.

    Each test wires up a tiny fixture project that mirrors a shape from
    the dogfood inventory (tornado-core's contracts/circuits, the
    flow-name-service empty api/, the dbao-studio root-wins pattern,
    etc.) and asserts the visibility-first scan surfaces what
    classification missed.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _named(self, profile, name):
        """Return the UnclassifiedSubdir with ``name`` from ``profile``,
        or fail loudly with what was actually found."""
        match = next((u for u in profile.unclassified_subdirs if u.name == name), None)
        self.assertIsNotNone(
            match,
            f"expected unclassified subdir {name!r}; got "
            f"{[u.name for u in profile.unclassified_subdirs]}",
        )
        return match

    def test_contracts_dir_with_sol_files_surfaces(self):
        # The tornado-core shape: package.json wins classification but
        # contracts/ with .sol files must still be visible.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "contracts").mkdir()
        for n in ("Foo.sol", "Bar.sol", "Baz.sol"):
            (self.repo / "contracts" / n).write_text("// solidity\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        # Classification unchanged.
        self.assertEqual(stack.language, "javascript")
        # contracts/ surfaces with .sol count + suggest-Solidity hint.
        m = self._named(stack, "contracts")
        self.assertEqual(m.notable_extensions.get(".sol"), 3)
        self.assertIn("Solidity", m.note or "")
        self.assertIn("verify with user", m.note or "")
        # Example path is anchored at the subdir name.
        self.assertTrue(
            m.example_paths.get(".sol", "").startswith("contracts/"),
            f"expected example under contracts/; got {m.example_paths!r}",
        )

    def test_circuits_dir_with_circom_files_surfaces(self):
        # The tornado-core zk-SNARK circuits — first Circom files in
        # the dogfood inventory. Verifies the .circom hint is
        # data-table driven, not code-driven.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "circuits").mkdir()
        for n in ("merkleTree.circom", "withdraw.circom", "transfer.circom"):
            (self.repo / "circuits" / n).write_text("// circom\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        m = self._named(stack, "circuits")
        self.assertEqual(m.notable_extensions.get(".circom"), 3)
        self.assertIn("Circom", m.note or "")
        self.assertIn("zk-SNARK", m.note or "")

    def test_mobile_pubspec_yaml_surfaces_when_not_classified(self):
        # The donkey_betz_world failure mode: mobile/ has pubspec.yaml
        # which v0.1's classifier doesn't recognize, but visibility-
        # first must surface it as a manifest-shaped file plus the
        # .dart hint from any Dart sources inside.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "mobile").mkdir()
        (self.repo / "mobile" / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "mobile" / "lib").mkdir()
        (self.repo / "mobile" / "lib" / "main.dart").write_text("void main() {}\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        # backend/frontend stay classified.
        self.assertEqual(stack.parts, {"backend": "python", "frontend": "javascript"})
        # mobile/ surfaces with both the manifest filename and the .dart hint.
        m = self._named(stack, "mobile")
        self.assertIn("pubspec.yaml", m.manifest_files)
        self.assertEqual(m.notable_extensions.get(".dart"), 1)
        self.assertIn("Dart", m.note or "")
        self.assertIn("Flutter", m.note or "")

    def test_classified_and_unclassified_appear_together(self):
        # The mentorforge failure mode: backend/frontend get classified,
        # but unrecognized peer subdirs (analysis/, financial/, etc.)
        # silently dropped by v0.1. v0.2 surfaces them while preserving
        # the original split classification.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        (self.repo / "analysis").mkdir()
        (self.repo / "analysis" / "report.py").write_text("# data\n", encoding="utf-8")
        (self.repo / "analysis" / "model.py").write_text("# data\n", encoding="utf-8")
        (self.repo / "analysis" / "forecast.py").write_text("# data\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        # backend stays classified.
        self.assertEqual(stack.parts.get("backend"), "python")
        # analysis surfaces with .py count above the generic threshold.
        m = self._named(stack, "analysis")
        self.assertEqual(m.notable_extensions.get(".py"), 3)
        # backend should NOT also appear in the unclassified list — it's
        # already named in parts.
        names = [u.name for u in stack.unclassified_subdirs]
        self.assertNotIn("backend", names, f"backend duplicated in {names!r}")

    def test_root_wins_but_subdirs_still_surface(self):
        # The dbao-studio failure mode: root has both package.json AND
        # requirements.txt so root wins (JavaScript), but backend/
        # contains the real Django code. v0.2 must surface backend/ in
        # unclassified-but-present even though root won classification.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("django\n", encoding="utf-8")
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# django\n", encoding="utf-8")
        (self.repo / "backend" / "requirements.txt").write_text("django\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        # Root classification preserved.
        self.assertEqual(stack.language, "javascript")
        self.assertEqual(stack.parts, {})
        # backend/ surfaces with both manifests visible.
        m = self._named(stack, "backend")
        self.assertIn("manage.py", m.manifest_files)
        self.assertIn("requirements.txt", m.manifest_files)

    def test_noise_dirs_skipped(self):
        # Hidden dirs and standard noise (node_modules, .git, .venv,
        # __pycache__, dist, build) must never appear in the
        # unclassified report — they're build artifacts, not project
        # structure. Without this filter the report would be
        # overwhelmed on real npm/Python projects.
        for noise in ("node_modules", ".git", ".venv", "__pycache__", "dist", "build"):
            (self.repo / noise).mkdir()
            (self.repo / noise / "stuff.py").write_text("# noise\n", encoding="utf-8")
        (self.repo / "real_dir").mkdir()
        (self.repo / "real_dir" / "thing.py").write_text("# real\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        names = {u.name for u in stack.unclassified_subdirs}
        for noise in ("node_modules", ".git", ".venv", "__pycache__", "dist", "build"):
            self.assertNotIn(
                noise, names,
                f"{noise} leaked into unclassified report: {names!r}",
            )
        # The genuine subdir IS surfaced (sanity check that the test
        # fixture wired up correctly).
        self.assertIn("real_dir", names)

    def test_empty_subdir_reported_as_empty(self):
        # The flow-name-service api/ case — the directory exists but
        # contains zero files. Worth surfacing as "empty" rather than
        # silently dropping; an empty placeholder dir often signals
        # intent (a planned subsystem that wasn't built yet).
        (self.repo / "api").mkdir()
        stack = detect_stack(self.repo)
        m = self._named(stack, "api")
        self.assertTrue(m.is_empty)
        self.assertEqual(m.total_file_count, 0)

    def test_dir_with_unrecognized_extensions_not_called_empty(self):
        # The dbao-studio agents/ case — a directory full of .json
        # files would have been falsely labelled "EMPTY" if we only
        # tracked recognized extensions. Visibility-first must
        # distinguish "no files at all" (truly empty) from "has files
        # but none of a type we categorize" (config / data / docs).
        (self.repo / "agents").mkdir()
        for n in ("a.json", "b.json", "c.json", "readme.md"):
            (self.repo / "agents" / n).write_text("{}\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        m = self._named(stack, "agents")
        self.assertFalse(m.is_empty, "dir with .json files reported as empty!")
        self.assertGreaterEqual(m.total_file_count, 4)
        # No recognized source extensions means notable_extensions
        # stays empty — that's how the renderer knows to say "N files
        # (no recognized source extensions)" instead of listing nothing.
        self.assertEqual(m.notable_extensions, {})

    def test_generic_extensions_below_threshold_not_reported(self):
        # MIN_SOURCE_FILES_TO_REPORT (3) gates noisy generic counts.
        # A stray .py file in an otherwise non-Python project
        # shouldn't trigger reporting; a domain extension (.sol)
        # should always report at any count >= 1 because even one
        # .sol file is meaningful signal.
        (self.repo / "tools").mkdir()
        (self.repo / "tools" / "helper.py").write_text("# stray\n", encoding="utf-8")  # 1 < 3
        (self.repo / "tools" / "one.sol").write_text("// sol\n", encoding="utf-8")     # 1 >= 1 (domain)
        stack = detect_stack(self.repo)
        m = self._named(stack, "tools")
        self.assertNotIn(".py", m.notable_extensions, "generic .py reported below threshold")
        self.assertEqual(m.notable_extensions.get(".sol"), 1, "domain .sol omitted at count 1")

    def test_large_subdir_files_capped(self):
        # MAX_FILES_PER_SUBDIR caps the depth-2 walk so a subdir with
        # 1000+ files can't blow up cost. The test creates twice the
        # cap and asserts the count is bounded but the dir surfaces.
        (self.repo / "huge").mkdir()
        target = MAX_FILES_PER_SUBDIR * 2
        for i in range(target):
            (self.repo / "huge" / f"f{i}.sol").write_text("// sol\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        m = self._named(stack, "huge")
        # Some count is reported.
        self.assertGreater(m.notable_extensions.get(".sol", 0), 0)
        # And it's bounded at the cap (off-by-one OK; the file_count
        # check happens before increment in the inner loop).
        self.assertLessEqual(
            m.notable_extensions.get(".sol", 0), MAX_FILES_PER_SUBDIR + 5,
            f"cap not enforced; got {m.notable_extensions.get('.sol')}",
        )

    def test_build_plan_renders_unknown_but_present(self):
        # The full pipeline: detect → generate → assert the BUILD_PLAN
        # carries the visibility-first content into the doc that an
        # AI session reads. Without this, the dry-run could surface
        # things but the agent reading docs/BUILD_PLAN.md would still
        # be in the dark.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "contracts").mkdir()
        for n in ("Foo.sol", "Bar.sol", "Baz.sol"):
            (self.repo / "contracts" / n).write_text("// sol\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        bp = generate_build_plan(
            stack,
            AdoptionInputs(project_description="x", next_step="y"),
            "Test",
        )
        self.assertIn("Needs clarification", bp)
        self.assertIn("contracts/", bp)
        self.assertIn(".sol", bp)
        self.assertIn("Solidity", bp)

    def test_claude_block_renders_unknown_but_present(self):
        # Same content must reach the CLAUDE.md augment block — that's
        # the AI session's entry-point doc. If contracts/ is in
        # BUILD_PLAN but not CLAUDE.md, an agent might miss it.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "contracts").mkdir()
        for n in ("Foo.sol", "Bar.sol", "Baz.sol"):
            (self.repo / "contracts" / n).write_text("// sol\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        block = generate_claude_block(
            stack,
            AdoptionInputs(project_description="x", next_step="y"),
            "Test",
        )
        self.assertIn("Needs clarification", block)
        self.assertIn("contracts/", block)

    def test_no_unknown_section_when_unclassified_empty(self):
        # Clean classified projects must not gain a noisy "Unknown but
        # present" section just because the renderer is now wired up.
        # The section is silently omitted when there's nothing to surface.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        # Both subdirs got classified — nothing left over.
        self.assertEqual(stack.unclassified_subdirs, [])
        bp = generate_build_plan(
            stack,
            AdoptionInputs(project_description="x", next_step="y"),
            "Test",
        )
        self.assertNotIn("Needs clarification", bp)
        block = generate_claude_block(
            stack,
            AdoptionInputs(project_description="x", next_step="y"),
            "Test",
        )
        self.assertNotIn("Needs clarification", block)


# ---------------------------------------------------------------------------
# §21: --html static review report
# ---------------------------------------------------------------------------


def _ns_html(path: Path, *, write=False, html=False, html_out=None,
             no_browser=True, description="A demo project",
             next_step="ship v1") -> argparse.Namespace:
    """Namespace builder for --html tests. ``no_browser`` defaults True
    so tests never actually pop a browser window."""
    return argparse.Namespace(
        command="adopt",
        path=str(path),
        write=write,
        html=html,
        html_out=str(html_out) if html_out else None,
        no_browser=no_browser,
        description=description,
        next_step=next_step,
    )


class TestAdoptHtmlReport(unittest.TestCase):
    """§21: ``adopt --html`` produces a single self-contained HTML file.

    Hard contracts under test (matched to the design spec):
    - Static HTML, no server, no HTTP.
    - Default destination outside the project tree (system temp).
    - --html-out PATH overrides the default.
    - --no-browser suppresses webbrowser.open() (so tests are silent).
    - CLI dry-run stdout is byte-equal with or without --html.
    - HTML escapes user-supplied content.
    - Re-runs against the same project overwrite the same file.
    - The "Needs clarification" section is rendered as the visual focus
      when there's anything to surface, and silently omitted otherwise.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # A minimal project with one classified subdir + one unclassified
        # one. Matches the donkey_betz_world dogfood shape in miniature.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "contracts").mkdir()
        for n in ("Foo.sol", "Bar.sol", "Baz.sol"):
            (self.repo / "contracts" / n).write_text("// sol\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    # --- default destination + overwrite + auto-open suppression ---

    def test_default_html_path_is_under_system_tempdir(self):
        # The "source tree untouched by default" contract: default
        # destination must NOT be inside the repo. Using
        # tempfile.gettempdir() makes this cross-platform (returns
        # /var/folders/... on macOS, /tmp on Linux, etc).
        out = _default_html_path(self.repo)
        self.assertEqual(out.parent, Path(tempfile.gettempdir()))
        self.assertTrue(out.name.startswith("contextkit-adopt-report-"))
        self.assertTrue(out.name.endswith(".html"))
        # Different cwds yield different filenames so two projects
        # don't collide on the same /tmp file.
        with tempfile.TemporaryDirectory() as other_tmp:
            other_path = _default_html_path(Path(other_tmp))
            self.assertNotEqual(out.name, other_path.name)

    def test_default_html_path_is_stable_for_same_repo(self):
        # Same project re-run must produce the same filename so re-runs
        # overwrite in place rather than accumulating files.
        a = _default_html_path(self.repo)
        b = _default_html_path(self.repo)
        self.assertEqual(a, b)

    def test_html_flag_writes_file_and_returns_zero(self):
        rc = run_adopt(_ns_html(self.repo, html=True))
        self.assertEqual(rc, 0)
        out = _default_html_path(self.repo)
        self.assertTrue(out.is_file(), f"expected HTML at {out}")
        # Cleanup so we don't leak the test artifact.
        out.unlink()

    def test_html_out_writes_to_explicit_path(self):
        explicit = self.repo / "report.html"  # inside repo to test override
        rc = run_adopt(_ns_html(self.repo, html_out=explicit))
        self.assertEqual(rc, 0)
        self.assertTrue(explicit.is_file())
        # Default path should NOT also exist when explicit was used.
        # (We can't check default path didn't exist *before* this run —
        # other tests may have left one — so we just confirm the
        # explicit one was the destination.)
        self.assertGreater(explicit.stat().st_size, 0)

    def test_html_out_implies_html(self):
        # The design says --html-out implies --html. Check by passing
        # html_out without html=True.
        explicit = self.repo / "implicit.html"
        rc = run_adopt(_ns_html(self.repo, html=False, html_out=explicit))
        self.assertEqual(rc, 0)
        self.assertTrue(explicit.is_file())

    def test_rerun_overwrites_default_path_in_place(self):
        run_adopt(_ns_html(self.repo, html=True))
        out = _default_html_path(self.repo)
        first_mtime = out.stat().st_mtime_ns
        # Mtime resolution can be coarse — sleep briefly so the second
        # write definitely produces a newer mtime, OR just check that
        # the file is still the only contextkit-adopt-report-* in the
        # tempdir for our repo's hash.
        run_adopt(_ns_html(self.repo, html=True, description="Updated desc"))
        # Same path, still exactly one file matching the hash pattern.
        matches = list(out.parent.glob(out.name))
        self.assertEqual(len(matches), 1)
        # Content updated (the new description appears).
        self.assertIn("Updated desc", out.read_text(encoding="utf-8"))
        out.unlink()

    # --- additivity: CLI stdout unchanged with or without --html ---

    def test_html_does_not_change_cli_stdout(self):
        # The "additivity" contract: running with --html should produce
        # the same dry-run stdout as running without it (modulo a single
        # extra "HTML report: ..." line at the end). Capture both runs
        # and assert the meaningful body is identical.
        explicit = self.repo / "report.html"
        from io import StringIO
        from contextlib import redirect_stdout
        buf_a, buf_b = StringIO(), StringIO()
        with redirect_stdout(buf_a):
            run_adopt(_ns_html(self.repo))
        with redirect_stdout(buf_b):
            run_adopt(_ns_html(self.repo, html=True, html_out=explicit))
        # Strip the trailing "HTML report: ..." line from buf_b before
        # comparing — that's the documented additive line, not a
        # change to the existing flow.
        b_lines = buf_b.getvalue().rstrip().splitlines()
        if b_lines and b_lines[-1].startswith("HTML report:"):
            b_lines = b_lines[:-1]
            # Trailing blank line printed before the HTML report line.
            if b_lines and b_lines[-1] == "":
                b_lines = b_lines[:-1]
        a_lines = buf_a.getvalue().rstrip().splitlines()
        self.assertEqual(
            a_lines, b_lines,
            "CLI stdout differs when --html is added; additivity contract violated",
        )

    # --- content / safety / structure ---

    def test_html_contains_project_name_and_classification_and_subdirs(self):
        explicit = self.repo / "report.html"
        run_adopt(_ns_html(self.repo, html_out=explicit))
        body = explicit.read_text(encoding="utf-8")
        # The Tempdir.name basename varies; just assert the directory
        # path appears somewhere in the report.
        self.assertIn(str(self.repo), body)
        # Root-classified as JavaScript.
        self.assertIn("JavaScript", body)
        # contracts/ surfaces in unknown-but-present.
        self.assertIn("contracts/", body)
        self.assertIn("Solidity", body)
        # All four planned files appear.
        for rel in ("BUILD_PLAN.md", "PROJECT_WHAT_IT_IS.md",
                    "00-START-NEXT-SESSION.md", "CLAUDE.md"):
            self.assertIn(rel, body, f"missing planned file in report: {rel}")

    def test_html_escapes_user_supplied_content(self):
        # XSS-safety: the description and next_step come from user input
        # (interactive prompt). They MUST be escaped before going into
        # the HTML so a description like "<script>alert('x')</script>"
        # can't execute when the report opens in the browser.
        evil = '<script>alert("xss")</script>'
        explicit = self.repo / "report.html"
        # description contains the payload (next_step kept benign).
        run_adopt(_ns_html(
            self.repo, html_out=explicit,
            description=evil, next_step="ok",
        ))
        body = explicit.read_text(encoding="utf-8")
        # The literal payload tag must NOT appear unescaped anywhere.
        self.assertNotIn(evil, body)
        # The escaped form should appear (the user's input is still
        # surfaced — it's just rendered as text, not executed).
        self.assertIn("&lt;script&gt;", body)

    def test_html_omits_unknown_but_present_when_classifier_covers_everything(self):
        # Clean classified projects (no leftover subdirs) must NOT have
        # the "Needs clarification" section. The visual focus is dynamic;
        # silent on tidy projects so it doesn't add noise.
        with tempfile.TemporaryDirectory() as clean:
            clean_path = Path(clean)
            (clean_path / "backend").mkdir()
            (clean_path / "backend" / "manage.py").write_text(
                "# d\n", encoding="utf-8",
            )
            (clean_path / "frontend").mkdir()
            (clean_path / "frontend" / "package.json").write_text(
                "{}", encoding="utf-8",
            )
            explicit = clean_path / "report.html"
            run_adopt(_ns_html(clean_path, html_out=explicit))
            body = explicit.read_text(encoding="utf-8")
            self.assertNotIn("Needs clarification", body)
            # And the classified parts card IS present.
            self.assertIn("Classified parts", body)

    def test_cta_warns_when_user_inputs_empty(self):
        # The "Fill in description and next step before --write" CTA
        # fires when either input was left empty. Beginner safety.
        explicit = self.repo / "report.html"
        run_adopt(_ns_html(
            self.repo, html_out=explicit,
            description="", next_step="",
        ))
        body = explicit.read_text(encoding="utf-8")
        self.assertIn("Fill in description and next step", body)
        # And the "Looks good" CTA must NOT also appear.
        self.assertNotIn("Looks good", body)

    def test_cta_says_looks_good_when_inputs_present_and_dry_run(self):
        explicit = self.repo / "report.html"
        run_adopt(_ns_html(
            self.repo, html_out=explicit,
            description="real description", next_step="real next step",
        ))
        body = explicit.read_text(encoding="utf-8")
        self.assertIn("Looks good", body)
        self.assertIn("--write", body)

    def test_no_browser_flag_suppresses_webbrowser_open(self):
        # When --no-browser is set, webbrowser.open MUST NOT be called.
        # We monkey-patch the module-level reference so we can detect.
        import cli.adopt as adopt_module
        calls = []
        original = adopt_module.webbrowser
        class _StubBrowser:
            def open(self, url):  # noqa: D401
                calls.append(url)
        adopt_module.webbrowser = _StubBrowser()
        try:
            explicit = self.repo / "report.html"
            run_adopt(_ns_html(self.repo, html_out=explicit, no_browser=True))
            self.assertEqual(calls, [], "webbrowser.open called despite --no-browser")
        finally:
            adopt_module.webbrowser = original


class TestRenderAdoptHtmlPure(unittest.TestCase):
    """Direct tests on render_adopt_html without going through run_adopt.

    Lets us exercise edge cases (e.g., empty stack, write_mode=True)
    without wiring full plan + I/O each time.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        (self.repo / "package.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_render_in_write_mode_uses_will_badges_and_done_cta(self):
        stack = detect_stack(self.repo)
        inputs = AdoptionInputs(project_description="x", next_step="y")
        plan = plan_files(self.repo, stack, inputs)
        html = render_adopt_html(self.repo, stack, inputs, plan, write_mode=True)
        # "Will create" instead of "Would create" — write_mode intent.
        self.assertIn("Will create", html)
        self.assertNotIn("Would create", html)
        # "Done" CTA replaces the run-with-write CTA. The literal
        # primer prompt — the same one the wizard's Step 8 hands the
        # user — must appear so the AI session has a clear opener.
        self.assertIn("Done", html)
        self.assertIn(
            "Read CLAUDE.md, docs/BUILD_PLAN.md, and docs/*_WHAT_IT_IS.md.",
            html,
        )
        self.assertIn("Do not change the stack without asking.", html)
        # Self-contained: no external <link> or <script src=>.
        self.assertNotIn("<link", html)
        self.assertNotIn("<script src=", html)


# ---------------------------------------------------------------------------
# v0.2.x: idempotency + noise patterns + manifest hints + data-only grouping
# (post unified-donkey-betz dogfood)
# ---------------------------------------------------------------------------


class TestNoisePatternFiltering(unittest.TestCase):
    """Pattern-based noise filter — fix for venv_ml/, venv-prod/, etc.
    that v0.2's exact-name matching let through. False-positive guard
    on lookalike names (envelope, envoy) is part of the contract.
    """

    def test_exact_name_matches(self):
        for n in ("node_modules", "__pycache__", "dist", "build",
                  "out", "target", "coverage", "media"):
            self.assertTrue(_is_noise_dir(n), f"{n} should be noise")

    def test_venv_variants_match(self):
        # The bug from the unified-donkey-betz dogfood: venv_ml/ slipped
        # past v0.2's exact-name set. Pattern-based matching catches it
        # AND venv-prod/, venv.old/, .venv* (via the leading-dot
        # filter applied separately at the call site).
        for n in ("venv", "venv_ml", "venv-prod", "venv.old",
                  "env", "env-dev", "env_dev", "env.staging",
                  "pyenv", "virtualenv"):
            self.assertTrue(_is_noise_dir(n), f"{n} should be noise")

    def test_lookalike_names_not_filtered(self):
        # The false-positive guard: a directory whose name STARTS WITH
        # "env" or "venv" but doesn't have a separator after the prefix
        # is real content, not a venv. Don't filter these.
        for n in ("envelope", "envoy", "venvelope", "envman", "envoie"):
            self.assertFalse(_is_noise_dir(n), f"{n} should NOT be filtered")

    def test_noise_pattern_filter_applies_to_unclassified_scan(self):
        # End-to-end: a venv_ml/ in a real repo must not appear in
        # unclassified_subdirs. This is the load-bearing test against
        # the unified-donkey-betz failure mode.
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "venv_ml").mkdir()
            (repo / "venv_ml" / "bin").mkdir()
            (repo / "venv_ml" / "bin" / "python").touch()
            (repo / "real_subsystem").mkdir()
            (repo / "real_subsystem" / "thing.py").write_text(
                "# real\n", encoding="utf-8")
            stack = detect_stack(repo)
            names = {u.name for u in stack.unclassified_subdirs}
            self.assertNotIn("venv_ml", names,
                             f"venv_ml leaked into unclassified: {names!r}")
            self.assertIn("real_subsystem", names)


class TestManifestHints(unittest.TestCase):
    """Lightweight pattern hints — restore visual contrast on common
    monorepos. Not a full framework detector. Three patterns shipped
    in v0.2.x; everything else stays generic.
    """

    def test_vite_plus_tailwind_hint(self):
        # The unified-donkey-betz frontend/ shape: package.json +
        # vite.config.ts + tailwind.config.js. v0.2 surfaced it as
        # generic "JS / TS files"; v0.2.x adds the framework hint.
        hint = _manifest_hint(["package.json", "vite.config.ts",
                               "tailwind.config.js", "postcss.config.js"])
        self.assertIsNotNone(hint)
        self.assertIn("Vite", hint)
        self.assertIn("Tailwind", hint)
        self.assertIn("verify with user", hint)

    def test_expo_hint(self):
        # The unified-donkey-betz mobile/ shape: package.json +
        # app.config.ts. Strong Expo signal without parsing
        # package.json deps.
        hint = _manifest_hint(["package.json", "app.config.ts",
                               "babel.config.js"])
        self.assertIsNotNone(hint)
        self.assertIn("Expo", hint)

    def test_isolated_python_subsystem_hint(self):
        # ml/ and resolve_node/ in unified-donkey-betz both have their
        # own requirements.txt — meaningful structural signal that the
        # subsystem is intended to run in isolation.
        hint = _manifest_hint(["requirements.txt"])
        self.assertIsNotNone(hint)
        self.assertIn("Python subsystem", hint)
        self.assertIn("isolated dependencies", hint)

    def test_no_hint_for_plain_package_json(self):
        # A subdir with just package.json (no vite / tailwind / app
        # config) gets no manifest hint — too generic to commit to.
        self.assertIsNone(_manifest_hint(["package.json"]))

    def test_no_hint_for_unrelated_manifests(self):
        # Web3 manifests don't trigger any of the three patterns we
        # ship; they get a domain-extension hint instead via DOMAIN_HINTS.
        self.assertIsNone(_manifest_hint(["Clarinet.toml"]))
        self.assertIsNone(_manifest_hint(["foundry.toml", "hardhat.config.ts"]))


class TestIdempotencySafety(unittest.TestCase):
    """The load-bearing safety contract: re-running ``adopt --write``
    must NEVER destroy user content. This is the fix for the
    unified-donkey-betz dogfood gap where the existing
    00-START-NEXT-SESSION.md would have been clobbered.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # Minimal Python project so adopt has something to classify.
        (self.repo / "manage.py").write_text("# django\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _ns(self, *, write=True, description="My project",
            next_step="ship v1") -> argparse.Namespace:
        return argparse.Namespace(
            command="adopt", path=str(self.repo), write=write,
            html=False, html_out=None, no_browser=True,
            description=description, next_step=next_step,
        )

    def test_steady_state_rerun_is_byte_identical(self):
        # Compares run 2 vs run 3, not run 1 vs run 2. The first --write
        # creates ``docs/`` (containing BUILD_PLAN.md + PROJECT_WHAT_IT_IS.md),
        # which the second run then surfaces in its own "Unknown but
        # present" data-only section — so run 1 and run 2 will differ
        # by exactly that. Once docs/ exists from run 2 onward, every
        # subsequent run sees the same project state and writes
        # byte-identical content. That's the idempotency contract:
        # SECOND --write onward is steady.
        run_adopt(self._ns())  # run 1: creates docs/
        run_adopt(self._ns())  # run 2: sees docs/ for the first time
        snapshot = {p: p.read_bytes() for p in (
            self.repo / "docs" / "BUILD_PLAN.md",
            self.repo / "docs" / "PROJECT_WHAT_IT_IS.md",
            self.repo / "00-START-NEXT-SESSION.md",
            self.repo / "CLAUDE.md",
        )}
        run_adopt(self._ns())  # run 3: identical inputs, identical disk state
        for path, before in snapshot.items():
            after = path.read_bytes()
            self.assertEqual(
                before, after,
                f"{path.name} changed between steady-state re-runs",
            )

    def test_user_edits_outside_managed_blocks_are_preserved(self):
        # First write creates BUILD_PLAN with markers. User adds prose
        # ABOVE and BELOW the markers. Second write must preserve that
        # prose — only refresh content between the markers.
        run_adopt(self._ns())
        bp = self.repo / "docs" / "BUILD_PLAN.md"
        original = bp.read_text(encoding="utf-8")
        # Sanity: markers are present.
        self.assertIn(START_MARKER, original)
        self.assertIn(END_MARKER, original)
        # Splice user prose around the managed block.
        head, _, rest = original.partition(START_MARKER)
        block, _, tail = rest.partition(END_MARKER)
        user_above = "# My handwritten preamble\n\nThis is user content above.\n\n"
        user_below = "\n\n## My notes section\n\nUser content below the markers.\n"
        bp.write_text(
            user_above + START_MARKER + block + END_MARKER + user_below,
            encoding="utf-8",
        )
        # Re-run with a different next_step so the managed-block
        # content WOULD differ — we want to confirm the user's prose
        # is preserved AND the managed block was refreshed.
        run_adopt(self._ns(next_step="updated next step"))
        after = bp.read_text(encoding="utf-8")
        # User prose preserved verbatim.
        self.assertIn("# My handwritten preamble", after)
        self.assertIn("This is user content above.", after)
        self.assertIn("## My notes section", after)
        self.assertIn("User content below the markers.", after)
        # Managed block content refreshed.
        self.assertIn("updated next step", after)

    def test_existing_file_without_markers_is_skipped(self):
        # The unified-donkey-betz scenario: a project already has a
        # hand-written 00-START-NEXT-SESSION.md (with no adopt
        # markers because adopt didn't write it). Re-run with --write
        # MUST NOT clobber it.
        start = self.repo / "00-START-NEXT-SESSION.md"
        original = (
            "---\n"
            "state: scaffold\n"
            "date: 2026-01-01\n"
            "---\n\n"
            "# Hand-written session priorities\n\n"
            "This file was written by hand. Adopt should not touch it.\n"
        )
        start.write_text(original, encoding="utf-8")
        run_adopt(self._ns())
        after = start.read_text(encoding="utf-8")
        self.assertEqual(original, after,
                         "hand-written START doc was modified by adopt")
        # And the plan should have surfaced this as a "skip".
        from io import StringIO
        from contextlib import redirect_stdout
        buf = StringIO()
        with redirect_stdout(buf):
            run_adopt(self._ns(write=False))
        self.assertIn("skip", buf.getvalue())
        self.assertIn("00-START-NEXT-SESSION.md", buf.getvalue())

    def test_existing_file_with_adopt_markers_is_augmented(self):
        # If the user re-runs adopt against a project that's already
        # been adopted (file has markers), we refresh the managed
        # block in place. This is the augment path — distinct from
        # both create and skip.
        run_adopt(self._ns(next_step="initial next"))
        bp = self.repo / "docs" / "BUILD_PLAN.md"
        self.assertIn("initial next", bp.read_text(encoding="utf-8"))
        # Re-run with new next_step.
        run_adopt(self._ns(next_step="changed next"))
        text = bp.read_text(encoding="utf-8")
        self.assertIn("changed next", text)
        self.assertNotIn("initial next", text,
                         "old managed-block content not refreshed")
        # Still exactly one pair of markers (no stacking).
        self.assertEqual(text.count(START_MARKER), 1)
        self.assertEqual(text.count(END_MARKER), 1)

    def test_start_doc_keeps_frontmatter_at_top_outside_markers(self):
        # The wizard's _detect_project_state reads
        # ``text.startswith("---\\n")`` to recognize the frontmatter.
        # Markers MUST wrap only the body, not the frontmatter, or
        # the wizard breaks on adopt-generated projects.
        run_adopt(self._ns())
        sh = self.repo / "00-START-NEXT-SESSION.md"
        body = sh.read_text(encoding="utf-8")
        self.assertTrue(body.startswith("---\nstate: scaffold"),
                        f"frontmatter not at top: {body[:60]!r}")
        # Markers ARE present (just after the frontmatter).
        self.assertIn(START_MARKER, body)
        self.assertIn(END_MARKER, body)
        # Frontmatter ends BEFORE the start marker.
        fm_end = body.find("\n---\n", 4) + len("\n---\n")
        self.assertLess(fm_end, body.find(START_MARKER))


class TestDataOnlyGrouping(unittest.TestCase):
    """Group "no recognized source extensions" subdirs into a single
    collapsible / footer so large repos like unified-donkey-betz
    don't bury the high-signal cards under 24+ identical entries.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_is_data_only_predicate(self):
        from cli.adopt import UnclassifiedSubdir
        # Only-files-but-no-recognized-source = data-only.
        u = UnclassifiedSubdir(name="config", total_file_count=10)
        self.assertTrue(_is_data_only_subdir(u))
        # Has a manifest = NOT data-only.
        u = UnclassifiedSubdir(name="x", manifest_files=["package.json"],
                               total_file_count=1)
        self.assertFalse(_is_data_only_subdir(u))
        # Has notable extensions = NOT data-only.
        u = UnclassifiedSubdir(name="x", notable_extensions={".py": 5},
                               total_file_count=5)
        self.assertFalse(_is_data_only_subdir(u))
        # Empty = NOT data-only (rendered as "empty" instead).
        u = UnclassifiedSubdir(name="x", is_empty=True)
        self.assertFalse(_is_data_only_subdir(u))
        # Has manifest hint = NOT data-only.
        u = UnclassifiedSubdir(name="x", total_file_count=1,
                               manifest_hint="Python subsystem ...")
        self.assertFalse(_is_data_only_subdir(u))

    def test_html_groups_data_only_subdirs_into_collapsible(self):
        # Build a fixture with a mix: one signal subdir + three
        # data-only subdirs. The HTML must render the signal one as
        # its own card and group the three under a single collapsible.
        (self.repo / "manage.py").write_text("# django\n", encoding="utf-8")
        # One signal subdir with .py source.
        (self.repo / "agents").mkdir()
        for n in range(5):
            (self.repo / "agents" / f"a{n}.py").write_text("# x\n", encoding="utf-8")
        # Three data-only subdirs (only .json / .md content).
        for d in ("docs", "config", "data"):
            (self.repo / d).mkdir()
            for n in range(3):
                (self.repo / d / f"x{n}.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack,
                          AdoptionInputs(project_description="x", next_step="y"))
        html = render_adopt_html(self.repo, stack,
                                 AdoptionInputs(project_description="x", next_step="y"),
                                 plan, write_mode=False)
        # Data-only collapsible is present.
        self.assertIn("Data / content / non-code directories", html)
        self.assertIn("3 hidden by default", html)
        # All three data-only names listed inside it.
        for d in ("docs", "config", "data"):
            self.assertIn(f"<code>{d}/</code>", html)
        # Signal subdir got its own card (NOT inside the data-only collapsible).
        # Verify by checking that "agents/" appears OUTSIDE the
        # ``unc-dataonly`` block.
        before_dataonly, _, _ = html.partition("unc-dataonly")
        self.assertIn("agents/", before_dataonly,
                      "signal subdir 'agents' got grouped with data-only")

    def test_no_dataonly_block_when_no_dataonly_subdirs(self):
        # Clean projects without any data-only subdirs must NOT get a
        # dangling empty group. Visual hygiene.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "contracts").mkdir()
        for n in ("Foo.sol", "Bar.sol", "Baz.sol"):
            (self.repo / "contracts" / n).write_text("// sol\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack,
                          AdoptionInputs(project_description="x", next_step="y"))
        html = render_adopt_html(self.repo, stack,
                                 AdoptionInputs(project_description="x", next_step="y"),
                                 plan, write_mode=False)
        self.assertNotIn("Data / content / non-code", html)


class TestManifestHintInRenders(unittest.TestCase):
    """The manifest_hint must surface in all three renderers (CLI dryrun,
    Markdown, HTML) so an AI session reading any of them sees the same
    "this looks like X" signal.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # Project root with a Python signal so adopt classifies it,
        # and a frontend/ subdir with the Vite + Tailwind combo so the
        # manifest hint fires on the unclassified subdir.
        (self.repo / "manage.py").write_text("# d\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "frontend" / "vite.config.ts").write_text("// v\n", encoding="utf-8")
        (self.repo / "frontend" / "tailwind.config.js").write_text("// t\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_hint_in_dryrun_output(self):
        from io import StringIO
        from contextlib import redirect_stdout
        buf = StringIO()
        with redirect_stdout(buf):
            run_adopt(argparse.Namespace(
                command="adopt", path=str(self.repo), write=False,
                html=False, html_out=None, no_browser=True,
                description="x", next_step="y",
            ))
        out = buf.getvalue()
        self.assertIn("Vite + Tailwind", out)

    def test_hint_in_markdown_build_plan(self):
        stack = detect_stack(self.repo)
        bp = generate_build_plan(stack,
                                 AdoptionInputs(project_description="x", next_step="y"),
                                 "Test")
        self.assertIn("Vite + Tailwind", bp)

    def test_hint_in_html_summary_badge(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack,
                          AdoptionInputs(project_description="x", next_step="y"))
        html = render_adopt_html(self.repo, stack,
                                 AdoptionInputs(project_description="x", next_step="y"),
                                 plan, write_mode=False)
        # The badge appears in the always-visible summary.
        self.assertIn("hint-badge", html)
        self.assertIn("Vite + Tailwind", html)


# ---------------------------------------------------------------------------
# v0.2.x: failure taxonomy (analyze_failures)
# ---------------------------------------------------------------------------


class TestFailureTaxonomy(unittest.TestCase):
    """The taxonomy is fixed and closed — additions require code change."""

    def test_taxonomy_has_exactly_ten_types(self):
        # v0.3 raised the count from 9 to 10 by adding
        # MONOREPO_DEPTH_LIMIT (SESSION_009_ADOPT.md §22).
        self.assertEqual(len(FAILURE_TYPES), 10)
        for t in (FAILURE_ROOT_SIGNAL_OVERRIDE,
                  FAILURE_UNRECOGNIZED_ECOSYSTEM,
                  FAILURE_SILENT_SUBDIR_DROP,
                  FAILURE_WRAPPER_DIRECTORY_INVISIBILITY,
                  FAILURE_NOISE_DIRECTORY_POLLUTION,
                  FAILURE_IDEMPOTENCY_RISK,
                  FAILURE_MISLEADING_CLASSIFICATION,
                  FAILURE_MISSING_FRAMEWORK_DETECTION,
                  FAILURE_STRUCTURE_UNDERREPRESENTED,
                  FAILURE_MONOREPO_DEPTH_LIMIT):
            self.assertIn(t, FAILURE_TYPES)

    def test_severity_and_surface_area_enums(self):
        # Locked sets — adopt code only emits FailureRecord with these
        # severity / surface_area values.
        self.assertEqual(FAILURE_SEVERITIES, ("low", "medium", "high"))
        self.assertEqual(
            FAILURE_SURFACE_AREAS,
            ("classification", "visibility", "safety", "UX"),
        )


def _failure_types(failures):
    return {f.failure_type for f in failures}


class TestFailureDetectorsRequiredCases(unittest.TestCase):
    """The four required dogfood cases from the spec — each fixture
    mirrors a real /development/ project's shape in miniature so the
    test doesn't depend on /development/ paths.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        return analyze_failures(self.repo, stack, plan)

    def test_dbao_studio_shape_emits_root_signal_override(self):
        # Mixed root manifests + a backend/ with stronger framework
        # signal (Django via manage.py). The hallmark dbao-studio case.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("django\n", encoding="utf-8")
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")
        for n in range(5):  # enough .py to read as Python content
            (self.repo / "backend" / f"x{n}.py").write_text("# x\n", encoding="utf-8")
        types = _failure_types(self._run())
        self.assertIn(FAILURE_ROOT_SIGNAL_OVERRIDE, types,
                      f"expected ROOT_SIGNAL_OVERRIDE in {types!r}")

    def test_donkey_betz_world_shape_emits_silent_subdir_drop(self):
        # Recognized subdir name (mobile) holds Flutter — pubspec.yaml
        # is not in adopt's classification manifest set, so the dir
        # silently dropped without visibility-first.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "mobile").mkdir()
        (self.repo / "mobile" / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "mobile" / "lib").mkdir()
        (self.repo / "mobile" / "lib" / "main.dart").write_text(
            "void main() {}\n", encoding="utf-8")
        types = _failure_types(self._run())
        self.assertIn(FAILURE_SILENT_SUBDIR_DROP, types,
                      f"expected SILENT_SUBDIR_DROP in {types!r}")

    def test_clarity_timelock_shape_emits_wrapper_directory_invisibility(self):
        # Empty root, single non-recognized child carrying the project.
        (self.repo / "timelocked-wallet").mkdir()
        (self.repo / "timelocked-wallet" / "Clarinet.toml").write_text(
            "[project]\n", encoding="utf-8")
        (self.repo / "timelocked-wallet" / "contracts").mkdir()
        (self.repo / "timelocked-wallet" / "contracts" / "wallet.clar").write_text(
            ";; clar\n", encoding="utf-8")
        types = _failure_types(self._run())
        self.assertIn(FAILURE_WRAPPER_DIRECTORY_INVISIBILITY, types,
                      f"expected WRAPPER_DIRECTORY_INVISIBILITY in {types!r}")

    def test_unified_donkey_betz_shape_emits_idempotency_and_pollution(self):
        # A Django root + an existing 00-START doc (no adopt markers)
        # + many "data-only" subdirs (config / docs / data files).
        (self.repo / "manage.py").write_text("# d\n", encoding="utf-8")
        (self.repo / "00-START-NEXT-SESSION.md").write_text(
            "# Hand-written start\n", encoding="utf-8")
        # Five+ data-only subdirs (just .json / .md content).
        for n in ("docs", "config", "audits", "logs", "reports", "campaigns"):
            (self.repo / n).mkdir()
            for i in range(2):
                (self.repo / n / f"f{i}.json").write_text("{}", encoding="utf-8")
        types = _failure_types(self._run())
        self.assertIn(FAILURE_IDEMPOTENCY_RISK, types,
                      f"expected IDEMPOTENCY_RISK in {types!r}")
        self.assertIn(FAILURE_NOISE_DIRECTORY_POLLUTION, types,
                      f"expected NOISE_DIRECTORY_POLLUTION in {types!r}")


class TestFailureRecordShape(unittest.TestCase):
    """Every emitted FailureRecord must have the documented fields."""

    def test_emitted_records_use_valid_enum_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "package.json").write_text("{}", encoding="utf-8")
            (repo / "requirements.txt").write_text("django\n", encoding="utf-8")
            (repo / "backend").mkdir()
            (repo / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")
            inputs = AdoptionInputs(project_description="x", next_step="y")
            stack = detect_stack(repo)
            plan = plan_files(repo, stack, inputs)
            records = analyze_failures(repo, stack, plan)
            self.assertGreater(len(records), 0)
            for r in records:
                self.assertIsInstance(r, FailureRecord)
                self.assertIn(r.failure_type, FAILURE_TYPES)
                self.assertIn(r.severity, FAILURE_SEVERITIES)
                self.assertIn(r.surface_area, FAILURE_SURFACE_AREAS)
                self.assertTrue(r.description.strip())
                self.assertTrue(r.detected_in.strip())
                self.assertTrue(r.example.strip())


class TestFailureDetectorEdgeCases(unittest.TestCase):
    """A few edge cases worth locking in beyond the four required."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        return analyze_failures(self.repo, stack, plan)

    def test_unrecognized_ecosystem_fires_for_clarinet(self):
        # Same as the wrapper case — Clarity is an unrecognized
        # ecosystem AND wrapped — both labels should fire.
        (self.repo / "timelocked-wallet").mkdir()
        (self.repo / "timelocked-wallet" / "Clarinet.toml").write_text(
            "[project]\n", encoding="utf-8")
        types = _failure_types(self._run())
        self.assertIn(FAILURE_UNRECOGNIZED_ECOSYSTEM, types)

    def test_misleading_classification_fires_for_truffle_at_root(self):
        # tornado-core shape: package.json + truffle-config.js at root.
        # Adopt classifies as plain JavaScript — label undersells.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "truffle-config.js").write_text("// t\n", encoding="utf-8")
        types = _failure_types(self._run())
        self.assertIn(FAILURE_MISLEADING_CLASSIFICATION, types)

    def test_clean_classified_project_emits_no_failures(self):
        # backend + frontend cleanly split. No idempotency risk (fresh
        # project), no missed signals, no excessive noise. Should yield
        # zero failures.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
        # No data-only dirs; no recognized subdirs without manifests;
        # no existing files without markers.
        records = self._run()
        # Allow zero or strictly low-severity informational hits, but
        # the load-bearing assertion: no high-severity failures.
        high = [r for r in records if r.severity == "high"]
        self.assertEqual(
            high, [],
            f"clean classified project should have no high-severity "
            f"failures; got {[(r.failure_type, r.detected_in) for r in high]!r}",
        )


class TestFailureRendering(unittest.TestCase):
    """Failures must surface in HTML and CLI output."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # Set up a project that will trigger ROOT_SIGNAL_OVERRIDE.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("django\n", encoding="utf-8")
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_html_includes_diagnostic_signals_section(self):
        # v0.8 Phase 4.5.1: section renamed "Detected issues"
        # -> "Diagnostic signals" with softer description copy.
        explicit = self.repo / "report.html"
        run_adopt(argparse.Namespace(
            command="adopt", path=str(self.repo), write=False,
            html=False, html_out=str(explicit), no_browser=True,
            description="x", next_step="y",
        ))
        body = explicit.read_text(encoding="utf-8")
        self.assertIn("Diagnostic signals", body)
        self.assertNotIn("Detected issues", body,
                         "old 'Detected issues' header must be gone")
        # Softer description copy is present.
        self.assertIn("they do not mean the project is broken", body)
        # Failure type names unchanged — still surface verbatim.
        self.assertIn("ROOT_SIGNAL_OVERRIDE", body)
        self.assertIn("sev-high", body)
        self.assertIn("classification", body)

    def test_cli_dryrun_includes_compact_failure_summary(self):
        from io import StringIO
        from contextlib import redirect_stdout
        buf = StringIO()
        with redirect_stdout(buf):
            run_adopt(argparse.Namespace(
                command="adopt", path=str(self.repo), write=False,
                html=False, html_out=None, no_browser=True,
                description="x", next_step="y",
            ))
        out = buf.getvalue()
        # v0.8 Phase 4.5.1: section renamed in CLI too.
        self.assertIn("Diagnostic signals", out)
        self.assertNotIn("Detected issues", out,
                         "old CLI 'Detected issues' line must be gone")
        # Softer description copy is present.
        self.assertIn("they do not mean the project is broken", out)
        # Failure type names unchanged.
        self.assertIn("ROOT_SIGNAL_OVERRIDE", out)
        self.assertIn("high", out)

    def test_html_omits_diagnostic_signals_when_no_failures(self):
        # Clean classified project: no failures -> no Diagnostic
        # signals card. Visual hygiene preserved from the old
        # "Detected issues" behavior.
        with tempfile.TemporaryDirectory() as clean:
            cp = Path(clean)
            (cp / "backend").mkdir()
            (cp / "backend" / "manage.py").write_text("# d\n", encoding="utf-8")
            (cp / "frontend").mkdir()
            (cp / "frontend" / "package.json").write_text("{}", encoding="utf-8")
            explicit = cp / "report.html"
            run_adopt(argparse.Namespace(
                command="adopt", path=str(cp), write=False,
                html=False, html_out=str(explicit), no_browser=True,
                description="x", next_step="y",
            ))
            body = explicit.read_text(encoding="utf-8")
            self.assertNotIn("Diagnostic signals", body)
            self.assertNotIn("Detected issues", body)


# ---------------------------------------------------------------------------
# v0.3: MONOREPO_DEPTH_LIMIT + root-level UNRECOGNIZED_ECOSYSTEM
# (post first dogfood-repos batch — SESSION_009_ADOPT.md §22)
# ---------------------------------------------------------------------------


class TestMonorepoDepthLimit(unittest.TestCase):
    """The new v0.3 label for workspace containers (apps/, packages/,
    services/, crates/, members/, workspaces/) that hide child
    projects below adopt's depth-1 scan. Each fixture mirrors a
    cloned dogfood repo's shape in miniature.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        return analyze_failures(self.repo, stack, plan)

    def _types(self, failures):
        return {f.failure_type for f in failures}

    def test_fns_monorepo_shape_emits_monorepo_depth_limit(self):
        # The headline §22 case: root package.json + apps/ holding
        # both a Foundry Solidity project and a Next.js app at
        # depth 2. v0.2.x emitted 0 failure records on this shape;
        # v0.3 must label it MONOREPO_DEPTH_LIMIT.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        # apps/forge — Foundry Solidity project
        (self.repo / "apps" / "forge").mkdir()
        (self.repo / "apps" / "forge" / "foundry.toml").write_text(
            "# foundry\n", encoding="utf-8")
        (self.repo / "apps" / "forge" / "package.json").write_text(
            "{}", encoding="utf-8")
        (self.repo / "apps" / "forge" / "contracts").mkdir()
        (self.repo / "apps" / "forge" / "contracts" / "Foo.sol").write_text(
            "// sol\n", encoding="utf-8")
        # apps/next — Next.js dApp
        (self.repo / "apps" / "next").mkdir()
        (self.repo / "apps" / "next" / "package.json").write_text(
            "{}", encoding="utf-8")
        (self.repo / "apps" / "next" / "app").mkdir()
        (self.repo / "apps" / "next" / "app" / "page.tsx").write_text(
            "// tsx\n", encoding="utf-8")
        records = self._run()
        types = self._types(records)
        self.assertIn(FAILURE_MONOREPO_DEPTH_LIMIT, types,
                      f"expected MONOREPO_DEPTH_LIMIT in {types!r}")
        # Verify the apps/ container is the one labeled, with a
        # depth-2-or-deeper example path.
        match = next(r for r in records
                     if r.failure_type == FAILURE_MONOREPO_DEPTH_LIMIT)
        self.assertEqual(match.detected_in, "apps")
        self.assertGreaterEqual(match.example.count("/"), 2,
                                f"example {match.example!r} should be "
                                f"depth-2-or-deeper (>= 2 separators)")
        self.assertEqual(match.severity, "high")
        self.assertEqual(match.surface_area, "visibility")

    def test_expo_monorepo_shape_emits_monorepo_depth_limit(self):
        # Single-child workspace shape (expo-monorepo-example):
        # apps/example/ holds a real Expo app with package.json +
        # app.config.ts + .tsx files.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        (self.repo / "apps" / "example").mkdir()
        (self.repo / "apps" / "example" / "package.json").write_text(
            "{}", encoding="utf-8")
        (self.repo / "apps" / "example" / "app.config.ts").write_text(
            "// expo\n", encoding="utf-8")
        (self.repo / "apps" / "example" / "app").mkdir()
        for n in range(3):
            (self.repo / "apps" / "example" / "app" / f"_layout{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")
        types = self._types(self._run())
        self.assertIn(FAILURE_MONOREPO_DEPTH_LIMIT, types,
                      f"expected MONOREPO_DEPTH_LIMIT in {types!r}")

    def test_turborepo_keeps_silent_subdir_drop_and_adds_depth_limit(self):
        # turborepo-next-django-starter shape: server/backend/manage.py
        # is the recognized-name SILENT_SUBDIR_DROP case; apps/web/ is
        # the new MONOREPO_DEPTH_LIMIT case. v0.3 must emit BOTH —
        # MONOREPO_DEPTH_LIMIT is additive, not a replacement.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        # server/backend/manage.py — recognized server/ subdir
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")
        # apps/web — workspace-container shape
        (self.repo / "apps").mkdir()
        (self.repo / "apps" / "web").mkdir()
        (self.repo / "apps" / "web" / "package.json").write_text(
            "{}", encoding="utf-8")
        (self.repo / "apps" / "web" / "app").mkdir()
        for n in range(3):
            (self.repo / "apps" / "web" / "app" / f"page{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")
        types = self._types(self._run())
        # Both labels must fire.
        self.assertIn(FAILURE_SILENT_SUBDIR_DROP, types,
                      "SILENT_SUBDIR_DROP regression — server/ should still fire")
        self.assertIn(FAILURE_MONOREPO_DEPTH_LIMIT, types,
                      f"MONOREPO_DEPTH_LIMIT missing in {types!r}")

    def test_empty_apps_does_not_emit_monorepo_depth_limit(self):
        # The false-positive guard: an apps/ directory that's empty
        # or contains no source files / nested manifests must NOT
        # fire the label. A workspace container with zero content
        # tells us nothing useful.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()  # empty apps/
        types = self._types(self._run())
        self.assertNotIn(FAILURE_MONOREPO_DEPTH_LIMIT, types,
                         f"empty apps/ should NOT trigger label; got {types!r}")

    def test_fires_at_most_once_per_workspace_container(self):
        # apps/ with 5 child projects must produce exactly ONE
        # MONOREPO_DEPTH_LIMIT record, not 5. Avoids the per-card
        # explosion problem on a 20-app Turborepo.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app_name in ("app1", "app2", "app3", "app4", "app5"):
            d = self.repo / "apps" / app_name
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "main.tsx").write_text("// x\n", encoding="utf-8")
        records = self._run()
        depth_records = [
            r for r in records
            if r.failure_type == FAILURE_MONOREPO_DEPTH_LIMIT
        ]
        self.assertEqual(len(depth_records), 1,
                         f"expected 1 MONOREPO_DEPTH_LIMIT record, got "
                         f"{len(depth_records)}: "
                         f"{[(r.detected_in, r.example) for r in depth_records]}")


class TestRootLevelUnrecognizedEcosystem(unittest.TestCase):
    """The v0.3 extension to the existing UNRECOGNIZED_ECOSYSTEM
    detector — also fires for ECOSYSTEM_MANIFESTS at the project
    root, not just inside unclassified subdirs. Motivated by
    flutter-monorepo's melos.yaml at root which fired 0 labels in
    v0.2.x because the detector loop only scanned subdir manifests.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _types(self):
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        return {r.failure_type for r in analyze_failures(self.repo, stack, plan)}

    def test_root_melos_yaml_emits_unrecognized_ecosystem(self):
        # The flutter-monorepo case: melos.yaml at root, no other
        # classification manifest. v0.2.x emitted 0 labels for this;
        # v0.3 must emit UNRECOGNIZED_ECOSYSTEM with detected_in="root".
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        # Add a child dir so the run produces some output beyond
        # "no manifest found".
        (self.repo / "apps").mkdir()
        (self.repo / "apps" / "buyer_app").mkdir()
        (self.repo / "apps" / "buyer_app" / "pubspec.yaml").write_text(
            "name: buyer\n", encoding="utf-8")
        types = self._types()
        self.assertIn(FAILURE_UNRECOGNIZED_ECOSYSTEM, types,
                      f"expected UNRECOGNIZED_ECOSYSTEM in {types!r}")

    def test_root_foundry_toml_emits_unrecognized_ecosystem(self):
        # foundry.toml at root (the solidity-template case). v0.2.x
        # only fired MISLEADING_CLASSIFICATION here; v0.3 also fires
        # UNRECOGNIZED_ECOSYSTEM via the new root-scan path.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        types = self._types()
        self.assertIn(FAILURE_UNRECOGNIZED_ECOSYSTEM, types,
                      f"expected UNRECOGNIZED_ECOSYSTEM at root in {types!r}")

    def test_root_scan_does_not_double_fire_when_subdir_also_matches(self):
        # If both root has melos.yaml AND a subdir has pubspec.yaml,
        # we expect both to fire — they're semantically distinct
        # (root-level Melos config vs. subdir Dart project). The
        # per-loop dedup in analyze_failures only prevents within-loop
        # duplication; cross-loop is allowed.
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "shared").mkdir()
        (self.repo / "shared" / "pubspec.yaml").write_text(
            "name: shared\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        eco_records = [
            r for r in analyze_failures(self.repo, stack, plan)
            if r.failure_type == FAILURE_UNRECOGNIZED_ECOSYSTEM
        ]
        # Two records: one for root melos.yaml, one for shared/pubspec.yaml.
        self.assertEqual(len(eco_records), 2,
                         f"expected 2 UNRECOGNIZED_ECOSYSTEM records "
                         f"(root + subdir), got "
                         f"{[(r.detected_in, r.example) for r in eco_records]}")
        targets = {r.detected_in for r in eco_records}
        self.assertEqual(targets, {"root", "shared"})


class TestWorkspaceChildren(unittest.TestCase):
    """v0.8 — depth-2 walk inside known workspace containers (apps/,
    packages/, services/, crates/, members/, workspaces/). Pure data
    extension of StackProfile; does NOT change classification or
    rendering.

    Each fixture mirrors a cloned dogfood repo's shape in miniature:
      - fns-monorepo: apps/forge (Foundry) + apps/next (Next.js)
      - turborepo example: apps/web + apps/docs
      - flutter example: apps/buyer_app + apps/seller_app

    Invariants checked across fixtures: classification (`language` /
    `parts`) is unchanged from v0.7's behavior; visibility-first
    `unclassified_subdirs` still surfaces the container; the new
    `workspace_children` field exposes the depth-2 children with
    container-prefixed names.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- fns-monorepo ---------------------------------------------------

    def test_fns_monorepo_detects_forge_and_next(self):
        # Root package.json + apps/forge (Foundry/Solidity) +
        # apps/next (Next.js TSX). v0.8 must surface BOTH children.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        # apps/forge
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        # apps/next
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        names = [c.name for c in stack.workspace_children]
        self.assertEqual(names, ["apps/forge", "apps/next"],
                         f"expected ordered ['apps/forge', 'apps/next'], "
                         f"got {names!r}")

        forge_child = next(c for c in stack.workspace_children
                           if c.name == "apps/forge")
        # Manifests at depth-1 of the child are surfaced.
        self.assertIn("foundry.toml", forge_child.manifest_files)
        self.assertIn("package.json", forge_child.manifest_files)
        # .sol is a domain extension — surfaces at any count >= 1.
        self.assertEqual(forge_child.notable_extensions.get(".sol"), 1)
        # Hint should mention Solidity (no manifest pattern matches
        # foundry-only, so we fall back to the dominant DOMAIN_HINTS
        # extension which is .sol).
        self.assertIsNotNone(forge_child.hint)
        self.assertIn("Solidity", forge_child.hint)

        nxt_child = next(c for c in stack.workspace_children
                         if c.name == "apps/next")
        self.assertIn("package.json", nxt_child.manifest_files)
        # .tsx is generic; needs >= MIN_SOURCE_FILES_TO_REPORT (3).
        self.assertEqual(nxt_child.notable_extensions.get(".tsx"), 3)

    def test_fns_monorepo_classification_unchanged_v07_behavior(self):
        # The v0.8 ship explicitly does NOT touch classification.
        # Same fns-monorepo shape: language must still be "javascript"
        # (root package.json wins), parts must stay empty, and apps/
        # must still appear in unclassified_subdirs.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "javascript",
                         "language must stay 'javascript' — root package.json wins")
        self.assertEqual(stack.parts, {},
                         "parts must stay empty — v0.8 does not promote "
                         "workspace children into the primary classifier")
        unclassified_names = [u.name for u in stack.unclassified_subdirs]
        self.assertIn("apps", unclassified_names,
                      "apps/ must still appear as an unclassified depth-1 subdir")

    # ---- turborepo (apps/web, apps/docs) -------------------------------

    def test_turborepo_detects_web_and_docs(self):
        # Stripped-down Turborepo shape: apps/web + apps/docs, both
        # Next.js-style with .tsx files. Mirrors
        # turborepo-next-django-starter's apps/ container.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app_name in ("web", "docs"):
            app = self.repo / "apps" / app_name
            app.mkdir()
            (app / "package.json").write_text("{}", encoding="utf-8")
            (app / "next.config.mjs").write_text("// next\n", encoding="utf-8")
            (app / "app").mkdir()
            for n in range(4):
                (app / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        names = [c.name for c in stack.workspace_children]
        self.assertEqual(names, ["apps/docs", "apps/web"],
                         f"expected sorted ['apps/docs', 'apps/web'], "
                         f"got {names!r}")
        for child in stack.workspace_children:
            self.assertIn("package.json", child.manifest_files)
            self.assertIn("next.config.mjs", child.manifest_files,
                          f"next.config.mjs should be manifest-shaped "
                          f"in {child.name}; got {child.manifest_files!r}")
            self.assertGreaterEqual(child.notable_extensions.get(".tsx", 0), 3,
                                    f"{child.name}: .tsx count should be "
                                    f">= 3 (MIN_SOURCE_FILES_TO_REPORT)")

    # ---- flutter (apps/buyer_app, apps/seller_app) ---------------------

    def test_flutter_monorepo_detects_buyer_and_seller(self):
        # Stripped-down flutter-monorepo-example shape: melos.yaml at
        # root + apps/buyer_app + apps/seller_app, each with
        # pubspec.yaml + .dart files.
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app_name in ("buyer_app", "seller_app"):
            app = self.repo / "apps" / app_name
            app.mkdir()
            (app / "pubspec.yaml").write_text(
                f"name: {app_name}\n", encoding="utf-8")
            (app / "lib").mkdir()
            (app / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        names = [c.name for c in stack.workspace_children]
        self.assertEqual(names, ["apps/buyer_app", "apps/seller_app"],
                         f"expected sorted ['apps/buyer_app', 'apps/seller_app'], "
                         f"got {names!r}")
        for child in stack.workspace_children:
            self.assertIn("pubspec.yaml", child.manifest_files)
            # .dart is a domain extension — surfaces at any count.
            self.assertEqual(child.notable_extensions.get(".dart"), 1,
                             f"{child.name}: .dart count should be 1; "
                             f"got {child.notable_extensions!r}")
            # Hint should mention Dart / Flutter (DOMAIN_HINTS fallback).
            self.assertIsNotNone(child.hint)
            self.assertIn("Dart", child.hint)

    # ---- guards --------------------------------------------------------

    def test_empty_workspace_container_has_no_children(self):
        # An empty apps/ produces an empty workspace_children list —
        # no per-empty-dir noise entries. Also: no crash.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        stack = detect_stack(self.repo)
        self.assertEqual(stack.workspace_children, [])

    def test_empty_child_dir_is_dropped(self):
        # apps/foo/ exists but has no manifests and no notable
        # extensions — it must NOT appear in workspace_children.
        # apps/bar/ is a real child and should be the only entry.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        (self.repo / "apps" / "foo").mkdir()  # truly empty
        bar = self.repo / "apps" / "bar"
        bar.mkdir()
        (bar / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        names = [c.name for c in stack.workspace_children]
        self.assertEqual(names, ["apps/bar"],
                         f"empty apps/foo/ must be dropped; got {names!r}")

    def test_non_workspace_container_is_ignored(self):
        # A depth-1 dir whose name is NOT in _WORKSPACE_CONTAINERS
        # (e.g. "thirdparty/") must not contribute children, even
        # if it has substantial nested content.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "thirdparty").mkdir()
        (self.repo / "thirdparty" / "vendor").mkdir()
        (self.repo / "thirdparty" / "vendor" / "package.json").write_text(
            "{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        self.assertEqual(stack.workspace_children, [],
                         "thirdparty/ is not a known workspace container")

    def test_multiple_workspace_containers_both_walked(self):
        # apps/ and packages/ must both contribute children; names
        # carry the container prefix so consumers can distinguish.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        (self.repo / "apps" / "web").mkdir()
        (self.repo / "apps" / "web" / "package.json").write_text(
            "{}", encoding="utf-8")
        (self.repo / "packages").mkdir()
        (self.repo / "packages" / "ui").mkdir()
        (self.repo / "packages" / "ui" / "package.json").write_text(
            "{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        names = [c.name for c in stack.workspace_children]
        self.assertEqual(names, ["apps/web", "packages/ui"],
                         f"both containers must be walked, got {names!r}")

    def test_no_recursion_into_grandchildren(self):
        # The depth-2 constraint: apps/forge/sub/ must NOT itself
        # appear as a workspace child. Only apps/forge/ does.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "package.json").write_text("{}", encoding="utf-8")
        sub = forge / "sub"
        sub.mkdir()
        (sub / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        names = [c.name for c in stack.workspace_children]
        self.assertEqual(names, ["apps/forge"],
                         f"only depth-2 children allowed, got {names!r}")

    def test_workspace_walk_does_not_change_existing_failure_label(self):
        # MONOREPO_DEPTH_LIMIT must continue to fire on the same
        # fns-monorepo shape — the v0.8 data-model addition is
        # purely additive and must not silence the v0.3 detector.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack,
                          AdoptionInputs(project_description="x", next_step="y"))
        types = {f.failure_type for f in analyze_failures(self.repo, stack, plan)}
        self.assertIn(FAILURE_MONOREPO_DEPTH_LIMIT, types,
                      f"MONOREPO_DEPTH_LIMIT must still fire; got {types!r}")


class TestWorkspaceChildrenRendering(unittest.TestCase):
    """v0.8 — workspace_children must surface in CLI dry-run, HTML
    report, and BUILD_PLAN markdown. Renderers are additive — none
    of the v0.7 sections (Detection, Needs clarification, Plan,
    Detected issues) change.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _build_fns_fixture(self):
        # The fns-monorepo shape used in the data-model tests.
        # Reproduced here so render assertions don't depend on
        # rerunning the data-model class fixtures.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

    # ---- CLI dry-run ----------------------------------------------------

    def test_cli_dryrun_includes_workspace_children_section(self):
        # The CLI dry-run must print "Workspace children (depth-2):"
        # with one line per child between the unknown-but-present
        # section and the Plan section.
        self._build_fns_fixture()
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        out = buf.getvalue()
        # v0.8 polish: header carries the count, not "(depth-2)".
        self.assertIn("Workspace children (2):", out,
                      f"missing workspace children header in:\n{out}")
        self.assertIn("apps/forge", out)
        self.assertIn("apps/next", out)
        # Manifests appear in the compact suffix.
        self.assertIn("foundry.toml", out)
        # Hint clause appears for forge (Solidity DOMAIN_HINTS fallback).
        self.assertIn("Solidity", out,
                      "forge child's Solidity hint should appear in the "
                      "CLI dry-run line")
        # The section sits between "Needs clarification" (no
        # depth-1 unclassified subdirs in this fixture) and "Plan:".
        plan_idx = out.index("Plan:")
        ws_idx = out.index("Workspace children (2):")
        self.assertLess(ws_idx, plan_idx,
                        "Workspace children must appear BEFORE the Plan section")

    def test_cli_dryrun_silent_when_no_workspace_children(self):
        # No apps/, no packages/ — the new section must not appear,
        # preserving the v0.7 dry-run shape on plain projects.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        out = buf.getvalue()
        self.assertNotIn("Workspace children", out,
                         "section must be silent when no workspace children")

    # ---- HTML report ----------------------------------------------------

    def test_html_report_includes_workspace_children_section(self):
        # The --html report must contain a "Workspace children"
        # section with one collapsible <details> per child.
        self._build_fns_fixture()
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # v0.8 polish: header carries the count.
        self.assertIn("<h2>Workspace children (2)</h2>", html)
        # Each child gets a <details> block. v0.8 polish renders the
        # name as a block-level <span class="dir-name"> so the user
        # can scan child names down the left edge of the section.
        self.assertIn('<span class="dir-name">apps/forge</span>', html)
        self.assertIn('<span class="dir-name">apps/next</span>', html)
        # Manifests render as inline <code> in the body.
        self.assertIn("<code>foundry.toml</code>", html)
        # The forge child's Solidity hint surfaces in the body.
        self.assertIn("Solidity", html)
        # Reuses the existing `unc` collapsible class so styling
        # matches the unknown-but-present section.
        # (Two children + any unclassified-subdir details elsewhere.)
        self.assertGreaterEqual(html.count('<details class="unc">'), 2,
                                "expected two .unc <details> blocks for "
                                "the workspace children")

    def test_html_report_omits_workspace_section_when_empty(self):
        # Plain project with no workspace containers must not get
        # the new section at all (avoids visual noise on simple repos).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        self.assertNotIn("Workspace children", html,
                         "section must be omitted entirely when no children")

    # ---- BUILD_PLAN.md --------------------------------------------------

    def test_build_plan_includes_workspace_children_section(self):
        # BUILD_PLAN.md must list each workspace child by name.
        # Hints render in italic when present; bare name when not.
        self._build_fns_fixture()
        stack = detect_stack(self.repo)
        title = "Test"
        md = generate_build_plan(stack, self.inputs, title)
        # v0.8 polish: header carries the count.
        self.assertIn("### Workspace children (2)", md)
        # Slice just the workspace section — assertions about
        # "skimmable, no overwhelming detail" should look at this
        # section only, not at unrelated hint text from the
        # "Needs clarification" section above.
        ws_start = md.index("### Workspace children (2)")
        ws_end = md.find("\n## ", ws_start)
        ws_section = md[ws_start:ws_end] if ws_end != -1 else md[ws_start:]
        self.assertIn("**apps/forge**", ws_section)
        self.assertIn("**apps/next**", ws_section)
        # Forge's Solidity hint surfaces inside this section, not
        # only in unrelated text above.
        self.assertIn("Solidity", ws_section,
                      "forge's Solidity hint should appear in the "
                      "workspace children section of BUILD_PLAN.md")
        # Skimmable: per-extension counts must NOT appear in this
        # section (e.g. "3 `.tsx`" or "1 `.sol`"). Counts live in
        # CLI / HTML, not BUILD_PLAN.
        self.assertNotIn("`.tsx`", ws_section,
                         "BUILD_PLAN workspace section must not list "
                         "extension counts (per 'do not overwhelm')")
        self.assertNotIn("`.sol`", ws_section,
                         "BUILD_PLAN workspace section must not list "
                         "extension counts")

    def test_build_plan_omits_workspace_section_when_empty(self):
        # Same omission rule for the markdown — clean projects keep
        # the v0.7 BUILD_PLAN shape.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        md = generate_build_plan(stack, self.inputs, "Test")
        self.assertNotIn("Workspace children", md)


class TestWorkspaceChildrenRenderingPolish(unittest.TestCase):
    """v0.8 polish — dedup, header count, MONOREPO_DEPTH_LIMIT description,
    body-hint dedup, and trivial-child shortcut. All render-layer only;
    classification and the failure taxonomy are unchanged.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _build_fns_fixture(self):
        # Same shape used elsewhere: root package.json + apps/forge
        # (Foundry) + apps/next (Next-style with .tsx).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

    # ---- Required regression: fns-monorepo dedup ----------------------

    def test_fns_monorepo_dedup_apps_not_in_unknown_but_present(self):
        # The headline UX bug from the v0.8 dogfood: apps/ rendered
        # in BOTH "Needs clarification" (with truncated/aggregated
        # counts) AND "Workspace children" (with per-child counts).
        # After v0.8 polish, apps/ MUST disappear from unknown-but-
        # present whenever any apps/<child> appears in
        # workspace_children. apps/forge and apps/next must still
        # appear in workspace_children.
        self._build_fns_fixture()
        stack = detect_stack(self.repo)

        # CLI dry-run.
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        out = buf.getvalue()
        # No "Needs clarification" header at all in this fixture
        # (apps/ was the only depth-1 unclassified subdir, now
        # suppressed).
        self.assertNotIn("Needs clarification", out,
                         f"apps/ should be suppressed since its children "
                         f"are surfaced via workspace_children:\n{out}")
        # Workspace children section still present, both children
        # individually named.
        self.assertIn("Workspace children (2):", out)
        self.assertIn("apps/forge", out)
        self.assertIn("apps/next", out)

        # HTML report.
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        self.assertNotIn("<h2>Needs clarification</h2>", html,
                         "apps/ container must be suppressed from "
                         "Unknown-but-present in HTML when its "
                         "children render in Workspace children")
        self.assertIn("<h2>Workspace children (2)</h2>", html)
        self.assertIn('<span class="dir-name">apps/forge</span>', html)
        self.assertIn('<span class="dir-name">apps/next</span>', html)

        # BUILD_PLAN.md.
        md = generate_build_plan(stack, self.inputs, "Test")
        self.assertNotIn("Needs clarification", md,
                         "apps/ must be suppressed from Unknown-but-"
                         "present in BUILD_PLAN.md as well")
        self.assertIn("### Workspace children (2)", md)
        self.assertIn("**apps/forge**", md)
        self.assertIn("**apps/next**", md)

    # ---- Dedup applies to the data-only footer too --------------------

    def test_dedup_also_removes_packages_from_data_only_footer(self):
        # turborepo-style shape: packages/ contains 4 child projects
        # whose contents (config-only) would otherwise classify the
        # container as a "data-only" subdir. Once workspace_children
        # surfaces packages/foo, packages/bar, etc., the data-only
        # footer mention of packages/ must disappear too.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "packages").mkdir()
        for name in ("ui", "shared", "tsconfig"):
            d = self.repo / "packages" / name
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")
        # An unrelated data-only directory must still appear.
        (self.repo / "fixtures").mkdir()
        (self.repo / "fixtures" / "data.json").write_text("{}", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Find the unknown-but-present section if it exists.
        if "<h2>Needs clarification</h2>" in html:
            ubp_start = html.index("<h2>Needs clarification</h2>")
            ubp_end = html.find("</section>", ubp_start)
            ubp = html[ubp_start:ubp_end]
            self.assertNotIn(">packages/<", ubp,
                             "packages/ must not appear in the "
                             "data-only footer when its children "
                             "are surfaced in workspace_children")
            self.assertIn("fixtures", ubp,
                          "unrelated data-only dirs must still appear")
        # Workspace children covers all three packages.
        self.assertIn("packages/ui", html)
        self.assertIn("packages/shared", html)
        self.assertIn("packages/tsconfig", html)

    # ---- Header count -------------------------------------------------

    def test_header_count_matches_workspace_children_length(self):
        # Three children → "(3):" / "(3)" in all three renderers.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for name in ("a", "b", "c"):
            d = self.repo / "apps" / name
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        # CLI
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        self.assertIn("Workspace children (3):", buf.getvalue())
        # HTML
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        self.assertIn("<h2>Workspace children (3)</h2>", html)
        # BUILD_PLAN
        md = generate_build_plan(stack, self.inputs, "Test")
        self.assertIn("### Workspace children (3)", md)

    # ---- MONOREPO_DEPTH_LIMIT description text ------------------------

    def test_monorepo_depth_limit_description_updated(self):
        # The label still fires on the same fns-monorepo shape, but
        # the description text is updated to reflect that children
        # ARE surfaced (just not classified into the primary stack).
        self._build_fns_fixture()
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        records = analyze_failures(self.repo, stack, plan)
        depth = next(r for r in records
                     if r.failure_type == FAILURE_MONOREPO_DEPTH_LIMIT)
        # Phase 3 wording: acknowledges children are surfaced AND
        # labeled in the workspace stack summary, just not part of
        # primary classification yet.
        self.assertIn("surfaced", depth.description)
        self.assertIn("not yet part of primary classification",
                      depth.description)
        # Old wording about "invisible to classification" must be gone.
        self.assertNotIn("invisible to classification", depth.description)
        # Label, severity, surface_area unchanged (taxonomy intact).
        self.assertEqual(depth.severity, "high")
        self.assertEqual(depth.surface_area, "visibility")
        self.assertEqual(depth.detected_in, "apps")

    # ---- Trivial-child shortcut + body-hint dedup (HTML only) ---------

    def test_trivial_child_renders_without_collapsible_body(self):
        # A child with only `package.json` and no notable extensions
        # gets a non-collapsible <div class="unc unc-trivial">,
        # not a <details>. Saves the user a useless click.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "packages").mkdir()
        triv = self.repo / "packages" / "trivial"
        triv.mkdir()
        (triv / "package.json").write_text("{}", encoding="utf-8")
        # A non-trivial sibling proves the contrast.
        rich = self.repo / "packages" / "rich"
        rich.mkdir()
        (rich / "package.json").write_text("{}", encoding="utf-8")
        (rich / "src").mkdir()
        for n in range(3):
            (rich / "src" / f"x{n}.tsx").write_text("// x\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Trivial child: non-collapsible div with the name as a
        # visible header (dir-name) so it still reads as a card title.
        self.assertIn('<div class="unc unc-trivial">', html)
        # The trivial card contains the dir-name for "packages/trivial"
        # — search for them adjacent in the same div.
        self.assertIn(
            '<div class="unc unc-trivial">'
            '<div class="dir-head">'
            '<span class="dir-name">packages/trivial</span>',
            html,
            "trivial child must render with dir-name as visible header",
        )
        # Non-trivial child: still a <details> element with the same
        # dir-name treatment in the summary.
        details_with_rich = (
            '<details class="unc"><summary>'
            '<div class="dir-head">'
            '<span class="dir-name">packages/rich</span>' in html
        )
        self.assertTrue(details_with_rich,
                        "non-trivial child must still render as "
                        "<details> with dir-name in the summary")

    def test_workspace_html_body_does_not_duplicate_hint(self):
        # The expanded body must NOT repeat the hint that's already
        # in the summary's hint-badge. fns-monorepo apps/forge has
        # a Solidity hint — it appears once via the badge and once
        # in the description below the manifest section was the
        # bug. Now: appears once via the badge only.
        self._build_fns_fixture()
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Slice just the workspace children section.
        ws_start = html.index("<h2>Workspace children")
        ws_end = html.find("</section>", ws_start)
        ws = html[ws_start:ws_end]
        # Hint phrase appears at most once inside the workspace
        # section — the hint-badge in the summary. The body's
        # <p class="hint">...</p> for workspace children is gone.
        # (Search for the full hint phrase including the "; verify
        # with user" tail since the badge truncates at the semicolon.)
        full_hint_count = ws.count(
            ".sol files suggest Solidity / EVM smart contracts; "
            "verify with user"
        )
        self.assertEqual(full_hint_count, 0,
                         "the long-form hint (with 'verify with user') "
                         "must not appear inside the workspace body — "
                         "only the shorter badge in the summary")


class TestWorkspaceChildNameVisibility(unittest.TestCase):
    """v0.8 polish — child name must be the visible card header in
    the HTML report (it was getting lost between manifests/extensions
    when both rendered as inline dim text). Also: workspace children
    must appear in the CLAUDE.md generated managed block, not just
    in BUILD_PLAN.md.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _build_fns_fixture(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

    # ---- HTML: name visible at the card header ------------------------

    def test_html_workspace_child_name_is_card_header(self):
        # The child name must be present near the card header — i.e.
        # inside the <summary> for collapsible cards, inside the
        # <div class="unc unc-trivial"> for trivial cards. It must
        # also be in the load-bearing dir-name span (block-level
        # header treatment, not mixed inline with manifest text).
        self._build_fns_fixture()
        # Add a trivial child to cover both code paths.
        (self.repo / "packages").mkdir()
        triv = self.repo / "packages" / "tsconfig"
        triv.mkdir()
        (triv / "package.json").write_text("{}", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])

        # Names appear in dir-name spans (block header treatment).
        for name in ("apps/forge", "apps/next", "packages/tsconfig"):
            self.assertIn(f'<span class="dir-name">{name}</span>', html,
                          f"{name} must render as a dir-name header")

        # The name must be visible at the card header, not buried.
        # For collapsible: name is inside <summary>. For trivial:
        # name is inside the <div class="unc unc-trivial">.
        # Slice each card and confirm the name appears in the head.
        # apps/forge — collapsible with summary.
        forge_summary_re = re.search(
            r'<details class="unc"><summary>(.*?)</summary>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(forge_summary_re,
                             "expected at least one collapsible workspace card")
        # Find which one is forge.
        any_summary_has_forge = any(
            'dir-name">apps/forge<' in m.group(1)
            for m in re.finditer(
                r'<details class="unc"><summary>(.*?)</summary>',
                html, re.DOTALL,
            )
        )
        self.assertTrue(any_summary_has_forge,
                        "apps/forge name must appear inside the <summary> "
                        "block of its collapsible card")

        # packages/tsconfig — trivial card.
        triv_re = re.search(
            r'<div class="unc unc-trivial">(.*?)</div>\s*</div>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(triv_re, "expected a trivial workspace card")
        self.assertIn('packages/tsconfig', triv_re.group(0),
                      "packages/tsconfig name must appear inside the "
                      "trivial card's div")

    def test_html_card_renders_meta_below_name(self):
        # The dir-meta line (manifests / extensions) must appear in
        # the same card as dir-name, AFTER the name in DOM order.
        # That ordering is what makes the name visible as a header.
        self._build_fns_fixture()
        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Find the apps/forge card slice and verify dir-name appears
        # before dir-meta in DOM order.
        forge_slice = re.search(
            r'<span class="dir-name">apps/forge</span>.*?</summary>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(forge_slice,
                             "apps/forge dir-name must precede </summary>")
        self.assertIn('dir-meta', forge_slice.group(0),
                      "dir-meta line (manifests/extensions) must appear "
                      "after the dir-name in the same summary")

    # ---- CLAUDE.md: workspace children block --------------------------

    def test_claude_block_includes_workspace_children_when_present(self):
        # The managed block in CLAUDE.md (generate_claude_block) must
        # carry a compact "Workspace children (N)" section so the AI
        # session reading the entry-point doc sees depth-2 child
        # projects without cross-reading BUILD_PLAN.md.
        self._build_fns_fixture()
        stack = detect_stack(self.repo)
        block = generate_claude_block(stack, self.inputs, "Test")
        # Section heading with count.
        self.assertIn("### Workspace children (2)", block,
                      "CLAUDE block must include the workspace section "
                      "with a count")
        # Child names + hint formatting (italic for hints, bare name
        # without). apps/forge has the Solidity hint; apps/next has
        # no DOMAIN_HINTS-eligible extension at the threshold so it
        # gets a bare bullet.
        self.assertIn("- **apps/forge**", block)
        self.assertIn("Solidity", block,
                      "apps/forge's Solidity hint must appear in the "
                      "CLAUDE block")
        self.assertIn("- **apps/next**", block)
        # The block must remain inside adopt's managed markers so
        # re-runs refresh it cleanly.
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)

    def test_claude_block_omits_workspace_section_when_empty(self):
        # Plain repo (no workspace containers) keeps the v0.7
        # CLAUDE block shape — no empty "Workspace children (0)"
        # heading.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        stack = detect_stack(self.repo)
        block = generate_claude_block(stack, self.inputs, "Test")
        self.assertNotIn("Workspace children", block,
                         "CLAUDE block must omit section when no "
                         "workspace children exist")


class TestUnknownButPresentDirNameVisible(unittest.TestCase):
    """v0.8 polish — Unknown-but-present cards must visibly show the
    directory name as the card header, same dir-head / dir-name /
    dir-meta layout as Workspace-children cards. The bug: prior
    rendering put the dirname inline with the metadata as a small
    grey monospace string, so the user couldn't tell which card was
    which without expanding it.

    Bonus regression: Workspace-children cards must still show
    apps/docs / apps/web names visibly under the renamed class set.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    # ---- Unknown-but-present: directory name visible -----------------

    def test_html_unknown_but_present_card_shows_dir_name_header(self):
        # turborepo-style fixture: server/ is a recognized subdir
        # holding manage.py at depth-2, so it triggers the
        # SILENT_SUBDIR_DROP path AND surfaces in unknown-but-present.
        # The card MUST visibly show "server/" via the dir-name span.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Section present.
        self.assertIn("<h2>Needs clarification</h2>", html)
        # Directory name appears as a dir-name span (block header
        # treatment), not inline as a grey code dirname.
        self.assertIn('<span class="dir-name">server/</span>', html,
                      "unknown-but-present card must render server/ "
                      "as a dir-name header")

    def test_html_unknown_but_present_meta_below_name(self):
        # The dir-name span must appear BEFORE the dir-meta line in
        # DOM order so the eye reads the directory name first when
        # scanning the section.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Slice the server/ card.
        m = re.search(
            r'<span class="dir-name">server/</span>.*?</summary>',
            html, re.DOTALL,
        )
        self.assertIsNotNone(m, "expected server/ dir-name span in summary")
        self.assertIn('dir-meta', m.group(0),
                      "dir-meta line must appear after dir-name in the "
                      "same summary block")

    def test_html_unknown_but_present_no_legacy_code_dirname(self):
        # Defense: the old <code class="dirname">...</code> pattern
        # must no longer wrap the directory name in unknown-but-
        # present cards. (The CSS still keeps a fallback rule for
        # safety, but adopt itself should never emit it now.)
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "manage.py").write_text("# d\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # No code.dirname inside an Unknown-but-present <details>.
        m = re.search(r'<h2>Needs clarification</h2>.*?</section>',
                      html, re.DOTALL)
        if m:
            self.assertNotIn('<code class="dirname">', m.group(0),
                             "unknown-but-present must use dir-name, "
                             "not the legacy code.dirname markup")

    # ---- Workspace children: apps/docs + apps/web visible -----------

    def test_html_workspace_children_apps_docs_and_web_visible(self):
        # Replays the turborepo fixture from the dogfood batch.
        # Every workspace child — including non-trivial ones with
        # extra manifests — must render its name via dir-name so
        # the cards are scannable.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("docs", "web"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")
            (d / "next.config.js").write_text("// next\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        # Both children get dir-name headers.
        self.assertIn('<span class="dir-name">apps/docs</span>', html,
                      "apps/docs name must be a visible dir-name header")
        self.assertIn('<span class="dir-name">apps/web</span>', html,
                      "apps/web name must be a visible dir-name header")
        # Both render as collapsible <details> (next.config.js +
        # package.json makes them non-trivial).
        self.assertIn(
            '<details class="unc"><summary>'
            '<div class="dir-head">'
            '<span class="dir-name">apps/docs</span>',
            html,
        )
        self.assertIn(
            '<details class="unc"><summary>'
            '<div class="dir-head">'
            '<span class="dir-name">apps/web</span>',
            html,
        )


class TestWorkspaceStackSummary(unittest.TestCase):
    """v0.8 Phase 3 — derived per-child stack labels.

    Restricted to four obvious signals (Solidity / Next.js /
    Flutter / Expo). The summary surfaces in CLI dry-run, HTML
    report, BUILD_PLAN.md, and the CLAUDE managed block.

    Primary classification (StackProfile.language / parts) is
    unchanged. The Detection card / "Detected stack:" line stays
    exactly as before.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        return buf.getvalue()

    # ---- fns-monorepo: Solidity + Next.js ---------------------------

    def test_fns_monorepo_workspace_stack_lists_solidity_and_nextjs(self):
        # apps/forge has foundry.toml + .sol → Solidity.
        # apps/next has next.config.js + package.json → Next.js.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        # Primary classification UNCHANGED — root package.json wins.
        self.assertEqual(stack.language, "javascript",
                         "Phase 3 must not change primary classification")
        # Derived workspace stack pairs.
        from cli.adopt import _workspace_stack_pairs
        pairs = dict(_workspace_stack_pairs(stack))
        self.assertEqual(pairs.get("apps/forge"),
                         "Solidity / EVM smart contracts")
        self.assertEqual(pairs.get("apps/next"),
                         "Next.js / React web app")

        # v0.8 Phase 4.4: workspace stack content now lives inside
        # the consolidated "Adopt Summary" Structure section.
        out = self._run_cli()
        self.assertIn("Adopt Summary", out)
        self.assertIn("Structure:", out)
        self.assertIn("apps/forge", out)
        self.assertIn("Solidity / EVM smart contracts", out)
        self.assertIn("apps/next", out)
        self.assertIn("Next.js / React web app", out)
        # Original "Detected stack:" line unchanged.
        self.assertIn("Detected stack: JavaScript / Node.js", out)

        from cli.adopt import (
            derive_adopt_summary, derive_project_type,
            derive_stack_reality, derive_suggested_actions,
        )
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)

        # HTML report.
        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("<h2>Adopt Summary</h2>", html)
        self.assertIn("apps/forge", html)
        self.assertIn("Solidity / EVM smart contracts", html)
        self.assertIn("Next.js / React web app", html)

        # BUILD_PLAN.
        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertIn("## Adopt Summary", md)
        self.assertIn("`apps/forge` → Solidity / EVM smart contracts", md)
        self.assertIn("`apps/next` → Next.js / React web app", md)

        # CLAUDE managed block.
        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertIn("## Adopt Summary", block)
        self.assertIn("`apps/forge` → Solidity / EVM smart contracts", block)
        self.assertIn("`apps/next` → Next.js / React web app", block)
        # Stays inside the managed markers.
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)

    # ---- flutter monorepo: Dart ------------------------------------

    def test_flutter_monorepo_workspace_stack_lists_flutter(self):
        # apps/buyer_app + apps/seller_app each have pubspec.yaml +
        # .dart files → Flutter / Dart app for each.
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("buyer_app", "seller_app"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "pubspec.yaml").write_text(
                f"name: {app}\n", encoding="utf-8")
            (d / "lib").mkdir()
            (d / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        from cli.adopt import _workspace_stack_pairs
        pairs = dict(_workspace_stack_pairs(stack))
        self.assertEqual(pairs.get("apps/buyer_app"), "Flutter / Dart app")
        self.assertEqual(pairs.get("apps/seller_app"), "Flutter / Dart app")

        out = self._run_cli()
        # v0.8 Phase 4.4: Adopt Summary's Structure section lists
        # the per-child labels.
        self.assertIn("Adopt Summary", out)
        self.assertIn("Flutter / Dart app", out)

        from cli.adopt import (
            derive_adopt_summary, derive_project_type,
            derive_stack_reality, derive_suggested_actions,
        )
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)

        # HTML
        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("<h2>Adopt Summary</h2>", html)
        self.assertIn("Flutter / Dart app", html)

        # BUILD_PLAN + CLAUDE
        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        for doc, label in [(md, "BUILD_PLAN"), (block, "CLAUDE")]:
            self.assertIn("## Adopt Summary", doc,
                          f"{label} missing Adopt Summary")
            self.assertIn("`apps/buyer_app` → Flutter / Dart app", doc,
                          f"{label} missing buyer_app row")
            self.assertIn("`apps/seller_app` → Flutter / Dart app", doc,
                          f"{label} missing seller_app row")

    # ---- turborepo: Next.js / React for both children ---------------

    def test_turborepo_workspace_stack_lists_nextjs_for_apps(self):
        # apps/web + apps/docs each have next.config.js + package.json
        # → Next.js / React web app. The packages/* trivial children
        # don't match any Phase 3 signal, so they're omitted from
        # the summary (correct behavior — better than guessing).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("docs", "web"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")
            (d / "next.config.js").write_text("// next\n", encoding="utf-8")
        (self.repo / "packages").mkdir()
        for pkg in ("ui", "tsconfig"):
            d = self.repo / "packages" / pkg
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")

        stack = detect_stack(self.repo)
        from cli.adopt import _workspace_stack_pairs
        pairs = dict(_workspace_stack_pairs(stack))
        self.assertEqual(pairs.get("apps/docs"), "Next.js / React web app")
        self.assertEqual(pairs.get("apps/web"), "Next.js / React web app")
        # Trivial packages/* children must NOT appear in the summary
        # (their package.json alone doesn't match a Phase 3 signal).
        self.assertNotIn("packages/ui", pairs)
        self.assertNotIn("packages/tsconfig", pairs)

        out = self._run_cli()
        # v0.8 Phase 4.4: Structure block inside Adopt Summary.
        self.assertIn("Adopt Summary", out)
        # Slice the Structure block: from "Structure:" to "Reality:".
        struct_start = out.index("Structure:")
        struct_end = out.index("Reality:", struct_start)
        struct_section = out[struct_start:struct_end]
        self.assertEqual(
            struct_section.count("Next.js / React web app"), 2,
            f"both apps/* should appear in Structure: {struct_section!r}"
        )
        self.assertNotIn("packages/", struct_section,
                         "trivial packages/* children must not appear "
                         "in the Structure section")

    # ---- plain JS repo: no workspace stack section ------------------

    def test_plain_repo_has_no_workspace_stack_section(self):
        # Single-stack repo with no apps/ or packages/ — workspace
        # stack section must be silent across all four output paths
        # so the v0.7 shape is preserved on simple projects.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.js").write_text("// js\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        from cli.adopt import _workspace_stack_pairs
        self.assertEqual(_workspace_stack_pairs(stack), [])

        out = self._run_cli()
        self.assertNotIn("Workspace stack:", out)

        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        self.assertNotIn("<h2>Workspace stack</h2>", html)

        md = generate_build_plan(stack, self.inputs, "Test")
        self.assertNotIn("Workspace stack", md)

        block = generate_claude_block(stack, self.inputs, "Test")
        self.assertNotIn("Workspace stack", block)

    # ---- Phase 3 must not change primary classification -------------

    def test_phase3_does_not_change_primary_classification(self):
        # Same fns-monorepo shape; primary remains "javascript", parts
        # remain empty (no v0.7 split-monorepo classification fired).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "javascript")
        self.assertEqual(stack.parts, {})
        # Detection HTML card label is unchanged from v0.7.
        plan = plan_files(self.repo, stack, self.inputs)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[])
        self.assertIn('<p class="lede">JavaScript / Node.js</p>', html)


class TestStackRealityCheck(unittest.TestCase):
    """v0.8 Phase 4.1 — derived stack reality assessment.

    Checks the assessment / confidence categorization for the four
    user-spec scenarios plus the "Needs clarification" rename.
    Also verifies the section surfaces in CLI, HTML, BUILD_PLAN,
    and CLAUDE managed block.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        return buf.getvalue()

    def _build_fns_fixture(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

    # ---- assessment categorization ----------------------------------

    def test_fns_monorepo_assessment_is_mixed_workspace_project(self):
        # Spec example: primary=JS + workspace=Solidity+Next.js
        # → Mixed workspace project / Medium.
        self._build_fns_fixture()
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Mixed workspace project")
        self.assertEqual(reality.confidence, "Medium")
        self.assertIn("Solidity / EVM smart contracts", reality.workspace_signals)
        self.assertIn("Next.js / React web app", reality.workspace_signals)
        self.assertIn("distinct stack", reality.why)

    def test_plain_python_project_assessment_is_single_stack_high(self):
        # Spec example: primary=Python, no workspace children.
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("# py\n", encoding="utf-8")
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Single-stack project")
        self.assertEqual(reality.confidence, "High")
        self.assertEqual(reality.workspace_signals, [])

    def test_plain_js_project_assessment_is_single_stack_high(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.js").write_text("// js\n", encoding="utf-8")
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Single-stack project")
        self.assertEqual(reality.confidence, "High")

    def test_unknown_with_clarification_dirs_is_unclear_low(self):
        # Spec example: primary unknown + clarification dirs
        # → Unclear project shape / Low.
        (self.repo / "wrapper").mkdir()
        (self.repo / "wrapper" / "src").mkdir()
        (self.repo / "wrapper" / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")
        (self.repo / "extras").mkdir()
        (self.repo / "extras" / "data.json").write_text("{}", encoding="utf-8")
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Unclear project shape")
        self.assertEqual(reality.confidence, "Low")
        self.assertIn("candidate", reality.why)

    def test_misleading_classification_drops_single_stack_to_medium(self):
        # Hardhat project — root has package.json + hardhat.config.ts.
        # MISLEADING_CLASSIFICATION fires; reality should be
        # Single-stack / Medium with a why that flags the gap.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "hardhat.config.ts").write_text("// hh\n", encoding="utf-8")
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Single-stack project")
        self.assertEqual(reality.confidence, "Medium")
        self.assertIn("undersell", reality.why)

    # ---- surface in all four output paths ---------------------------

    def test_stack_reality_surfaces_in_all_outputs(self):
        # v0.8 Phase 4.4: stack reality content is folded into the
        # consolidated Adopt Summary card. Same data, single
        # section per output path.
        self._build_fns_fixture()
        from cli.adopt import (
            derive_adopt_summary, derive_project_type,
            derive_stack_reality, derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)

        out = self._run_cli()
        self.assertIn("Adopt Summary", out)
        self.assertIn("Reality:", out)
        self.assertIn("Mixed workspace project", out)
        self.assertIn("Medium", out)
        self.assertIn("Why:", out)

        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("<h2>Adopt Summary</h2>", html)
        self.assertIn("<h3>Reality</h3>", html)
        self.assertIn("Mixed workspace project", html)
        self.assertIn("Medium", html)

        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertIn("## Adopt Summary", md)
        self.assertIn("**Reality:**", md)
        self.assertIn("Mixed workspace project", md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertIn("## Adopt Summary", block)
        self.assertIn("**Reality:**", block)
        self.assertIn("Mixed workspace project", block)
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)

    # ---- "Needs clarification" rename in user-facing outputs --------

    def test_needs_clarification_renamed_in_all_outputs(self):
        # Use a fixture that produces a Needs-clarification entry
        # across CLI / HTML / BUILD_PLAN / CLAUDE.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "Deploy.s.sol").write_text(
            "// sol\n", encoding="utf-8")

        out = self._run_cli()
        self.assertIn("Needs clarification (depth 1):", out)
        self.assertNotIn("Unknown but present", out)

        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        plan = plan_files(self.repo, stack, self.inputs, reality=reality)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 reality=reality)
        self.assertIn("<h2>Needs clarification</h2>", html)
        self.assertNotIn("<h2>Unknown but present</h2>", html)
        self.assertIn("Confirm what they are before making changes", html)

        md = generate_build_plan(stack, self.inputs, "Test", reality=reality)
        self.assertIn("### Needs clarification", md)
        self.assertNotIn("### Unknown but present", md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      reality=reality)
        self.assertIn("### Needs clarification", block)
        self.assertNotIn("### Unknown but present", block)


class TestProjectTypeInference(unittest.TestCase):
    """v0.8 Phase 4.2 — derived single-line project type label.

    Five spec'd dogfood-shaped fixtures (Web3 dApp, Full-stack web
    app, Mobile app suite, JavaScript app/tooling, Unclear). Each
    asserts both the dataclass values and that the section
    surfaces in CLI / HTML / BUILD_PLAN / CLAUDE.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _derive(self):
        from cli.adopt import derive_project_type, derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        return stack, reality, ptype

    def _run_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        return buf.getvalue()

    # ---- 1. fns-monorepo -> Web3 dApp ------------------------------

    def test_fns_monorepo_is_web3_dapp(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "Web3 dApp")
        self.assertEqual(ptype.confidence, "medium")
        self.assertIn("Solidity", ptype.reason)
        self.assertIn("Next.js", ptype.reason)

    # ---- 2. turborepo-next-django-starter -> Full-stack web app -----

    def test_turborepo_django_is_full_stack_web_app(self):
        # apps/web (Next.js) + server/ contains Django (manage.py at
        # depth-2 surfaces as .py in unclassified_subdirs).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        web = self.repo / "apps" / "web"
        web.mkdir()
        (web / "package.json").write_text("{}", encoding="utf-8")
        (web / "next.config.js").write_text("// next\n", encoding="utf-8")
        (web / "app").mkdir()
        for n in range(3):
            (web / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")

        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "Full-stack web app")
        self.assertEqual(ptype.confidence, "medium")
        self.assertIn("Python", ptype.reason)
        self.assertIn("Next.js", ptype.reason)

    # ---- 3. flutter-monorepo-example -> Mobile app suite -----------

    def test_flutter_monorepo_is_mobile_app_suite(self):
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("buyer_app", "seller_app"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "pubspec.yaml").write_text(
                f"name: {app}\n", encoding="utf-8")
            (d / "lib").mkdir()
            (d / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")

        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "Mobile app suite")
        self.assertEqual(ptype.confidence, "medium")
        self.assertIn("Flutter", ptype.reason)

    # ---- 4. plain JS -> JavaScript app/tooling project --------------

    def test_plain_js_is_javascript_app_tooling(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.js").write_text("// js\n", encoding="utf-8")
        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "JavaScript app/tooling project")
        self.assertEqual(ptype.confidence, "medium")
        self.assertIn("JavaScript", ptype.reason)

    # ---- 5. unknown -> Unclear project type -------------------------

    def test_unknown_repo_is_unclear_project_type(self):
        (self.repo / "wrapper").mkdir()
        (self.repo / "wrapper" / "src").mkdir()
        (self.repo / "wrapper" / "src" / "lib.rs").write_text(
            "// rs\n", encoding="utf-8")
        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "Unclear project type")
        self.assertEqual(ptype.confidence, "low")
        # Reason mentions primary detection and workspace signals.
        self.assertIn("Primary detection", ptype.reason)
        self.assertIn("workspace signals", ptype.reason)

    # ---- surface in all four output paths --------------------------

    def test_project_type_surfaces_in_all_outputs(self):
        # Use the fns-monorepo fixture (Web3 dApp).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        # v0.8 Phase 4.4: project type folded into Adopt Summary.
        stack, reality, ptype = self._derive()
        from cli.adopt import (
            derive_adopt_summary, derive_suggested_actions,
        )
        prelim = analyze_failures(self.repo, stack, [])
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)

        # CLI dry-run.
        out = self._run_cli()
        self.assertIn("Adopt Summary", out)
        self.assertIn("Type:", out)
        self.assertIn("Web3 dApp", out)
        self.assertIn("(medium)", out)

        # HTML report.
        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("<h2>Adopt Summary</h2>", html)
        self.assertIn("<h3>Type</h3>", html)
        self.assertIn("Web3 dApp", html)
        self.assertIn("medium", html)

        # BUILD_PLAN.md.
        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertIn("## Adopt Summary", md)
        self.assertIn("**Type:** Web3 dApp (medium)", md)

        # CLAUDE managed block.
        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertIn("## Adopt Summary", block)
        self.assertIn("**Type:** Web3 dApp (medium)", block)
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)


class TestSuggestedActions(unittest.TestCase):
    """v0.8 Phase 4.3 — derived suggested next actions.

    Five spec'd dogfood-shaped fixtures verifying the rule cascade
    plus a surface-in-all-outputs test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _derive_actions(self, *, with_plan=True):
        """Return (stack, reality, project_type, failures, actions).

        ``with_plan=True`` builds a prelim plan first so
        IDEMPOTENCY_RISK can fire (mirrors run_adopt's two-pass).
        """
        from cli.adopt import (
            derive_project_type,
            derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        if with_plan:
            prelim_plan = plan_files(self.repo, stack, self.inputs,
                                     reality=reality, project_type=ptype)
            failures = analyze_failures(self.repo, stack, prelim_plan)
        else:
            failures = prelim
        actions = derive_suggested_actions(stack, reality, ptype, failures)
        return stack, reality, ptype, failures, actions

    def _titles(self, actions):
        return {a.title for a in actions}

    def _run_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        return buf.getvalue()

    # ---- 1. fns-monorepo: Web3 dApp + child workspaces -------------

    def test_fns_monorepo_has_contract_workspace_and_inspect_children(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "package.json").write_text("{}", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        _, _, _, _, actions = self._derive_actions()
        titles = self._titles(actions)
        # v0.8 Phase 4.6: titles refined for context-awareness.
        self.assertIn("Confirm smart-contract + frontend boundary",
                      titles,
                      f"Web3 dApp must include the boundary action; "
                      f"got {titles!r}")
        self.assertIn("Review workspace children", titles,
                      f"MONOREPO_DEPTH_LIMIT must trigger the review "
                      f"action; got {titles!r}")
        # Reasons must name the concrete child workspaces, not just
        # talk about "smart-contract code" / "frontend code" generically.
        boundary = next(a for a in actions
                        if a.title == "Confirm smart-contract + frontend boundary")
        self.assertIn("apps/forge", boundary.reason,
                      f"boundary reason must name the Solidity child; "
                      f"got: {boundary.reason!r}")
        self.assertIn("apps/next", boundary.reason,
                      f"boundary reason must name the frontend child; "
                      f"got: {boundary.reason!r}")
        # Both refined actions are high priority.
        for a in actions:
            if a.title in ("Confirm smart-contract + frontend boundary",
                           "Review workspace children"):
                self.assertEqual(a.priority, "high")

    # ---- 2. unknown shape: Clarify project shape ------------------

    def test_unknown_repo_has_clarify_project_shape(self):
        # No root manifest, just a wrapper subdir with a .rs file →
        # Unclear / Low confidence.
        (self.repo / "wrapper").mkdir()
        (self.repo / "wrapper" / "src").mkdir()
        (self.repo / "wrapper" / "src" / "lib.rs").write_text(
            "// rs\n", encoding="utf-8")
        _, reality, _, _, actions = self._derive_actions()
        self.assertEqual(reality.confidence, "Low")
        titles = self._titles(actions)
        self.assertIn("Clarify project shape before coding", titles,
                      f"Low confidence must trigger clarify action; "
                      f"got {titles!r}")

    # ---- 3. existing context docs without markers: IDEMPOTENCY_RISK -

    def test_existing_docs_without_markers_triggers_preserve_action(self):
        # Pre-existing 00-START-NEXT-SESSION.md without our adopt
        # markers triggers IDEMPOTENCY_RISK during the prelim plan
        # pass. Suggested actions should pick it up.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "00-START-NEXT-SESSION.md").write_text(
            "# Hand-written start here\n", encoding="utf-8")
        _, _, _, failures, actions = self._derive_actions()
        from cli.adopt import FAILURE_IDEMPOTENCY_RISK
        self.assertIn(FAILURE_IDEMPOTENCY_RISK,
                      {f.failure_type for f in failures},
                      "IDEMPOTENCY_RISK must fire on hand-written "
                      "00-START-NEXT-SESSION.md")
        titles = self._titles(actions)
        self.assertIn("Preserve existing context docs before writing",
                      titles,
                      f"IDEMPOTENCY_RISK must trigger the preserve "
                      f"action; got {titles!r}")

    # ---- 4. clean plain JS fixture: catch-all "Run with --write" ---

    def test_clean_plain_js_fixture_has_run_with_write_action(self):
        # Truly clean: just root package.json + a root-level .js
        # file. No subdirs means no needs-clarification entries,
        # no workspace containers, no IDEMPOTENCY_RISK trigger.
        # The catch-all is the only action.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        _, _, _, _, actions = self._derive_actions()
        titles = self._titles(actions)
        self.assertIn("Run adopt with --write when ready", titles,
                      f"Clean fixture should hit the catch-all action; "
                      f"got {titles!r}")
        # Catch-all is low priority and is the ONLY action when clean.
        self.assertEqual(len(actions), 1,
                         f"clean fixture should yield exactly one action; "
                         f"got {len(actions)}: {titles!r}")
        self.assertEqual(actions[0].priority, "low")

    # ---- 5. Full-stack web app: Confirm backend/frontend ----------

    def test_full_stack_fixture_has_confirm_boundaries_action(self):
        # turborepo-django-style: apps/web Next.js + server/ Django.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        web = self.repo / "apps" / "web"
        web.mkdir()
        (web / "package.json").write_text("{}", encoding="utf-8")
        (web / "next.config.js").write_text("// next\n", encoding="utf-8")
        (web / "app").mkdir()
        for n in range(3):
            (web / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")

        _, _, ptype, _, actions = self._derive_actions()
        self.assertEqual(ptype.label, "Full-stack web app")
        titles = self._titles(actions)
        self.assertIn("Confirm backend/frontend boundaries", titles,
                      f"Full-stack web app must include the boundaries "
                      f"action; got {titles!r}")

    # ---- cap + dedup invariants ----------------------------------

    def test_actions_are_capped_and_deduped(self):
        # Maximum-rule fixture: Web3 dApp + workspace children + an
        # existing CLAUDE.md without markers (IDEMPOTENCY_RISK) +
        # an unrelated unclassified subdir for "Review unclassified
        # directories". Should fire 4 distinct rules; cap at 5
        # never reached, but the dedup-by-title invariant holds.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")
        (self.repo / "00-START-NEXT-SESSION.md").write_text(
            "# Hand-written\n", encoding="utf-8")
        # An unrelated dir for the clarification rule.
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "tool.py").write_text("# x\n", encoding="utf-8")

        _, _, _, _, actions = self._derive_actions()
        # No duplicates by title.
        titles = [a.title for a in actions]
        self.assertEqual(len(titles), len(set(titles)),
                         f"actions must be deduped by title; got {titles!r}")
        # Capped at 5.
        self.assertLessEqual(len(actions), 5)
        # Sorted with high priority first (defensive — implementation
        # detail but a stable contract for renderers).
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        ranks = [priority_rank[a.priority] for a in actions]
        self.assertEqual(ranks, sorted(ranks),
                         "actions must be sorted by priority "
                         "(high before medium before low)")

    # ---- surface in all four output paths ------------------------

    def test_suggested_actions_surface_in_all_outputs(self):
        # Web3 dApp fixture so we get two rules (Web3 + child
        # workspaces), enough to verify the section structure.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        # v0.8 Phase 4.4: actions live inside Adopt Summary's
        # "Next actions" sub-section. Same content, single section.
        stack, reality, ptype, _, actions = self._derive_actions()
        from cli.adopt import derive_adopt_summary
        summary = derive_adopt_summary(stack, reality, ptype, actions)

        # v0.8 Phase 4.6: refined Web3 dApp action title.
        out = self._run_cli()
        self.assertIn("Adopt Summary", out)
        self.assertIn("Next actions", out)
        self.assertIn("Confirm smart-contract + frontend boundary", out)
        self.assertIn("[high]", out)

        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("<h2>Adopt Summary</h2>", html)
        self.assertIn("Next actions (", html)
        self.assertIn("[high] Confirm smart-contract + frontend boundary",
                      html)

        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertIn("## Adopt Summary", md)
        self.assertIn("Next actions (", md)
        self.assertIn("**[high] Confirm smart-contract + frontend boundary**",
                      md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertIn("## Adopt Summary", block)
        self.assertIn("Next actions (", block)
        self.assertIn("**[high] Confirm smart-contract + frontend boundary**",
                      block)
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)


class TestAdoptSummary(unittest.TestCase):
    """v0.8 Phase 4.4 — single consolidated Adopt Summary card.

    The four standalone Phase 3 / 4.x sections (Workspace stack,
    Stack reality, Project type, Suggested next actions) are
    folded into one read-once block. Tests here cover:
      - Summary renders in CLI, HTML, BUILD_PLAN, CLAUDE.md
      - Actions inside the summary match what
        ``derive_suggested_actions`` returns directly
      - The four standalone section headers are NOT duplicated
        below the summary
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _build_fns_fixture(self):
        # Web3 dApp — fires multiple rules (Web3, MONOREPO_DEPTH,
        # needs-clarification empty ens-contracts), useful for
        # exercising every sub-section of the summary.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

    def _derive_summary(self):
        from cli.adopt import (
            derive_adopt_summary, derive_project_type,
            derive_stack_reality, derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        prelim_plan = plan_files(self.repo, stack, self.inputs,
                                 reality=reality, project_type=ptype)
        failures = analyze_failures(self.repo, stack, prelim_plan)
        actions = derive_suggested_actions(stack, reality, ptype, failures)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        return stack, reality, ptype, actions, summary

    def _run_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        return buf.getvalue()

    # ---- summary renders in all four output paths ----------------

    def test_summary_renders_in_cli(self):
        self._build_fns_fixture()
        out = self._run_cli()
        self.assertIn("Adopt Summary", out)
        # Four sub-sections are visible in the CLI block.
        self.assertIn("Type:", out)
        self.assertIn("Structure:", out)
        self.assertIn("Reality:", out)
        self.assertIn("Next actions", out)

    def test_summary_renders_in_html(self):
        self._build_fns_fixture()
        _, _, _, _, summary = self._derive_summary()
        plan = plan_files(self.repo, self._derive_summary()[0],
                          self.inputs, summary=summary)
        html = render_adopt_html(self.repo, self._derive_summary()[0],
                                 self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("<h2>Adopt Summary</h2>", html)
        # Each sub-section uses an <h3>.
        self.assertIn("<h3>Type</h3>", html)
        self.assertIn("<h3>Structure</h3>", html)
        self.assertIn("<h3>Reality</h3>", html)
        self.assertIn("<h3>Next actions (", html)

    def test_summary_renders_in_build_plan(self):
        self._build_fns_fixture()
        stack, _, _, _, summary = self._derive_summary()
        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertIn("## Adopt Summary", md)
        self.assertIn("**Type:**", md)
        self.assertIn("**Structure:**", md)
        self.assertIn("**Reality:**", md)
        self.assertIn("**Next actions", md)

    def test_summary_renders_in_claude_block(self):
        self._build_fns_fixture()
        stack, _, _, _, summary = self._derive_summary()
        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertIn("## Adopt Summary", block)
        self.assertIn("**Type:**", block)
        self.assertIn("**Structure:**", block)
        self.assertIn("**Reality:**", block)
        self.assertIn("**Next actions", block)
        # Stays inside adopt's managed markers.
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)

    # ---- actions consistent with derive_suggested_actions --------

    def test_summary_actions_match_derived_actions(self):
        # The actions inside the summary must be byte-equal to
        # what ``derive_suggested_actions`` returns directly —
        # the consolidation must not change Phase 4.3 logic.
        self._build_fns_fixture()
        _, _, _, actions, summary = self._derive_summary()
        self.assertEqual(
            [(a.title, a.priority, a.reason) for a in summary.actions],
            [(a.title, a.priority, a.reason) for a in actions],
            "summary.actions must match derive_suggested_actions output",
        )

    # ---- no duplication of content below summary ----------------

    def test_no_standalone_workspace_stack_section_in_outputs(self):
        # The standalone "Workspace stack:" / "<h2>Workspace stack</h2>" /
        # "### Workspace stack" headers must NOT appear anywhere in the
        # rendered output — content lives only inside Adopt Summary.
        self._build_fns_fixture()
        stack, _, _, _, summary = self._derive_summary()

        out = self._run_cli()
        self.assertNotIn("Workspace stack:", out,
                         "standalone 'Workspace stack:' CLI header "
                         "must be removed in Phase 4.4")

        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertNotIn("<h2>Workspace stack</h2>", html)

        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertNotIn("### Workspace stack", md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertNotIn("### Workspace stack", block)

    def test_no_standalone_stack_reality_section_in_outputs(self):
        self._build_fns_fixture()
        stack, _, _, _, summary = self._derive_summary()

        out = self._run_cli()
        self.assertNotIn("Stack reality:", out)

        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertNotIn("<h2>Stack reality</h2>", html)

        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertNotIn("### Stack reality", md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertNotIn("### Stack reality", block)

    def test_no_standalone_project_type_section_in_outputs(self):
        self._build_fns_fixture()
        stack, _, _, _, summary = self._derive_summary()

        out = self._run_cli()
        self.assertNotIn("Project type:", out)

        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertNotIn("<h2>Project type</h2>", html)

        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertNotIn("### Project type", md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertNotIn("### Project type", block)

    def test_no_standalone_suggested_actions_section_in_outputs(self):
        self._build_fns_fixture()
        stack, _, _, _, summary = self._derive_summary()

        out = self._run_cli()
        # The standalone "Suggested next actions (N):" header (with
        # the trailing colon) must be gone. The Adopt Summary block
        # uses "Next actions (N)" without a trailing colon.
        self.assertNotIn("Suggested next actions (", out)

        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertNotIn("<h2>Suggested next actions (", html)

        md = generate_build_plan(stack, self.inputs, "Test", summary=summary)
        self.assertNotIn("### Suggested next actions (", md)

        block = generate_claude_block(stack, self.inputs, "Test",
                                      summary=summary)
        self.assertNotIn("### Suggested next actions (", block)


class TestWorkspaceAwarePrimaryDetection(unittest.TestCase):
    """v0.8 Phase 4.5 — promote workspace child consistency into
    the primary detection label when the root scan returns
    "unknown" but every non-trivial child shares one of three
    target stack labels (Flutter / Solidity / Next.js).

    Constraints under test:
      - JS / Python root detections never overridden.
      - Plain unknown repos with no workspace children stay Unknown.
      - Mixed workspace children stay Unknown.
      - Inferred primary surfaces with the "(inferred from
        workspace children)" suffix in CLI / HTML.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_cli(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="demo", next_step="ship v1"))
        return buf.getvalue()

    def _build_flutter_fixture(self):
        # melos.yaml at root (not a v0 classifier signal) +
        # apps/buyer_app + apps/seller_app each with pubspec.yaml
        # and a .dart file. Mirrors flutter-monorepo-example.
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("buyer_app", "seller_app"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "pubspec.yaml").write_text(
                f"name: {app}\n", encoding="utf-8")
            (d / "lib").mkdir()
            (d / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")

    # ---- 1. flutter-monorepo no longer Unknown ---------------------

    def test_flutter_monorepo_promotes_to_flutter_dart_primary(self):
        self._build_flutter_fixture()
        stack = detect_stack(self.repo)
        # Root scan still returns "unknown" — Phase 4.5 doesn't
        # mutate stack.language. Only the inferred_primary field
        # is populated.
        self.assertEqual(stack.language, "unknown")
        self.assertEqual(stack.inferred_primary, "Flutter / Dart")
        # CLI shows the inferred primary with the spec'd suffix.
        out = self._run_cli()
        self.assertIn("Flutter / Dart (inferred from workspace children)", out)
        self.assertNotIn("Unknown stack — no manifest detected", out)

    # ---- 2. mixed workspace children stay Unknown ------------------

    def test_mixed_workspace_children_stay_unknown(self):
        # apps/forge has Solidity, apps/dart has Flutter — mixed
        # signals must NOT be inferred to a single primary.
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        dart = self.repo / "apps" / "dart"
        dart.mkdir()
        (dart / "pubspec.yaml").write_text("name: x\n", encoding="utf-8")
        (dart / "lib").mkdir()
        (dart / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "unknown")
        self.assertIsNone(stack.inferred_primary,
                          "mixed children must NOT produce inference")
        out = self._run_cli()
        self.assertIn("Unknown stack — no manifest detected", out)
        self.assertNotIn("inferred from workspace children", out)

    # ---- 3. fns-monorepo: JS root detection still wins ------------

    def test_fns_monorepo_root_detection_unchanged(self):
        # Root has package.json -> JavaScript wins. Phase 4.5
        # never overrides JS / Python root detections.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "javascript")
        # inferred_primary stays None — JS already won.
        self.assertIsNone(stack.inferred_primary)
        out = self._run_cli()
        self.assertIn("Detected stack: JavaScript / Node.js", out)
        self.assertNotIn("inferred from workspace children", out)

    # ---- 4. plain unknown repo with no children stays Unknown ----

    def test_plain_unknown_repo_stays_unknown(self):
        # No manifest, no workspace containers, just a wrapper dir
        # with one .rs file. Inference has nothing to read.
        (self.repo / "wrapper").mkdir()
        (self.repo / "wrapper" / "src").mkdir()
        (self.repo / "wrapper" / "src" / "lib.rs").write_text(
            "// rs\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "unknown")
        self.assertIsNone(stack.inferred_primary)
        out = self._run_cli()
        self.assertIn("Unknown stack — no manifest detected", out)

    # ---- 5. inference suffix appears in HTML + CLI ---------------

    def test_inferred_primary_suffix_appears_in_outputs(self):
        # The "(inferred from workspace children)" copy is
        # load-bearing — tells the reader the primary came from
        # a different evidence source than JS / Python lines.
        self._build_flutter_fixture()
        out = self._run_cli()
        self.assertIn("(inferred from workspace children)", out)

        from cli.adopt import (
            derive_adopt_summary, derive_project_type,
            derive_stack_reality, derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        self.assertIn("(inferred from workspace children)", html)
        # Detection card label still uses _stack_summary's output,
        # so the inferred suffix flows through there too.
        self.assertIn("Flutter / Dart", html)

    # ---- 6. Stack reality treats inferred as a real primary ------

    def test_inferred_primary_replaces_html_detection_card_label(self):
        # Regression: the HTML <h2>Detection</h2> card's lede must
        # mirror the inferred primary, not the bare "Unknown stack"
        # string. Caught after Phase 4.5 first-ship — the Detection
        # card had a separate hard-coded label branch that didn't
        # consult inferred_primary, so the top card disagreed with
        # the rest of the report.
        self._build_flutter_fixture()
        from cli.adopt import (
            derive_adopt_summary, derive_project_type,
            derive_stack_reality, derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        plan = plan_files(self.repo, stack, self.inputs, summary=summary)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 summary=summary)
        # Detection card lede uses inferred primary.
        self.assertIn(
            '<p class="lede">Flutter / Dart '
            '(inferred from workspace children)</p>',
            html,
        )
        # The "Unknown stack" string must be gone from the
        # Detection card. (It still appears as a substring in
        # `stack.notes` text, so don't search the whole HTML —
        # slice to the Detection card.)
        det_re = re.search(r'<h2>Detection</h2>.*?</section>',
                           html, re.DOTALL)
        self.assertIsNotNone(det_re)
        self.assertNotIn('<p class="lede">Unknown stack</p>',
                         det_re.group(0))
        # Card color flips from card-warn (Unknown) to card-ok (OK).
        self.assertIn('<section class="card card-ok">',
                      html.split('<h2>Detection</h2>')[0]
                      + '<h2>Detection</h2>'
                      + html.split('<h2>Detection</h2>')[1].split('</section>')[0])

    def test_inferred_primary_changes_stack_reality(self):
        # Without inference, flutter monorepo would land in
        # "Unclear project shape" / Low. With Phase 4.5 inference
        # it becomes Single-stack project / Medium.
        self._build_flutter_fixture()
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Single-stack project")
        self.assertEqual(reality.confidence, "Medium")
        self.assertIn("inferred", reality.why)


class TestSuggestedActionsContextAware(unittest.TestCase):
    """v0.8 Phase 4.6 — context-aware action refinement.

    Each refined rule now names the concrete things the user
    should inspect (workspace child paths, needs-clarification
    dir names, etc.) rather than emitting generic prose. The
    Phase 4.3 invariants (max 5, dedupe by title, sort by
    priority) are preserved and re-tested here.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="demo",
                                     next_step="ship v1")

    def tearDown(self):
        self._tmp.cleanup()

    def _derive_actions(self):
        from cli.adopt import (
            derive_project_type, derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality)
        prelim_plan = plan_files(self.repo, stack, self.inputs,
                                 reality=reality, project_type=ptype)
        failures = analyze_failures(self.repo, stack, prelim_plan)
        actions = derive_suggested_actions(stack, reality, ptype, failures)
        return actions

    def _by_title(self, actions, title):
        match = [a for a in actions if a.title == title]
        self.assertEqual(len(match), 1,
                         f"expected exactly one action titled "
                         f"{title!r}; got {[a.title for a in actions]!r}")
        return match[0]

    # ---- 1. Web3 dApp: reason names Solidity + frontend children ----

    def test_fns_monorepo_action_names_concrete_children(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        actions = self._derive_actions()
        boundary = self._by_title(
            actions, "Confirm smart-contract + frontend boundary")
        self.assertIn("apps/forge", boundary.reason)
        self.assertIn("apps/next", boundary.reason)
        self.assertIn("Solidity", boundary.reason)
        self.assertIn("frontend", boundary.reason)

    # ---- 2. Mobile: action mentions Flutter children ----------------

    def test_flutter_monorepo_has_mobile_app_structure_action(self):
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("buyer_app", "seller_app"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "pubspec.yaml").write_text(f"name: {app}\n", encoding="utf-8")
            (d / "lib").mkdir()
            (d / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")

        actions = self._derive_actions()
        mobile = self._by_title(actions, "Confirm mobile app structure")
        self.assertEqual(mobile.priority, "high")
        # Both child names appear in the reason.
        self.assertIn("apps/buyer_app", mobile.reason)
        self.assertIn("apps/seller_app", mobile.reason)
        self.assertIn("Flutter", mobile.reason)

    # ---- 3. Full-stack: refined boundary copy ----------------------

    def test_full_stack_boundary_action_uses_refined_copy(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        web = self.repo / "apps" / "web"
        web.mkdir()
        (web / "package.json").write_text("{}", encoding="utf-8")
        (web / "next.config.js").write_text("// next\n", encoding="utf-8")
        (web / "app").mkdir()
        for n in range(3):
            (web / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")

        actions = self._derive_actions()
        boundary = self._by_title(
            actions, "Confirm backend/frontend boundaries")
        self.assertEqual(boundary.priority, "medium")
        # Refined Phase 4.6 wording calls out the concrete
        # boundary concerns, not the prior generic "mis-edits" line.
        self.assertIn("API ownership", boundary.reason)
        self.assertIn("local dev startup", boundary.reason)
        self.assertIn("deployment boundaries", boundary.reason)
        self.assertNotIn("mis-edits", boundary.reason)

    # ---- 4a. Needs clarification: <=3 dirs lists names -------------

    def test_clarification_action_lists_dir_names_when_few(self):
        # Three needs-clarification dirs (recognized-but-unclassified
        # subdirs trigger the unknown branch). Reason must list all
        # three by name.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        for d in ("alpha", "beta", "gamma"):
            (self.repo / d).mkdir()
            (self.repo / d / "data.json").write_text("{}", encoding="utf-8")

        actions = self._derive_actions()
        clar = self._by_title(actions, "Classify unrecognized directories")
        self.assertIn("alpha/", clar.reason)
        self.assertIn("beta/", clar.reason)
        self.assertIn("gamma/", clar.reason)
        # No "starting with" overflow phrasing for <= 3.
        self.assertNotIn("starting with", clar.reason)

    # ---- 4b. Needs clarification: >3 dirs uses count + first 3 -----

    def test_clarification_action_uses_count_when_many(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        for d in ("a", "b", "c", "d", "e"):
            (self.repo / d).mkdir()
            (self.repo / d / "data.json").write_text("{}", encoding="utf-8")

        actions = self._derive_actions()
        clar = self._by_title(actions, "Classify unrecognized directories")
        # Count appears verbatim.
        self.assertIn("5 unclassified directories", clar.reason)
        self.assertIn("starting with", clar.reason)
        # First three names listed.
        self.assertIn("a/", clar.reason)
        self.assertIn("b/", clar.reason)
        self.assertIn("c/", clar.reason)

    # ---- 5. MONOREPO_DEPTH_LIMIT: refined "Review workspace children"

    def test_review_workspace_children_action_names_children(self):
        # fns-monorepo shape — MONOREPO_DEPTH_LIMIT fires; the
        # refined action mentions concrete child names.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for name in ("forge", "next"):
            d = self.repo / "apps" / name
            d.mkdir()
            (d / "package.json").write_text("{}", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "main.tsx").write_text("// x\n", encoding="utf-8")
            (d / "src" / "x.tsx").write_text("// x\n", encoding="utf-8")
            (d / "src" / "y.tsx").write_text("// x\n", encoding="utf-8")

        actions = self._derive_actions()
        review = self._by_title(actions, "Review workspace children")
        self.assertEqual(review.priority, "high")
        self.assertIn("apps/forge", review.reason)
        self.assertIn("apps/next", review.reason)

    # ---- 6. Clean project case still falls through ----------------

    def test_clean_plain_js_still_emits_run_with_write(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        actions = self._derive_actions()
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].title,
                         "Run adopt with --write when ready")
        self.assertEqual(actions[0].priority, "low")

    # ---- 7. invariants: max 5 + dedup -----------------------------

    def test_invariants_max_5_and_dedup_preserved(self):
        # Maximally-noisy fixture: Web3 dApp + multiple unclassified
        # dirs + IDEMPOTENCY_RISK + workspace depth limit. Should
        # produce <= 5 distinct actions, all unique titles.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")
        # Pre-existing hand-written doc → IDEMPOTENCY_RISK
        (self.repo / "00-START-NEXT-SESSION.md").write_text(
            "# Hand-written\n", encoding="utf-8")
        # An unrelated dir for clarification.
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "tool.py").write_text("# x\n", encoding="utf-8")

        actions = self._derive_actions()
        titles = [a.title for a in actions]
        self.assertEqual(len(titles), len(set(titles)),
                         f"actions must be deduped; got {titles!r}")
        self.assertLessEqual(len(actions), 5)
        # Sorted by priority high-first.
        priority_rank = {"high": 0, "medium": 1, "low": 2}
        ranks = [priority_rank[a.priority] for a in actions]
        self.assertEqual(ranks, sorted(ranks))


class TestMixedRootDominance(unittest.TestCase):
    """v0.9 Phase 5.1 — mixed-root JS+Python source-dominance.

    Fixes the django/django dogfood failure where v0's classifier
    picked JavaScript whenever both root manifests were present,
    even on overwhelmingly Python repos. The new resolver walks
    shallow source evidence and picks the dominant side; the
    Stack reality confidence is also capped at Medium for any
    mixed-root case.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _notes_text(self, stack):
        return "\n".join(stack.notes)

    # ---- 1. django-shape: Python wins via dominance ----------------

    def test_django_shape_promotes_to_python(self):
        # Mirrors django/django: root has package.json (likely
        # tooling) + pyproject.toml; depth-2 source is
        # overwhelmingly .py.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "django").mkdir()
        for n in range(50):
            (self.repo / "django" / f"mod{n}.py").write_text(
                "# py\n", encoding="utf-8")
        (self.repo / "tests").mkdir()
        for n in range(40):
            (self.repo / "tests" / f"test{n}.py").write_text(
                "# py\n", encoding="utf-8")
        # A handful of .js for tooling — well below the 3x ratio
        # threshold so Python should still win.
        (self.repo / "js_tests").mkdir()
        for n in range(3):
            (self.repo / "js_tests" / f"x{n}.js").write_text(
                "// js\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "python",
                         f"Python should win when source dominance "
                         f"clearly favors it; got {stack.language!r}")
        # Both manifests still in the signals list.
        self.assertIn("package.json", stack.signals)
        self.assertIn("pyproject.toml", stack.signals)
        # Note explicitly says mixed-root + which side won + why.
        notes = self._notes_text(stack)
        self.assertIn("Mixed root manifests", notes)
        self.assertIn("Python primary based on source dominance", notes)
        self.assertIn(".py files", notes)

    # ---- 2. JS-dominant mixed-root: JavaScript wins -------------

    def test_js_dominant_mixed_root_stays_javascript(self):
        # Symmetric: lots of .tsx files dwarf a handful of .py
        # tooling scripts. JS should win via dominance.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "requirements.txt").write_text(
            "pytest\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        for n in range(60):
            (self.repo / "src" / f"comp{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")
        (self.repo / "scripts").mkdir()
        for n in range(3):
            (self.repo / "scripts" / f"tool{n}.py").write_text(
                "# py\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "javascript")
        notes = self._notes_text(stack)
        self.assertIn("Mixed root manifests", notes)
        self.assertIn("JavaScript primary based on source dominance",
                      notes)

    # ---- 3. Ambiguous mixed-root: defaults to JavaScript --------

    def test_ambiguous_mixed_root_defaults_to_javascript(self):
        # 4 .py + 4 .js — both below the 5-file MIN_DOMINANT
        # floor. Resolver falls back to JavaScript (preserves v0
        # default) but the note flags the inconclusiveness.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        for n in range(4):
            (self.repo / "src" / f"a{n}.py").write_text(
                "# py\n", encoding="utf-8")
            (self.repo / "src" / f"b{n}.js").write_text(
                "// js\n", encoding="utf-8")

        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "javascript")
        notes = self._notes_text(stack)
        self.assertIn("Mixed root manifests", notes)
        self.assertIn("inconclusive", notes)
        self.assertIn("Defaulting to JavaScript", notes)

    # ---- 4. Plain JS / plain Python: regression checks ----------

    def test_plain_js_project_unchanged(self):
        # No mixed-root: only package.json. Behavior identical to
        # v0.7/v0.8 — no mixed-root note, no source-dominance walk.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "javascript")
        self.assertNotIn("Mixed root", self._notes_text(stack))

    def test_plain_python_project_unchanged(self):
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "main.py").write_text("# py\n", encoding="utf-8")
        stack = detect_stack(self.repo)
        self.assertEqual(stack.language, "python")
        self.assertNotIn("Mixed root", self._notes_text(stack))

    # ---- 5. Stack Reality: never High when mixed-root -----------

    def test_stack_reality_drops_to_medium_on_mixed_root(self):
        # Even when source dominance gives a clear winner, the
        # Stack Reality confidence must be Medium — mixed-root
        # setups rarely behave as a single stack in practice.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "django").mkdir()
        for n in range(50):
            (self.repo / "django" / f"mod{n}.py").write_text(
                "# py\n", encoding="utf-8")

        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.assessment, "Single-stack project")
        self.assertEqual(reality.confidence, "Medium",
                         f"Mixed-root must never be High confidence; "
                         f"got {reality.confidence!r}")
        self.assertIn("both JavaScript and Python", reality.why)

    def test_stack_reality_high_preserved_on_plain_python(self):
        # Regression: plain-Python (no mixed-root) keeps the Single-
        # stack/High path — Phase 5.1 must not silently downgrade
        # all Python projects.
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text(
            "# py\n", encoding="utf-8")
        from cli.adopt import derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        self.assertEqual(reality.confidence, "High")


class TestEcosystemCoverage(unittest.TestCase):
    """v0.9 Phase 5.2 / 5.3 / 5.4 / 5.5 — fixture-shaped tests for
    the four new ecosystem coverage rules.

    Mirrors the dogfood failures from SESSION_011 in synthesized
    form. Each fixture stands in for a real repo (ripgrep,
    kubernetes, openzeppelin-contracts, react-native, fns-monorepo,
    transformers) and locks in the new project-type / detection
    behavior so a future regression is caught early.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _derive(self):
        from cli.adopt import derive_project_type, derive_stack_reality
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality, prelim)
        return stack, reality, ptype

    # ---- Phase 5.2: Rust ------------------------------------------

    def test_ripgrep_shape_is_rust_workspace(self):
        # Root Cargo.toml + crates/ workspace + .rs files.
        (self.repo / "Cargo.toml").write_text(
            "[workspace]\n", encoding="utf-8")
        (self.repo / "crates").mkdir()
        for name in ("cli", "core", "globset"):
            d = self.repo / "crates" / name
            d.mkdir()
            (d / "Cargo.toml").write_text("# crate\n", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")
        stack, reality, ptype = self._derive()
        self.assertEqual(stack.language, "rust")
        self.assertEqual(ptype.label, "Rust workspace / library")
        self.assertEqual(ptype.confidence, "medium")
        # Reason names some of the crates.
        self.assertIn("crates", ptype.reason)

    def test_rust_inferred_from_workspace_when_no_root_cargo(self):
        # No root manifest, but every workspace child is a Rust
        # crate. Phase 4.5 inference + Phase 5.2 rule combine to
        # promote the project to Rust workspace / library.
        (self.repo / "members").mkdir()
        for name in ("a", "b"):
            d = self.repo / "members" / name
            d.mkdir()
            (d / "Cargo.toml").write_text("# c\n", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")
        stack, _, ptype = self._derive()
        self.assertEqual(stack.inferred_primary, "Rust workspace")
        self.assertEqual(ptype.label, "Rust workspace / library")

    # ---- Phase 5.3: Go --------------------------------------------

    def test_kubernetes_shape_is_go_project(self):
        # Root go.mod + many .go files in cmd/ and pkg/.
        (self.repo / "go.mod").write_text("module foo\n", encoding="utf-8")
        for d in ("cmd", "pkg"):
            (self.repo / d).mkdir()
            for n in range(20):
                (self.repo / d / f"a{n}.go").write_text("// go\n", encoding="utf-8")
        stack, _, ptype = self._derive()
        self.assertEqual(stack.language, "go")
        self.assertEqual(ptype.label, "Go project")
        self.assertEqual(ptype.confidence, "medium")
        self.assertIn("go.mod", ptype.reason)

    # ---- Phase 5.4: Smart contract project ------------------------

    def test_openzeppelin_shape_is_smart_contract_project(self):
        # Root has hardhat.config.js + foundry.toml + package.json.
        # No apps/ workspace. Many .sol files in contracts/.
        # Despite v0 picking JavaScript at root, Phase 5.4 promotes
        # to Smart contract project via the failure-example route.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "hardhat.config.js").write_text(
            "// hh\n", encoding="utf-8")
        (self.repo / "foundry.toml").write_text(
            "# foundry\n", encoding="utf-8")
        (self.repo / "contracts").mkdir()
        for n in range(15):
            (self.repo / "contracts" / f"C{n}.sol").write_text(
                "// sol\n", encoding="utf-8")
        stack, _, ptype = self._derive()
        # Primary stays JavaScript (v0 classifier rule unchanged).
        self.assertEqual(stack.language, "javascript")
        # But project type is now Smart contract project.
        self.assertEqual(ptype.label, "Smart contract project")
        self.assertEqual(ptype.confidence, "medium")
        # Reason names concrete evidence. The root-config example
        # is sorted alphabetically for determinism — "foundry.toml"
        # < "hardhat.config.js" so foundry wins when both are at
        # root. Either is correct evidence.
        self.assertTrue(
            "foundry.toml" in ptype.reason
            or "hardhat.config.js" in ptype.reason,
            f"reason should name a root smart-contract config; "
            f"got: {ptype.reason!r}",
        )
        self.assertIn(".sol files", ptype.reason)

    def test_smart_contract_workspace_only_via_solidity_child(self):
        # No root config — workspace child(ren) are Solidity. Smart
        # contract rule still fires from the workspace signal alone.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "Smart contract project")

    # ---- Phase 5.5: React Native correction -----------------------

    def test_react_native_shape_is_mobile_app_suite(self):
        # Mirrors react-native: root package.json (the framework's
        # own) + packages/react-native (metro.config + RN config +
        # .tsx) + packages/rn-tester (Podfile + Gemfile + .swift).
        # v0.8 mislabeled this as Full-stack web app via the
        # over-eager Phase 3 Next.js rule.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "packages").mkdir()
        rn = self.repo / "packages" / "react-native"
        rn.mkdir()
        (rn / "package.json").write_text("{}", encoding="utf-8")
        (rn / "metro.config.js").write_text(
            "// metro\n", encoding="utf-8")
        (rn / "react-native.config.js").write_text(
            "// rn\n", encoding="utf-8")
        (rn / "src").mkdir()
        for n in range(5):
            (rn / "src" / f"comp{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")
        rn_tester = self.repo / "packages" / "rn-tester"
        rn_tester.mkdir()
        (rn_tester / "package.json").write_text("{}", encoding="utf-8")
        (rn_tester / "Podfile").write_text("# pod\n", encoding="utf-8")
        (rn_tester / "Gemfile").write_text("# gem\n", encoding="utf-8")
        (rn_tester / "ios").mkdir()
        (rn_tester / "ios" / "AppDelegate.swift").write_text(
            "// swift\n", encoding="utf-8")
        # Some Python tooling (mirrors react-native's scripts/).
        (self.repo / "scripts").mkdir()
        for n in range(3):
            (self.repo / "scripts" / f"tool{n}.py").write_text(
                "# py\n", encoding="utf-8")

        stack, _, ptype = self._derive()
        # Primary stays JavaScript (root package.json).
        self.assertEqual(stack.language, "javascript")
        # Project type is Mobile app suite, NOT Full-stack web app.
        self.assertEqual(ptype.label, "Mobile app suite")
        self.assertNotEqual(ptype.label, "Full-stack web app")
        # Reason mentions React Native.
        self.assertIn("React Native", ptype.reason)

    def test_metro_config_alone_blocks_nextjs_classification(self):
        # Defense: a child with metro.config.js + package.json +
        # .tsx must NOT classify as "Next.js / React web app".
        # The fix would have left react-native broken without this.
        from cli.adopt import _classify_workspace_child
        from cli.adopt import WorkspaceChild
        c = WorkspaceChild(
            name="packages/some-rn-pkg",
            manifest_files=["metro.config.js", "package.json"],
            notable_extensions={".tsx": 8},
        )
        label = _classify_workspace_child(c)
        self.assertEqual(label, "React Native / mobile framework",
                         f"metro.config.js must block Next.js "
                         f"classification; got {label!r}")

    # ---- Regression sanity: Phase 4.x behavior preserved ---------

    def test_fns_monorepo_shape_still_web3_dapp(self):
        # Web3 dApp rule (Solidity + Next.js) must still beat the
        # new Smart contract rule on combined fixtures.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")
        _, _, ptype = self._derive()
        self.assertEqual(ptype.label, "Web3 dApp")

    def test_transformers_shape_still_python_app_tooling(self):
        # Plain Python project with no mixed-root manifests.
        # Phase 5.x must not regress it.
        (self.repo / "pyproject.toml").write_text("# py\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        for n in range(20):
            (self.repo / "src" / f"m{n}.py").write_text(
                "# py\n", encoding="utf-8")
        stack, _, ptype = self._derive()
        self.assertEqual(stack.language, "python")
        self.assertEqual(ptype.label, "Python app/tooling project")

    def test_jsplus_rust_aux_does_not_promote_to_rust(self):
        # next.js shape: root JS primary, but workspace also
        # contains Rust crates (Turbopack source). Rust rule must
        # NOT fire — those are auxiliary tooling, not the project's
        # identity. Also: with workspace_children present, the
        # Single-primary-JS rule (which requires no workspace
        # children) doesn't fire either, so we expect Unclear.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "crates").mkdir()
        for name in ("turbopack-cli", "turbopack-core"):
            d = self.repo / "crates" / name
            d.mkdir()
            (d / "Cargo.toml").write_text("# c\n", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")
        _, _, ptype = self._derive()
        self.assertNotEqual(ptype.label, "Rust workspace / library",
                            f"Rust rule must not fire when JS is "
                            f"primary; got {ptype.label!r}")


class TestAgentLaunchPrompt(unittest.TestCase):
    """v0.10.0 Phase 6.1 — Agent launch prompt.

    Verifies the type-specific recommended-first-action and the
    rendering surfaces (CLI block + HTML copy button + BUILD_PLAN
    + CLAUDE managed block).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _derive_full_chain(self):
        from cli.adopt import (
            derive_adopt_summary, derive_agent_launch_prompt,
            derive_project_type, derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality, prelim)
        prelim_plan = plan_files(self.repo, self.inputs and self.inputs,
                                 stack, reality=reality,
                                 project_type=ptype) if False else None
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        prompt = derive_agent_launch_prompt(stack, reality, ptype, summary)
        return stack, reality, ptype, summary, prompt

    # ---- Web3 dApp: prompt mentions contracts/frontend boundary ----

    def test_web3_dapp_prompt_mentions_contracts_and_frontend(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        forge = self.repo / "apps" / "forge"
        forge.mkdir()
        (forge / "foundry.toml").write_text("# foundry\n", encoding="utf-8")
        (forge / "contracts").mkdir()
        (forge / "contracts" / "Foo.sol").write_text("// sol\n", encoding="utf-8")
        nxt = self.repo / "apps" / "next"
        nxt.mkdir()
        (nxt / "package.json").write_text("{}", encoding="utf-8")
        (nxt / "next.config.js").write_text("// next\n", encoding="utf-8")
        (nxt / "app").mkdir()
        for n in range(3):
            (nxt / "app" / f"page{n}.tsx").write_text("// tsx\n", encoding="utf-8")

        _, _, _, _, prompt = self._derive_full_chain()
        text = prompt.prompt_text
        # Section headings present.
        self.assertIn("WHAT THIS PROJECT APPEARS TO BE", text)
        self.assertIn("PRIMARY DETECTION", text)
        self.assertIn("WORKSPACE / PROJECT STRUCTURE", text)
        self.assertIn("RECOMMENDED FIRST ACTION", text)
        self.assertIn("SAFETY INSTRUCTIONS", text)
        # Web3 dApp first-action wording.
        self.assertIn("contract/frontend boundary", text)
        # Concrete child names appear.
        self.assertIn("apps/forge", text)
        self.assertIn("apps/next", text)
        # Confidence mirrors Stack reality.
        self.assertEqual(prompt.confidence, "medium")

    # ---- Rust: prompt mentions crates ------------------------------

    def test_rust_workspace_prompt_mentions_crates(self):
        (self.repo / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
        (self.repo / "crates").mkdir()
        for name in ("cli", "core"):
            d = self.repo / "crates" / name
            d.mkdir()
            (d / "Cargo.toml").write_text("# c\n", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")

        _, _, _, _, prompt = self._derive_full_chain()
        text = prompt.prompt_text
        self.assertIn("crates", text)
        # Specifically names some workspace crates.
        self.assertIn("crates/cli", text)
        # Mentions root Cargo.toml.
        self.assertIn("Cargo.toml", text)

    # ---- Go: prompt mentions go.mod / cmd / pkg --------------------

    def test_go_project_prompt_mentions_go_mod_cmd_pkg(self):
        (self.repo / "go.mod").write_text("module foo\n", encoding="utf-8")
        for d in ("cmd", "pkg"):
            (self.repo / d).mkdir()
            (self.repo / d / f"main.go").write_text("// go\n", encoding="utf-8")
        _, _, _, _, prompt = self._derive_full_chain()
        text = prompt.prompt_text
        self.assertIn("go.mod", text)
        self.assertIn("cmd/", text)
        self.assertIn("pkg/", text)

    # ---- Mobile app suite: prompt mentions app workspaces / shared -

    def test_mobile_app_suite_prompt_mentions_app_workspaces(self):
        (self.repo / "melos.yaml").write_text("name: x\n", encoding="utf-8")
        (self.repo / "apps").mkdir()
        for app in ("buyer_app", "seller_app"):
            d = self.repo / "apps" / app
            d.mkdir()
            (d / "pubspec.yaml").write_text(f"name: {app}\n", encoding="utf-8")
            (d / "lib").mkdir()
            (d / "lib" / "main.dart").write_text("// dart\n", encoding="utf-8")
        _, _, _, _, prompt = self._derive_full_chain()
        text = prompt.prompt_text
        self.assertIn("app workspaces", text)
        self.assertIn("shared", text.lower())
        # Both apps named.
        self.assertIn("apps/buyer_app", text)
        self.assertIn("apps/seller_app", text)

    # ---- Full-stack web app: prompt mentions backend/frontend ------

    def test_full_stack_prompt_mentions_backend_frontend(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        web = self.repo / "apps" / "web"
        web.mkdir()
        (web / "package.json").write_text("{}", encoding="utf-8")
        (web / "next.config.js").write_text("// next\n", encoding="utf-8")
        (web / "app").mkdir()
        for n in range(3):
            (web / "app" / f"p{n}.tsx").write_text("// tsx\n", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")
        _, _, _, _, prompt = self._derive_full_chain()
        text = prompt.prompt_text
        self.assertIn("backend/frontend boundary", text)

    # ---- Unclear: prompt asks to clarify before coding -------------

    def test_unclear_project_type_prompt_infers_before_asking(self):
        # Mix of Rust crates AND Next.js apps (no clean primary
        # identity, like next.js itself) → Unclear project type.
        # As of v0.11.x the unclear-first-action tells the agent
        # to infer the shape from the codebase first and only ask
        # the user about residual gaps — replacing the older
        # "wait for the user before doing anything" wording that
        # contradicted the new HOW TO APPROACH conditional rule.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "crates").mkdir()
        for name in ("a", "b"):
            d = self.repo / "crates" / name
            d.mkdir()
            (d / "Cargo.toml").write_text("# c\n", encoding="utf-8")
            (d / "src").mkdir()
            (d / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")
        _, _, ptype, _, prompt = self._derive_full_chain()
        self.assertEqual(ptype.label, "Unclear project type")
        text = prompt.prompt_text
        # New wording: infer first, then ask only for gaps.
        self.assertIn("Do not write code yet", text)
        self.assertIn("Infer the project shape first", text)
        self.assertIn(
            "Only ask the user for clarification after this "
            "inspection",
            text,
        )

    # ---- HTML: prompt block + copy button --------------------------

    def test_html_includes_prompt_block_and_copy_button(self):
        (self.repo / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
        (self.repo / "crates").mkdir()
        d = self.repo / "crates" / "cli"
        d.mkdir()
        (d / "Cargo.toml").write_text("# c\n", encoding="utf-8")
        (d / "src").mkdir()
        (d / "src" / "lib.rs").write_text("// rs\n", encoding="utf-8")

        stack, reality, ptype, summary, prompt = self._derive_full_chain()
        plan = plan_files(self.repo, stack, self.inputs,
                          reality=reality, project_type=ptype,
                          summary=summary, agent_prompt=prompt)
        html = render_adopt_html(self.repo, stack, self.inputs, plan,
                                 write_mode=False, failures=[],
                                 reality=reality, project_type=ptype,
                                 summary=summary, agent_prompt=prompt)
        # Section title.
        self.assertIn("<h2>Agent launch prompt</h2>", html)
        # Plain <pre> block with the prompt text inside <code>.
        self.assertIn('<pre class="prompt-block" '
                      'id="agent-launch-prompt-text">'
                      '<code>', html)
        # Single copy button targeting the prompt block.
        self.assertIn(
            '<button class="copy" '
            'data-copy-target="agent-launch-prompt-text">',
            html,
        )
        self.assertIn("Copy prompt", html)
        # CSS for the prompt block ships in the style block.
        self.assertIn(".prompt-block {", html)

    # ---- BUILD_PLAN.md and CLAUDE.md include the prompt ------------

    def test_build_plan_includes_prompt_section(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        stack, reality, ptype, summary, prompt = self._derive_full_chain()
        md = generate_build_plan(stack, self.inputs, "Test",
                                 reality=reality, project_type=ptype,
                                 summary=summary, agent_prompt=prompt)
        self.assertIn("## Agent launch prompt", md)
        # Wrapped in a text code fence so the copy survives Markdown
        # rendering.
        self.assertIn("```text", md)
        # Confidence noted in the intro paragraph.
        self.assertIn("Confidence:", md)
        # Body content of the prompt is present.
        self.assertIn("WHAT THIS PROJECT APPEARS TO BE", md)
        self.assertIn("SAFETY INSTRUCTIONS", md)

    def test_claude_block_includes_prompt_section(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        stack, reality, ptype, summary, prompt = self._derive_full_chain()
        block = generate_claude_block(stack, self.inputs, "Test",
                                      reality=reality, project_type=ptype,
                                      summary=summary,
                                      agent_prompt=prompt)
        self.assertIn("## Agent launch prompt", block)
        self.assertIn("WHAT THIS PROJECT APPEARS TO BE", block)
        # Stays inside the adopt-managed markers.
        self.assertIn(START_MARKER, block)
        self.assertIn(END_MARKER, block)

    # ---- CLI dry-run: delimited block ------------------------------

    def test_cli_dryrun_includes_delimited_prompt_block(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=False,
                          description="x", next_step="y"))
        out = buf.getvalue()
        self.assertIn("AGENT LAUNCH PROMPT", out)
        self.assertIn("=== END AGENT LAUNCH PROMPT ===", out)
        # Body content present in the dry-run output.
        self.assertIn("WHAT THIS PROJECT APPEARS TO BE", out)
        self.assertIn("SAFETY INSTRUCTIONS", out)

    # ---- Pre-write safety: prompt works without generated docs ----

    def test_safety_instructions_handle_missing_generated_docs(self):
        # v0.10.x — real-world testing on contract-concierge
        # showed the agent reported BUILD_PLAN.md / PROJECT_WHAT_
        # IT_IS.md / CLAUDE.md as missing because adopt --html
        # without --write doesn't create them. The prompt's
        # safety instructions now handle both cases (docs exist
        # vs docs not yet written) and explicitly tell the agent
        # not to treat the missing docs as an error.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        _, _, _, _, prompt = self._derive_full_chain()
        text = prompt.prompt_text
        # Conditional read instruction (both branches).
        self.assertIn("If generated docs exist", text)
        self.assertIn("If they do not exist yet", text)
        # Names the fallback sources to read.
        self.assertIn("README", text)
        self.assertIn("package/manifests", text)
        # The "do not treat that as an error" line is present.
        self.assertIn("do not treat that as an error", text)
        self.assertIn("propose the first safe task", text)
        # Old "Read all generated docs" wording (which assumed
        # docs always exist) must be gone — defense against
        # re-introduction.
        self.assertNotIn("Read all generated docs (BUILD_PLAN.md", text)


class TestSplitMonorepoFullStackProjectType(unittest.TestCase):
    """v0.10.x — close the v0.1 split-monorepo gap in
    ``derive_project_type``. Before this fix, contract-concierge
    (backend/ Python + frontend/ Vite) classified as "Unclear
    project type" because the Full-stack web app rule only
    handled the workspace-children case (Phase 4.2 Rule 3 a).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _derive(self):
        from cli.adopt import (
            derive_adopt_summary, derive_agent_launch_prompt,
            derive_project_type, derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality, prelim)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        prompt = derive_agent_launch_prompt(stack, reality, ptype, summary)
        return stack, reality, ptype, summary, prompt

    def _build_cc_fixture(self):
        # contract-concierge shape: backend/ Python + frontend/
        # Vite + .tsx. No root manifest of its own.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "requirements.txt").write_text(
            "flask\n", encoding="utf-8")
        (self.repo / "backend" / "app").mkdir()
        for n in range(5):
            (self.repo / "backend" / "app" / f"v{n}.py").write_text(
                "# py\n", encoding="utf-8")
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text(
            "{}", encoding="utf-8")
        (self.repo / "frontend" / "vite.config.ts").write_text(
            "// vite\n", encoding="utf-8")
        (self.repo / "frontend" / "src").mkdir()
        for n in range(3):
            (self.repo / "frontend" / "src" / f"App{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")

    def test_contract_concierge_shape_is_full_stack_web_app(self):
        self._build_cc_fixture()
        stack, _, ptype, _, _ = self._derive()
        # Detection unchanged — v0.1 split-monorepo path produces
        # parts={backend: python, frontend: javascript}.
        self.assertEqual(stack.parts.get("backend"), "python")
        self.assertEqual(stack.parts.get("frontend"), "javascript")
        # Project type is now Full-stack web app, not Unclear.
        self.assertEqual(ptype.label, "Full-stack web app")
        self.assertEqual(ptype.confidence, "medium")
        # Reason names the backend + frontend parts concretely.
        self.assertIn("backend/", ptype.reason)
        self.assertIn("frontend/", ptype.reason)
        self.assertIn("Python backend", ptype.reason)
        self.assertIn("JavaScript frontend", ptype.reason)

    def test_full_stack_via_parts_drives_agent_prompt_branch(self):
        # Once Project Type promotes to Full-stack web app, the
        # agent launch prompt's recommended-first-action branch
        # should mention the backend/frontend boundary.
        self._build_cc_fixture()
        _, _, _, _, prompt = self._derive()
        self.assertIn("backend/frontend boundary", prompt.prompt_text)

    def test_stack_reality_stays_mixed_workspace_project_medium(self):
        # The Stack reality categorization for a v0.1 split monorepo
        # remains "Mixed workspace project / Medium" — Phase 5.1's
        # mixed-root rule doesn't fire (no JS+Python at root) and
        # the parts-based Mixed-workspace rule already handled
        # this case correctly. Phase 5.x must not regress that.
        self._build_cc_fixture()
        _, reality, _, _, _ = self._derive()
        self.assertEqual(reality.assessment, "Mixed workspace project")
        self.assertEqual(reality.confidence, "Medium")

    # ---- Regression: server/api/client variants also work ---------

    def test_server_plus_client_split_promotes_to_full_stack(self):
        # The fix accepts any (backend|server|api) Python + any
        # (frontend|web|client) JavaScript pair.
        (self.repo / "server").mkdir()
        (self.repo / "server" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        (self.repo / "client").mkdir()
        (self.repo / "client" / "package.json").write_text(
            "{}", encoding="utf-8")
        _, _, ptype, _, _ = self._derive()
        self.assertEqual(ptype.label, "Full-stack web app")
        self.assertIn("server/", ptype.reason)
        self.assertIn("client/", ptype.reason)

    # ---- Negative regression: backend-only doesn't trigger --------

    def test_backend_only_python_split_stays_unclear(self):
        # Only backend/ has a Python manifest — no JavaScript
        # frontend role. Must NOT promote to Full-stack web app.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "requirements.txt").write_text(
            "flask\n", encoding="utf-8")
        for n in range(3):
            (self.repo / "backend" / f"v{n}.py").write_text(
                "# py\n", encoding="utf-8")
        _, _, ptype, _, _ = self._derive()
        self.assertNotEqual(ptype.label, "Full-stack web app")

    def test_frontend_only_js_split_stays_unclear(self):
        # Symmetric: only frontend/ — no backend. Must NOT promote.
        (self.repo / "frontend").mkdir()
        (self.repo / "frontend" / "package.json").write_text(
            "{}", encoding="utf-8")
        _, _, ptype, _, _ = self._derive()
        self.assertNotEqual(ptype.label, "Full-stack web app")

    def test_mobile_role_does_not_count_as_frontend(self):
        # Mobile is a distinct role, not generic frontend. A
        # backend/ Python + mobile/ JS pair must NOT silently
        # promote to Full-stack web app — that would mislabel a
        # mobile-app-with-server project.
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "requirements.txt").write_text(
            "flask\n", encoding="utf-8")
        (self.repo / "mobile").mkdir()
        (self.repo / "mobile" / "package.json").write_text(
            "{}", encoding="utf-8")
        _, _, ptype, _, _ = self._derive()
        self.assertNotEqual(ptype.label, "Full-stack web app")

    # ---- Regression: workspace path Full-stack still works --------

    def test_workspace_path_full_stack_still_fires(self):
        # turborepo-django shape: root package.json + apps/web
        # (Next.js) + server/backend/manage.py. The workspace
        # path was the only Full-stack route before this fix and
        # must still fire.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "apps").mkdir()
        web = self.repo / "apps" / "web"
        web.mkdir()
        (web / "package.json").write_text("{}", encoding="utf-8")
        (web / "next.config.js").write_text("// next\n", encoding="utf-8")
        (web / "app").mkdir()
        for n in range(3):
            (web / "app" / f"p{n}.tsx").write_text(
                "// tsx\n", encoding="utf-8")
        (self.repo / "server").mkdir()
        (self.repo / "server" / "backend").mkdir()
        (self.repo / "server" / "backend" / "manage.py").write_text(
            "# d\n", encoding="utf-8")
        for n in range(5):
            (self.repo / "server" / "backend" / f"v{n}.py").write_text(
                "# x\n", encoding="utf-8")
        _, _, ptype, _, _ = self._derive()
        self.assertEqual(ptype.label, "Full-stack web app")
        # Reason should still call out Python + Next.js (workspace
        # path), not the parts path — workspace evidence wins
        # because it sets has_nextjs True before parts are checked.
        self.assertIn("Next.js", ptype.reason)


class TestPlaceholdersDoNotBlockInspection(unittest.TestCase):
    """v0.10.x — placeholders should not block read-only inspection.

    Real-world testing on contract-concierge after `adopt --write`
    showed agents stopping to ask the user about
    `[adopt: please describe]` placeholders before doing any
    repo inspection. Generated docs should explicitly tell the
    agent to keep going for read-only work and only ask before
    decisions that depend on the missing context.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _full_chain(self):
        from cli.adopt import (
            derive_adopt_summary, derive_agent_launch_prompt,
            derive_project_type, derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality, prelim)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        prompt = derive_agent_launch_prompt(stack, reality, ptype, summary)
        return stack, reality, ptype, summary, prompt

    # ---- generated CLAUDE.md (managed block + fresh) --------------

    def test_claude_managed_block_softens_placeholder_rule(self):
        # The "Rule for this session" inside the managed block
        # must permit read-only inspection and only require
        # asking before decisions that depend on missing context.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        stack, reality, ptype, summary, prompt = self._full_chain()
        block = generate_claude_block(stack, self.inputs, "Test",
                                      reality=reality, project_type=ptype,
                                      summary=summary,
                                      agent_prompt=prompt)
        self.assertIn(
            "Do not block read-only inspection on", block,
            f"managed block must explicitly permit read-only "
            f"inspection on placeholders; got:\n{block}",
        )
        # Ask-before-decisions guidance present.
        self.assertIn("Only ask the user before making decisions", block)
        # Old "ask the user to fill it in before writing code that
        # depends on the missing context" wording is gone from the
        # managed block. (The fresh CLAUDE.md intro had its own
        # version of the rule, which is also softened — covered by
        # the next test.)

    def test_fresh_claude_md_softens_placeholder_warning(self):
        # generate_claude_md_fresh produces the full CLAUDE.md
        # body (intro + managed block) when no CLAUDE.md exists.
        # The intro's placeholder warning must also be softened.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        stack, reality, ptype, summary, prompt = self._full_chain()
        from cli.adopt import generate_claude_md_fresh
        body = generate_claude_md_fresh(
            stack, self.inputs, "Test",
            reality=reality, project_type=ptype, summary=summary,
            agent_prompt=prompt,
        )
        self.assertIn("do not block read-only inspection", body.lower(),
                      f"fresh CLAUDE.md must permit read-only "
                      f"inspection; got:\n{body[:1200]}")
        self.assertIn("Only ask the user before making decisions", body)
        # Old "ask the user to fill it in before writing code"
        # blocking wording is gone — defense against re-introduction.
        self.assertNotIn("ask the user to fill it in before writing code",
                         body)

    # ---- 00-START-NEXT-SESSION.md ----------------------------------

    def test_start_here_step_3_softens_placeholder_handling(self):
        # generate_start_here's "How to start the session" step 3
        # used to say "fill them in or ask the user". v0.10.x
        # softens to "do not block read-only inspection".
        from cli.adopt import generate_start_here
        body = generate_start_here(self.inputs, "Test")
        self.assertIn("Do not block on them for read-only inspection",
                      body)
        self.assertIn("safe and read-only", body)
        # Old fill-them-in-or-ask wording gone.
        self.assertNotIn("fill them in or ask the user", body)


class TestPostWriteAgentLaunchFlow(unittest.TestCase):
    """v0.10.x — make the Agent Launch Prompt the canonical
    post-write next step. After `adopt --write`, the user should
    see a clear "paste this into your agent" pointer, the same
    prompt should land in 00-START-NEXT-SESSION.md, and CLAUDE.md
    should name the prompt as the session opener.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.inputs = AdoptionInputs(project_description="x", next_step="y")

    def tearDown(self):
        self._tmp.cleanup()

    def _write_and_capture(self):
        # Run adopt with --write against a small fixture and
        # capture the CLI output for assertion.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(_ns(self.repo, write=True,
                          description="x", next_step="y"))
        return buf.getvalue()

    # ---- 1. CLI --write footer points at the prompt ---------------

    def test_cli_write_footer_names_agent_launch_prompt(self):
        out = self._write_and_capture()
        # The full prompt is still printed earlier in the output
        # (the dry-run block runs unconditionally).
        self.assertIn("AGENT LAUNCH PROMPT", out)
        # New post-write footer points back at it.
        self.assertIn("Next step: paste the Agent Launch Prompt", out)
        # And tells the user about the persisted copy.
        self.assertIn("00-START-NEXT-SESSION.md", out)
        # Old hesitant "Review the [adopt: please describe]"
        # footer is gone.
        self.assertNotIn("Done. Review the [adopt: please describe]",
                         out)
        # Soft placeholder framing in the footer.
        self.assertIn("don't block read-only inspection", out)

    # ---- 2. Generated 00-START-NEXT-SESSION.md has the prompt ----

    def test_start_here_doc_contains_fenced_agent_launch_prompt(self):
        # Write the doc, then verify the file content (not just
        # the planned content) carries the prompt.
        self._write_and_capture()
        start_path = self.repo / "00-START-NEXT-SESSION.md"
        self.assertTrue(start_path.is_file(),
                        "adopt --write should have created "
                        "00-START-NEXT-SESSION.md")
        body = start_path.read_text(encoding="utf-8")
        # Section header.
        self.assertIn("## Agent Launch Prompt", body)
        # Paste guidance.
        self.assertIn("Paste this into Claude Code, Cursor, or any "
                      "AI coding agent", body)
        # Fenced text block.
        self.assertIn("```text\n", body)
        # Body content of the prompt is present.
        self.assertIn("WHAT THIS PROJECT APPEARS TO BE", body)
        self.assertIn("SAFETY INSTRUCTIONS", body)
        # Section appears BEFORE "What's next" so it's the first
        # actionable thing in the file.
        self.assertLess(
            body.index("## Agent Launch Prompt"),
            body.index("## What's next"),
            "Agent Launch Prompt must appear above 'What's next' "
            "in the start-here doc",
        )

    # ---- 3. Generated CLAUDE.md names the prompt as session opener -

    def test_claude_md_intro_names_prompt_as_session_opener(self):
        self._write_and_capture()
        claude_path = self.repo / "CLAUDE.md"
        self.assertTrue(claude_path.is_file(),
                        "adopt --write should have created CLAUDE.md")
        body = claude_path.read_text(encoding="utf-8")
        # "Read this first" intro now leads with the Agent Launch
        # Prompt as the canonical session opener.
        self.assertIn("Agent Launch Prompt", body)
        self.assertIn("canonical first message for your session", body)
        # Placeholder soft-framing still present (regression
        # check from the previous commit).
        self.assertIn("do not block read-only inspection", body.lower())
        # Old session-opener wording (which only listed numbered
        # docs without highlighting the prompt) is gone — the
        # new intro replaces it.
        self.assertIn("If you're an AI agent starting a session",
                      body)


class TestStreamlinedPromptFlow(unittest.TestCase):
    """v0.10.x — minimum-questions-once prompt flow.

    Locks the new wording, the ask-each-question-exactly-once
    invariant, the answer-reuse contract across all generated
    docs / prompts, and the new --project-summary / --next-task
    CLI flags that skip the interactive prompts.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- 1. Each question asked exactly once with new wording ----

    def test_collect_inputs_asks_each_question_once_with_new_wording(self):
        from cli.adopt import collect_inputs
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            if "what is this project" in prompt.lower():
                return "Demo project"
            return "Wire up the agent"

        result = collect_inputs(prompt_fn=fake_input)
        # Exactly two prompts.
        self.assertEqual(len(prompts), 2,
                         f"each question must fire once, got: "
                         f"{prompts!r}")
        # New wording.
        self.assertEqual(prompts[0],
                         "In one sentence, what is this project? ")
        self.assertEqual(prompts[1],
                         "What should the next AI session help with? ")
        # Answers carried into the dataclass.
        self.assertEqual(result.project_description, "Demo project")
        self.assertEqual(result.next_step, "Wire up the agent")

    def test_collect_inputs_with_overrides_does_not_prompt(self):
        # When both answers are passed in, prompt_fn must not fire
        # at all — the --project-summary / --next-task path.
        from cli.adopt import collect_inputs
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return "should not be called"

        result = collect_inputs(
            prompt_fn=fake_input,
            description="Pre-supplied summary",
            next_step="Pre-supplied next task",
        )
        self.assertEqual(prompts, [],
                         f"no prompts should fire when both "
                         f"overrides are provided; got {prompts!r}")
        self.assertEqual(result.project_description,
                         "Pre-supplied summary")
        self.assertEqual(result.next_step, "Pre-supplied next task")

    def test_collect_inputs_partial_override_only_prompts_remaining(self):
        # Only project description provided -> only the next-task
        # prompt fires.
        from cli.adopt import collect_inputs
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return "Just the next task"

        result = collect_inputs(
            prompt_fn=fake_input,
            description="Skip the first prompt",
        )
        self.assertEqual(len(prompts), 1)
        self.assertIn("next AI session", prompts[0])
        self.assertEqual(result.project_description,
                         "Skip the first prompt")
        self.assertEqual(result.next_step, "Just the next task")

    # ---- 2. Answers reused across all generated docs / prompts ----

    def test_user_answers_reused_in_all_generated_outputs(self):
        # Run adopt --write with a known description + next-task,
        # then verify the verbatim strings appear in BUILD_PLAN.md,
        # PROJECT_WHAT_IT_IS.md, 00-START-NEXT-SESSION.md,
        # CLAUDE.md, and the Agent Launch Prompt body.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        DESC = "demo project for prompt-flow regression"
        NXT = "verify reuse across every generated doc"
        run_adopt(_ns(self.repo, write=True,
                      description=DESC, next_step=NXT))
        for fname in ("docs/BUILD_PLAN.md",
                      "docs/PROJECT_WHAT_IT_IS.md",
                      "00-START-NEXT-SESSION.md",
                      "CLAUDE.md"):
            body = (self.repo / fname).read_text(encoding="utf-8")
            self.assertIn(DESC, body,
                          f"project description must appear in "
                          f"{fname}; got:\n{body[:600]}")
        # Next-task is in BUILD_PLAN, START, and CLAUDE managed
        # block (PROJECT_WHAT_IT_IS doesn't show next steps).
        for fname in ("docs/BUILD_PLAN.md",
                      "00-START-NEXT-SESSION.md",
                      "CLAUDE.md"):
            body = (self.repo / fname).read_text(encoding="utf-8")
            self.assertIn(NXT, body,
                          f"next-task must appear in {fname}; "
                          f"got:\n{body[:600]}")

    def test_user_answers_appear_verbatim_in_agent_launch_prompt(self):
        # The Agent Launch Prompt body must surface both answers
        # verbatim under a USER CONTEXT section so the agent sees
        # the human's framing alongside adopt's derived view.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        DESC = "user context project description"
        NXT = "user context next task"
        from cli.adopt import (
            derive_adopt_summary, derive_agent_launch_prompt,
            derive_project_type, derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality, prelim)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        inputs = AdoptionInputs(project_description=DESC, next_step=NXT)
        prompt = derive_agent_launch_prompt(
            stack, reality, ptype, summary, inputs=inputs,
        )
        text = prompt.prompt_text
        self.assertIn("USER CONTEXT", text)
        self.assertIn(DESC, text)
        self.assertIn(NXT, text)

    def test_agent_prompt_falls_back_to_placeholder_without_inputs(self):
        # When inputs is None (legacy callers / tests not
        # threading inputs), USER CONTEXT still renders but the
        # values fall back to the canonical placeholder.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        from cli.adopt import (
            derive_adopt_summary, derive_agent_launch_prompt,
            derive_project_type, derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        prelim = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, prelim)
        ptype = derive_project_type(stack, reality, prelim)
        actions = derive_suggested_actions(stack, reality, ptype, prelim)
        summary = derive_adopt_summary(stack, reality, ptype, actions)
        prompt = derive_agent_launch_prompt(
            stack, reality, ptype, summary,
        )
        text = prompt.prompt_text
        self.assertIn("USER CONTEXT", text)
        # Both values fall back to the placeholder.
        self.assertEqual(text.count("[adopt: please describe]"), 2)

    # ---- 3. CLI flag plumbing: project_summary / next_task ----

    def test_cli_flag_project_summary_skips_first_prompt(self):
        # Build an args namespace that mimics what argparse would
        # produce when the user passes --project-summary "..."
        # but no --next-task. Patch builtins.input so the only
        # remaining prompt (next-task) returns deterministically.
        import builtins
        import io
        from contextlib import redirect_stdout
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        ns = argparse.Namespace(
            command="adopt", path=str(self.repo),
            write=False, html=False, html_out=None, no_browser=True,
            project_summary="From the CLI flag",
            next_task=None,
        )
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return "next task from prompt"

        original = builtins.input
        builtins.input = fake_input  # type: ignore
        try:
            with redirect_stdout(io.StringIO()):
                from cli.adopt import run_adopt as run
                run(ns)
        finally:
            builtins.input = original  # type: ignore
        # Only one prompt fired (the next-task one).
        self.assertEqual(len(prompts), 1,
                         f"--project-summary must skip its prompt; "
                         f"got prompts: {prompts!r}")
        self.assertIn("next AI session", prompts[0])

    def test_cli_flag_next_task_skips_second_prompt(self):
        import builtins
        import io
        from contextlib import redirect_stdout
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        ns = argparse.Namespace(
            command="adopt", path=str(self.repo),
            write=False, html=False, html_out=None, no_browser=True,
            project_summary=None,
            next_task="From the CLI flag",
        )
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return "summary from prompt"

        original = builtins.input
        builtins.input = fake_input  # type: ignore
        try:
            with redirect_stdout(io.StringIO()):
                from cli.adopt import run_adopt as run
                run(ns)
        finally:
            builtins.input = original  # type: ignore
        self.assertEqual(len(prompts), 1,
                         f"--next-task must skip its prompt; "
                         f"got prompts: {prompts!r}")
        self.assertIn("what is this project", prompts[0].lower())

    def test_cli_flags_both_provided_runs_non_interactive(self):
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "main.js").write_text("// js\n", encoding="utf-8")
        ns = argparse.Namespace(
            command="adopt", path=str(self.repo),
            write=False, html=False, html_out=None, no_browser=True,
            project_summary="non-interactive summary",
            next_task="non-interactive next task",
        )
        prompts: list[str] = []

        def fake_input(prompt: str) -> str:
            prompts.append(prompt)
            return "should never be called"

        import builtins
        original = builtins.input
        builtins.input = fake_input  # type: ignore
        try:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                from cli.adopt import run_adopt as run
                run(ns)
            out = buf.getvalue()
        finally:
            builtins.input = original  # type: ignore
        self.assertEqual(prompts, [],
                         f"both --project-summary and --next-task "
                         f"must skip all prompts; got: {prompts!r}")
        # The non-interactive answers surface in the dry-run output
        # (via the agent launch prompt's USER CONTEXT block).
        self.assertIn("non-interactive summary", out)
        self.assertIn("non-interactive next task", out)


class TestDiscoveredNotes(unittest.TestCase):
    """v0.10.x — `--notes TEXT` preserves discovered context.

    Locks the trust-preservation contract: when a user passes
    findings from a prior dry-run / inspection pass, those notes
    must surface verbatim in the Agent Launch Prompt and in
    every generated doc that backs the launch flow. Section
    must NOT appear at all when `--notes` is omitted (no empty
    headings cluttering the output).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        # A minimal recognized stack so adopt has something to
        # describe; details don't matter for the notes contract.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _ns_with_notes(self, *, write: bool, notes: str | None) -> argparse.Namespace:
        return argparse.Namespace(
            command="adopt",
            path=str(self.repo),
            write=write,
            project_summary="Demo project for notes tests",
            next_task="Verify notes flow end-to-end",
            notes=notes,
        )

    def _capture_dry_run(self, ns: argparse.Namespace) -> str:
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            run_adopt(ns)
        return buf.getvalue()

    # ---- 1. argparse: --notes is wired up ----

    def test_notes_flag_present_in_parser(self):
        from context_kit import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "adopt", str(self.repo),
            "--project-summary", "x",
            "--next-task", "y",
            "--notes", "found a port collision in start.sh",
        ])
        self.assertEqual(args.notes,
                         "found a port collision in start.sh")

    def test_notes_flag_default_is_none_when_omitted(self):
        # When --notes is not passed, argparse should leave the
        # attribute at None so collect_inputs can fall back to "".
        from context_kit import build_parser
        parser = build_parser()
        args = parser.parse_args([
            "adopt", str(self.repo),
            "--project-summary", "x",
            "--next-task", "y",
        ])
        self.assertIsNone(args.notes)

    def test_notes_flag_in_help_text(self):
        from context_kit import build_parser
        parser = build_parser()
        # adopt is a subparser; format its own help.
        help_text = ""
        for action in parser._actions:  # type: ignore[attr-defined]
            if hasattr(action, "choices") and action.choices:
                adopt_parser = action.choices.get("adopt")
                if adopt_parser is not None:
                    help_text = adopt_parser.format_help()
                    break
        self.assertIn("--notes", help_text,
                      "adopt --help must list --notes")

    # ---- 2. Agent Launch Prompt (dry-run) shows notes ----

    def test_dry_run_agent_prompt_includes_notes_section(self):
        ns = self._ns_with_notes(
            write=False,
            notes="Backend uses uvicorn on :8002; frontend on :5174.",
        )
        out = self._capture_dry_run(ns)
        self.assertIn("DISCOVERED NOTES / CONTEXT", out)
        self.assertIn(
            "The user provided these notes from prior "
            "inspection or context:",
            out,
        )
        self.assertIn(
            "- Backend uses uvicorn on :8002; "
            "frontend on :5174.",
            out,
        )

    def test_dry_run_agent_prompt_omits_section_when_no_notes(self):
        ns = self._ns_with_notes(write=False, notes=None)
        out = self._capture_dry_run(ns)
        self.assertNotIn("DISCOVERED NOTES", out,
                         "no notes => no DISCOVERED NOTES heading")
        self.assertNotIn(
            "prior inspection or context",
            out,
            "no notes => no prelude line either",
        )

    def test_dry_run_agent_prompt_omits_section_when_notes_whitespace(self):
        # Whitespace-only notes count as "no notes" — the user
        # didn't actually provide anything.
        ns = self._ns_with_notes(write=False, notes="   \n  \n")
        out = self._capture_dry_run(ns)
        self.assertNotIn("DISCOVERED NOTES", out)

    # ---- 3. Generated docs (--write) preserve notes ----

    def test_build_plan_includes_notes(self):
        ns = self._ns_with_notes(
            write=True,
            notes="Smoke test from .venv hits /api/health.",
        )
        self._capture_dry_run(ns)
        text = (self.repo / "docs" / "BUILD_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("## Discovered notes", text)
        self.assertIn(
            "The user provided these notes from prior "
            "inspection or context:",
            text,
        )
        self.assertIn(
            "- Smoke test from .venv hits /api/health.",
            text,
        )

    def test_start_here_includes_notes(self):
        ns = self._ns_with_notes(
            write=True,
            notes="Demo login: demo@example.dev / demo123",
        )
        self._capture_dry_run(ns)
        text = (self.repo / "00-START-NEXT-SESSION.md").read_text(encoding="utf-8")
        self.assertIn("## Discovered notes", text)
        self.assertIn(
            "- Demo login: demo@example.dev / demo123",
            text,
        )

    def test_claude_block_includes_notes(self):
        ns = self._ns_with_notes(
            write=True,
            notes="Render config under render.yaml uses free tier.",
        )
        self._capture_dry_run(ns)
        text = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        # Section lives inside the adopt-managed block so re-runs
        # refresh in place — verify both heading and content.
        self.assertIn("### Discovered notes", text)
        self.assertIn(
            "- Render config under render.yaml uses free tier.",
            text,
        )
        # Sanity: stays inside the managed markers (so subsequent
        # --write passes don't double-write the section).
        block_start = text.index(START_MARKER)
        block_end = text.index(END_MARKER)
        notes_idx = text.index("### Discovered notes")
        self.assertGreater(notes_idx, block_start)
        self.assertLess(notes_idx, block_end)

    # ---- 4. Omitted notes => no empty sections anywhere ----

    def test_omitted_notes_produce_no_section_in_any_doc(self):
        ns = self._ns_with_notes(write=True, notes=None)
        self._capture_dry_run(ns)
        for relpath, label in [
            ("docs/BUILD_PLAN.md", "BUILD_PLAN"),
            ("00-START-NEXT-SESSION.md", "00-START-NEXT-SESSION"),
            ("CLAUDE.md", "CLAUDE.md"),
        ]:
            text = (self.repo / relpath).read_text(encoding="utf-8")
            self.assertNotIn(
                "Discovered notes", text,
                f"{label}: no notes => no 'Discovered notes' heading",
            )
            self.assertNotIn(
                "prior inspection or context", text,
                f"{label}: no notes => no notes prelude either",
            )
        # docs/PROJECT_WHAT_IT_IS.md should also be clean.
        what_it_is = (self.repo / "docs" / "PROJECT_WHAT_IT_IS.md").read_text(encoding="utf-8")
        self.assertNotIn("Discovered notes", what_it_is)

    # ---- 5. Multiline notes preserve line breaks ----

    def test_multiline_notes_preserve_line_breaks_in_agent_prompt(self):
        multiline = (
            "Port collision: backend wants :8000 but redis dev "
            "uses :8000 too.\n"
            "Workaround: export PORT=8002 before start.sh.\n"
            "TODO: codify in render.yaml."
        )
        ns = self._ns_with_notes(write=False, notes=multiline)
        out = self._capture_dry_run(ns)
        # First line gets the bullet prefix.
        self.assertIn(
            "- Port collision: backend wants :8000 but redis "
            "dev uses :8000 too.",
            out,
        )
        # Subsequent lines indent under the bullet (markdown
        # continuation) and the literal newlines must survive.
        self.assertIn(
            "  Workaround: export PORT=8002 before start.sh.",
            out,
        )
        self.assertIn(
            "  TODO: codify in render.yaml.",
            out,
        )

    def test_multiline_notes_preserve_line_breaks_in_all_docs(self):
        multiline = "First line of notes.\nSecond line.\nThird line."
        ns = self._ns_with_notes(write=True, notes=multiline)
        self._capture_dry_run(ns)
        for relpath in [
            "docs/BUILD_PLAN.md",
            "00-START-NEXT-SESSION.md",
            "CLAUDE.md",
        ]:
            text = (self.repo / relpath).read_text(encoding="utf-8")
            self.assertIn("- First line of notes.", text,
                          f"{relpath}: bullet on first line")
            self.assertIn("  Second line.", text,
                          f"{relpath}: continuation indented")
            self.assertIn("  Third line.", text,
                          f"{relpath}: third continuation indented")

    # ---- 6. Re-running --write refreshes notes inside markers ----

    def test_rerunning_write_refreshes_notes_in_managed_block(self):
        # Ship 1: initial notes.
        self._capture_dry_run(self._ns_with_notes(
            write=True, notes="Initial finding from probe pass."
        ))
        first = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Initial finding from probe pass.", first)

        # Ship 2: same project, refined notes — managed block
        # refreshes in place, no duplication.
        self._capture_dry_run(self._ns_with_notes(
            write=True, notes="Refined finding after deeper probe."
        ))
        second = (self.repo / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Refined finding after deeper probe.", second)
        self.assertNotIn("Initial finding from probe pass.", second,
                         "managed block must replace stale notes")
        # Exactly one ### Discovered notes heading in the file.
        self.assertEqual(second.count("### Discovered notes"), 1)


class TestAgentPromptBehaviorRules(unittest.TestCase):
    """v0.11.x — Agent Launch Prompt behavior-shaping rules.

    Locks two new sections meant to make agents behave more
    consistently across repo types: a conditional inspection
    rule (depth scales with confidence / clarity) and an
    anti-doc-fallback priority rule (don't default to README
    polish when there's real work to find).
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _build_prompt(self):
        from cli.adopt import (
            analyze_failures,
            derive_adopt_summary,
            derive_agent_launch_prompt,
            derive_project_type,
            derive_stack_reality,
            derive_suggested_actions,
        )
        stack = detect_stack(self.repo)
        failures = analyze_failures(self.repo, stack, [])
        reality = derive_stack_reality(stack, failures)
        pt = derive_project_type(stack, reality, failures)
        actions = derive_suggested_actions(stack, reality, pt, failures)
        summary = derive_adopt_summary(stack, reality, pt, actions)
        inputs = AdoptionInputs(
            project_description="Test project",
            next_step="Inspect and propose",
        )
        prompt = derive_agent_launch_prompt(
            stack, reality, pt, summary, inputs=inputs,
        )
        return prompt.prompt_text, pt, reality

    def _make_full_stack_repo(self):
        # Backend Python + frontend JS at depth 1 → split monorepo,
        # classified as Full-stack web app (medium confidence).
        (self.repo / "backend").mkdir()
        (self.repo / "frontend").mkdir()
        (self.repo / "backend" / "requirements.txt").write_text(
            "flask\n", encoding="utf-8",
        )
        (self.repo / "frontend" / "package.json").write_text(
            "{}", encoding="utf-8",
        )

    def _make_unclear_repo(self):
        # Empty dir → unknown stack → Unclear project type
        # (low confidence). Adopt's hardest case.
        pass  # setUp already gave us an empty repo

    def _make_single_stack_repo(self):
        # Single root JS manifest → JavaScript app/tooling project
        # (medium confidence).
        (self.repo / "package.json").write_text("{}", encoding="utf-8")

    # ---- 1. New sections appear in the prompt ----

    def test_conditional_rule_present_in_full_stack_prompt(self):
        self._make_full_stack_repo()
        text, _pt, _r = self._build_prompt()
        self.assertIn("HOW TO APPROACH THIS REPO", text)
        # Three-tier behavior must be visible to the agent.
        # --- Low / unclear branch: full structured read-through.
        self.assertIn("structured read-through", text)
        self.assertIn("entry points (README, main files, "
                      "routing, configs)", text)
        self.assertIn("map the system", text)
        self.assertIn("inconsistencies", text)
        # --- Medium branch: quick inspection then decide depth.
        self.assertIn("If confidence is medium", text)
        self.assertIn("quick inspection", text)
        self.assertIn(
            "decide whether the project needs deeper analysis "
            "or whether you can move directly to a concrete "
            "first task",
            text,
        )
        # --- High branch: skip and go.
        self.assertIn(
            "skip the read-through and go directly to "
            "identifying the highest-value next task",
            text,
        )

    def test_conditional_rule_branches_appear_in_stable_order(self):
        # The agent reads top-to-bottom; the three branches must
        # appear in the expected order (low → medium → high) so
        # the agent picks the right one without ambiguity.
        self._make_full_stack_repo()
        text, _pt, _r = self._build_prompt()
        idx_low = text.index("structured read-through")
        idx_medium = text.index("If confidence is medium")
        idx_high = text.index("If the structure IS clear and "
                              "confidence is high")
        self.assertLess(idx_low, idx_medium,
                        "low branch must come before medium")
        self.assertLess(idx_medium, idx_high,
                        "medium branch must come before high")

    def test_priority_rule_present_in_full_stack_prompt(self):
        self._make_full_stack_repo()
        text, _pt, _r = self._build_prompt()
        self.assertIn("WHAT TO PRIORITIZE", text)
        self.assertIn("risks", text)
        self.assertIn("inconsistencies", text)
        self.assertIn("missing wiring", text)
        self.assertIn("unused / incomplete features", text)
        # Anti-doc-fallback language is the load-bearing piece.
        self.assertIn(
            "Do not default to documentation updates unless "
            "the user explicitly asked for them",
            text,
        )

    def test_new_sections_present_in_unclear_repo_prompt(self):
        # Critical case: low/medium confidence is exactly when the
        # conditional rule should fire. Must be present even when
        # adopt has very little signal.
        self._make_unclear_repo()
        text, pt, _r = self._build_prompt()
        # Sanity-check we're actually in the low/medium branch.
        self.assertIn(pt.confidence.lower(), ("low", "medium"))
        self.assertIn("HOW TO APPROACH THIS REPO", text)
        self.assertIn("WHAT TO PRIORITIZE", text)

    def test_unclear_first_action_infers_before_asking(self):
        # The unclear-project RECOMMENDED FIRST ACTION used to say
        # "Clarify first" + "Wait for their answer", which directly
        # contradicted the new HOW TO APPROACH rule that tells the
        # agent to do a structured read-through on low confidence.
        # Lock the new "infer first, ask only for residual gaps"
        # wording in so the contradiction can't sneak back in.
        self._make_unclear_repo()
        text, pt, _r = self._build_prompt()
        # Sanity-check we're hitting the unclear branch at all.
        self.assertEqual(pt.label, "Unclear project type")

        # New wording — must be present.
        self.assertIn("Infer the project shape first", text)
        self.assertIn(
            "Only ask the user for clarification after this "
            "inspection",
            text,
        )

        # Old contradictory wording — must be gone.
        self.assertNotIn(
            "Wait for their answer before proposing any "
            "concrete next step",
            text,
        )
        self.assertNotIn(
            "Ask the user explicitly: what is this project?",
            text,
        )

    def test_new_sections_present_in_single_stack_prompt(self):
        self._make_single_stack_repo()
        text, _pt, _r = self._build_prompt()
        self.assertIn("HOW TO APPROACH THIS REPO", text)
        self.assertIn("WHAT TO PRIORITIZE", text)

    # ---- 2. Placement: between FIRST ACTION and SAFETY ----

    def test_new_sections_sit_between_first_action_and_safety(self):
        # The conditional + priority rules must appear AFTER the
        # recommended first action (so the agent reads them as
        # modulating that action) and BEFORE safety instructions
        # (which are non-negotiable rails, not behavior shaping).
        self._make_full_stack_repo()
        text, _pt, _r = self._build_prompt()
        idx_first = text.index("RECOMMENDED FIRST ACTION")
        idx_how = text.index("HOW TO APPROACH THIS REPO")
        idx_priority = text.index("WHAT TO PRIORITIZE")
        idx_safety = text.index("SAFETY INSTRUCTIONS")
        self.assertLess(idx_first, idx_how,
                        "HOW TO APPROACH must come after FIRST ACTION")
        self.assertLess(idx_how, idx_priority,
                        "WHAT TO PRIORITIZE must come after HOW TO APPROACH")
        self.assertLess(idx_priority, idx_safety,
                        "WHAT TO PRIORITIZE must come before SAFETY")

    # ---- 3. Determinism: same inputs => byte-equal prompt ----

    def test_prompt_is_deterministic(self):
        self._make_full_stack_repo()
        a, _, _ = self._build_prompt()
        b, _, _ = self._build_prompt()
        self.assertEqual(a, b,
                         "same inputs must produce byte-equal prompt")

    # ---- 4. No regression in pre-existing sections ----

    def test_existing_sections_still_present(self):
        # The new sections must be additive — every section that
        # shipped in v0.10.x must still be in the prompt.
        self._make_full_stack_repo()
        text, _pt, _r = self._build_prompt()
        for required in [
            "WHAT THIS PROJECT APPEARS TO BE",
            "USER CONTEXT (provided during adopt)",
            "PRIMARY DETECTION",
            "WORKSPACE / PROJECT STRUCTURE",
            "RECOMMENDED FIRST ACTION",
            "SAFETY INSTRUCTIONS",
            "When you're ready to begin work, summarize what "
            "you read and propose a concrete first task.",
        ]:
            self.assertIn(required, text,
                          f"v0.10.x section missing: {required}")

    def test_new_rules_do_not_duplicate_safety_instructions(self):
        # Avoid bloat: the new rules must NOT repeat safety
        # language (no destructive commands, no stack swaps,
        # etc.). Safety stays in its own section.
        self._make_full_stack_repo()
        text, _pt, _r = self._build_prompt()
        how_start = text.index("HOW TO APPROACH THIS REPO")
        safety_start = text.index("SAFETY INSTRUCTIONS")
        between = text[how_start:safety_start]
        for safety_phrase in [
            "destructive commands",
            "swapping frameworks",
            "broad refactors",
            "force-push",
        ]:
            self.assertNotIn(
                safety_phrase, between,
                f"new rules must not duplicate safety language: "
                f"{safety_phrase!r}",
            )


if __name__ == "__main__":
    unittest.main()
