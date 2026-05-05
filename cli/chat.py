"""context-kit `chat` subcommand.

Assembles the existing orient prompt, sends it to a local Ollama model,
and either prints a one-shot response or keeps an interactive REPL open
for multi-turn testing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ollama
from .orient import render_orient

STARTUP_LINE = "context-kit chat started. Type /exit to quit."
CHAT_BEHAVIOR_PREAMBLE = (
    "You are running inside context-kit chat mode.\n"
    "Use the project orientation below as grounding, not as the only topic of conversation.\n"
    "The live user conversation is the current working context.\n"
    'When the user asks "what are we doing/testing/discussing right now", answer from the recent chat messages first.\n'
    "Use the orientation to preserve project rules, source-of-truth hierarchy, and anti-drift behavior.\n"
    "Do not replace the live conversation with the repo's documented NEXT TASK unless the user specifically asks for repo priorities.\n"
    "If live conversation and orientation conflict, explain the conflict instead of silently switching topics.\n"
    "Do not invent repo facts or stats."
)
HELP_TEXT = (
    "Commands:\n"
    "  /help   Show this help text\n"
    "  /reset  Clear conversation history but keep the orientation\n"
    "  /orient Show the current orientation summary\n"
    "  /exit   Quit the chat\n"
    "  /quit   Quit the chat"
)


def run_chat(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if getattr(args, "project", None) else Path.cwd().resolve()
    if not _looks_like_context_kit_project(project):
        print(
            f"context-kit: {project} doesn't look like a context-kit project.\n"
            f"  Expected to find '00-START-NEXT-SESSION.md' or 'docs/docs-pattern/' here.\n"
            f"  Run from inside a project scaffolded with `context-kit init`,\n"
            f"  or pass --project PATH.",
        )
        return 2

    orientation = render_orient(project, short=False)
    system_message = _build_system_message(orientation)
    prompt = _resolve_one_shot_prompt(args)
    if prompt is not None:
        return _run_one_shot(prompt, system_message, args)

    if not sys.stdin.isatty():
        sys.stderr.write(
            "error: chat needs a prompt.\n"
            "Pass words after `chat`, pipe input on stdin, or run it in a terminal for interactive mode.\n"
        )
        return 2

    return _run_interactive_session(system_message, orientation, args)


def _run_one_shot(prompt: str, system_message: str, args: argparse.Namespace) -> int:
    try:
        response = ollama.chat(
            system_message,
            prompt,
            model=getattr(args, "model", None),
        )
    except ollama.OllamaError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    print(response.rstrip())
    return 0


def _run_interactive_session(system_message: str, orientation: str, args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if getattr(args, "project", None) else Path.cwd().resolve()
    messages: list[dict[str, str]] = [{"role": "system", "content": system_message}]
    print(STARTUP_LINE)
    while True:
        try:
            line = input("chat> ")
        except EOFError:
            return 0

        line = line.strip()
        if not line:
            continue
        if line in {"/exit", "/quit"}:
            return 0
        if line == "/help":
            print(HELP_TEXT)
            continue
        if line == "/reset":
            messages = [messages[0]]
            print("Conversation reset.")
            continue
        if line == "/orient":
            print(render_orient(project, short=True).rstrip())
            continue
        messages.append({"role": "user", "content": line})
        try:
            response = ollama.chat_messages(
                messages,
                model=getattr(args, "model", None),
            )
        except ollama.OllamaError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        messages.append({"role": "assistant", "content": response})
        print(response.rstrip())


def _build_system_message(orientation: str) -> str:
    return f"{CHAT_BEHAVIOR_PREAMBLE}\n\nProject orientation:\n{orientation}"


def _resolve_one_shot_prompt(args: argparse.Namespace) -> str | None:
    parts = getattr(args, "prompt", None) or []
    if parts:
        prompt = " ".join(parts).strip()
        return prompt if prompt else None
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        return prompt if prompt else None
    return None


def _looks_like_context_kit_project(project: Path) -> bool:
    return (project / "00-START-NEXT-SESSION.md").is_file() or (project / "docs" / "docs-pattern").is_dir()
