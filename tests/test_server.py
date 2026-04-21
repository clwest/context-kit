"""Tests for the context-kit onboarding server.

Combines unit tests for pure functions with a short live-server integration
test over a real HTTP socket.
"""

from __future__ import annotations

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

from cli.server import (  # noqa: E402
    _find_project_title,
    _key_files,
    _OnboardingHandler,
    _render_html,
)


class TestProjectTitleDiscovery(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reads_title_from_frontmatter(self):
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "MY_APP_WHAT_IT_IS.md").write_text(
            '---\n'
            'title: "My App — What It Actually Is"\n'
            'status: stub\n'
            '---\n\n'
            '# My App\n'
        )
        # The " — What It Actually Is" suffix is stripped.
        self.assertEqual(_find_project_title(self.tmpdir), "My App")

    def test_falls_back_to_directory_name(self):
        root = self.tmpdir / "fallback-proj"
        root.mkdir()
        self.assertEqual(_find_project_title(root), "fallback-proj")

    def test_handles_missing_frontmatter(self):
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "APP_WHAT_IT_IS.md").write_text("# No frontmatter here\n")
        # Falls back to tmpdir name since no frontmatter title found.
        self.assertEqual(_find_project_title(self.tmpdir), self.tmpdir.name)


class TestKeyFilesListing(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_canonical_paths_always_listed(self):
        entries = {name: exists for name, exists in _key_files(self.tmpdir)}
        self.assertIn("00-START-NEXT-SESSION.md", entries)
        self.assertIn("CLAUDE.md", entries)
        self.assertIn("docs/topics/", entries)
        self.assertIn("docs/handoffs/", entries)

    def test_missing_files_marked_false(self):
        for name, exists in _key_files(self.tmpdir):
            self.assertFalse(exists, f"unexpectedly present: {name}")

    def test_present_files_detected(self):
        (self.tmpdir / "00-START-NEXT-SESSION.md").write_text("x")
        (self.tmpdir / "docs").mkdir()
        (self.tmpdir / "docs" / "MY_APP_WHAT_IT_IS.md").write_text("x")
        (self.tmpdir / "docs" / "topics").mkdir()

        entries = {name: exists for name, exists in _key_files(self.tmpdir)}
        self.assertTrue(entries["00-START-NEXT-SESSION.md"])
        self.assertTrue(entries["docs/topics/"])
        self.assertTrue(entries["docs/MY_APP_WHAT_IT_IS.md"])


class TestHtmlRendering(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_contains_expected_sections(self):
        body = _render_html(self.tmpdir, "http://127.0.0.1:1234/")
        self.assertIn("First Steps", body)
        self.assertIn("Why this exists", body)
        self.assertIn("Key Files", body)
        self.assertIn("context-kit", body)

    def test_escapes_malicious_title(self):
        docs = self.tmpdir / "docs"
        docs.mkdir()
        (docs / "APP_WHAT_IT_IS.md").write_text(
            '---\ntitle: "<script>alert(1)</script>"\n---\n'
        )
        body = _render_html(self.tmpdir, "http://127.0.0.1:1234/")
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_placeholders_fully_substituted(self):
        body = _render_html(self.tmpdir, "http://127.0.0.1:1234/")
        # No unreplaced template placeholders should leak.
        for placeholder in ("{{PROJECT_TITLE}}", "{{PROJECT_ROOT}}",
                            "{{URL}}", "{{KEY_FILES_LIST}}"):
            self.assertNotIn(placeholder, body, f"leaked: {placeholder}")


class TestLiveServer(unittest.TestCase):
    """Spin a real HTTPServer on a background thread and hit it."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmpdir = Path(cls._tmp.name)
        (cls.tmpdir / "00-START-NEXT-SESSION.md").write_text("hi")

        # Port 0 means "OS picks a free port"; we read it back after bind.
        cls.server = HTTPServer(("127.0.0.1", 0), _OnboardingHandler)
        # Matches the monkey-patch pattern used by cli.server.run_start: the
        # handler reads ``self.server.onboarding_html`` at request time.
        cls.server.onboarding_html = _render_html(cls.tmpdir, "http://test/")  # type: ignore[attr-defined]
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._tmp.cleanup()

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        return urllib.request.urlopen(url, timeout=5)

    def test_root_returns_200(self):
        resp = self._get("/")
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("First Steps", body)
        self.assertIn("context-kit", body)

    def test_index_html_returns_200(self):
        resp = self._get("/index.html")
        self.assertEqual(resp.status, 200)

    def test_unknown_path_returns_404(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self._get("/nope")
        self.assertEqual(cm.exception.code, 404)

    def test_content_type_header(self):
        resp = self._get("/")
        content_type = resp.headers.get("Content-Type", "")
        self.assertTrue(
            content_type.startswith("text/html"),
            f"unexpected Content-Type: {content_type!r}",
        )


if __name__ == "__main__":
    unittest.main()
