"""Tests for the deterministic ``context-kit capabilities`` command."""

from __future__ import annotations

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.capabilities import run_capabilities  # noqa: E402
from cli.bootstrap import run_init  # noqa: E402


def _capabilities_args(
    project=None,
    *,
    output=None,
    scope=None,
    include_related=False,
    include_history=False,
    format="full",
    include_tests=False,
    include_detectors=False,
):
    return argparse.Namespace(
        command="capabilities",
        project=str(project) if project is not None else None,
        output=str(output) if output is not None else None,
        scope=scope,
        include_related=include_related,
        include_history=include_history,
        format=format,
        include_tests=include_tests,
        include_detectors=include_detectors,
    )


def _seed_capability_project(root: Path) -> None:
    run_init(
        argparse.Namespace(
            command="init",
            name="Cap App",
            target=str(root),
            with_scaffold=False,
            force=False,
            quiet=True,
        )
    )
    backend = root / "backend"
    app_dir = backend / "app"
    backend.mkdir()
    app_dir.mkdir()
    (backend / "requirements.txt").write_text("fastapi==0.115.0\nsqlalchemy==2.0.0\n", encoding="utf-8")
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
        "@app.post('/api/sessions/{session_id}/chat')\n"
        "def session_chat(): return {'ok': True}\n"
        "@app.post('/api/checkout')\n"
        "def checkout(): return {'ok': True}\n"
        "@app.post('/api/webhook')\n"
        "def webhook(): return {'ok': True}\n"
        "Base = declarative_base()\n"
        "class Thing(Base):\n"
        "    pass\n",
        encoding="utf-8",
    )
    (app_dir / "tiers.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class TierConfig:\n"
        "    allowed_modes = ['basic', 'pro']\n"
        "    max_sessions_per_day = 10\n"
        "    max_response_tokens = 2000\n"
        "    max_messages_per_session = 25\n"
        "TIERS = {'free': TierConfig()}\n",
        encoding="utf-8",
    )
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "CAP_APP_WHAT_IT_IS.md").write_text(
        "# What it is\nThis doc says the app manages a project and has documentation.\n",
        encoding="utf-8",
    )


