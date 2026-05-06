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
    user=None,
    include_inspect=False,
    include_capabilities=False,
    include_doctor=False,
    include_hotpath=False,
    include_behavior=False,
    no_auto_context=False,
    capabilities_format="shortlist",
    debug_prompt=False,
    prompt_soft_threshold=20000,
    no_prime=False,
    no_task_wrapper=False,
):
    return argparse.Namespace(
        command="chat",
        project=str(project) if project is not None else None,
        model=model,
        user=user,
        prompt=prompt,
        include_inspect=include_inspect,
        include_capabilities=include_capabilities,
        include_doctor=include_doctor,
        include_hotpath=include_hotpath,
        include_behavior=include_behavior,
        no_auto_context=no_auto_context,
        capabilities_format=capabilities_format,
        debug_prompt=debug_prompt,
        prompt_soft_threshold=prompt_soft_threshold,
        no_prime=no_prime,
        no_task_wrapper=no_task_wrapper,
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
        (self.project / "docs" / "CHAT_APP_TRANSLATION_LAYER.md").write_text(
            "# TRANSLATION LAYER\n"
            "| Persona | Notes |\n"
            "| Jessica (operator) | business reviewer |\n"
            "| Chris (builder) | engineer |\n",
            encoding="utf-8",
        )
        (self.other_project / "docs" / "OTHER_CHAT_APP_TRANSLATION_LAYER.md").write_text(
            "# TRANSLATION LAYER\n"
            "| Persona | Notes |\n"
            "| Chris (builder) | engineer |\n",
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

    def _payload_text(self, captured: dict) -> str:
        return "\n".join(message["content"] for message in captured["payload"]["messages"])

    def _wrap_user_task(self, user_text: str) -> str:
        return (
            "USER_TASK_START\n"
            "Treat the following as one complete user task.\n"
            "Do not split numbered lists or bullet rules into separate turns.\n"
            "Do not roleplay audiences unless explicitly requested.\n"
            "Answer once, then stop.\n"
            "USER_TASK:\n\n"
            f"{user_text}\n\n"
            "USER_TASK_END"
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
        self.assertIn("Answer the user's current question directly.", payload["messages"][0]["content"])
        self.assertIn("Do not repeatedly introduce yourself.", payload["messages"][0]["content"])
        self.assertIn("Do not ask \"what would you like to discuss?\"", payload["messages"][0]["content"])
        self.assertIn(
            "If the user asks what project you are oriented to, answer once with the project name/path and stop.",
            payload["messages"][0]["content"],
        )
        self.assertIn("If the user sends a multi-part request, treat the entire message as ONE task unless the user explicitly separates future turns.", payload["messages"][0]["content"])
        self.assertIn("\"Explain to X audience\" does not mean simulate a live conversation with that audience.", payload["messages"][0]["content"])
        self.assertIn("Do not continue audience simulations after the requested answer is complete.", payload["messages"][0]["content"])
        self.assertIn("After answering a structured request, return to neutral assistant mode.", payload["messages"][0]["content"])
        self.assertIn("Never continue the conversation by answering your own previous outputs.", payload["messages"][0]["content"])
        self.assertIn("Never generate follow-up user prompts.", payload["messages"][0]["content"])
        self.assertIn("Never simulate multi-party dialogue unless explicitly requested.", payload["messages"][0]["content"])
        self.assertIn("After a completed response, stop cleanly.", payload["messages"][0]["content"])
        self.assertIn("Do not append \"What would you like to discuss?\", \"As a CTO...\", or \"Let's continue...\" unless the user explicitly asked for interactive simulation.", payload["messages"][0]["content"])
        self.assertIn("Audience adaptation changes framing only, not factual certainty.", payload["messages"][0]["content"])
        self.assertIn("Translation-layer explanations must preserve implementation confidence, speculation labels, and evidence boundaries.", payload["messages"][0]["content"])
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
        self.assertIn(
            "For \"what can this app do?\" questions, answer only from DETERMINISTIC CAPABILITY SUMMARY when it is present.",
            payload["messages"][0]["content"],
        )
        self.assertIn(
            "Summarize the Recommended capability shortlist first only when the user has not requested shortlist-only mode.",
            payload["messages"][0]["content"],
        )
        self.assertIn("Do not omit high-confidence capabilities from the shortlist unless the user asks for a narrower answer.", payload["messages"][0]["content"])
        self.assertIn("Use MACHINE-DERIVED REPO INSPECTION for details only when capabilities are missing.", payload["messages"][0]["content"])
        self.assertIn("Do not override deterministic capability evidence with orientation claims.", payload["messages"][0]["content"])
        self.assertIn("When summarizing deterministic capabilities, preserve Confidence and Reason exactly; do not upgrade confidence from orientation or inspection.", payload["messages"][0]["content"])
        self.assertIn(
            "If the user asks \"what can this project do\", \"what can context-kit do\", \"what capabilities exist\", or \"what can this do for me\" and DETERMINISTIC CAPABILITY SUMMARY exists, answer ONLY from that section.",
            payload["messages"][0]["content"],
        )
        self.assertIn(
            "Do not synthesize from orientation, repo inspection, stack/framework detection, or the mere presence of inspect/capabilities commands.",
            payload["messages"][0]["content"],
        )
        self.assertIn(
            "Do not infer unused code detection, optimization suggestions, maintainability analysis, performance analysis, modularization analysis, or architecture recommendations unless they are explicitly present in DETERMINISTIC CAPABILITY SUMMARY.",
            payload["messages"][0]["content"],
        )
        self.assertIn(
            "Capability answers must render as: command name, literal detected type, evidence, confidence.",
            payload["messages"][0]["content"],
        )
        self.assertIn("No narrative paragraph before or after.", payload["messages"][0]["content"])
        self.assertIn("For capability questions, prefer route/decorator evidence over request model evidence.", payload["messages"][0]["content"])
        self.assertIn("Request/response models support shape, not user-facing capability.", payload["messages"][0]["content"])
        self.assertIn("Do not cite BaseModel classes as primary capability evidence when route evidence exists.", payload["messages"][0]["content"])
        self.assertIn("Command names are not product promises.", payload["messages"][0]["content"])
        self.assertIn("Do not infer business value, automation, collaboration, AI intelligence, optimization, orchestration, or workflow impact unless explicitly evidenced.", payload["messages"][0]["content"])
        self.assertIn("Do not infer user benefit from command names.", payload["messages"][0]["content"])
        self.assertIn("Do not infer productivity gains.", payload["messages"][0]["content"])
        self.assertIn("Do not infer automation level.", payload["messages"][0]["content"])
        self.assertIn("Do not infer AI capabilities.", payload["messages"][0]["content"])
        self.assertIn("Do not infer orchestration or intelligence.", payload["messages"][0]["content"])
        self.assertIn("Do not infer workflow streamlining or collaboration enhancement.", payload["messages"][0]["content"])
        self.assertIn("Prefer literal implementation-grounded summaries like \"The repo exposes a connections CLI command.\" over marketing-style summaries.", payload["messages"][0]["content"])
        self.assertIn("Avoid phrases like \"facilitates collaboration\" or \"architecture intelligence\" unless the injected evidence explicitly says that.", payload["messages"][0]["content"])
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
        self.assertEqual(payload["messages"][1], {"role": "user", "content": self._wrap_user_task("How do I start?")})
        self.assertIn("ollama says hello", buf.getvalue())

    def test_structured_task_boundary_rules_are_in_prompt(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        [
                            "Explain",
                            "context-kit",
                            "to",
                            "a",
                            "junior",
                            "developer,",
                            "a",
                            "CTO,",
                            "and",
                            "a",
                            "non-technical",
                            "operations",
                            "manager.",
                        ],
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("If the user sends a multi-part request, treat the entire message as ONE task unless the user explicitly separates future turns.", system_message)
        self.assertIn("\"Explain to X audience\" does not mean simulate a live conversation with that audience.", system_message)
        self.assertIn("Do not continue audience simulations after the requested answer is complete.", system_message)
        self.assertIn("After answering a structured request, return to neutral assistant mode.", system_message)
        self.assertIn("Never continue the conversation by answering your own previous outputs.", system_message)
        self.assertIn("Never generate follow-up user prompts.", system_message)
        self.assertIn("Never simulate multi-party dialogue unless explicitly requested.", system_message)
        self.assertIn("After a completed response, stop cleanly.", system_message)
        self.assertIn("Audience adaptation changes framing only, not factual certainty.", system_message)
        self.assertIn("Translation-layer explanations must preserve implementation confidence, speculation labels, and evidence boundaries.", system_message)
        self.assertIn("Do not append \"What would you like to discuss?\", \"As a CTO...\", or \"Let's continue...\" unless the user explicitly asked for interactive simulation.", system_message)

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
        self.assertEqual(
            captured_payloads[0]["messages"][3],
            {"role": "user", "content": self._wrap_user_task("Hello")},
        )
        self.assertEqual(
            captured_payloads[1]["messages"],
            [
                captured_payloads[0]["messages"][0],
                captured_payloads[0]["messages"][1],
                captured_payloads[0]["messages"][2],
                {"role": "user", "content": self._wrap_user_task("Hello")},
                {"role": "assistant", "content": "reply 1"},
                {"role": "user", "content": self._wrap_user_task("How are you?")},
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
        self.assertEqual(
            captured_payloads[0]["messages"][3],
            {"role": "user", "content": self._wrap_user_task("Hello")},
        )
        self.assertEqual(
            captured_payloads[1]["messages"],
            [
                captured_payloads[0]["messages"][0],
                captured_payloads[0]["messages"][1],
                captured_payloads[0]["messages"][2],
                {"role": "user", "content": self._wrap_user_task("After reset")},
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
                {"role": "user", "content": self._wrap_user_task("Hello")},
            ],
        )

    def test_one_shot_no_task_wrapper_sends_raw_text(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "reply"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.project, ["Hello"], no_task_wrapper=True))

        self.assertEqual(rc, 0)
        self.assertEqual(
            captured["payload"]["messages"],
            [
                captured["payload"]["messages"][0],
                {"role": "user", "content": "Hello"},
            ],
        )

    def test_persona_match_injects_translation_layer_context(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "reply"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["Explain", "context-kit"],
                        user="Jessica",
                        include_capabilities=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("## PERSONA MODE", system_message)
        self.assertIn("Requested user: Jessica", system_message)
        self.assertIn("Matched persona: Jessica (operator)", system_message)
        self.assertIn("Adjust explanation tone, framing, and priorities for this persona.", system_message)
        self.assertIn("Do not change facts; only change explanation style.", system_message)
        self.assertIn("If you cannot translate without inventing or implying unsupported facts, fall back to neutral.", system_message)
        self.assertIn("Persona changes framing only; it must not override evidence, confidence, or tool boundaries.", system_message)
        self.assertIn("Translation-layer context must not invent capabilities.", system_message)
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)

    def test_no_task_wrapper_sends_raw_user_text(self):
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
                        rc = run_chat(_chat_args(self.project, no_task_wrapper=True))

        self.assertEqual(rc, 0)
        self.assertEqual(len(captured_payloads), 1)
        self.assertEqual(
            captured_payloads[0]["messages"],
            [
                captured_payloads[0]["messages"][0],
                captured_payloads[0]["messages"][1],
                captured_payloads[0]["messages"][2],
                {"role": "user", "content": "Hello"},
            ],
        )

    def test_persona_unmatched_stays_neutral(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "reply"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(
                    _chat_args(
                        self.other_project,
                        ["Explain", "context-kit"],
                        user="Jessica",
                        include_capabilities=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertNotIn("## PERSONA MODE", system_message)
        self.assertNotIn("Matched persona:", system_message)
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)

    def test_debug_prompt_reports_persona_match_status(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "reply"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["Explain", "context-kit"],
                        user="Jessica",
                        include_capabilities=True,
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("Persona requested: Jessica", output)
        self.assertIn("Persona match status: matched", output)
        self.assertIn("Matched persona: Jessica (operator)", output)
        self.assertIn("=== PERSONA MODE ===", output)
        self.assertIn("Translation-layer context must not invent capabilities.", output)

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
        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        self.assertIn("Shortlist capability summary derived from inspect structured implementation facts.", system_message)
        self.assertIn("## Capability answer contract", system_message)
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

    def test_include_startup_snapshot_blocks_inject_sections(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with (
            patch("cli.chat._build_doctor_report", return_value="doctor snapshot\n"),
            patch("cli.chat._build_hotpath_report", return_value="hotpath snapshot\n"),
            patch("cli.chat._build_behavior_report", return_value="behavior snapshot\n"),
            patch("cli.ollama.request.urlopen", side_effect=fake_urlopen),
        ):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["What", "do", "you", "see?"],
                        include_doctor=True,
                        include_hotpath=True,
                        include_behavior=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("Included command outputs are startup snapshots captured before chat begins; they are not live state after chat starts.", system_message)
        self.assertIn("## DOCTOR DIAGNOSTICS", system_message)
        self.assertIn("doctor snapshot", system_message)
        self.assertIn("## HOTPATH SUMMARY", system_message)
        self.assertIn("hotpath snapshot", system_message)
        self.assertIn("## BEHAVIOR LAYER SUMMARY", system_message)
        self.assertIn("behavior snapshot", system_message)

    def test_omitted_startup_snapshot_flags_preserve_current_behavior(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(_chat_args(self.project, ["What", "do", "you", "see?"]))

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertNotIn("## DOCTOR DIAGNOSTICS", system_message)
        self.assertNotIn("## HOTPATH SUMMARY", system_message)
        self.assertNotIn("## BEHAVIOR LAYER SUMMARY", system_message)

    def test_shortlist_only_developer_prompt_is_source_bound(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(io.StringIO()):
                rc = run_chat(
                    _chat_args(
                        self.nested_project,
                        [
                            "Explain",
                            "what",
                            "context-kit",
                            "can",
                            "actually",
                            "do",
                            "for",
                            "me",
                            "as",
                            "a",
                            "developer.",
                            "Use",
                            "only",
                            "the",
                            "capability",
                            "shortlist.",
                        ],
                        include_inspect=True,
                        include_capabilities=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn(
            "If the user asks \"what can this project do\", \"what can context-kit do\", \"what capabilities exist\", or \"what can this do for me\" and DETERMINISTIC CAPABILITY SUMMARY exists, answer ONLY from that section.",
            system_message,
        )
        self.assertIn(
            "Do not synthesize from orientation, repo inspection, stack/framework detection, or the mere presence of inspect/capabilities commands.",
            system_message,
        )
        self.assertIn(
            "Do not infer unused code detection, optimization suggestions, maintainability analysis, performance analysis, modularization analysis, or architecture recommendations unless they are explicitly present in DETERMINISTIC CAPABILITY SUMMARY.",
            system_message,
        )
        self.assertIn(
            "If the user says \"use only the capability shortlist\", ignore orientation, repo inspection, inferred repo identity, and framework indicators except evidence lines already present in the shortlist.",
            system_message,
        )
        self.assertIn("Capability answers must render as: command name, literal detected type, evidence, confidence.", system_message)
        self.assertIn("No narrative paragraph before or after.", system_message)
        self.assertIn("## Capability answer contract", system_message)
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        self.assertIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertIn("## PROJECT ORIENTATION", system_message)

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
        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
        self.assertNotIn("## MACHINE-DERIVED REPO INSPECTION", system_message)

    def test_auto_context_routes_capability_questions_to_shortlist(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.nested_project,
                        ["What", "can", "this", "project", "do", "for", "me", "as", "a", "developer?"],
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("## AUTO CONTEXT (this turn only)", system_message)
        self.assertIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        self.assertIn("## Capability answer contract", system_message)
        self.assertNotIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertNotIn("## DOCTOR DIAGNOSTICS", system_message)
        self.assertNotIn("## HOTPATH SUMMARY", system_message)
        self.assertNotIn("## BEHAVIOR LAYER SUMMARY", system_message)
        output = stdout.getvalue()
        self.assertIn("Auto-context query type: capability", output)
        self.assertIn("Auto-context routing: enabled", output)
        self.assertIn("Auto-injected sections: capabilities", output)
        self.assertIn("Skipped sections: inspect, doctor, hotpath, behavior", output)

    def test_no_auto_context_disables_routing(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.nested_project,
                        ["What", "can", "this", "project", "do", "for", "me?"],
                        no_auto_context=True,
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertNotIn("## AUTO CONTEXT (this turn only)", system_message)
        self.assertNotIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        output = stdout.getvalue()
        self.assertIn("Auto-context routing: disabled", output)

    def test_auto_context_routes_repo_structure_questions_to_inspect(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["Show", "me", "the", "repo", "structure", "and", "key", "files."],
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("## AUTO CONTEXT (this turn only)", system_message)
        self.assertIn("## MACHINE-DERIVED REPO INSPECTION", system_message)
        self.assertNotIn("## DETERMINISTIC CAPABILITY SUMMARY", system_message)
        output = stdout.getvalue()
        self.assertIn("Auto-context query type: inspect", output)
        self.assertIn("Auto-injected sections: inspect", output)

    def test_auto_context_routes_diagnostics_questions_to_doctor(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["I", "need", "diagnostics", "and", "setup", "help."],
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("## AUTO CONTEXT (this turn only)", system_message)
        self.assertIn("## DOCTOR DIAGNOSTICS", system_message)
        output = stdout.getvalue()
        self.assertIn("Auto-context query type: doctor", output)
        self.assertIn("Auto-injected sections: doctor", output)

    def test_auto_context_routes_persona_questions_to_behavior_layer(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with patch("cli.ollama.request.urlopen", side_effect=fake_urlopen):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["How", "should", "I", "explain", "this", "to", "a", "CTO?"],
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        system_message = self._payload_text(captured)
        self.assertIn("## AUTO CONTEXT (this turn only)", system_message)
        self.assertIn("## BEHAVIOR LAYER SUMMARY", system_message)
        output = stdout.getvalue()
        self.assertIn("Auto-context query type: behavior", output)
        self.assertIn("Auto-injected sections: behavior", output)

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

    def test_debug_prompt_reports_startup_snapshot_sections(self):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            del timeout
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            return _FakeResponse({"message": {"content": "ok"}})

        stdout = io.StringIO()
        with (
            patch("cli.chat._build_doctor_report", return_value="doctor snapshot\n"),
            patch("cli.chat._build_hotpath_report", return_value="hotpath snapshot\n"),
            patch("cli.chat._build_behavior_report", return_value="behavior snapshot\n"),
            patch("cli.ollama.request.urlopen", side_effect=fake_urlopen),
        ):
            with redirect_stdout(stdout):
                rc = run_chat(
                    _chat_args(
                        self.project,
                        ["Explain", "context-kit"],
                        include_doctor=True,
                        include_hotpath=True,
                        include_behavior=True,
                        debug_prompt=True,
                    )
                )

        self.assertEqual(rc, 0)
        output = stdout.getvalue()
        self.assertIn("--include-doctor enabled: yes", output)
        self.assertIn("--include-hotpath enabled: yes", output)
        self.assertIn("--include-behavior enabled: yes", output)
        self.assertIn("Doctor diagnostics generated: yes", output)
        self.assertIn("Hotpath summary generated: yes", output)
        self.assertIn("Behavior layer summary generated: yes", output)
        self.assertIn("doctor diagnostics:", output)
        self.assertIn("hotpath summary:", output)
        self.assertIn("behavior layer summary:", output)
        self.assertIn("=== DOCTOR DIAGNOSTICS ===", output)
        self.assertIn("doctor snapshot", output)
        self.assertIn("=== HOTPATH SUMMARY ===", output)
        self.assertIn("hotpath snapshot", output)
        self.assertIn("=== BEHAVIOR LAYER SUMMARY ===", output)
        self.assertIn("behavior snapshot", output)

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

        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
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
        system_message = self._payload_text(captured)
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
