"""context-kit `start-codex` subcommand.

Prints a ready-to-copy Codex startup prompt grounded in the same runtime
state that `orient` and `doctor` use. Read-only by contract.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from . import state


def run_start_codex(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if getattr(args, "project", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    verify_status = _ensure_verify_config(project)

    prompt = render_codex_prompt(
        project,
        user=getattr(args, "user", None),
        mode=getattr(args, "mode", "design"),
        model=getattr(args, "model", None),
        short=getattr(args, "short", False),
    )
    if verify_status == "created":
        print("Verification config: created `.context-kit/verify.yaml`.")
    else:
        print("Verification config: `.context-kit/verify.yaml` already exists.")
    print(prompt.rstrip() + "\n")
    return 0


def run_codex(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if getattr(args, "project", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    verify_status = _ensure_verify_config(project)
    prompt = render_codex_prompt(
        project,
        user=getattr(args, "user", None),
        mode=getattr(args, "mode", "design"),
        model=getattr(args, "model", None),
        short=getattr(args, "short", False),
    )
    exec_mode = bool(getattr(args, "exec", False))
    interactive_mode = bool(getattr(args, "interactive", False)) or not exec_mode
    launch_mode = "exec" if exec_mode else "interactive"
    print_prompt = bool(getattr(args, "print_prompt", False))

    codex_bin = shutil.which("codex")
    if codex_bin is None:
        print("Codex CLI: not found on PATH.")
        _print_verify_status(verify_status)
        if print_prompt:
            print("=== Codex startup prompt ===")
            print(prompt.rstrip())
            print("=== End Codex startup prompt ===")
        if interactive_mode:
            _print_interactive_handoff_notice(prompt_copied=False)
        else:
            print("Codex is running one-shot with `codex exec`.")
        _emit_prompt_fallback(prompt, copied=_copy_to_clipboard(prompt), interactive=interactive_mode)
        return 0

    _print_verify_status(verify_status)
    if print_prompt:
        print("=== Codex startup prompt ===")
        print(prompt.rstrip())
        print("=== End Codex startup prompt ===")
    if interactive_mode:
        copied = _copy_to_clipboard(prompt)
        print("Prompt copied to clipboard." if copied else "Clipboard unavailable.")
    launch_result = _launch_codex(codex_bin, project, prompt, launch_mode=launch_mode)
    if launch_result == "exec":
        print("Codex CLI: launched with `codex exec`.")
        return 0
    if launch_result == "interactive":
        print("Codex CLI: launched interactively.")
        _print_interactive_handoff_notice(prompt_copied=True)
        print("If Codex opened without the context-kit prompt, rerun and paste the clipboard contents as the first message.")
        return 0

    print("Codex CLI: launch failed; showing the prompt instead.")
    _emit_prompt_fallback(prompt, copied=_copy_to_clipboard(prompt), interactive=interactive_mode)
    return 0


def render_codex_prompt(
    project: Path,
    *,
    user: str | None = None,
    mode: str = "design",
    model: str | None = None,
    short: bool = False,
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

    if short:
        return _render_short_prompt(
            project=project,
            version=version,
            tests=tests,
            latest_token=latest_token,
            next_token=next_token,
            next_task=next_task,
            doctor_counts=doctor_counts,
            mode=mode,
            model=model,
        )

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
    lines.append("- Warnings are advisory; only blocking items stop work.")
    lines.append("")
    lines.append("-----")
    lines.append("")
    lines.append("Key docs:")
    for doc in docs:
        lines.append(f"- {doc}")
    if not docs:
        lines.append("- (none found)")
    lines.append("")
    lines.extend(_trust_verify_ignore())
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
    lines.append("- Treat runtime and config files as truth when docs conflict")
    lines.append("- Treat historical docs as memory, not current truth")
    lines.append("- Use `.context-kit/verify.yaml` as the verification source map")
    lines.append("- Run `context-kit inspect` before trusting the repo shape")
    lines.append("- Run `context-kit verify` before trusting documentation claims")
    lines.append("- Close the loop before you leave: update docs when behavior changes")
    lines.append("- Close the loop before you leave: refresh or verify the inventory when commands, routes, or features change")
    lines.append("- Close the loop before you leave: remove, ignore, or intentionally track generated artifacts")
    lines.append("- Close the loop before you leave: run `context-kit verify` and `context-kit doctor` where applicable before handoff")
    lines.append("- Close the loop before you leave: write or update a handoff note after major work")
    lines.append("- Correct stale docs before closing the task")
    lines.append("- Do not modify protected systems")
    lines.append("- LLM = language layer only")
    lines.append("- Drift checks are warnings; do not treat warnings as blockers unless the user says so")
    lines.append("")
    lines.append("Steps:")
    lines.append("1. Run `context-kit inspect`")
    lines.append("2. Run `context-kit verify`")
    lines.append("3. Run `context-kit orient`")
    lines.append("4. Run `context-kit doctor`")
    lines.append("5. Build understanding")
    lines.append("6. Confirm before coding")
    return "\n".join(lines)


def _render_short_prompt(
    *,
    project: Path,
    version: str,
    tests: str,
    latest_token: str,
    next_token: str,
    next_task: str,
    doctor_counts: dict[str, int],
    mode: str,
    model: str | None,
) -> str:
    lines: list[str] = []
    lines.append("## CONTEXT-KIT SESSION START — CODEX")
    lines.append("")
    lines.append(f"Project: {project.name}")
    lines.append(f"Version: {version}")
    lines.append(f"Tests: {tests}")
    lines.append(f"Latest handoff: {latest_token}")
    lines.append(f"Next session: {next_token}")
    lines.append(f"Doctor: {doctor_counts['blocking']} blocking, {doctor_counts['warnings']} warnings")
    lines.append("")
    if model:
        lines.extend(_model_hint(model))
        lines.append("")
    if mode == "execute":
        lines.extend(_execution_mode())
        lines.append("")
    lines.append("Next task:")
    lines.append(_compact_task(next_task))
    lines.append("")
    lines.append("Essential rules:")
    lines.append("- Docs override assumptions")
    lines.append("- Treat runtime and config files as truth when docs conflict")
    lines.append("- Treat historical docs as memory, not current truth")
    lines.append("- Use `.context-kit/verify.yaml` as the verification source map")
    lines.append("- Run `context-kit inspect` before trusting the repo shape")
    lines.append("- Run `context-kit verify` before trusting documentation claims")
    lines.append("- Close the loop before you leave: update docs when behavior changes")
    lines.append("- Close the loop before you leave: refresh or verify the inventory when commands, routes, or features change")
    lines.append("- Close the loop before you leave: remove, ignore, or intentionally track generated artifacts")
    lines.append("- Close the loop before you leave: run `context-kit verify` and `context-kit doctor` where applicable before handoff")
    lines.append("- Close the loop before you leave: write or update a handoff note after major work")
    lines.append("- Correct stale docs before closing the task")
    lines.append("- Warnings are advisory; blocking items stop work")
    lines.append("- Do not expand scope without asking")
    lines.append("- If unclear, ask before acting")
    return "\n".join(lines)


def _trust_verify_ignore() -> list[str]:
    return [
        "## TRUST / VERIFY / IGNORE",
        "",
        "Trust:",
        "- pyproject.toml version",
        "- unittest discovery count shown above",
        "- docs/CONTEXT_KIT_INVENTORY.md as the runtime anchor",
        "",
        "Verify:",
        "- run `context-kit inspect` first",
        "- run `context-kit verify` after inspect",
        "- runtime and config files over docs when they disagree",
        "- doctor warnings before treating them as blockers",
        "- latest handoff and 00-START-NEXT-SESSION.md when they differ",
        "- `.context-kit/verify.yaml` as the verification source map",
        "",
        "Ignore:",
        "- historical docs as current truth",
        "- missing optional docs unless the task needs them",
    ]


def _compact_task(next_task: str) -> str:
    for line in next_task.splitlines():
        stripped = line.strip()
        if stripped:
            if not stripped.endswith((".", "!", "?")) and "." in stripped:
                return stripped[: stripped.rfind(".") + 1]
            return stripped
    return "(no next task found in 00-START-NEXT-SESSION.md)"


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


def _print_verify_status(status: str) -> None:
    if status == "created":
        print("Verification config: created `.context-kit/verify.yaml`.")
    else:
        print("Verification config: `.context-kit/verify.yaml` already exists.")


def _emit_prompt_fallback(prompt: str, *, copied: bool, interactive: bool) -> None:
    if copied:
        print("Prompt copied to clipboard.")
    else:
        print("Clipboard unavailable.")
    if interactive:
        _print_interactive_handoff_notice(prompt_copied=copied)
        print("If Codex opened without the context-kit prompt, rerun and paste the clipboard contents as the first message.")
    else:
        print("Codex is running one-shot with `codex exec`.")
        print("Paste the prompt below into Codex.")
    print("")
    print("=== Codex startup prompt ===")
    print(prompt.rstrip())
    print("=== End Codex startup prompt ===")


def _print_interactive_handoff_notice(*, prompt_copied: bool) -> None:
    print("NEXT STEP: paste the copied context-kit startup prompt into Codex.")
    print("Do not type a task first.")
    if prompt_copied:
        print("The prompt is already on your clipboard.")
    else:
        print("The prompt is not on your clipboard yet.")


def _launch_codex(codex_bin: str, project: Path, prompt: str, *, launch_mode: str) -> str:
    try:
        if launch_mode == "exec":
            result = subprocess.run(
                [codex_bin, "exec", "--cd", str(project)],
                input=prompt,
                text=True,
                check=False,
            )
            return "exec" if result.returncode == 0 else "failed"
        subprocess.run([codex_bin, prompt], cwd=project, check=False)
        return "interactive"
    except OSError:
        return "failed"


def _copy_to_clipboard(text: str) -> bool:
    commands: list[list[str]] = []
    if shutil.which("pbcopy"):
        commands.append(["pbcopy"])
    if shutil.which("wl-copy"):
        commands.append(["wl-copy"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-selection", "clipboard"])
    if shutil.which("xsel"):
        commands.append(["xsel", "--clipboard", "--input"])
    if shutil.which("clip"):
        commands.append(["clip"])
    for command in commands:
        try:
            subprocess.run(command, input=text, text=True, check=False)
            return True
        except OSError:
            continue
    return False


def _ensure_verify_config(project: Path) -> str:
    path = project / ".context-kit" / "verify.yaml"
    if path.exists():
        return "exists"

    canonical_docs = [
        "00-START-NEXT-SESSION.md",
        "README.md",
        "CLAUDE.md",
        "docs/CONTEXT_KIT_INVENTORY.md",
        "docs/CONTEXT_KIT_WHAT_IT_IS.md",
        "docs/PLATFORM_INVENTORY.md",
        "docs/PLATFORM_WHAT_IT_IS.md",
    ]
    active_doc_roots = ["docs/", ".claude/"]
    historical_roots = ["archive/", "docs/archive/", "external-project-docs/"]
    generated_artifact_roots = ["frontend/dist/", "dist/", "build/", "venv/", ".venv/", "venv_ml/"]

    existing = [doc for doc in canonical_docs if (project / doc).exists()]

    body = [
        "canonical_docs:",
        *[f"  - {doc}" for doc in existing],
        "active_doc_roots:",
        *[f"  - {root}" for root in active_doc_roots],
        "historical_roots:",
        *[f"  - {root}" for root in historical_roots],
        "generated_artifact_roots:",
        *[f"  - {root}" for root in generated_artifact_roots],
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(body), encoding="utf-8")
    return "created"
