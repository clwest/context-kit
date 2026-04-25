"""context-kit `init` subcommand: scaffold a new project from packaged assets.

All starter, pattern, and skill content lives inside the ``cli`` package
under ``_starter/``, ``_pattern/``, and ``_skills/``. Reads happen via
``importlib.resources`` so the same code path works for editable installs
(``pip install -e .``) and for wheel installs from PyPI.

Public entry points:
- :func:`run_init` — argparse-driven entry point
- :func:`bootstrap` — lower-level, callable from tests/tools without argparse
"""

from __future__ import annotations

import argparse
import importlib.resources as resources
import shutil
import sys
from pathlib import Path
from typing import Mapping, Optional

from .placeholders import apply_placeholders, derive_placeholders

# Files from the cli package + top-level context_kit module that every
# generated project needs at runtime so that ``python3 context_kit.py
# {start, orient, hotpath, inventory}`` works standalone — no source
# repo and no pip install required inside the generated project.
#
# Source is "<top-level-module-name> | cli/<filename>" — destination is
# the path inside the generated project.
RUNTIME_COPY = (
    ("context_kit.py", "context_kit.py"),
    ("cli/__init__.py", "cli/__init__.py"),
    ("cli/server.py", "cli/server.py"),
    ("cli/orient.py", "cli/orient.py"),
    ("cli/hotpath.py", "cli/hotpath.py"),
    ("cli/inventory.py", "cli/inventory.py"),
    ("cli/seed.py", "cli/seed.py"),
    ("cli/doctor.py", "cli/doctor.py"),
    ("cli/recommend_stack.py", "cli/recommend_stack.py"),
)

# The bundled Claude skill lives at ``cli/_skills/context-kit/`` inside
# the package and gets copied into the generated project's local
# ``.claude/skills/`` so any agent run inside the project picks it up.
SKILLS_COPY = (
    ("context-kit", ".claude/skills/context-kit"),
)

# Suffixes treated as text (placeholder substitution applies). Everything
# else is copied byte-for-byte.
TEXT_SUFFIXES = frozenset({
    ".md", ".py", ".toml", ".json", ".yaml", ".yml",
    ".txt", ".ini", ".cfg", ".env", ".html",
})

# Names that should never be materialized into a generated project,
# even if they accidentally got included as package data (e.g. Python
# imported a template at some point and dropped a __pycache__).
_IGNORE_NAMES = frozenset({"__pycache__", ".DS_Store"})
_IGNORE_SUFFIXES = (".pyc", ".pyo")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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

    # 1. Pattern (8 guide docs + reference templates) → docs/docs-pattern/
    pattern_dst = target / "docs" / "docs-pattern"
    written += _materialize_pattern(pattern_dst, force=force)

    # 2. Starter — files the developer edits on day one.
    written += _materialize_tree(_pkg("_starter", "root"), target, placeholders, force=force)
    written += _materialize_tree(_pkg("_starter", "docs"), target / "docs", placeholders, force=force)

    # 3. Optional Python scaffold.
    if with_scaffold:
        written += _materialize_tree(
            _pkg("_starter", "scaffold"), target / "scaffold", placeholders, force=force
        )

    # 4. Runtime files — so the generated project can run start/orient/
    #    hotpath/inventory standalone.
    written += _copy_runtime(target, force=force)

    # 5. Bundled Claude Code skill.
    written += _copy_skills(target, force=force)

    return written


def run_init(args: argparse.Namespace) -> int:
    """Argparse entry point dispatched from ``context_kit.py``."""
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


# ---------------------------------------------------------------------------
# Resource helpers (single source of truth: importlib.resources)
# ---------------------------------------------------------------------------


def _pkg(*parts: str):
    """Return a ``Traversable`` to a path inside the ``cli`` package."""
    base = resources.files("cli")
    for p in parts:
        base = base / p
    return base


def _materialize_pattern(dst: Path, *, force: bool) -> list[Path]:
    """Copy the pattern (guide docs + templates) into ``dst``.

    Top-level no-substitution copy. Skips if ``dst`` exists unless ``force``.
    """
    if dst.exists() and not force:
        return []
    if dst.exists() and force:
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    src = _pkg("_pattern")
    written += _materialize_tree(src, dst, placeholders=None, force=True)
    return written


def _materialize_tree(
    src,  # importlib.resources Traversable
    dst: Path,
    placeholders: Optional[Mapping[str, str]],
    *,
    force: bool,
) -> list[Path]:
    """Recursively materialize a packaged Traversable tree to disk.

    When ``placeholders`` is provided, both filenames and the contents of
    text files are substituted. Binary files (or text files that fail to
    decode) are written byte-for-byte.
    """
    written: list[Path] = []
    if not src.is_dir():
        return written

    for item in sorted(src.iterdir(), key=lambda x: x.name):
        if item.name in _IGNORE_NAMES or item.name.endswith(_IGNORE_SUFFIXES):
            continue
        rendered_name = (
            apply_placeholders(item.name, placeholders) if placeholders else item.name
        )
        out = dst / rendered_name

        if item.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            written += _materialize_tree(item, out, placeholders, force=force)
            continue

        if out.exists() and not force:
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        data = item.read_bytes()

        if placeholders is not None and Path(item.name).suffix.lower() in TEXT_SUFFIXES:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                out.write_bytes(data)
                written.append(out)
                continue
            out.write_text(apply_placeholders(text, placeholders), encoding="utf-8")
        else:
            out.write_bytes(data)

        written.append(out)
    return written


def _copy_runtime(dst_root: Path, *, force: bool) -> list[Path]:
    """Copy RUNTIME_COPY entries from installed package locations."""
    written: list[Path] = []
    for src_rel, dst_rel in RUNTIME_COPY:
        dst = dst_root / dst_rel
        if dst.exists() and not force:
            continue
        data = _read_runtime_source(src_rel)
        if data is None:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        written.append(dst)
    return written


def _read_runtime_source(src_rel: str) -> Optional[bytes]:
    """Read a runtime-copy source file by its conceptual path.

    Maps logical paths like ``cli/server.py`` and ``context_kit.py`` to
    actual installed locations using ``importlib.resources`` for package
    members and ``__file__`` for the top-level module.
    """
    if src_rel.startswith("cli/"):
        rel = src_rel[len("cli/"):]
        try:
            return (resources.files("cli") / rel).read_bytes()
        except (FileNotFoundError, ModuleNotFoundError):
            return None
    if src_rel == "context_kit.py":
        try:
            import context_kit  # type: ignore
        except ImportError:
            return None
        path = getattr(context_kit, "__file__", None)
        if not path:
            return None
        try:
            return Path(path).read_bytes()
        except OSError:
            return None
    # Unknown source path — silently skip rather than crash bootstrap.
    return None


def _copy_skills(dst_root: Path, *, force: bool) -> list[Path]:
    """Copy bundled Claude Code skill directories into the generated project."""
    written: list[Path] = []
    for src_name, dst_rel in SKILLS_COPY:
        src = _pkg("_skills", src_name)
        if not src.is_dir():
            continue
        dst = dst_root / dst_rel
        if dst.exists() and not force:
            continue
        if dst.exists() and force:
            shutil.rmtree(dst)
        dst.mkdir(parents=True, exist_ok=True)
        written += _materialize_tree(src, dst, placeholders=None, force=True)
    return written
