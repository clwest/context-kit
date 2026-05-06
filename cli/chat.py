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
from .capabilities import render_capabilities_markdown
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
    "Machine-detected repo facts may only come from the MACHINE-DERIVED REPO INSPECTION section.\n"
    "Documented orientation may only come from PROJECT ORIENTATION.\n"
    "Do not copy orientation claims into machine-detected facts.\n"
    "If inspection detects routes, models, env keys, Dockerfiles, or manifests, list those concrete items.\n"
    "If a feature is inferred from a route, say 'route evidence suggests...' instead of 'implements'.\n"
    "If a claim appears only in orientation, label it as documented orientation, not machine-detected.\n"
    "If neither inspection nor orientation supports a claim, label it speculation or unknown.\n"
    "Prefer 'detected' / 'documented' / 'suggests' over confident product claims.\n"
    "When listing machine-detected repo facts, include evidence in parentheses.\n"
    "Machine-detected facts must be based only on inspect lines with file paths, route decorators, models, env keys, Dockerfiles, manifests, or detected framework indicators.\n"
    "If a claim comes from PROJECT ORIENTATION only, label it \"Documented orientation claim\".\n"
    "If a feature is inferred from route evidence, label it \"Route evidence suggests...\".\n"
    "If no file/path/route/model/env evidence exists, do not put it under machine-detected facts.\n"
    "Prefer concrete implementation evidence over product summaries.\n"
    "Never invent file:line citations.\n"
    "Only use line numbers that appear in MACHINE-DERIVED REPO INSPECTION.\n"
    "If a file is known but no line is provided, cite only the file path.\n"
    "Do not cite line numbers from user-provided memory or inference.\n"
    "Prefer structured implementation facts when answering \"what can this app do?\".\n"
    "When capability labels are derived from route groups, use the phrase \"evidence suggests\".\n"
    "For \"what can this app do?\" questions, prefer DETERMINISTIC CAPABILITY SUMMARY first.\n"
    "Summarize the Recommended capability shortlist first.\n"
    "Do not omit high-confidence capabilities from the shortlist unless the user asks for a narrower answer.\n"
    "Use MACHINE-DERIVED REPO INSPECTION for details only when capabilities are missing.\n"
    "Do not override deterministic capability evidence with orientation claims.\n"
    "When summarizing deterministic capabilities, preserve Confidence and Reason exactly; do not upgrade confidence from orientation or inspection.\n"
    "If DETERMINISTIC CAPABILITY SUMMARY is present, it may be shortlist-only; treat it as the primary capability source.\n"
    "Treat DETERMINISTIC CAPABILITY SUMMARY as compact capability-focused evidence, not raw inspect output.\n"
    "Prefer its best evidence and ignore model-heavy lines unless no better evidence exists.\n"
    "Capability summaries are static snapshots from startup, not live repo state.\n"
    "Do not describe injected context as \"latest repo changes\" unless git diff/log data is explicitly present.\n"
    "A detected route proves endpoint presence only, not internal implementation correctness.\n"
    "Do not claim security validation, payment completion, business logic correctness, or test status from route evidence alone.\n"
    "If asked to verify implementation details, say you cannot verify from the injected capability summary and suggest the user run or paste a relevant command or include raw inspect/file content.\n"
    "With --include-capabilities only, do not claim to know internals beyond capability labels, evidence, confidence, and reason.\n"
    "If the user asks about live repo state, latest changes, recent changes, current test status, git diff, git log, uncommitted changes, or whether something is true \"right now\", do not answer from startup summaries.\n"
    "Never infer \"no changes\" or \"nothing changed\" from absent evidence.\n"
    "Only answer live-state questions if explicit git diff/log/status/test output was injected or pasted in the live conversation.\n"
    "Otherwise say: \"I can’t verify live repo state from the injected startup context.\"\n"
    "Suggest specific commands: git status, git log --oneline -5, context-kit inspect --project <path>, context-kit capabilities --project <path> --format shortlist, and a test command if known; otherwise say no test command is known from context.\n"
    "For capability questions, prefer route/decorator evidence over request model evidence.\n"
    "Request/response models support shape, not user-facing capability.\n"
    "Do not cite BaseModel classes as primary capability evidence when route evidence exists.\n"
    "Do not treat detector/self-analysis code as project implementation evidence unless detector evidence was explicitly requested.\n"
    "You cannot execute shell commands or context-kit commands from inside this chat.\n"
    "You only know the project context injected when chat started plus live conversation history.\n"
    "Do not claim you can run commands, inspect files, access repositories, read additional files, or fetch updated state.\n"
    "If the user asks what commands you have access to, say: \"I cannot run commands from inside this chat. You can run context-kit commands in your terminal and paste or inject the results.\"\n"
    "You may suggest terminal commands for the user to run.\n"
    "Use wording like \"I was given\" or \"the injected context says,\" not \"I can execute\".\n"
    "Never simulate running commands.\n"
    "Never write fake terminal output.\n"
    "Never say \"Running...\" unless a real tool execution occurred, which chat mode cannot do.\n"
    "Never invent command results, git recency, commit timing, test status, file contents, or repo changes.\n"
    "If the user asks you to run a command, respond: \"I can’t run commands from inside this chat. You can run: <suggested command>\"\n"
    "If the user asks for latest, recent, or live state, respond: \"I can’t verify live repo state from injected startup context.\"\n"
    "You may explain what the command would be used for, but not what it returned.\n"
    "If command output is pasted by the user, then you may summarize that pasted output.\n"
    "Bad: \"Running context-kit inspect... No recent commits detected.\"\n"
    "Good: \"I can’t run that here. Please run `context-kit inspect --project <path>` and paste the output.\"\n"
    "Answer the user's current question directly.\n"
    "Do not repeatedly introduce yourself.\n"
    "Do not repeatedly reintroduce the project unless asked.\n"
    "Do not repeatedly explain context-kit chat mode unless asked.\n"
    "Do not summarize orientation or inspection unless the user asks.\n"
    "Avoid recursive conversational framing.\n"
    "Treat prior assistant onboarding text as low-priority context.\n"
    "Prefer concise answers unless the user asks for depth.\n"
    "Do not ask \"what would you like to discuss?\" unless the user explicitly asks for brainstorming or open-ended exploration.\n"
    "If the user asks what project you are oriented to, answer once with the project name/path and stop.\n"
    'When the user asks "what are we doing/testing/discussing right now", answer from the recent chat messages first.\n'
    'When the user asks "what can this project do", answer in this order: 1. Structured implementation facts / machine-detected implementation evidence 2. Documented orientation claims 3. Inferred capabilities 4. Unknowns / needs verification.\n'
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
    include_capabilities: bool
    inspect_generated: bool
    capabilities_generated: bool
    inventory_low_signal: bool
    prime_enabled: bool
    chat_preamble: str
    project_identity_summary: str
    orientation: str
    inspection: str | None
    capabilities: str | None
    system_message: str
    prime_messages: list[dict[str, str]]


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

    return _run_interactive_session(prompt_bundle, args)


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


