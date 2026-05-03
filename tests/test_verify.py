"""Tests for the context-kit `verify` subcommand."""

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

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.verify import END_MARKER, START_MARKER, run_verify  # noqa: E402


def _args(
    project: Path,
    *,
    json_: bool = False,
    write: bool = False,
    include_archive: bool = False,
    all_docs: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        command="verify",
        path=str(project),
        json=json_,
        write=write,
        include_archive=include_archive,
        all_docs=all_docs,
    )


def _capture(args: argparse.Namespace) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_verify(args)
    return rc, buf.getvalue()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_verify_config(project: Path, content: str) -> None:
    _write(project / ".context-kit" / "verify.yaml", content)


class VerifyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()


class TestVerifyJsonSchema(VerifyTestCase):
    def test_json_shape(self):
        _write(self.project / "README.md", "- agents: 74\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(sorted(data.keys()), ["canonical_docs_used", "config_path", "findings", "generated_at", "repo", "summary"])
        self.assertIn("total", data["summary"])
        self.assertIn("by_status", data["summary"])
        self.assertIsInstance(data["findings"], list)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        for key in ("id", "title", "status", "category", "evidence", "evidence_by_scope", "details", "recommendation"):
            self.assertIn(key, finding)
        self.assertIsNone(data["config_path"])
        self.assertFalse(data["canonical_docs_used"])
        self.assertIn("active_docs", finding["evidence_by_scope"])


class TestVerifyDjangoSettings(VerifyTestCase):
    def test_reports_conflict_when_docs_and_runtime_disagree(self):
        _write(self.project / ".env", "DJANGO_SETTINGS_MODULE=proj.settings\n")
        _write(
            self.project / "manage.py",
            'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "other.settings")\n',
        )
        _write(
            self.project / "core" / "asgi.py",
            'import os\nos.environ.setdefault("DJANGO_SETTINGS_MODULE", "other.settings")\n',
        )
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("Django settings module", out)
        self.assertIn("proj.settings", out)
        self.assertIn("other.settings", out)


class TestVerifyDocCounts(VerifyTestCase):
    def test_docs_only_count_claim(self):
        _write(self.project / "README.md", "- agents: 74\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("DOC_ONLY", out)
        self.assertIn("Agents count claims", out)
        self.assertIn("74", out)

    def test_conflicting_count_claims(self):
        _write(self.project / "README.md", "## Total Agents: 74\n")
        _write(self.project / "docs" / "NOTES.md", "## Total Agents: 75\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("74", out)
        self.assertIn("75", out)

    def test_canonical_docs_limit_count_scoring(self):
        _write_verify_config(
            self.project,
            "canonical_docs:\n"
            "  - README.md\n"
            "active_doc_roots:\n"
            "  - docs/\n"
            "historical_roots:\n"
            "  - docs/archive/\n"
            "generated_artifact_roots:\n"
            "  - dist/\n",
        )
        _write(self.project / "README.md", "## Total Agents: 74\n")
        _write(self.project / "docs" / "NOTES.md", "## Total Agents: 75\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "DOC_ONLY")
        self.assertEqual(data["config_path"], ".context-kit/verify.yaml")
        self.assertTrue(data["canonical_docs_used"])
        self.assertIn("canonical_docs", finding["evidence_by_scope"])
        self.assertIn("supporting_docs", finding["evidence_by_scope"])
        self.assertIn("74", finding["details"])
        self.assertIn("75", finding["details"])

    def test_supporting_docs_do_not_create_primary_conflicts(self):
        _write_verify_config(
            self.project,
            "canonical_docs:\n"
            "  - README.md\n"
            "active_doc_roots:\n"
            "  - docs/\n",
        )
        _write(self.project / "README.md", "## Total Agents: 74\n")
        _write(self.project / "docs" / "NOTES.md", "## Total Agents: 75\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("DOC_ONLY", out)
        self.assertIn("Canonical evidence", out)
        self.assertIn("Supporting drift", out)

    def test_all_docs_restores_broad_behavior(self):
        _write_verify_config(
            self.project,
            "canonical_docs:\n"
            "  - README.md\n"
            "active_doc_roots:\n"
            "  - docs/\n",
        )
        _write(self.project / "README.md", "## Total Agents: 74\n")
        _write(self.project / "docs" / "NOTES.md", "## Total Agents: 75\n")
        rc, out = _capture(_args(self.project, json_=True, all_docs=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "CONFLICT")

    def test_archived_docs_do_not_create_primary_conflict_by_default(self):
        _write(self.project / "docs" / "handoffs" / "SESSION_001.md", "## Total Agents: 74\n")
        _write(self.project / "docs" / "archive" / "SESSION_002.md", "## Total Agents: 75\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "DOC_ONLY")
        self.assertIn("historical_docs", finding["evidence_by_scope"])
        self.assertIn("74", finding["details"])
        self.assertIn("75", finding["details"])

    def test_env_files_create_primary_conflict(self):
        _write(self.project / ".env", "DJANGO_SETTINGS_MODULE=proj.settings\n")
        _write(self.project / ".env.example", "DJANGO_SETTINGS_MODULE=other.settings\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("Django settings module", out)

    def test_include_archive_brings_historical_evidence_into_scoring(self):
        _write(self.project / "docs" / "handoffs" / "SESSION_001.md", "## Total Agents: 74\n")
        _write(self.project / "docs" / "archive" / "SESSION_002.md", "## Total Agents: 75\n")
        rc, out = _capture(_args(self.project, json_=True, include_archive=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "CONFLICT")
        self.assertIn("historical_docs", finding["evidence_by_scope"])
        self.assertIn("74", finding["details"])
        self.assertIn("75", finding["details"])

    def test_human_report_truncates_long_evidence_lists(self):
        _write(self.project / "README.md", "## Total Agents: 74\n")
        for idx in range(1, 9):
            _write(self.project / "docs" / "notes" / f"NOTE_{idx}.md", f"## Total Agents: {74 + idx}\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("Primary evidence:", out)
        self.assertIn("+", out)
        self.assertIn("more primary matches", out)

    def test_incidental_numeric_phrases_do_not_create_count_claims(self):
        _write(self.project / "README.md", "We shipped 74 agents in 2026 and moved on.\n")
        _write(self.project / "docs" / "NOTES.md", "A filename like report_75.md is not a count claim.\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertFalse(any(item["id"].startswith("doc-count-") for item in data["findings"]))

    def test_numbered_prefixes_and_padded_numbers_are_ignored(self):
        _write(self.project / "README.md", "1. agents: 74\n")
        _write(self.project / "docs" / "NOTES.md", "- spiders: 01\n")
        _write(self.project / "docs" / "MORE.md", "| apis | 002 |\n")
        _write(self.project / "docs" / "STILL_MORE.md", "024 frontend pages are mentioned here.\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertFalse(any(item["id"].startswith("doc-count-") for item in data["findings"]))

    def test_small_values_need_strong_labels(self):
        _write(self.project / "README.md", "- agents: 3\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertFalse(any(item["id"].startswith("doc-count-") for item in data["findings"]))
        _write(self.project / "docs" / "strong.md", "### Total Agents: 3\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(any(item["id"] == "doc-count-agents" for item in data["findings"]))

    def test_headings_bullets_and_tables_create_count_claims(self):
        _write(self.project / "README.md", "## Agents: 74\n")
        _write(self.project / "docs" / "notes.md", "- total spiders: 3\n")
        _write(self.project / "docs" / "table.md", "| total apis | 5 |\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        ids = {item["id"] for item in data["findings"] if item["id"].startswith("doc-count-")}
        self.assertIn("doc-count-agents", ids)
        self.assertIn("doc-count-spiders", ids)
        self.assertIn("doc-count-apis", ids)

    def test_years_and_large_ids_are_ignored(self):
        _write(self.project / "README.md", "## Agents: 2026\n")
        _write(self.project / "docs" / "notes.md", "- spiders: 12345\n")
        _write(self.project / "docs" / "table.md", "| apis | 000 |\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertFalse(any(item["id"].startswith("doc-count-") for item in data["findings"]))

    def test_strong_labels_allow_small_values(self):
        _write(self.project / "README.md", "### Total Agents: 3\n")
        _write(self.project / "docs" / "counts.md", "| total spiders | 4 |\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        ids = {item["id"] for item in data["findings"] if item["id"].startswith("doc-count-")}
        self.assertIn("doc-count-agents", ids)
        self.assertIn("doc-count-spiders", ids)

    def test_total_agents_do_not_conflict_with_db_persona_counts(self):
        _write(self.project / "README.md", "## AGENT_MAP: 83 agents\n")
        _write(self.project / "docs" / "people.md", "DB persona agents: 223\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "DOC_ONLY")
        self.assertIn("83", finding["details"])
        self.assertIn("223", finding["details"])

    def test_category_table_rows_do_not_conflict_with_total(self):
        _write(self.project / "README.md", "## Total Agents: 83\n")
        _write(self.project / "docs" / "table.md", "| Creation | 4 |\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "DOC_ONLY")
        self.assertIn("4", finding["details"])

    def test_dormant_provenance_workspace_counts_do_not_conflict_with_total(self):
        _write(self.project / "README.md", "## Total Agents: 83\n")
        _write(self.project / "docs" / "dormant.md", "- dormant agents: 12\n")
        _write(self.project / "docs" / "provenance.md", "- provenance-tracked agents: 11\n")
        _write(self.project / "docs" / "workspace.md", "- workspace-aware agents: 10\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "DOC_ONLY")
        self.assertIn("83", finding["details"])
        self.assertIn("12", finding["details"])
        self.assertIn("11", finding["details"])
        self.assertIn("10", finding["details"])

    def test_total_agents_conflict_with_total_only(self):
        _write(self.project / "README.md", "## Total Agents: 83\n")
        _write(self.project / "docs" / "other.md", "## Total Agents: 74\n")
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "doc-count-agents")
        self.assertEqual(finding["status"], "CONFLICT")
        self.assertIn("83", finding["details"])
        self.assertIn("74", finding["details"])

    def test_verification_report_is_ignored_as_input(self):
        _write(self.project / "README.md", "- agents: 74\n")
        _write(self.project / "docs" / "verification" / "VERIFY_REPORT.md", "- agents: 75\n")
        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("DOC_ONLY", out)
        self.assertIn("74", out)
        self.assertNotIn("75", out)
        self.assertNotIn("docs/verification/VERIFY_REPORT.md", out)


class TestVerifyTrackedArtifacts(VerifyTestCase):
    def test_detects_tracked_generated_artifact(self):
        subprocess.run(["git", "init"], cwd=self.project, check=True, capture_output=True, text=True)
        _write(self.project / "frontend" / "dist" / "bundle.js", "console.log('hi');\n")
        subprocess.run(["git", "add", "frontend/dist/bundle.js"], cwd=self.project, check=True, capture_output=True, text=True)

        rc, out = _capture(_args(self.project))
        self.assertEqual(rc, 0)
        self.assertIn("CONFLICT", out)
        self.assertIn("Tracked generated artifacts", out)
        self.assertIn("frontend/dist/bundle.js", out)


class TestVerifyWriteMode(VerifyTestCase):
    def test_write_preserves_human_content_around_managed_block(self):
        report = self.project / "docs" / "verification" / "VERIFY_REPORT.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "# Human Notes\n\nKeep this.\n\n"
            f"{START_MARKER}\nold block\n{END_MARKER}\n\n"
            "# Footer\n",
            encoding="utf-8",
        )
        _write(self.project / "README.md", "- agents: 74\n")
        rc, _ = _capture(_args(self.project, write=True))
        self.assertEqual(rc, 0)
        body = report.read_text(encoding="utf-8")
        self.assertIn("# Human Notes", body)
        self.assertIn("Keep this.", body)
        self.assertIn("# Footer", body)
        self.assertIn(START_MARKER, body)
        self.assertIn(END_MARKER, body)
        self.assertNotIn("old block", body)
        self.assertIn("Verification Report", body)


class TestVerifyCeleryOwnership(VerifyTestCase):
    def test_generic_celery_task_files_are_not_ownership_evidence(self):
        _write(
            self.project / "app" / "tasks.py",
            "from celery import shared_task\n\n# PeriodicTask appears in a comment only.\n@shared_task\ndef ping():\n    return 1\n",
        )
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "celery-beat-schedule")
        self.assertEqual(finding["status"], "UNKNOWN")

    def test_direct_beat_schedule_config_is_ownership_evidence(self):
        _write(
            self.project / "app" / "celery.py",
            "from celery import Celery\n\napp = Celery('demo')\napp.conf.beat_schedule = {'ping': {'task': 'app.tasks.ping', 'schedule': 10}}\nPeriodicTask.objects.get_or_create(name='ping')\n",
        )
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "celery-beat-schedule")
        self.assertEqual(finding["status"], "VERIFIED")
        self.assertIn("app/celery.py", finding["details"])

    def test_split_ownership_docs_with_matching_runtime_are_verified(self):
        _write(
            self.project / "README.md",
            "Split Celery ownership: the static celery beat schedule lives in core/celery.py, django-celery-beat stores PeriodicTask rows, sync_celery_schedules repairs rows, and core/settings.py handles routing config.\n",
        )
        _write(
            self.project / "core" / "celery.py",
            "from celery import Celery\n\napp = Celery('demo')\napp.conf.beat_schedule = {'ping': {'task': 'app.tasks.ping', 'schedule': 10}}\n",
        )
        _write(
            self.project / "core" / "settings.py",
            "CELERY_TASK_ROUTES = {'app.tasks.ping': {'queue': 'default'}}\nCELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'\n",
        )
        _write(
            self.project / "app" / "management" / "commands" / "sync_celery_schedules.py",
            "def sync_celery_schedules():\n    return True\n",
        )
        _write(
            self.project / "app" / "models.py",
            "from django_celery_beat.models import PeriodicTask\n\nPeriodicTask.objects.get_or_create(name='ping')\n",
        )
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "celery-beat-schedule")
        self.assertEqual(finding["status"], "VERIFIED")
        self.assertIn("split celery ownership", finding["details"].lower())
        self.assertIn("core/celery.py", finding["details"])
        self.assertIn("DB store", finding["details"])

    def test_exclusive_settings_docs_conflict_with_celery_runtime(self):
        _write(
            self.project / "README.md",
            "settings.py owns the celery beat schedule and celery.py is dead code.\n",
        )
        _write(
            self.project / "core" / "celery.py",
            "from celery import Celery\n\napp = Celery('demo')\napp.conf.beat_schedule = {'ping': {'task': 'app.tasks.ping', 'schedule': 10}}\n",
        )
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "celery-beat-schedule")
        self.assertEqual(finding["status"], "CONFLICT")
        self.assertIn("exclusive ownership", finding["details"].lower())
        self.assertIn("core/celery.py", finding["details"])

    def test_historical_old_ownership_does_not_conflict_by_default(self):
        _write(
            self.project / "docs" / "archive" / "OLD_CELERY.md",
            "Old docs said celery.py owns the beat schedule, but that has since moved.\n",
        )
        _write(
            self.project / "core" / "celery.py",
            "from celery import Celery\n\napp = Celery('demo')\napp.conf.beat_schedule = {'ping': {'task': 'app.tasks.ping', 'schedule': 10}}\n",
        )
        rc, out = _capture(_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        finding = next(item for item in data["findings"] if item["id"] == "celery-beat-schedule")
        self.assertEqual(finding["status"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
