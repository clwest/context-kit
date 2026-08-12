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
VERIFY_CONFIG_REL = Path(".context-kit/verify.yaml")

# Token embedded by `cli.inventory.render_block_body` when the
# context-kit-shape detectors don't match the project. When orient
# sees this marker inside the inventory file, it softens the
# "wins on conflict" framing: those rows are zero by detector design,
# not by repo absence, and using them as the runtime-truth anchor
# would mislead an agent.
_INVENTORY_LOW_SIGNAL_MARKER = "<!-- context-kit:inventory:low-signal -->"

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

    # --short is opt-in via argparse; tolerate absence (e.g. when
    # callers construct Namespace by hand for tests / scripts).
    if getattr(args, "short", False):
        print(render_orient(project, short=True).rstrip() + "\n")
        return 0

    print(render_orient(project).rstrip() + "\n")
    return 0


def render_orient(project: Path, *, short: bool = False) -> str:
    if short:
        return _render_short(project)

    sections: list[str] = []
    sections.append(_section_header(project))
    sections.append(_section_source_of_truth(project))
    sections.append(_section_start_here(project))
    sections.append(_section_session_start(project))
    sections.append(_section_anchors(project))
    sections.append(_section_pipeline(project))
    sections.append(_section_behavior_layer(project))
    sections.append(_section_translation_layer(project))
    sections.append(_section_do_nots(project))
    sections.append(_section_latest_handoff(project))
    sections.append(_section_runtime_state(project))
    sections.append(_section_pattern_pointer(project))
    sections.append(_section_what_to_do_now())
    return "\n\n".join(s for s in sections if s)


def render_chat_orient(project: Path) -> str:
    """Return a compact orientation block for chat prompts.

    Chat should keep the high-signal project rules but avoid dumping the
    full inventory preview when it would add boilerplate instead of
    grounding. The block is intentionally shorter than ``render_orient``.
    """
    sections: list[str] = []
    sections.append("## PROJECT ORIENTATION")
    sections.append("")
    sections.append(_section_source_of_truth(project))

    what, inventory = _find_anchor_docs(project)
    if what:
        sections.append("## WHAT_IT_IS PREVIEW")
        sections.append(f"### {what.relative_to(project)}\n\n" + _preview(what))

    if inventory and not _is_low_signal_inventory(inventory):
        sections.append("## INVENTORY PREVIEW")
        sections.append(f"### {inventory.relative_to(project)}\n\n" + _preview(inventory))

    latest_handoff = _section_latest_handoff(project)
    if latest_handoff:
        sections.append(latest_handoff)

    next_pointer = _short_next_task_pointer(project)
    if next_pointer:
        sections.append("## ACTIVE NEXT TASK SUMMARY")
        sections.append(next_pointer)

    return "\n\n".join(s for s in sections if s)


