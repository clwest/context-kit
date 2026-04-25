"""context-kit `seed` subcommand: turn a raw idea file into project context.

Reads a structured markdown idea file (see ``IDEA_SCHEMA.md`` shipped at
``cli/_pattern/IDEA_SCHEMA.md``) and populates the load-bearing parts of
a freshly-init'd context-kit project: the narrative anchor's TL;DR
section, the start-here doc's first milestone, the bootstrap handoff,
the product framing topic, and a structured BUILD_PLAN.md.

Five files in total. Five managed-block markers. Everything outside the
markers stays human-editable forever. Re-running on the same idea
produces byte-identical output (modulo the ``Last seeded`` timestamp);
re-running with an updated idea regenerates only the seed-owned content.

Deterministic / template-based. No LLM calls.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

START_MARKER = "<!-- context-kit:seed:start -->"
END_MARKER = "<!-- context-kit:seed:end -->"
SCHEMA_VERSION = 1


# Heading text → canonical key. Headings are normalized via
# ``_normalize_heading`` (lowercase, trailing punctuation stripped) so
# users can write ``## What are we building?`` or ``## What it is`` and
# both match the same key.
_HEADING_MAP: dict[str, str] = {
    "what are we building": "what",
    "what we're building": "what",
    "what we are building": "what",
    "what it is": "what",
    "what we're making": "what",
    "what we make": "what",
    "what": "what",

    "who is it for": "who",
    "who it's for": "who",
    "who it is for": "who",
    "audience": "who",
    "who": "who",

    "problem": "problem",
    "the problem": "problem",
    "what problem": "problem",

    "core features": "features",
    "features": "features",
    "what it does": "features",

    "tech stack": "stack",
    "stack": "stack",
    "tech": "stack",

    "first milestone": "milestone",
    "milestone": "milestone",
    "first ship": "milestone",
    "first cut": "milestone",

    "what not to build yet": "non_goals",
    "what not to build": "non_goals",
    "non-goals": "non_goals",
    "non goals": "non_goals",
    "out of scope": "non_goals",
    "not yet": "non_goals",

    "open questions": "questions",
    "questions": "questions",
    "things to figure out": "questions",
}

_OPTIONAL_KEYS = ("who", "problem", "features", "stack", "milestone", "non_goals", "questions")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_seed(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else Path.cwd().resolve()
    idea_path = Path(args.idea).resolve()

    if not idea_path.is_file():
        print(f"context-kit: idea file not found: {idea_path}")
        return 2

    if not _is_context_kit_project(project):
        print(
            f"context-kit: {project} doesn't look like a context-kit project.\n"
            f"  Run `context-kit init` first to scaffold one, then re-run seed."
        )
        return 2

    text = idea_path.read_text(encoding="utf-8")
    sections = parse_idea(text)
    errors, warnings = validate_sections(sections)
    if errors:
        for err in errors:
            print(f"context-kit: error: {err}")
        return 2

    for warning in warnings:
        print(f"context-kit: warning: {warning}")

    actions: list[tuple[Path, str]] = []
    actions += _seed_what_it_is(project, sections, idea_path, force=args.force, dry_run=args.dry_run)
    actions += _seed_start_here(project, sections, idea_path, force=args.force, dry_run=args.dry_run)
    actions += _seed_handoff(project, sections, idea_path, force=args.force, dry_run=args.dry_run)
    actions += _seed_product_topic(project, sections, idea_path, force=args.force, dry_run=args.dry_run)
    actions += _seed_build_plan(project, sections, idea_path, force=args.force, dry_run=args.dry_run)

    print()
    verb = "would " if args.dry_run else ""
    for path, action in actions:
        try:
            rel = path.relative_to(project)
        except ValueError:
            rel = path
        print(f"  {verb}{action:9}  {rel}")

    if args.dry_run:
        print("\n(dry run — no files written)")
        return 0

    print(
        "\nNext:\n"
        "  context-kit inventory --write     # refresh the runtime anchor\n"
        "  context-kit orient                # confirm the agent has what it needs\n"
        "  claude  # or your AI tool of choice — the bundled skill loads automatically"
    )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_idea(text: str) -> dict:
    """Parse a markdown idea file into a dict.

    Returns:
        ``{"_title": str | None, "_unknown": [(label, body), ...], "<canonical>": str, ...}``
    """
    sections: dict = {}
    title: Optional[str] = None
    unknown: list[tuple[str, str]] = []

    current_key: Optional[str] = None
    current_label: Optional[str] = None
    current_lines: list[str] = []

    def _flush() -> None:
        nonlocal current_lines
        if current_key is None:
            return
        body = "\n".join(current_lines).strip()
        if current_key == "_unknown":
            assert current_label is not None
            unknown.append((current_label, body))
        else:
            sections[current_key] = body
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# ") and not line.startswith("## "):
            if title is None:
                title = line[2:].strip()
            continue
        if line.startswith("## "):
            _flush()
            heading_text = line[3:].strip()
            normalized = _normalize_heading(heading_text)
            mapped = _HEADING_MAP.get(normalized)
            if mapped:
                current_key = mapped
                current_label = None
            else:
                current_key = "_unknown"
                current_label = heading_text
            continue
        if current_key is not None:
            current_lines.append(raw_line)

    _flush()
    sections["_title"] = title
    sections["_unknown"] = unknown
    return sections


def _normalize_heading(text: str) -> str:
    return text.lower().rstrip("?.!").strip()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_sections(sections: dict) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)``."""
    errors: list[str] = []
    warnings: list[str] = []

    what = sections.get("what", "").strip() if "what" in sections else None
    if what is None:
        errors.append(
            "required section 'what' is missing — add a `## What are we building?` "
            "section to your idea file"
        )
    elif what == "":
        errors.append(
            "required section 'what' is present but empty — add a sentence describing "
            "what's being built"
        )

    for key in _OPTIONAL_KEYS:
        if key not in sections:
            warnings.append(
                f"optional section '{key}' is missing — corresponding output will use "
                "a placeholder"
            )
        # Present-but-empty optional sections are silent by design.

    unknown = sections.get("_unknown") or []
    if unknown:
        labels = ", ".join(f"'{label}'" for label, _ in unknown)
        warnings.append(
            f"unrecognized headings preserved under 'Other notes' in BUILD_PLAN.md: {labels}"
        )

    return errors, warnings


