"""context-kit adopt — minimal v0.

Retrofits context-kit's docs layer onto an existing project. Detects a
basic stack from manifest files, asks the user two questions, and
generates the load-bearing docs (BUILD_PLAN.md, *_WHAT_IT_IS.md,
00-START-NEXT-SESSION.md, plus a CLAUDE.md augmentation).

This is the v0 from the SESSION_009 design proposal — proves the
concept end-to-end without the multi-stack handling, confidence
scoring, or recommend-stack integration described for the full
release. Source code is never modified; only docs are written.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Marker convention mirrors seed.py and inventory.py: anything inside
# the start/end markers is auto-generated and safe to overwrite on
# re-run; anything outside is human content and must be preserved.
START_MARKER = "<!-- context-kit:adopt:start -->"
END_MARKER = "<!-- context-kit:adopt:end -->"


@dataclass
class StackProfile:
    """What we detected about the project's stack.

    ``language`` is the *primary* language (the one the AI should
    treat as default). ``parts`` is non-empty for split monorepos
    where each subdir has its own stack — e.g.
    ``{"backend": "python", "frontend": "javascript"}``. When parts
    is populated the generators render a per-subdir stack table
    instead of a single-line summary.
    """

    language: str  # "javascript" | "python" | "unknown"
    signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # v0.1: per-subdir detection results. Populated only when the
    # repo root has no top-level manifest and one or more recognized
    # subdirectories (backend, frontend, etc.) carry their own.
    parts: dict[str, str] = field(default_factory=dict)
    # v0.1: which manifest file each part was detected from. Parallel
    # keys to ``parts``. Lets the BUILD_PLAN render "(detected from
    # backend/manage.py)" instead of just naming the language.
    part_signals: dict[str, str] = field(default_factory=dict)


@dataclass
class AdoptionInputs:
    """The two answers we collect from the user."""

    project_description: str
    next_step: str


@dataclass
class PlannedFile:
    """One file the adopt run intends to create or augment.

    ``kind`` is "create" when the file doesn't exist yet, "augment"
    when we'll append a managed block to an existing file. We never
    overwrite a file outside its managed block.
    """

    path: Path
    content: str
    kind: str  # "create" | "augment"


# ---------------------------------------------------------------------------
# Layer 1: detection (read-only)
# ---------------------------------------------------------------------------


# v0.1: subdirs we'll look inside when the root has no manifest.
# Order matters — the first hit becomes the primary stack when no
# ``backend`` is detected (backend wins by convention; see _pick_primary).
RECOGNIZED_SUBDIRS = ("backend", "frontend", "web", "mobile", "api", "client", "server")


def _detect_in_dir(d: Path) -> tuple[str, list[str]]:
    """Return ``(language, signals)`` for a single directory.

    ``language`` is "javascript" | "python" | "unknown". ``signals``
    lists the manifest filenames found in ``d`` (for reporting; not
    prefixed with the directory). Mixed JS+Python in the same
    directory still resolves to JavaScript with a multi-stack note
    appended at the call site.
    """
    signals: list[str] = []
    if (d / "package.json").is_file():
        signals.append("package.json")
    if (d / "manage.py").is_file():
        signals.append("manage.py")
    if (d / "requirements.txt").is_file():
        signals.append("requirements.txt")
    if (d / "pyproject.toml").is_file():
        signals.append("pyproject.toml")
    has_js = "package.json" in signals
    has_py = any(s in signals for s in ("manage.py", "requirements.txt", "pyproject.toml"))
    if has_js and has_py:
        return "javascript", signals  # caller decides whether to add a note
    if has_js:
        return "javascript", signals
    if has_py:
        return "python", signals
    return "unknown", signals


def _pick_primary(parts: dict[str, str]) -> str:
    """Backend wins by convention; otherwise first detected in scan order.

    The "backend wins" rule comes from the dogfood split-monorepo
    shape (focus-flow, dealflowtracker, etc.). Backend is where the
    domain logic lives, so the AI session's default frame is best
    anchored there. A user who disagrees can edit BUILD_PLAN.md.
    """
    if "backend" in parts and parts["backend"] != "unknown":
        return parts["backend"]
    for sub in RECOGNIZED_SUBDIRS:
        if parts.get(sub) and parts[sub] != "unknown":
            return parts[sub]
    return "unknown"


def detect_stack(repo: Path) -> StackProfile:
    """Detect the project's stack, root-first then one level deep.

    Order:
      1. Scan ``repo`` root. If any manifest is found there, return
         that profile and ignore subdirs (root wins; preserves v0
         behavior for single-stack repos like ai-content-studio).
      2. Otherwise, scan each recognized subdir
         (backend / frontend / web / mobile / api / client / server)
         for the same set of manifests. Populate ``parts`` per
         subdir. ``language`` becomes the primary (backend if
         present, else first detected, else unknown).

    Depth is capped at 1 by design. Microservice / Turborepo shapes
    (``apps/<name>/...``) are intentionally not handled yet — that's
    v0.2's job.
    """
    # Step 1: root scan. Existing v0 behavior.
    root_lang, root_signals = _detect_in_dir(repo)
    if root_signals:
        notes: list[str] = []
        # Preserve the v0 "mixed JS+Python at root" honest note.
        if (
            "package.json" in root_signals
            and any(s in root_signals for s in ("manage.py", "requirements.txt", "pyproject.toml"))
        ):
            notes.append(
                "Detected both JavaScript and Python manifests at root. "
                "v0 reports JavaScript and notes Python presence; "
                "multi-stack handling is planned for a later release."
            )
        return StackProfile(language=root_lang, signals=root_signals, notes=notes)

    # Step 2: one-level-deep scan into recognized subdirs only.
    parts: dict[str, str] = {}
    part_signals: dict[str, str] = {}
    aggregated_signals: list[str] = []
    for sub in RECOGNIZED_SUBDIRS:
        d = repo / sub
        if not d.is_dir():
            continue
        lang, sigs = _detect_in_dir(d)
        if not sigs:
            continue
        parts[sub] = lang
        # Surface the most informative signal per subdir (the first
        # match in the canonical priority of _detect_in_dir).
        part_signals[sub] = sigs[0]
        for s in sigs:
            aggregated_signals.append(f"{sub}/{s}")

    if parts:
        primary = _pick_primary(parts)
        notes = [
            "Split monorepo detected. Per-subdir stack listed below; "
            "deeper layouts (apps/<name>/...) are not yet handled."
        ]
        return StackProfile(
            language=primary,
            signals=aggregated_signals,
            notes=notes,
            parts=parts,
            part_signals=part_signals,
        )

    # Nothing at root, nothing in recognized subdirs.
    return StackProfile(
        language="unknown",
        signals=[],
        notes=[
            "No package.json, manage.py, requirements.txt, or pyproject.toml "
            "found at repo root or in recognized subdirs "
            f"({', '.join(RECOGNIZED_SUBDIRS)})."
        ],
    )


def derive_project_title(repo: Path) -> str:
    """Use the directory basename as the project title (Title Case)."""
    raw = repo.resolve().name or "Project"
    # Replace common separators with spaces then title-case word-by-word.
    cleaned = raw.replace("-", " ").replace("_", " ").strip()
    return " ".join(w.capitalize() for w in cleaned.split()) or "Project"


# ---------------------------------------------------------------------------
# Layer 2: generators (pure transforms)
# ---------------------------------------------------------------------------


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _lang_label(lang: str) -> str:
    if lang == "javascript":
        return "JavaScript / Node.js"
    if lang == "python":
        return "Python"
    return "Unknown"


def _stack_summary(stack: StackProfile) -> str:
    """Single-line summary used in dry-run output and the CLAUDE.md block.

    For split monorepos this returns a one-line "Split: backend=Python,
    frontend=JavaScript" form so the CLI dry-run report stays compact;
    the Markdown generators use ``_stack_table`` instead for the
    longer rendering inside docs.
    """
    if stack.parts:
        items = ", ".join(
            f"{sub}={_lang_label(lang)}" for sub, lang in stack.parts.items()
        )
        return f"Split monorepo — {items}"
    if stack.language == "javascript":
        return "JavaScript / Node.js (detected from package.json)"
    if stack.language == "python":
        sig = next(
            (s for s in stack.signals if s in ("manage.py", "requirements.txt", "pyproject.toml")),
            "manifest",
        )
        return f"Python (detected from {sig})"
    return "Unknown stack — no manifest detected"


def _stack_table(stack: StackProfile) -> list[str]:
    """Multi-line markdown rendering of the stack for BUILD_PLAN / CLAUDE.

    Returns a list of lines (no trailing newline). For split monorepos
    this is a bullet list per subdir; for single-stack repos this is
    the same one-line string ``_stack_summary`` returns.
    """
    if not stack.parts:
        return [_stack_summary(stack)]
    lines: list[str] = []
    for sub, lang in stack.parts.items():
        sig = stack.part_signals.get(sub)
        from_clause = f" (detected from `{sub}/{sig}`)" if sig else ""
        lines.append(f"- **{sub.capitalize()}:** {_lang_label(lang)}{from_clause}")
    return lines


def generate_build_plan(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    """The minimum BUILD_PLAN.md a freshly-adopted project needs.

    The strengthened first prompt (Step 8 of the wizard) tells agents
    to read this file before writing code, so it has to carry real
    signal even in v0.
    """
    body = [
        f"# {title} — Build Plan",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "> Review the [adopt: please describe] sections before relying on this.",
        "",
        "## What this project is",
        "",
        inputs.project_description.strip() or "[adopt: please describe]",
        "",
        "## Tech stack",
        "",
    ]
    body += _stack_table(stack)
    if stack.signals:
        body.append("")
        body.append("Manifest files seen: " + ", ".join(f"`{s}`" for s in stack.signals))
    if stack.notes:
        body.append("")
        for note in stack.notes:
            body.append(f"> Note: {note}")
    body += [
        "",
        "## Next milestone",
        "",
        inputs.next_step.strip() or "[adopt: please describe]",
        "",
        "## What NOT to change without asking",
        "",
        "- The detected stack above. If the AI proposes switching frameworks,",
        "  ask first.",
        "- Any code outside this `docs/` tree. `adopt` is read-only against",
        "  source.",
        "",
    ]
    return "\n".join(body)


def generate_what_it_is(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    body = [
        f"# {title} — What It Is",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "> The narrative anchor for this project. Refine the description below",
        "> as the project's mental model sharpens.",
        "",
        "## In one paragraph",
        "",
        inputs.project_description.strip() or "[adopt: please describe]",
        "",
        "## Stack",
        "",
    ]
    body += _stack_table(stack)
    body += [
        "",
        "## Why it exists",
        "",
        "[adopt: please describe — adopt cannot infer the original motivation.]",
        "",
        "## Who it's for",
        "",
        "[adopt: please describe — adopt cannot infer the audience.]",
        "",
    ]
    return "\n".join(body)


def generate_start_here(inputs: AdoptionInputs, title: str) -> str:
    body = [
        "---",
        "state: scaffold",
        f"date: {_today()}",
        "---",
        "",
        f"# Next session — {title}",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "",
        "## What's next",
        "",
        inputs.next_step.strip() or "[adopt: please describe]",
        "",
        "## How to start the session",
        "",
        "1. Read `docs/BUILD_PLAN.md` — confirm the stack matches reality.",
        "2. Read `docs/PROJECT_WHAT_IT_IS.md` (or your project's *_WHAT_IT_IS.md).",
        "3. If you see `[adopt: please describe]` markers, fill them in or ask the user.",
        "4. Then begin the work above.",
        "",
    ]
    return "\n".join(body)


def generate_claude_block(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    """The managed block we append (or insert) into CLAUDE.md.

    Wrapped in markers so re-running ``adopt`` updates these facts in
    place without disturbing surrounding human-written content.
    """
    lines = [
        START_MARKER,
        "",
        "## Project facts (auto-detected)",
        "",
        f"_Generated by `context-kit adopt` on {_today()}. Re-runs update this block in place._",
        "",
        f"- **Project:** {title}",
    ]
    if stack.parts:
        # Split monorepo: render the per-subdir table inline so the
        # AI session sees each component's stack as a discrete fact.
        lines.append("- **Stack:**")
        for line in _stack_table(stack):
            lines.append(f"  {line}")
    else:
        lines.append(f"- **Stack:** {_stack_summary(stack)}")
    if stack.signals:
        lines.append(f"- **Manifests seen:** {', '.join(f'`{s}`' for s in stack.signals)}")
    lines += [
        "",
        "### What the user told adopt",
        "",
        f"- **What this project is:** {inputs.project_description.strip() or '[adopt: please describe]'}",
        f"- **What's next:** {inputs.next_step.strip() or '[adopt: please describe]'}",
        "",
        "### Rule for this session",
        "",
        "- Always read `docs/BUILD_PLAN.md` before choosing a stack or writing",
        "  code. The detected stack above is the source of truth — do not",
        "  switch frameworks without asking.",
        "",
        END_MARKER,
    ]
    return "\n".join(lines)


def generate_claude_md_fresh(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    """Full CLAUDE.md when none exists yet.

    Mirrors the shape of cli/_starter/root/CLAUDE.md but tighter — we
    don't ship the full template at adopt time because the user hasn't
    seen the docs-pattern yet. They'll get the full thing if they
    later run ``context-kit init . --force``.
    """
    block = generate_claude_block(stack, inputs, title)
    return "\n".join([
        f"# CLAUDE / AGENTS — {title}",
        "",
        f"> Generated by `context-kit adopt` on {_today()}. AI session entry point.",
        "",
        "## Read this first",
        "",
        "1. `docs/BUILD_PLAN.md` — the stack and what NOT to change.",
        "2. `docs/PROJECT_WHAT_IT_IS.md` (or `docs/<slug>_WHAT_IT_IS.md`) — what this is and why.",
        "3. `00-START-NEXT-SESSION.md` — the current session priority.",
        "",
        "If you see `[adopt: please describe]` anywhere, ask the user to fill",
        "it in before writing code that depends on the missing context.",
        "",
        block,
        "",
    ])


# ---------------------------------------------------------------------------
# Layer 3: materializer (the only thing that touches disk)
# ---------------------------------------------------------------------------


def plan_files(
    repo: Path,
    stack: StackProfile,
    inputs: AdoptionInputs,
) -> list[PlannedFile]:
    """Build the list of files we'd create or augment, without writing."""
    title = derive_project_title(repo)
    plan: list[PlannedFile] = []

    plan.append(PlannedFile(
        path=repo / "docs" / "BUILD_PLAN.md",
        content=generate_build_plan(stack, inputs, title),
        kind="create",
    ))
    # v0 uses a fixed filename (``PROJECT_WHAT_IT_IS.md``) rather than
    # the slug-based ``<APP>_WHAT_IT_IS.md`` the rest of context-kit
    # uses. Keeps the v0 output predictable and sidesteps the "temp
    # dir name leaks into a docs filename" footgun. The full release
    # can switch to slug-based naming once we add the project-name
    # prompt promised in the design.
    plan.append(PlannedFile(
        path=repo / "docs" / "PROJECT_WHAT_IT_IS.md",
        content=generate_what_it_is(stack, inputs, title),
        kind="create",
    ))
    plan.append(PlannedFile(
        path=repo / "00-START-NEXT-SESSION.md",
        content=generate_start_here(inputs, title),
        kind="create",
    ))

    claude_path = repo / "CLAUDE.md"
    if claude_path.is_file():
        plan.append(PlannedFile(
            path=claude_path,
            content=generate_claude_block(stack, inputs, title),
            kind="augment",
        ))
    else:
        plan.append(PlannedFile(
            path=claude_path,
            content=generate_claude_md_fresh(stack, inputs, title),
            kind="create",
        ))
    return plan


