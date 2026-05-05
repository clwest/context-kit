"""Tests for the first milestone of the context-kit audit dashboard."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.server import (  # noqa: E402
    _OnboardingHandler,
    _audit_agent_handoff,
    _audit_fix_plan_markdown,
    _audit_risk_level,
    _audit_run,
    _audit_fix_plan,
    _audit_impact,
    _audit_handoff_markdown,
    _audit_translate_report,
    _render_audit_html,
    _render_html,
)


class TestAuditDispatch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_inspect_dispatch_uses_inspect_normalizer(self):
        fake = {
            "command": "inspect",
            "scope": "frontend",
            "status": "ok",
            "summary": {"tracked_files": 1},
            "findings": [],
            "warnings": [],
            "generated_at": "2026-05-04T00:00:00+00:00",
        }
        with patch("cli.server._normalize_audit_inspect", return_value=fake) as mock:
            report = _audit_run(self.project, {
                "command": "inspect",
                "scope": "frontend",
                "depth": 3,
                "include_history": True,
                "include_related": True,
            })
        mock.assert_called_once()
        self.assertEqual(report["command"], "inspect")
        self.assertEqual(report["scope"], "frontend")

    def test_verify_dispatch_uses_verify_normalizer(self):
        fake = {
            "command": "verify",
            "scope": None,
            "status": "warning",
            "summary": {"total": 1},
            "findings": [
                {
                    "id": "claim-1",
                    "title": "Claim needs review",
                    "status": "DOC_ONLY",
                }
            ],
            "warnings": ["DOC_ONLY: Claim needs review"],
            "generated_at": "2026-05-04T00:00:00+00:00",
        }
        with patch("cli.server._normalize_audit_verify", return_value=fake) as mock:
            report = _audit_run(self.project, {
                "command": "verify",
                "include_archive": True,
                "all_docs": True,
            })
        mock.assert_called_once()
        self.assertEqual(report["command"], "verify")
        self.assertEqual(report["status"], "warning")

    def test_coverage_dispatch_uses_coverage_normalizer(self):
        fake = {
            "command": "coverage",
            "scope": "frontend",
            "status": "warning",
            "summary": {"unknown_files": 1},
            "findings": [],
            "warnings": [],
            "generated_at": "2026-05-04T00:00:00+00:00",
        }
        with patch("cli.server._normalize_audit_coverage", return_value=fake) as mock:
            report = _audit_run(self.project, {
                "command": "coverage",
                "scope": "frontend",
            })
        mock.assert_called_once()
        self.assertEqual(report["command"], "coverage")

    def test_behavior_dispatch_uses_behavior_normalizer(self):
        fake = {
            "command": "behavior",
            "scope": "frontend",
            "status": "warning",
            "summary": {"files_with_signals": 1},
            "findings": [],
            "warnings": [],
            "generated_at": "2026-05-04T00:00:00+00:00",
        }
        with patch("cli.server._normalize_audit_behavior", return_value=fake) as mock:
            report = _audit_run(self.project, {
                "command": "behavior",
                "scope": "frontend",
            })
        mock.assert_called_once()
        self.assertEqual(report["command"], "behavior")

    def test_connections_dispatch_uses_connections_normalizer(self):
        fake = {
            "command": "connections",
            "scope": "frontend",
            "status": "warning",
            "summary": {"missing_backend_endpoints": 1},
            "findings": [],
            "warnings": [],
            "generated_at": "2026-05-04T00:00:00+00:00",
        }
        with patch("cli.server._normalize_audit_connections", return_value=fake) as mock:
            report = _audit_run(self.project, {
                "command": "connections",
                "scope": "frontend",
            })
        mock.assert_called_once()
        self.assertEqual(report["command"], "connections")

    def test_doctor_dispatch_uses_doctor_normalizer(self):
        fake = {
            "command": "doctor",
            "scope": None,
            "status": "warning",
            "summary": {"warning": 1},
            "findings": [],
            "warnings": [],
            "generated_at": "2026-05-04T00:00:00+00:00",
        }
        with patch("cli.server._normalize_audit_doctor", return_value=fake) as mock:
            report = _audit_run(self.project, {
                "command": "doctor",
            })
        mock.assert_called_once()
        self.assertEqual(report["command"], "doctor")

    def test_invalid_command_is_rejected(self):
        with self.assertRaises(ValueError):
            _audit_run(self.project, {"command": "bogus"})

    def test_invalid_scope_is_rejected_for_inspect(self):
        with self.assertRaises(ValueError):
            _audit_run(self.project, {"command": "inspect", "scope": "bogus"})

    def test_verify_rejects_scope(self):
        with self.assertRaises(ValueError):
            _audit_run(self.project, {"command": "verify", "scope": "frontend"})

    def test_fix_plan_derives_ordered_steps_and_prompt(self):
        report = {
            "command": "inspect",
            "scope": "frontend",
            "findings": [
                {
                    "title": "Second issue",
                    "severity": "medium",
                    "recommendation": "Fix the second issue.",
                    "details": "b.py: second",
                    "impact": "Medium impact: likely to create a visible or operational gap.",
                },
                {
                    "title": "First issue",
                    "severity": "high",
                    "recommendation": "Fix the first issue.",
                    "details": "a.py: first",
                    "impact": "High impact: likely to block correct operation or create user-facing breakage.",
                },
            ],
        }
        fix_plan = _audit_fix_plan(report)
        self.assertEqual(fix_plan["summary"]["critical_count"], 2)
        self.assertEqual(fix_plan["steps"][0]["title"], "First issue")
        self.assertIn("Codex", fix_plan["codex_prompt"])
        self.assertIn("highest-priority issues", fix_plan["codex_prompt"])

    def test_impact_labels_are_derived_from_command_context(self):
        self.assertIn("High impact", _audit_impact({"severity": "high"}, "inspect"))
        self.assertIn("Medium impact", _audit_impact({"status": "DOC_ONLY"}, "verify"))
        self.assertIn(
            "High impact",
            _audit_impact(
                {
                    "category": "missing_target",
                    "title": "Missing backend endpoint",
                    "details": "No backend route matched /api/demo",
                },
                "connections",
            ),
        )
        self.assertIn(
            "Medium impact",
            _audit_impact({"title": "Fallback metadata", "details": "fallback path"}, "inspect"),
        )
        self.assertIn(
            "Low impact",
            _audit_impact({"category": "unknown_dynamic_reference", "title": "Unknown dynamic reference"}, "behavior"),
        )
        self.assertIn(
            "Advisory impact",
            _audit_impact(
                {"category": "orphaned_route", "route_role": "admin", "title": "Orphaned backend route"},
                "connections",
            ),
        )

    def test_fix_plan_markdown_export_contains_sections(self):
        report = {
            "command": "full",
            "scope": "frontend",
            "generated_at": "2026-05-04T00:00:00+00:00",
            "critical_issues": [
                {
                    "title": "Missing backend endpoint",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "details": "frontend/app.py: /api/demo",
                }
            ],
            "fix_plan": {
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "evidence": "frontend/app.py: /api/demo",
                        "action": "Add the missing route.",
                    }
                ],
                "codex_prompt": "You are Codex helping fix the highest-priority issues.\n",
            },
        }
        md = _audit_fix_plan_markdown(report)
        self.assertIn("Critical Issues", md)
        self.assertIn("Fix Order", md)
        self.assertIn("Evidence", md)
        self.assertIn("Codex Prompt", md)
        self.assertIn("frontend/app.py: /api/demo", md)

    def test_handoff_translation_includes_prompts_and_guardrails(self):
        report = {
            "command": "inspect",
            "scope": "frontend",
            "path": "/tmp/demo",
            "generated_at": "2026-05-04T00:00:00+00:00",
            "findings": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "critical_issues": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "fix_plan": {
                "summary": {"critical_count": 1, "command": "inspect", "scope": "frontend"},
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "action": "Implement the endpoint.",
                        "evidence": "frontend/app.py: /api/demo",
                    }
                ],
                "codex_prompt": "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.\n",
            },
        }
        translated = _audit_translate_report(report, "founder")
        handoff = _audit_agent_handoff(translated)
        self.assertEqual(handoff["repo_path"], "/tmp/demo")
        self.assertEqual(handoff["audit_command"], "inspect")
        self.assertEqual(handoff["critical_count"], 1)
        self.assertIn("Codex Prompt", handoff["markdown"])
        self.assertIn("Claude Code Prompt", handoff["markdown"])
        self.assertIn("AGENTS.md Prompt", handoff["markdown"])
        self.assertIn("Close the loop before you leave", handoff["agents_prompt"])
        self.assertIn("context-kit verify", handoff["agents_prompt"])
        self.assertIn("handoff note", handoff["agents_prompt"])
        self.assertIn("do not commit unless instructed", handoff["markdown"].lower())
        self.assertIn("run tests after making changes", handoff["markdown"].lower())
        self.assertIn("read `00-start-next-session.md` first", handoff["markdown"].lower())
        self.assertIn("context-kit doctor", handoff["agents_prompt"])
        self.assertIn("context-kit orient", handoff["agents_prompt"])
        self.assertIn("highest-priority", handoff["codex_prompt"])
        self.assertIn("read-only context-kit audit", handoff["claude_prompt"])

    def test_handoff_markdown_export_contains_sections(self):
        report = {
            "command": "inspect",
            "scope": "frontend",
            "path": "/tmp/demo",
            "generated_at": "2026-05-04T00:00:00+00:00",
            "findings": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "critical_issues": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "fix_plan": {
                "summary": {"critical_count": 1, "command": "inspect", "scope": "frontend"},
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "action": "Implement the endpoint.",
                        "evidence": "frontend/app.py: /api/demo",
                    }
                ],
                "codex_prompt": "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.\n",
            },
            "translation": {
                "critical_issues": [
                    {
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "details": "frontend/app.py: /api/demo",
                        "explanation": "The client call has no matching backend route.",
                    }
                ],
                "fix_plan": {
                    "steps": [
                        {
                            "step": 1,
                            "title": "Missing backend endpoint",
                            "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                            "action": "Implement the endpoint.",
                            "evidence": "frontend/app.py: /api/demo",
                        }
                    ],
                    "codex_prompt": "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.\n",
                },
            },
        }
        md = _audit_handoff_markdown(report)
        self.assertIn("Agent Handoff", md)
        self.assertIn("Repo path", md)
        self.assertIn("Risk level", md)
        self.assertIn("Critical Issues", md)
        self.assertIn("Fix Plan", md)
        self.assertIn("Codex Prompt", md)
        self.assertIn("Claude Code Prompt", md)
        self.assertIn("AGENTS.md Prompt", md)
        self.assertIn("Close the loop before you leave", md)

    def test_risk_level_calculation_changes_with_signals(self):
        low = {"command": "inspect", "findings": [], "critical_issues": []}
        medium = {
            "command": "inspect",
            "findings": [
                {
                    "title": "Missing backend endpoint",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High technical impact: the client references a backend route that the server does not expose.",
                }
            ],
        }
        high = {
            "command": "verify",
            "findings": [
                {
                    "title": "Deployment config failure",
                    "category": "config",
                    "details": "deployment/config.yaml: failure detected",
                    "impact": "High technical impact: failure metadata suggests a broken or missing integration.",
                },
                {
                    "title": "Fallback path degraded",
                    "category": "runtime",
                    "details": "fallback path degraded",
                    "impact": "Medium technical impact: the current path looks degraded or may be masking a failure.",
                },
            ],
        }
        self.assertEqual(_audit_risk_level(low), "Low")
        self.assertEqual(_audit_risk_level(medium), "Medium")
        self.assertEqual(_audit_risk_level(high), "High")

    def test_audience_translation_exists_for_each_audience(self):
        report = {
            "command": "connections",
            "scope": "frontend",
            "findings": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "critical_issues": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "fix_plan": {
                "summary": {"critical_count": 1, "command": "connections", "scope": "frontend"},
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "action": "Implement the endpoint.",
                        "evidence": "frontend/app.py: /api/demo",
                    }
                ],
                "codex_prompt": "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.\n",
            },
        }
        for audience in ("developer", "founder", "business"):
            with self.subTest(audience=audience):
                translated = _audit_translate_report(report, audience)
                self.assertEqual(translated["audience"], audience)
                self.assertIn("translation", translated)
                self.assertEqual(translated["findings"], report["findings"])
                self.assertEqual(translated["critical_issues"], report["critical_issues"])
                self.assertEqual(translated["fix_plan"], report["fix_plan"])
                self.assertEqual(translated["translation"]["audience"], audience)
                self.assertEqual(translated["translation"]["summary"]["critical_count"], 1)
                self.assertIn("executive_summary", translated["translation"])
                self.assertIn("risk_level", translated["translation"]["executive_summary"])
                self.assertIn("explanation", translated["translation"]["critical_issues"][0])
                self.assertIn("codex_prompt", translated["translation"]["fix_plan"])
                self.assertIn("agent_handoff", translated["translation"])
                self.assertNotEqual(
                    translated["translation"]["fix_plan"]["codex_prompt"],
                    report["fix_plan"]["codex_prompt"],
                )

    def test_translation_changes_wording_only(self):
        report = {
            "command": "connections",
            "scope": "frontend",
            "findings": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "critical_issues": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "fix_plan": {
                "summary": {"critical_count": 1, "command": "connections", "scope": "frontend"},
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "action": "Implement the endpoint.",
                        "evidence": "frontend/app.py: /api/demo",
                    }
                ],
                "codex_prompt": "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.\n",
            },
        }
        dev = _audit_translate_report(report, "developer")
        founder = _audit_translate_report(report, "founder")
        business = _audit_translate_report(report, "business")
        self.assertNotEqual(dev["translation"]["critical_issues"][0]["impact"], founder["translation"]["critical_issues"][0]["impact"])
        self.assertNotEqual(founder["translation"]["critical_issues"][0]["impact"], business["translation"]["critical_issues"][0]["impact"])
        self.assertEqual(dev["findings"], report["findings"])
        self.assertEqual(founder["findings"], report["findings"])
        self.assertEqual(business["findings"], report["findings"])
        self.assertNotEqual(dev["translation"]["executive_summary"]["description"], founder["translation"]["executive_summary"]["description"])
        self.assertNotEqual(founder["translation"]["executive_summary"]["description"], business["translation"]["executive_summary"]["description"])

    def test_summary_translation_includes_risk_level(self):
        report = {
            "command": "connections",
            "scope": "frontend",
            "findings": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "critical_issues": [
                {
                    "id": "missing-target:/api/demo",
                    "title": "Missing backend endpoint",
                    "severity": "high",
                    "status": "high",
                    "category": "missing_target",
                    "details": "frontend/app.py: /api/demo",
                    "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                    "recommendation": "Implement the endpoint.",
                }
            ],
            "fix_plan": {
                "summary": {"critical_count": 1, "command": "connections", "scope": "frontend"},
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing backend endpoint",
                        "impact": "High impact: a backend endpoint is referenced by clients but no matching route was found.",
                        "action": "Implement the endpoint.",
                        "evidence": "frontend/app.py: /api/demo",
                    }
                ],
                "codex_prompt": "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.\n",
            },
        }
        translated = _audit_translate_report(report, "founder")
        self.assertIn("executive_summary", translated["translation"])
        self.assertEqual(translated["translation"]["executive_summary"]["risk_level"], "Medium")
        self.assertIn("product risk summary", translated["translation"]["executive_summary"]["description"])
        self.assertEqual(translated["risk_level"], "Medium")


class TestLiveAuditServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.cwd = Path(cls._tmp.name).resolve()
        (cls.cwd / "00-START-NEXT-SESSION.md").write_text("hi", encoding="utf-8")

        cls.server = HTTPServer(("127.0.0.1", 0), _OnboardingHandler)
        cls.server.onboarding_html = _render_html(cls.cwd, "http://test/")  # type: ignore[attr-defined]
        cls.server.audit_html = _render_audit_html(cls.cwd, "http://test/audit")  # type: ignore[attr-defined]
        cls.server.audit_report = None  # type: ignore[attr-defined]
        cls.server.cwd = cls.cwd  # type: ignore[attr-defined]

        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def _get(self, path: str) -> tuple[int, str]:
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def _post_json(self, path: str, payload: dict) -> tuple[int, str]:
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def test_audit_page_returns_200(self):
        status, body = self._get("/audit")
        self.assertEqual(status, 200)
        self.assertIn("AgentReality Audit Report", body)
        self.assertIn("Executive Summary", body)
        self.assertIn("Risk Level", body)
        self.assertIn("Critical Issues", body)
        self.assertIn("Generate Fix Plan", body)
        self.assertIn("Run Full Audit", body)
        self.assertIn("Fix Plan", body)
        self.assertIn("Agent Handoff", body)
        self.assertIn("Copy Codex Prompt", body)
        self.assertIn("Copy Claude Prompt", body)
        self.assertIn("Download Handoff.md", body)
        self.assertIn("Supporting Findings", body)

    def test_audit_state_reports_supported_commands_and_scopes(self):
        status, body = self._get("/api/audit/state")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["supported_commands"], ["inspect", "coverage", "behavior", "connections", "verify", "doctor"])
        self.assertEqual(data["supported_audiences"], ["developer", "founder", "business"])
        self.assertIn("frontend", data["supported_scopes"])
        self.assertEqual(data["default_path"], ".")

    def test_audit_report_requires_a_prior_run(self):
        status, body = self._get("/api/audit/report?format=json")
        self.assertEqual(status, 404)
        self.assertIn("no audit report", body.lower())

    def test_audit_run_and_report_round_trip(self):
        fake_report = {
            "command": "inspect",
            "scope": "frontend",
            "status": "warning",
            "summary": {
                "tracked_files": 2,
                "total_bytes": 12,
                "primary_stack": {"languages": ["python"]},
                "risk_count": 1,
                "recommendation_count": 1,
            },
            "findings": [
                {
                    "id": "risk-1",
                    "title": "Missing route wiring",
                    "severity": "medium",
                    "status": "medium",
                    "details": "frontend/app.py: /api/demo",
                    "evidence": ["frontend/app.py: /api/demo"],
                    "recommendation": "Wire the route.",
                    "impact": "Medium impact: likely to create a visible or operational gap.",
                }
            ],
            "critical_issues": [
                {
                    "title": "Missing route wiring",
                    "impact": "Medium impact: likely to create a visible or operational gap.",
                    "details": "frontend/app.py: /api/demo",
                }
            ],
            "warnings": ["Wire the route."],
            "generated_at": "2026-05-04T00:00:00+00:00",
            "raw_json": None,
            "fix_plan": {
                "summary": {
                    "critical_count": 1,
                    "command": "inspect",
                    "scope": "frontend",
                },
                "steps": [
                    {
                        "step": 1,
                        "title": "Missing route wiring",
                        "impact": "Medium impact: likely to create a visible or operational gap.",
                        "action": "Wire the route.",
                        "evidence": "frontend/app.py: /api/demo",
                    }
                ],
                "codex_prompt": "You are helping fix the highest-priority issues from a read-only context-kit audit.\n",
            },
        }
        fake_report["agent_handoff"] = _audit_agent_handoff(_audit_translate_report(fake_report, None))
        with patch("cli.server._audit_run", return_value=fake_report):
            status, body = self._post_json("/api/audit/run", {
                "path": ".",
                "command": "inspect",
                "scope": "frontend",
                "depth": 2,
                "include_history": False,
                "include_related": False,
            })
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["command"], "inspect")
        self.assertEqual(data["summary"]["risk_count"], 1)
        self.assertEqual(data["findings"][0]["title"], "Missing route wiring")
        self.assertIn("impact", data["findings"][0])
        self.assertIn("fix_plan", data)
        self.assertEqual(data["fix_plan"]["summary"]["critical_count"], 1)

        status, body = self._get("/api/audit/state")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual(state["last_run"]["command"], "inspect")

        status, body = self._get("/api/audit/report?format=json")
        self.assertEqual(status, 200)
        report = json.loads(body)
        self.assertEqual(report["command"], "inspect")
        self.assertEqual(report["findings"][0]["id"], "risk-1")
        self.assertEqual(report["fix_plan"]["steps"][0]["step"], 1)
        self.assertIn("agent_handoff", report)
        self.assertIn("Codex Prompt", report["agent_handoff"]["markdown"])
        self.assertIn("Claude Code Prompt", report["agent_handoff"]["markdown"])

        status, body = self._get("/api/audit/report?format=fix-plan-md")
        self.assertEqual(status, 200)
        self.assertIn("Critical Issues", body)
        self.assertIn("Fix Order", body)
        self.assertIn("Codex Prompt", body)
        self.assertIn("Evidence", body)

        status, body = self._get("/api/audit/report?format=handoff-md")
        self.assertEqual(status, 200)
        self.assertIn("Agent Handoff", body)
        self.assertIn("Repo path", body)
        self.assertIn("AGENTS.md Prompt", body)
        self.assertIn("Claude Code Prompt", body)
        self.assertIn("Codex Prompt", body)

    def test_unsupported_command_is_rejected(self):
        status, body = self._post_json("/api/audit/run", {
            "path": ".",
            "command": "bogus",
        })
        self.assertEqual(status, 400)
        self.assertIn("unknown audit command", body.lower())

    def test_new_audit_commands_run_via_http(self):
        fake_reports = {
            "coverage": {
                "command": "coverage",
                "scope": "frontend",
                "status": "warning",
                "summary": {"unknown_files": 1},
                "findings": [],
                "critical_issues": [],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 0}, "steps": [], "codex_prompt": "prompt"},
            },
            "behavior": {
                "command": "behavior",
                "scope": "frontend",
                "status": "warning",
                "summary": {"files_with_signals": 1},
                "findings": [],
                "critical_issues": [],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 0}, "steps": [], "codex_prompt": "prompt"},
            },
            "connections": {
                "command": "connections",
                "scope": "frontend",
                "status": "warning",
                "summary": {"missing_backend_endpoints": 1},
                "findings": [],
                "critical_issues": [],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 0}, "steps": [], "codex_prompt": "prompt"},
            },
            "doctor": {
                "command": "doctor",
                "scope": None,
                "status": "warning",
                "summary": {"warning": 1},
                "findings": [],
                "critical_issues": [],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 0}, "steps": [], "codex_prompt": "prompt"},
            },
        }
        patchers = [
            patch("cli.server._normalize_audit_coverage", return_value=fake_reports["coverage"]),
            patch("cli.server._normalize_audit_behavior", return_value=fake_reports["behavior"]),
            patch("cli.server._normalize_audit_connections", return_value=fake_reports["connections"]),
            patch("cli.server._normalize_audit_doctor", return_value=fake_reports["doctor"]),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        cases = [
            ("coverage", {"command": "coverage", "scope": "frontend"}),
            ("behavior", {"command": "behavior", "scope": "frontend"}),
            ("connections", {"command": "connections", "scope": "frontend"}),
            ("doctor", {"command": "doctor"}),
        ]
        for command, payload in cases:
            with self.subTest(command=command):
                status, body = self._post_json("/api/audit/run", payload)
                self.assertEqual(status, 200)
                data = json.loads(body)
                self.assertEqual(data["command"], command)
                self.assertIn("fix_plan", data)

    def test_run_full_audit_response_shape(self):
        patchers = [
            patch("cli.server._normalize_audit_inspect", return_value={
                "command": "inspect",
                "scope": "frontend",
                "status": "warning",
                "summary": {"risk_count": 1},
                "findings": [{"title": "Inspect issue", "severity": "medium", "status": "medium"}],
                "critical_issues": [{"title": "Inspect issue", "impact": "Medium impact"}],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 1}, "steps": [{"step": 1, "title": "Inspect issue", "impact": "Medium impact", "action": "Fix it.", "evidence": "evidence"}], "codex_prompt": "prompt"},
            }),
            patch("cli.server._normalize_audit_coverage", return_value={
                "command": "coverage",
                "scope": "frontend",
                "status": "warning",
                "summary": {"unknown_files": 1},
                "findings": [{"title": "Coverage issue", "severity": "medium", "status": "medium"}],
                "critical_issues": [{"title": "Coverage issue", "impact": "Medium impact"}],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 1}, "steps": [{"step": 1, "title": "Coverage issue", "impact": "Medium impact", "action": "Fix it.", "evidence": "evidence"}], "codex_prompt": "prompt"},
            }),
            patch("cli.server._normalize_audit_behavior", return_value={
                "command": "behavior",
                "scope": "frontend",
                "status": "warning",
                "summary": {"files_with_signals": 1},
                "findings": [{"title": "Behavior issue", "severity": "medium", "status": "medium"}],
                "critical_issues": [{"title": "Behavior issue", "impact": "Medium impact"}],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 1}, "steps": [{"step": 1, "title": "Behavior issue", "impact": "Medium impact", "action": "Fix it.", "evidence": "evidence"}], "codex_prompt": "prompt"},
            }),
            patch("cli.server._normalize_audit_connections", return_value={
                "command": "connections",
                "scope": "frontend",
                "status": "warning",
                "summary": {"missing_backend_endpoints": 1},
                "findings": [{"title": "Connection issue", "severity": "high", "status": "high"}],
                "critical_issues": [{"title": "Connection issue", "impact": "High impact"}],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 1}, "steps": [{"step": 1, "title": "Connection issue", "impact": "High impact", "action": "Fix it.", "evidence": "evidence"}], "codex_prompt": "prompt"},
            }),
            patch("cli.server._normalize_audit_verify", return_value={
                "command": "verify",
                "scope": None,
                "status": "warning",
                "summary": {"by_status": {"VERIFIED": 1, "DOC_ONLY": 0, "CONFLICT": 0, "UNKNOWN": 0}},
                "findings": [{"title": "Verify issue", "status": "DOC_ONLY"}],
                "critical_issues": [{"title": "Verify issue", "impact": "Medium impact"}],
                "warnings": [],
                "generated_at": "2026-05-04T00:00:00+00:00",
                "fix_plan": {"summary": {"critical_count": 1}, "steps": [{"step": 1, "title": "Verify issue", "impact": "Medium impact", "action": "Fix it.", "evidence": "evidence"}], "codex_prompt": "prompt"},
            }),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

        status, body = self._post_json("/api/audit/run", {
            "path": ".",
            "command": "full",
            "scope": "frontend",
        })
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["command"], "full")
        self.assertIn("commands", data["summary"])
        self.assertIn("inspect", data["summary"]["commands"])
        self.assertEqual(len(data["findings"]), 5)
        self.assertIn("fix_plan", data)
        self.assertGreaterEqual(data["fix_plan"]["summary"]["critical_count"], 1)


if __name__ == "__main__":
    unittest.main()
