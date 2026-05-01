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
    sections.append(_section_pipeline(project))
    sections.append(_section_do_nots(project))
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
    """The authoritative path: which docs the agent must trust, in order.

    Ordering — concept first, runtime state last:
        1. WHAT_IT_IS    (narrative)
        2. INVENTORY     (runtime, regenerable)
        3. PIPELINE      (runtime flow map; optional)
        4. DO_NOTS       (project-specific anti-patterns; optional)
        5. handoff + 00-START-NEXT-SESSION (current state / next priority)
    """
    what, inventory = _find_anchor_docs(project)
    pipeline = _find_pipeline_doc(project)
    do_nots = _find_do_nots_doc(project)
    lines = ["## SOURCE OF TRUTH (read in this order)"]
    if what:
        lines.append(f"  1. {what.relative_to(project)}    — narrative anchor")
    else:
        lines.append("  1. docs/<APP>_WHAT_IT_IS.md    — narrative anchor (NOT FOUND)")
    if inventory:
        lines.append(f"  2. {inventory.relative_to(project)}    — runtime anchor (regenerable; wins on conflict)")
    else:
        lines.append("  2. docs/<APP>_INVENTORY.md    — runtime anchor (NOT FOUND)")
    if pipeline:
        lines.append(f"  3. {pipeline.relative_to(project)}    — runtime flow map (entry points, guards, retrieval, scrubs)")
    else:
        lines.append("  3. docs/<APP>_PIPELINE.md    — runtime flow map (optional; recommended for LLM/agent/task projects)")
    if do_nots:
        lines.append(f"  4. {do_nots.relative_to(project)}    — project-specific anti-patterns / dos and don'ts")
    else:
        lines.append("  4. docs/<APP>_DO_NOTS.md    — project-specific anti-patterns (optional)")
    lines.append(
        f"  5. docs/handoffs/SESSION_<latest>_*.md + {START_DOC}    — what last session shipped + this session's priorities"
    )
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


def _section_pipeline(project: Path) -> str:
    """Optional runtime flow map. Silently omitted if absent so older
    projects (pre-PIPELINE.md) keep printing the same orient report."""
    pipeline = _find_pipeline_doc(project)
    if pipeline is None:
        return ""
    rel = pipeline.relative_to(project)
    return f"## PIPELINE — {rel}\n\n" + _preview(pipeline)


def _section_do_nots(project: Path) -> str:
    """Optional project-level dos-and-don'ts doc. Silently omitted if absent."""
    do_nots = _find_do_nots_doc(project)
    if do_nots is None:
        return ""
    rel = do_nots.relative_to(project)
    return f"## DO NOTS — {rel}\n\n" + _preview(do_nots)


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


def _find_pipeline_doc(project: Path) -> Path | None:
    """Discover the runtime flow map.

    Search order — first hit wins:
    1. ``docs/<APP>_PIPELINE.md`` (matches the two-doc anchor naming)
    2. ``docs/PIPELINE.md`` (plain, no app prefix)
    3. ``PIPELINE.md`` at the repo root (compatibility with projects
       that keep flow docs at the top level)

    Absent → returns None and orient silently omits the PIPELINE
    section, so older projects (pre-PIPELINE.md) keep working.
    """
    docs = project / DOCS_DIR
    if docs.is_dir():
        suffixed = _first_match(docs.glob("*_PIPELINE.md"))
        if suffixed is not None:
            return suffixed
        plain = docs / "PIPELINE.md"
        if plain.is_file():
            return plain
    root_plain = project / "PIPELINE.md"
    if root_plain.is_file():
        return root_plain
    return None


def _find_do_nots_doc(project: Path) -> Path | None:
    """Discover an optional project-level DO_NOTS doc.

    Search order — first hit wins:
    1. ``docs/<APP>_DO_NOTS.md``
    2. ``docs/DO_NOTS.md``
    3. ``DO_NOTS.md`` at the repo root

    Absent → returns None. Pattern teaching docs at
    ``docs/docs-pattern/06_dos_and_donts.md`` are NOT considered an
    anchor; this discovery looks for project-specific lessons.
    """
    docs = project / DOCS_DIR
    if docs.is_dir():
        suffixed = _first_match(docs.glob("*_DO_NOTS.md"))
        if suffixed is not None:
            return suffixed
        plain = docs / "DO_NOTS.md"
        if plain.is_file():
            return plain
    root_plain = project / "DO_NOTS.md"
    if root_plain.is_file():
        return root_plain
    return None


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
