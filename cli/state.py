"""Shared runtime-state helpers for doctor, orient, and start-codex.

All helpers are deterministic, read-only, and dependency-free. They
centralize the small bits of "what is true right now?" logic that would
otherwise drift between commands.
"""

from __future__ import annotations

import re
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


START_DOC = "00-START-NEXT-SESSION.md"
HANDOFFS_DIR = Path("docs/handoffs")
INVENTORY_REL = Path("docs/CONTEXT_KIT_INVENTORY.md")

_VERSION_RE = re.compile(r"\b\d+\.\d+\.\d+(?:[a-zA-Z0-9.+-]*)?\b")
_SESSION_FILE_RE = re.compile(r"^SESSION_(\d+)_.+\.md$")
_SESSION_TOKEN_RE = re.compile(r"SESSION_(\d+)\b")
_INVENTORY_TEST_COUNT_RE = re.compile(r"\|\s*Tests collected\s*\|\s*(\d+)\s*\|")

# Frontmatter date fields, in priority order. The narrative anchor template
# uses `generated`; handoffs use `date`; some adopt-emitted docs use
# `last_revised`. We accept any of the three so doctor doesn't need to know
# which doc shape it's looking at.
_FRONTMATTER_DATE_FIELDS = ("last_revised", "date", "generated")
_ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class HandoffInfo:
    number: int
    path: Path

    @property
    def token(self) -> str:
        return f"SESSION_{self.number:03d}"

    @property
    def next_token(self) -> str:
        return f"SESSION_{self.number + 1:03d}"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def get_current_version(project: Path) -> str | None:
    """Return the project version from pyproject.toml, if present."""
    text = read_text(project / "pyproject.toml")
    if not text:
        return None
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def versions_in_text(text: str) -> list[str]:
    return _VERSION_RE.findall(text)


def highest_version_in_text(text: str) -> str | None:
    versions = versions_in_text(text)
    if not versions:
        return None
    return max(versions, key=_version_key)


def _version_key(value: str) -> tuple[int, int, int, str]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", value)
    if not match:
        return (0, 0, 0, value)
    major, minor, patch, suffix = match.groups()
    return (int(major), int(minor), int(patch), suffix)


def get_actual_test_count(project: Path) -> int | None:
    """Return unittest discovery's test count without running tests."""
    tests = project / "tests"
    if not tests.is_dir():
        return 0
    loader = unittest.TestLoader()
    inserted = False
    project_str = str(project)
    try:
        if project_str not in sys.path:
            sys.path.insert(0, project_str)
            inserted = True
        for path in tests.glob("test*.py"):
            sys.modules.pop(path.stem, None)
        suite = loader.discover(start_dir=str(tests), pattern="test*.py")
    except Exception:
        return None
    finally:
        if inserted:
            try:
                sys.path.remove(project_str)
            except ValueError:
                pass
    return suite.countTestCases()


def get_inventory_test_count(project: Path) -> int | None:
    text = read_text(project / INVENTORY_REL)
    if not text:
        return None
    match = _INVENTORY_TEST_COUNT_RE.search(text)
    return int(match.group(1)) if match else None


def get_inventory_status(project: Path) -> tuple[str, str]:
    """Return (status, detail): current / stale / missing / unknown."""
    try:
        from .inventory import check_inventory  # type: ignore
    except ImportError:
        return "unknown", "inventory checker unavailable"
    try:
        current, reason = check_inventory(project)
    except Exception as exc:
        return "unknown", f"inventory check failed: {exc}"
    return ("current" if current else "stale", reason)


def get_latest_handoff(project: Path) -> HandoffInfo | None:
    handoffs = project / HANDOFFS_DIR
    if not handoffs.is_dir():
        return None
    candidates: list[tuple[int, float, Path]] = []
    for path in handoffs.glob("SESSION_*.md"):
        if not path.is_file():
            continue
        match = _SESSION_FILE_RE.match(path.name)
        if match is None:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((int(match.group(1)), mtime, path))
    if not candidates:
        return None
    number, _, path = max(candidates)
    return HandoffInfo(number=number, path=path)


