"""context-kit ``handoff`` subcommand: session-end housekeeping.

One operator action; two side-effects.

**Re-stamp anchor docs** (drift-prevention item 2): bump every anchor
doc's ``last_revised:`` frontmatter to the closing session's date in
one shot. The forgetting surface this removes is per-slice — sessions
that landed real work shipped without their narrative anchor's date
moving (see SESSION 147 drift audit).

**Calibration drift detection** (drift-prevention item 3): parse the
session's handoff for a ``## Calibration moments worth carrying`` or
``## AI Notes`` section and compare its subsections against
``docs/TRUST_CALIBRATION.md`` entries dated to the same handoff. Report
``✓`` for matched / ``⚠`` for missing. Read-only — never writes to
TRUST_CALIBRATION (the headline translation from prose to the
5-field shape is operator judgment, not a deterministic transform).

Deterministic. No LLM calls.

CLI shape::

    context-kit handoff write <N> [--project PATH] [--dry-run] [--date YYYY-MM-DD]

Exit codes:
- 0 on success (calibration warnings are advisory, mirroring ``doctor``)
- 2 on bad input (project not a dir, handoff for N missing, N not int)
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

# Anchor docs the re-stamp touches. Globs are matched against
# ``project/docs/``. INVENTORY is intentionally excluded — it's managed
# by ``inventory --write`` and has its own timestamp surface.
ANCHOR_DOC_GLOBS = (
    "*_WHAT_IT_IS.md",
    "*_PIPELINE.md",
    "*_BEHAVIOR_LAYER.md",
    "*_TRANSLATION_LAYER.md",
    "*_SESSION_START.md",
)

# Section headings that may contain calibration moments worth promoting
# to TRUST_CALIBRATION.md. The recent example-agent-os convention is
# "Calibration moments worth carrying"; the original collab-roles guide
# uses "AI Notes". Accept both — fuzzy on either word.
CALIBRATION_HEADING_PATTERNS = (
    re.compile(r"^##\s+calibration\s+moments?\b", re.IGNORECASE),
    re.compile(r"^##\s+ai\s+notes?\b", re.IGNORECASE),
)

# Stopwords stripped before fuzzy headline match. Conservative — only
# strip what's nearly always noise in this context.
_FUZZY_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "at",
    "is", "was", "be", "been", "by", "from", "with", "without",
    "into", "onto", "as", "but", "this", "that", "it", "its",
    "ai", "operator", "session",  # very common in our handoffs
})

_FUZZY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TRUST_CAL_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s+[—\-]\s*(.+?)\s*$")

# Match `date: YYYY-MM-DD` (with optional quoting) in handoff frontmatter.
_HANDOFF_DATE_RE = re.compile(r"^date\s*:\s*['\"]?(\d{4}-\d{2}-\d{2})", re.MULTILINE)

# Frontmatter delimiter — both `---\n` and `---\r\n` paths handled by
# the parse helper. Anchor docs in the wild use unix line endings.
_FRONTMATTER_DELIM = "---\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_handoff_write(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    try:
        session = int(args.session)
    except (TypeError, ValueError):
        print(f"context-kit: session must be an integer, got {args.session!r}.")
        return 2

    handoff_path = find_handoff_for_session(project, session)
    if handoff_path is None:
        print(
            f"context-kit: no handoff for SESSION {session} found under "
            f"docs/handoffs/. Write the handoff first, then re-run."
        )
        return 2

    date = args.date or extract_handoff_date(handoff_path) or _today_iso()
    if not _looks_like_iso_date(date):
        print(f"context-kit: --date must be YYYY-MM-DD, got {date!r}.")
        return 2

    dry_run = bool(args.dry_run)

    # --- item 2: re-stamp anchor docs ---------------------------------------
    restamp_results = restamp_anchor_docs(project, session=session, date=date, dry_run=dry_run)
    _print_restamp_summary(restamp_results, project, dry_run=dry_run)

    # --- item 3: calibration drift detection --------------------------------
    cal_results = audit_calibration_promotion(project, handoff_path=handoff_path, handoff_date=date)
    _print_calibration_summary(cal_results)

    return 0


# ---------------------------------------------------------------------------
# Handoff discovery
# ---------------------------------------------------------------------------


def find_handoff_for_session(project: Path, session: int) -> Optional[Path]:
    """Return the handoff file for SESSION_<NNN>_*.md, or None.

    The filename's number is normalized to three zero-padded digits, but
    older handoffs in the wild use 1, 2, or 3 digits. Match all three.
    """
    handoffs = project / "docs" / "handoffs"
    if not handoffs.is_dir():
        return None
    for width in (3, 2, 1):
        token = f"SESSION_{session:0{width}d}_"
        for path in handoffs.glob(f"{token}*.md"):
            if path.is_file():
                return path
    return None


def extract_handoff_date(handoff_path: Path) -> Optional[str]:
    """Parse ``date: YYYY-MM-DD`` out of the handoff's frontmatter.

    Returns None when the file has no frontmatter or no date field.
    """
    try:
        text = handoff_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    frontmatter = text[3:end]
    match = _HANDOFF_DATE_RE.search(frontmatter)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Item 2 — anchor doc re-stamping
# ---------------------------------------------------------------------------


@dataclass
class RestampResult:
    path: Path
    action: str  # "restamped" | "skipped (no frontmatter)" | "skipped (no anchor fields)" | "unchanged"
    last_revised_before: Optional[str] = None
    last_revised_after: Optional[str] = None
    covers_before: Optional[str] = None
    covers_after: Optional[str] = None


def restamp_anchor_docs(
    project: Path,
    *,
    session: int,
    date: str,
    dry_run: bool,
) -> list[RestampResult]:
    docs = project / "docs"
    if not docs.is_dir():
        return []
    results: list[RestampResult] = []
    for path in _discover_anchor_docs(docs):
        result = _restamp_one(path, session=session, date=date, dry_run=dry_run)
        results.append(result)
    return results


def _discover_anchor_docs(docs: Path) -> list[Path]:
    seen: dict[Path, None] = {}
    for pattern in ANCHOR_DOC_GLOBS:
        for path in sorted(docs.glob(pattern)):
            if path.is_file():
                seen[path] = None
    return list(seen.keys())


def _restamp_one(
    path: Path,
    *,
    session: int,
    date: str,
    dry_run: bool,
) -> RestampResult:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return RestampResult(path=path, action="skipped (read failed)")

    frontmatter, body = _split_frontmatter(text)
    if frontmatter is None:
        return RestampResult(path=path, action="skipped (no frontmatter)")

    has_generated = bool(re.search(r"^generated\s*:", frontmatter, re.MULTILINE))
    has_last_revised = bool(re.search(r"^last_revised\s*:", frontmatter, re.MULTILINE))
    has_covers = bool(re.search(r"^covers_sessions\s*:", frontmatter, re.MULTILINE))

    # A doc qualifies for re-stamping when it has at least one of the
    # anchor-shape fields. Docs with frontmatter that's purely about
    # other things (e.g. blog post `tags:`) are skipped.
    if not (has_generated or has_last_revised or has_covers):
        return RestampResult(path=path, action="skipped (no anchor fields)")

    new_last_revised = f"{date} (SESSION {session})"
    new_frontmatter, lr_before = _set_or_insert_field(
        frontmatter,
        field="last_revised",
        new_value=new_last_revised,
        insert_after="generated",
    )

    covers_before = covers_after = None
    if has_covers:
        new_frontmatter, covers_before, covers_after = _bump_covers_sessions(
            new_frontmatter, session=session
        )

    if new_frontmatter == frontmatter:
        return RestampResult(
            path=path,
            action="unchanged",
            last_revised_before=lr_before,
            last_revised_after=new_last_revised,
            covers_before=covers_before,
            covers_after=covers_after,
        )

    new_text = _join_frontmatter(new_frontmatter, body)
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return RestampResult(
        path=path,
        action="restamped",
        last_revised_before=lr_before,
        last_revised_after=new_last_revised,
        covers_before=covers_before,
        covers_after=covers_after,
    )


def _split_frontmatter(text: str) -> tuple[Optional[str], str]:
    """Return (frontmatter_body, rest_of_file) or (None, text).

    Frontmatter body is the YAML content *between* the ``---`` delimiters,
    without the delimiters themselves. ``rest_of_file`` is everything from
    after the closing delimiter onward (including its leading newline).
    """
    if not text.startswith(_FRONTMATTER_DELIM):
        return None, text
    end = text.find("\n---\n", len(_FRONTMATTER_DELIM))
    if end < 0:
        return None, text
    fm_body = text[len(_FRONTMATTER_DELIM):end]
    rest = text[end + len("\n---\n"):]
    return fm_body, rest


def _join_frontmatter(fm_body: str, rest: str) -> str:
    return _FRONTMATTER_DELIM + fm_body + "\n---\n" + rest


def _set_or_insert_field(
    frontmatter: str,
    *,
    field: str,
    new_value: str,
    insert_after: Optional[str] = None,
) -> tuple[str, Optional[str]]:
    """Return ``(updated_frontmatter, previous_value_or_None)``.

    If ``field:`` is already present, replace its value. Otherwise insert
    a new line ``<field>: <new_value>`` right after the ``insert_after``
    line, or appended to the end of the frontmatter if that's missing.
    """
    pattern = re.compile(rf"^{re.escape(field)}\s*:\s*(.*)$", re.MULTILINE)
    match = pattern.search(frontmatter)
    if match is not None:
        previous = match.group(1).strip()
        new_line = f"{field}: {new_value}"
        return pattern.sub(new_line, frontmatter, count=1), previous

    # Field is missing — insert it. Try after `insert_after:`; fall back to end.
    if insert_after:
        anchor = re.compile(rf"^{re.escape(insert_after)}\s*:.*$", re.MULTILINE)
        anchor_match = anchor.search(frontmatter)
        if anchor_match is not None:
            insertion_point = anchor_match.end()
            return (
                frontmatter[:insertion_point]
                + f"\n{field}: {new_value}"
                + frontmatter[insertion_point:],
                None,
            )

    # No anchor — append at the end of the frontmatter body.
    sep = "" if frontmatter.endswith("\n") else "\n"
    return frontmatter + sep + f"{field}: {new_value}", None


def _bump_covers_sessions(
    frontmatter: str,
    *,
    session: int,
) -> tuple[str, Optional[str], Optional[str]]:
    """Bump the upper bound of ``covers_sessions: "MIN-MAX"`` to ``session``.

    Returns ``(updated_frontmatter, before, after)``. If the field is
    not present, returns the input unchanged with ``None``s.
    """
    pattern = re.compile(
        r"^covers_sessions\s*:\s*['\"]?(\d+)\s*-\s*(\d+)['\"]?",
        re.MULTILINE,
    )
    match = pattern.search(frontmatter)
    if match is None:
        return frontmatter, None, None
    low, high = match.group(1), match.group(2)
    before = f"{low}-{high}"
    after = f"{low}-{session}"
    if before == after:
        return frontmatter, before, after
    replacement = f'covers_sessions: "{after}"'
    return pattern.sub(replacement, frontmatter, count=1), before, after


# ---------------------------------------------------------------------------
# Item 3 — calibration drift detection
# ---------------------------------------------------------------------------


@dataclass
class CalibrationEntry:
    """One subsection under the handoff's `## Calibration moments` heading."""
    heading: str  # The `### …` text, without the leading `###`
    body: str
    matched: bool = False
    matched_against: Optional[str] = None  # TRUST_CALIBRATION header it matched


