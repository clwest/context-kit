"""Tests for the context-kit `behavior` subcommand."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.behavior import run_behavior  # noqa: E402


def _args(project: Path, *, json_out: bool = False, scope: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(command="behavior", path=str(project), json=json_out, scope=scope)


def _run(project: Path, *, json_out: bool = False, scope: str | None = None) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_behavior(_args(project, json_out=json_out, scope=scope))
    return rc, buf.getvalue()


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


class _GitRepo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()
        subprocess.run(["git", "init"], cwd=self.project, check=True, capture_output=True, text=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _add_all(self) -> None:
        subprocess.run(["git", "add", "-A"], cwd=self.project, check=True, capture_output=True, text=True)


class TestBehaviorJsonShape(_GitRepo):
    def test_json_shape(self):
        _write(self.project / "core" / "celery.py", "@shared_task\ndef work(): pass\n")
        _write(self.project / "core" / "agent_router.py", "AGENT_MAP = {}\n")
        _write(self.project / "frontend" / "app.js", "console.log(1)\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], None)
        self.assertEqual(data["disclaimer"], "This is a heuristic risk map, not a correctness audit.")
        self.assertEqual(
            data["scoring"],
            "risk_score is the number of distinct risk categories detected for a file",
        )
        self.assertIn("summary", data)
        self.assertIn("risk_categories", data)
        self.assertIn("files", data)
        self.assertIn("top_files", data)
        self.assertIn("recommendations", data)
        self.assertIn("total_files_scanned", data["summary"])
        self.assertIn("files_with_signals", data["summary"])
        self.assertIsInstance(data["files"], list)
        self.assertGreaterEqual(len(data["files"]), 1)
        first = data["files"][0]
        self.assertIn("path", first)
        self.assertIn("categories", first)
        self.assertIn("risk_score", first)
        self.assertIn("entrypoint", first)
        self.assertEqual(first["risk_score"], len(first["categories"]))
        self.assertIn("entrypoints", data)
        self.assertGreaterEqual(data["entrypoints"], 1)


class TestBehaviorSignals(_GitRepo):
    def test_detects_celery_task_behavior_signals(self):
        _write(
            self.project / "core" / "celery.py",
            "@shared_task\n"
            "def work():\n"
            "    app.conf.beat_schedule = {}\n"
            "    PeriodicTask.objects.create(name='x')\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertGreaterEqual(data["risk_categories"].get("task_or_scheduler", 0), 1)
        top = data["top_files"][0]
        self.assertEqual(top["path"], "core/celery.py")
        self.assertIn("task_or_scheduler", top["categories"])
        self.assertEqual(top["risk_score"], len(top["categories"]))

    def test_repeated_matches_do_not_inflate_score(self):
        _write(
            self.project / "core" / "repeat.py",
            "import subprocess\n"
            "subprocess.run(['echo', '1'])\n"
            "subprocess.run(['echo', '2'])\n"
            "subprocess.run(['echo', '3'])\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        top = next(item for item in data["top_files"] if item["path"] == "core/repeat.py")
        self.assertEqual(top["risk_score"], 1)
        self.assertEqual(top["categories"], ["subprocess_or_shell"])
        self.assertGreaterEqual(data["risk_categories"].get("subprocess_or_shell", 0), 1)

    def test_detects_registry_and_dispatch_signals(self):
        _write(
            self.project / "core" / "agents" / "router.py",
            "AGENT_MAP = {'x': 'y'}\n"
            "def dispatch(kind):\n"
            "    return getattr(kind, 'run', None)\n"
            "import importlib\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertGreaterEqual(data["risk_categories"].get("registry_or_dispatch", 0), 1)
        self.assertGreaterEqual(data["risk_categories"].get("dynamic_import_or_getattr", 0), 1)

    def test_detects_filesystem_and_subprocess_signals(self):
        _write(
            self.project / "core" / "io.py",
            "from pathlib import Path\n"
            "import subprocess\n"
            "Path('x').write_text('hi')\n"
            "subprocess.run(['echo', 'hi'])\n"
            "except Exception:\n"
            "    pass\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertGreaterEqual(data["risk_categories"].get("filesystem_write", 0), 1)
        self.assertGreaterEqual(data["risk_categories"].get("subprocess_or_shell", 0), 1)
        self.assertGreaterEqual(data["risk_categories"].get("broad_exception_swallow", 0), 1)

    def test_detects_module_level_state_mutation(self):
        _write(
            self.project / "core" / "cache.py",
            "SOME_CACHE = {}\n"
            "GLOBAL_LIST = []\n"
            "REGISTRY = dict()\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertGreaterEqual(data["risk_categories"].get("state_mutation", 0), 1)
        top = next(item for item in data["top_files"] if item["path"] == "core/cache.py")
        self.assertIn("state_mutation", top["categories"])

    def test_detects_global_statement_state_mutation(self):
        _write(
            self.project / "core" / "stateful.py",
            "x = 1\n"
            "def mutate():\n"
            "    global x\n"
            "    x = 2\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertGreaterEqual(data["risk_categories"].get("state_mutation", 0), 1)
        top = next(item for item in data["top_files"] if item["path"] == "core/stateful.py")
        self.assertIn("state_mutation", top["categories"])

    def test_detects_manage_py_entrypoint(self):
        _write(self.project / "manage.py", "def main(): pass\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        top = next(item for item in data["files"] if item["path"] == "manage.py")
        self.assertTrue(top["entrypoint"])
        self.assertIn("entrypoint", top["categories"])
        self.assertGreaterEqual(data["entrypoints"], 1)

    def test_detects_management_command_entrypoint(self):
        _write(
            self.project / "core" / "management" / "commands" / "refresh_cache.py",
            "from django.core.management.base import BaseCommand\n"
            "class Command(BaseCommand):\n"
            "    def handle(self, *args, **kwargs):\n"
            "        return None\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        top = next(item for item in data["files"] if item["path"].endswith("refresh_cache.py"))
        self.assertTrue(top["entrypoint"])
        self.assertIn("entrypoint", top["categories"])
        self.assertGreaterEqual(data["entrypoints"], 1)

    def test_detects_procfile_entrypoint(self):
        _write(self.project / "Procfile", "web: python manage.py runserver\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        top = next(item for item in data["files"] if item["path"] == "Procfile")
        self.assertTrue(top["entrypoint"])
        self.assertIn("entrypoint", top["categories"])
        self.assertGreaterEqual(data["entrypoints"], 1)


class TestBehaviorScope(_GitRepo):
    def setUp(self):
        super().setUp()
        _write(self.project / "core" / "celery.py", "@shared_task\ndef work(): pass\n")
        _write(self.project / "frontend" / "app.js", "console.log(1)\n")
        self._add_all()

    def test_scope_narrows_files(self):
        rc, out = _run(self.project, json_out=True, scope="core")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], "core")
        self.assertEqual(data["summary"]["total_files_scanned"], 1)
        self.assertTrue(all(item["path"].startswith("core/") for item in data["top_files"]))

    def test_invalid_scope_errors_clearly(self):
        rc, out = _run(self.project, scope="bogus")
        self.assertEqual(rc, 2)
        self.assertIn("unknown behavior scope", out.lower())

    def test_human_output_includes_disclaimer(self):
        _write(self.project / "core" / "celery.py", "@shared_task\ndef work(): pass\n")
        self._add_all()

        rc, out = _run(self.project)
        self.assertEqual(rc, 0)
        self.assertIn("This is a heuristic risk map, not a correctness audit.", out)
        self.assertIn("risk_score is the number of distinct risk categories detected for a file", out)


if __name__ == "__main__":
    unittest.main()
