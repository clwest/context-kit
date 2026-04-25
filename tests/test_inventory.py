"""Tests for the context-kit `inventory` subcommand.

Each test scaffolds a real project into a temp directory (so the
generator has a realistic file tree to scan), then exercises one of
the three modes. Sequential and self-cleaning.
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

from cli.bootstrap import run_init  # noqa: E402
from cli.inventory import (  # noqa: E402
    END_MARKER,
    START_MARKER,
    check_inventory,
    collect_inventory,
    run_inventory,
    write_inventory,
)


def _init_args(name, target):
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=True,
        force=False,
        quiet=True,
    )


def _inv_args(project, *, write=False, check=False, json_=False):
    return argparse.Namespace(
        command="inventory",
        project=str(project),
        write=write,
        check=check,
        json=json_,
    )


def _capture(args) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = run_inventory(args)
    return rc, buf.getvalue()


def _scaffold(tmpdir: Path, name: str = "Inv App") -> Path:
    project = tmpdir / "inv-app"
    run_init(_init_args(name, project))
    return project


# ---------------------------------------------------------------------------
# JSON mode
# ---------------------------------------------------------------------------


class TestInventoryJsonMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_json_output_is_valid(self):
        rc, out = _capture(_inv_args(self.project, json_=True))
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertIsInstance(data, dict)

    def test_json_includes_expected_keys(self):
        _, out = _capture(_inv_args(self.project, json_=True))
        data = json.loads(out)
        for key in (
            "schema_version",
            "generated_at",
            "project_path",
            "package",
            "cli_subcommands",
            "cli_modules",
            "guide_docs",
            "docs_files",
            "handoff_files",
            "template_files",
            "starter_files",
            "scaffold_files",
            "test_files",
            "test_count",
            "skill_files",
            "tracked_file_count",
            "hotpath",
        ):
            self.assertIn(key, data, f"missing key: {key}")

    def test_json_subcommands_include_inventory(self):
        _, out = _capture(_inv_args(self.project, json_=True))
        data = json.loads(out)
        self.assertIn("inventory", data["cli_subcommands"])

    def test_json_does_not_modify_inventory_file(self):
        inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"
        # Generated projects don't have this file by default.
        self.assertFalse(inv_path.exists())
        _capture(_inv_args(self.project, json_=True))
        self.assertFalse(inv_path.exists())


# ---------------------------------------------------------------------------
# --write mode
# ---------------------------------------------------------------------------


class TestInventoryWriteCreatesNewFile(unittest.TestCase):
    """When the inventory file doesn't exist, --write creates a sensible default."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))
        self.inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_creates_file_with_block(self):
        rc, _ = _capture(_inv_args(self.project, write=True))
        self.assertEqual(rc, 0)
        self.assertTrue(self.inv_path.is_file())
        body = self.inv_path.read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)
        self.assertIn(END_MARKER, body)

    def test_write_creates_file_with_human_intro(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        # Default human header lives outside the markers.
        intro, _, _ = body.partition(START_MARKER)
        self.assertIn("# Repo Inventory", intro)


class TestInventoryWriteUpdatesExistingBlock(unittest.TestCase):
    """When the file already has markers, --write replaces only the block."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))
        self.inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"
        self.inv_path.parent.mkdir(parents=True, exist_ok=True)
        self.inv_path.write_text(
            "# My Notes\n\nThings I want to keep.\n\n"
            f"{START_MARKER}\nold stale content\n{END_MARKER}\n\n"
            "## Footer\n\nAlso keep this.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_write_replaces_block_content(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        self.assertNotIn("old stale content", body)
        self.assertIn("Auto-generated counts", body)

    def test_write_preserves_content_outside_markers(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        self.assertIn("# My Notes", body)
        self.assertIn("Things I want to keep.", body)
        self.assertIn("## Footer", body)
        self.assertIn("Also keep this.", body)

    def test_write_keeps_exactly_one_marker_pair(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        self.assertEqual(body.count(START_MARKER), 1)
        self.assertEqual(body.count(END_MARKER), 1)


class TestInventoryWriteAppendsBlockSafely(unittest.TestCase):
    """File exists with hand-written content but no markers — append safely."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))
        self.inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"
        self.inv_path.parent.mkdir(parents=True, exist_ok=True)
        self.original_body = (
            "# Hand-written Inventory\n\n"
            "I've been maintaining this manually for years.\n\n"
            "Don't delete my notes please.\n"
        )
        self.inv_path.write_text(self.original_body, encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_existing_content_preserved(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        self.assertIn("# Hand-written Inventory", body)
        self.assertIn("I've been maintaining this manually for years.", body)
        self.assertIn("Don't delete my notes please.", body)

    def test_block_added(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)
        self.assertIn(END_MARKER, body)

    def test_block_appended_after_existing_content(self):
        _capture(_inv_args(self.project, write=True))
        body = self.inv_path.read_text(encoding="utf-8")
        # Original content should appear before the marker.
        self.assertLess(body.index("Don't delete my notes please."), body.index(START_MARKER))


# ---------------------------------------------------------------------------
# --check mode
# ---------------------------------------------------------------------------


class TestInventoryCheckMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_check_passes_immediately_after_write(self):
        _capture(_inv_args(self.project, write=True))
        rc, out = _capture(_inv_args(self.project, check=True))
        self.assertEqual(rc, 0)
        self.assertIn("current", out)

    def test_check_fails_when_inventory_missing(self):
        rc, out = _capture(_inv_args(self.project, check=True))
        self.assertEqual(rc, 1)
        self.assertIn("not found", out)

    def test_check_fails_when_block_missing(self):
        inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"
        inv_path.parent.mkdir(parents=True, exist_ok=True)
        inv_path.write_text("# Just a doc, no markers here.\n", encoding="utf-8")
        rc, out = _capture(_inv_args(self.project, check=True))
        self.assertEqual(rc, 1)
        self.assertIn("no managed block", out)

    def test_check_fails_when_inventory_is_stale(self):
        _capture(_inv_args(self.project, write=True))
        inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"
        # Mutate the project state (drop a guide doc) so a regen would differ.
        guide = self.project / "docs" / "docs-pattern" / "01_two_doc_anchor.md"
        if guide.is_file():
            guide.unlink()
        # Add a new test file too, just to be sure something visible drifts.
        new_test = self.project / "tests" / "test_drift_marker.py"
        new_test.parent.mkdir(parents=True, exist_ok=True)
        new_test.write_text("def test_marker():\n    pass\n", encoding="utf-8")
        rc, out = _capture(_inv_args(self.project, check=True))
        self.assertEqual(rc, 1)
        self.assertIn("stale", out)
        # Sanity: the file itself wasn't modified by --check.
        body = inv_path.read_text(encoding="utf-8")
        self.assertIn(START_MARKER, body)


class TestInventoryCheckIgnoresTimestampDrift(unittest.TestCase):
    """A second --check immediately after --write should still pass — the
    'Last generated' timestamp must be normalized out of the comparison."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_check_passes_ignoring_timestamp(self):
        _capture(_inv_args(self.project, write=True))
        # Use the in-process check helper to bypass any subprocess timing
        # weirdness — this exercises the timestamp-normalization path.
        is_current, _ = check_inventory(self.project)
        self.assertTrue(is_current)


# ---------------------------------------------------------------------------
# Direct API tests (skip argparse layer)
# ---------------------------------------------------------------------------


class TestCollectAndRender(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_collect_returns_dict(self):
        # In a generated project, guide_docs is correctly 0 — the guides
        # ship at docs/docs-pattern/ rather than the project root, and
        # the discovery rule is root-only by design.
        inv = collect_inventory(self.project)
        self.assertIsInstance(inv, dict)
        self.assertGreater(len(inv["cli_modules"]), 0)
        self.assertGreater(len(inv["cli_subcommands"]), 0)
        self.assertGreater(len(inv["docs_files"]), 0)
        self.assertGreater(len(inv["handoff_files"]), 0)

    def test_write_returns_action_label(self):
        inv_path = self.project / "docs" / "CONTEXT_KIT_INVENTORY.md"
        path1, action1 = write_inventory(self.project)
        self.assertEqual(path1, inv_path)
        self.assertEqual(action1, "created")
        # Second --write should report 'updated', not 'created'.
        _, action2 = write_inventory(self.project)
        self.assertEqual(action2, "updated")


# ---------------------------------------------------------------------------
# Argparse error cases
# ---------------------------------------------------------------------------


class TestInventoryNoMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = _scaffold(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_mode_returns_two(self):
        rc, out = _capture(_inv_args(self.project))
        self.assertEqual(rc, 2)
        self.assertIn("--write", out)
        self.assertIn("--check", out)
        self.assertIn("--json", out)


if __name__ == "__main__":
    unittest.main()
