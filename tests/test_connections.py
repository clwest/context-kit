"""Tests for the context-kit `connections` subcommand."""

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

from cli.connections import run_connections  # noqa: E402


def _args(project: Path, *, json_out: bool = False, scope: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(command="connections", path=str(project), json=json_out, scope=scope)


def _run(project: Path, *, json_out: bool = False, scope: str | None = None) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_connections(_args(project, json_out=json_out, scope=scope))
    return rc, buf.getvalue()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


class TestConnectionsJsonShape(_GitRepo):
    def test_json_shape(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        _write(self.project / "frontend" / "src" / "app.tsx", "fetch('/api/ping/')\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], None)
        self.assertIn("summary", data)
        self.assertIn("findings", data)
        self.assertIn("backend_routes", data)
        self.assertIn("frontend_endpoints", data)
        self.assertIn("mobile_endpoints", data)
        self.assertIn("total_files_scanned", data["summary"])
        self.assertIsInstance(data["findings"], list)


class TestConnectionsSignals(_GitRepo):
    def test_detects_django_route(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["backend_routes"], 1)
        self.assertEqual(data["summary"]["orphaned_backend_routes"], 1)

    def test_detects_frontend_api_call_matching_route(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        _write(self.project / "frontend" / "src" / "app.tsx", "fetch('/api/ping/')\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)
        self.assertEqual(data["summary"]["orphaned_backend_routes"], 0)

    def test_detects_frontend_api_call_missing_route(self):
        _write(self.project / "frontend" / "src" / "app.tsx", "fetch('/api/missing/')\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 1)
        severities = {item["severity"] for item in data["findings"]}
        self.assertIn("high", severities)

    def test_detects_backend_route_with_no_client_reference(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["category"] == "orphaned_route")
        self.assertEqual(finding["severity"], "medium")

    def test_detects_celery_task_reference_missing_definition(self):
        _write(self.project / "frontend" / "src" / "tasks.ts", "celery.send_task('core.tasks.missing')\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["task_refs_missing_definition"], 1)
        finding = next(item for item in data["findings"] if item["id"].startswith("task-missing:"))
        self.assertEqual(finding["severity"], "high")

    def test_detects_agent_registry_reference_missing_target(self):
        _write(
            self.project / "core" / "agents" / "registry.py",
            "AGENT_MAP = {'alpha': object()}\n"
            "AGENT_MAP.get('GhostAgent')\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["agent_refs_missing_entry"], 1)
        finding = next(item for item in data["findings"] if item["id"].startswith("agent-missing:"))
        self.assertEqual(finding["severity"], "high")

    def test_registered_agents_and_config_keys_do_not_create_missing_refs(self):
        _write(
            self.project / "core" / "agents" / "routing_config.py",
            "from .content import ContentWriterAgent\n"
            "from .social import SocialMediaAgent\n"
            "AGENT_MAP = {'content_writer': ContentWriterAgent, 'social_media': SocialMediaAgent}\n",
        )
        _write(
            self.project / "core" / "agents" / "__init__.py",
            "from .routing_config import AGENT_MAP\n"
            "from .content import ContentWriterAgent\n"
            "from .social import SocialMediaAgent\n",
        )
        _write(
            self.project / "core" / "agent_usage.py",
            "AGENT_MAP.get('ContentWriterAgent')\n"
            "AGENT_MAP.get('SocialMediaAgent')\n"
            "AGENT_MAP.get('owner')\n"
            "AGENT_MAP.get('priority')\n"
            "AGENT_MAP.get('merge')\n"
            "AGENT_MAP.get('hold_hours')\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["agent_refs_missing_entry"], 0)
        self.assertFalse(any(item["id"].startswith("agent-missing:") for item in data["findings"]))

    def test_existing_ats_endpoint_is_not_missing(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ats/', view)]\n")
        _write(self.project / "frontend" / "src" / "app.tsx", "fetch('/api/ats/')\n")
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)
        self.assertFalse(any(item["id"].startswith("missing-target:/api/ats") for item in data["findings"]))

    def test_beat_setup_reference_to_existing_task_is_not_missing(self):
        _write(
            self.project / "core" / "tasks.py",
            "from celery import shared_task\n\n"
            "@shared_task\ndef workspace_autopilot_conductor():\n    return 1\n",
        )
        _write(
            self.project / "core" / "celery.py",
            "from celery import Celery\n"
            "app = Celery('demo')\n"
            "app.conf.beat_schedule = {'workspace_autopilot_conductor': {'task': 'core.tasks.workspace_autopilot_conductor', 'schedule': 10}}\n"
            "PeriodicTask.objects.create(name='Workspace Autopilot Conductor', task='core.tasks.workspace_autopilot_conductor')\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["task_refs_missing_definition"], 0)
        self.assertFalse(any(item["id"].startswith("task-missing:") for item in data["findings"]))

    def test_demo_and_testing_sources_are_ignored(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        _write(self.project / "frontend" / "src" / "app.tsx", "fetch('/api/ping/')\n")
        _write(
            self.project / "mobile" / "src" / "demo" / "demoData.ts",
            "fetch('/api/missing-demo/')\nAGENT_MAP.get('merge')\n",
        )
        _write(
            self.project / "scripts" / "testing" / "smoke.ts",
            "fetch('/api/missing-testing/')\nAGENT_MAP.get('owner')\n",
        )
        _write(
            self.project / "docs" / "notes.md",
            "fetch('/api/missing-docs/')\nAGENT_MAP.get('priority')\n",
        )
        _write(
            self.project / "archive" / "old.md",
            "fetch('/api/missing-archive/')\n",
        )
        _write(
            self.project / "external-project-docs" / "ref.md",
            "fetch('/api/missing-external/')\n",
        )
        _write(
            self.project / ".rag" / "snippet.md",
            "fetch('/api/missing-rag/')\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)
        self.assertEqual(data["summary"]["agent_refs_missing_entry"], 0)
        self.assertEqual(data["summary"]["task_refs_missing_definition"], 0)


class TestConnectionsScope(_GitRepo):
    def setUp(self):
        super().setUp()
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        _write(self.project / "frontend" / "src" / "app.tsx", "fetch('/api/ping/')\n")
        self._add_all()

    def test_scope_narrows_results(self):
        rc, out = _run(self.project, json_out=True, scope="frontend")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], "frontend")
        self.assertEqual(data["summary"]["backend_routes"], 0)
        self.assertEqual(data["summary"]["frontend_endpoints"], 1)

    def test_invalid_scope_errors_clearly(self):
        rc, out = _run(self.project, scope="bogus")
        self.assertEqual(rc, 2)
        self.assertIn("unknown connections scope", out.lower())


if __name__ == "__main__":
    unittest.main()