def _render_short(project: Path) -> str:
    """Compact orient: source-of-truth order, session-start doc,
    latest handoff, next-task pointer, doctor warning summary.

    Designed for repeated re-orientation mid-session, where the full
    report (with anchor previews) would burn context for nothing.
    """
    lines: list[str] = []
    lines.append("# context-kit orient (short)")
    lines.append(f"Project: {project.name}")
    lines.append(f"Path:    {project}")
    lines.append("")

    # Source-of-truth order — same logic as the full report, just
    # without the long preamble.
    lines.append(_section_source_of_truth(project))
    lines.append("")

    # Session-start index — filename only, no preview.
    session_start = _find_session_start_doc(project)
    if session_start is not None:
        rel = session_start.relative_to(project)
        lines.append("## SESSION START INDEX")
        lines.append(f"  {rel}    (open and read first)")
        lines.append("")

    # Translation layer — filename only, never the body, so --short
    # stays compact. The audience contract is too large to inline.
    translation = _find_translation_layer_doc(project)
    if translation is not None:
        rel = translation.relative_to(project)
        lines.append("## TRANSLATION LAYER")
        lines.append(f"  {rel}    (audience contract; same truth → different explanation)")
        lines.append("")

    # Latest numbered handoff — filename only.
    handoffs_dir = project / HANDOFFS_DIR
    if handoffs_dir.is_dir():
        latest = _latest_numbered_handoff(handoffs_dir)
        if latest is not None:
            rel = latest.relative_to(project)
            lines.append("## LATEST HANDOFF")
            lines.append(f"  {rel}")
            lines.append("")

    # Next-task pointer extracted from 00-START-NEXT-SESSION.md.
    next_pointer = _short_next_task_pointer(project)
    if next_pointer:
        lines.append("## NEXT TASK")
        lines.append(next_pointer)
        lines.append("")

    # Doctor warning summary — counts only, no per-check details.
    doctor_summary = _short_doctor_summary(project)
    if doctor_summary:
        lines.append("## DOCTOR")
        lines.append(doctor_summary)
        lines.append("")

    # Current runtime state block — version, tests, inventory freshness,
    # latest handoff, next session, doctor counts, drift summary. Same
    # contract as the full report so a returning agent gets the same
    # one-shot answer regardless of mode.
    runtime_state = _section_runtime_state(project)
    if runtime_state:
        lines.append(runtime_state)
        lines.append("")

    lines.append(
        "Run `context-kit orient` (no --short) to print full anchor previews."
    )
    return "\n".join(lines)