def _run_interactive_session(bundle: SystemPromptBundle, args: argparse.Namespace) -> int:
    messages: list[dict[str, str]] = [{"role": "system", "content": bundle.system_message}]
    messages.extend(bundle.prime_messages)
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
            messages = [messages[0], *bundle.prime_messages]
            print("Conversation reset.")
            continue
        if line == "/orient":
            print(render_orient(bundle.project, short=True).rstrip())
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
    capabilities_report = None
    if getattr(args, "include_inspect", False):
        from .inspect import render_inspect_markdown

        inspect_result = _inspect_for_chat(project, args)
        inspect_report = render_inspect_markdown(inspect_result)
    if getattr(args, "include_capabilities", False):
        capabilities_report = _build_capabilities_report(project, args, inspect_result)
    identity_summary = _build_project_identity_summary(project, inspect_result)
    inventory_low_signal = _chat_inventory_low_signal(project)
    prime_enabled = not getattr(args, "no_prime", False)
    prime_messages = _build_prime_messages(project) if prime_enabled else []
    system_message = _build_system_message(
        identity_summary,
        inspect_report,
        orientation,
    )
    if capabilities_report:
        system_message = "\n".join([system_message, "", "## DETERMINISTIC CAPABILITY SUMMARY", capabilities_report])
    return SystemPromptBundle(
        project=project,
        include_inspect=getattr(args, "include_inspect", False),
        include_capabilities=getattr(args, "include_capabilities", False),
        inspect_generated=inspect_report is not None,
        capabilities_generated=capabilities_report is not None,
        inventory_low_signal=inventory_low_signal,
        prime_enabled=prime_enabled,
        chat_preamble=CHAT_BEHAVIOR_PREAMBLE,
        project_identity_summary=identity_summary,
        orientation=orientation,
        inspection=inspect_report,
        capabilities=capabilities_report,
        system_message=system_message,
        prime_messages=prime_messages,
    )


def _print_debug_prompt(bundle: SystemPromptBundle) -> None:
    inspect_generated = "yes" if bundle.inspect_generated else "no"
    inspection_count = len(bundle.inspection or "")
    total_count = len(bundle.system_message)
    print(f"Resolved project path: {bundle.project}")
    print(f"--include-inspect enabled: {'yes' if bundle.include_inspect else 'no'}")
    print(f"--include-capabilities enabled: {'yes' if bundle.include_capabilities else 'no'}")
    print(f"Priming exchange enabled: {'yes' if bundle.prime_enabled else 'no'}")
    print(f"Inspection text generated: {inspect_generated}")
    print(f"Capability summary generated: {'yes' if bundle.capabilities_generated else 'no'}")
    print(f"Inventory preview skipped: {'yes' if bundle.inventory_low_signal else 'no'}")
    print(f"Character counts:")
    print(f"  chat preamble: {len(bundle.chat_preamble)}")
    print(f"  project identity summary: {len(bundle.project_identity_summary)}")
    print(f"  orientation: {len(bundle.orientation)}")
    print(f"  inspection: {inspection_count}")
    print(f"  capabilities: {len(bundle.capabilities or '')}")
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
    print("=== DETERMINISTIC CAPABILITY SUMMARY ===")
    if bundle.include_capabilities and bundle.capabilities:
        print(bundle.capabilities.rstrip())
    else:
        print("capability summary not included")
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


def _build_capabilities_report(project: Path, args: argparse.Namespace, inspect_result) -> str | None:
    from .inspect import _inspect

    if inspect_result is None:
        inspect_result = _inspect(
            project,
            depth=getattr(args, "inspect_depth", 2),
            scope=getattr(args, "inspect_scope", None),
            include_related=getattr(args, "inspect_include_related", False),
            include_history=getattr(args, "inspect_include_history", False),
        )
    return render_capabilities_markdown(
        project,
        inspect_result.files,
        inspect_result,
        format=getattr(args, "capabilities_format", "compact"),
        include_tests=False,
        include_detectors=False,
    )


def _build_prime_messages(project: Path) -> list[dict[str, str]]:
    project_name = project.name
    project_path = str(project)
    user_message = (
        f"Before we begin: you are oriented to project '{project_name}' at '{project_path}'. "
        "Use the provided machine-derived repo inspection and project orientation as your grounding. "
        "When asked what project you are oriented to, answer with this project."
    )
    assistant_message = f"Understood. I am oriented to {project_name}."
    return [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_message},
    ]


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