class TestCapabilitiesCommand(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "cap-app"
        _seed_capability_project(self.project)

    def tearDown(self):
        self._tmp.cleanup()

    def test_outputs_route_and_tier_evidence(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(_capabilities_args(self.project))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("# context-kit capabilities", out)
        self.assertIn("### auth", out)
        self.assertIn("Capability label is heuristic.", out)
        self.assertIn("Meaning: Detected route group for auth-related endpoints.", out)
        self.assertIn("Confidence: high", out)
        self.assertIn("Reason: Explicit register/login/current-user routes detected.", out)
        self.assertIn("@app.post('/api/auth/register')", out)
        self.assertRegex(out, r"backend/main\.py:\d+ @app\.post\('/api/auth/register'\)")
        self.assertIn("### stripe/checkout", out)
        self.assertIn("Meaning: Detected route group for Stripe checkout endpoints.", out)
        self.assertIn("Confidence: medium", out)
        self.assertIn("Reason: Stripe checkout route detected, but payment flow completion is not verified.", out)
        self.assertRegex(out, r"backend/main\.py:\d+ @app\.post\('/api/checkout'\)")
        self.assertIn("### stripe/webhook", out)
        self.assertIn("Meaning: Detected route group for Stripe webhook endpoints.", out)
        self.assertRegex(out, r"backend/main\.py:\d+ @app\.post\('/api/webhook'\)")
        self.assertIn("### tier_config", out)
        self.assertIn("allowed_modes", out)
        self.assertIn("max_sessions_per_day", out)
        self.assertIn("backend/app/tiers.py", out)
        self.assertIn("Confidence: medium", out)
        self.assertIn("Reason: Config evidence suggests tier limits, allowed modes, token limits, and session/message enforcement, but runtime enforcement is not verified.", out)
        self.assertIn("command_name: `connections`", out)
        self.assertIn("command_type: CLI command", out)
        self.assertIn("detected_entrypoint:", out)
        self.assertIn("literal description: The repo exposes a CLI command named `connections`.", out)
        self.assertIn("command_name: `recommend-stack`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `recommend-stack`.", out)
        self.assertIn("command_name: `verify`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `verify`.", out)
        self.assertIn("command_name: `exec`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `exec`.", out)
        self.assertIn("command_name: `codex`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `codex`.", out)

    def test_omits_orientation_only_claims(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(_capabilities_args(self.project))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertNotIn("PROJECT ORIENTATION", out)
        self.assertNotIn("docs/CAP_APP_WHAT_IT_IS.md", out)
        self.assertNotIn("manages a project and has documentation", out)

    def test_compact_output_excludes_models_and_base_model_evidence(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(_capabilities_args(self.project, format="compact"))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Compact capability summary derived from inspect structured implementation facts.", out)
        self.assertIn("## Recommended capability shortlist", out)
        self.assertIn("### auth", out)
        self.assertIn("### sessions/chat", out)
        self.assertIn("### stripe/checkout", out)
        self.assertIn("### tier_config", out)
        self.assertIn("### tier_config", out)
        self.assertNotIn("### data/models", out)
        self.assertNotIn("Base = declarative_base()", out)
        self.assertNotIn("class Thing(Base):", out)
        self.assertIn("Best evidence:", out)
        self.assertLess(out.index("## Recommended capability shortlist"), out.index("### auth"))

    def test_shortlist_format_includes_shortlist_and_not_full_list(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(_capabilities_args(self.project, format="shortlist"))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Shortlist capability summary derived from inspect structured implementation facts.", out)
        self.assertIn("## Capability answer contract", out)
        self.assertIn("## Recommended capability shortlist", out)
        self.assertNotIn("## Capability summary", out.split("## Recommended capability shortlist", 1)[1])
        self.assertNotIn("### data/models", out)
        self.assertNotIn("Base = declarative_base()", out)
        self.assertNotIn("class Thing(Base):", out)
        self.assertIn("### auth", out)
        self.assertIn("### sessions/chat", out)
        self.assertIn("### stripe/checkout", out)
        self.assertIn("### tier_config", out)

    def test_repo_root_excludes_test_fixture_evidence_by_default(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(_capabilities_args(REPO_ROOT, format="shortlist"))

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("### orient", out)
        self.assertIn("### inspect", out)
        self.assertIn("### capabilities", out)
        self.assertIn("### chat", out)
        self.assertRegex(out, r"context_kit\.py:\d+ if args\.command == \"orient\":")
        self.assertRegex(out, r"context_kit\.py:\d+ if args\.command == \"inspect\":")
        self.assertRegex(out, r"cli/chat\.py:\d+ def run_chat\(args: argparse\.Namespace\) -> int:")
        self.assertIn("### connections", out)
        self.assertIn("command_name: `connections`", out)
        self.assertIn("command_type: CLI command", out)
        self.assertIn("literal description: The repo exposes a CLI command named `connections`.", out)
        self.assertIn("### recommend-stack", out)
        self.assertIn("command_name: `recommend-stack`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `recommend-stack`.", out)
        self.assertIn("### verify", out)
        self.assertIn("command_name: `verify`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `verify`.", out)
        self.assertIn("### exec", out)
        self.assertIn("command_name: `exec`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `exec`.", out)
        self.assertIn("### codex", out)
        self.assertIn("command_name: `codex`", out)
        self.assertIn("literal description: The repo exposes a CLI command named `codex`.", out)
        self.assertNotIn("### auth", out)
        self.assertNotIn("### sessions/chat", out)
        self.assertNotIn("### founder_projects/export", out)
        self.assertNotIn("### stripe/checkout", out)
        self.assertNotIn("### stripe/webhook", out)
        self.assertNotIn("### tier_config", out)
        self.assertNotIn("facilitates collaboration between components/modules/ideas", out.lower())
        self.assertNotIn("the repo has architecture intelligence", out.lower())
        self.assertNotIn("minimal human intervention", out.lower())
        self.assertNotIn("streamline your development workflow", out.lower())
        self.assertNotIn("enhance collaboration", out.lower())
        self.assertNotIn("productivity gains", out.lower())
        self.assertNotIn("Test/fixture evidence — not implementation.", out)
        self.assertNotIn("Detector logic evidence — not project implementation.", out)

    def test_include_tests_labels_test_fixture_evidence(self):
        args = _capabilities_args(REPO_ROOT, format="shortlist")
        args.include_tests = True
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(args)

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("### orient", out)
        self.assertIn("### inspect", out)
        self.assertIn("Test/fixture evidence — not implementation.", out)
        self.assertIn("### auth", out)
        self.assertIn("### sessions/chat", out)
        self.assertIn("### founder_projects/export", out)
        self.assertIn("### stripe/checkout", out)
        self.assertIn("### stripe/webhook", out)

    def test_include_detectors_labels_detector_logic_evidence(self):
        args = _capabilities_args(REPO_ROOT, format="shortlist", include_detectors=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(args)

        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("### orient", out)
        self.assertIn("### inspect", out)
        self.assertIn("### tier_config", out)
        self.assertIn("Detector logic evidence — not project implementation.", out)
        self.assertNotIn("### auth", out)
        self.assertNotIn("### sessions/chat", out)

    def test_output_file_is_written(self):
        output = self.tmpdir / "capabilities.md"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = run_capabilities(_capabilities_args(self.project, output=output))

        self.assertEqual(rc, 0)
        self.assertTrue(output.is_file())
        text = output.read_text(encoding="utf-8")
        self.assertIn("### auth", text)
        self.assertIn("### tier_config", text)
