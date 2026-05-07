"""context-kit `chat` subcommand.

Assembles the existing orient prompt, sends it to a local Ollama model,
and either prints a one-shot response or keeps an interactive REPL open
for multi-turn testing.
"""

from __future__ import annotations

import argparse
import io
from dataclasses import dataclass
import sys
from pathlib import Path
from contextlib import redirect_stdout

from . import ollama
from .behavior import run_behavior
from .doctor import run_doctor
from .hotpath import run_hotpath
from . import state
from .capabilities import render_capabilities_markdown
from .orient import _find_translation_layer_doc, render_chat_orient, render_orient

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
    "Capability-question hard constraint:\n"
    "If the user asks \"what can this project do\", \"what can context-kit do\", \"what capabilities exist\", or \"what can this do for me\" and DETERMINISTIC CAPABILITY SUMMARY exists, answer ONLY from that section.\n"
    "Do not synthesize from orientation, repo inspection, stack/framework detection, or the mere presence of inspect/capabilities commands.\n"
    "Do not generalize from the existence of commands into repo-analysis features.\n"
    "Do not infer unused code detection, optimization suggestions, maintainability analysis, performance analysis, modularization analysis, or architecture recommendations unless they are explicitly present in DETERMINISTIC CAPABILITY SUMMARY.\n"
    "If the user says \"use only the capability shortlist\", ignore orientation, repo inspection, inferred repo identity, and framework indicators except evidence lines already present in the shortlist.\n"
    "Capability answers must render as: command name, literal detected type, evidence, confidence.\n"
    "No narrative paragraph before or after.\n"
    "For \"what can this app do?\" questions, answer only from DETERMINISTIC CAPABILITY SUMMARY when it is present.\n"
    "Summarize the Recommended capability shortlist first only when the user has not requested shortlist-only mode.\n"
    "Do not omit high-confidence capabilities from the shortlist unless the user asks for a narrower answer.\n"
    "Command names are not product promises.\n"
    "Do not infer business value, automation, collaboration, AI intelligence, optimization, orchestration, or workflow impact unless explicitly evidenced.\n"
    "Do not infer user benefit from command names.\n"
    "Do not infer productivity gains.\n"
    "Do not infer automation level.\n"
    "Do not infer AI capabilities.\n"
    "Do not infer orchestration or intelligence.\n"
    "Do not infer workflow streamlining or collaboration enhancement.\n"
    "Prefer literal implementation-grounded summaries like \"The repo exposes a connections CLI command.\" over marketing-style summaries.\n"
    "Avoid phrases like \"facilitates collaboration\" or \"architecture intelligence\" unless the injected evidence explicitly says that.\n"
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
    "Included command outputs are startup snapshots captured before chat begins; they are not live state after chat starts.\n"
    "If the user asks for current or latest status, tell them to rerun the command manually.\n"
    "Auto-context routing is deterministic and injects only the relevant startup snapshots for the current turn.\n"
    "Skipped snapshot sections are omitted by design; do not treat absence as evidence about the repo.\n"
    "Answer the user's current question directly.\n"
    "Do not repeatedly introduce yourself.\n"
    "Do not repeatedly reintroduce the project unless asked.\n"
    "Do not repeatedly explain context-kit chat mode unless asked.\n"
    "Do not summarize orientation or inspection unless the user asks.\n"
    "Avoid recursive conversational framing.\n"
    "Treat prior assistant onboarding text as low-priority context.\n"
    "Prefer concise answers unless the user asks for depth.\n"
    "If the user sends a multi-part request, treat the entire message as ONE task unless the user explicitly separates future turns.\n"
    "Do not continue unfinished subparts after completing the answer.\n"
    "\"Explain to X audience\" does not mean simulate a live conversation with that audience.\n"
    "Do not continue audience simulations after the requested answer is complete.\n"
    "Do not switch into conversational roleplay unless explicitly requested.\n"
    "After answering a structured request, return to neutral assistant mode.\n"
    "Do not continue generating additional prompts, questions, or hypothetical dialogue after the answer is complete.\n"
    "Never continue the conversation by answering your own previous outputs.\n"
    "Never generate follow-up user prompts.\n"
    "Never simulate multi-party dialogue unless explicitly requested.\n"
    "After a completed response, stop cleanly.\n"
    "Do not append \"What would you like to discuss?\", \"As a CTO...\", or \"Let's continue...\" unless the user explicitly asked for interactive simulation.\n"
    "Audience adaptation changes framing only, not factual certainty.\n"
    "Translation-layer explanations must preserve implementation confidence, speculation labels, and evidence boundaries.\n"
    "Persona changes framing only; it must not override evidence, confidence, or tool boundaries.\n"
    "Translation-layer context must not invent capabilities.\n"
    "Do not ask \"what would you like to discuss?\" unless the user explicitly asks for brainstorming or open-ended exploration.\n"
    "If the user asks what project you are oriented to, answer once with the project name/path and stop.\n"
    'When the user asks "what are we doing/testing/discussing right now", answer from the recent chat messages first.\n'
    'When the user asks "what can this project do", answer in this order: 1. Structured implementation facts / machine-detected implementation evidence 2. Documented orientation claims 3. Inferred capabilities 4. Unknowns / needs verification.\n'
    "Do not replace the live conversation with the repo's documented NEXT TASK unless the user specifically asks for repo priorities.\n"
    "Do not invent repo facts or stats."
)
PLANNER_RESPONSE_CONTRACT = (
    "You are a command planner.\n"
    "You cannot run commands.\n"
    "Recommend exactly one command at a time.\n"
    "Prefer {preferred_family} commands when available.\n"
    "If the user pasted command output, summarize in at most 3 bullets, then give exactly one next command.\n"
    "Never ask open-ended follow-up questions.\n"
    "Never continue the conversation after the command.\n"
    "Never respond to your own prior output.\n"
    "If no command is appropriate, output: COMMAND: none\n"
    "Response format:\n"
    "SUMMARY:\n"
    "- ...\n"
    "COMMAND:\n"
    "<one command>\n"
)
PLANNER_TASK_PREFIX = "PLANNER_TASK:\n"
PLANNER_TASK_SUFFIX = "\nEND_PLANNER_TASK"
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
    planner_mode: bool
    planner_prefer_git: bool
    persona_requested: str | None
    persona_matched: str | None
    include_inspect: bool
    include_capabilities: bool
    include_doctor: bool
    include_hotpath: bool
    include_behavior: bool
    auto_context_enabled: bool
    inspect_generated: bool
    capabilities_generated: bool
    doctor_generated: bool
    hotpath_generated: bool
    behavior_generated: bool
    inventory_low_signal: bool
    prime_enabled: bool
    chat_preamble: str
    project_identity_summary: str
    orientation: str
    inspection: str | None
    capabilities: str | None
    doctor: str | None
    hotpath: str | None
    behavior: str | None
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
        return _run_one_shot(prompt, prompt_bundle, args)

    if not sys.stdin.isatty():
        sys.stderr.write(
            "error: chat needs a prompt.\n"
            "Pass words after `chat`, pipe input on stdin, or run it in a terminal for interactive mode.\n"
        )
        return 2

    return _run_interactive_session(prompt_bundle, args)


