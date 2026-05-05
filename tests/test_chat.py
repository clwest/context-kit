"""Smoke tests for the ``context-kit chat`` subcommand."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.bootstrap import run_init  # noqa: E402
from cli.chat import run_chat  # noqa: E402
from cli.chat import CHAT_BEHAVIOR_PREAMBLE  # noqa: E402


def _init_args(name, target):
    return argparse.Namespace(
        command="init",
        name=name,
        target=str(target),
        with_scaffold=False,
        force=False,
        quiet=True,
    )


def _chat_args(
    project=None,
    prompt=None,
    *,
    model="llama3",
    include_inspect=False,
    debug_prompt=False,
    prompt_soft_threshold=20000,
):
    return argparse.Namespace(
        command="chat",
        project=str(project) if project is not None else None,
        model=model,
        prompt=prompt,
        include_inspect=include_inspect,
        debug_prompt=debug_prompt,
        prompt_soft_threshold=prompt_soft_threshold,
    )


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class TestChatSmoke(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self._tmp.name)
        self.project = self.tmpdir / "chat-app"
        self.other_project = self.tmpdir / "other-chat-app"
        run_init(_init_args("Chat App", self.project))
        run_init(_init_args("Other Chat App", self.other_project))

    def tearDown(self):
        self._tmp.cleanup()

    def _mark_inventory_low_signal(self, project: Path) -> None:
        inventory_files = sorted(project.glob("docs/*_INVENTORY.md"))
        self.assertTrue(inventory_files)
        inventory_files[0].write_text(
            inventory_files[0].read_text(encoding="utf-8") + "\n<!-- context-kit:inventory:low-signal -->\n",
            encoding="utf-8",
        )

    def test_posts_orientation_and_prompt_to_ollama(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["url"] = req.full_url
            captured["method"] = req.get_method()
            captured["headers"] = {key.lower(): value for key, value in req.header_items()}
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ollama says hello"}})

        buf = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(buf):
                rc = run_chat(_chat_args(self.project, ["How", "do", "I", "start?"]))

        self.assertEqual(rc, 0)
        self.assertEqual(captured["url"], "http://localhost:11434/api/chat")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["headers"]["content-type"], "application/json")

        payload = captured["payload"]
        self.assertEqual(payload["model"], "llama3")
        self.assertFalse(payload["stream"])
        self.assertEqual(len(payload["messages"]), 2)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertTrue(payload["messages"][0]["content"].startswith(CHAT_BEHAVIOR_PREAMBLE))
        self.assertIn("## PROJECT IDENTITY SUMMARY", payload["messages"][0]["content"])
        self.assertIn("## PROJECT ORIENTATION", payload["messages"][0]["content"])
        self.assertIn("docs/CHAT_APP_WHAT_IT_IS.md", payload["messages"][0]["content"])
        self.assertIn(
            'When the user asks "what are we doing/testing/discussing right now", answer from the recent chat messages first.',
            payload["messages"][0]["content"],
        )
        self.assertEqual(payload["messages"][1], {"role": "user", "content": "How do I start?"})
        self.assertIn("ollama says hello", buf.getvalue())

    def test_interactive_mode_sends_accumulated_history(self):
        captured_payloads: list[dict] = []

        def fake_urlopen(req, timeout=None):
            del timeout
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            content = f"reply {len(captured_payloads)}"
            return _FakeResponse({"message": {"content": content}})

        buf = io.StringIO()
        with patch("cli.chat.sys.stdin.isatty", return_value=True):
            with patch("cli.chat.input", side_effect=["Hello", "How are you?", "/exit"]):
                with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
                    with redirect_stdout(buf):
                        rc = run_chat(_chat_args(self.project))

        self.assertEqual(rc, 0)
        self.assertIn("context-kit chat started. Type /exit to quit.", buf.getvalue())
        self.assertEqual(len(captured_payloads), 2)
        self.assertTrue(captured_payloads[0]["messages"][0]["content"].startswith(CHAT_BEHAVIOR_PREAMBLE))
        self.assertIn("## PROJECT ORIENTATION", captured_payloads[0]["messages"][0]["content"])
        self.assertIn("docs/CHAT_APP_WHAT_IT_IS.md", captured_payloads[0]["messages"][0]["content"])
        self.assertEqual(captured_payloads[0]["messages"][1], {"role": "user", "content": "Hello"})
        self.assertEqual(
            captured_payloads[1]["messages"],
            [
                captured_payloads[0]["messages"][0],
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "reply 1"},
                {"role": "user", "content": "How are you?"},
            ],
        )
        self.assertIn("reply 1", buf.getvalue())
        self.assertIn("reply 2", buf.getvalue())

    def test_reset_clears_prior_turns(self):
        captured_payloads: list[dict] = []

        def fake_urlopen(req, timeout=None):
            del timeout
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            content = f"reset reply {len(captured_payloads)}"
            return _FakeResponse({"message": {"content": content}})

        buf = io.StringIO()
        with patch("cli.chat.sys.stdin.isatty", return_value=True):
            with patch("cli.chat.input", side_effect=["Hello", "/reset", "After reset", "/exit"]):
                with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
                    with redirect_stdout(buf):
                        rc = run_chat(_chat_args(self.project))

        self.assertEqual(rc, 0)
        self.assertEqual(len(captured_payloads), 2)
        self.assertTrue(captured_payloads[0]["messages"][0]["content"].startswith(CHAT_BEHAVIOR_PREAMBLE))
        self.assertEqual(captured_payloads[0]["messages"][1], {"role": "user", "content": "Hello"})
        self.assertEqual(
            captured_payloads[1]["messages"],
            [
                captured_payloads[0]["messages"][0],
                {"role": "user", "content": "After reset"},
            ],
        )
        self.assertIn("Conversation reset.", buf.getvalue())

    def test_exit_exits_cleanly(self):
        with patch("cli.chat.sys.stdin.isatty", return_value=True):
            with patch("cli.chat.input", return_value="/exit") as input_mock:
                with patch("cli.ollama.request.urlopen") as urlopen_mock:
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        rc = run_chat(_chat_args(self.project))

        self.assertEqual(rc, 0)
        input_mock.assert_called_once()
        urlopen_mock.assert_not_called()
        self.assertIn("context-kit chat started. Type /exit to quit.", buf.getvalue())

    def test_project_flag_uses_target_orientation(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.other_project, ["What", "is", "this?"]))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("Other Chat App", system_message)
        self.assertIn("docs/OTHER_CHAT_APP_WHAT_IT_IS.md", system_message)
        self.assertNotIn("docs/CHAT_APP_WHAT_IT_IS.md", system_message)

    def test_omitted_project_preserves_current_cwd_behavior(self):
        prev_cwd = Path.cwd()
        os.chdir(self.project)
        try:
            captured: dict = {}

            def fake_urlopen(req, timeout=None):
                del timeout
                captured["payload"] = json.loads(req.data.decode("utf-8"))
                return _FakeResponse({"message": {"content": "ok"}})

            with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
                with redirect_stdout(io.StringIO()):
                    rc = run_chat(_chat_args(None, ["What", "is", "this?"]))
        finally:
            os.chdir(prev_cwd)

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("Chat App", system_message)
        self.assertIn("docs/CHAT_APP_WHAT_IT_IS.md", system_message)

    def test_invalid_project_returns_clear_error(self):
        bad_project = self.tmpdir / "missing-project"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            rc = run_chat(_chat_args(bad_project, ["Hello"]))

        self.assertEqual(rc, 2)
        self.assertIn("error: --project path does not exist", stderr.getvalue())

    def test_include_inspect_appends_machine_inspection(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.project, ["What", "do", "you", "see?"], include_inspect=True))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("## PROJECT IDENTITY SUMMARY", system_message)
        self.assertIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertIn("## PROJECT ORIENTATION", system_message)
        self.assertIn("Project identity", system_message)
        self.assertIn("docs/CHAT_APP_WHAT_IT_IS.md", system_message)

    def test_omit_include_inspect_preserves_current_behavior(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.project, ["What", "do", "you", "see?"]))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertNotIn("MACHINE-DERIVED REPO INSPECTION", system_message)

    def test_debug_prompt_prints_counts_and_system_prompt(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(_chat_args(self.project, ["Explain", "context-kit"], debug_prompt=True))

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Resolved project path:", output)
        self.assertIn("--include-inspect enabled: no", output)
        self.assertIn("Inspection text generated: no", output)
        self.assertIn("Inventory preview skipped:", output)
        self.assertIn("Character counts:", output)
        self.assertIn("chat preamble:", output)
        self.assertIn("project identity summary:", output)
        self.assertIn("orientation:", output)
        self.assertIn("inspection:", output)
        self.assertIn("total system prompt:", output)
        self.assertIn("=== CHAT PREAMBLE ===", output)
        self.assertIn("=== PROJECT IDENTITY SUMMARY ===", output)
        self.assertIn("=== MACHINE-DERIVED REPO INSPECTION ===", output)
        self.assertIn("=== PROJECT ORIENTATION ===", output)
        self.assertIn("inspection not included", output)
        self.assertNotIn("chat>", output)
        self.assertIn("ok", output)
        self.assertIn(CHAT_BEHAVIOR_PREAMBLE, output)

    def test_debug_prompt_with_inspect_includes_machine_inspection(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(_chat_args(self.other_project, ["What", "is", "this?"], include_inspect=True, debug_prompt=True))

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("--include-inspect enabled: yes", output)
        self.assertIn("Inspection text generated: yes", output)
        self.assertIn("Inventory preview skipped:", output)
        self.assertIn("=== MACHINE-DERIVED REPO INSPECTION ===", output)
        self.assertIn("=== PROJECT ORIENTATION ===", output)
        self.assertIn("docs/OTHER_CHAT_APP_WHAT_IT_IS.md", output)
        self.assertIn(str(self.other_project), output)

        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("## PROJECT IDENTITY SUMMARY", system_message)
        self.assertIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertIn("## PROJECT ORIENTATION", system_message)
        self.assertIn("docs/OTHER_CHAT_APP_WHAT_IT_IS.md", system_message)
        self.assertNotIn("docs/CHAT_APP_WHAT_IT_IS.md", system_message)

    def test_low_signal_inventory_is_compressed_and_skipped(self):
        self._mark_inventory_low_signal(self.project)
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(_chat_args(self.project, ["What", "is", "this?"], include_inspect=True, debug_prompt=True))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertNotIn("## INVENTORY PREVIEW", system_message)
        self.assertIn("## PROJECT ORIENTATION", system_message)
        self.assertIn("## WHAT_IT_IS PREVIEW", system_message)
        self.assertIn("docs/CHAT_APP_WHAT_IT_IS.md", system_message)
        self.assertLess(system_message.index("## MACHINE-DERIVED REPO INSPECTION"), system_message.index("## PROJECT ORIENTATION"))
        self.assertIn("Inventory preview skipped: yes", stdout.getvalue())

    def test_prompt_soft_threshold_warns(self):
        stderr = io.StringIO()

        def fake_urlopen(req, timeout=None):
            del timeout
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stderr(stderr):
                rc = run_chat(_chat_args(self.project, ["Hello"], prompt_soft_threshold=1))

        self.assertEqual(rc, 0)
        self.assertIn("warning: chat system prompt is", stderr.getvalue())