def audit_calibration_promotion(
    project: Path,
    *,
    handoff_path: Path,
    handoff_date: str,
) -> list[CalibrationEntry]:
    """Parse handoff calibration entries and check they're in TRUST_CALIBRATION.

    Returns the parsed entries, each tagged with whether a same-date
    TRUST_CALIBRATION entry exists with overlapping headline words.
    Empty list if the handoff has no calibration section.
    """
    try:
        handoff_text = handoff_path.read_text(encoding="utf-8")
    except OSError:
        return []

    entries = _extract_calibration_entries(handoff_text)
    if not entries:
        return []

    trust_path = project / "docs" / "TRUST_CALIBRATION.md"
    try:
        trust_text = trust_path.read_text(encoding="utf-8")
    except OSError:
        return entries  # No TRUST_CALIBRATION — every entry stays unmatched.

    same_date_headers = [
        header for date, header in _iter_trust_calibration_headers(trust_text)
        if date == handoff_date
    ]
    for entry in entries:
        entry_tokens = _fuzzy_tokens(entry.heading)
        if not entry_tokens:
            continue
        for header in same_date_headers:
            header_tokens = _fuzzy_tokens(header)
            if not header_tokens:
                continue
            overlap = len(entry_tokens & header_tokens) / len(entry_tokens)
            if overlap >= 0.4:
                entry.matched = True
                entry.matched_against = header
                break
    return entries


