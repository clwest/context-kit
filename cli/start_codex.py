"""context-kit `start-codex` subcommand.

Prints a ready-to-copy Codex startup prompt grounded in the same runtime
state that `orient` and `doctor` use. Read-only by contract.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import state


def run_start_codex(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if getattr(args, "project", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    prompt = render_codex_prompt(
        project,
        user=getattr(args, "user", None),
        mode=getattr(args, "mode", "design"),
        model=getattr(args, "model", None),
    )
    print(prompt.rstrip() + "\n")
    return 0


def render_codex_prompt(
    project: Path,
    *,
    user: str | None = None,
    mode: str = "design",
    model: str | None = None,
) -> str:
    version = state.get_current_version(project) or "(unknown)"
    test_count = state.get_actual_test_count(project)
    tests = "(unknown)" if test_count is None else f"{test_count} discovered"
    latest = state.get_latest_handoff(project)
    latest_token = latest.token if latest else "(none)"
    next_token = latest.next_token if latest else "(unknown)"
    next_task = state.get_next_task(project) or "(no next task found in 00-START-NEXT-SESSION.md)"

    doctor_counts = _doctor_counts(project)
    docs = _key_docs(project)
    persona = _persona_context(project, user)

    lines: list[str] = []
    lines.append("## CONTEXT-KIT SESSION START — CODEX")
    lines.append("")
    lines.append(f"Project: {project.name}")
    lines.append(f"Version: {version}")
    lines.append(f"Tests: {tests}")
    lines.append("")
    lines.append(f"Latest handoff: {latest_token}")
    lines.append(f"Next session: {next_token}")
    lines.append("")
    lines.append("Doctor:")
    lines.append(f"- {doctor_counts['warnings']} warnings")
    lines.append(f"- {doctor_counts['blocking']} blocking")
    lines.append("")
    lines.append("Key docs:")
    for doc in docs:
        lines.append(f"- {doc}")
    if not docs:
        lines.append("- (none found)")
    lines.append("")
    if persona:
        lines.extend(persona)
        lines.append("")
    if model:
        lines.extend(_model_hint(model))
        lines.append("")
    if mode == "execute":
        lines.extend(_execution_mode())
        lines.append("")
    lines.append("Your task:")
    lines.append(next_task)
    lines.append("")
    lines.append("Rules:")
    lines.append("- Docs override assumptions")
    lines.append("- Do not modify protected systems")
    lines.append("- LLM = language layer only")
    lines.append("- Drift checks are warnings; do not treat warnings as blockers unless the user says so")
    lines.append("")
    lines.append("Steps:")
    lines.append("1. Run `context-kit orient`")
    lines.append("2. Run `context-kit doctor`")
    lines.append("3. Build understanding")
    lines.append("4. Confirm before coding")
    return "\n".join(lines)


def _execution_mode() -> list[str]:
    return [
        "## EXECUTION MODE",
        "",
        "You are executing a defined task.",
        "",
        "Rules:",
        "- Do not redesign systems",
        "- Do not expand scope",
        "- Do not introduce new abstractions",
        "- Apply minimal changes only",
        "- Prefer direct edits over exploration",
        "- Keep responses concise",
        "",
        "If unclear:",
        "ask before acting",
    ]


def _model_hint(model: str) -> list[str]:
    if model == "cheap":
        return ["Model hint: use a lower-cost / faster model for this task."]
    if model == "heavy":
        return ["Model hint: use a higher-capability model for this task."]
    return []


def _doctor_counts(project: Path) -> dict[str, int]:
    try:
        from .doctor import run_all_checks  # type: ignore
        results = run_all_checks(project)
    except Exception:
        return {"blocking": 0, "warnings": 0}
    return {
        "blocking": sum(1 for r in results if r.status == "blocking"),
        "warnings": sum(1 for r in results if r.status == "warning"),
    }


def _key_docs(project: Path) -> list[str]:
    try:
        from .orient import (  # type: ignore
            _find_behavior_layer_doc,
            _find_pipeline_doc,
            _find_session_start_doc,
            _find_translation_layer_doc,
        )
    except ImportError:
        return []

    docs: list[str] = []
    for label, path in (
        ("SESSION_START", _find_session_start_doc(project)),
        ("PIPELINE", _find_pipeline_doc(project)),
        ("BEHAVIOR_LAYER", _find_behavior_layer_doc(project)),
        ("TRANSLATION_LAYER", _find_translation_layer_doc(project)),
    ):
        if path is None:
            continue
        try:
            rel = path.relative_to(project)
        except ValueError:
            rel = path
        docs.append(f"{label}: {rel}")
    return docs


def _persona_context(project: Path, user: str | None) -> list[str]:
    if not user:
        return []
    try:
        from .orient import _find_translation_layer_doc  # type: ignore
    except ImportError:
        return [
            "Persona mode:",
            f"- Requested user: {user}",
            "- No TRANSLATION_LAYER discovery available; keep facts unchanged and use neutral framing.",
        ]

    translation = _find_translation_layer_doc(project)
    if translation is None:
        return [
            "Persona mode:",
            f"- Requested user: {user}",
            "- No TRANSLATION_LAYER.md found; keep facts unchanged and use neutral framing.",
        ]

    text = state.read_text(translation)
    match = _find_persona_line(text, user)
    if match is None:
        return [
            "Persona mode:",
            f"- Requested user: {user}",
            f"- No matching persona found in {translation.name}; keep facts unchanged and use neutral framing.",
        ]

    return [
        "Persona mode:",
        f"- Requested user: {user}",
        f"- Matched persona: {match}",
        "- Adjust explanation tone, framing, and priorities for this persona.",
        "- Do not change facts; only change explanation style.",
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
