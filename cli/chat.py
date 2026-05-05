"""context-kit `chat` subcommand.

Assembles the existing orient prompt, sends it to a local Ollama model,
and either prints a one-shot response or keeps an interactive REPL open
for multi-turn testing.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from pathlib import Path

from . import ollama
from .orient import render_chat_orient, render_orient

STARTUP_LINE = "context-kit chat started. Type /exit to quit."
CHAT_BEHAVIOR_PREAMBLE = (
    "You are running inside context-kit chat mode.\n"
    "Use the project identity summary and machine-derived repo inspection as the highest-signal repo facts.\n"
    "Use the project orientation below for project meaning, source-of-truth rules, and anti-drift behavior.\n"
    "The live user conversation is the current working context.\n"
    "If a machine-derived repo inspection block is present, treat it as factual repo evidence.\n"
    "If orientation and inspection disagree, say so instead of silently switching topics.\n"
    "Do not invent capabilities not present in either the orientation or the inspection.\n"
    'When the user asks "what are we doing/testing/discussing right now", answer from the recent chat messages first.\n'
    "Do not replace the live conversation with the repo's documented NEXT TASK unless the user specifically asks for repo priorities.\n"
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


@dataclass
class SystemPromptBundle:
    project: Path
    include_inspect: bool
    inspect_generated: bool
    inventory_low_signal: bool
    chat_preamble: str
    project_identity_summary: str
    orientation: str
    inspection: str | None
    system_message: str


def run_chat(args: argparse.Namespace) -> int:
    project = _resolve_project_path(getattr(args, "project", None))
    if project is None:
        return 2

    prompt_bundle = _build_system_prompt_bundle(project, args)
    if getattr(args, "debug_prompt", False):
        _print_debug_prompt(prompt_bundle)
    _warn_if_prompt_too_large(prompt_bundle, getattr(args, "prompt_soft_threshold", 20000))

    prompt = _resolve_one_shot_prompt(args)
    if prompt is not None:
        return _run_one_shot(prompt, prompt_bundle.system_message, args)

    if not sys.stdin.isatty():
        sys.stderr.write(
            "error: chat needs a prompt.\n"
            "Pass words after `chat`, pipe input on stdin, or run it in a terminal for interactive mode.\n"
        )
        return 2

    return _run_interactive_session(prompt_bundle.system_message, project, args)


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


def _run_interactive_session(system_message: str, project: Path, args: argparse.Namespace) -> int:
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


def _build_system_message(identity_summary: str, inspect_report: str | None, orientation: str) -> str:
    parts = [CHAT_BEHAVIOR_PREAMBLE, "", identity_summary]
    if inspect_report:
        parts.extend(["", "## MACHINE-DERIVED REPO INSPECTION", inspect_report])
    parts.extend(["", orientation])
    return "\n".join(parts)


def _build_system_prompt_bundle(project: Path, args: argparse.Namespace) -> SystemPromptBundle:
    orientation = render_chat_orient(project)
    inspect_report = None
    inspect_result = None
    if getattr(args, "include_inspect", False):
        from .inspect import render_inspect_markdown

        inspect_result = _inspect_for_chat(project, args)
        inspect_report = render_inspect_markdown(inspect_result)
    identity_summary = _build_project_identity_summary(project, inspect_result)
    inventory_low_signal = _chat_inventory_low_signal(project)
    system_message = _build_system_message(
        identity_summary,
        inspect_report,
        orientation,
    )
    return SystemPromptBundle(
        project=project,
        include_inspect=getattr(args, "include_inspect", False),
        inspect_generated=inspect_report is not None,
        inventory_low_signal=inventory_low_signal,
        chat_preamble=CHAT_BEHAVIOR_PREAMBLE,
        project_identity_summary=identity_summary,
        orientation=orientation,
        inspection=inspect_report,
        system_message=system_message,
    )


def _print_debug_prompt(bundle: SystemPromptBundle) -> None:
    inspect_generated = "yes" if bundle.inspect_generated else "no"
    inspection_count = len(bundle.inspection or "")
    total_count = len(bundle.system_message)
    print(f"Resolved project path: {bundle.project}")
    print(f"--include-inspect enabled: {'yes' if bundle.include_inspect else 'no'}")
    print(f"Inspection text generated: {inspect_generated}")
    print(f"Inventory preview skipped: {'yes' if bundle.inventory_low_signal else 'no'}")
    print(f"Character counts:")
    print(f"  chat preamble: {len(bundle.chat_preamble)}")
    print(f"  project identity summary: {len(bundle.project_identity_summary)}")
    print(f"  orientation: {len(bundle.orientation)}")
    print(f"  inspection: {inspection_count}")
    print(f"  total system prompt: {total_count}")
    print("")
    print("=== CHAT PREAMBLE ===")
    print(bundle.chat_preamble.rstrip())
    print("")
    print("=== PROJECT IDENTITY SUMMARY ===")
    print(bundle.project_identity_summary.rstrip())
    print("")
    print("=== MACHINE-DERIVED REPO INSPECTION ===")
    if bundle.include_inspect and bundle.inspection:
        print(bundle.inspection.rstrip())
    else:
        print("inspection not included")
    print("")
    print("=== PROJECT ORIENTATION ===")
    print(bundle.orientation.rstrip())
    print("")


def _warn_if_prompt_too_large(bundle: SystemPromptBundle, soft_threshold: int) -> None:
    if soft_threshold <= 0:
        return
    total_count = len(bundle.system_message)
    if total_count > soft_threshold:
        sys.stderr.write(
            f"warning: chat system prompt is {total_count} chars, exceeding soft threshold {soft_threshold}\n"
        )


def _build_project_identity_summary(project: Path, inspect_result) -> str:
    lines = ["## PROJECT IDENTITY SUMMARY"]
    lines.append(f"- Project path: `{project}`")
    lines.append(f"- Project name: `{project.name}`")
    if inspect_result is None:
        lines.append("- Machine-derived repo facts: not included")
        return "\n".join(lines)

    lines.append(f"- Repo name: `{inspect_result.repo}`")
    primary_stack = inspect_result.primary_stack or {}
    languages = ", ".join(primary_stack.get("languages", [])) or "(unknown)"
    frameworks = ", ".join(primary_stack.get("frameworks", [])) or "(none)"
    manifests = ", ".join(primary_stack.get("manifests", [])) or "(none)"
    lines.append(f"- Primary stack: {languages}")
    lines.append(f"- Frameworks: {frameworks}")
    lines.append(f"- Manifests: {manifests}")
    if inspect_result.head:
        branch = inspect_result.head.get("branch") or "(unknown)"
        sha = inspect_result.head.get("sha") or "(unknown)"
        lines.append(f"- Git branch: `{branch}`")
        lines.append(f"- Latest commit hash: `{sha}`")
    else:
        lines.append("- Git branch: (not a git repo)")
        lines.append("- Latest commit hash: (not available)")
    return "\n".join(lines)


def _chat_inventory_low_signal(project: Path) -> bool:
    try:
        from .orient import _find_anchor_docs, _is_low_signal_inventory
    except ImportError:
        return False

    _, inventory = _find_anchor_docs(project)
    return inventory is not None and _is_low_signal_inventory(inventory)


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


def _resolve_project_path(project_value: str | None) -> Path | None:
    project = Path(project_value).expanduser().resolve() if project_value else Path.cwd().resolve()
    if not project.exists():
        sys.stderr.write(f"error: --project path does not exist: {project}\n")
        return None
    if not project.is_dir():
        sys.stderr.write(f"error: --project path is not a directory: {project}\n")
        return None
    if not _looks_like_context_kit_project(project):
        sys.stderr.write(
            f"error: --project path does not look like a context-kit project: {project}\n"
            "  Expected to find '00-START-NEXT-SESSION.md' or 'docs/docs-pattern/' here.\n"
        )
        return None
    return project


def _inspect_for_chat(project: Path, args: argparse.Namespace):
    from .inspect import _inspect

    return _inspect(
        project,
        depth=getattr(args, "inspect_depth", 2),
        scope=None,
        include_related=False,
        include_history=False,
    )
