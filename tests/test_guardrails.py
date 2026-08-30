"""Tests for the context-kit `guardrails` subcommand.

Tests are unit-scoped: they exercise the built-in checks against
temp directories, verify the plug-in loader's error-surfacing, and
confirm the runner honors ``--advisory`` and ``--only``. They do NOT
shell out to git or subprocess for a live context-kit run; the
``verify-conflicts`` check is tested against a real (but minimal)
temp repo so the ``collect_verification`` seam is exercised.
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.guardrails import (  # noqa: E402
    BUILTIN_CHECKS,
    check_tracked_generated_paths,
    check_verify_conflicts,
    load_forbidden_paths,
    load_plugin_checks,
    run_checks,
    run_guardrails,
    _parse_yaml_list,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git_init(project: Path) -> None:
    """Init a git repo in ``project`` and stage all files.

    Kept minimal — no commit, no user config. `git ls-files` needs
    files staged, so we stage everything at the end.
    """
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)


class ParseYamlListTests(unittest.TestCase):
    def test_extracts_simple_list(self):
        text = (
            "forbidden_paths:\n"
            "  - dist/**\n"
            "  - build/**\n"
        )
        self.assertEqual(
            _parse_yaml_list(text, "forbidden_paths"),
            ["dist/**", "build/**"],
        )

    def test_ignores_comments_and_blank_lines(self):
        text = (
            "# top comment\n"
            "\n"
            "forbidden_paths:\n"
            "  # inner comment\n"
            "  - dist/**\n"
        )
        self.assertEqual(_parse_yaml_list(text, "forbidden_paths"), ["dist/**"])

    def test_strips_quotes(self):
        text = (
            "forbidden_paths:\n"
            '  - "docs/_index.json"\n'
            "  - '**/*.pyc'\n"
        )
        self.assertEqual(
            _parse_yaml_list(text, "forbidden_paths"),
            ["docs/_index.json", "**/*.pyc"],
        )

    def test_stops_at_next_top_level_key(self):
        text = (
            "forbidden_paths:\n"
            "  - dist/**\n"
            "other_key:\n"
            "  - not-included\n"
        )
        self.assertEqual(_parse_yaml_list(text, "forbidden_paths"), ["dist/**"])

    def test_missing_key_returns_empty_list(self):
        self.assertEqual(_parse_yaml_list("other: 1\n", "forbidden_paths"), [])


class LoadForbiddenPathsTests(unittest.TestCase):
    def test_returns_empty_when_config_absent(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_forbidden_paths(Path(td)), [])

    def test_reads_configured_patterns(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(
                project / ".context-kit" / "guardrails.yaml",
                "forbidden_paths:\n  - dist/**\n  - build/**\n",
            )
            self.assertEqual(
                load_forbidden_paths(project),
                ["dist/**", "build/**"],
            )


class CheckTrackedGeneratedPathsTests(unittest.TestCase):
    def test_no_config_is_noop_ok(self):
        with tempfile.TemporaryDirectory() as td:
            result = check_tracked_generated_paths(Path(td))
        self.assertTrue(result.ok)
        self.assertFalse(result.blocking)
        self.assertIn("no-op", result.messages[0])

    def test_configured_but_no_matches_ok(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(project / ".context-kit" / "guardrails.yaml",
                   "forbidden_paths:\n  - dist/**\n")
            _write(project / "src" / "app.py", "print('hi')\n")
            _git_init(project)
            result = check_tracked_generated_paths(project)
        self.assertTrue(result.ok)
        self.assertFalse(result.blocking)

    def test_matches_fail_and_block(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(project / ".context-kit" / "guardrails.yaml",
                   "forbidden_paths:\n  - dist/**\n")
            _write(project / "dist" / "app.js", "// built\n")
            _write(project / "src" / "app.py", "print('hi')\n")
            _git_init(project)
            result = check_tracked_generated_paths(project)
        self.assertFalse(result.ok)
        self.assertTrue(result.blocking)
        self.assertTrue(any("dist/app.js" in m for m in result.messages))


class CheckVerifyConflictsTests(unittest.TestCase):
    """The verify subsystem is heavy; stub it here to keep the test fast
    and to make the OK/CONFLICT/DOC_ONLY paths independently observable.
    """

    def test_no_findings_is_ok(self):
        report = type("R", (), {"findings": []})()
        with patch("cli.guardrails.collect_verification", return_value=report):
            with tempfile.TemporaryDirectory() as td:
                result = check_verify_conflicts(Path(td))
        self.assertTrue(result.ok)
        self.assertFalse(result.blocking)

    def test_conflict_fails_and_blocks(self):
        finding = type("F", (), {
            "status": "CONFLICT",
            "title": "docs claim 100, code says 50",
            "details": "docs/X.md line 3",
            "recommendation": "regen inventory",
        })()
        report = type("R", (), {"findings": [finding]})()
        with patch("cli.guardrails.collect_verification", return_value=report):
            with tempfile.TemporaryDirectory() as td:
                result = check_verify_conflicts(Path(td))
        self.assertFalse(result.ok)
        self.assertTrue(result.blocking)
        self.assertTrue(any("CONFLICT" in m for m in result.messages))

    def test_doc_only_is_advisory_not_blocking(self):
        finding = type("F", (), {
            "status": "DOC_ONLY",
            "title": "unverified claim",
            "details": "",
            "recommendation": "",
        })()
        report = type("R", (), {"findings": [finding]})()
        with patch("cli.guardrails.collect_verification", return_value=report):
            with tempfile.TemporaryDirectory() as td:
                result = check_verify_conflicts(Path(td))
        self.assertTrue(result.ok)
        self.assertFalse(result.blocking)
        self.assertTrue(any("DOC_ONLY" in m for m in result.messages))


class LoadPluginChecksTests(unittest.TestCase):
    def test_no_plugin_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(load_plugin_checks(Path(td)), [])

    def test_valid_plugin_returns_checks(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(
                project / ".context-kit" / "guardrails.py",
                "from cli.guardrails import Check, CheckResult\n"
                "def _ok(project):\n"
                "    return CheckResult(name='custom', ok=True)\n"
                "CHECKS = [Check(name='custom', fn=_ok)]\n",
            )
            checks = load_plugin_checks(project)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].name, "custom")

    def test_missing_CHECKS_surfaces_plugin_load_failure(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(project / ".context-kit" / "guardrails.py",
                   "# no CHECKS attribute\n")
            checks = load_plugin_checks(project)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].name, "plugin-load")
        result = checks[0].fn(project)
        self.assertFalse(result.ok)
        self.assertTrue(result.blocking)

    def test_import_error_surfaces_plugin_load_failure(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(project / ".context-kit" / "guardrails.py",
                   "raise RuntimeError('boom')\n")
            checks = load_plugin_checks(project)
        self.assertEqual(len(checks), 1)
        result = checks[0].fn(project)
        self.assertFalse(result.ok)
        self.assertIn("boom", result.messages[0])

    def test_wrong_shape_surfaces_plugin_load_failure(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            _write(project / ".context-kit" / "guardrails.py",
                   "CHECKS = ['not a check']\n")
            checks = load_plugin_checks(project)
        self.assertEqual(len(checks), 1)
        result = checks[0].fn(project)
        self.assertFalse(result.ok)


class RunChecksTests(unittest.TestCase):
    def test_only_restricts_the_run(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            with patch("cli.guardrails.collect_verification",
                       return_value=type("R", (), {"findings": []})()):
                results = run_checks(project, only=["verify-conflicts"])
        names = [r.name for r in results]
        self.assertIn("verify-conflicts", names)
        self.assertNotIn("tracked-generated-paths", names)

    def test_advisory_downgrades_blocking(self):
        finding = type("F", (), {
            "status": "CONFLICT", "title": "X",
            "details": "", "recommendation": "",
        })()
        report = type("R", (), {"findings": [finding]})()
        with patch("cli.guardrails.collect_verification", return_value=report):
            with tempfile.TemporaryDirectory() as td:
                results = run_checks(
                    Path(td),
                    advisory=["verify-conflicts"],
                    only=["verify-conflicts"],
                )
        # The check found a real conflict, but advisory should have
        # cleared blocking. The result should still not be ok — the
        # information is not lost, just downgraded.
        verify = next(r for r in results if r.name == "verify-conflicts")
        self.assertFalse(verify.ok)
        self.assertFalse(verify.blocking)
        self.assertTrue(any("advisory" in m for m in verify.messages))

    def test_unknown_check_names_surface_warnings(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            with patch("cli.guardrails.collect_verification",
                       return_value=type("R", (), {"findings": []})()):
                results = run_checks(
                    project,
                    advisory=["typo-check"],
                    only=["verify-conflicts"],
                )
        self.assertTrue(any(r.name == "unknown:typo-check" for r in results))


class RunGuardrailsCLITests(unittest.TestCase):
    def _args(self, project, **overrides):
        base = dict(
            project=str(project),
            guardrails_action=overrides.pop("action", "run"),
            advisory=overrides.pop("advisory", None),
            only=overrides.pop("only", ["verify-conflicts"]),
            strict=overrides.pop("strict", True),
            force=overrides.pop("force", False),
        )
        base.update(overrides)
        return argparse.Namespace(**base)

    def test_run_returns_0_on_clean(self):
        with patch("cli.guardrails.collect_verification",
                   return_value=type("R", (), {"findings": []})()):
            with tempfile.TemporaryDirectory() as td:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = run_guardrails(self._args(Path(td)))
        self.assertEqual(rc, 0)

    def test_run_returns_1_on_conflict_strict(self):
        finding = type("F", (), {
            "status": "CONFLICT", "title": "X",
            "details": "", "recommendation": "",
        })()
        report = type("R", (), {"findings": [finding]})()
        with patch("cli.guardrails.collect_verification", return_value=report):
            with tempfile.TemporaryDirectory() as td:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = run_guardrails(self._args(Path(td)))
        self.assertEqual(rc, 1)

    def test_no_strict_never_fails(self):
        finding = type("F", (), {
            "status": "CONFLICT", "title": "X",
            "details": "", "recommendation": "",
        })()
        report = type("R", (), {"findings": [finding]})()
        with patch("cli.guardrails.collect_verification", return_value=report):
            with tempfile.TemporaryDirectory() as td:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = run_guardrails(self._args(Path(td), strict=False))
        self.assertEqual(rc, 0)

    def test_install_workflow_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = run_guardrails(self._args(
                    project, action="install-workflow", only=None,
                ))
            wf = project / ".github" / "workflows" / "repo-guardrails.yml"
            self.assertEqual(rc, 0)
            self.assertTrue(wf.exists())
            self.assertIn("context-kit guardrails run", wf.read_text())

    def test_install_workflow_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            wf = project / ".github" / "workflows" / "repo-guardrails.yml"
            wf.parent.mkdir(parents=True)
            wf.write_text("existing", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = run_guardrails(self._args(
                    project, action="install-workflow", only=None,
                ))
            self.assertEqual(rc, 1)
            self.assertEqual(wf.read_text(), "existing")

    def test_install_workflow_force_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            wf = project / ".github" / "workflows" / "repo-guardrails.yml"
            wf.parent.mkdir(parents=True)
            wf.write_text("existing", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = run_guardrails(self._args(
                    project, action="install-workflow", only=None, force=True,
                ))
            self.assertEqual(rc, 0)
            self.assertIn("context-kit guardrails run", wf.read_text())


class BuiltinRegistryTests(unittest.TestCase):
    def test_expected_builtins_registered(self):
        names = {c.name for c in BUILTIN_CHECKS}
        self.assertEqual(names, {"verify-conflicts", "tracked-generated-paths"})


if __name__ == "__main__":
    unittest.main()