def _run_one_shot(prompt: str, bundle: SystemPromptBundle, args: argparse.Namespace) -> int:
    request_messages, routing = _build_request_messages([{"role": "system", "content": bundle.system_message}], prompt, bundle, args)
    if getattr(args, "debug_prompt", False) and not bundle.planner_mode:
        _print_turn_routing_debug(routing)
    try:
        response = ollama.chat_messages(
            request_messages,
            model=getattr(args, "model", None),
        )
    except ollama.OllamaError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    print(response.rstrip())
    return 0


def _run_interactive_session(bundle: SystemPromptBundle, args: argparse.Namespace) -> int:
    messages: list[dict[str, str]] = [{"role": "system", "content": bundle.system_message}]
    if bundle.prime_enabled:
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
            messages = [messages[0]]
            if bundle.prime_enabled:
                messages.extend(bundle.prime_messages)
            print("Conversation reset.")
            continue
        if line == "/orient":
            print(render_orient(bundle.project, short=True).rstrip())
            continue
        request_messages, routing = _build_request_messages(messages, line, bundle, args)
        if getattr(args, "debug_prompt", False) and not bundle.planner_mode:
            _print_turn_routing_debug(routing)
        try:
            response = ollama.chat_messages(
                request_messages,
                model=getattr(args, "model", None),
            )
        except ollama.OllamaError as exc:
            sys.stderr.write(f"error: {exc}\n")
            return 2
        if bundle.planner_mode:
            messages.append({"role": "user", "content": _wrap_planner_task(line)})
        else:
            messages.append({"role": "user", "content": _wrap_user_task(line, getattr(args, "no_task_wrapper", False))})
            messages.append({"role": "assistant", "content": response})
        print(response.rstrip())


