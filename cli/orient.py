"""context-kit `orient` subcommand: assemble the current project's
session-start orientation into a single plain-text report.

The output is the *single authoritative path* an agent (or a returning
human) reads at the start of a session. It points at the source-of-truth
docs in priority order so nothing gets re-derived from scattered files.

Run from inside a project that was scaffolded with `context-kit init`
(or any project that adopts the pattern: a ``00-START-NEXT-SESSION.md``
at the root and a ``docs/`` folder with the two-doc anchor).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

START_DOC = "00-START-NEXT-SESSION.md"
HANDOFFS_DIR = Path("docs/handoffs")
DOCS_DIR = Path("docs")
PATTERN_DIR = Path("docs/docs-pattern")

# Numbered session handoff: ``SESSION_<digits>_<anything>.md``. Files
# that don't match this shape (e.g. ``SESSION_ROADMAP_*.md``,
# ``SESSION_NOTES.md``) are not handoffs and must not be picked as
# "latest". The capture group holds the numeric session ID.
_HANDOFF_RE = re.compile(r"^SESSION_(\d+)_.+\.md$")

# How many lines of each doc to preview in the orient report. Enough to
# show the source-of-truth header + first real content; not so much that
# the report turns into a doc dump.
PREVIEW_LINES = 25


def run_orient(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else Path.cwd().resolve()

    if not _looks_like_context_kit_project(project):
        print(
            f"context-kit: {project} doesn't look like a context-kit project.\n"
            f"  Expected to find '{START_DOC}' or '{PATTERN_DIR}/' here.\n"
            f"  Run from inside a project scaffolded with `context-kit init`,\n"
            f"  or pass --project PATH.",
        )
        return 2

    sections: list[str] = []
    sections.append(_section_header(project))
    sections.append(_section_source_of_truth(project))
    sections.append(_section_start_here(project))
    sections.append(_section_anchors(project))
    sections.append(_section_latest_handoff(project))
    sections.append(_section_pattern_pointer(project))
    sections.append(_section_what_to_do_now())

    print("\n\n".join(s for s in sections if s).rstrip() + "\n")
    return 0


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _looks_like_context_kit_project(project: Path) -> bool:
    return (project / START_DOC).is_file() or (project / PATTERN_DIR).is_dir()


# ---------------------------------------------------------------------------
# Sections (each returns a markdown block or "" to omit)
# ---------------------------------------------------------------------------


def _section_header(project: Path) -> str:
    return (
        f"# context-kit orient\n"
        f"Project: {project.name}\n"
        f"Path:    {project}\n\n"
        f"Read each section in order. Runtime wins over narrative."
    )


def _section_source_of_truth(project: Path) -> str:
    """The authoritative path: which docs the agent must trust, in order."""
    what, inventory = _find_anchor_docs(project)
    lines = ["## SOURCE OF TRUTH (read in this order)"]
    lines.append(f"  1. {START_DOC}    — this session's priorities")
    if what:
        lines.append(f"  2. {what.relative_to(project)}    — narrative anchor")
    else:
        lines.append("  2. docs/<APP>_WHAT_IT_IS.md    — narrative anchor (NOT FOUND)")
    if inventory:
        lines.append(f"  3. {inventory.relative_to(project)}    — runtime anchor (regenerable; wins on conflict)")
    else:
        lines.append("  3. docs/<APP>_INVENTORY.md    — runtime anchor (NOT FOUND)")
    lines.append("  4. docs/handoffs/SESSION_<latest>_*.md    — what last session shipped")
    lines.append("")
    lines.append("If any other doc disagrees with the inventory, the inventory is right.")
    return "\n".join(lines)


def _section_start_here(project: Path) -> str:
    path = project / START_DOC
    if not path.is_file():
        return f"## START HERE\n  (missing) {START_DOC}"
    return f"## START HERE — {START_DOC}\n\n" + _preview(path)


def _section_anchors(project: Path) -> str:
    what, inventory = _find_anchor_docs(project)
    blocks = ["## ANCHORS (preview)"]
    if what:
        blocks.append(f"### {what.relative_to(project)}\n\n" + _preview(what))
    if inventory:
        blocks.append(f"### {inventory.relative_to(project)}\n\n" + _preview(inventory))
    if len(blocks) == 1:
        blocks.append("  (no anchor docs found under docs/)")
    return "\n\n".join(blocks)


def _section_latest_handoff(project: Path) -> str:
    handoffs_dir = project / HANDOFFS_DIR
    if not handoffs_dir.is_dir():
        return f"## LATEST HANDOFF\n  (missing) {HANDOFFS_DIR}/"

    latest = _latest_numbered_handoff(handoffs_dir)
    if latest is None:
        return f"## LATEST HANDOFF\n  (none yet) {HANDOFFS_DIR}/"

    rel = latest.relative_to(project)
    return f"## LATEST HANDOFF — {rel}\n\n" + _preview(latest)


def _latest_numbered_handoff(handoffs_dir: Path) -> Path | None:
    """Pick the most-recent numbered session handoff.

    Selection rule (in order):
    1. Only files matching ``SESSION_<digits>_*.md`` are considered.
       Non-numbered names (``SESSION_ROADMAP_*``, ``SESSION_NOTES``)
       are ignored entirely — they're not session handoffs and must
       not win selection on lexicographic luck.
    2. Sort by integer session number ascending. This makes
       ``SESSION_1098_*`` beat ``SESSION_999_*`` instead of losing
       to it under ASCII string ordering.
    3. Tiebreak on ``mtime`` ascending — when two handoffs share a
       session number (e.g. addendum / wrap pairs), the most-recently
       modified file wins.

    Returns ``None`` when no numbered handoffs exist (the directory
    may still hold non-handoff markdown).
    """
    candidates: list[tuple[int, float, Path]] = []
    for path in handoffs_dir.glob("SESSION_*.md"):
        if not path.is_file():
            continue
        match = _HANDOFF_RE.match(path.name)
        if match is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((int(match.group(1)), mtime, path))
    if not candidates:
        return None
    return max(candidates)[2]


def _section_pattern_pointer(project: Path) -> str:
    pattern_readme = project / PATTERN_DIR / "README.md"
    if not pattern_readme.is_file():
        return ""
    return (
        "## THE PATTERN\n"
        f"Full guide lives at {PATTERN_DIR}/. Most useful entry points:\n"
        f"  - {PATTERN_DIR}/05_start_here.md    (why 00-START-NEXT-SESSION.md exists)\n"
        f"  - {PATTERN_DIR}/01_two_doc_anchor.md (narrative vs runtime split)\n"
        f"  - {PATTERN_DIR}/02_drift_verifier.md (how runtime stays authoritative)\n"
        f"  - {PATTERN_DIR}/08_collaboration_roles.md (how AI and human share work)"
    )


def _section_what_to_do_now() -> str:
    return (
        "## WHAT TO DO NOW\n"
        "  1. If START HERE points at a 'FIRST THING', do that first.\n"
        "  2. Don't invent stats. If a number isn't in the anchors, say so.\n"
        "  3. End the session by writing the next handoff and overwriting\n"
        f"     {START_DOC} with the next session's priorities."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_anchor_docs(project: Path) -> tuple[Path | None, Path | None]:
    """Discover the two-doc anchor by suffix, since prefix is project-specific."""
    docs = project / DOCS_DIR
    if not docs.is_dir():
        return None, None
    what = _first_match(docs.glob("*_WHAT_IT_IS.md"))
    inventory = _first_match(docs.glob("*_INVENTORY.md"))
    return what, inventory


def _first_match(it: Iterable[Path]) -> Path | None:
    for p in sorted(it):
        if p.is_file():
            return p
    return None


def _preview(path: Path, limit: int = PREVIEW_LINES) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return f"  (could not read: {exc})"
    head = lines[:limit]
    body = "\n".join(head)
    if len(lines) > limit:
        body += f"\n... ({len(lines) - limit} more lines — open {path.name} to read in full)"
    return body