def _augment_claude_md(existing: str, block: str) -> str:
    """Append (or replace) the managed block in CLAUDE.md.

    Preserves all human content outside markers. If the markers
    already exist, we replace what's between them; otherwise we
    append the block to the end of the file.
    """
    if START_MARKER in existing and END_MARKER in existing:
        head, _, rest = existing.partition(START_MARKER)
        _, _, tail = rest.partition(END_MARKER)
        return head.rstrip() + "\n\n" + block + "\n" + tail.lstrip("\n")
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + "\n" + block + "\n"


def apply_plan(plan: list[PlannedFile], dry_run: bool) -> list[str]:
    """Execute the plan; return per-file action verbs ("create"/"augment"/"would create"/"would augment").

    Source code is never touched. Only docs/* and root-level CLAUDE.md /
    00-START-NEXT-SESSION.md are written.
    """
    actions: list[str] = []
    for item in plan:
        verb_prefix = "would " if dry_run else ""
        if item.kind == "augment" and item.path.is_file():
            verb = f"{verb_prefix}augment"
            if not dry_run:
                existing = item.path.read_text(encoding="utf-8")
                merged = _augment_claude_md(existing, item.content)
                item.path.write_text(merged, encoding="utf-8")
        else:
            # "create" path — also fires for "augment" when the file
            # is missing, which can happen if CLAUDE.md vanishes
            # between plan() and apply().
            verb = f"{verb_prefix}create"
            if not dry_run:
                item.path.parent.mkdir(parents=True, exist_ok=True)
                item.path.write_text(item.content, encoding="utf-8")
        actions.append(f"  {verb:<14} {item.path}")
    return actions


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def collect_inputs(
    prompt_fn: Callable[[str], str] = input,
    description: Optional[str] = None,
    next_step: Optional[str] = None,
) -> AdoptionInputs:
    """Ask the two questions. Tests inject ``prompt_fn`` and overrides."""
    if description is None:
        description = prompt_fn("What is this project? ").strip()
    if next_step is None:
        next_step = prompt_fn("What are you trying to do next? ").strip()
    return AdoptionInputs(
        project_description=description,
        next_step=next_step,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_adopt(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "path", ".") or ".").resolve()
    if not repo.is_dir():
        sys.stderr.write(f"context-kit: not a directory: {repo}\n")
        return 1

    stack = detect_stack(repo)
    inputs = collect_inputs(
        description=getattr(args, "description", None),
        next_step=getattr(args, "next_step", None),
    )
    plan = plan_files(repo, stack, inputs)

    write = bool(getattr(args, "write", False))
    actions = apply_plan(plan, dry_run=not write)

    print(f"context-kit adopt — {'WRITE' if write else 'DRY RUN'}")
    print(f"target: {repo}")
    print()
    print(f"Detected stack: {_stack_summary(stack)}")
    if stack.notes:
        for note in stack.notes:
            print(f"  note: {note}")
    print()
    print("Plan:")
    for line in actions:
        print(line)
    print()
    if not write:
        print("Re-run with --write to apply this plan.")
    else:
        print("Done. Review the [adopt: please describe] sections before")
        print("running your AI tool against this project.")
    return 0
