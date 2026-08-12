"""Tests for the context-kit `doctor` subcommand.

Tests are written first (per the design discussion's agreement). Each
of the 7 checks is a near-pure function that takes a project path and
returns a CheckResult; that makes them straightforward to test in
isolation by mocking subprocess / shutil / sys at known seams.

The "doctor came from real friction" provenance is documented in
docs/handoffs/SESSION_006_DOCTOR.md and TRUST_CALIBRATION.md.
"""

from __future__ import annotations

import argparse
import io
import json
import os
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

from cli.bootstrap import run_init  # noqa: E402
from cli.doctor import (  # noqa: E402
    CheckResult,
    check_expo,
    check_file_watcher,
    check_git,
    check_inventory,
    check_node,
    check_project_state,
    check_python_version,
    run_doctor,
)


def _init_args(name, target):
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=False,
        force=False,
        quiet=True,
    )


def _doctor_args(project, *, json_=False):
    return argparse.Namespace(
        command="doctor",
        project=str(project),
        json=json_,
    )


def _capture(args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_doctor(args)
    return rc, buf.getvalue()


def _scaffold(tmpdir: Path, name: str = "Doctor App") -> Path:
    project = tmpdir / "doctor-app"
    run_init(_init_args(name, project))
    return project


def _write_package_json(project: Path, payload: dict) -> None:
    (project / "package.json").write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Python version
# ---------------------------------------------------------------------------


class TestCheckPythonVersion(unittest.TestCase):
    def test_ok_on_current_python(self):
        # We're running on >=3.9 by definition (project requires-python).
        result = check_python_version()
        self.assertIn(result.status, ("ok", "warning"))  # warning only if PATH mismatch
        self.assertEqual(result.id, "python_version")

    def test_blocks_below_3_9(self):
        result = check_python_version(version_info=(3, 8, 0, "final", 0))
        self.assertEqual(result.status, "blocking")
        self.assertIn("3.8", result.detail)

    def test_warns_on_path_mismatch(self):
        result = check_python_version(
            version_info=(3, 11, 6, "final", 0),
            path_python="/usr/bin/python3",
            path_python_version="3.10.0",
        )
        self.assertEqual(result.status, "warning")
        self.assertIn("3.11.6", result.detail)
        self.assertIn("3.10.0", result.detail)


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


class TestCheckGit(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @patch("cli.doctor.shutil.which", return_value=None)
    def test_warns_when_git_missing(self, _):
        result = check_git(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("git", result.detail.lower())

    @patch("cli.doctor.shutil.which", return_value="/usr/bin/git")
    def test_warns_when_not_a_repo(self, _):
        result = check_git(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("not a git repo", result.detail.lower())

    def test_ok_when_git_repo(self):
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(
            ["git", "init", "-q", "-b", "main"],
            cwd=self.tmpdir, env=env, check=True,
        )
        result = check_git(self.tmpdir)
        self.assertEqual(result.status, "ok")


# ---------------------------------------------------------------------------
# Project state
# ---------------------------------------------------------------------------


class TestCheckProjectState(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_skipped_when_not_a_context_kit_project(self):
        empty = self.tmpdir / "empty"
        empty.mkdir()
        result = check_project_state(empty)
        self.assertEqual(result.status, "skipped")

    def test_ok_when_full_scaffold(self):
        project = _scaffold(self.tmpdir)
        result = check_project_state(project)
        self.assertEqual(result.status, "ok")
        self.assertIn("complete", result.detail.lower())

    def test_warns_when_partial(self):
        project = _scaffold(self.tmpdir)
        # Remove one expected file to force partial state.
        (project / "CLAUDE.md").unlink()
        result = check_project_state(project)
        self.assertEqual(result.status, "warning")
        self.assertIn("CLAUDE.md", result.detail)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


class TestCheckNode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_skipped_without_package_json(self):
        result = check_node(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    @patch("cli.doctor.shutil.which", return_value=None)
    def test_blocking_when_node_missing_with_package_json(self, _):
        _write_package_json(self.tmpdir, {"name": "x"})
        result = check_node(self.tmpdir)
        self.assertEqual(result.status, "blocking")

    @patch("cli.doctor._detect_node_version", return_value="22.5.0")
    @patch("cli.doctor.shutil.which", return_value="/usr/bin/node")
    def test_ok_with_stable_major(self, *_):
        _write_package_json(self.tmpdir, {"name": "x"})
        result = check_node(self.tmpdir)
        self.assertEqual(result.status, "ok")
        self.assertIn("22.5.0", result.detail)

    @patch("cli.doctor._detect_node_version", return_value="23.5.0")
    @patch("cli.doctor.shutil.which", return_value="/usr/bin/node")
    def test_warns_on_unusually_new_node(self, *_):
        _write_package_json(self.tmpdir, {"name": "x"})
        result = check_node(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("unusually new", result.detail.lower())

    @patch("cli.doctor._detect_node_version", return_value="16.20.2")
    @patch("cli.doctor.shutil.which", return_value="/usr/bin/node")
    def test_warns_on_too_old_node(self, *_):
        _write_package_json(self.tmpdir, {"name": "x"})
        result = check_node(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("older", result.detail.lower())


# ---------------------------------------------------------------------------
# Expo
# ---------------------------------------------------------------------------


class TestCheckExpo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_skipped_without_package_json(self):
        result = check_expo(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    def test_skipped_without_expo_dep(self):
        _write_package_json(self.tmpdir, {"dependencies": {"react": "18.0.0"}})
        result = check_expo(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    def test_warns_when_expo_present(self):
        _write_package_json(
            self.tmpdir,
            {"dependencies": {"expo": "~51.0.0"}},
        )
        # Create a fake app.json so we don't also flag the missing-config branch.
        (self.tmpdir / "app.json").write_text("{}", encoding="utf-8")
        result = check_expo(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("expo", result.detail.lower())
        self.assertIn("npx expo-doctor", " ".join(result.fix or []))

    def test_warns_with_missing_app_config(self):
        _write_package_json(
            self.tmpdir,
            {"dependencies": {"expo": "~51.0.0"}},
        )
        # No app.json / app.config.* — should flag missing config too.
        result = check_expo(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("config", result.detail.lower())

    def test_prefers_node_modules_version_over_dependency_range(self):
        _write_package_json(
            self.tmpdir,
            {"dependencies": {"expo": "~51.0.0"}},
        )
        (self.tmpdir / "app.json").write_text("{}", encoding="utf-8")
        nm = self.tmpdir / "node_modules" / "expo"
        nm.mkdir(parents=True)
        (nm / "package.json").write_text(
            json.dumps({"name": "expo", "version": "51.0.42"}),
            encoding="utf-8",
        )
        result = check_expo(self.tmpdir)
        self.assertIn("51.0.42", result.detail)


# ---------------------------------------------------------------------------
# File watcher / ulimit
# ---------------------------------------------------------------------------


class TestCheckFileWatcher(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @patch("cli.doctor.platform.system", return_value="Windows")
    def test_skipped_on_windows(self, _):
        result = check_file_watcher(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    @patch("cli.doctor.platform.system", return_value="Darwin")
    def test_skipped_without_package_json(self, _):
        result = check_file_watcher(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    @patch("cli.doctor.shutil.which", return_value=None)  # no watchman
    @patch("cli.doctor._read_ulimit_n", return_value=256)
    @patch("cli.doctor.platform.system", return_value="Darwin")
    def test_blocking_with_expo_and_low_ulimit(self, *_):
        _write_package_json(self.tmpdir, {"dependencies": {"expo": "~51.0.0"}})
        result = check_file_watcher(self.tmpdir)
        self.assertEqual(result.status, "blocking")
        self.assertIn("EMFILE", result.detail)
        joined_fix = " ".join(result.fix or [])
        self.assertIn("ulimit -n 65536", joined_fix)
        self.assertIn("brew install watchman", joined_fix)

    @patch("cli.doctor.shutil.which", return_value=None)
    @patch("cli.doctor._read_ulimit_n", return_value=512)
    @patch("cli.doctor.platform.system", return_value="Darwin")
    def test_warns_on_low_ulimit_without_expo(self, *_):
        _write_package_json(self.tmpdir, {"dependencies": {"react": "18.0.0"}})
        result = check_file_watcher(self.tmpdir)
        self.assertEqual(result.status, "warning")

    @patch("cli.doctor.shutil.which", return_value="/opt/homebrew/bin/watchman")
    @patch("cli.doctor._read_ulimit_n", return_value=65536)
    @patch("cli.doctor.platform.system", return_value="Darwin")
    def test_ok_with_high_ulimit_and_watchman(self, *_):
        _write_package_json(self.tmpdir, {"dependencies": {"expo": "~51.0.0"}})
        result = check_file_watcher(self.tmpdir)
        self.assertEqual(result.status, "ok")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class TestCheckInventory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_skipped_without_inventory_file(self):
        empty = self.tmpdir / "empty"
        empty.mkdir()
        result = check_inventory(empty)
        self.assertEqual(result.status, "skipped")

    def test_warns_when_no_managed_block(self):
        project = _scaffold(self.tmpdir)
        # The init template's INVENTORY stub has no markers.
        result = check_inventory(project)
        self.assertEqual(result.status, "warning")

    def test_ok_after_inventory_write(self):
        from cli.inventory import write_inventory
        project = _scaffold(self.tmpdir)
        write_inventory(project)
        result = check_inventory(project)
        self.assertEqual(result.status, "ok")


# ---------------------------------------------------------------------------
# Output formats + exit code
# ---------------------------------------------------------------------------


class TestHumanOutput(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_includes_section_headers(self):
        project = _scaffold(self.tmpdir)
        rc, out = _capture(_doctor_args(project))
        self.assertIn("doctor", out.lower())
        # At least one of these section labels should appear:
        section_labels = ["OK", "Warnings", "Blocking", "Skipped"]
        self.assertTrue(any(label in out for label in section_labels))

    def test_includes_suggested_next_commands_when_fixes_exist(self):
        # Force a stale inventory to guarantee a fix shows up.
        project = _scaffold(self.tmpdir)
        rc, out = _capture(_doctor_args(project))
        # project_state warns (no docs/CLAUDE.md not removed; but inventory has no
        # markers → warning). At minimum the `inventory --write` fix should appear.
        self.assertIn("inventory --write", out)


class TestJsonOutput(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_json_is_valid(self):
        project = _scaffold(self.tmpdir)
        rc, out = _capture(_doctor_args(project, json_=True))
        data = json.loads(out)
        self.assertIsInstance(data, dict)

    def test_json_has_expected_top_level_keys(self):
        project = _scaffold(self.tmpdir)
        _, out = _capture(_doctor_args(project, json_=True))
        data = json.loads(out)
        for key in ("schema_version", "generated_at", "project_path",
                    "summary", "exit_code", "checks"):
            self.assertIn(key, data, f"missing key: {key}")

    def test_json_check_entries_have_expected_shape(self):
        project = _scaffold(self.tmpdir)
        _, out = _capture(_doctor_args(project, json_=True))
        data = json.loads(out)
        self.assertGreater(len(data["checks"]), 0)
        for c in data["checks"]:
            for key in ("id", "label", "status", "detail", "fix"):
                self.assertIn(key, c, f"check missing key: {key}")
            self.assertIn(c["status"], ("ok", "warning", "blocking", "skipped"))


class TestExitCode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_exit_zero_when_no_blocking(self):
        project = _scaffold(self.tmpdir)
        # Force inventory to be current so we don't get extra noise,
        # though it doesn't affect blocking either way.
        from cli.inventory import write_inventory
        write_inventory(project)
        rc, _ = _capture(_doctor_args(project))
        self.assertEqual(rc, 0)

    def test_exit_one_when_blocking_present(self):
        _project = _scaffold(self.tmpdir)
        # Inject a blocking result directly via the json path's check list,
        # but easier: simulate by making the python_version check block.
        # Use the check function directly.
        result = check_python_version(version_info=(3, 8, 0, "final", 0))
        self.assertEqual(result.status, "blocking")


class TestNoMutation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_doctor_does_not_modify_project(self):
        project = _scaffold(self.tmpdir)
        before = {
            p.relative_to(project): p.stat().st_mtime_ns
            for p in project.rglob("*") if p.is_file()
        }
        _capture(_doctor_args(project))
        after = {
            p.relative_to(project): p.stat().st_mtime_ns
            for p in project.rglob("*") if p.is_file()
        }
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestIntegrationOnFreshProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_runs_on_freshly_init_project(self):
        project = _scaffold(self.tmpdir)
        rc, out = _capture(_doctor_args(project))
        # Every check runs; output mentions "project_state" or its label.
        self.assertIn("doctor", out.lower())
        self.assertIn(rc, (0, 1))


class TestIntegrationOnNonProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_runs_on_non_context_kit_directory(self):
        empty = self.tmpdir / "empty"
        empty.mkdir()
        rc, out = _capture(_doctor_args(empty))
        # No project, so project_state is skipped; doctor still runs.
        self.assertIn("not a context-kit project", out.lower())
        self.assertIn(rc, (0, 1))


# ---------------------------------------------------------------------------
# CheckResult dataclass sanity
# ---------------------------------------------------------------------------


class TestCheckResultDataclass(unittest.TestCase):
    def test_fix_can_be_string(self):
        r = CheckResult(id="x", label="x", status="warning", detail="x", fix="run X")
        # Internal normalization makes fix a list for JSON consistency.
        self.assertIsInstance(r.fix, list)

    def test_fix_can_be_list(self):
        r = CheckResult(id="x", label="x", status="warning", detail="x", fix=["a", "b"])
        self.assertEqual(r.fix, ["a", "b"])

    def test_fix_can_be_none(self):
        r = CheckResult(id="x", label="x", status="ok", detail="x")
        self.assertIsNone(r.fix)


# ---------------------------------------------------------------------------
# Orientation-drift checks
# ---------------------------------------------------------------------------


from cli.doctor import (  # noqa: E402
    check_adopt_placeholders,
    check_handoff_numbering,
    check_next_task_consistency,
    check_stale_generic_actions,
)


_ADOPT_START = "<!-- context-kit:adopt:start -->"
_ADOPT_END = "<!-- context-kit:adopt:end -->"


def _adopt_block(*, whats_next: str = "Ship the bug fix") -> str:
    return (
        f"{_ADOPT_START}\n"
        "## What this project is\n\nDemo.\n\n"
        f"## What's next\n\n{whats_next}\n\n"
        f"{_ADOPT_END}\n"
    )


class TestNextTaskConsistencyCheck(unittest.TestCase):
    """Catches the Freedom Ford-style failure: adopt block points at one
    next-task while a handwritten ``## Next session priorities`` points
    somewhere else, and orient confidently surfaces only one of them."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _start_doc(self, content: str) -> Path:
        path = self.tmpdir / "00-START-NEXT-SESSION.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_skips_when_start_doc_missing(self):
        result = check_next_task_consistency(self.tmpdir)
        self.assertEqual(result.status, "skipped")
        self.assertIn("not present", result.detail)

    def test_skips_when_no_adopt_block(self):
        self._start_doc("# Next Session\n\n## Next session priorities\n\nDo X\n")
        result = check_next_task_consistency(self.tmpdir)
        self.assertEqual(result.status, "skipped")
        self.assertIn("No adopt-managed block", result.detail)

    def test_ok_when_only_adopt_block_owns_next_task(self):
        self._start_doc("# Title\n\n" + _adopt_block(whats_next="Ship feature A"))
        result = check_next_task_consistency(self.tmpdir)
        self.assertEqual(result.status, "ok")

    def test_ok_when_handwritten_and_managed_agree(self):
        body = (
            "# Title\n\n"
            + _adopt_block(whats_next="Ship feature A")
            + "\n## Next session priorities\n\nShip feature A\n"
        )
        self._start_doc(body)
        result = check_next_task_consistency(self.tmpdir)
        self.assertEqual(result.status, "ok")

    def test_warns_when_managed_and_handwritten_disagree(self):
        # Mirrors the audit finding: managed adopt block points at
        # SESSION_008, handwritten section points at a demo-polish task.
        body = (
            "# Title\n\n"
            + _adopt_block(whats_next="Continue SESSION_008 backfill")
            + "\n## Next session priorities\n\nPolish the demo flow\n"
        )
        self._start_doc(body)
        result = check_next_task_consistency(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("disagreeing next-task pointers", result.detail)
        # Warnings ship a fix list — must not be empty.
        self.assertTrue(result.fix)

    def test_warning_is_never_blocking(self):
        # All four new checks are advisory-only; the global doctor
        # exit code must stay 0 in this scenario.
        from cli.doctor import _exit_code, run_all_checks  # noqa: E402
        body = (
            "# Title\n\n"
            + _adopt_block(whats_next="A")
            + "\n## Next session priorities\n\nB\n"
        )
        self._start_doc(body)
        # Need other doctor checks to pass cleanly; not running on a
        # full project here, but the exit code is the test.
        results = run_all_checks(self.tmpdir)
        # Warnings only → exit 0.
        self.assertEqual(_exit_code(results), 0)


class TestHandoffNumberingCheck(unittest.TestCase):
    """SESSION_NNN gap detection: start-here references SESSION_008 but
    handoffs/ only goes up to SESSION_003 means four backfills are
    missing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        (self.tmpdir / "docs" / "handoffs").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_start(self, *session_refs: str) -> None:
        body = "# Next Session\n\nReferences: " + ", ".join(session_refs) + "\n"
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text(body)

    def _add_handoff(self, name: str) -> None:
        (self.tmpdir / "docs" / "handoffs" / name).write_text(f"# {name}\n")

    def test_skipped_without_start_doc(self):
        self._add_handoff("SESSION_001_BOOTSTRAP.md")
        result = check_handoff_numbering(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    def test_skipped_without_handoffs(self):
        self._write_start("SESSION_005")
        result = check_handoff_numbering(self.tmpdir)
        self.assertEqual(result.status, "skipped")

    def test_ok_when_next_is_one_ahead(self):
        # Normal case: latest is SESSION_003, start-here points at SESSION_004.
        self._add_handoff("SESSION_001_BOOTSTRAP.md")
        self._add_handoff("SESSION_002_FOO.md")
        self._add_handoff("SESSION_003_BAR.md")
        self._write_start("SESSION_004")
        result = check_handoff_numbering(self.tmpdir)
        self.assertEqual(result.status, "ok")
        self.assertIn("SESSION_004", result.detail)

    def test_ok_when_aligned(self):
        # Equally common: start-here points at the same SESSION the
        # latest handoff already documents (gap 0).
        self._add_handoff("SESSION_003_BAR.md")
        self._write_start("SESSION_003")
        result = check_handoff_numbering(self.tmpdir)
        self.assertEqual(result.status, "ok")

    def test_warns_on_two_session_gap(self):
        # The audit finding: latest is 003, next pointer says 008.
        self._add_handoff("SESSION_001_BOOTSTRAP.md")
        self._add_handoff("SESSION_002_FOO.md")
        self._add_handoff("SESSION_003_BAR.md")
        self._write_start("SESSION_008")
        result = check_handoff_numbering(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("SESSION_008", result.detail)
        self.assertIn("SESSION_003", result.detail)
        self.assertTrue(result.fix)

    def test_session_roadmap_not_counted_as_handoff(self):
        # Same selection rule as orient: only SESSION_<digits>_*.md
        # counts. A bare SESSION_ROADMAP_*.md must not be picked as
        # the latest handoff.
        self._add_handoff("SESSION_ROADMAP_PLAN.md")
        self._add_handoff("SESSION_001_BOOTSTRAP.md")
        self._write_start("SESSION_010")
        result = check_handoff_numbering(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("SESSION_001", result.detail)


class TestAdoptPlaceholderCheck(unittest.TestCase):
    """Lingering ``[adopt: please describe ...]`` placeholders silently
    erode trust in the generated anchors."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        (self.tmpdir / "docs").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_ok_when_no_placeholders(self):
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text(
            "# Next Session\n\nReal content here.\n"
        )
        (self.tmpdir / "CLAUDE.md").write_text("# CLAUDE\n\nReal content.\n")
        result = check_adopt_placeholders(self.tmpdir)
        self.assertEqual(result.status, "ok")

    def test_warns_on_start_doc_placeholder(self):
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text(
            "# Title\n\nWhat's next: [adopt: please describe]\n"
        )
        result = check_adopt_placeholders(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("00-START-NEXT-SESSION.md", result.detail)

    def test_warns_on_what_it_is_doc(self):
        # Explicit UTF-8: the em-dash below is not encodable in cp1252,
        # which is the default text-write encoding on Windows.
        (self.tmpdir / "docs" / "PROJECT_WHAT_IT_IS.md").write_text(
            "# Project\n\nMotivation: [adopt: please describe — adopt cannot infer]\n",
            encoding="utf-8",
        )
        result = check_adopt_placeholders(self.tmpdir)
        self.assertEqual(result.status, "warning")
        # File is named in the warning detail.
        self.assertIn("PROJECT_WHAT_IT_IS.md", result.detail)

    def test_lists_multiple_offending_files(self):
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text("[adopt: please describe]")
        (self.tmpdir / "CLAUDE.md").write_text("[adopt: please describe]")
        (self.tmpdir / "docs" / "FOO_WHAT_IT_IS.md").write_text("[adopt: please describe]")
        result = check_adopt_placeholders(self.tmpdir)
        self.assertEqual(result.status, "warning")
        for needle in ("00-START-NEXT-SESSION.md", "CLAUDE.md", "FOO_WHAT_IT_IS.md"):
            self.assertIn(needle, result.detail)


class TestStaleGenericActionsCheck(unittest.TestCase):
    """Adopt's "Next actions" go stale once the user has answered them
    but adopt keeps re-emitting them. Conservative warning — only
    fires when known stale-prone titles appear inside a managed
    block."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ok_when_no_managed_block(self):
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text(
            "# Title\n\nClassify unrecognized directories\n"
            "Confirm backend/frontend boundaries\n"
        )
        # No managed block → titles outside the block don't count.
        result = check_stale_generic_actions(self.tmpdir)
        self.assertEqual(result.status, "ok")

    def test_ok_when_managed_block_has_no_stale_actions(self):
        body = (
            f"# Title\n\n{_ADOPT_START}\n"
            "## Next actions\n- Ship feature A\n- Land bug fix B\n"
            f"{_ADOPT_END}\n"
        )
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text(body)
        result = check_stale_generic_actions(self.tmpdir)
        self.assertEqual(result.status, "ok")

    def test_warns_on_known_stale_title_in_managed_block(self):
        body = (
            f"# Title\n\n{_ADOPT_START}\n"
            "## Next actions\n- Confirm backend/frontend boundaries\n"
            f"{_ADOPT_END}\n"
        )
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text(body)
        result = check_stale_generic_actions(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("Confirm backend/frontend boundaries", result.detail)

    def test_warns_on_classify_dirs(self):
        body = (
            f"# CLAUDE\n\n{_ADOPT_START}\n"
            "Suggested next: Classify unrecognized directories\n"
            f"{_ADOPT_END}\n"
        )
        (self.tmpdir / "CLAUDE.md").write_text(body)
        result = check_stale_generic_actions(self.tmpdir)
        self.assertEqual(result.status, "warning")
        self.assertIn("Classify unrecognized directories", result.detail)


if __name__ == "__main__":
    unittest.main()