def get_handoff_numbers(project: Path) -> list[int]:
    handoffs = project / HANDOFFS_DIR
    if not handoffs.is_dir():
        return []
    numbers: list[int] = []
    for path in handoffs.glob("SESSION_*.md"):
        if not path.is_file():
            continue
        match = _SESSION_FILE_RE.match(path.name)
        if match is not None:
            numbers.append(int(match.group(1)))
    return sorted(set(numbers))


def missing_handoff_numbers(numbers: Iterable[int]) -> list[int]:
    values = sorted(set(numbers))
    if not values:
        return []
    expected = set(range(values[0], values[-1] + 1))
    return sorted(expected - set(values))


def get_start_session_number(project: Path) -> int | None:
    text = read_text(project / START_DOC)
    matches = _SESSION_TOKEN_RE.findall(text)
    if not matches:
        return None
    return max(int(m) for m in matches)


def get_next_task(project: Path) -> str:
    """Extract the start doc's next-task body. Empty string if absent."""
    text = read_text(project / START_DOC)
    if not text:
        return ""
    body = _first_section_body(
        text,
        (
            r"^##\s+Next Task\b",
            r"^##\s+Next session priorit",
            r"^##\s+Next priority\b",
            r"^##\s+Next step\b",
            r"^##\s+This session's priorities\b",
            r"^##\s+What's next\b",
            r"^##\s+Priorit",
        ),
    )
    return body.strip()


def first_task_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("```"):
            return stripped.lstrip("-").strip()
    return ""


def parse_frontmatter_date(text: str) -> str | None:
    """Return the first ISO date found in YAML frontmatter, or None.

    Looks for ``last_revised``, ``date``, or ``generated`` (in that order)
    inside the leading ``---`` ... ``---`` block. Returns the bare
    ``YYYY-MM-DD`` portion so callers can compare dates lexicographically
    without parsing time / timezone.
    """
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    frontmatter = text[3:end]
    for field in _FRONTMATTER_DATE_FIELDS:
        pattern = re.compile(rf"^{field}\s*:\s*(.+)$", re.MULTILINE)
        match = pattern.search(frontmatter)
        if match is None:
            continue
        value = match.group(1).strip().strip('"').strip("'")
        iso = _ISO_DATE_RE.match(value)
        if iso is not None:
            return iso.group(1)
    return None


def get_narrative_anchor_path(project: Path) -> Path | None:
    """Return the path to the project's narrative anchor doc, or None.

    Matches ``docs/*_WHAT_IT_IS.md``. Mirrors the discovery rule used by
    orient and the project-state doctor check, so we don't drift on which
    file counts as "the narrative anchor."
    """
    docs = project / "docs"
    if not docs.is_dir():
        return None
    for path in sorted(docs.glob("*_WHAT_IT_IS.md")):
        if path.is_file():
            return path
    return None


def get_narrative_anchor_date(project: Path) -> str | None:
    """Return the narrative anchor's frontmatter date, or None."""
    path = get_narrative_anchor_path(project)
    if path is None:
        return None
    return parse_frontmatter_date(read_text(path))


def get_handoff_date(handoff: HandoffInfo) -> str | None:
    """Return the frontmatter date of a handoff, or None."""
    return parse_frontmatter_date(read_text(handoff.path))


def _first_section_body(text: str, header_patterns: tuple[str, ...]) -> str:
    compiled = [re.compile(p, re.IGNORECASE) for p in header_patterns]
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if any(p.search(line) for p in compiled):
            body: list[str] = []
            for follow in lines[idx + 1:]:
                if follow.startswith("## "):
                    break
                body.append(follow)
            return "\n".join(body).strip()
    return ""
