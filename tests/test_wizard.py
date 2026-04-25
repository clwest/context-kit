"""Tests for the context-kit `start` wizard routes and APIs.

Covers the wizard HTML page, project-state classification, idea.md write
endpoint (with path traversal protection), and per-step filesystem polling
(`/api/check`). Existing `/` route behavior is unchanged and remains
covered by tests/test_server.py.
"""

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

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.bootstrap import run_init  # noqa: E402
from cli.server import (  # noqa: E402
    _OnboardingHandler,
    _detect_project_state,
    _load_wizard_html,
    _render_html,
    _safe_project_path,
)


# ---------------------------------------------------------------------------
# Project-state classification
# ---------------------------------------------------------------------------


class TestDetectProjectState(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_none_when_empty_dir(self):
        self.assertEqual(_detect_project_state(self.tmpdir), "none")

    def test_scaffold_after_init(self):
        # After init, frontmatter has state: scaffold
        import argparse
        run_init(argparse.Namespace(
            command="init", name="State Test", target=str(self.tmpdir / "p"),
            with_scaffold=False, force=False, quiet=True,
        ))
        self.assertEqual(_detect_project_state(self.tmpdir / "p"), "scaffold")

    def test_seeded_after_seed(self):
        import argparse
        from cli.seed import run_seed
        project = self.tmpdir / "p"
        run_init(argparse.Namespace(
            command="init", name="Seed Test", target=str(project),
            with_scaffold=False, force=False, quiet=True,
        ))
        idea = self.tmpdir / "idea.md"
        idea.write_text("# X\n\n## What\n\nA thing.\n", encoding="utf-8")
        run_seed(argparse.Namespace(
            command="seed", idea=str(idea), project=str(project),
            force=False, dry_run=False,
        ))
        self.assertEqual(_detect_project_state(project), "seeded")


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


class TestSafeProjectPath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_simple_subdir_allowed(self):
        result = _safe_project_path(self.tmpdir, "med-tracker")
        self.assertEqual(result, self.tmpdir / "med-tracker")

    def test_empty_or_dot_means_cwd(self):
        for value in ("", ".", "./"):
            result = _safe_project_path(self.tmpdir, value)
            self.assertEqual(result.resolve(), self.tmpdir)

    def test_dotdot_traversal_rejected(self):
        with self.assertRaises(ValueError):
            _safe_project_path(self.tmpdir, "../escape")

    def test_absolute_outside_cwd_rejected(self):
        with self.assertRaises(ValueError):
            _safe_project_path(self.tmpdir, "/etc/passwd")

    def test_nested_dotdot_rejected(self):
        with self.assertRaises(ValueError):
            _safe_project_path(self.tmpdir, "med-tracker/../../sneaky")


# ---------------------------------------------------------------------------
# Wizard HTML loader
# ---------------------------------------------------------------------------


class TestWizardHtmlLoader(unittest.TestCase):
    def test_loads_packaged_wizard_html(self):
        # When invoked from the source repo (or any cli with _static), the
        # loader should return the wizard HTML body.
        body = _load_wizard_html()
        self.assertIsNotNone(body)
        # Sanity: contains the marker our wizard uses.
        self.assertIn("context-kit", body)


# ---------------------------------------------------------------------------
# Live server: /, /wizard, /api/state, POST /api/idea, /api/check
# ---------------------------------------------------------------------------


class TestLiveWizardServer(unittest.TestCase):
    """Spin a real HTTPServer with the new handler and exercise every route."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.cwd = Path(cls._tmp.name).resolve()
        # Existing onboarding renders the project-view HTML; needed for / route.
        (cls.cwd / "00-START-NEXT-SESSION.md").write_text("hi", encoding="utf-8")

        cls.server = HTTPServer(("127.0.0.1", 0), _OnboardingHandler)
        # Attach handler context the same way run_start does.
        cls.server.onboarding_html = _render_html(cls.cwd, "http://test/")  # type: ignore[attr-defined]
        cls.server.wizard_html = _load_wizard_html() or "(wizard not available)"  # type: ignore[attr-defined]
        cls.server.cwd = cls.cwd  # type: ignore[attr-defined]

        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def _get(self, path: str) -> tuple[int, str, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), dict(e.headers)

    def _post_json(self, path: str, payload: dict) -> tuple[int, str, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), dict(e.headers)

    # --- existing route still works ---

    def test_root_returns_existing_onboarding(self):
        status, body, _ = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("First Steps", body)

    # --- /wizard ---

    def test_wizard_returns_200_with_html(self):
        status, body, headers = self._get("/wizard")
        self.assertEqual(status, 200)
        self.assertTrue(headers.get("Content-Type", "").startswith("text/html"))
        self.assertIn("context-kit", body)

    def test_wizard_step2_uses_clearer_naming_copy(self):
        """Step 2 explains what the project name is for and de-emphasizes
        the folder field."""
        _, body, _ = self._get("/wizard")
        # New title and intro (assert two short fragments — the source HTML
        # wraps the long line, so a single long substring won't match)
        self.assertIn("Where should we create your project?", body)
        self.assertIn("Give your idea a short, clear name.", body)
        self.assertIn("where your project files will live", body)
        # Re-framed labels
        self.assertIn("Project name", body)
        self.assertIn("Folder name", body)
        # Examples that signal what kind of name is useful
        self.assertIn("Dad Med Reminder", body)
        self.assertIn("Kids Fitness Tracker", body)
        # Folder helper makes it clear this field rarely needs editing
        self.assertIn(
            "Auto-created from the project name. You usually don't need to change this.",
            body,
        )

    def test_wizard_step2_warns_on_generic_project_names(self):
        """Locks in the gentle warning behavior + the trigger list.

        We assert the warning text and a representative subset of trigger
        words are present in the page (the JS list lives in the served
        HTML; the actual warning fires client-side at input time).
        """
        _, body, _ = self._get("/wizard")
        self.assertIn(
            "That name may be hard to recognize later. Consider something more specific.",
            body,
        )
        # A few representative trigger words from the GENERIC_NAMES set
        for trigger in ('"new"', '"app"', '"test"', '"project"'):
            self.assertIn(trigger, body, f"missing generic-name trigger: {trigger}")

    def test_wizard_step3_uses_friendly_beginner_copy(self):
        """Step 3 must read like a friendly conversation, not a tech form.

        Locks in the user's exact wording so future edits don't quietly drift
        back to technical labels.
        """
        _, body, _ = self._get("/wizard")
        # Friendly intro framing
        self.assertIn(
            "describe your idea like you would to a friend",
            body,
            "Step 3 intro should use the conversational framing",
        )
        self.assertIn(
            "You can leave most of this blank",
            body,
            "Step 3 should reassure the user that most fields are optional",
        )
        # Conversational field labels (not the canonical heading text)
        self.assertIn("What do you want to build?", body)
        self.assertIn("Who is this for?", body)
        self.assertIn("Why do you want this?", body)
        self.assertIn("What would a first simple version do?", body)
        self.assertIn("Not sure about tech? Skip this.", body)
        self.assertIn("Anything you're unsure about?", body)
        # The required-field example is the medication-reminder dogfood case
        self.assertIn(
            'an app to remind my dad to take his medication',
            body,
        )

    # --- /api/state ---

    def test_api_state_returns_json(self):
        status, body, _ = self._get("/api/state")
        self.assertEqual(status, 200)
        data = json.loads(body)
        for key in ("cwd", "project_state"):
            self.assertIn(key, data)

    # --- POST /api/idea ---

    def test_post_idea_writes_file(self):
        # The TestLiveServer's cwd is a scratch dir; write idea into a subdir.
        status, body, _ = self._post_json("/api/idea", {
            "project_dir": "wizard-write-test",
            "content": "# Wiz\n\n## What\n\nA test.\n",
        })
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("written"))
        path = Path(data["path"])
        self.assertTrue(path.is_file())
        self.assertIn("A test.", path.read_text(encoding="utf-8"))

    def test_post_idea_rejects_empty_content(self):
        status, _, _ = self._post_json("/api/idea", {
            "project_dir": "x", "content": "",
        })
        self.assertEqual(status, 400)

    def test_post_idea_rejects_path_traversal(self):
        status, _, _ = self._post_json("/api/idea", {
            "project_dir": "../escape", "content": "# X\n\n## What\n\nx\n",
        })
        self.assertEqual(status, 400)

    def test_post_idea_rejects_absolute_outside_cwd(self):
        status, _, _ = self._post_json("/api/idea", {
            "project_dir": "/etc/passwd", "content": "# X\n\n## What\n\nx\n",
        })
        self.assertEqual(status, 400)

    # --- /api/check ---

    def test_api_check_init_unsatisfied_for_empty_dir(self):
        status, body, _ = self._get("/api/check?step=init&project_dir=nope")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data.get("satisfied"))

    def test_api_check_init_satisfied_when_start_doc_present(self):
        status, body, _ = self._get(
            "/api/check?step=init&project_dir=."
        )
        # Our test cwd has 00-START-NEXT-SESSION.md from setUpClass.
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data.get("satisfied"))

    def test_api_check_seed_unsatisfied_without_build_plan(self):
        status, body, _ = self._get("/api/check?step=seed&project_dir=.")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertFalse(data.get("satisfied"))

    def test_api_check_unknown_step_returns_400(self):
        status, _, _ = self._get("/api/check?step=bogus&project_dir=.")
        self.assertEqual(status, 400)

    # --- 404 for unknown paths ---

    def test_unknown_path_returns_404(self):
        status, _, _ = self._get("/nope")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