def _extract_calibration_entries(handoff_text: str) -> list[CalibrationEntry]:
    """Return subsections under any matching calibration heading."""
    lines = handoff_text.splitlines()
    in_section = False
    current_heading: Optional[str] = None
    current_body: list[str] = []
    entries: list[CalibrationEntry] = []

    def _flush() -> None:
        nonlocal current_heading, current_body
        if current_heading is not None:
            entries.append(
                CalibrationEntry(
                    heading=current_heading,
                    body="\n".join(current_body).strip(),
                )
            )
        current_heading = None
        current_body = []

    for line in lines:
        if line.startswith("## "):
            _flush()
            in_section = any(p.match(line) for p in CALIBRATION_HEADING_PATTERNS)
            continue
        if not in_section:
            continue
        if line.startswith("### "):
            _flush()
            current_heading = line[len("### "):].strip()
            continue
        if current_heading is not None:
            current_body.append(line)

    _flush()
    return entries


def _iter_trust_calibration_headers(trust_text: str) -> Iterable[tuple[str, str]]:
    """Yield (date, header_text) tuples for each `## YYYY-MM-DD — …` line."""
    for line in trust_text.splitlines():
        match = _TRUST_CAL_HEADER_RE.match(line)
        if match is not None:
            yield match.group(1), match.group(2).strip()