# ---------------------------------------------------------------------------
# Project detection + state handling
# ---------------------------------------------------------------------------


def _is_context_kit_project(project: Path) -> bool:
    """Sanity check: looks like an init'd context-kit project."""
    has_anchor = bool(list((project / "docs").glob("*_WHAT_IT_IS.md"))) if (project / "docs").is_dir() else False
    has_start = (project / "00-START-NEXT-SESSION.md").is_file()
    return has_anchor and has_start


def _find_anchor_doc(project: Path) -> Optional[Path]:
    docs = project / "docs"
    if not docs.is_dir():
        return None
    for p in sorted(docs.glob("*_WHAT_IT_IS.md")):
        if p.is_file():
            return p
    return None


def _detect_frontmatter_state(text: str) -> Optional[str]:
    """Return the value of ``state:`` in the file's frontmatter, or None."""
    if not text.startswith("---\n"):
        return None
    end_idx = text.find("\n---\n", 4)
    if end_idx < 0:
        return None
    fm = text[4:end_idx]
    for line in fm.splitlines():
        s = line.strip()
        if s.startswith("state:"):
            return s[len("state:"):].strip()
    return None


def _set_frontmatter_state(text: str, new_state: str) -> str:
    """Set ``state:`` in the file's frontmatter; add it if missing."""
    if not text.startswith("---\n"):
        return f"---\nstate: {new_state}\n---\n\n{text}"
    end_idx = text.find("\n---\n", 4)
    if end_idx < 0:
        return text
    fm = text[4:end_idx]
    if re.search(r"^state:", fm, re.MULTILINE):
        new_fm = re.sub(
            r"^state:\s*\S*",
            f"state: {new_state}",
            fm,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        new_fm = fm.rstrip() + f"\nstate: {new_state}"
    return f"---\n{new_fm}\n---\n" + text[end_idx + len("\n---\n"):]


# ---------------------------------------------------------------------------
# Renderers — each returns a string of seed-owned content (no markers)
# ---------------------------------------------------------------------------


def _wrap_block(body: str, idea_path: Path) -> str:
    return (
        f"{START_MARKER}\n"
        f"<!-- Generated by `context-kit seed`. Edit outside the markers. -->\n"
        f"<!-- Schema version: {SCHEMA_VERSION} · Source: {idea_path.name} · "
        f"Last seeded: {_now_iso()} -->\n"
        f"\n"
        f"{body}\n"
        f"{END_MARKER}"
    )


def _now_iso() -> str:
    override = os.environ.get("CONTEXT_KIT_SEED_TIMESTAMP")
    if override:
        return override
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _section_or_placeholder(sections: dict, key: str, placeholder: str) -> str:
    val = sections.get(key, "").strip() if key in sections else ""
    return val if val else placeholder


def _render_what_it_is_body(sections: dict) -> str:
    what = sections["what"].strip()
    non_goals = _section_or_placeholder(
        sections, "non_goals", "*(none specified yet)*"
    )
    return (
        "## TL;DR\n\n"
        f"{what}\n\n"
        "## What we're deliberately not building yet\n\n"
        f"{non_goals}"
    )


def _render_start_here_body(sections: dict) -> str:
    milestone = _section_or_placeholder(
        sections, "milestone", "*(define your first milestone in idea.md)*"
    )
    questions = _section_or_placeholder(
        sections, "questions", "*(no open questions yet)*"
    )
    return (
        "## SESSION 1 — START HERE\n\n"
        "### FIRST THING — first milestone\n\n"
        f"{milestone}\n\n"
        "## Queued Investigations\n\n"
        f"{questions}"
    )


def _render_product_topic_body(sections: dict) -> str:
    what = sections["what"].strip()
    who = _section_or_placeholder(sections, "who", "*(audience not yet specified)*")
    problem = _section_or_placeholder(sections, "problem", "*(problem not yet specified)*")
    return (
        "## What we're building\n\n"
        f"{what}\n\n"
        "## Who it's for\n\n"
        f"{who}\n\n"
        "## The problem\n\n"
        f"{problem}"
    )


def _render_build_plan_body(sections: dict, idea_text: str = "") -> str:
    # Tech stack: use the user's content if present; otherwise call into
    # `recommend-stack` and bake the recommendation in. Same engine the
    # standalone command uses, so the two paths can never disagree.
    user_stack = sections.get("stack", "").strip() if "stack" in sections else ""
    if user_stack:
        stack_body = user_stack
    elif idea_text:
        try:
            from .recommend_stack import recommend, format_for_build_plan  # type: ignore
            result = recommend(idea_text)
            stack_body = format_for_build_plan(result)
        except ImportError:
            stack_body = "*(stack TBD — recommend_stack module unavailable)*"
    else:
        stack_body = "*(stack TBD)*"

    parts = [
        "## First milestone",
        "",
        _section_or_placeholder(sections, "milestone", "*(no milestone in idea.md yet)*"),
        "",
        "## Core features",
        "",
        _section_or_placeholder(sections, "features", "*(no features in idea.md yet)*"),
        "",
        "## Tech stack",
        "",
        stack_body,
        "",
        "## Non-goals",
        "",
        _section_or_placeholder(sections, "non_goals", "*(nothing explicitly out of scope yet)*"),
        "",
        "## Open questions",
        "",
        _section_or_placeholder(sections, "questions", "*(none yet)*"),
    ]
    unknown = sections.get("_unknown") or []
    if unknown:
        parts += ["", "## Other notes (unrecognized headings, preserved verbatim)"]
        for label, body in unknown:
            parts += ["", f"### {label}", "", body or "*(empty)*"]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# File writers — each returns ``[(path, action), ...]``
# ---------------------------------------------------------------------------


def _replace_or_insert_block(existing: str, new_block: str) -> str:
    """Replace a ``seed:start`` … ``seed:end`` block, or insert it.

    If markers are present, replace between them. Otherwise, insert
    after the file's frontmatter (if any), else at the top.
    """
    if START_MARKER in existing and END_MARKER in existing:
        pre, _, after_start = existing.partition(START_MARKER)
        _, _, post = after_start.partition(END_MARKER)
        return pre + new_block + post

    # No markers — insert after frontmatter (if present), else at top.
    insert_at = 0
    if existing.startswith("---\n"):
        end_fm = existing.find("\n---\n", 4)
        if end_fm >= 0:
            insert_at = end_fm + len("\n---\n")
            # Skip over a single blank line if present
            if existing[insert_at:insert_at + 1] == "\n":
                insert_at += 1

    head = existing[:insert_at]
    tail = existing[insert_at:]
    sep = "\n" if head and not head.endswith("\n\n") else ""
    return head + sep + new_block + "\n\n" + tail


def _seed_what_it_is(
    project: Path,
    sections: dict,
    idea_path: Path,
    *,
    force: bool,
    dry_run: bool,
) -> list[tuple[Path, str]]:
    anchor = _find_anchor_doc(project)
    if anchor is None:
        return []
    body = _wrap_block(_render_what_it_is_body(sections), idea_path)
    existing = anchor.read_text(encoding="utf-8")
    new_text = _replace_or_insert_block(existing, body)
    action = "updated" if (START_MARKER in existing) else "seeded"
    if not dry_run:
        anchor.write_text(new_text, encoding="utf-8")
    return [(anchor, action)]


def _seed_start_here(
    project: Path,
    sections: dict,
    idea_path: Path,
    *,
    force: bool,
    dry_run: bool,
) -> list[tuple[Path, str]]:
    path = project / "00-START-NEXT-SESSION.md"
    if not path.is_file():
        return []
    existing = path.read_text(encoding="utf-8")
    state = _detect_frontmatter_state(existing)
    is_safe = (state == "scaffold") or (state == "seeded")
    if not is_safe and not force:
        return [(path, "skipped (state != scaffold; use --force)")]

    body = _wrap_block(_render_start_here_body(sections), idea_path)
    new_text = _replace_or_insert_block(existing, body)
    new_text = _set_frontmatter_state(new_text, "seeded")
    action = "updated" if (START_MARKER in existing) else "seeded"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return [(path, action)]


def _seed_handoff(
    project: Path,
    sections: dict,
    idea_path: Path,
    *,
    force: bool,
    dry_run: bool,
) -> list[tuple[Path, str]]:
    path = project / "docs" / "handoffs" / "SESSION_001_IDEA_BOOTSTRAP.md"
    if path.is_file() and not force:
        return [(path, "skipped (exists; use --force)")]

    existed_before = path.is_file()
    title = sections.get("_title") or "Idea Bootstrap"
    handoff = _build_handoff_body(sections, idea_path, title)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(handoff, encoding="utf-8")
    return [(path, "updated" if existed_before else "created")]


def _build_handoff_body(sections: dict, idea_path: Path, title: str) -> str:
    today = _now_iso().split("T", 1)[0]
    extracted_rows = []
    for key in ("what", "who", "problem", "features", "stack", "milestone", "non_goals", "questions"):
        val = sections.get(key, "").strip() if key in sections else None
        present = "✓" if val else ("(empty)" if key in sections else "(missing)")
        extracted_rows.append(f"| `{key}` | {present} |")
    extracted_table = "\n".join(extracted_rows)

    unknown = sections.get("_unknown") or []
    unknown_block = ""
    if unknown:
        labels = ", ".join(f"'{label}'" for label, _ in unknown)
        unknown_block = (
            f"\n\nUnrecognized headings preserved under 'Other notes' in "
            f"`docs/BUILD_PLAN.md`: {labels}.\n"
        )

    return f"""---
title: "Session 001 — Idea Bootstrap"
date: {today}
status: shipped
---

# Session 001 — Idea Bootstrap

`context-kit seed` populated the initial project context from
`{idea_path.name}`. This handoff is a one-time historical record;
re-running seed updates the live files (BUILD_PLAN.md, the seed block
in `*_WHAT_IT_IS.md`, the seed block in `00-START-NEXT-SESSION.md`)
but does not rewrite this handoff. If the project's direction
changes substantially, write `SESSION_002_PIVOT.md` (or similar)
yourself to document the shift.

## Source idea

- File: `{idea_path.name}`
- Title: {title}
- Schema version: {SCHEMA_VERSION}

## Sections extracted

| Section | Status |
|---|---|
{extracted_table}{unknown_block}

## What seed wrote

| File | What changed |
|---|---|
| `docs/<APP>_WHAT_IT_IS.md` | TL;DR + non-goals (managed block) |
| `00-START-NEXT-SESSION.md` | FIRST THING + Queued Investigations (managed block; frontmatter `state:` → `seeded`) |
| `docs/topics/product.md` | Product framing (managed block) |
| `docs/BUILD_PLAN.md` | Full structured plan |
| `docs/handoffs/SESSION_001_IDEA_BOOTSTRAP.md` | This file |

## Next session

1. Read `00-START-NEXT-SESSION.md` — the FIRST THING is the milestone
   you wrote in `{idea_path.name}`.
2. Implement that milestone.
3. End the session by writing `docs/handoffs/SESSION_002_<slug>.md`
   and overwriting `00-START-NEXT-SESSION.md` with the next session's
   priorities. From this point on, the pattern's normal rules apply
   and seed steps out of the way.

## AI Notes

This handoff was generated deterministically by
`context-kit seed`. No LLM was involved. The file is part of the
permanent record of how the project bootstrapped. If the AI assistant
makes any consequential decision in Session 2 onward that turns out
to be wrong (or right despite pushback), log it in
`docs/TRUST_CALIBRATION.md` per the standard collaboration pattern.
"""


def _seed_product_topic(
    project: Path,
    sections: dict,
    idea_path: Path,
    *,
    force: bool,
    dry_run: bool,
) -> list[tuple[Path, str]]:
    path = project / "docs" / "topics" / "product.md"
    body = _wrap_block(_render_product_topic_body(sections), idea_path)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        new_text = _replace_or_insert_block(existing, body)
        action = "updated"
    else:
        new_text = (
            "---\n"
            "title: \"Product Framing\"\n"
            "status: seeded\n"
            "---\n\n"
            "# Product Framing\n\n"
            f"{body}\n"
        )
        action = "created"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    return [(path, action)]


def _seed_build_plan(
    project: Path,
    sections: dict,
    idea_path: Path,
    *,
    force: bool,
    dry_run: bool,
) -> list[tuple[Path, str]]:
    path = project / "docs" / "BUILD_PLAN.md"
    # Pass the raw idea text so recommend-stack can match on full context
    # (not just the parsed sections) when filling in a missing Tech stack.
    try:
        idea_text = idea_path.read_text(encoding="utf-8")
    except OSError:
        idea_text = ""
    body = _wrap_block(_render_build_plan_body(sections, idea_text), idea_path)
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        new_text = _replace_or_insert_block(existing, body)
        action = "updated"
    else:
        new_text = (
            "---\n"
            "title: \"Build Plan\"\n"
            "status: seeded\n"
            "---\n\n"
            "# Build Plan\n\n"
            f"{body}\n\n"
            "## Implementation notes\n\n"
            "*(your notes go here. This section survives re-seed.)*\n"
        )
        action = "created"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_text, encoding="utf-8")
    return [(path, action)]
