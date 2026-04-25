"""context-kit `hotpath` subcommand: file-size dashboard.

Inspired by Damian Tedrow's "hot path" idea: when an AI session keeps
looping in the same code, the underlying cause is often that the
relevant files no longer fit comfortably in context. Pure file-size is
a surprisingly good proxy for "this will dominate your context window."

This command is read-only and advisory. It always exits 0; the value is
the printed warnings, which an agent can read and act on (narrow focus,
start a fresh session, or split a hot file into smaller modules).
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Iterable

# Directories that should never count as "your project's code." Pruned
# during the recursive walk and filtered out of git's tracked-file list
# defensively (in case something noisy got committed).
IGNORED_DIR_NAMES = frozenset({
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
})

# Directory-name suffix patterns to prune (e.g. ``mypackage.egg-info``).
IGNORED_DIR_SUFFIXES = (".egg-info",)


def run_hotpath(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else Path.cwd().resolve()

    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    files, source = _collect_files(project)
    sized = _with_sizes(files)
    sized.sort(key=lambda fs: fs[1], reverse=True)

    top = sized[: args.top_count]
    top_sum = sum(size for _, size in top)
    total_sum = sum(size for _, size in sized)

    single_threshold = args.single_threshold_kb * 1024
    top_threshold = args.top_threshold_kb * 1024

    over_single = [(p, s) for p, s in top if s > single_threshold]
    over_top = top_sum > top_threshold

    print(_format_report(
        project=project,
        source=source,
        sized=sized,
        top=top,
        top_sum=top_sum,
        total_sum=total_sum,
        single_threshold_kb=args.single_threshold_kb,
        top_threshold_kb=args.top_threshold_kb,
        top_count=args.top_count,
        over_single=over_single,
        over_top=over_top,
    ))
    return 0


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------


def _collect_files(project: Path) -> tuple[list[Path], str]:
    """Return (files, source_label). Prefers git-tracked when available."""
    if (project / ".git").exists():
        tracked = _git_ls_files(project)
        if tracked is not None:
            return [project / p for p in tracked if not _is_ignored(p)], "git ls-files"
    return _walk(project), "recursive walk"


def _git_ls_files(project: Path) -> list[str] | None:
    """Return git-tracked paths (relative), or None if git invocation fails."""
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "ls-files", "-z"],
            capture_output=True,
            check=False,
            text=False,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    raw = result.stdout.split(b"\x00")
    return [p.decode("utf-8", errors="replace") for p in raw if p]


def _walk(project: Path) -> list[Path]:
    out: list[Path] = []
    for root, dirs, files in os.walk(project):
        # Prune ignored dirs in-place so os.walk doesn't descend.
        dirs[:] = [d for d in dirs if not _dir_is_ignored(d)]
        for name in files:
            out.append(Path(root) / name)
    return out


def _dir_is_ignored(name: str) -> bool:
    if name in IGNORED_DIR_NAMES:
        return True
    return any(name.endswith(sfx) for sfx in IGNORED_DIR_SUFFIXES)


def _is_ignored(rel_path: str) -> bool:
    """Defensive filter for git-tracked paths that landed inside ignored dirs."""
    parts = Path(rel_path).parts
    return any(_dir_is_ignored(part) for part in parts[:-1])


def _with_sizes(files: Iterable[Path]) -> list[tuple[Path, int]]:
    out: list[tuple[Path, int]] = []
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        if not path.is_file():
            continue
        out.append((path, st.st_size))
    return out


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _format_report(
    *,
    project: Path,
    source: str,
    sized: list[tuple[Path, int]],
    top: list[tuple[Path, int]],
    top_sum: int,
    total_sum: int,
    single_threshold_kb: int,
    top_threshold_kb: int,
    top_count: int,
    over_single: list[tuple[Path, int]],
    over_top: bool,
) -> str:
    sections: list[str] = []

    sections.append(
        f"# context-kit hotpath\n"
        f"Project: {project.name}\n"
        f"Path:    {project}"
    )

    if not sized:
        sections.append("## STATUS\n  No files found to scan.")
        sections.append(_method_section(source, single_threshold_kb, top_threshold_kb, top_count))
        return "\n\n".join(sections) + "\n"

    sections.append(_top_section(project, top))

    if over_single or over_top:
        sections.append(_warnings_section(
            project=project,
            over_single=over_single,
            over_top=over_top,
            top_sum=top_sum,
            single_threshold_kb=single_threshold_kb,
            top_threshold_kb=top_threshold_kb,
            top_count=top_count,
        ))
    else:
        sections.append(
            "## STATUS\n"
            f"  OK — no file exceeds {single_threshold_kb} KB and the top "
            f"{top_count} sum to {_fmt_size(top_sum)} (under {top_threshold_kb} KB)."
        )

    sections.append(
        "## SUMMARY\n"
        f"  Files scanned: {len(sized)}\n"
        f"  Top {len(top)} sum:  {_fmt_size(top_sum)}\n"
        f"  Total size:    {_fmt_size(total_sum)}"
    )

    sections.append(_method_section(source, single_threshold_kb, top_threshold_kb, top_count))
    return "\n\n".join(sections) + "\n"


def _top_section(project: Path, top: list[tuple[Path, int]]) -> str:
    lines = [f"## TOP {len(top)} LARGEST FILES"]
    for path, size in top:
        try:
            rel = path.relative_to(project)
        except ValueError:
            rel = path
        lines.append(f"  {_fmt_size(size):>10}  {rel}")
    return "\n".join(lines)


def _warnings_section(
    *,
    project: Path,
    over_single: list[tuple[Path, int]],
    over_top: bool,
    top_sum: int,
    single_threshold_kb: int,
    top_threshold_kb: int,
    top_count: int,
) -> str:
    lines = ["## WARNINGS"]
    for path, size in over_single:
        try:
            rel = path.relative_to(project)
        except ValueError:
            rel = path
        lines.append(
            f"  ! {rel} is {_fmt_size(size)} "
            f"(over {single_threshold_kb} KB single-file threshold)"
        )
    if over_top:
        lines.append(
            f"  ! Top {top_count} sum is {_fmt_size(top_sum)} "
            f"(over {top_threshold_kb} KB cumulative threshold)"
        )
    lines.append("")
    lines.append(
        "  Suggested actions: narrow focus to one file at a time, start a fresh\n"
        "  AI session before tackling these, or split the largest files into\n"
        "  smaller modules so future sessions stay inside a comfortable context."
    )
    return "\n".join(lines)


def _method_section(source: str, single_kb: int, top_kb: int, top_count: int) -> str:
    ignored = ", ".join(sorted(IGNORED_DIR_NAMES)) + ", *.egg-info"
    return (
        "## METHOD\n"
        f"  Source:       {source}\n"
        f"  Thresholds:   single>{single_kb}KB, top{top_count}>{top_kb}KB\n"
        f"  Ignored dirs: {ignored}"
    )


def _fmt_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KB"
    mb = kb / 1024
    return f"{mb:.2f} MB"
