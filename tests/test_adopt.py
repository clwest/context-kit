"""Tests for ``context-kit adopt`` (v0).

Scope matches the v0 contract: detect three buckets (JavaScript /
Python / unknown), generate four files, and offer dry-run vs --write.
We're validating usefulness, not completeness — the test count is
intentionally small and focused.
"""

from __future__ import annotations

import argparse
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

    def test_mixed_repo_reports_javascript_and_notes_python(self):
        # v0 doesn't handle this properly; the test locks the
        # documented v0 behavior so the eventual upgrade is a real
        # signal, not a silent change.
        (self.repo / "package.json").write_text("{}", encoding="utf-8")
        (self.repo / "requirements.txt").write_text("flask\n", encoding="utf-8")
        result = detect_stack(self.repo)
        self.assertEqual(result.language, "javascript")
        self.assertTrue(
            any("multi-stack" in n.lower() for n in result.notes),
            f"expected multi-stack note; got {result.notes!r}",
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
        self.assertIn("Unknown but present", bp)
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
        self.assertIn("Unknown but present", block)
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
        self.assertNotIn("Unknown but present", bp)
        block = generate_claude_block(
            stack,
            AdoptionInputs(project_description="x", next_step="y"),
            "Test",
        )
        self.assertNotIn("Unknown but present", block)


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
    - The "Unknown but present" section is rendered as the visual focus
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
        # the "Unknown but present" section. The visual focus is dynamic;
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
            self.assertNotIn("Unknown but present", body)
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

    def test_html_includes_detected_issues_section(self):
        explicit = self.repo / "report.html"
        run_adopt(argparse.Namespace(
            command="adopt", path=str(self.repo), write=False,
            html=False, html_out=str(explicit), no_browser=True,
            description="x", next_step="y",
        ))
        body = explicit.read_text(encoding="utf-8")
        self.assertIn("Detected issues", body)
        self.assertIn("ROOT_SIGNAL_OVERRIDE", body)
        # Severity badge class fires for the high-severity case.
        self.assertIn("sev-high", body)
        # Surface-area annotation visible in the summary line.
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
        self.assertIn("Detected issues", out)
        self.assertIn("ROOT_SIGNAL_OVERRIDE", out)
        # High-severity surfaces with its severity tag.
        self.assertIn("high", out)

    def test_html_omits_detected_issues_when_no_failures(self):
        # A clean classified project: no failures should produce no
        # "Detected issues" card. Visual hygiene.
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
            # Either no failures section at all, OR a section that
            # doesn't claim "Detected issues" as a header.
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


if __name__ == "__main__":
    unittest.main()
