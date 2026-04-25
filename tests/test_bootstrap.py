"""End-to-end tests for the context-kit `init` subcommand.

Each test scaffolds a real project into a temp directory and asserts on the
resulting file tree. Tests are sequential and clean up after themselves.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.bootstrap import RUNTIME_COPY, bootstrap, run_init  # noqa: E402
from cli.placeholders import derive_placeholders  # noqa: E402


def _init_args(name, target, with_scaffold=False, force=False, quiet=True):
    """Construct an argparse.Namespace matching context_kit.py's init parser."""
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target) if target is not None else None,
        with_scaffold=with_scaffold,
        force=force,
        quiet=quiet,
    )


class TestInitWritesExpectedFiles(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_core_files_present(self):
        target = self.tmpdir / "my-app"
        rc = run_init(_init_args("My App", target))
        self.assertEqual(rc, 0)

        expected = [
            "00-START-NEXT-SESSION.md",
            "CLAUDE.md",
            "docs/MY_APP_WHAT_IT_IS.md",
            "docs/MY_APP_INVENTORY.md",
            "docs/TRUST_CALIBRATION.md",
            "docs/topics/infrastructure.md",
            "docs/handoffs/SESSION_001_BOOTSTRAP.md",
            "docs/docs-pattern/README.md",
            "docs/docs-pattern/01_two_doc_anchor.md",
            "docs/docs-pattern/08_collaboration_roles.md",
            "docs/docs-pattern/templates/PLATFORM_WHAT_IT_IS.template.md",
        ]
        for rel in expected:
            self.assertTrue((target / rel).is_file(), f"missing: {rel}")

    def test_placeholder_filenames_rendered(self):
        target = self.tmpdir / "acme"
        run_init(_init_args("Acme Co", target))
        self.assertTrue((target / "docs" / "ACME_CO_WHAT_IT_IS.md").is_file())
        self.assertTrue((target / "docs" / "ACME_CO_INVENTORY.md").is_file())
        self.assertFalse((target / "docs" / "{{APP_UPPER}}_WHAT_IT_IS.md").exists())

    def test_runtime_files_copied_for_start_command(self):
        target = self.tmpdir / "runtime"
        run_init(_init_args("R", target))
        for _, dst_rel in RUNTIME_COPY:
            self.assertTrue((target / dst_rel).is_file(), f"runtime missing: {dst_rel}")

    def test_default_target_is_slug_in_cwd(self):
        old_cwd = os.getcwd()
        try:
            os.chdir(self.tmpdir)
            run_init(_init_args("Slug Test", target=None))
            self.assertTrue((self.tmpdir / "slug-test").is_dir())
        finally:
            os.chdir(old_cwd)

    def test_scaffolded_start_here_has_state_scaffold_frontmatter(self):
        """Locks in the contract `context-kit seed` relies on."""
        target = self.tmpdir / "state-check"
        run_init(_init_args("State Check", target))
        body = (target / "00-START-NEXT-SESSION.md").read_text(encoding="utf-8")
        self.assertTrue(body.startswith("---\n"))
        self.assertIn("state: scaffold", body.split("\n---\n", 1)[0])

    def test_claude_skill_copied_into_generated_project(self):
        target = self.tmpdir / "skill"
        run_init(_init_args("Skill", target))
        skill = target / ".claude" / "skills" / "context-kit" / "SKILL.md"
        self.assertTrue(skill.is_file(), "SKILL.md was not copied into the generated project")
        body = skill.read_text(encoding="utf-8")
        self.assertIn("name: context-kit", body)
        self.assertIn("context-kit orient", body)


class TestPackagedResources(unittest.TestCase):
    """Asserts that all package data needed by `init` is accessible
    via importlib.resources.

    This is the same code path the wheel install uses at runtime;
    if these paths don't exist here they won't exist after `pip
    install context-kit` either.
    """

    def test_pattern_resources_present(self):
        import importlib.resources as resources
        cli_root = resources.files("cli")
        self.assertTrue((cli_root / "_pattern" / "01_two_doc_anchor.md").is_file())
        self.assertTrue((cli_root / "_pattern" / "08_collaboration_roles.md").is_file())
        self.assertTrue((cli_root / "_pattern" / "README.md").is_file())
        self.assertTrue(
            (cli_root / "_pattern" / "templates" / "PLATFORM_WHAT_IT_IS.template.md").is_file()
        )

    def test_starter_resources_present(self):
        import importlib.resources as resources
        cli_root = resources.files("cli")
        self.assertTrue((cli_root / "_starter" / "root" / "CLAUDE.md").is_file())
        self.assertTrue((cli_root / "_starter" / "root" / "00-START-NEXT-SESSION.md").is_file())
        self.assertTrue((cli_root / "_starter" / "docs" / "TRUST_CALIBRATION.md").is_file())
        self.assertTrue(
            (cli_root / "_starter" / "docs" / "{{APP_UPPER}}_WHAT_IT_IS.md").is_file()
        )
        self.assertTrue(
            (cli_root / "_starter" / "scaffold" / "python" / "doc_claim_verification.py").is_file()
        )

    def test_skill_resources_present(self):
        import importlib.resources as resources
        skill = resources.files("cli") / "_skills" / "context-kit" / "SKILL.md"
        self.assertTrue(skill.is_file())


class TestContentSubstitution(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_app_name_appears_in_content(self):
        target = self.tmpdir / "proj"
        run_init(_init_args("Example Project", target))
        body = (target / "docs" / "EXAMPLE_PROJECT_WHAT_IT_IS.md").read_text()
        # APP_TITLE substitution (titlecase each slug part) appears in prose.
        self.assertIn("Example Project", body)
        # APP_UPPER substitution appears in filename-style references.
        self.assertIn("EXAMPLE_PROJECT_INVENTORY.md", body)

    def test_all_caps_input_is_normalized(self):
        """APP_TITLE lowercases-then-titlecases: 'XY App' -> 'Xy App'.

        Pins the documented derivation pipeline; not a bug. Users who want
        to preserve 'XY' (e.g. brand names, acronyms) hand-edit the
        generated anchor doc after scaffolding.
        """
        target = self.tmpdir / "allcaps"
        run_init(_init_args("XY App", target))
        body = (target / "docs" / "XY_APP_WHAT_IT_IS.md").read_text()
        self.assertIn("Xy App", body)
        self.assertNotIn("XY App", body)

    def test_no_placeholder_leakage(self):
        """No unreplaced {{X}} should remain in generated files.

        Exceptions:
          - docs/docs-pattern/ is teaching material that legitimately contains
            example placeholders like <APP> and {{APP_UPPER}}.
          - cli/server.py contains runtime placeholders ({{PROJECT_TITLE}},
            {{URL}}, etc.) that are substituted at request time, not at
            bootstrap time.
        """
        target = self.tmpdir / "proj"
        run_init(_init_args("Leak Test", target, with_scaffold=True))

        pattern_dir = target / "docs" / "docs-pattern"
        cli_server = target / "cli" / "server.py"
        offenders = []
        for path in list(target.rglob("*.md")) + list(target.rglob("*.py")):
            try:
                path.relative_to(pattern_dir)
                continue
            except ValueError:
                pass
            if path == cli_server:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"\{\{[A-Z_]+\}\}", text):
                offenders.append(str(path.relative_to(target)))
        self.assertFalse(offenders, f"placeholder leakage in: {offenders}")


class TestIdempotenceAndForce(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rerun_without_force_preserves_user_edits(self):
        target = self.tmpdir / "idem"
        run_init(_init_args("Idem", target))
        canary = target / "00-START-NEXT-SESSION.md"
        canary.write_bytes(canary.read_bytes() + b"\n<user-edit>\n")

        run_init(_init_args("Idem", target))
        self.assertIn(b"<user-edit>", canary.read_bytes())

    def test_rerun_with_force_overwrites_user_edits(self):
        target = self.tmpdir / "forced"
        run_init(_init_args("Forced", target))
        canary = target / "00-START-NEXT-SESSION.md"
        canary.write_bytes(b"<user-edit-only>")

        run_init(_init_args("Forced", target, force=True))
        body = canary.read_bytes()
        self.assertNotIn(b"<user-edit-only>", body)
        self.assertIn(b"Forced", body)


class TestScaffoldOptIn(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scaffold_absent_by_default(self):
        target = self.tmpdir / "without"
        run_init(_init_args("A", target, with_scaffold=False))
        self.assertFalse((target / "scaffold").exists())

    def test_scaffold_present_when_requested(self):
        target = self.tmpdir / "with"
        run_init(_init_args("A", target, with_scaffold=True))
        self.assertTrue((target / "scaffold" / "python" / "doc_claim_verification.py").is_file())
        self.assertTrue((target / "scaffold" / "python" / "build_docs_index.py").is_file())


class TestInvalidInput(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_invalid_name_returns_exit_code_2(self):
        rc = run_init(_init_args("!!!", self.tmpdir / "invalid"))
        self.assertEqual(rc, 2)
        self.assertFalse((self.tmpdir / "invalid" / "CLAUDE.md").exists())


class TestBootstrapFunctionDirectly(unittest.TestCase):
    """Exercise the lower-level bootstrap() without argparse wiring."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_list_of_real_files(self):
        target = self.tmpdir / "direct"
        placeholders = derive_placeholders("Direct")
        written = bootstrap(target, placeholders)
        self.assertGreater(len(written), 15)
        for p in written:
            self.assertTrue(Path(p).is_file(), f"not a file: {p}")


if __name__ == "__main__":
    unittest.main()