def _build_system_message(
    identity_summary: str,
    inspect_report: str | None,
    orientation: str,
    persona_context: list[str],
) -> str:
    parts = [CHAT_BEHAVIOR_PREAMBLE, "", identity_summary]
    if inspect_report:
        parts.extend(["", "## MACHINE-DERIVED REPO INSPECTION", inspect_report])
    parts.extend(["", orientation])
    if persona_context:
        parts.extend(["", "\n".join(persona_context)])
    return "\n".join(parts)


def _build_planner_system_message(project: Path, args: argparse.Namespace) -> str:
    preferred_family = "git" if getattr(args, "planner_prefer_git", False) else "context-kit"
    return "\n".join(
        [
            PLANNER_RESPONSE_CONTRACT.format(preferred_family=preferred_family).rstrip(),
            f"Project path: `{project}`",
            "When no pasted command output is present, start with:",
            "SUMMARY:",
            "- Starting repo inspection.",
            "COMMAND:",
            f"context-kit doctor --project {project}",
        ]
    )


def _build_system_prompt_bundle(project: Path, args: argparse.Namespace) -> SystemPromptBundle:
    planner_mode = getattr(args, "planner_mode", False)
    if planner_mode:
        system_message = _build_planner_system_message(project, args)
        return SystemPromptBundle(
            project=project,
            planner_mode=True,
            planner_prefer_git=getattr(args, "planner_prefer_git", False),
            persona_requested=None,
            persona_matched=None,
            include_inspect=False,
            include_capabilities=False,
            include_doctor=False,
            include_hotpath=False,
            include_behavior=False,
            auto_context_enabled=False,
            inspect_generated=False,
            capabilities_generated=False,
            doctor_generated=False,
            hotpath_generated=False,
            behavior_generated=False,
            inventory_low_signal=False,
            prime_enabled=False,
            chat_preamble=PLANNER_RESPONSE_CONTRACT,
            project_identity_summary="",
            orientation="",
            inspection=None,
            capabilities=None,
            doctor=None,
            hotpath=None,
            behavior=None,
            system_message=system_message,
            prime_messages=[],
        )
    orientation = render_chat_orient(project)
    persona_requested = getattr(args, "user", None)
    persona_context, _persona_translation, persona_matched = _build_persona_context(project, persona_requested)
    inspect_report = None
    inspect_result = None
    capabilities_report = None
    doctor_report = None
    hotpath_report = None
    behavior_report = None
    if getattr(args, "include_inspect", False):
        from .inspect import render_inspect_markdown

        inspect_result = _inspect_for_chat(project, args)
        inspect_report = render_inspect_markdown(inspect_result)
    if getattr(args, "include_capabilities", False):
        capabilities_report = _build_capabilities_report(project, args, inspect_result)
    if getattr(args, "include_doctor", False):
        doctor_report = _build_doctor_report(project)
    if getattr(args, "include_hotpath", False):
        hotpath_report = _build_hotpath_report(project)
    if getattr(args, "include_behavior", False):
        behavior_report = _build_behavior_report(project)
    identity_summary = _build_project_identity_summary(project, inspect_result)
    inventory_low_signal = _chat_inventory_low_signal(project)
    prime_enabled = not getattr(args, "no_prime", False)
    prime_messages = _build_prime_messages(project) if prime_enabled else []
    system_message = _build_system_message(
        identity_summary,
        inspect_report,
        orientation,
        persona_context,
    )
    return SystemPromptBundle(
        project=project,
        planner_mode=False,
        planner_prefer_git=getattr(args, "planner_prefer_git", False),
        persona_requested=persona_requested,
        persona_matched=persona_matched,
        include_inspect=getattr(args, "include_inspect", False),
        include_capabilities=getattr(args, "include_capabilities", False),
        include_doctor=getattr(args, "include_doctor", False),
        include_hotpath=getattr(args, "include_hotpath", False),
        include_behavior=getattr(args, "include_behavior", False),
        auto_context_enabled=not getattr(args, "no_auto_context", False),
        inspect_generated=inspect_report is not None,
        capabilities_generated=capabilities_report is not None,
        doctor_generated=doctor_report is not None,
        hotpath_generated=hotpath_report is not None,
        behavior_generated=behavior_report is not None,
        inventory_low_signal=inventory_low_signal,
        prime_enabled=prime_enabled,
        chat_preamble=CHAT_BEHAVIOR_PREAMBLE,
        project_identity_summary=identity_summary,
        orientation=orientation,
        inspection=inspect_report,
        capabilities=capabilities_report,
        doctor=doctor_report,
        hotpath=hotpath_report,
        behavior=behavior_report,
        system_message=system_message,
        prime_messages=prime_messages,
    )


