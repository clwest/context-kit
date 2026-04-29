"""Tests for ``context-kit refactor track``.

Each test creates a temp directory with synthetic Python files and
optional plan markdown, runs ``run_refactor`` against it, and asserts
on stdout / exit code / JSON shape. Read-only command — exits 0 unless
the source path is missing.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli._refactor.detectors import (  # noqa: E402
    detect_celery_tasks,
    detect_classes,
    detect_functions,
    get_detector,
)
from cli._refactor.plan_parser import autodiscover_plan, parse_plan  # noqa: E402
from cli._refactor.scan import resolve_siblings, scan_file  # noqa: E402
from cli._refactor.track import compute_track  # noqa: E402
from cli.refactor import run_refactor  # noqa: E402


def _track_args(
    source: str,
    *,
    siblings: str | None = None,
    detector: str = "function",
    plan: str | None = "",  # default: disable autodiscovery
    baseline_count: int | None = None,
    avg_per_pr: int = 10,
    top: int = 5,
    fmt: str = "text",
):
    return argparse.Namespace(
        command="refactor",
        refactor_command="track",
        source=source,
        siblings=siblings,
        detector=detector,
        plan=plan,
        baseline_count=baseline_count,
        avg_per_pr=avg_per_pr,
        top=top,
        format=fmt,
    )


def _run(ns) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_refactor(ns)
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# Detector unit tests
# ---------------------------------------------------------------------------


class TestDetectors(unittest.TestCase):
    def test_function_detector_picks_module_level_only(self):
        import ast
        src = (
            "def a(): pass\n"
            "def b(): pass\n"
            "class C:\n"
            "    def method(self): pass\n"
        )
        names = detect_functions(ast.parse(src))
        self.assertEqual(names, ["a", "b"])

    def test_function_detector_includes_async(self):
        import ast
        src = "async def x(): pass\ndef y(): pass\n"
        names = detect_functions(ast.parse(src))
        self.assertEqual(sorted(names), ["x", "y"])

    def test_class_detector(self):
        import ast
        src = "class A: pass\nclass B: pass\ndef c(): pass\n"
        names = detect_classes(ast.parse(src))
        self.assertEqual(sorted(names), ["A", "B"])

    def test_celery_task_detector_all_decorator_forms(self):
        import ast
        src = (
            "@shared_task\n"
            "def bare(): pass\n"
            "@shared_task()\n"
            "def parens(): pass\n"
            "@shared_task(name='x')\n"
            "def named(): pass\n"
            "@app.task\n"
            "def app_task(): pass\n"
            "@celery.task(bind=True)\n"
            "def celery_attr(): pass\n"
            "def undecorated(): pass\n"
        )
        names = detect_celery_tasks(ast.parse(src))
        self.assertEqual(
            sorted(names),
            ["app_task", "bare", "celery_attr", "named", "parens"],
        )

    def test_get_detector_unknown_name_raises(self):
        with self.assertRaises(ValueError) as ctx:
            get_detector("nope")
        self.assertIn("nope", str(ctx.exception))


# ---------------------------------------------------------------------------
# Scan unit tests
# ---------------------------------------------------------------------------


class TestScan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scan_missing_file(self):
        scan = scan_file(self.tmp / "ghost.py", detect_functions)
        self.assertFalse(scan.exists)
        self.assertEqual(scan.item_count, 0)
        self.assertIsNone(scan.parse_error)

    def test_scan_parse_error_captured_not_raised(self):
        bad = self.tmp / "bad.py"
        bad.write_text("def broken(\n", encoding="utf-8")
        scan = scan_file(bad, detect_functions)
        self.assertTrue(scan.exists)
        self.assertIsNotNone(scan.parse_error)
        self.assertEqual(scan.item_count, 0)

    def test_scan_returns_sorted_names(self):
        f = self.tmp / "x.py"
        f.write_text("def b(): pass\ndef a(): pass\n", encoding="utf-8")
        scan = scan_file(f, detect_functions)
        self.assertEqual(scan.item_names, ["a", "b"])

    def test_resolve_siblings_default_glob(self):
        (self.tmp / "tasks.py").write_text("", encoding="utf-8")
        (self.tmp / "tasks_a.py").write_text("", encoding="utf-8")
        (self.tmp / "tasks_b.py").write_text("", encoding="utf-8")
        (self.tmp / "other.py").write_text("", encoding="utf-8")
        siblings = resolve_siblings(self.tmp / "tasks.py", None)
        names = sorted(p.name for p in siblings)
        self.assertEqual(names, ["tasks_a.py", "tasks_b.py"])

    def test_resolve_siblings_excludes_source(self):
        (self.tmp / "tasks.py").write_text("", encoding="utf-8")
        (self.tmp / "tasks_a.py").write_text("", encoding="utf-8")
        siblings = resolve_siblings(self.tmp / "tasks.py", "tasks*.py")
        # tasks.py itself must be excluded.
        names = sorted(p.name for p in siblings)
        self.assertEqual(names, ["tasks_a.py"])


# ---------------------------------------------------------------------------
# Plan parser unit tests
# ---------------------------------------------------------------------------


class TestPlanParser(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_parse_plan_extracts_total(self):
        f = self.tmp / "plan.md"
        f.write_text(
            "# Plan\n\n"
            "## Summary\n\n"
            "- **Total tasks:** 356\n"
            "- Other: 1\n",
            encoding="utf-8",
        )
        plan = parse_plan(f)
        self.assertEqual(plan.total_expected, 356)

    def test_parse_plan_extracts_destinations_with_underscores(self):
        f = self.tmp / "plan.md"
        f.write_text(
            "## Counts by proposed destination\n\n"
            "| Destination | Tasks |\n"
            "| --- | ---: |\n"
            "| `tasks_ops.py` | 134 |\n"
            "| `tasks_agents.py` | 45 |\n",
            encoding="utf-8",
        )
        plan = parse_plan(f)
        self.assertEqual(
            plan.per_destination,
            {"tasks_ops.py": 134, "tasks_agents.py": 45},
        )

    def test_parse_plan_missing_file_returns_empty(self):
        plan = parse_plan(self.tmp / "ghost.md")
        self.assertIsNone(plan.total_expected)
        self.assertEqual(plan.per_destination, {})

    def test_parse_plan_handles_items_header(self):
        # Generic case: not Celery-specific.
        f = self.tmp / "plan.md"
        f.write_text(
            "**Total items:** 12\n\n"
            "| Destination | Items |\n"
            "| --- | ---: |\n"
            "| utils_a.py | 5 |\n"
            "| utils_b.py | 7 |\n",
            encoding="utf-8",
        )
        plan = parse_plan(f)
        self.assertEqual(plan.total_expected, 12)
        self.assertEqual(plan.per_destination, {"utils_a.py": 5, "utils_b.py": 7})

    def test_autodiscover_finds_plan_under_docs_refactors(self):
        # Layout: tmp/core/tasks.py + tmp/docs/refactors/PLAN.md
        (self.tmp / "core").mkdir()
        (self.tmp / "core" / "tasks.py").write_text("", encoding="utf-8")
        rd = self.tmp / "docs" / "refactors"
        rd.mkdir(parents=True)
        plan = rd / "TASKS_MIGRATION_PLAN.md"
        plan.write_text("**Total tasks:** 1\n", encoding="utf-8")
        found = autodiscover_plan(self.tmp / "core" / "tasks.py")
        self.assertIsNotNone(found)
        self.assertEqual(found.resolve(), plan.resolve())


# ---------------------------------------------------------------------------
# Fixture 1: fresh state — source has all items, no siblings, no plan
# ---------------------------------------------------------------------------


class TestFreshState(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        src = self.tmp / "tasks.py"
        src.write_text(
            "@shared_task\ndef a(): pass\n"
            "@shared_task\ndef b(): pass\n"
            "@shared_task\ndef c(): pass\n",
            encoding="utf-8",
        )
        self.source = src

    def tearDown(self):
        self._tmp.cleanup()

    def test_zero_percent_complete(self):
        rc, out = _run(_track_args(str(self.source), detector="celery-task"))
        self.assertEqual(rc, 0)
        self.assertIn("Migrated", out)
        self.assertIn("3 items", out)  # baseline = current source = 3
        self.assertIn("  0.0%", out)   # nothing migrated

    def test_baseline_source_is_computed_when_no_flag_or_plan(self):
        ns = _track_args(str(self.source), detector="celery-task")
        rc, out = _run(ns)
        self.assertEqual(rc, 0)
        self.assertIn("computed", out)

    def test_computed_baseline_emits_underreport_warning_in_text(self):
        ns = _track_args(str(self.source), detector="celery-task")
        _, out = _run(ns)
        # The warning must appear in the rendered Warnings section.
        self.assertIn("Warnings", out)
        self.assertIn(
            "baseline inferred from current files; progress may be "
            "underreported. Use --baseline-count for accurate "
            "historical progress.",
            out,
        )

    def test_computed_baseline_emits_underreport_warning_in_json(self):
        ns = _track_args(str(self.source), detector="celery-task", fmt="json")
        _, out = _run(ns)
        obj = json.loads(out)
        self.assertEqual(obj["baseline_source"], "computed")
        self.assertTrue(
            any(
                "underreported" in w and "--baseline-count" in w
                for w in obj["warnings"]
            ),
            f"expected underreport warning in JSON warnings; got {obj['warnings']!r}",
        )


# ---------------------------------------------------------------------------
# Fixture 2: mid-refactor — source + siblings + plan
# ---------------------------------------------------------------------------


class TestMidRefactor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # Source with 50 celery tasks remaining.
        body = "".join(
            f"@shared_task\ndef src_{i}(): pass\n" for i in range(50)
        )
        (self.tmp / "tasks.py").write_text(body, encoding="utf-8")
        # Three siblings with 5 / 10 / 15 tasks respectively.
        for prefix, n in (("a", 5), ("b", 10), ("c", 15)):
            sb = "".join(
                f"@shared_task\ndef {prefix}_{i}(): pass\n" for i in range(n)
            )
            (self.tmp / f"tasks_{prefix}.py").write_text(sb, encoding="utf-8")
        # Plan with destinations totalling 80 and per-destination expectations.
        plan = self.tmp / "PLAN.md"
        plan.write_text(
            "## Summary\n\n"
            "- **Total tasks:** 80\n\n"
            "## Counts by proposed destination\n\n"
            "| Destination | Tasks |\n"
            "| --- | ---: |\n"
            "| tasks_a.py | 5 |\n"
            "| tasks_b.py | 10 |\n"
            "| tasks_c.py | 15 |\n"
            "| tasks_d.py | 20 |\n"
            "| tasks_e.py | 30 |\n",
            encoding="utf-8",
        )
        self.source = self.tmp / "tasks.py"
        self.plan_path = plan

    def tearDown(self):
        self._tmp.cleanup()

    def test_pct_complete_against_plan(self):
        ns = _track_args(
            str(self.source),
            detector="celery-task",
            plan=str(self.plan_path),
        )
        rc, out = _run(ns)
        self.assertEqual(rc, 0)
        # Baseline from plan = 80; remaining = 50; migrated = 30; pct = 37.5%
        self.assertIn("80 items", out)
        self.assertIn("30 items", out)
        self.assertIn(" 37.5%", out)

    def test_top_remaining_excludes_already_done_destinations(self):
        # tasks_a, tasks_b, tasks_c each meet plan; only d (20) and e (30) remain.
        ns = _track_args(
            str(self.source),
            detector="celery-task",
            plan=str(self.plan_path),
        )
        _, out = _run(ns)
        self.assertIn("tasks_d.py", out)
        self.assertIn("tasks_e.py", out)
        # The completed ones must not appear in the remaining table.
        # (They DO appear in "Items by destination" — but not in the
        # "Top remaining" section.)
        idx = out.find("Top remaining")
        self.assertGreater(idx, 0)
        tail = out[idx:]
        self.assertNotIn("tasks_a.py", tail)

    def test_eta_calculation_with_avg_per_pr(self):
        ns = _track_args(
            str(self.source),
            detector="celery-task",
            plan=str(self.plan_path),
            avg_per_pr=10,
        )
        _, out = _run(ns)
        # ceil(50 / 10) = 5
        self.assertIn("Estimated PRs remaining", out)
        self.assertIn(" 5", out)

    def test_json_output_shape_and_determinism(self):
        ns = _track_args(
            str(self.source),
            detector="celery-task",
            plan=str(self.plan_path),
            fmt="json",
        )
        _, out_a = _run(ns)
        _, out_b = _run(ns)
        self.assertEqual(out_a, out_b, "JSON output must be byte-identical across runs")
        obj = json.loads(out_a)
        # Required top-level keys.
        for key in (
            "source",
            "detector",
            "siblings",
            "plan",
            "baseline_count",
            "baseline_source",
            "migrated_count",
            "remaining_count",
            "pct_complete",
            "largest_remaining",
            "avg_per_pr",
            "estimated_prs_remaining",
            "warnings",
        ):
            self.assertIn(key, obj, f"missing JSON key: {key}")
        self.assertEqual(obj["source"]["item_count"], 50)
        self.assertEqual(obj["baseline_count"], 80)
        self.assertEqual(obj["baseline_source"], "plan")
        self.assertEqual(obj["migrated_count"], 30)
        self.assertEqual(obj["remaining_count"], 50)


# ---------------------------------------------------------------------------
# Fixture 3: plan / reality mismatch — sibling exceeds plan expectation
# ---------------------------------------------------------------------------


class TestPlanRealityMismatch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        (self.tmp / "tasks.py").write_text(
            "@shared_task\ndef only_one(): pass\n", encoding="utf-8"
        )
        # Sibling has 25 items but plan says 20 — a real overage.
        sb = "".join(
            f"@shared_task\ndef big_{i}(): pass\n" for i in range(25)
        )
        (self.tmp / "tasks_big.py").write_text(sb, encoding="utf-8")
        plan = self.tmp / "PLAN.md"
        plan.write_text(
            "**Total tasks:** 21\n\n"
            "| Destination | Tasks |\n"
            "| --- | ---: |\n"
            "| tasks_big.py | 20 |\n",
            encoding="utf-8",
        )
        self.source = self.tmp / "tasks.py"
        self.plan_path = plan

    def tearDown(self):
        self._tmp.cleanup()

    def test_overflowing_sibling_is_treated_as_done(self):
        # The sibling exceeds its plan target → not in Top remaining.
        ns = _track_args(
            str(self.source),
            detector="celery-task",
            plan=str(self.plan_path),
            fmt="json",
        )
        _, out = _run(ns)
        obj = json.loads(out)
        names = [r["destination"] for r in obj["largest_remaining"]]
        self.assertNotIn("tasks_big.py", names)


# ---------------------------------------------------------------------------
# Edge cases — missing source, bad detector, baseline-flag override
# ---------------------------------------------------------------------------


class TestEdgeCases(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_source_exits_2_with_clean_message(self):
        ns = _track_args(str(self.tmp / "nonexistent.py"))
        rc, out = _run(ns)
        self.assertEqual(rc, 2)
        self.assertIn("source file not found", out)

    def test_baseline_flag_overrides_plan(self):
        src = self.tmp / "tasks.py"
        src.write_text(
            "@shared_task\ndef a(): pass\n", encoding="utf-8"
        )
        plan = self.tmp / "PLAN.md"
        plan.write_text("**Total tasks:** 100\n", encoding="utf-8")
        ns = _track_args(
            str(src),
            detector="celery-task",
            plan=str(plan),
            baseline_count=50,
            fmt="json",
        )
        _, out = _run(ns)
        obj = json.loads(out)
        self.assertEqual(obj["baseline_count"], 50)
        self.assertEqual(obj["baseline_source"], "flag")

    def test_underreport_warning_absent_when_baseline_flag_supplied(self):
        src = self.tmp / "tasks.py"
        src.write_text(
            "@shared_task\ndef a(): pass\n", encoding="utf-8"
        )
        ns = _track_args(
            str(src),
            detector="celery-task",
            baseline_count=10,
            fmt="json",
        )
        _, out = _run(ns)
        obj = json.loads(out)
        self.assertFalse(
            any("underreported" in w for w in obj["warnings"]),
            f"warning must NOT appear when --baseline-count is supplied; "
            f"got {obj['warnings']!r}",
        )

    def test_underreport_warning_absent_when_plan_supplies_total(self):
        src = self.tmp / "tasks.py"
        src.write_text(
            "@shared_task\ndef a(): pass\n", encoding="utf-8"
        )
        plan = self.tmp / "PLAN.md"
        plan.write_text("**Total tasks:** 5\n", encoding="utf-8")
        ns = _track_args(
            str(src),
            detector="celery-task",
            plan=str(plan),
            fmt="json",
        )
        _, out = _run(ns)
        obj = json.loads(out)
        self.assertEqual(obj["baseline_source"], "plan")
        self.assertFalse(
            any("underreported" in w for w in obj["warnings"]),
            f"warning must NOT appear when plan total supplies baseline; "
            f"got {obj['warnings']!r}",
        )

    def test_unknown_detector_rejected_by_argparse(self):
        # We exercise compute_track directly here because argparse would
        # reject an unknown detector before run_refactor runs. compute_track
        # raises ValueError, which is the contract the CLI wraps.
        with self.assertRaises(ValueError):
            compute_track(
                source=self.tmp / "x.py",
                detector_name="nope",
                siblings_pattern=None,
                plan_path=None,
                baseline_count=None,
                avg_per_pr=10,
                top_n=5,
            )


if __name__ == "__main__":
    unittest.main()