def _short_next_task_pointer(project: Path) -> str:
    """Return a 1–3 line excerpt of the start-here doc's next-task section.

    Tries each of these section headers in order, returning the first
    non-empty body (truncated to ~3 lines so --short stays compact):

    1. handwritten ``## Next session priorities`` / ``## Next task``
    2. handwritten ``## What's next`` (when not inside the adopt block)
    3. adopt-managed ``## What's next``

    Falls back to "  (see 00-START-NEXT-SESSION.md)" when nothing matches.
    """
    start_doc = project / START_DOC
    try:
        text = start_doc.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Look for handwritten next-task section first (outside any
    # adopt-managed block). If absent, fall through to the adopt
    # block's "What's next".
    handwritten = _strip_adopt_managed(text)
    handwritten_body = _first_section_body(
        handwritten,
        (
            r"^##\s+Next session priorit",
            r"^##\s+Next task\b",
            r"^##\s+Next priority\b",
            r"^##\s+Next step\b",
            r"^##\s+This session's priorities\b",
            r"^##\s+What's next\b",
            r"^##\s+Priorit",
        ),
    )
    if handwritten_body:
        return _short_excerpt(handwritten_body)

    managed_body = _adopt_managed_next(text)
    if managed_body:
        return _short_excerpt(managed_body)

    return f"  (see {START_DOC} — no recognized next-task section found)"


_ADOPT_START = "<!-- context-kit:adopt:start -->"
_ADOPT_END = "<!-- context-kit:adopt:end -->"


def _strip_adopt_managed(text: str) -> str:
    """Return ``text`` with adopt-managed blocks removed (outside-only view)."""
    out: list[str] = []
    cursor = 0
    while True:
        s = text.find(_ADOPT_START, cursor)
        if s == -1:
            out.append(text[cursor:])
            return "".join(out)
        out.append(text[cursor:s])
        e = text.find(_ADOPT_END, s + len(_ADOPT_START))
        if e == -1:
            return "".join(out)
        cursor = e + len(_ADOPT_END)


def _adopt_managed_next(text: str) -> str:
    """Return the body of ``## What's next`` from inside an adopt-managed block."""
    s = text.find(_ADOPT_START)
    if s == -1:
        return ""
    e = text.find(_ADOPT_END, s + len(_ADOPT_START))
    block = text[s + len(_ADOPT_START):] if e == -1 else text[s + len(_ADOPT_START):e]
    return _first_section_body(block, (r"^##\s+What's next\b",))


def _first_section_body(text: str, header_patterns: tuple[str, ...]) -> str:
    """Return the body of the first section whose header matches any
    pattern in ``header_patterns`` (case-insensitive). Body runs from
    the line after the header to the next ``##`` or end of text.
    Returns "" when no header matches.
    """
    compiled = [re.compile(p, re.IGNORECASE) for p in header_patterns]
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if any(p.search(line) for p in compiled):
            body_lines: list[str] = []
            for follow in lines[idx + 1:]:
                if follow.startswith("## "):
                    break
                body_lines.append(follow)
            return "\n".join(body_lines).strip()
    return ""


def _short_excerpt(body: str, max_lines: int = 6) -> str:
    """Indent ``body`` to two spaces, truncate to ``max_lines`` non-blank
    lines plus a trailing ellipsis when more remain. Keeps --short tight."""
    raw_lines = body.splitlines()
    kept: list[str] = []
    skipped_more = False
    for line in raw_lines:
        if len(kept) >= max_lines:
            skipped_more = True
            break
        kept.append(line)
    indented = ["  " + ln if ln else "" for ln in kept]
    if skipped_more:
        indented.append("  ...")
    return "\n".join(indented)


def _short_doctor_summary(project: Path) -> str:
    """Run doctor in-process and summarize counts only.

    Lazy import — keeps the cold-start cost off the regular orient
    path. Failures degrade to ``"  (doctor unavailable)"`` rather
    than crashing orient.
    """
    try:
        from .doctor import run_all_checks  # type: ignore
    except ImportError:
        return "  (doctor unavailable)"
    try:
        results = run_all_checks(project)
    except Exception:
        return "  (doctor failed; run `context-kit doctor` for details)"
    blocking = sum(1 for r in results if r.status == "blocking")
    warnings = sum(1 for r in results if r.status == "warning")
    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    summary = f"  {blocking} blocking, {warnings} warnings, {ok} ok, {skipped} skipped"
    if blocking == 0 and warnings == 0:
        return summary + " — clean."
    if warnings > 0 and blocking == 0:
        # Name the warning labels so --short is actionable without a
        # second invocation. Cap at 5 to keep the summary short.
        names = [r.label for r in results if r.status == "warning"][:5]
        more = "" if len(names) >= sum(1 for r in results if r.status == "warning") else " ..."
        return summary + "\n  warnings: " + ", ".join(names) + more
    return summary


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
        1. WHAT_IT_IS         (narrative)
        2. INVENTORY          (runtime, regenerable)
        3. PIPELINE           (runtime flow map; optional)
        4. BEHAVIOR_LAYER     (voice, presentation, constraint preservation; optional)
        5. TRANSLATION_LAYER  (audience contract; optional, project-owned)
        6. DO_NOTS            (project-specific anti-patterns; optional)
        7. handoff + 00-START-NEXT-SESSION (current state / next priority)

    When the inventory carries the LOW-SIGNAL marker, the line for
    that anchor is reworded so the agent doesn't treat detector-zero
    rows as authoritative — they're zero by detector design, not by
    repo absence.
    """
    what, inventory = _find_anchor_docs(project)
    pipeline = _find_pipeline_doc(project)
    behavior = _find_behavior_layer_doc(project)
    translation = _find_translation_layer_doc(project)
    do_nots = _find_do_nots_doc(project)
    session_start = _find_session_start_doc(project)
    inventory_low_signal = inventory is not None and _is_low_signal_inventory(inventory)
    lines = ["## SOURCE OF TRUTH (read in this order)"]
    if session_start:
        # Project-owned short-form index — call out as the entry
        # point above the detected anchors. Mature repos write this
        # file specifically so a returning agent has a 30-second
        # answer before the long anchor docs.
        lines.append(
            f"  0. {session_start.relative_to(project)}    "
            "— project-owned session-start index (read this first)"
        )
    if what:
        lines.append(f"  1. {what.relative_to(project)}    — narrative anchor")
    else:
        lines.append("  1. docs/<APP>_WHAT_IT_IS.md    — narrative anchor (NOT FOUND)")
    if inventory:
        if inventory_low_signal:
            lines.append(
                f"  2. {inventory.relative_to(project)}    — runtime anchor "
                "(LOW-SIGNAL: context-kit-shape detectors didn't match this repo; "
                "treat counts as informational, not authoritative)"
            )
        else:
            lines.append(f"  2. {inventory.relative_to(project)}    — runtime anchor (regenerable; wins on conflict)")
    else:
        lines.append("  2. docs/<APP>_INVENTORY.md    — runtime anchor (NOT FOUND)")
    if pipeline:
        lines.append(f"  3. {pipeline.relative_to(project)}    — runtime flow map (entry points, guards, retrieval, scrubs)")
    else:
        lines.append("  3. docs/<APP>_PIPELINE.md    — runtime flow map (optional; recommended for LLM/agent/task projects)")
    if behavior:
        lines.append(f"  4. {behavior.relative_to(project)}    — behavior layer (voice, UI/source-of-truth, constraint preservation)")
    else:
        lines.append("  4. docs/<APP>_BEHAVIOR_LAYER.md    — behavior layer (optional; recommended for chat/voice/persona surfaces)")
    if translation:
        lines.append(
            f"  5. {translation.relative_to(project)}    "
            "— translation layer (audience contract: same truth → different explanation, zero invention)"
        )
    else:
        lines.append(
            "  5. docs/<APP>_TRANSLATION_LAYER.md    "
            "— translation layer (optional; recommended for multi-audience / stakeholder projects)"
        )
    if do_nots:
        lines.append(f"  6. {do_nots.relative_to(project)}    — project-specific anti-patterns / dos and don'ts")
    else:
        lines.append("  6. docs/<APP>_DO_NOTS.md    — project-specific anti-patterns (optional)")
    lines.append(
        f"  7. docs/handoffs/SESSION_<latest>_*.md + {START_DOC}    — what last session shipped + this session's priorities"
    )
    lines.append("")
    if inventory_low_signal:
        lines.append(
            "Inventory is LOW-SIGNAL for this repo — detectors didn't match. "
            "Verify counts directly (ls / git ls-files / your test runner) "
            "before relying on them; do not present zero counts as facts."
        )
    else:
        lines.append("If any other doc disagrees with the inventory, the inventory is right.")
    # Anchor-ambiguity warnings: when ``docs/`` has multiple
    # ``*_INVENTORY.md`` (or ``*_WHAT_IT_IS.md``) files and verify.yaml
    # doesn't pin one, the alphabetic-first selection is meaningless.
    # Surface this so the project owner can fix it via canonical_docs.
    for warning in _anchor_ambiguity(project):
        lines.append("")
        lines.append(warning)
    return "\n".join(lines)


def _is_low_signal_inventory(inventory_path: Path) -> bool:
    """Return True if the inventory file carries the LOW-SIGNAL marker.

    Read failures fall back to False — a failure to detect is the
    safer default than incorrectly downgrading a real inventory.
    """
    try:
        text = inventory_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return _INVENTORY_LOW_SIGNAL_MARKER in text


def _section_start_here(project: Path) -> str:
    path = project / START_DOC
    if not path.is_file():
        return f"## START HERE\n  (missing) {START_DOC}"
    return f"## START HERE — {START_DOC}\n\n" + _preview(path)


def _section_session_start(project: Path) -> str:
    """Optional project-owned session-start index.

    Mature repos accumulate 250+ lines across the two-doc anchor pair
    plus the latest handoff plus 00-START-NEXT-SESSION; that's too
    much to re-read on every session. ``docs/<APP>_SESSION_START.md``
    (or ``docs/SESSION_START.md``) is the project's *handwritten*
    short-form index — read order, canonical next-task location,
    current baseline, smoke checks, what to skip. ``orient`` shows it
    above the anchor previews so a returning agent has the 30-second
    answer before the long anchors.

    Silently omitted when absent. Older projects keep printing the
    same orient report unchanged.
    """
    session_start = _find_session_start_doc(project)
    if session_start is None:
        return ""
    rel = session_start.relative_to(project)
    return f"## SESSION START INDEX — {rel}\n\n" + _preview(session_start)


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


def _section_behavior_layer(project: Path) -> str:
    """Optional behavior layer (voice, presentation, constraint preservation).
    Silently omitted if absent so older projects keep working."""
    behavior = _find_behavior_layer_doc(project)
    if behavior is None:
        return ""
    rel = behavior.relative_to(project)
    return f"## BEHAVIOR LAYER — {rel}\n\n" + _preview(behavior)


def _section_translation_layer(project: Path) -> str:
    """Optional translation-layer contract.

    Lives between the behavior layer (how it sounds) and project-specific
    do-nots (what to never do). The translation layer says **how to
    explain the same source-of-truth to different audiences without
    inventing facts** — same truth, different framing, zero distortion.

    Silently omitted if absent so older projects keep working unchanged.
    """
    translation = _find_translation_layer_doc(project)
    if translation is None:
        return ""
    rel = translation.relative_to(project)
    return f"## TRANSLATION LAYER — {rel}\n\n" + _preview(translation)


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
    """Discover the two-doc anchor.

    Resolution order — project-local pin wins over alphabetic-luck:

    1. ``.context-kit/verify.yaml``'s ``canonical_docs`` list. If it
       names exactly one ``*_WHAT_IT_IS.md`` (or ``*_INVENTORY.md``)
       file that exists on disk, that file is the anchor.
    2. Otherwise fall back to the suffix-glob (``docs/*_INVENTORY.md``)
       and pick the alphabetic-first match — preserving behavior for
       projects without verify.yaml or with a single matching candidate.

    When multiple suffix-glob candidates exist and the config does not
    pin exactly one, ``_section_source_of_truth`` emits a visible
    warning (via :func:`_anchor_ambiguity`) so the project owner can
    disambiguate by editing ``canonical_docs``. The current selection
    is still returned — orient never crashes on an ambiguous tree.

    Older projects with a single ``*_INVENTORY.md`` and no verify.yaml
    keep their existing behavior unchanged.
    """
    docs = project / DOCS_DIR
    if not docs.is_dir():
        return None, None
    canonical = _load_canonical_docs(project)
    what = _resolve_anchor(project, docs, "_WHAT_IT_IS.md", canonical)
    inventory = _resolve_anchor(project, docs, "_INVENTORY.md", canonical)
    return what, inventory


def _resolve_anchor(
    project: Path,
    docs: Path,
    suffix: str,
    canonical_docs: list[str],
) -> Path | None:
    """Pick the anchor for a given suffix: pinned-by-config first, else
    alphabetic-first of the suffix-glob matches."""
    matches = sorted(p for p in docs.glob(f"*{suffix}") if p.is_file())
    pinned = _pin_from_canonical(project, matches, canonical_docs, suffix)
    if pinned is not None:
        return pinned
    return matches[0] if matches else None


def _pin_from_canonical(
    project: Path,
    suffix_matches: list[Path],
    canonical_docs: list[str],
    suffix: str,
) -> Path | None:
    """Return the suffix-match pinned by ``canonical_docs``, or None.

    A pin requires:
      - ``canonical_docs`` to contain **exactly one** entry ending in
        ``suffix`` (multiple ``*_INVENTORY.md`` entries → not a pin),
      - that entry to exist on disk under the project root,
      - the entry path to match one of the suffix-glob results
        (so a config typo doesn't silently override the glob).

    Returns None on any failure mode, deferring to the alphabetic-first
    fallback.
    """
    if not canonical_docs or not suffix_matches:
        return None

    matching = [c for c in canonical_docs if c.endswith(suffix)]
    if len(matching) != 1:
        return None

    candidate_rel = matching[0]
    suffix_rels = {str(p.relative_to(project)) for p in suffix_matches}
    if candidate_rel not in suffix_rels:
        return None

    return project / candidate_rel


def _anchor_ambiguity(project: Path) -> list[str]:
    """Return human-readable warning lines for anchors that have multiple
    unpinned suffix-glob candidates.

    Empty list means the tree is unambiguous (single candidate, or
    config pins one). Each returned string is a one-line warning that
    callers (currently :func:`_section_source_of_truth`) print verbatim
    inside the orient report so the message stays in the same buffer
    as the rest of the source-of-truth output.
    """
    docs = project / DOCS_DIR
    if not docs.is_dir():
        return []
    canonical = _load_canonical_docs(project)

    warnings: list[str] = []
    for label, suffix in (("WHAT_IT_IS", "_WHAT_IT_IS.md"), ("INVENTORY", "_INVENTORY.md")):
        matches = sorted(p for p in docs.glob(f"*{suffix}") if p.is_file())
        if len(matches) <= 1:
            continue
        if _pin_from_canonical(project, matches, canonical, suffix) is not None:
            continue
        rels = [str(p.relative_to(project)) for p in matches]
        warnings.append(
            f"WARNING: {len(matches)} {label} candidates found "
            f"({', '.join(rels)}). Picked '{rels[0]}' alphabetically. "
            f"To disambiguate, list exactly one of these in "
            f"`{VERIFY_CONFIG_REL}` under `canonical_docs:`."
        )
    return warnings


def _load_canonical_docs(project: Path) -> list[str]:
    """Return the project's ``canonical_docs`` list from verify.yaml.

    Read failures, missing files, and parse errors all return ``[]`` so
    that orient falls back to suffix-glob behavior. Project-local config
    is **additive**; its absence must not break older repos.

    The parser is intentionally minimal: line-oriented, no nesting
    beyond the top-level ``canonical_docs:`` list. It mirrors the
    conservative parser in ``cli/verify.py`` so the two stay in sync
    without a hard cross-module dependency.
    """
    config_path = project / VERIFY_CONFIG_REL
    try:
        text = config_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    canonical: list[str] = []
    in_canonical = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            in_canonical = key == "canonical_docs"
            continue
        if in_canonical and re.match(r"^\s*-\s+", line):
            item = line.split("-", 1)[1].strip().strip("'\"")
            if not item:
                continue
            value = item.replace("\\", "/")
            if value.startswith("./"):
                value = value[2:]
            while value.startswith("/"):
                value = value[1:]
            canonical.append(value)
    return canonical


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


def _find_behavior_layer_doc(project: Path) -> Path | None:
    """Discover the behavior layer doc (voice / presentation / constraint
    preservation rules).

    Search order — first hit wins:
    1. ``docs/<APP>_BEHAVIOR_LAYER.md`` (matches the anchor naming)
    2. ``docs/BEHAVIOR_LAYER.md`` (plain)
    3. ``BEHAVIOR_LAYER.md`` at the repo root

    Absent → returns None and orient silently omits the BEHAVIOR LAYER
    section. Older projects keep working unchanged.

    To avoid colliding with the pipeline glob (``*_PIPELINE.md``), the
    suffix used here is ``_BEHAVIOR_LAYER.md``. Both anchor docs can
    coexist in the same project.
    """
    docs = project / DOCS_DIR
    if docs.is_dir():
        suffixed = _first_match(docs.glob("*_BEHAVIOR_LAYER.md"))
        if suffixed is not None:
            return suffixed
        plain = docs / "BEHAVIOR_LAYER.md"
        if plain.is_file():
            return plain
    root_plain = project / "BEHAVIOR_LAYER.md"
    if root_plain.is_file():
        return root_plain
    return None


def _find_translation_layer_doc(project: Path) -> Path | None:
    """Discover the translation-layer doc (audience contract).

    Search order — first hit wins:
    1. ``docs/<APP>_TRANSLATION_LAYER.md`` (matches anchor naming)
    2. ``docs/TRANSLATION_LAYER.md`` (plain)
    3. ``TRANSLATION_LAYER.md`` at the repo root

    Absent → returns None and orient silently omits the
    TRANSLATION LAYER section. Older projects keep working unchanged.

    To avoid colliding with the pipeline / behavior-layer globs
    (``*_PIPELINE.md`` / ``*_BEHAVIOR_LAYER.md``), the suffix used
    here is ``_TRANSLATION_LAYER.md`` — distinct enough that
    ``glob("*_TRANSLATION_LAYER.md")`` cannot accidentally match
    a pipeline or behavior-layer doc.
    """
    docs = project / DOCS_DIR
    if docs.is_dir():
        suffixed = _first_match(docs.glob("*_TRANSLATION_LAYER.md"))
        if suffixed is not None:
            return suffixed
        plain = docs / "TRANSLATION_LAYER.md"
        if plain.is_file():
            return plain
    root_plain = project / "TRANSLATION_LAYER.md"
    if root_plain.is_file():
        return root_plain
    return None


def _find_session_start_doc(project: Path) -> Path | None:
    """Discover the project-owned session-start index (handwritten).

    Search order — first hit wins:
    1. ``docs/<APP>_SESSION_START.md`` (matches anchor naming)
    2. ``docs/SESSION_START.md`` (plain)
    3. ``SESSION_START.md`` at the repo root

    Absent → returns None and orient silently omits the SESSION
    START INDEX section so older projects (pre-template) keep working.

    Note: this is *project-owned*. ``adopt`` / ``seed`` /
    ``inventory --write`` must not touch it. The starter template at
    ``cli/_starter/docs/<APP_UPPER>_SESSION_START.md`` is materialized
    once on ``init``; further runs leave it alone.
    """
    docs = project / DOCS_DIR
    if docs.is_dir():
        suffixed = _first_match(docs.glob("*_SESSION_START.md"))
        if suffixed is not None:
            return suffixed
        plain = docs / "SESSION_START.md"
        if plain.is_file():
            return plain
    root_plain = project / "SESSION_START.md"
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


# ---------------------------------------------------------------------------
# Runtime state section (Truth/State Layer — orient side)
# ---------------------------------------------------------------------------


_MAX_DRIFT_LINES = 6  # Cap on drift-summary lines so the section stays compact.


def _section_runtime_state(project: Path) -> str:
    """Render the ``## CURRENT RUNTIME STATE`` block.

    Pulls runtime facts from :mod:`cli.state` and the doctor's aggregate
    check results so a returning agent can see — without running anything
    extra — the package version, test count, inventory freshness, latest
    handoff, next-expected session number, doctor warning/blocking
    counts, and a one-line-per-category drift summary.

    Spec sources:
      - ``00-START-NEXT-SESSION.md`` "Truth/State Layer (orient side)"
      - ``docs/handoffs/SESSION_015_POST_V0_15_FEATURE_BURST.md``
      - ``tests/test_truth_state.py::TestOrientRuntimeState`` (the contract)

    Constraints (per the spec):
      - No CLI argument changes, no external dependencies.
      - Reuse ``cli.state`` and ``cli.doctor`` helpers; never re-shell
        ``unittest discover``.
      - Doctor failures degrade to ``"  Doctor: unavailable"`` rather
        than crashing orient — runtime-state is informational, not a
        new gate.

    Lazy imports keep the cold-start cost off the regular orient path
    when the project hasn't bothered to scaffold a tests/ tree yet.
    """
    try:
        from . import state as _state  # type: ignore
    except ImportError:
        return ""

    lines: list[str] = ["## CURRENT RUNTIME STATE"]

    # Version: read from pyproject.toml. Emitted only when a real
    # version is available — the literal token "version" in an "(unknown)"
    # placeholder line is enough to tip the audit-response classifier's
    # token-overlap threshold for unrelated claims, so projects without
    # a pyproject.toml simply omit this line.
    try:
        version = _state.get_current_version(project)
    except Exception:
        version = None
    if version:
        lines.append(f"  Version: {version}")

    # Tests: actual unittest-discovery count, optionally compared to the
    # inventory's recorded count. Spec says read inventory first; we
    # show both when they exist so drift is visible inline.
    try:
        actual = _state.get_actual_test_count(project)
    except Exception:
        actual = None
    try:
        recorded = _state.get_inventory_test_count(project)
    except Exception:
        recorded = None
    if actual is not None and recorded is not None:
        if actual == recorded:
            lines.append(f"  Tests: {actual} (matches inventory)")
        else:
            lines.append(
                f"  Tests: {actual} discovered, {recorded} in inventory (drift)"
            )
    elif actual is not None:
        lines.append(f"  Tests: {actual} discovered")
    elif recorded is not None:
        lines.append(f"  Tests: {recorded} in inventory (no live count)")
    else:
        lines.append("  Tests: (unknown)")

    # Inventory freshness: status + reason from the existing helper.
    try:
        inv_status, inv_reason = _state.get_inventory_status(project)
    except Exception:
        inv_status, inv_reason = "unknown", ""
    inv_line = f"  Inventory: {inv_status}"
    if inv_reason:
        inv_line += f" — {inv_reason}"
    lines.append(inv_line)

    # Latest handoff + next expected session number. Both lines are
    # printed in both full and short modes per the test contract; full
    # asserts on "Latest handoff: SESSION_NNN" and short asserts on
    # "Next session: SESSION_NNN+1".
    try:
        latest = _state.get_latest_handoff(project)
    except Exception:
        latest = None
    if latest is not None:
        latest_id = f"SESSION_{latest.number:03d}"
        next_id = f"SESSION_{latest.number + 1:03d}"
        lines.append(f"  Latest handoff: {latest_id}")
        lines.append(f"  Next session: {next_id}")
    else:
        lines.append("  Latest handoff: (none yet)")
        lines.append("  Next session: SESSION_001")

    # Doctor counts + drift summary. Wrapped in try/except so an
    # internal doctor failure (subprocess, missing tool, etc.) doesn't
    # crash orient — the section degrades to "Doctor: unavailable".
    blocking, warnings, drift_lines = _summarize_doctor(project)
    if blocking is None:
        lines.append("  Doctor: unavailable")
    else:
        lines.append(f"  Doctor: {blocking} blocking, {warnings} warnings")
        for drift_line in drift_lines:
            lines.append(f"  - {drift_line}")

    return "\n".join(lines)


def _summarize_doctor(
    project: Path,
) -> tuple[int | None, int, list[str]]:
    """Run the doctor in-process and return (blocking, warnings, drift_lines).

    ``blocking`` is ``None`` when the doctor itself fails to load or
    crashes — :func:`_section_runtime_state` uses that to render the
    ``Doctor: unavailable`` fallback.

    ``drift_lines`` is one short line per warning, capped at
    :data:`_MAX_DRIFT_LINES` so the runtime-state block stays compact.
    Each line is the check label plus, when present, a short tail of
    the detail string (truncated for readability).
    """
    try:
        from .doctor import run_all_checks  # type: ignore
    except ImportError:
        return None, 0, []
    try:
        results = run_all_checks(project)
    except Exception:
        return None, 0, []

    blocking = sum(1 for r in results if r.status == "blocking")
    warnings = sum(1 for r in results if r.status == "warning")

    drift_lines: list[str] = []
    for r in results:
        if r.status != "warning":
            continue
        if len(drift_lines) >= _MAX_DRIFT_LINES:
            drift_lines.append("...")
            break
        line = r.label
        detail = getattr(r, "detail", "")
        if detail:
            short_detail = " ".join(detail.split())
            if len(short_detail) > 80:
                short_detail = short_detail[:77] + "..."
            line = f"{line}: {short_detail}"
        drift_lines.append(line)
    return blocking, warnings, drift_lines