def _print_debug_prompt(bundle: SystemPromptBundle) -> None:
    if bundle.planner_mode:
        total_count = len(bundle.system_message)
        print(f"Resolved project path: {bundle.project}")
        print("Planner mode: yes")
        print(f"Planner prefers git: {'yes' if bundle.planner_prefer_git else 'no'}")
        print("Character counts:")
        print(f"  planner prompt: {len(bundle.chat_preamble)}")
        print(f"  total system prompt: {total_count}")
        print("")
        print("=== PLANNER PROMPT ===")
        print(bundle.system_message.rstrip())
        print("")
        return
    inspect_generated = "yes" if bundle.inspect_generated else "no"
    inspection_count = len(bundle.inspection or "")
    total_count = len(bundle.system_message)
    print(f"Resolved project path: {bundle.project}")
    print(f"--user enabled: {'yes' if bundle.persona_requested else 'no'}")
    if bundle.persona_requested:
        print(f"Persona requested: {bundle.persona_requested}")
        if bundle.persona_matched:
            print("Persona match status: matched")
            print(f"Matched persona: {bundle.persona_matched}")
        else:
            print("Persona match status: not matched")
    else:
        print("Persona requested: (none)")
    print(f"--include-inspect enabled: {'yes' if bundle.include_inspect else 'no'}")
    print(f"--include-capabilities enabled: {'yes' if bundle.include_capabilities else 'no'}")
    print(f"--include-doctor enabled: {'yes' if bundle.include_doctor else 'no'}")
    print(f"--include-hotpath enabled: {'yes' if bundle.include_hotpath else 'no'}")
    print(f"--include-behavior enabled: {'yes' if bundle.include_behavior else 'no'}")
    print(f"Auto-context routing enabled: {'yes' if bundle.auto_context_enabled else 'no'}")
    print(f"Priming exchange enabled: {'yes' if bundle.prime_enabled else 'no'}")
    print(f"Inspection text generated: {inspect_generated}")
    print(f"Capability summary generated: {'yes' if bundle.capabilities_generated else 'no'}")
    print(f"Doctor diagnostics generated: {'yes' if bundle.doctor_generated else 'no'}")
    print(f"Hotpath summary generated: {'yes' if bundle.hotpath_generated else 'no'}")
    print(f"Behavior layer summary generated: {'yes' if bundle.behavior_generated else 'no'}")
    print(f"Inventory preview skipped: {'yes' if bundle.inventory_low_signal else 'no'}")
    print(f"Character counts:")
    print(f"  chat preamble: {len(bundle.chat_preamble)}")
    print(f"  project identity summary: {len(bundle.project_identity_summary)}")
    print(f"  orientation: {len(bundle.orientation)}")
    print(f"  inspection: {inspection_count}")
    print(f"  capabilities: {len(bundle.capabilities or '')}")
    print(f"  doctor diagnostics: {len(bundle.doctor or '')}")
    print(f"  hotpath summary: {len(bundle.hotpath or '')}")
    print(f"  behavior layer summary: {len(bundle.behavior or '')}")
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
    print("=== DOCTOR DIAGNOSTICS ===")
    if bundle.doctor:
        print(bundle.doctor.rstrip())
    else:
        print("doctor diagnostics not included")
    print("")
    print("=== HOTPATH SUMMARY ===")
    if bundle.hotpath:
        print(bundle.hotpath.rstrip())
    else:
        print("hotpath summary not included")
    print("")
    print("=== BEHAVIOR LAYER SUMMARY ===")
    if bundle.behavior:
        print(bundle.behavior.rstrip())
    else:
        print("behavior layer summary not included")
    print("")
    print("=== PERSONA MODE ===")
    if bundle.persona_requested and bundle.persona_matched:
        print("\n".join(_persona_context_lines(bundle.persona_requested, bundle.persona_matched)).rstrip())
    elif bundle.persona_requested:
        print("persona not matched")
    else:
        print("persona not requested")
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


