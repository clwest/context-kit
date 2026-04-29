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


def _inspect_args(path, *, json_out=False, depth=2):
    return argparse.Namespace(
        command="inspect",
        path=str(path),
        json=json_out,
        depth=depth,
    )


def _run_capture(path, *, json_out=False) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_inspect(_inspect_args(path, json_out=json_out))
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

    def test_tracked_build_artifact_dir_flagged(self):
        _, out = _run_capture(self.tmpdir)
        self.assertIn("[tracked-build-artifacts]", out)
        self.assertIn("__pycache__", out)


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
            "head",
            "counts",
            "primary_stack",
            "subsystems",
            "entry_points",
            "framework_signals",
            "hot_files",
            "risks",
            "stale_docs",
            "recommendations",
        }
        self.assertEqual(set(data.keys()), expected)

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
