"""Parse a Phase-0-style migration plan markdown file.

The reference shape is the auto-generated ``TASKS_MIGRATION_PLAN.md``
produced by example-monorepo's ``scripts/phase0_tasks_inventory.py``,
but the parser is intentionally lenient: any markdown file with a
``Total tasks:`` (or ``Total items:``) line and a markdown table whose
first column is a destination filename will work.

We extract three things:

1. ``total_expected`` — from a ``**Total tasks:** N`` (or ``Total items``)
   line. Optional; falls back to None.
2. ``per_destination`` — from a ``Counts by proposed destination`` table
   (or any table whose first row reads "Destination | Tasks" /
   "Destination | Items"). Optional.
3. ``item_assignments`` — currently unused at the call site, deferred.

If none of these are found, ``parse_plan`` returns ``PlanData(...)``
with empty fields rather than raising. The renderer treats an empty
plan as "no plan available, skip domain breakdown."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PlanData:
    path: Path | None = None
    total_expected: int | None = None
    per_destination: dict[str, int] = field(default_factory=dict)


_TOTAL_RE = re.compile(
    # Optional list bullet (- or *), then optional bold (** or __),
    # then "Total tasks" / "Total items", optional colon, optional
    # closing bold, then the number.
    r"""^
    (?:[-*]\s+)?           # markdown list bullet
    (?:\*\*|__)?\s*        # optional bold open
    Total\s+(?:tasks|items)
    \s*:?\s*
    (?:\*\*|__)?\s*        # optional bold close
    ([\d,]+)
    \s*$""",
    re.IGNORECASE | re.VERBOSE,
)

# A markdown table row: starts with `|`, has at least two cells.
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")

# Destination heading row matches "Destination | Tasks" or "... | Items"
# (case-insensitive, allowing markdown emphasis).
_HEADER_DEST_RE = re.compile(
    r"^\s*destination\s*$", re.IGNORECASE,
)
_HEADER_COUNT_RE = re.compile(
    r"^\s*(?:tasks|items|count)\s*$", re.IGNORECASE,
)


def _split_table_row(line: str) -> list[str] | None:
    """Return the cell texts of a markdown table row, or None."""
    m = _TABLE_ROW_RE.match(line)
    if not m:
        return None
    inner = m.group(1)
    cells = [c.strip() for c in inner.split("|")]
    return cells


def _is_separator_row(cells: list[str]) -> bool:
    """A row like ``| --- | ---: |`` between header and body."""
    if not cells:
        return False
    return all(re.match(r"^:?-+:?$", c) for c in cells if c)


def _strip_md_emphasis(s: str) -> str:
    """Remove markdown emphasis around a cell's content.

    Only strips:
      - backticks (any count)
      - paired ``**bold**`` and ``__bold__`` markers
      - paired ``*italic*`` and ``_italic_`` markers

    Crucially, lone underscores inside identifiers (``tasks_ops.py``)
    are preserved — only the outermost paired emphasis is removed.
    """
    s = s.strip()
    s = s.replace("`", "")
    # Strip paired bold/italic from the outside only.
    for marker in ("**", "__", "*", "_"):
        if len(s) >= 2 * len(marker) and s.startswith(marker) and s.endswith(marker):
            s = s[len(marker) : -len(marker)]
    return s.strip()


def parse_plan(path: Path) -> PlanData:
    """Parse a plan file. Missing or unreadable files return empty PlanData."""
    out = PlanData(path=path)
    if not path.exists() or not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out

    lines = text.splitlines()

    # 1. Total expected.
    for line in lines:
        m = _TOTAL_RE.match(line.strip())
        if m:
            try:
                out.total_expected = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
            break

    # 2. Counts by destination — find a table whose header is
    #    "Destination | Tasks" (or Items).
    in_table = False
    header_seen = False
    sep_seen = False
    for line in lines:
        cells = _split_table_row(line)
        if cells is None:
            in_table = False
            header_seen = False
            sep_seen = False
            continue

        if not in_table:
            # First row of a candidate table — must be the header.
            if len(cells) >= 2:
                first = _strip_md_emphasis(cells[0])
                second = _strip_md_emphasis(cells[1])
                if _HEADER_DEST_RE.match(first) and _HEADER_COUNT_RE.match(second):
                    in_table = True
                    header_seen = True
            continue

        if header_seen and not sep_seen:
            if _is_separator_row(cells):
                sep_seen = True
            else:
                # Not a real table — abort.
                in_table = False
                header_seen = False
            continue

        # Body row.
        if len(cells) >= 2:
            dest = _strip_md_emphasis(cells[0])
            count_str = _strip_md_emphasis(cells[1])
            try:
                count = int(count_str.replace(",", ""))
            except ValueError:
                continue
            # Only keep the FIRST destination table; once we've seen
            # entries, ignore later candidate tables.
            if dest and dest not in out.per_destination:
                out.per_destination[dest] = count

    return out


def autodiscover_plan(source: Path) -> Path | None:
    """Look for a likely plan file near ``source``.

    Returns the first match (deterministic order) of:

    1. ``<source.parent>/../docs/refactors/*MIGRATION_PLAN*.md``
    2. ``<cwd>/docs/refactors/*MIGRATION_PLAN*.md``
    3. ``<source.parent>/*MIGRATION_PLAN*.md``

    Otherwise None. Caller decides whether the absence is a warning.
    """
    candidates: list[Path] = []
    for base in (source.parent.parent, Path.cwd(), source.parent):
        refdir = base / "docs" / "refactors"
        if refdir.is_dir():
            candidates.extend(sorted(refdir.glob("*MIGRATION_PLAN*.md")))
            candidates.extend(sorted(refdir.glob("*migration_plan*.md")))
    # Also check directly under source.parent.
    candidates.extend(sorted(source.parent.glob("*MIGRATION_PLAN*.md")))

    seen: set[Path] = set()
    for c in candidates:
        rp = c.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        if c.is_file():
            return c
    return None