def _build_doctor_report(project: Path) -> str | None:
    return _capture_subcommand_output(run_doctor, argparse.Namespace(project=str(project), json=False))


def _build_hotpath_report(project: Path) -> str | None:
    return _capture_subcommand_output(
        run_hotpath,
        argparse.Namespace(
            project=str(project),
            single_threshold_kb=50,
            top_count=10,
            top_threshold_kb=200,
        ),
    )


def _build_behavior_report(project: Path) -> str | None:
    return _capture_subcommand_output(
        run_behavior,
        argparse.Namespace(
            path=str(project),
            scope=None,
            json=False,
        ),
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


def _build_request_messages(
    base_messages: list[dict[str, str]],
    user_text: str,
    bundle: SystemPromptBundle,
    args: argparse.Namespace,
) -> tuple[list[dict[str, str]], dict[str, object]]:
    if bundle.planner_mode:
        request_messages = list(base_messages)
        request_messages.append({"role": "user", "content": _wrap_planner_task(user_text)})
        return request_messages, {
            "query_type": "planner",
            "auto_enabled": False,
            "sections": [],
            "auto_sections": [],
            "explicit_sections": [],
            "skipped_sections": [],
        }
    routing = _route_user_query(user_text, bundle, args)
    request_messages = list(base_messages)
    if routing["sections"]:
        request_messages.append(
            {
                "role": "system",
                "content": _render_auto_context_block(routing["sections"]),
            }
        )
    request_messages.append({"role": "user", "content": _wrap_user_task(user_text, getattr(args, "no_task_wrapper", False))})
    return request_messages, routing


def _render_auto_context_block(sections: list[tuple[str, str]]) -> str:
    lines = ["## AUTO CONTEXT (this turn only)", ""]
    for heading, content in sections:
        lines.append(f"## {heading}")
        lines.append(content.rstrip())
        lines.append("")
    return "\n".join(lines).rstrip()


def _route_user_query(user_text: str, bundle: SystemPromptBundle, args: argparse.Namespace) -> dict[str, object]:
    query_type = _detect_query_type(user_text)
    auto_enabled = getattr(args, "no_auto_context", False) is False
    explicit_sections: list[tuple[str, str]] = []
    auto_sections: list[tuple[str, str]] = []
    skipped: list[str] = []

    explicit_map = [
        ("capabilities", getattr(args, "include_capabilities", False), _ensure_capabilities_report),
        ("inspect", getattr(args, "include_inspect", False), _ensure_inspect_report),
        ("doctor", getattr(args, "include_doctor", False), _ensure_doctor_report),
        ("hotpath", getattr(args, "include_hotpath", False), _ensure_hotpath_report),
        ("behavior", getattr(args, "include_behavior", False), _ensure_behavior_report),
    ]

    for key, enabled, getter in explicit_map:
        if enabled:
            explicit_sections.append((key, getter(bundle, args)))

    routed_key = _query_type_to_section(query_type)
    if auto_enabled and routed_key is not None:
        if not any(key == routed_key for key, _ in explicit_sections):
            getter = {
                "capabilities": _ensure_capabilities_report,
                "inspect": _ensure_inspect_report,
                "doctor": _ensure_doctor_report,
                "hotpath": _ensure_hotpath_report,
                "behavior": _ensure_behavior_report,
            }[routed_key]
            auto_sections.append((routed_key, getter(bundle, args)))

    if query_type == "live-state":
        skipped = ["capabilities", "inspect", "doctor", "hotpath", "behavior"]
    else:
        all_keys = ["capabilities", "inspect", "doctor", "hotpath", "behavior"]
        injected_keys = {key for key, _ in explicit_sections} | {key for key, _ in auto_sections}
        skipped = [key for key in all_keys if key not in injected_keys]

    sections = [( _SECTION_HEADINGS[key], content) for key, content in explicit_sections + auto_sections if content]
    return {
        "query_type": query_type,
        "auto_enabled": auto_enabled,
        "sections": sections,
        "auto_sections": [key for key, _ in auto_sections],
        "explicit_sections": [key for key, _ in explicit_sections],
        "skipped_sections": skipped,
    }


_SECTION_HEADINGS = {
    "capabilities": "DETERMINISTIC CAPABILITY SUMMARY",
    "inspect": "MACHINE-DERIVED REPO INSPECTION",
    "doctor": "DOCTOR DIAGNOSTICS",
    "hotpath": "HOTPATH SUMMARY",
    "behavior": "BEHAVIOR LAYER SUMMARY",
}


def _query_type_to_section(query_type: str) -> str | None:
    return {
        "capability": "capabilities",
        "inspect": "inspect",
        "doctor": "doctor",
        "hotpath": "hotpath",
        "behavior": "behavior",
    }.get(query_type)


def _detect_query_type(user_text: str) -> str:
    text = user_text.lower()
    if _is_live_state_query(text):
        return "live-state"
    if _is_capability_query(text):
        return "capability"
    if _is_behavior_query(text):
        return "behavior"
    if _is_doctor_query(text):
        return "doctor"
    if _is_hotpath_query(text):
        return "hotpath"
    if _is_inspect_query(text):
        return "inspect"
    return "general"


def _is_capability_query(text: str) -> bool:
    phrases = (
        "what can this project do",
        "what can context-kit do",
        "what capabilities exist",
        "what can this do for me",
        "what can this app do",
        "capability shortlist",
        "capabilities",
    )
    return any(phrase in text for phrase in phrases)


def _is_behavior_query(text: str) -> bool:
    phrases = ("persona", "behavior", "tone", "voice", "ux", "audience", "style")
    if any(phrase in text for phrase in phrases):
        return True
    if "explain" in text and ("to a " in text or "to the " in text):
        audience_terms = (
            "cto",
            "developer",
            "engineer",
            "manager",
            "operator",
            "stakeholder",
            "executive",
            "junior",
            "non-technical",
        )
        return any(term in text for term in audience_terms)
    return False


def _is_doctor_query(text: str) -> bool:
    phrases = ("doctor", "diagnostic", "diagnostics", "setup", "environment", "install", "dependency", "health check")
    return any(phrase in text for phrase in phrases)


def _is_hotpath_query(text: str) -> bool:
    phrases = ("hotpath", "hot path", "largest files", "file size", "architecture", "context window", "entrypoints")
    return any(phrase in text for phrase in phrases)


def _is_inspect_query(text: str) -> bool:
    phrases = ("inspect", "repo structure", "project structure", "file tree", "what files", "layout", "source of truth")
    return any(phrase in text for phrase in phrases)


def _is_live_state_query(text: str) -> bool:
    phrases = ("latest", "recent changes", "current status", "right now", "git diff", "git log", "uncommitted", "test status")
    return any(phrase in text for phrase in phrases)


def _print_turn_routing_debug(routing: dict[str, object]) -> None:
    print(f"Auto-context query type: {routing['query_type']}")
    if routing["auto_enabled"]:
        print("Auto-context routing: enabled")
    else:
        print("Auto-context routing: disabled")
    auto_sections = ", ".join(routing["auto_sections"]) if routing["auto_sections"] else "(none)"
    explicit_sections = ", ".join(routing["explicit_sections"]) if routing["explicit_sections"] else "(none)"
    skipped_sections = ", ".join(routing["skipped_sections"]) if routing["skipped_sections"] else "(none)"
    print(f"Auto-injected sections: {auto_sections}")
    print(f"Explicit sections: {explicit_sections}")
    print(f"Skipped sections: {skipped_sections}")


def _ensure_inspect_report(bundle: SystemPromptBundle, args: argparse.Namespace) -> str | None:
    if bundle.inspection is not None:
        return bundle.inspection
    from .inspect import render_inspect_markdown

    result = _inspect_for_chat(bundle.project, args)
    bundle.inspection = render_inspect_markdown(result)
    return bundle.inspection


def _ensure_capabilities_report(bundle: SystemPromptBundle, args: argparse.Namespace) -> str | None:
    if bundle.capabilities is not None:
        return bundle.capabilities
    bundle.capabilities = _build_capabilities_report(bundle.project, args, None)
    return bundle.capabilities


def _ensure_doctor_report(bundle: SystemPromptBundle, args: argparse.Namespace) -> str | None:
    if bundle.doctor is not None:
        return bundle.doctor
    bundle.doctor = _build_doctor_report(bundle.project)
    return bundle.doctor


def _ensure_hotpath_report(bundle: SystemPromptBundle, args: argparse.Namespace) -> str | None:
    if bundle.hotpath is not None:
        return bundle.hotpath
    bundle.hotpath = _build_hotpath_report(bundle.project)
    return bundle.hotpath


def _ensure_behavior_report(bundle: SystemPromptBundle, args: argparse.Namespace) -> str | None:
    if bundle.behavior is not None:
        return bundle.behavior
    bundle.behavior = _build_behavior_report(bundle.project)
    return bundle.behavior


def _capture_subcommand_output(func, args: argparse.Namespace) -> str | None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        func(args)
    text = buf.getvalue().strip()
    if not text:
        return None
    return text + "\n"


def _build_persona_context(
    project: Path,
    user: str | None,
) -> tuple[list[str], Path | None, str | None]:
    if not user:
        return [], None, None
    translation = _find_translation_layer_doc(project)
    if translation is None:
        return [], None, None

    text = state.read_text(translation)
    match = _find_persona_line(text, user)
    if match is None:
        return [], translation, None

    return _persona_context_lines(user, match), translation, match


def _persona_context_lines(user: str, match: str) -> list[str]:
    return [
        "## PERSONA MODE",
        f"- Requested user: {user}",
        f"- Matched persona: {match}",
        "- Adjust explanation tone, framing, and priorities for this persona.",
        "- Do not change facts; only change explanation style.",
        "- If you cannot translate without inventing or implying unsupported facts, fall back to neutral.",
        "- Persona changes framing only; it must not override evidence, confidence, or tool boundaries.",
        "- Translation-layer context must not invent capabilities.",
    ]


def _find_persona_line(text: str, user: str) -> str | None:
    needle = user.strip().lower()
    if not needle:
        return None
    for line in text.splitlines():
        stripped = line.strip().strip("|").strip()
        if needle in stripped.lower():
            return stripped
    return None


def _wrap_user_task(user_text: str, disabled: bool) -> str:
    if disabled:
        return user_text
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


def _wrap_planner_task(user_text: str) -> str:
    return f"{PLANNER_TASK_PREFIX}{user_text}{PLANNER_TASK_SUFFIX}"


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
