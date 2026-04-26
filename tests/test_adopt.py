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
    MAX_FILES_PER_SUBDIR,
    AdoptionInputs,
    END_MARKER,
    START_MARKER,
    apply_plan,
    detect_stack,
    generate_build_plan,
    generate_claude_block,
    plan_files,
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


if __name__ == "__main__":
    unittest.main()
