"""Tests for the context-kit `inspect` subcommand.

Each test scaffolds a synthetic project tree under a temp cwd, runs
`inspect` against it, and asserts on stdout + the JSON output. No
external commands beyond ``git`` invocations the inspect module
itself runs (which gracefully degrade when ``.git`` is absent).
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.inspect import run_inspect  # noqa: E402


def _inspect_args(
    path=None,
    *,
    project=None,
    json_out=False,
    depth=2,
    scope=None,
    include_related=False,
    include_history=False,
    output=None,
):
    return argparse.Namespace(
        command="inspect",
        path=str(path) if path is not None else None,
        project=str(project) if project is not None else None,
        json=json_out,
        output=str(output) if output is not None else None,
        depth=depth,
        scope=scope,
        include_related=include_related,
        include_history=include_history,
        format="markdown",
    )


def _run_capture(
    path=None,
    *,
    project=None,
    json_out=False,
    scope=None,
    include_related=False,
    include_history=False,
) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_inspect(
            _inspect_args(
                path,
                project=project,
                json_out=json_out,
                scope=scope,
                include_related=include_related,
                include_history=include_history,
            )
        )
    return rc, buf.getvalue()


def _seed_python_django(root: Path) -> None:
    """Plant a minimal Django-shaped project under ``root``."""
    (root / "manage.py").write_text(
        "import os, sys\nif __name__ == '__main__':\n    pass\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    core = root / "core"
    core.mkdir()
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "settings.py").write_text(
        "INSTALLED_APPS = [\n"
        "    'django.contrib.admin',\n"
        "    'django.contrib.auth',\n"
        "    'core',\n"
        "    'core.api',\n"
        "]\n",
        encoding="utf-8",
    )
    (core / "urls.py").write_text(
        "from django.urls import path, include\n"
        "urlpatterns = [\n"
        "    path('admin/', admin_view),\n"
        "    path('api/', include('core.api.urls')),\n"
        "    path('health/', health_view),\n"
        "]\n",
        encoding="utf-8",
    )
    (core / "tasks.py").write_text(
        "from celery import shared_task\n"
        "@shared_task\n"
        "def do_one(): return 1\n"
        "@shared_task\n"
        "def do_two(): return 2\n",
        encoding="utf-8",
    )
    (core / "views.py").write_text("def health_view(request): pass\n", encoding="utf-8")
    (core / "models.py").write_text("class Foo: pass\n", encoding="utf-8")

    cmds = core / "management" / "commands"
    cmds.mkdir(parents=True)
    (cmds / "__init__.py").write_text("", encoding="utf-8")
    (cmds / "do_one.py").write_text(
        "from django.core.management.base import BaseCommand\n"
        "class Command(BaseCommand): pass\n",
        encoding="utf-8",
    )


def _seed_nextjs(root: Path) -> None:
    """Plant a minimal Next.js-shaped project under ``root``."""
    (root / "package.json").write_text(
        '{"name":"demo","dependencies":{"next":"14.0.0"}}\n',
        encoding="utf-8",
    )
    (root / "next.config.js").write_text("module.exports = {};\n", encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "page.tsx").write_text("export default function Home(){return null;}\n", encoding="utf-8")
    (root / "app" / "about").mkdir()
    (root / "app" / "about" / "page.tsx").write_text(
        "export default function About(){return null;}\n", encoding="utf-8"
    )
    (root / "app" / "api").mkdir()
    (root / "app" / "api" / "ping").mkdir()
    (root / "app" / "api" / "ping" / "route.ts").write_text(
        "export async function GET(){return new Response('ok');}\n", encoding="utf-8"
    )


def _seed_nested_backend_frontend(root: Path) -> None:
    backend = root / "backend"
    frontend = root / "frontend"
    backend.mkdir()
    frontend.mkdir()
    app_dir = backend / "app"
    app_dir.mkdir()
    (backend / "requirements.txt").write_text(
        "fastapi==0.115.0\nsqlalchemy==2.0.0\n",
        encoding="utf-8",
    )
    (backend / "main.py").write_text(
        "from fastapi import FastAPI, APIRouter\n"
        "from sqlalchemy.orm import declarative_base\n"
        "app = FastAPI()\n"
        "router = APIRouter()\n"
        "@app.post('/api/auth/register')\n"
        "def register(): return {'ok': True}\n"
        "@app.post('/api/auth/login')\n"
        "def login(): return {'ok': True}\n"
        "@app.get('/api/users/me')\n"
        "def me(): return {'ok': True}\n"
        "@app.post('/api/sessions')\n"
        "def sessions(): return {'ok': True}\n"
        "@app.post('/api/sessions/{session_id}/chat')\n"
        "def session_chat(): return {'ok': True}\n"
        "@app.post('/api/founder-projects')\n"
        "def founder_project_create(): return {'ok': True}\n"
        "@app.get('/api/founder-projects')\n"
        "def founder_project_list(): return {'ok': True}\n"
        "@app.get('/api/founder-projects/{project_id}')\n"
        "def founder_project_get(): return {'ok': True}\n"
        "Base = declarative_base()\n"
        "class Thing(Base):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_dir / "models.py").write_text(
        "from sqlalchemy.orm import DeclarativeBase\n"
        "class Base(DeclarativeBase):\n"
        "    pass\n"
        "class Widget(Base):\n"
        "    __tablename__ = 'widgets'\n",
        encoding="utf-8",
    )
    (app_dir / "tiers.py").write_text(
        "from dataclasses import dataclass\n"
        "\n"
        "@dataclass\n"
        "class TierConfig:\n"
        "    allowed_modes = ['basic', 'pro']\n"
        "    max_sessions_per_day = 10\n"
        "    max_response_tokens = 2000\n"
        "    max_messages_per_session = 25\n"
        "\n"
        "TIERS = {\n"
        "    'free': TierConfig(),\n"
        "}\n",
        encoding="utf-8",
    )
    (frontend / "package.json").write_text(
        '{"name":"mentorforge-ui","dependencies":{"react":"18.3.1","vite":"5.4.0"}}\n',
        encoding="utf-8",
    )
    (frontend / "vite.config.ts").write_text(
        "import { defineConfig } from 'vite';\nexport default defineConfig({});\n",
        encoding="utf-8",
    )


class _CwdSandbox(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self._prev_cwd = Path.cwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# Generic skeleton + non-repo
# ---------------------------------------------------------------------------


class TestEmptyDirectory(_CwdSandbox):
    def test_empty_dir_runs_cleanly(self):
        rc, out = _run_capture(self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("=== CONTEXT-KIT INSPECT ===", out)

    def test_empty_dir_reports_no_manifests(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("(no manifests detected at root)", out)

    def test_handles_non_git_directory(self):
        rc, out = _run_capture(self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertIn("(not a git repo)", out)

    def test_json_includes_null_scope_by_default(self):
        rc, out = _run_capture(self.tmpdir, json_out=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIn("scope", data)
        self.assertIsNone(data["scope"])
        self.assertIn("include_related", data)
        self.assertIn("include_history", data)
        self.assertFalse(data["include_related"])
        self.assertFalse(data["include_history"])


# ---------------------------------------------------------------------------
# Django probe
# ---------------------------------------------------------------------------


class TestDjangoDetection(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_python_django(self.tmpdir)

    def test_primary_stack_names_python_and_django(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("Languages: python", out)
        self.assertIn("django", out)
        self.assertIn("manage.py", out)
        self.assertIn("Confidence: high", out)

    def test_django_signals_named_in_report(self):
        _, out = _run_capture(self.tmpdir)
        # `INSTALLED_APPS = [...]` had 4 entries; we counted 3 path() calls;
        # 2 @shared_task decorators; 1 management command (do_one.py).
        self.assertIn("Django:", out)
        self.assertIn("apps=4", out)
        self.assertIn("url_patterns=3", out)
        self.assertIn("tasks=2", out)
        self.assertIn("mgmt_commands=1", out)

    def test_manage_py_listed_as_entry_point(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("manage.py", out)
        self.assertIn("django-cli", out)


class TestNestedManifestDetection(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_nested_backend_frontend(self.tmpdir)

    def test_nested_backend_requirements_detect_python_indicators(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("backend/requirements.txt", out)
        self.assertIn("Python indicators", out)
        self.assertIn("FastAPI", out)
        self.assertIn("SQLAlchemy", out)

    def test_nested_frontend_package_json_detects_node_indicators(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("frontend/package.json", out)
        self.assertIn("Node indicators", out)

    def test_nested_package_json_detects_react_vite_dependencies(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("frontend/package.json: Vite, React", out)
        self.assertIn("React", out)
        self.assertIn("Vite", out)

    def test_structured_implementation_facts_section_is_emitted(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("## Structured implementation facts", out)
        self.assertIn("capability: auth", out)
        self.assertIn("capability: sessions/chat", out)
        self.assertIn("capability: founder_projects/export", out)
        self.assertIn("capability: tier_config", out)
        self.assertIn("backend/main.py", out)
        self.assertIn("@app.post('/api/auth/register')", out)
        self.assertRegex(out, r"backend/app/tiers\.py:\d+ .*allowed_modes")

    def test_nested_primary_stack_reflects_frameworks(self):
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        self.assertIn("backend/requirements.txt", data["primary_stack"]["manifests"])
        self.assertIn("frontend/package.json", data["primary_stack"]["manifests"])
        self.assertIn("python", data["primary_stack"]["languages"])
        self.assertIn("javascript", data["primary_stack"]["languages"])
        self.assertIn("FastAPI", data["primary_stack"]["frameworks"])
        self.assertIn("SQLAlchemy", data["primary_stack"]["frameworks"])
        self.assertIn("React", data["primary_stack"]["frameworks"])
        self.assertIn("Vite", data["primary_stack"]["frameworks"])
        self.assertIn("backend/app/models.py", out)


class TestContextKitSelfFrameworkFiltering(unittest.TestCase):
    def test_repo_root_ignores_test_fixture_frameworks(self):
        _, out = _run_capture(project=REPO_ROOT, json_out=True)
        data = json.loads(out)
        self.assertEqual(data["primary_stack"]["languages"], ["python"])
        self.assertNotIn("FastAPI", data["primary_stack"]["frameworks"])
        self.assertNotIn("SQLAlchemy", data["primary_stack"]["frameworks"])
        self.assertIn("pyproject.toml", data["primary_stack"]["manifests"])
        self.assertNotIn("FastAPI: ", out)
        self.assertNotIn("SQLAlchemy: ", out)


class TestContextKitCliCapabilities(unittest.TestCase):
    def test_repo_root_detects_cli_capabilities(self):
        _, out = _run_capture(project=REPO_ROOT)
        self.assertIn("## Structured implementation facts", out)
        self.assertIn("capability: orient", out)
        self.assertIn("capability: inspect", out)
        self.assertIn("capability: capabilities", out)
        self.assertIn("capability: chat", out)
        # Dispatch-table detection: each entry in context_kit.py's ``_COMMANDS``
        # dict maps a command name to a (module, function) tuple. See
        # ``_group_cli_capabilities`` in cli/inspect.py.
        self.assertRegex(out, r"context_kit\.py:\d+ \"orient\":\s+\(\"cli\.")
        self.assertRegex(out, r"context_kit\.py:\d+ \"inspect\":\s+\(\"cli\.")
        self.assertRegex(out, r"context_kit\.py:\d+ \"capabilities\":\s+\(\"cli\.")
        self.assertRegex(out, r"context_kit\.py:\d+ \"chat\":\s+\(\"cli\.")
        self.assertRegex(out, r"cli/chat\.py:\d+ def run_chat\(args: argparse\.Namespace\) -> int:")
        self.assertRegex(out, r"cli/inspect\.py:\d+ def run_inspect\(args: argparse\.Namespace\) -> int:")
        self.assertRegex(out, r"cli/capabilities\.py:\d+ def run_capabilities\(args: argparse\.Namespace\) -> int:")


class TestScopedInspect(_CwdSandbox):
    def setUp(self):
        super().setUp()
        (self.tmpdir / "manage.py").write_text("print('root')\n", encoding="utf-8")
        core = self.tmpdir / "core"
        core.mkdir()
        (core / "settings.py").write_text("INSTALLED_APPS = ['core']\n", encoding="utf-8")
        (core / "urls.py").write_text("from django.urls import path\nurlpatterns = [path('x', view)]\n", encoding="utf-8")
        frontend = self.tmpdir / "frontend"
        frontend.mkdir()
        (frontend / "package.json").write_text('{"dependencies":{"next":"14.0.0"}}\n', encoding="utf-8")
        (frontend / "next.config.js").write_text("module.exports = {};\n", encoding="utf-8")

    def test_default_behavior_does_not_show_scope_label(self):
        rc, out = _run_capture(self.tmpdir)
        self.assertEqual(rc, 0)
        self.assertNotIn("Scope:", out)

    def test_core_scope_narrows_output(self):
        rc, out = _run_capture(self.tmpdir, scope="core")
        self.assertEqual(rc, 0)
        self.assertIn("Scope:          core", out)
        self.assertIn("Scope mode:     strict", out)
        self.assertIn("core/", out)
        self.assertNotIn("frontend/", out)
        self.assertNotIn("nextjs", out.lower())

        rc, out = _run_capture(self.tmpdir, json_out=True, scope="core")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], "core")
        self.assertFalse(data["include_related"])
        self.assertFalse(data["include_history"])

    def test_invalid_scope_returns_clear_error(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_inspect(_inspect_args(self.tmpdir, scope="bogus"))
        self.assertEqual(rc, 2)
        self.assertIn("unknown inspect scope", buf.getvalue().lower())


class TestCeleryScopeSelection(_CwdSandbox):
    def setUp(self):
        super().setUp()
        core = self.tmpdir / "core"
        core.mkdir()
        (core / "celery.py").write_text(
            "from celery import Celery\napp = Celery('demo')\napp.conf.beat_schedule = {'ping': {'task': 'core.tasks.ping', 'schedule': 10}}\n",
            encoding="utf-8",
        )
        (core / "tasks.py").write_text(
            "@shared_task\ndef ping(): return 1\n",
            encoding="utf-8",
        )
        (core / "schedulers.py").write_text("class Scheduler: pass\n", encoding="utf-8")
        (core / "management").mkdir()
        (core / "management" / "commands").mkdir(parents=True)
        (core / "management" / "commands" / "repair_celery.py").write_text(
            "def handle(): pass\n",
            encoding="utf-8",
        )
        (self.tmpdir / "Procfile").write_text("worker: celery -A core.celery worker\n", encoding="utf-8")
        docs = self.tmpdir / "docs"
        (docs / "topics").mkdir(parents=True)
        (docs / "topics" / "celery-workers.md").write_text("# Celery workers\n", encoding="utf-8")
        (docs / "external-project-docs").mkdir(parents=True)
        (docs / "external-project-docs" / "celery.md").write_text("Celery notes from elsewhere\n", encoding="utf-8")
        (docs / "archive").mkdir(parents=True)
        (docs / "archive" / "old-celery.md").write_text("Legacy celery details\n", encoding="utf-8")
        (docs / "verification").mkdir(parents=True)
        (docs / "verification" / "VERIFY_REPORT.md").write_text("Celery report\n", encoding="utf-8")

    def test_celery_scope_excludes_external_project_docs_by_default(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="celery")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], "celery")
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertIn("core/", by_path)
        self.assertIn("docs/", by_path)
        self.assertEqual(by_path["docs/"]["files"], 1)
        self.assertEqual(by_path["core/"]["files"], 4)
        hot_paths = [item["path"] for item in data["hot_files"]]
        self.assertIn("core/celery.py", hot_paths)
        self.assertNotIn("docs/external-project-docs/celery.md", hot_paths)
        self.assertNotIn("docs/archive/old-celery.md", hot_paths)
        self.assertNotIn("docs/verification/VERIFY_REPORT.md", hot_paths)

    def test_celery_scope_can_include_history_when_requested(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="celery", include_history=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertEqual(by_path["docs/"]["files"], 3)


class TestStrictVsRelatedScopes(_CwdSandbox):
    def setUp(self):
        super().setUp()
        docs = self.tmpdir / "docs"
        (docs / "topics").mkdir(parents=True)
        (docs / "topics" / "agent-system.md").write_text("# agents\n", encoding="utf-8")
        (docs / "topics" / "spider-network.md").write_text("# spiders\n", encoding="utf-8")
        (docs / "topics" / "celery-workers.md").write_text("# celery\n", encoding="utf-8")
        (docs / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
        (docs / "SPIDERS.md").write_text("# spiders\n", encoding="utf-8")
        (docs / "notes.md").write_text("# rag index\n", encoding="utf-8")
        (docs / "images").mkdir()
        (docs / "images" / "diagram.png").write_bytes(b"png")
        (docs / "mobile").mkdir()
        (docs / "mobile" / "asset.png").write_bytes(b"png")
        (self.tmpdir / ".rag").mkdir()
        (self.tmpdir / ".rag" / "agent-context.json").write_text('{"agent_map": true}\n', encoding="utf-8")
        (self.tmpdir / "core").mkdir()
        (self.tmpdir / "core" / "agents").mkdir(parents=True)
        (self.tmpdir / "core" / "agents" / "registry.py").write_text("AGENT_MAP = {}\n", encoding="utf-8")
        (self.tmpdir / "ai_core").mkdir()
        (self.tmpdir / "ai_core" / "spiders").mkdir(parents=True)
        (self.tmpdir / "ai_core" / "spiders" / "registry.py").write_text("SpiderData = {}\n", encoding="utf-8")
        (self.tmpdir / "frontend").mkdir()
        (self.tmpdir / "frontend" / "links.md").write_text("spider link\n", encoding="utf-8")

    def test_docs_rag_excludes_images_by_default(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="docs-rag")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["scope"], "docs-rag")
        self.assertFalse(data["include_related"])
        hot_paths = [item["path"] for item in data["hot_files"]]
        self.assertIn("docs/notes.md", hot_paths)
        self.assertIn(".rag/agent-context.json", hot_paths)
        self.assertNotIn("docs/images/diagram.png", hot_paths)
        self.assertNotIn("docs/mobile/asset.png", hot_paths)
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertIn("docs/", by_path)
        self.assertIn(".rag/", by_path)

    def test_agents_default_excludes_related_rag(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="agents")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        hot_paths = [item["path"] for item in data["hot_files"]]
        self.assertIn("core/agents/registry.py", hot_paths)
        self.assertIn("docs/AGENTS.md", hot_paths)
        self.assertNotIn(".rag/agent-context.json", hot_paths)
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertNotIn(".rag/", by_path)

    def test_agents_include_related_can_pull_rag(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="agents", include_related=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(data["include_related"])
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertIn(".rag/", by_path)

    def test_spiders_default_excludes_frontend(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="spiders")
        self.assertEqual(rc, 0)
        data = json.loads(out)
        hot_paths = [item["path"] for item in data["hot_files"]]
        self.assertIn("ai_core/spiders/registry.py", hot_paths)
        self.assertNotIn("frontend/links.md", hot_paths)
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertNotIn("frontend/", by_path)

    def test_spiders_include_related_can_pull_frontend(self):
        rc, out = _run_capture(self.tmpdir, json_out=True, scope="spiders", include_related=True)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertIn("frontend/", by_path)


# ---------------------------------------------------------------------------
# Next.js probe
# ---------------------------------------------------------------------------


class TestNextJsDetection(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_nextjs(self.tmpdir)

    def test_primary_stack_names_javascript_and_nextjs(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("Languages: javascript", out)
        self.assertIn("nextjs", out)
        self.assertIn("next.config.js", out)

    def test_nextjs_signals_count_routes_and_api_routes(self):
        _, out = _run_capture(self.tmpdir)
        # Two `page.tsx` files (root + about) + one `route.ts` (api/ping).
        self.assertIn("Next.js:", out)
        self.assertIn("route_files=2", out)
        self.assertIn("api_routes=1", out)


class TestStaticRepoHints(_CwdSandbox):
    def setUp(self):
        super().setUp()
        (self.tmpdir / "package.json").write_text(
            json.dumps(
                {
                    "name": "demo-app",
                    "scripts": {
                        "dev": "vite",
                        "test": "vitest",
                        "lint": "eslint .",
                    },
                    "dependencies": {
                        "react": "^18.0.0",
                        "react-dom": "^18.0.0",
                        "vite": "^5.0.0",
                        "react-router-dom": "^6.0.0",
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.tmpdir / "pyproject.toml").write_text(
            "[project]\nname = \"demo-app\"\n[project.scripts]\nserve = \"demo:main\"\n",
            encoding="utf-8",
        )
        (self.tmpdir / "Makefile").write_text(
            "test:\n\tpytest\nbuild:\n\tpython -m build\n",
            encoding="utf-8",
        )
        src = self.tmpdir / "src"
        src.mkdir()
        (src / "api.py").write_text(
            "from fastapi import FastAPI, APIRouter\n"
            "app = FastAPI()\n"
            "router = APIRouter()\n"
            "@app.get('/health')\n"
            "def health():\n    return {'ok': True}\n"
            "@router.post('/items')\n"
            "def create_item():\n    return {'ok': True}\n",
            encoding="utf-8",
        )
        web = self.tmpdir / "web"
        web.mkdir()
        (web / "urls.py").write_text(
            "from django.urls import path, re_path\n"
            "urlpatterns = [path('health/', health), re_path(r'^x/$', x)]\n",
            encoding="utf-8",
        )
        (web / "models.py").write_text(
            "from django.db import models\n"
            "class Thing(models.Model):\n    pass\n",
            encoding="utf-8",
        )
        (web / "schema.py").write_text(
            "from pydantic import BaseModel\n"
            "class Payload(BaseModel):\n    value: str\n",
            encoding="utf-8",
        )
        (self.tmpdir / "app.py").write_text(
            "from flask import Flask\napp = Flask(__name__)\n@app.route('/ping')\ndef ping(): return 'ok'\n",
            encoding="utf-8",
        )
        (self.tmpdir / ".env.example").write_text(
            "API_KEY=\nDEBUG=true\n# comment\nexport EXPORTED=value\n",
            encoding="utf-8",
        )
        (self.tmpdir / ".env").write_text("SECRET_TOKEN=do-not-read\n", encoding="utf-8")
        (self.tmpdir / "docker-compose.yml").write_text(
            "services:\n  web:\n    image: demo\n  db:\n    image: postgres\n",
            encoding="utf-8",
        )
        (self.tmpdir / "Dockerfile").write_text("FROM python:3.11\n", encoding="utf-8")
        (self.tmpdir / "app").mkdir()
        (self.tmpdir / "app" / "page.tsx").write_text(
            "export default function Home(){return null;}\n",
            encoding="utf-8",
        )
        bulky = self.tmpdir / "node_modules"
        bulky.mkdir()
        (bulky / "big.js").write_text("x" * 1024, encoding="utf-8")

    def test_package_json_scripts_are_reported(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("package.json scripts", out)
        self.assertIn("dev", out)
        self.assertIn("vitest", out)

    def test_project_flag_uses_target_path(self):
        _, out = _run_capture(project=self.tmpdir)
        self.assertIn("demo-app", out)
        self.assertIn("package.json scripts", out)

    def test_output_file_is_written(self):
        output_path = Path("inspect.md")
        with redirect_stdout(io.StringIO()):
            rc = run_inspect(_inspect_args(project=self.tmpdir, output=output_path))
        self.assertEqual(rc, 0)
        self.assertTrue(output_path.is_file())
        self.assertIn("# context-kit inspect", output_path.read_text(encoding="utf-8"))

    def test_ignored_bulky_dirs_do_not_show_up(self):
        _, out = _run_capture(self.tmpdir)
        self.assertNotIn("node_modules/", out)

    def test_fastapi_routes_are_detected(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("FastAPI", out)
        self.assertIn("health", out)
        self.assertIn("items", out)

    def test_django_urls_are_detected(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("Django", out)
        self.assertIn("urlpatterns", out)

    def test_env_example_keys_are_reported_without_secrets(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("API_KEY", out)
        self.assertIn("DEBUG", out)
        self.assertIn("EXPORTED", out)
        self.assertNotIn("SECRET_TOKEN=do-not-read", out)


# ---------------------------------------------------------------------------
# Monorepo: depth-1 child workspaces with framework probes per child
# ---------------------------------------------------------------------------


class TestMonorepoSplit(_CwdSandbox):
    def setUp(self):
        super().setUp()
        # Root has nothing; backend/ has Django; frontend/ has Next.js.
        backend = self.tmpdir / "backend"
        frontend = self.tmpdir / "frontend"
        backend.mkdir()
        frontend.mkdir()
        _seed_python_django(backend)
        _seed_nextjs(frontend)

    def test_both_workspaces_detected_as_subsystems(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("backend/", out)
        self.assertIn("frontend/", out)

    def test_each_workspace_carries_its_own_framework_signals(self):
        # Use --json so we can read the structured per-subsystem signals
        # without parsing the human-readable summary.
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        by_path = {s["path"]: s for s in data["subsystems"]}
        self.assertIn("backend/", by_path)
        self.assertIn("frontend/", by_path)
        # backend/ has Django signals; frontend/ has Next.js signals.
        self.assertIsNotNone(by_path["backend/"]["framework_signals"]["django"])
        self.assertIsNone(by_path["backend/"]["framework_signals"]["nextjs"])
        self.assertIsNone(by_path["frontend/"]["framework_signals"]["django"])
        self.assertIsNotNone(by_path["frontend/"]["framework_signals"]["nextjs"])

    def test_root_has_no_framework_signals_when_only_children_do(self):
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        # Root itself has no manifests / framework signals — only the
        # workspaces do. The "framework_signals" object is present but
        # both languages are None.
        self.assertIsNone(data["framework_signals"]["django"])
        self.assertIsNone(data["framework_signals"]["nextjs"])


# ---------------------------------------------------------------------------
# Risk patterns
# ---------------------------------------------------------------------------


class TestRiskPatterns(_CwdSandbox):
    def setUp(self):
        super().setUp()
        # Tracked virtualenv: synthesize the dir + a couple files.
        venv = self.tmpdir / "venv_ml"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n", encoding="utf-8")
        (venv / "bin").mkdir()
        (venv / "bin" / "activate").write_text("# activate\n", encoding="utf-8")

        # Multiple .env templates.
        for name in (".env.example", ".env.template", ".env.sample", ".env.new"):
            (self.tmpdir / name).write_text("# example\n", encoding="utf-8")

        # Tracked .env (the secret-leak case).
        (self.tmpdir / ".env").write_text("SECRET_KEY=abc\n", encoding="utf-8")

        # Oversized static asset (6 MB > 5 MB threshold).
        static = self.tmpdir / "core" / "static" / "images"
        static.mkdir(parents=True)
        (static / "logo.png").write_bytes(b"\x89PNG" + b"\x00" * (6 * 1024 * 1024))

        # Tracked __pycache__ inside a tracked dir.
        cache = self.tmpdir / "core" / "__pycache__"
        cache.mkdir()
        (cache / "x.cpython-311.pyc").write_bytes(b"\x00\x00")

    def test_tracked_venv_flagged(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("[tracked-venv]", out)
        self.assertIn("venv_ml", out)

    def test_tracked_env_file_flagged(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("[tracked-env-file]", out)

    def test_multiple_env_templates_flagged(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("[multiple-env-templates]", out)
        # Output renders only the first 3 evidence lines (alphabetical) to
        # keep the section concise. With 4 templates seeded, .env.example
        # and .env.sample sort into the top 3; .env.template is the 4th and
        # gets cut off.
        self.assertIn(".env.example", out)
        self.assertIn(".env.sample", out)
        # Total count is reported in the summary line regardless.
        self.assertIn("4 `.env.*` template variants", out)

    def test_oversized_static_asset_flagged(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("[oversized-static-asset]", out)
        self.assertIn("logo.png", out)
        self.assertIn("MB", out)

    def test_tracked_build_artifact_dir_is_skipped_when_ignored(self):
        _, out = _run_capture(self.tmpdir)
        self.assertNotIn("[tracked-build-artifacts]", out)
        self.assertNotIn("node_modules", out)


# ---------------------------------------------------------------------------
# JSON output schema lock
# ---------------------------------------------------------------------------


class TestJsonOutputShape(_CwdSandbox):
    def setUp(self):
        super().setUp()
        _seed_python_django(self.tmpdir)

    def test_json_parses(self):
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        self.assertIsInstance(data, dict)

    def test_top_level_keys_are_locked(self):
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        expected = {
            "repo",
            "path",
            "scope",
            "include_related",
            "include_history",
            "head",
            "counts",
            "primary_stack",
            "subsystems",
            "entry_points",
            "framework_signals",
            "hot_files",
            "risks",
            "stale_docs",
            "documentation_intelligence",
            "recommendations",
        }
        self.assertEqual(set(data.keys()), expected)

    def test_documentation_intelligence_field_shape(self):
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        di = data["documentation_intelligence"]
        self.assertEqual(set(di.keys()), {
            "markdown_file_count",
            "session_handoff_count",
            "anchor_docs",
            "audit_folders",
            "process_docs_present",
            "rag_corpus_present",
            "rag_corpus_paths",
            "strength",
        })
        self.assertIn(di["strength"], {"none", "low", "medium", "high"})

    def test_risks_use_stable_ids(self):
        # Re-seed with a known risk so we can assert on `id`.
        (self.tmpdir / ".env").write_text("X=1\n", encoding="utf-8")
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        ids = {r["id"] for r in data["risks"]}
        self.assertIn("tracked-env-file", ids)
        # Severity is one of the documented values.
        for risk in data["risks"]:
            self.assertIn(risk["severity"], {"high", "medium", "low"})


# ---------------------------------------------------------------------------
# Stale doc heuristic
# ---------------------------------------------------------------------------


class TestStaleDocs(_CwdSandbox):
    def test_old_dated_doc_is_flagged(self):
        # Doc with a frontmatter date 90 days in the past.
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
        (self.tmpdir / "OLD_DOC.md").write_text(
            f"---\ndate: {old}\n---\n\n# Old\n",
            encoding="utf-8",
        )
        _, out = _run_capture(self.tmpdir)
        self.assertIn("Possibly stale docs", out)
        self.assertIn("OLD_DOC.md", out)

    def test_recent_doc_is_not_flagged(self):
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date().isoformat()
        (self.tmpdir / "FRESH_DOC.md").write_text(
            f"---\ndate: {today}\n---\n\n# Fresh\n",
            encoding="utf-8",
        )
        _, out = _run_capture(self.tmpdir)
        self.assertNotIn("Possibly stale docs", out)


class TestDocumentationIntelligence(_CwdSandbox):
    """Detection of `docs/` as active AI memory infrastructure vs.
    passive reference docs. Section appears for `medium`+ strength;
    recommendation fires only at `high`."""

    def _di_from_json(self) -> dict:
        _, out = _run_capture(self.tmpdir, json_out=True)
        return json.loads(out)["documentation_intelligence"]

    def test_no_docs_folder_yields_strength_none(self):
        di = self._di_from_json()
        self.assertEqual(di["strength"], "none")
        self.assertEqual(di["markdown_file_count"], 0)
        self.assertEqual(di["session_handoff_count"], 0)
        # Section must NOT render at strength=none.
        _, text = _run_capture(self.tmpdir)
        self.assertNotIn("## Documentation Intelligence", text)

    def test_small_unstructured_docs_folder_is_low(self):
        # A handful of READMEs, no handoffs, no anchors, no rag.
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "README.md").write_text("# r\n", encoding="utf-8")
        (docs / "CONTRIBUTING.md").write_text("# c\n", encoding="utf-8")

        di = self._di_from_json()
        self.assertEqual(di["strength"], "low")
        self.assertEqual(di["markdown_file_count"], 2)
        # Section still suppressed at low strength.
        _, text = _run_capture(self.tmpdir)
        self.assertNotIn("## Documentation Intelligence", text)

    def test_medium_signal_renders_section_without_recommendation(self):
        # Two distinct active-context signals (handoffs + anchor),
        # but no scale (markdown < 200, handoffs < 50).
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "PLATFORM_WHAT_IT_IS.md").write_text("# anchor\n", encoding="utf-8")
        (docs / "PLATFORM_INVENTORY.md").write_text("# anchor\n", encoding="utf-8")
        handoffs = docs / "handoffs"
        handoffs.mkdir()
        for i in range(1, 11):
            (handoffs / f"SESSION_{i:03d}_X.md").write_text("# h\n", encoding="utf-8")

        di = self._di_from_json()
        self.assertEqual(di["strength"], "medium")
        self.assertGreaterEqual(di["session_handoff_count"], 5)
        self.assertTrue(di["anchor_docs"])

        # Section renders.
        _, text = _run_capture(self.tmpdir)
        self.assertIn("## Documentation Intelligence", text)
        self.assertIn("active context/memory layer", text)
        self.assertIn("Caution", text)
        # But the recommendation does NOT fire at medium.
        ids = [r["id"] for r in json.loads(_run_capture(self.tmpdir, json_out=True)[1])["recommendations"]]
        self.assertNotIn("review-docs-context-first", ids)

    def test_high_signal_fires_recommendation(self):
        # Multiple distinct signals + scale.
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "PLATFORM_WHAT_IT_IS.md").write_text("# anchor\n", encoding="utf-8")
        (docs / "PLATFORM_INVENTORY.md").write_text("# anchor\n", encoding="utf-8")
        # >= 50 session handoffs to trip the scale_high path.
        handoffs = docs / "handoffs"
        handoffs.mkdir()
        for i in range(1, 56):
            (handoffs / f"SESSION_{i:04d}_X.md").write_text("# h\n", encoding="utf-8")
        # Audit folder under docs/.
        (docs / "audit").mkdir()
        (docs / "audit" / "AUDIT_V1.md").write_text("# a\n", encoding="utf-8")
        # RAG corpus at root.
        rag = self.tmpdir / ".rag"
        rag.mkdir()
        (rag / "corpus.jsonl").write_text('{"x":1}\n', encoding="utf-8")

        di = self._di_from_json()
        self.assertEqual(di["strength"], "high")
        self.assertGreaterEqual(di["session_handoff_count"], 50)
        self.assertTrue(di["anchor_docs"])
        self.assertTrue(di["audit_folders"])
        self.assertTrue(di["rag_corpus_present"])

        # Section renders + recommendation fires.
        _, text = _run_capture(self.tmpdir)
        self.assertIn("## Documentation Intelligence", text)
        self.assertIn("[high]", text)

        recs = json.loads(_run_capture(self.tmpdir, json_out=True)[1])["recommendations"]
        ids = [r["id"] for r in recs]
        self.assertIn("review-docs-context-first", ids)
        rec = next(r for r in recs if r["id"] == "review-docs-context-first")
        self.assertEqual(rec["confidence"], "high")
        self.assertIn("docs context layer", rec["suggestion"])

    def test_anchor_doc_paths_are_relative(self):
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "FOO_WHAT_IT_IS.md").write_text("# x\n", encoding="utf-8")
        (docs / "FOO_INVENTORY.md").write_text("# x\n", encoding="utf-8")
        di = self._di_from_json()
        self.assertEqual(set(di["anchor_docs"]), {
            "docs/FOO_WHAT_IT_IS.md",
            "docs/FOO_INVENTORY.md",
        })

    def test_rag_corpus_detected_with_jsonl(self):
        rag = self.tmpdir / ".rag"
        rag.mkdir()
        (rag / "corpus.jsonl").write_text('{"a":1}\n', encoding="utf-8")
        # Need at least one doc to avoid strength=none short-circuit
        # (we want to confirm rag_corpus_present is set independently).
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "x.md").write_text("# x\n", encoding="utf-8")

        di = self._di_from_json()
        self.assertTrue(di["rag_corpus_present"])
        self.assertEqual(di["rag_corpus_paths"], [".rag/corpus.jsonl"])


class TestRecommendations(_CwdSandbox):
    """Recommendation rules are deterministic, signal-driven, capped at 5,
    and carry stable IDs so a future override store can target them."""

    def _recs_from_json(self) -> list[dict]:
        _, out = _run_capture(self.tmpdir, json_out=True)
        data = json.loads(out)
        return data["recommendations"]

    def test_recommendation_shape_locked(self):
        # Seed enough signal to fire at least one recommendation.
        _seed_python_django(self.tmpdir)
        recs = self._recs_from_json()
        self.assertGreater(len(recs), 0)
        for rec in recs:
            self.assertEqual(set(rec.keys()), {"id", "suggestion", "why", "confidence"})
            self.assertIn(rec["confidence"], {"low", "medium", "high"})
            self.assertTrue(rec["id"])
            self.assertTrue(rec["suggestion"])
            self.assertTrue(rec["why"])

    def test_recommendations_capped_at_five(self):
        # Plant signals for every rule we have, then check the cap.
        _seed_python_django(self.tmpdir)
        # Tracked venv (high)
        venv = self.tmpdir / "venv_ml"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home=/usr\n", encoding="utf-8")
        # Tracked .env (high)
        (self.tmpdir / ".env").write_text("X=1\n", encoding="utf-8")
        # Multiple env templates (medium)
        for n in (".env.example", ".env.template", ".env.sample"):
            (self.tmpdir / n).write_text("# x\n", encoding="utf-8")
        # Oversized asset (medium)
        static = self.tmpdir / "core" / "static" / "img"
        static.mkdir(parents=True)
        (static / "big.png").write_bytes(b"\x89PNG" + b"\x00" * (6 * 1024 * 1024))
        # Stale doc (low)
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc) - timedelta(days=120)).date().isoformat()
        (self.tmpdir / "OLD.md").write_text(f"---\ndate: {old}\n---\n", encoding="utf-8")
        # Two workspaces with distinct frameworks (low: per-subsystem audit)
        backend = self.tmpdir / "backend"
        frontend = self.tmpdir / "frontend"
        backend.mkdir()
        frontend.mkdir()
        _seed_python_django(backend)
        _seed_nextjs(frontend)

        recs = self._recs_from_json()
        self.assertLessEqual(len(recs), 5)
        # And we still got a meaningful set, not an empty list.
        self.assertGreaterEqual(len(recs), 3)

    def test_high_severity_risk_emits_targeted_recommendation(self):
        venv = self.tmpdir / "venv_ml"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home=/usr\n", encoding="utf-8")

        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertIn("cleanup-tracked-venv", ids)
        rec = next(r for r in recs if r["id"] == "cleanup-tracked-venv")
        self.assertEqual(rec["confidence"], "high")
        # Suggestion phrasing ("Run a targeted cleanup audit ..."), not
        # a bare command.
        self.assertIn("targeted cleanup audit", rec["suggestion"].lower())

    def test_audit_workspace_missing_recommendation_fires_when_substantive(self):
        # Substantive: Django signals present, no docs/audit/ yet.
        _seed_python_django(self.tmpdir)
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertIn("scaffold-audit-workspace", ids)
        rec = next(r for r in recs if r["id"] == "scaffold-audit-workspace")
        self.assertEqual(rec["confidence"], "medium")
        self.assertIn("audit --write", rec["suggestion"])

    def test_audit_workspace_recommendation_skipped_for_empty_dir(self):
        # No manifests, no risks, no large file count -> no rec at all.
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertNotIn("scaffold-audit-workspace", ids)

    def test_audit_workspace_recommendation_skipped_when_workspace_exists(self):
        _seed_python_django(self.tmpdir)
        audit = self.tmpdir / "docs" / "audit"
        audit.mkdir(parents=True)
        (audit / "AUDIT_V1.md").write_text("# Filled audit\n", encoding="utf-8")
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertNotIn("scaffold-audit-workspace", ids)

    def test_multiple_env_templates_emits_consolidation_recommendation(self):
        for n in (".env.example", ".env.template", ".env.sample"):
            (self.tmpdir / n).write_text("# x\n", encoding="utf-8")
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertIn("consolidate-env-templates", ids)
        rec = next(r for r in recs if r["id"] == "consolidate-env-templates")
        self.assertEqual(rec["confidence"], "medium")
        self.assertIn("consolidate", rec["suggestion"].lower())

    def test_hot_files_recommendation_only_fires_when_files_are_large(self):
        # Tiny file -> no hotpath recommendation.
        (self.tmpdir / "small.txt").write_text("hi\n", encoding="utf-8")
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertNotIn("run-hotpath-leaderboard", ids)

        # Add a multi-MB file -> recommendation appears.
        (self.tmpdir / "fat.bin").write_bytes(b"\x00" * (2 * 1024 * 1024))
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertIn("run-hotpath-leaderboard", ids)
        rec = next(r for r in recs if r["id"] == "run-hotpath-leaderboard")
        self.assertEqual(rec["confidence"], "medium")

    def test_stale_doc_recommendation_is_low_confidence(self):
        from datetime import datetime, timedelta, timezone
        old = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()
        (self.tmpdir / "OLD.md").write_text(f"---\ndate: {old}\n---\n", encoding="utf-8")
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertIn("review-stale-docs", ids)
        rec = next(r for r in recs if r["id"] == "review-stale-docs")
        self.assertEqual(rec["confidence"], "low")

    def test_per_subsystem_recommendation_only_fires_with_two_framework_workspaces(self):
        # Single workspace -> no rec.
        backend = self.tmpdir / "backend"
        backend.mkdir()
        _seed_python_django(backend)
        recs = self._recs_from_json()
        self.assertNotIn("consider-per-subsystem-audit", [r["id"] for r in recs])

        # Add a second framework workspace -> rec fires.
        frontend = self.tmpdir / "frontend"
        frontend.mkdir()
        _seed_nextjs(frontend)
        recs = self._recs_from_json()
        ids = [r["id"] for r in recs]
        self.assertIn("consider-per-subsystem-audit", ids)

    def test_text_output_shows_confidence_and_id(self):
        # Use ``venv_ml/`` rather than plain ``venv/`` — the latter is in
        # ``cli.hotpath.IGNORED_DIR_NAMES`` and gets filtered before any
        # risk check sees it. ``venv_ml/`` still triggers ``tracked-venv``.
        venv = self.tmpdir / "venv_ml"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home=/usr\n", encoding="utf-8")
        _, out = _run_capture(self.tmpdir)
        self.assertIn("## Recommended next moves", out)
        # New formatting tags for confidence and id are visible.
        self.assertIn("[high]", out)
        self.assertIn("id:", out)
        self.assertIn("why:", out)
        # And the override-friendly framing line is present.
        self.assertIn("Override or ignore as needed", out)


if __name__ == "__main__":
    unittest.main()