def _fuzzy_tokens(text: str) -> set[str]:
    """Tokenize for fuzzy headline match. Lowercase + drop stopwords."""
    tokens = _FUZZY_TOKEN_RE.findall(text.lower())
    return {t for t in tokens if t not in _FUZZY_STOPWORDS and not t.isdigit()}


# ---------------------------------------------------------------------------
# Reporters
# ---------------------------------------------------------------------------


def _print_restamp_summary(
    results: list[RestampResult],
    project: Path,
    *,
    dry_run: bool,
) -> None:
    verb_prefix = "would " if dry_run else ""
    print("Anchor doc frontmatter:")
    if not results:
        print("  (no anchor docs found under docs/)")
        return
    for r in results:
        try:
            rel = r.path.relative_to(project)
        except ValueError:
            rel = r.path
        if r.action == "restamped":
            change = f"last_revised: {r.last_revised_before or '(missing)'} → {r.last_revised_after}"
            if r.covers_before and r.covers_after and r.covers_before != r.covers_after:
                change += f"; covers_sessions: {r.covers_before} → {r.covers_after}"
            print(f"  {verb_prefix}restamp   {rel} ({change})")
        elif r.action == "unchanged":
            print(f"  unchanged          {rel} (already at {r.last_revised_after})")
        else:
            print(f"  {r.action:<18} {rel}")
    if dry_run:
        print("  (dry run — no files written)")


def _print_calibration_summary(entries: list[CalibrationEntry]) -> None:
    print()
    print("Calibration promotion check (read-only):")
    if not entries:
        print("  (handoff has no `## Calibration moments` or `## AI Notes` section)")
        return
    for entry in entries:
        if entry.matched:
            print(f"  ✓ promoted   {entry.heading}")
            if entry.matched_against:
                print(f"               (matched TRUST_CALIBRATION: {entry.matched_against})")
        else:
            print(f"  ⚠ MISSING    {entry.heading}")
            print("               (appears in handoff; no same-date TRUST_CALIBRATION entry)")
    missing = sum(1 for e in entries if not e.matched)
    if missing:
        print(
            f"\n  {missing} calibration moment(s) missing from "
            "docs/TRUST_CALIBRATION.md. Promote them manually — the "
            "headline translation (event type + lesson) is operator "
            "judgment, not deterministic."
        )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _looks_like_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
