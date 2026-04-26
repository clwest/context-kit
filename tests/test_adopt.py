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
    AdoptionInputs,
    END_MARKER,
    START_MARKER,
    apply_plan,
    detect_stack,
    generate_claude_block,
    plan_files,
    run_adopt,
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


if __name__ == "__main__":
    unittest.main()
