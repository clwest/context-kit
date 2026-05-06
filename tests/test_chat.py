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
    include_capabilities=False,
    capabilities_format="shortlist",
    debug_prompt=False,
    prompt_soft_threshold=20000,
    no_prime=False,
):
    return argparse.Namespace(
        command="chat",
        project=str(project) if project is not None else None,
        model=model,
        prompt=prompt,
        include_inspect=include_inspect,
        include_capabilities=include_capabilities,
        capabilities_format=capabilities_format,
        debug_prompt=debug_prompt,
        prompt_soft_threshold=prompt_soft_threshold,
        no_prime=no_prime,
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
        self.nested_project = self.tmpdir / "mentorforge"
        run_init(_init_args("Chat App", self.project))
        run_init(_init_args("Other Chat App", self.other_project))
        run_init(_init_args("Mentorforge", self.nested_project))
        backend = self.nested_project / "backend"
        frontend = self.nested_project / "frontend"
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
            "@dataclass\n"
            "class TierConfig:\n"
            "    allowed_modes = ['basic', 'pro']\n"
            "    max_sessions_per_day = 10\n"
            "    max_response_tokens = 2000\n"
            "    max_messages_per_session = 25\n"
            "TIERS = {'free': TierConfig()}\n",
            encoding="utf-8",
        )
        (frontend / "package.json").write_text(
            '{"name":"mentorforge-ui","dependencies":{"react":"18.3.1","vite":"5.4.0"}}\n',
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _mark_inventory_low_signal(self, project: Path) -> None:
        inventory_files = sorted(project.glob("docs/*_INVENTORY.md"))
        self.assertTrue(inventory_files)
        inventory_files[0].write_text(
            inventory_files[0].read_text(encoding="utf-8") + "\n<!-- context-kit:inventory:low-signal -->\n",
            encoding="utf-8",
        )

    def _extract_section(self, text: str, heading: str) -> str:
        start = text.index(heading) + len(heading)
        remainder = text[start:]
        next_heading = remainder.find("\n## ")
        if next_heading == -1:
            return remainder
        return remainder[:next_heading]

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
        self.assertIn("Answer the user's current question directly.", payload["messages"][0]["content"])
        self.assertIn("Do not repeatedly introduce yourself.", payload["messages"][0]["content"])
        self.assertIn("Do not ask \"what would you like to discuss?\"", payload["messages"][0]["content"])
        self.assertIn(
            "If the user asks what project you are oriented to, answer once with the project name/path and stop.",
            payload["messages"][0]["content"],
        )
        self.assertIn("Machine-detected repo facts may only come from the MACHINE-DERIVED REPO INSPECTION section.", payload["messages"][0]["content"])
        self.assertIn("Documented orientation may only come from PROJECT ORIENTATION.", payload["messages"][0]["content"])
        self.assertIn("Do not copy orientation claims into machine-detected facts.", payload["messages"][0]["content"])
        self.assertIn("If a feature is inferred from a route, say 'route evidence suggests...' instead of 'implements'.", payload["messages"][0]["content"])
        self.assertIn("If neither inspection nor orientation supports a claim, label it speculation or unknown.", payload["messages"][0]["content"])
        self.assertIn("Prefer 'detected' / 'documented' / 'suggests' over confident product claims.", payload["messages"][0]["content"])
        self.assertIn("When listing machine-detected repo facts, include evidence in parentheses.", payload["messages"][0]["content"])
        self.assertIn("Machine-detected facts must be based only on inspect lines with file paths, route decorators, models, env keys, Dockerfiles, manifests, or detected framework indicators.", payload["messages"][0]["content"])
        self.assertIn('If a claim comes from PROJECT ORIENTATION only, label it "Documented orientation claim".', payload["messages"][0]["content"])
        self.assertIn('If a feature is inferred from route evidence, label it "Route evidence suggests...".', payload["messages"][0]["content"])
        self.assertIn("If no file/path/route/model/env evidence exists, do not put it under machine-detected facts.", payload["messages"][0]["content"])
        self.assertIn("Prefer concrete implementation evidence over product summaries.", payload["messages"][0]["content"])
        self.assertIn("Never invent file:line citations.", payload["messages"][0]["content"])
        self.assertIn("Only use line numbers that appear in MACHINE-DERIVED REPO INSPECTION.", payload["messages"][0]["content"])
        self.assertIn("If a file is known but no line is provided, cite only the file path.", payload["messages"][0]["content"])
        self.assertIn("Do not cite line numbers from user-provided memory or inference.", payload["messages"][0]["content"])
        self.assertIn("When the user asks \"what can this project do\", answer in this order:", payload["messages"][0]["content"])
        self.assertIn("Structured implementation facts / machine-detected implementation evidence", payload["messages"][0]["content"])
        self.assertIn("Prefer structured implementation facts when answering \"what can this app do?\".", payload["messages"][0]["content"])
        self.assertIn("When capability labels are derived from route groups, use the phrase \"evidence suggests\".", payload["messages"][0]["content"])
        self.assertIn("For \"what can this app do?\" questions, prefer DETERMINISTIC CAPABILITY SUMMARY first.", payload["messages"][0]["content"])
        self.assertIn("Summarize the Recommended capability shortlist first.", payload["messages"][0]["content"])
        self.assertIn("Do not omit high-confidence capabilities from the shortlist unless the user asks for a narrower answer.", payload["messages"][0]["content"])
        self.assertIn("Use MACHINE-DERIVED REPO INSPECTION for details only when capabilities are missing.", payload["messages"][0]["content"])
        self.assertIn("Do not override deterministic capability evidence with orientation claims.", payload["messages"][0]["content"])
        self.assertIn("When summarizing deterministic capabilities, preserve Confidence and Reason exactly; do not upgrade confidence from orientation or inspection.", payload["messages"][0]["content"])
        self.assertIn("For capability questions, prefer route/decorator evidence over request model evidence.", payload["messages"][0]["content"])
        self.assertIn("Request/response models support shape, not user-facing capability.", payload["messages"][0]["content"])
        self.assertIn("Do not cite BaseModel classes as primary capability evidence when route evidence exists.", payload["messages"][0]["content"])
        self.assertIn("Do not treat detector/self-analysis code as project implementation evidence unless detector evidence was explicitly requested.", payload["messages"][0]["content"])
        self.assertIn("Capability summaries are static snapshots from startup, not live repo state.", payload["messages"][0]["content"])
        self.assertIn("Do not describe injected context as \"latest repo changes\" unless git diff/log data is explicitly present.", payload["messages"][0]["content"])
        self.assertIn("A detected route proves endpoint presence only, not internal implementation correctness.", payload["messages"][0]["content"])
        self.assertIn("Do not claim security validation, payment completion, business logic correctness, or test status from route evidence alone.", payload["messages"][0]["content"])
        self.assertIn("If asked to verify implementation details, say you cannot verify from the injected capability summary and suggest the user run or paste a relevant command or include raw inspect/file content.", payload["messages"][0]["content"])
        self.assertIn("With --include-capabilities only, do not claim to know internals beyond capability labels, evidence, confidence, and reason.", payload["messages"][0]["content"])
        self.assertIn("If the user asks about live repo state, latest changes, recent changes, current test status, git diff, git log, uncommitted changes, or whether something is true \"right now\", do not answer from startup summaries.", payload["messages"][0]["content"])
        self.assertIn("Never infer \"no changes\" or \"nothing changed\" from absent evidence.", payload["messages"][0]["content"])
        self.assertIn("Only answer live-state questions if explicit git diff/log/status/test output was injected or pasted in the live conversation.", payload["messages"][0]["content"])
        self.assertIn("I can’t verify live repo state from the injected startup context.", payload["messages"][0]["content"])
        self.assertIn("Suggest specific commands: git status, git log --oneline -5, context-kit inspect --project <path>, context-kit capabilities --project <path> --format shortlist, and a test command if known; otherwise say no test command is known from context.", payload["messages"][0]["content"])
        self.assertIn("You cannot execute shell commands or context-kit commands from inside this chat.", payload["messages"][0]["content"])
        self.assertIn("You only know the project context injected when chat started plus live conversation history.", payload["messages"][0]["content"])
        self.assertIn("Do not claim you can run commands, inspect files, access repositories, read additional files, or fetch updated state.", payload["messages"][0]["content"])
        self.assertIn("You may suggest terminal commands for the user to run.", payload["messages"][0]["content"])
        self.assertIn("Use wording like \"I was given\" or \"the injected context says,\" not \"I can execute\".", payload["messages"][0]["content"])
        self.assertIn("Never simulate running commands.", payload["messages"][0]["content"])
        self.assertIn("Never write fake terminal output.", payload["messages"][0]["content"])
        self.assertIn("I can’t run commands from inside this chat.", payload["messages"][0]["content"])
        self.assertIn("I can’t verify live repo state from injected startup context.", payload["messages"][0]["content"])
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
        self.assertEqual(
            captured_payloads[0]["messages"][1],
            {
                "role": "user",
                "content": (
                    "Before we begin: you are oriented to project 'chat-app' at "
                    f"'{self.project.resolve()}'. Use the provided machine-derived repo inspection and project orientation as your grounding. "
                    "When asked what project you are oriented to, answer with this project."
                ),
            },
        )
        self.assertEqual(
            captured_payloads[0]["messages"][2],
            {
                "role": "assistant",
                "content": "Understood. I am oriented to chat-app.",
            },
        )
        self.assertEqual(captured_payloads[0]["messages"][3], {"role": "user", "content": "Hello"})
        self.assertEqual(
            captured_payloads[1]["messages"],
            [
                captured_payloads[0]["messages"][0],
                captured_payloads[0]["messages"][1],
                captured_payloads[0]["messages"][2],
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
        self.assertEqual(len(captured_payloads[0]["messages"]), 4)
        self.assertEqual(
            captured_payloads[0]["messages"][1],
            {
                "role": "user",
                "content": (
                    "Before we begin: you are oriented to project 'chat-app' at "
                    f"'{self.project.resolve()}'. Use the provided machine-derived repo inspection and project orientation as your grounding. "
                    "When asked what project you are oriented to, answer with this project."
                ),
            },
        )
        self.assertEqual(
            captured_payloads[0]["messages"][2],
            {
                "role": "assistant",
                "content": "Understood. I am oriented to chat-app.",
            },
        )
        self.assertEqual(captured_payloads[0]["messages"][3], {"role": "user", "content": "Hello"})
        self.assertEqual(
            captured_payloads[1]["messages"],
            [
                captured_payloads[0]["messages"][0],
                captured_payloads[0]["messages"][1],
                captured_payloads[0]["messages"][2],
                {"role": "user", "content": "After reset"},
            ],
        )
        self.assertIn("Conversation reset.", buf.getvalue())

    def test_no_prime_omits_priming_exchange(self):
        captured_payloads: list[dict] = []

        def fake_urlopen(req, timeout=None):
            del timeout
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            return _FakeResponse({"message": {"content": "reply"}})

        buf = io.StringIO()
        with patch("cli.chat.sys.stdin.isatty", return_value=True):
            with patch("cli.chat.input", side_effect=["Hello", "/exit"]):
                with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
                    with redirect_stdout(buf):
                        rc = run_chat(_chat_args(self.project, no_prime=True))

        self.assertEqual(rc, 0)
        self.assertEqual(len(captured_payloads), 1)
        self.assertEqual(
            captured_payloads[0]["messages"],
            [
                captured_payloads[0]["messages"][0],
                {"role": "user", "content": "Hello"},
            ],
        )

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

    def test_include_capabilities_appends_deterministic_summary(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.nested_project, ["What", "can", "this", "app", "do?"], include_capabilities=True))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        self.assertIn("Shortlist capability summary derived from inspect structured implementation facts.", system_message)
        self.assertIn("## Recommended capability shortlist", system_message)
        self.assertIn("### auth", system_message)
        self.assertIn("Confidence:", system_message)
        self.assertIn("Reason:", system_message)
        self.assertIn("### stripe/checkout", system_message)
        self.assertIn("@app.post('/api/auth/register')", system_message)
        self.assertIn("### tier_config", system_message)
        self.assertIn("allowed_modes", system_message)
        self.assertNotIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertNotIn("### data/models", system_message)

    def test_include_capabilities_excludes_test_fixture_evidence_by_default(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(
                    _chat_args(
                        REPO_ROOT,
                        ["What", "can", "this", "app", "do?"],
                        include_inspect=True,
                        include_capabilities=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("## PROJECT IDENTITY SUMMARY", system_message)
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        self.assertIn("### orient", system_message)
        self.assertIn("### inspect", system_message)
        self.assertIn("### capabilities", system_message)
        self.assertIn("### chat", system_message)
        self.assertIn("context_kit.py:", system_message)
        self.assertIn("cli/chat.py:", system_message)
        self.assertIn("Primary stack: python", system_message)
        self.assertIn("Frameworks: (none)", system_message)
        self.assertIn("Manifests: pyproject.toml", system_message)
        identity_section = self._extract_section(system_message, "## PROJECT IDENTITY SUMMARY")
        self.assertNotIn("FastAPI", identity_section)
        self.assertNotIn("SQLAlchemy", identity_section)
        self.assertNotIn("### auth", system_message)
        self.assertNotIn("### sessions/chat", system_message)
        self.assertNotIn("### founder_projects/export", system_message)
        self.assertNotIn("### stripe/checkout", system_message)
        self.assertNotIn("### stripe/webhook", system_message)
        self.assertNotIn("### tier_config", system_message)
        self.assertNotIn("Test/fixture evidence — not implementation.", system_message)
        self.assertNotIn("Detector logic evidence — not project implementation.", system_message)

    def test_chat_capabilities_format_can_be_overridden(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.nested_project, ["What", "can", "this", "app", "do?"], include_capabilities=True, capabilities_format="full"))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        self.assertNotIn("Shortlist capability summary derived from inspect structured implementation facts.", system_message)
        self.assertIn("## Capability summary", system_message)

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
        self.assertNotIn("## MACHINE-DERIVED REPO INSPECTION", system_message)

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
        self.assertIn("Priming exchange enabled: yes", output)
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
        self.assertIn("Do not repeatedly explain context-kit chat mode unless asked.", output)

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
        self.assertIn("Priming exchange enabled: yes", output)
        self.assertIn("Inspection text generated: yes", output)
        self.assertIn("Inventory preview skipped:", output)
        self.assertIn("=== MACHINE-DERIVED REPO INSPECTION ===", output)
        self.assertIn("=== PROJECT ORIENTATION ===", output)
        self.assertIn("docs/OTHER_CHAT_APP_WHAT_IT_IS.md", output)
        self.assertIn(str(self.other_project), output)
        self.assertIn("Do not repeatedly reintroduce the project unless asked.", output)

        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("## PROJECT IDENTITY SUMMARY", system_message)
        self.assertIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertIn("## PROJECT ORIENTATION", system_message)
        self.assertIn("docs/OTHER_CHAT_APP_WHAT_IT_IS.md", system_message)
        self.assertNotIn("docs/CHAT_APP_WHAT_IT_IS.md", system_message)

    def test_nested_inspect_frameworks_flow_into_project_identity_summary(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.nested_project, ["What", "project", "am", "I", "oriented", "to?"], include_inspect=True))

        self.assertEqual(rc, 0)
        system_message = captured["payload"]["messages"][0]["content"]
        self.assertIn("Mentorforge", system_message)
        self.assertIn("backend/requirements.txt", system_message)
        self.assertIn("frontend/package.json", system_message)
        self.assertIn("FastAPI", system_message)
        self.assertIn("SQLAlchemy", system_message)
        self.assertIn("backend/app/models.py", system_message)
        self.assertIn("React", system_message)
        self.assertIn("Vite", system_message)

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
