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

from cli.connections import (  # noqa: E402
    _extract_backend_routes,
    _extract_endpoint_refs,
    _route_matches,
    collect_connections,
    classify_route_role,
    run_connections,
)


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

    def test_detects_normalized_frontend_calls_against_django_routes(self):
        _write(
            self.project / "core" / "urls.py",
            "from django.urls import path\n"
            "urlpatterns = [\n"
            "    path('api/ats/analyze/', ATSAnalyzeView.as_view(), name='ats-analyze'),\n"
            "    path('api/ats/generate-summary/', ATSGenerateSummaryView.as_view(), name='ats-generate-summary'),\n"
            "    path('api/autonomous/skill-gaps/', skill_gap_api, name='skill-gaps'),\n"
            "    path('api/autonomous/viral-predictions/', viral_predictions_api, name='viral-predictions'),\n"
            "    path('api/bpaas/create-from-packet/', create_from_packet, name='bpaas-create-from-packet'),\n"
            "]\n",
        )
        _write(
            self.project / "frontend" / "src" / "app.tsx",
            "fetch('/api/ats/analyze/', { method: 'POST' })\n"
            "fetch('/api/ats/generate-summary/', { method: 'POST' })\n"
            "fetch('/api/autonomous/skill-gaps/?limit=50', { credentials: 'include' })\n"
            "fetch('/api/autonomous/viral-predictions/?limit=50', { credentials: 'include' })\n"
            "fetch('/api/bpaas/create-from-packet/', { method: 'POST' })\n",
        )
        self._add_all()

        backend_routes = _extract_backend_routes("core/urls.py", (self.project / "core" / "urls.py").read_text(encoding="utf-8"))
        frontend_refs = _extract_endpoint_refs(
            "frontend/src/app.tsx",
            (self.project / "frontend" / "src" / "app.tsx").read_text(encoding="utf-8"),
            kind="frontend",
        )
        self.assertEqual([route["route"] for route in backend_routes], [
            "/api/ats/analyze/",
            "/api/ats/generate-summary/",
            "/api/autonomous/skill-gaps/",
            "/api/autonomous/viral-predictions/",
            "/api/bpaas/create-from-packet/",
        ])
        self.assertEqual([ref["endpoint"] for ref in frontend_refs], [
            "/api/ats/analyze",
            "/api/ats/generate-summary",
            "/api/autonomous/skill-gaps",
            "/api/autonomous/viral-predictions",
            "/api/bpaas/create-from-packet",
        ])
        self.assertTrue(all(_route_matches(route["route"], ref["endpoint"]) for route, ref in zip(backend_routes, frontend_refs)))

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)
        for endpoint in (
            "/api/ats/analyze",
            "/api/ats/generate-summary",
            "/api/autonomous/skill-gaps",
            "/api/autonomous/viral-predictions",
            "/api/bpaas/create-from-packet",
        ):
            self.assertFalse(any(item["id"] == f"missing-target:{endpoint}" for item in data["findings"]))

    def test_detects_fastapi_routes_and_matches_frontend_calls(self):
        _write(
            self.project / "backend" / "app" / "main.py",
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.post('/api/auth/login')\n"
            "def login():\n"
            "    return {'ok': True}\n",
        )
        _write(
            self.project / "frontend" / "src" / "app.tsx",
            "fetch('/api/auth/login', { method: 'POST' })\n",
        )
        self._add_all()

        backend_routes = _extract_backend_routes("backend/app/main.py", (self.project / "backend" / "app" / "main.py").read_text(encoding="utf-8"))
        self.assertEqual([route["route"] for route in backend_routes], ["/api/auth/login/"])

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["backend_routes"], 1)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)
        self.assertFalse(any(item["id"] == "missing-target:/api/auth/login" for item in data["findings"]))

    def test_extracts_fastapi_router_decorators(self):
        text = (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/api/auth/me')\n"
            "def me():\n"
            "    return {'user': 'me'}\n"
        )
        routes = _extract_backend_routes("backend/app/main.py", text)
        self.assertEqual([route["route"] for route in routes], ["/api/auth/me/"])

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
        self.assertEqual(finding["severity"], "advisory")
        self.assertEqual(finding["route_role"], "health")

    def test_orphan_route_roles_adjust_severity_and_json_shape(self):
        _write(
            self.project / "core" / "urls.py",
            "from django.urls import path\nurlpatterns = [\n"
            "    path('admin/panel/', view),\n"
            "    path('healthz/', view),\n"
            "    path('metrics/', view),\n"
            "    path('api/internal/reports/', view),\n"
            "    path('docs/api/', view),\n"
            "    path('api/users/', view),\n"
            "    path('status/', view),\n"
            "]\n",
        )
        self._add_all()

        rc, out = _run(self.project, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        findings = {item["id"]: item for item in data["findings"] if item["category"] == "orphaned_route"}
        self.assertEqual(findings["orphaned-route:/admin/panel/"]["route_role"], "admin")
        self.assertEqual(findings["orphaned-route:/admin/panel/"]["severity"], "advisory")
        self.assertEqual(findings["orphaned-route:/healthz/"]["route_role"], "health")
        self.assertEqual(findings["orphaned-route:/healthz/"]["severity"], "advisory")
        self.assertEqual(findings["orphaned-route:/metrics/"]["route_role"], "monitoring")
        self.assertEqual(findings["orphaned-route:/metrics/"]["severity"], "advisory")
        self.assertEqual(findings["orphaned-route:/api/internal/reports/"]["route_role"], "internal_api")
        self.assertEqual(findings["orphaned-route:/api/internal/reports/"]["severity"], "advisory")
        self.assertEqual(findings["orphaned-route:/docs/api/"]["route_role"], "docs")
        self.assertEqual(findings["orphaned-route:/docs/api/"]["severity"], "advisory")
        self.assertEqual(findings["orphaned-route:/api/users/"]["route_role"], "public_api")
        self.assertEqual(findings["orphaned-route:/api/users/"]["severity"], "medium")
        self.assertEqual(findings["orphaned-route:/status/"]["route_role"], "unknown")
        self.assertEqual(findings["orphaned-route:/status/"]["severity"], "medium")

    def test_classify_route_role(self):
        cases = {
            "/admin/panel/": "admin",
            "/healthz/": "health",
            "/metrics/": "monitoring",
            "/api/internal/reports/": "internal_api",
            "/docs/api/": "docs",
            "/api/users/": "public_api",
            "/status/": "unknown",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(classify_route_role(path), expected)

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
        self.assertEqual(data["summary"]["backend_routes"], 1)
        self.assertEqual(data["summary"]["frontend_endpoints"], 1)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)

    def test_frontend_scope_keeps_backend_routes_for_matching(self):
        _write(
            self.project / "core" / "urls.py",
            "from django.urls import path\nurlpatterns = [path('api/ats/analyze/', ATSAnalyzeView.as_view(), name='ats-analyze')]\n",
        )
        _write(
            self.project / "frontend" / "src" / "app.tsx",
            "fetch('/api/ats/analyze/', { method: 'POST' })\n",
        )
        self._add_all()

        report = collect_connections(self.project, scope="frontend")
        self.assertEqual([route["route"] for route in report.backend_routes], ["/api/ats/analyze/"])
        self.assertEqual([ref["endpoint"] for ref in report.frontend_endpoints], ["/api/ats/analyze"])
        self.assertEqual(report.summary["orphaned_backend_routes"], 0)
        self.assertFalse(any(item.category == "missing_target" and item.title == "Missing backend endpoint" for item in report.findings))
        self.assertFalse(any(item.category == "orphaned_route" for item in report.findings))

        rc, out = _run(self.project, json_out=True, scope="frontend")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["backend_routes"], 1)
        self.assertEqual(data["summary"]["orphaned_backend_routes"], 0)
        self.assertEqual(data["summary"]["missing_backend_endpoints"], 0)
        self.assertFalse(any(item["category"] == "orphaned_route" for item in data["findings"]))
        self.assertFalse(any(item["id"] == "missing-target:/api/ats/analyze" for item in data["findings"]))

    def test_agents_scope_keeps_clean_backend_routes(self):
        _write(
            self.project / "core" / "urls.py",
            "from django.urls import include, path, re_path\n"
            "urlpatterns = [\n"
            "    path('', include('core.urls_unified')),\n"
            "    path('', lambda request: render(request, 'home.html'), name='home'),\n"
            "    path('api/foo/', include('core.api.urls')),\n"
            "    path('dashboard/', TruthDashboardView.as_view(), name='dashboard'),\n"
            "    re_path(r'^(?!api/|admin/|media/|static/|ws/|health/)(?!.*\\\\.\\\\w{1,10}(?:/|$)).*$', react_app, name='react-app'),\n"
            "]\n",
        )
        self._add_all()

        report = collect_connections(self.project, scope="agents")
        routes = [item["route"] for item in report.backend_routes]
        self.assertIn("/", routes)
        self.assertIn("/api/foo/", routes)
        self.assertIn("/dashboard/", routes)
        self.assertEqual(report.summary["orphaned_backend_routes"], 0)
        self.assertFalse(any(item.category == "orphaned_route" for item in report.findings))
        self.assertFalse(any("include" in route or ".as_view" in route for route in routes))
        self.assertFalse(any(any(ch in route for ch in ("'", '"', ",")) for route in routes))

        rc, out = _run(self.project, json_out=True, scope="agents")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["backend_routes"], 4)
        self.assertEqual(data["summary"]["orphaned_backend_routes"], 0)
        self.assertFalse(any(item["category"] == "orphaned_route" for item in data["findings"]))

    def test_backend_scope_still_emits_orphan_routes(self):
        _write(self.project / "core" / "urls.py", "from django.urls import path\nurlpatterns = [path('api/ping/', view)]\n")
        self._add_all()

        report = collect_connections(self.project, scope="backend")
        self.assertEqual(report.summary["backend_routes"], 1)
        self.assertEqual(report.summary["orphaned_backend_routes"], 1)
        self.assertTrue(any(item.category == "orphaned_route" for item in report.findings))

        rc, out = _run(self.project, json_out=True, scope="backend")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"]["backend_routes"], 1)
        self.assertEqual(data["summary"]["orphaned_backend_routes"], 1)
        self.assertTrue(any(item["category"] == "orphaned_route" for item in data["findings"]))

    def test_invalid_scope_errors_clearly(self):
        rc, out = _run(self.project, scope="bogus")
        self.assertEqual(rc, 2)
        self.assertIn("unknown connections scope", out.lower())


if __name__ == "__main__":
    unittest.main()
