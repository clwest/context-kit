"""Tests for the context-kit `hotpath` subcommand.

Each test creates a temp directory with a controlled set of files, runs
hotpath against it, and asserts on the captured stdout. Hotpath is
read-only and always exits 0; the assertions cover the warning surface.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.hotpath import run_hotpath  # noqa: E402


def _hotpath_args(
    project,
    *,
    single_threshold_kb: int = 50,
    top_count: int = 10,
    top_threshold_kb: int = 200,
):
    return argparse.Namespace(
        command="hotpath",
        project=str(project),
        single_threshold_kb=single_threshold_kb,
        top_count=top_count,
        top_threshold_kb=top_threshold_kb,
    )


def _run(args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_hotpath(args)
    return rc, buf.getvalue()


def _write_file(path: Path, kb: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * (kb * 1024))


class TestHotpathSmallProject(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        _write_file(self.tmpdir / "small.py", kb=2)
        _write_file(self.tmpdir / "tiny.md", kb=1)

    def tearDown(self):
        self._tmp.cleanup()

    def test_returns_zero(self):
        rc, _ = _run(_hotpath_args(self.tmpdir))
        self.assertEqual(rc, 0)

    def test_status_is_ok_when_under_thresholds(self):
        _, out = _run(_hotpath_args(self.tmpdir))
        self.assertIn("## STATUS", out)
        self.assertIn("OK", out)
        self.assertNotIn("## WARNINGS", out)

    def test_lists_files_largest_first(self):
        _, out = _run(_hotpath_args(self.tmpdir))
        small_idx = out.find("small.py")
        tiny_idx = out.find("tiny.md")
        self.assertGreater(small_idx, 0)
        self.assertGreater(tiny_idx, 0)
        self.assertLess(small_idx, tiny_idx)


class TestHotpathSingleFileWarning(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        _write_file(self.tmpdir / "huge.py", kb=120)

    def tearDown(self):
        self._tmp.cleanup()

    def test_warns_on_oversized_single_file(self):
        _, out = _run(_hotpath_args(self.tmpdir, single_threshold_kb=50))
        self.assertIn("## WARNINGS", out)
        self.assertIn("huge.py", out)
        self.assertIn("over 50 KB single-file threshold", out)

    def test_threshold_flag_silences_warning(self):
        _, out = _run(_hotpath_args(self.tmpdir, single_threshold_kb=200))
        self.assertNotIn("## WARNINGS", out)


class TestHotpathTopSumWarning(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        # 10 files at 30 KB each = 300 KB sum (over default 200 KB),
        # but each is under the 50 KB single-file threshold.
        for i in range(10):
            _write_file(self.tmpdir / f"file_{i:02d}.py", kb=30)

    def tearDown(self):
        self._tmp.cleanup()

    def test_warns_on_cumulative_top_sum(self):
        _, out = _run(_hotpath_args(self.tmpdir))
        self.assertIn("## WARNINGS", out)
        self.assertIn("over 200 KB cumulative threshold", out)
        self.assertNotIn("single-file threshold", out)

    def test_top_count_flag_changes_what_gets_summed(self):
        # With top-count=3 the sum is 90 KB — under the 200 KB threshold.
        _, out = _run(_hotpath_args(self.tmpdir, top_count=3))
        self.assertIn("## TOP 3 LARGEST", out)
        self.assertIn("OK", out)


class TestHotpathHonorsIgnoreList(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        _write_file(self.tmpdir / "src" / "app.py", kb=5)
        _write_file(self.tmpdir / "node_modules" / "junk.js", kb=500)
        _write_file(self.tmpdir / "__pycache__" / "x.pyc", kb=300)
        _write_file(self.tmpdir / "mything.egg-info" / "PKG-INFO", kb=200)
        _write_file(self.tmpdir / ".venv" / "lib.py", kb=400)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ignored_directories_are_pruned(self):
        _, out = _run(_hotpath_args(self.tmpdir))
        self.assertIn("app.py", out)
        self.assertNotIn("node_modules", out.split("## METHOD")[0])
        self.assertNotIn("__pycache__", out.split("## METHOD")[0])
        self.assertNotIn(".egg-info", out.split("## METHOD")[0])
        self.assertNotIn(".venv", out.split("## METHOD")[0])


class TestHotpathGitTrackedPath(unittest.TestCase):
    """When in a git repo, only tracked files should be scanned."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        _write_file(self.tmpdir / "tracked.py", kb=5)
        _write_file(self.tmpdir / "untracked_huge.py", kb=120)
        # Initialize a quiet git repo and commit only the tracked file.
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        for cmd in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "add", "tracked.py"],
            ["git", "commit", "-q", "-m", "init"],
        ):
            subprocess.run(cmd, cwd=self.tmpdir, env=env, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def tearDown(self):
        self._tmp.cleanup()

    def test_untracked_huge_file_is_ignored(self):
        _, out = _run(_hotpath_args(self.tmpdir))
        self.assertIn("git ls-files", out)
        self.assertIn("tracked.py", out)
        self.assertNotIn("untracked_huge.py", out)
        # And therefore no single-file warning fires.
        self.assertNotIn("## WARNINGS", out)


class TestHotpathWalkFallback(unittest.TestCase):
    """Outside a git repo, the recursive walk picks up everything (minus ignored)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        _write_file(self.tmpdir / "loose.py", kb=5)

    def tearDown(self):
        self._tmp.cleanup()

    def test_uses_walk_when_no_git_repo(self):
        _, out = _run(_hotpath_args(self.tmpdir))
        self.assertIn("recursive walk", out)
        self.assertIn("loose.py", out)


class TestHotpathIsReadOnly(unittest.TestCase):
    """Hotpath must not mutate the project."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        _write_file(self.tmpdir / "a.py", kb=2)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_files_added_or_modified(self):
        before = {p.relative_to(self.tmpdir): p.stat().st_mtime_ns
                  for p in self.tmpdir.rglob("*") if p.is_file()}
        _run(_hotpath_args(self.tmpdir))
        after = {p.relative_to(self.tmpdir): p.stat().st_mtime_ns
                 for p in self.tmpdir.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


class TestHotpathInvalidProject(unittest.TestCase):
    def test_nonexistent_path_returns_two(self):
        rc, out = _run(_hotpath_args("/definitely/does/not/exist/here"))
        self.assertEqual(rc, 2)
        self.assertIn("not a directory", out)


if __name__ == "__main__":
    unittest.main()
