"""File scanning for ``context-kit refactor track``.

Two responsibilities:

1. Parse a Python source file with ``ast`` and run a detector against
   it, capturing both the names found and any parse error.
2. Resolve the ``--siblings`` glob into a deterministic, sorted list
   of destination files to scan.

Both operations are pure: they take paths, return data. No mutation,
no network, no subprocess. Failures are captured in ``parse_error``
rather than raised so the renderer can surface them as warnings.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from cli._refactor.detectors import Detector


@dataclass
class FileScan:
    """One file's scan result, sufficient to render and compute totals."""

    path: Path
    exists: bool
    item_count: int = 0
    item_names: list[str] = field(default_factory=list)
    parse_error: str | None = None


def scan_file(path: Path, detector: Detector) -> FileScan:
    """Read ``path``, parse with ``ast``, and run the detector.

    Missing files produce ``FileScan(exists=False)`` rather than raising —
    a destination listed in a plan but not yet created is a normal
    in-progress state, not an error.
    """
    if not path.exists():
        return FileScan(path=path, exists=False)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return FileScan(
            path=path,
            exists=True,
            parse_error=f"read error: {exc.__class__.__name__}: {exc}",
        )
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return FileScan(
            path=path,
            exists=True,
            parse_error=f"syntax error: line {exc.lineno}: {exc.msg}",
        )
    names = detector(tree)
    return FileScan(
        path=path,
        exists=True,
        item_count=len(names),
        item_names=sorted(names),
    )


def resolve_siblings(source: Path, pattern: str | None) -> list[Path]:
    """Resolve ``--siblings`` glob to a sorted deduped list, sans source.

    If ``pattern`` is None, derive a default from ``source``: same
    parent directory, same basename prefix split on the first ``_``,
    same suffix. So ``core/tasks.py`` → ``core/tasks_*.py``.

    Glob is applied relative to ``source.parent`` when the pattern has
    no path separator, and relative to ``Path.cwd()`` otherwise — so a
    user-supplied ``--siblings 'core/tasks_*.py'`` works no matter
    where they invoke from, as long as they're at the project root.
    """
    if pattern is None:
        stem = source.stem
        prefix = stem.split("_", 1)[0]
        pattern = f"{prefix}_*{source.suffix}"

    if "/" in pattern or "\\" in pattern:
        anchor = Path.cwd()
        matches = sorted(anchor.glob(pattern))
    else:
        anchor = source.parent
        matches = sorted(anchor.glob(pattern))

    source_resolved = source.resolve()
    out: list[Path] = []
    seen: set[Path] = set()
    for m in matches:
        rp = m.resolve()
        if rp == source_resolved:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        out.append(m)
    return out
