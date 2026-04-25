"""context-kit `init` subcommand: scaffold a new project from the template.

Exposes :func:`run_init`, which takes an :class:`argparse.Namespace` produced
by ``context_kit.py``'s ``init`` subparser and writes the project skeleton.
The lower-level :func:`bootstrap` function can be called directly from tests
or other tooling without an argparse namespace.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Mapping

from .placeholders import apply_placeholders, derive_placeholders

REPO_ROOT = Path(__file__).resolve().parent.parent
STARTER_ROOT = REPO_ROOT / "starter"

# When we copy this repo's pattern content into the generated project's
# ``docs/docs-pattern/`` folder, exclude everything that's tooling rather
# than teaching material.
PATTERN_EXCLUDES = frozenset({
    "cli",
    "starter",
    "examples",
    "bin",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".venv",
    "context_kit.py",
    # Keep the legacy entry-point name excluded too, in case any downstream
    # fork still carries it — harmless if absent.
    "docs_pattern_bootstrap.py",
})

# Files from the context-kit source that every generated project needs at
# runtime so that ``python3 context_kit.py start`` and ``orient`` work
# standalone. These are copied byte-for-byte (no placeholder substitution).
RUNTIME_COPY = (
    ("context_kit.py", "context_kit.py"),
    ("cli/__init__.py", "cli/__init__.py"),
    ("cli/server.py", "cli/server.py"),
    ("cli/orient.py", "cli/orient.py"),
)

# The Claude Code skill ships into the generated project's local
# ``.claude/skills/`` so any agent run inside the project picks it up
# automatically. Source dir, destination dir (relative to project root).
SKILLS_COPY = (
    ("skills/context-kit", ".claude/skills/context-kit"),
)

# Suffixes treated as text (placeholder substitution applies). Everything else
# is copied byte-for-byte.
TEXT_SUFFIXES = frozenset({
    ".md", ".py", ".toml", ".json", ".yaml", ".yml",
    ".txt", ".ini", ".cfg", ".env", ".html",
})


def bootstrap(
    target: Path,
    placeholders: Mapping[str, str],
    with_scaffold: bool = False,
    force: bool = False,
) -> list[Path]:
    """Generate a new project skeleton at ``target``.

    Returns the list of paths that were written (or updated, with ``force``).
    Idempotent by default: existing files are preserved unless ``force=True``.
    """
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # 1. The meta-framework — copy this repo's pattern guide + reference
    #    templates into ``<target>/docs/docs-pattern/``.
    pattern_dst = target / "docs" / "docs-pattern"
    written += _copy_pattern(REPO_ROOT, pattern_dst, force=force)

    # 2. The project starter — the files the developer will edit on day one.
    written += _render_tree(STARTER_ROOT / "root", target, placeholders, force=force)
    written += _render_tree(STARTER_ROOT / "docs", target / "docs", placeholders, force=force)

    # 3. Optional framework scaffold — only when asked for.
    if with_scaffold:
        written += _render_tree(
            STARTER_ROOT / "scaffold", target / "scaffold", placeholders, force=force
        )

    # 4. Runtime files — so the generated project can run
    #    ``python3 context_kit.py start`` / ``orient`` without the source repo.
    written += _copy_runtime(REPO_ROOT, target, force=force)

    # 5. Claude Code skill — agent-facing entry point. Drops into
    #    ``<project>/.claude/skills/context-kit/`` so any agent run in
    #    the project picks it up automatically.
    written += _copy_skills(REPO_ROOT, target, force=force)

    return written


def _copy_pattern(src: Path, dst: Path, *, force: bool) -> list[Path]:
    """Copy this repo's pattern guide + reference templates into ``dst``."""
    if dst.exists() and not force:
        return []

    if dst.exists() and force:
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for item in sorted(src.iterdir()):
        if item.name in PATTERN_EXCLUDES or item.name.startswith("."):
            continue
        out = dst / item.name
        if item.is_dir():
            shutil.copytree(item, out, dirs_exist_ok=True)
            written += [p for p in sorted(out.rglob("*")) if p.is_file()]
        else:
            shutil.copy2(item, out)
            written.append(out)
    return written


def _render_tree(
    src: Path,
    dst: Path,
    placeholders: Mapping[str, str],
    *,
    force: bool,
) -> list[Path]:
    """Mirror ``src`` into ``dst``, rendering filenames and text contents."""
    if not src.exists():
        return []

    written: list[Path] = []
    for item in sorted(src.rglob("*")):
        rel = item.relative_to(src)
        rel_rendered = Path(*[apply_placeholders(part, placeholders) for part in rel.parts])
        out = dst / rel_rendered

        if item.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue

        if out.exists() and not force:
            continue

        out.parent.mkdir(parents=True, exist_ok=True)

        if item.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = item.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copy2(item, out)
                written.append(out)
                continue
            out.write_text(apply_placeholders(text, placeholders), encoding="utf-8")
        else:
            shutil.copy2(item, out)

        written.append(out)
    return written


def _copy_runtime(src_root: Path, dst_root: Path, *, force: bool) -> list[Path]:
    """Copy the files needed so the generated project can run `start`."""
    written: list[Path] = []
    for src_rel, dst_rel in RUNTIME_COPY:
        src = src_root / src_rel
        dst = dst_root / dst_rel
        if not src.exists():
            continue
        if dst.exists() and not force:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(dst)
    return written


def _copy_skills(src_root: Path, dst_root: Path, *, force: bool) -> list[Path]:
    """Copy Claude Code skill directories into the generated project."""
    written: list[Path] = []
    for src_rel, dst_rel in SKILLS_COPY:
        src = src_root / src_rel
        dst = dst_root / dst_rel
        if not src.is_dir():
            continue
        if dst.exists() and not force:
            continue
        if dst.exists() and force:
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        written += [p for p in sorted(dst.rglob("*")) if p.is_file()]
    return written


def run_init(args: argparse.Namespace) -> int:
    """Entry point for the ``init`` subcommand dispatched from context_kit.py."""
    try:
        placeholders = derive_placeholders(args.name)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    target = Path(args.target) if args.target else Path.cwd() / placeholders["APP_SLUG"]
    target = target.resolve()

    if not args.quiet:
        print(f"context-kit: scaffolding '{placeholders['APP_TITLE']}' at {target}")

    written = bootstrap(
        target=target,
        placeholders=placeholders,
        with_scaffold=args.with_scaffold,
        force=args.force,
    )

    if not args.quiet:
        for p in written:
            try:
                rel = p.relative_to(target)
            except ValueError:
                rel = p
            print(f"  + {rel}")
        print(f"\ncontext-kit: wrote {len(written)} files.")
        if written:
            print("\nNext:")
            print(f"  cd {target}")
            print(f"  python3 context_kit.py start    # onboarding server")
            print(f"  open 00-START-NEXT-SESSION.md   # or read it directly")
        else:
            print("\nNo files written (already scaffolded). Re-run with --force to overwrite.")

    return 0
