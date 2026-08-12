"""context-kit `doctor` subcommand: environment + setup diagnostics.

Read-only. Each check is a near-pure function (project Path in,
``CheckResult`` out) with mockable seams (``shutil.which``,
``subprocess.run``, optional kwargs for the Python check) so the test
suite can exercise edge cases without depending on the host machine.

Status taxonomy:

- ``ok``        — present and healthy
- ``warning``   — works but suboptimal / risky
- ``blocking``  — actively prevents the user's work; doctor exits 1
- ``skipped``   — this check doesn't apply to this project / platform

Warnings never affect the exit code. Only blocking does.

Provenance: the specific checks here came directly from real dogfood
friction (an Expo / React Native app). See
``docs/handoffs/SESSION_006_DOCTOR.md`` for the receipts. The dependency
direction is **doctor → inventory**; never invert it.
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from . import state

SCHEMA_VERSION = 1

# Updated periodically. Reflects "no surprises with mainstream tooling
# (Expo, Metro, Vite, etc.) at the time this constant was last bumped."
# Last bumped: 2026-04-25.
KNOWN_STABLE_NODE_MAJORS = (18, 19, 20, 21, 22)
NODE_MIN_MAJOR = KNOWN_STABLE_NODE_MAJORS[0]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    id: str
    label: str
    status: str  # "ok" | "warning" | "blocking" | "skipped"
    detail: str
    fix: Union[None, str, list[str]] = None

    def __post_init__(self) -> None:
        # Normalize fix to a list (or None) for JSON consistency.
        if isinstance(self.fix, str):
            self.fix = [self.fix]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_doctor(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve() if args.project else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    results = run_all_checks(project)
    if args.json:
        _emit_json(results, project)
    else:
        _emit_human(results, project)
    return _exit_code(results)


def run_all_checks(project: Path) -> list[CheckResult]:
    return [
        check_python_version(),
        check_git(project),
        check_project_state(project),
        check_node(project),
        check_expo(project),
        check_file_watcher(project),
        check_inventory(project),
        check_version_drift(project),
        check_test_count_drift(project),
        check_narrative_anchor_freshness(project),
        check_pipeline_doc(project),
        check_behavior_layer_doc(project),
        check_translation_layer_doc(project),
        check_next_task_consistency(project),
        check_handoff_numbering(project),
        check_start_handoff_conflict(project),
        check_adopt_placeholders(project),
        check_stale_generic_actions(project),
    ]


def _exit_code(results: list[CheckResult]) -> int:
    return 1 if any(r.status == "blocking" for r in results) else 0


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_python_version(
    *,
    version_info: Optional[tuple] = None,
    path_python: Optional[str] = None,
    path_python_version: Optional[str] = None,
) -> CheckResult:
    """All optional kwargs are testing seams; production callers pass none."""
    if version_info is None:
        version_info = tuple(sys.version_info)
    major, minor, micro = version_info[0], version_info[1], version_info[2]
    running = f"{major}.{minor}.{micro}"

    if (major, minor) < (3, 9):
        return CheckResult(
            id="python_version",
            label="Python version",
            status="blocking",
            detail=f"Python {running} is below the required >= 3.9",
            fix="Install Python 3.9 or later (pyenv, asdf, brew, etc.)",
        )

    if path_python is None:
        path_python = shutil.which("python3")
    if path_python is None:
        return CheckResult(
            id="python_version",
            label="Python version",
            status="ok",
            detail=f"Python {running} (>= 3.9 required); python3 not on PATH",
        )

    if path_python_version is None:
        try:
            result = subprocess.run(
                [path_python, "--version"],
                capture_output=True, check=False, text=True, timeout=5,
            )
            path_python_version = (
                (result.stdout + result.stderr).strip().replace("Python ", "")
            )
        except (OSError, subprocess.TimeoutExpired):
            path_python_version = running

    if path_python_version != running:
        return CheckResult(
            id="python_version",
            label="Python version",
            status="warning",
            detail=(
                f"Running Python {running}, but `python3` on PATH resolves to "
                f"{path_python_version} ({path_python}). Normal for pyenv / asdf "
                "/ conda — informational only."
            ),
        )
    return CheckResult(
        id="python_version",
        label="Python version",
        status="ok",
        detail=f"Python {running} (>= 3.9 required)",
    )


def check_git(project: Path) -> CheckResult:
    git_path = shutil.which("git")
    if git_path is None:
        return CheckResult(
            id="git",
            label="git availability",
            status="warning",
            detail="git not found on PATH",
            fix="Install git (https://git-scm.com/downloads)",
        )
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--git-dir"],
            capture_output=True, check=False, text=True, timeout=5,
        )
        if result.returncode == 0:
            return CheckResult(
                id="git",
                label="git availability",
                status="ok",
                detail=f"git found at {git_path}, project is a repo",
            )
    except (OSError, subprocess.TimeoutExpired):
        pass
    return CheckResult(
        id="git",
        label="git availability",
        status="warning",
        detail=f"git found at {git_path}, but {project} is not a git repo",
        fix=f"git -C {project} init",
    )


def check_project_state(project: Path) -> CheckResult:
    docs = project / "docs"
    items = [
        ("CLAUDE.md", (project / "CLAUDE.md").is_file()),
        ("00-START-NEXT-SESSION.md", (project / "00-START-NEXT-SESSION.md").is_file()),
        ("docs/*_WHAT_IT_IS.md", _has_glob_match(docs, "*_WHAT_IT_IS.md")),
        ("docs/*_INVENTORY.md", _has_glob_match(docs, "*_INVENTORY.md")),
        ("docs/handoffs/", (project / "docs" / "handoffs").is_dir()),
        (
            ".claude/skills/context-kit/SKILL.md",
            (project / ".claude" / "skills" / "context-kit" / "SKILL.md").is_file(),
        ),
    ]
    present_count = sum(1 for _, exists in items if exists)
    missing = [name for name, exists in items if not exists]
    total = len(items)

    if present_count == 0:
        return CheckResult(
            id="project_state",
            label="context-kit project structure",
            status="skipped",
            detail=f"{project} is not a context-kit project",
            fix='context-kit init "<App Name>"  # to start a new project',
        )
    if not missing:
        return CheckResult(
            id="project_state",
            label="context-kit project structure",
            status="ok",
            detail=f"context-kit project structure complete ({present_count}/{total})",
        )
    return CheckResult(
        id="project_state",
        label="context-kit project structure",
        status="warning",
        detail=(
            f"{present_count}/{total} expected items present; "
            f"missing: {', '.join(missing)}"
        ),
        fix="context-kit init  # or context-kit seed idea.md",
    )


def _has_glob_match(dir_: Path, pattern: str) -> bool:
    if not dir_.is_dir():
        return False
    return any(p.is_file() for p in dir_.glob(pattern))


def check_node(project: Path) -> CheckResult:
    package_json = project / "package.json"
    if not package_json.is_file():
        return CheckResult(
            id="node_version",
            label="Node.js version",
            status="skipped",
            detail="No package.json in project root",
        )

    if shutil.which("node") is None:
        return CheckResult(
            id="node_version",
            label="Node.js version",
            status="blocking",
            detail="package.json present but `node` not on PATH",
            fix=[
                "Install Node.js (https://nodejs.org/)",
                f"Recommended: a current LTS (Node {KNOWN_STABLE_NODE_MAJORS[-1]} as of "
                "this build).",
            ],
        )

    version_str = _detect_node_version()
    if version_str is None:
        return CheckResult(
            id="node_version",
            label="Node.js version",
            status="warning",
            detail="Could not parse `node --version` output",
        )

    try:
        major = int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return CheckResult(
            id="node_version",
            label="Node.js version",
            status="warning",
            detail=f"Could not parse Node major from version string {version_str!r}",
        )

    if major < NODE_MIN_MAJOR:
        return CheckResult(
            id="node_version",
            label="Node.js version",
            status="warning",
            detail=(
                f"Node v{version_str} is older than {NODE_MIN_MAJOR}; many modern "
                f"packages require {NODE_MIN_MAJOR}+"
            ),
            fix=f"Upgrade Node.js to a current LTS (Node {KNOWN_STABLE_NODE_MAJORS[-1]} recommended)",
        )
    if major not in KNOWN_STABLE_NODE_MAJORS:
        return CheckResult(
            id="node_version",
            label="Node.js version",
            status="warning",
            detail=(
                f"Node v{version_str} is unusually new (known-stable majors: "
                f"{KNOWN_STABLE_NODE_MAJORS[0]}-{KNOWN_STABLE_NODE_MAJORS[-1]})"
            ),
            fix=(
                "Some tooling (Expo / Metro especially) may not have caught up. "
                f"Consider Node {KNOWN_STABLE_NODE_MAJORS[-1]} (LTS) for app work."
            ),
        )
    return CheckResult(
        id="node_version",
        label="Node.js version",
        status="ok",
        detail=(
            f"Node v{version_str} (within known-stable majors "
            f"{KNOWN_STABLE_NODE_MAJORS[0]}-{KNOWN_STABLE_NODE_MAJORS[-1]})"
        ),
    )


def _detect_node_version() -> Optional[str]:
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True, check=False, text=True, timeout=5,
        )
        return result.stdout.strip().lstrip("v") or None
    except (OSError, subprocess.TimeoutExpired):
        return None


def check_expo(project: Path) -> CheckResult:
    package_json = project / "package.json"
    if not package_json.is_file():
        return CheckResult(
            id="expo",
            label="Expo SDK",
            status="skipped",
            detail="No package.json — not a JavaScript project",
        )
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CheckResult(
            id="expo",
            label="Expo SDK",
            status="skipped",
            detail="package.json present but unparseable",
        )

    deps = (data.get("dependencies") or {}) | (data.get("devDependencies") or {})
    expo_dep = deps.get("expo")
    if not expo_dep:
        return CheckResult(
            id="expo",
            label="Expo SDK",
            status="skipped",
            detail="No `expo` dependency in package.json",
        )

    installed = _detect_installed_expo_version(project)
    version_label = installed or expo_dep

    detail_parts = [f"Expo SDK {version_label} detected"]
    fix_parts = [
        "Latest Expo Go in the App Store may require a newer SDK.",
        "  npx expo-doctor                  # diagnose Expo project health",
        "  npx expo install expo@latest     # bump to latest, follow prompts",
        "Note: legacy global `expo-cli` is deprecated; use `npx expo` for all CLI commands.",
    ]

    config_paths = [project / "app.json", project / "app.config.js", project / "app.config.ts"]
    if not any(p.is_file() for p in config_paths):
        detail_parts.append(
            "no app.json / app.config.js / app.config.ts at project root — Expo config appears missing"
        )
        fix_parts.insert(
            0,
            "Create app.json (or app.config.js/.ts) for your Expo project.",
        )

    if shutil.which("expo") is not None:
        detail_parts.append(
            "legacy global `expo` (expo-cli) detected on PATH; deprecated"
        )
        fix_parts.append("npm uninstall -g expo-cli  # clean up legacy install")

    return CheckResult(
        id="expo",
        label="Expo SDK",
        status="warning",
        detail=" | ".join(detail_parts),
        fix=fix_parts,
    )


def _detect_installed_expo_version(project: Path) -> Optional[str]:
    expo_pkg = project / "node_modules" / "expo" / "package.json"
    if not expo_pkg.is_file():
        return None
    try:
        data = json.loads(expo_pkg.read_text(encoding="utf-8"))
        return data.get("version")
    except (OSError, json.JSONDecodeError):
        return None


def _is_expo_project(project: Path) -> bool:
    package_json = project / "package.json"
    if not package_json.is_file():
        return False
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    deps = (data.get("dependencies") or {}) | (data.get("devDependencies") or {})
    return "expo" in deps


def check_file_watcher(project: Path) -> CheckResult:
    if platform.system() == "Windows":
        return CheckResult(
            id="file_watcher",
            label="File watcher / open-file limit",
            status="skipped",
            detail="Windows file-watcher checks not implemented in MVP",
        )

    package_json = project / "package.json"
    if not package_json.is_file():
        return CheckResult(
            id="file_watcher",
            label="File watcher / open-file limit",
            status="skipped",
            detail="No package.json — file-watcher pressure unlikely",
        )

    has_expo = _is_expo_project(project)
    soft_limit = _read_ulimit_n()
    has_watchman = shutil.which("watchman") is not None

    if soft_limit is None:
        return CheckResult(
            id="file_watcher",
            label="File watcher / open-file limit",
            status="warning",
            detail="Could not read `ulimit -n` for current shell",
        )

    # Dogfood-tuned thresholds, in priority order:
    #   Expo + < 4096 + no watchman → blocking (EMFILE imminent under Metro)
    #   < 1024                       → warning (low for any file-watching workload)
    #   Expo + no watchman           → warning (suggest watchman)
    #   else                         → ok
    if has_expo and soft_limit < 4096 and not has_watchman:
        return CheckResult(
            id="file_watcher",
            label="File watcher / open-file limit",
            status="blocking",
            detail=f"Expo project with ulimit -n = {soft_limit}; EMFILE imminent under Metro",
            fix=[
                "ulimit -n 65536",
                "brew install watchman",
                "Persist in your shell config (~/.zshrc / ~/.bashrc / etc.)",
            ],
        )
    if soft_limit < 1024:
        return CheckResult(
            id="file_watcher",
            label="File watcher / open-file limit",
            status="warning",
            detail=f"ulimit -n = {soft_limit} is low for file-watcher workloads",
            fix=["ulimit -n 65536", "brew install watchman  # macOS"],
        )
    if has_expo and not has_watchman:
        return CheckResult(
            id="file_watcher",
            label="File watcher / open-file limit",
            status="warning",
            detail=f"Expo project; watchman not installed (ulimit -n = {soft_limit})",
            fix="brew install watchman",
        )
    watchman_state = "installed" if has_watchman else "not required for this project"
    return CheckResult(
        id="file_watcher",
        label="File watcher / open-file limit",
        status="ok",
        detail=f"ulimit -n = {soft_limit}; watchman {watchman_state}",
    )


def _read_ulimit_n() -> Optional[int]:
    """`ulimit` is a shell builtin, not a binary — invoke via sh."""
    try:
        result = subprocess.run(
            ["sh", "-c", "ulimit -n"],
            capture_output=True, check=False, text=True, timeout=5,
        )
        return int(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def check_inventory(project: Path) -> CheckResult:
    """Direct import. doctor depends on inventory; never the reverse."""
    try:
        from .inventory import (  # type: ignore
            DEFAULT_INVENTORY_REL,
            check_inventory as inv_check,
        )
    except ImportError:
        return CheckResult(
            id="inventory_freshness",
            label="Inventory freshness",
            status="skipped",
            detail="cli.inventory not importable",
        )

    inventory_path = project / DEFAULT_INVENTORY_REL
    if not inventory_path.is_file():
        # If this looks like an init'd context-kit project, the user should
        # have run `inventory --write` to create the managed-block file.
        # Otherwise it's truly not a context-kit project — skip.
        looks_init = (project / "00-START-NEXT-SESSION.md").is_file()
        if looks_init:
            return CheckResult(
                id="inventory_freshness",
                label="Inventory freshness",
                status="warning",
                detail=(
                    f"No managed inventory file at {DEFAULT_INVENTORY_REL.as_posix()} "
                    "(generated lazily on first `inventory --write`)"
                ),
                fix="context-kit inventory --write",
            )
        return CheckResult(
            id="inventory_freshness",
            label="Inventory freshness",
            status="skipped",
            detail="Not a context-kit project (no inventory file, no start-here)",
        )

    is_current, reason = inv_check(project)
    if is_current:
        return CheckResult(
            id="inventory_freshness",
            label="Inventory freshness",
            status="ok",
            detail="inventory --check passes",
        )
    return CheckResult(
        id="inventory_freshness",
        label="Inventory freshness",
        status="warning",
        detail=reason,
        fix="context-kit inventory --write",
    )


# ---------------------------------------------------------------------------
# Truth / state drift checks
# ---------------------------------------------------------------------------


def check_version_drift(project: Path) -> CheckResult:
    """Warn when docs name a different latest package version than pyproject."""
    current = state.get_current_version(project)
    if current is None:
        return CheckResult(
            id="version_drift",
            label="Version drift",
            status="skipped",
            detail="No pyproject.toml version found",
        )

    start_version = state.highest_version_in_text(
        state.read_text(project / state.START_DOC)
    )
    latest = state.get_latest_handoff(project)
    handoff_version = (
        state.highest_version_in_text(state.read_text(latest.path))
        if latest is not None else None
    )

    mismatches: list[str] = []
    if start_version is not None and start_version != current:
        mismatches.append(f"start-here references {start_version}")
    if handoff_version is not None and handoff_version != current:
        mismatches.append(f"latest handoff references {handoff_version}")

    if mismatches:
        return CheckResult(
            id="version_drift",
            label="Version drift",
            status="warning",
            detail=f"pyproject.toml is {current}; " + "; ".join(mismatches),
            fix="Update start-here / latest handoff to match pyproject.toml, or update pyproject.toml if the docs are ahead.",
        )

    if start_version is None and handoff_version is None:
        return CheckResult(
            id="version_drift",
            label="Version drift",
            status="skipped",
            detail=f"pyproject.toml is {current}; no version references found in start-here or latest handoff",
        )

    return CheckResult(
        id="version_drift",
        label="Version drift",
        status="ok",
        detail=f"pyproject.toml version {current} matches documented current version",
    )


def check_test_count_drift(project: Path) -> CheckResult:
    """Warn when unittest discovery count and inventory count diverge."""
    actual = state.get_actual_test_count(project)
    inventory_count = state.get_inventory_test_count(project)

    if actual is None:
        return CheckResult(
            id="test_count_drift",
            label="Test count drift",
            status="warning",
            detail="Could not count tests via unittest discovery",
            fix="Run `python3 -m unittest discover -s tests -t .` to inspect the import error.",
        )
    if inventory_count is None:
        return CheckResult(
            id="test_count_drift",
            label="Test count drift",
            status="skipped",
            detail="Inventory test count not found",
        )
    if actual != inventory_count:
        return CheckResult(
            id="test_count_drift",
            label="Test count drift",
            status="warning",
            detail=f"unittest discovery counts {actual}; inventory says {inventory_count}",
            fix="Regenerate inventory after confirming the test suite shape.",
        )
    return CheckResult(
        id="test_count_drift",
        label="Test count drift",
        status="ok",
        detail=f"unittest discovery and inventory both count {actual} tests",
    )


def check_narrative_anchor_freshness(project: Path) -> CheckResult:
    """Warn when the narrative anchor's frontmatter date is older than the
    latest handoff's frontmatter date.

    The narrative anchor (``docs/*_WHAT_IT_IS.md``) is the conceptual
    source of truth. Every handoff that lands real work has the chance to
    invalidate something it says. When handoffs keep moving forward and
    the anchor's ``generated:`` / ``last_revised:`` date stops moving,
    that's the early signal that narrative is decaying — agents reading
    orient form a stale picture of the project's shape.

    Comparison is on the bare ``YYYY-MM-DD`` portion, lexicographic.
    Equal dates pass. Anchor newer than handoff passes. Anchor older
    than handoff warns. Missing / unparseable dates skip.
    """
    anchor_path = state.get_narrative_anchor_path(project)
    if anchor_path is None:
        return CheckResult(
            id="narrative_anchor_freshness",
            label="Narrative anchor freshness",
            status="skipped",
            detail="No narrative anchor (docs/*_WHAT_IT_IS.md) found",
        )

    anchor_date = state.get_narrative_anchor_date(project)
    if anchor_date is None:
        return CheckResult(
            id="narrative_anchor_freshness",
            label="Narrative anchor freshness",
            status="skipped",
            detail=(
                f"{anchor_path.relative_to(project)} has no parseable "
                "frontmatter date (last_revised / date / generated)"
            ),
        )

    latest = state.get_latest_handoff(project)
    if latest is None:
        return CheckResult(
            id="narrative_anchor_freshness",
            label="Narrative anchor freshness",
            status="skipped",
            detail="No handoffs on disk to compare against",
        )

    handoff_date = state.get_handoff_date(latest)
    if handoff_date is None:
        return CheckResult(
            id="narrative_anchor_freshness",
            label="Narrative anchor freshness",
            status="skipped",
            detail=(
                f"{latest.path.relative_to(project)} has no parseable "
                "frontmatter date"
            ),
        )

    if anchor_date >= handoff_date:
        return CheckResult(
            id="narrative_anchor_freshness",
            label="Narrative anchor freshness",
            status="ok",
            detail=(
                f"narrative anchor dated {anchor_date}; "
                f"latest handoff ({latest.token}) dated {handoff_date}"
            ),
        )

    return CheckResult(
        id="narrative_anchor_freshness",
        label="Narrative anchor freshness",
        status="warning",
        detail=(
            f"narrative anchor ({anchor_path.relative_to(project)}) "
            f"dated {anchor_date} is older than latest handoff "
            f"({latest.token}) dated {handoff_date}. Sessions have "
            "moved on; the anchor's frontmatter hasn't."
        ),
        fix=[
            "Review the narrative anchor against the latest handoff.",
            "Update the body where it's drifted, then bump the "
            "frontmatter date.",
            "Or rubber-stamp the date if no content change is needed.",
        ],
    )


# ---------------------------------------------------------------------------
# Pipeline doc check (LLM/agent/task projects)
# ---------------------------------------------------------------------------

# File-name and content signals that suggest the project has LLM, agent,
# task-runner, or queue-driven flows worth mapping in PIPELINE.md.
_PIPELINE_INDICATOR_FILENAMES = (
    "agent", "agents",
    "pipeline", "pipelines",
    "chain", "chains",
    "llm", "openai", "anthropic",
    "tasks",
    "celery", "rq_worker", "sidekiq",
)

# Dependency tokens that imply LLM / agent / queue infrastructure.
# Matched as case-insensitive substrings against pyproject.toml,
# requirements*.txt, package.json, Pipfile, poetry.lock — kept tight to
# avoid false positives.
_PIPELINE_INDICATOR_DEPS = (
    "openai", "anthropic", "langchain", "llama-index", "llama_index",
    "haystack", "litellm", "instructor",
    "celery", "dramatiq", "rq ", "huey", "sidekiq",
    "@anthropic-ai/sdk", "@langchain/",
)


def _project_has_pipeline_indicators(project: Path) -> bool:
    """Heuristic: does this project look like it runs an LLM / agent /
    task pipeline? Used to decide whether a missing PIPELINE.md is a
    warning or a non-event.

    Two signals — either is sufficient:
    1. A filename anywhere under the project root contains an LLM /
       agent / task token (excluding common throwaway dirs).
    2. A dependency manifest mentions an LLM / agent / queue library.

    Skips ``.git/``, ``node_modules/``, ``__pycache__/``, ``.venv/``
    and the project's own ``cli/`` and ``docs/`` to avoid recursing
    into context-kit's own scaffold.
    """
    if _scan_dependency_manifests(project):
        return True
    return _scan_filenames_for_pipeline_tokens(project)


def _scan_dependency_manifests(project: Path) -> bool:
    manifest_names = (
        "pyproject.toml", "requirements.txt", "requirements-dev.txt",
        "Pipfile", "poetry.lock", "package.json",
    )
    for name in manifest_names:
        path = project / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        for token in _PIPELINE_INDICATOR_DEPS:
            if token.lower() in text:
                return True
    return False


def _scan_filenames_for_pipeline_tokens(project: Path) -> bool:
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        "docs",  # PIPELINE.md itself lives here; don't trigger off it
    }
    if not project.is_dir():
        return False
    stack = [project]
    visited = 0
    while stack and visited < 2000:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            visited += 1
            if visited >= 2000:
                break
            if child.is_dir():
                if child.name in skip_dirs or child.name.startswith("."):
                    continue
                stack.append(child)
                continue
            if not child.is_file():
                continue
            stem = child.stem.lower()
            if not stem:
                continue
            for token in _PIPELINE_INDICATOR_FILENAMES:
                if token in stem:
                    return True
    return False


def _has_pipeline_doc(project: Path) -> bool:
    """Mirror of ``cli.orient._find_pipeline_doc``'s discovery rules.

    Kept inline so doctor doesn't import orient (avoids circular
    import risk if either file grows).
    """
    docs = project / "docs"
    if docs.is_dir():
        for path in sorted(docs.glob("*_PIPELINE.md")):
            if path.is_file():
                return True
        if (docs / "PIPELINE.md").is_file():
            return True
    return (project / "PIPELINE.md").is_file()


def check_pipeline_doc(project: Path) -> CheckResult:
    """Soft warning when a project has LLM / agent / task indicators
    but no PIPELINE.md.

    Status taxonomy:
    - ok       — PIPELINE.md present
    - skipped  — no LLM / agent / task indicators detected
    - warning  — indicators present, doc missing

    Never blocking. Older projects without LLM flows pass silently
    via skipped status.
    """
    has_doc = _has_pipeline_doc(project)
    if has_doc:
        return CheckResult(
            id="pipeline_doc",
            label="Pipeline / runtime flow map",
            status="ok",
            detail="PIPELINE.md present",
        )

    if not _project_has_pipeline_indicators(project):
        return CheckResult(
            id="pipeline_doc",
            label="Pipeline / runtime flow map",
            status="skipped",
            detail="No LLM / agent / task indicators detected; PIPELINE.md not required",
        )

    return CheckResult(
        id="pipeline_doc",
        label="Pipeline / runtime flow map",
        status="warning",
        detail=(
            "PIPELINE.md missing. Projects with LLM, agent, queue, or "
            "automation flows should document request paths and guard "
            "coverage to prevent bypass drift."
        ),
        fix=[
            "Create docs/<APP>_PIPELINE.md (template ships with `context-kit init`)",
            "Document every entry point, guard, retrieval path, and post-processing step",
        ],
    )


# ---------------------------------------------------------------------------
# Behavior-layer doc check (chat / voice / persona / UI surfaces)
# ---------------------------------------------------------------------------

# Behavior surfaces are a superset of pipeline surfaces: anything LLM /
# agent / task-related, plus chat / voice / persona / dialog / prompt
# surfaces, plus interactive-UI deps that imply user-facing language.
_BEHAVIOR_INDICATOR_FILENAMES = _PIPELINE_INDICATOR_FILENAMES + (
    "chat", "conversation", "conversations",
    "dialog", "dialogue",
    "persona", "personas",
    "voice",
    "prompt", "prompts",
    "completion", "completions",
)

# UI dep tokens are intentionally additive — the warning fires only
# when an LLM/agent indicator AND a UI surface coexist, OR when a
# chat/voice/persona filename is present. A plain CRUD UI without
# any AI doesn't trigger this warning (handled in
# ``_project_has_behavior_indicators``).
_UI_INDICATOR_DEPS = (
    "react", "react-dom", "react-native",
    "vue",
    "svelte",
    "next",
    "expo", "@expo/",
    "solid-js",
    "preact",
)


def _project_has_behavior_indicators(project: Path) -> bool:
    """Heuristic: does this project have LLM / agent / chat / voice /
    persona / interactive-UI surfaces where a behavior-layer contract
    is meaningful?

    Trigger logic — any of these is sufficient:
    1. The project has pipeline indicators (LLM/agent/task deps or
       filename tokens). Pipeline projects almost always benefit from
       a behavior layer too.
    2. A chat / conversation / dialog / persona / voice / prompt
       filename appears anywhere outside skip dirs.
    3. A UI dep coexists with an LLM dep in the same dependency
       manifest. (UI alone is not enough — most plain CRUD UIs don't
       need a behavior layer; pairing with LLM signals intent to
       generate user-facing language.)
    """
    if _project_has_pipeline_indicators(project):
        return True
    if _scan_filenames_for_behavior_tokens(project):
        return True
    if _ui_paired_with_llm(project):
        return True
    return False


def _scan_filenames_for_behavior_tokens(project: Path) -> bool:
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        "docs",  # BEHAVIOR_LAYER.md itself lives here
    }
    if not project.is_dir():
        return False
    stack = [project]
    visited = 0
    while stack and visited < 2000:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            visited += 1
            if visited >= 2000:
                break
            if child.is_dir():
                if child.name in skip_dirs or child.name.startswith("."):
                    continue
                stack.append(child)
                continue
            if not child.is_file():
                continue
            stem = child.stem.lower()
            if not stem:
                continue
            for token in _BEHAVIOR_INDICATOR_FILENAMES:
                if token in stem:
                    return True
    return False


def _ui_paired_with_llm(project: Path) -> bool:
    """Return True only if a single manifest mentions both a UI dep
    and an LLM dep — the case where a behavior layer is meaningful
    even without explicit chat/persona filenames."""
    manifest_names = (
        "package.json", "pyproject.toml", "requirements.txt",
        "requirements-dev.txt", "Pipfile", "poetry.lock",
    )
    for name in manifest_names:
        path = project / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        has_ui = any(t.lower() in text for t in _UI_INDICATOR_DEPS)
        has_llm = any(t.lower() in text for t in _PIPELINE_INDICATOR_DEPS)
        if has_ui and has_llm:
            return True
    return False


def _has_behavior_layer_doc(project: Path) -> bool:
    """Mirror of ``cli.orient._find_behavior_layer_doc``'s discovery rules."""
    docs = project / "docs"
    if docs.is_dir():
        for path in sorted(docs.glob("*_BEHAVIOR_LAYER.md")):
            if path.is_file():
                return True
        if (docs / "BEHAVIOR_LAYER.md").is_file():
            return True
    return (project / "BEHAVIOR_LAYER.md").is_file()


def check_behavior_layer_doc(project: Path) -> CheckResult:
    """Soft warning when a project has LLM / chat / voice / persona /
    UI behavior-surface indicators but no BEHAVIOR_LAYER.md.

    Status taxonomy:
    - ok       — BEHAVIOR_LAYER.md present
    - skipped  — no behavior-surface indicators
    - warning  — indicators present, doc missing

    Never blocking.
    """
    if _has_behavior_layer_doc(project):
        return CheckResult(
            id="behavior_layer_doc",
            label="Behavior layer (voice, presentation, constraints)",
            status="ok",
            detail="BEHAVIOR_LAYER.md present",
        )

    if not _project_has_behavior_indicators(project):
        return CheckResult(
            id="behavior_layer_doc",
            label="Behavior layer (voice, presentation, constraints)",
            status="skipped",
            detail="No LLM / chat / voice / persona / UI behavior-surface indicators detected; BEHAVIOR_LAYER.md not required",
        )

    return CheckResult(
        id="behavior_layer_doc",
        label="Behavior layer (voice, presentation, constraints)",
        status="warning",
        detail=(
            "BEHAVIOR_LAYER.md missing. Projects with chat, voice, "
            "persona-bearing UI, or any LLM-generated user-facing "
            "language should document voice, source-of-truth display "
            "rules, and constraint preservation across turns to "
            "prevent tone drift and rendered-data restatement bugs."
        ),
        fix=[
            "Create docs/<APP>_BEHAVIOR_LAYER.md (template ships with `context-kit init`)",
            "Document voice / tone, UI source-of-truth contract, constraint preservation, GOOD/BAD examples, and post-generation checks",
        ],
    )


# ---------------------------------------------------------------------------
# Translation-layer doc check (multi-audience / stakeholder projects)
# ---------------------------------------------------------------------------

# Audience / role tokens — when several show up in a single project,
# someone is writing prose for multiple readers, and a translation
# contract is meaningful. Kept lowercase; matched as substrings
# against filename stems and (separately) against doc text. Conservative
# list: each token must be unambiguous enough that a single hit on a
# trivial repo doesn't false-positive.
_TRANSLATION_INDICATOR_TOKENS = (
    "stakeholder", "stakeholders",
    "persona", "personas",
    "audience", "audiences",
    "executive", "executives",
    "operator", "operators",
    "owner", "owners",
    "reviewer", "reviewers",
    "tester", "testers",
    "qa",
    "training",
    "onboarding",
    "customer", "customers",
    "sales",
    "demo",
)

# Multi-audience signals require *more than one* role token to fire.
# A single "customer" mention in a README is not enough; two distinct
# audience words across docs / filenames is the threshold. Tunable —
# raise to reduce noise, lower to surface earlier.
_MIN_DISTINCT_TRANSLATION_INDICATORS = 2

# Minimum handoff count before "you have multiple build sessions and
# multiple readers" is a fair claim. Below this, the translation
# contract is overkill — one builder, one reader, one session.
_MIN_HANDOFFS_FOR_TRANSLATION_HINT = 3


def _has_translation_layer_doc(project: Path) -> bool:
    """Mirror of ``cli.orient._find_translation_layer_doc``'s discovery
    rules. Inlined to keep doctor a leaf module (no orient import)."""
    docs = project / "docs"
    if docs.is_dir():
        for path in sorted(docs.glob("*_TRANSLATION_LAYER.md")):
            if path.is_file():
                return True
        if (docs / "TRANSLATION_LAYER.md").is_file():
            return True
    return (project / "TRANSLATION_LAYER.md").is_file()


def _project_has_translation_indicators(project: Path) -> tuple[bool, list[str]]:
    """Heuristic: does this project look like it serves multiple
    audiences / stakeholders?

    Returns ``(triggered, reasons)`` so the warning can name the
    specific evidence that fired (avoids opaque "trust me" warnings
    on a heuristic).

    Triggers — any one is sufficient *if* the project also has
    BEHAVIOR_LAYER (clear sign of LLM-generated user-facing language)
    or a non-trivial handoff history. Tiny one-doc repos pass silently.

    1. Filenames containing two or more distinct audience tokens
       (``stakeholder``, ``persona``, ``executive``, ``tester``,
       ``operator``, etc.) — see ``_TRANSLATION_INDICATOR_TOKENS``.
    2. Multiple sessions in ``docs/handoffs/`` (``>=
       _MIN_HANDOFFS_FOR_TRANSLATION_HINT``) AND a BEHAVIOR_LAYER
       doc present (real multi-session product with persona output).
    """
    reasons: list[str] = []

    filename_hits = _scan_filenames_for_translation_tokens(project)
    if len(filename_hits) >= _MIN_DISTINCT_TRANSLATION_INDICATORS:
        reasons.append(
            "filename signals: " + ", ".join(sorted(filename_hits)[:5])
        )

    handoff_count = _count_session_handoffs(project)
    behavior_present = _has_behavior_layer_doc(project)
    if handoff_count >= _MIN_HANDOFFS_FOR_TRANSLATION_HINT and behavior_present:
        reasons.append(
            f"{handoff_count} session handoffs + a BEHAVIOR_LAYER doc — "
            "multi-session product with persona-bearing output"
        )

    return (bool(reasons), reasons)


def _scan_filenames_for_translation_tokens(project: Path) -> set[str]:
    """Walk the project (skipping ignored dirs) collecting which
    audience tokens appear in filename stems. Returns the set of
    tokens that hit at least once.
    """
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        # docs/ included because role tokens often appear in doc
        # filenames (e.g. ONBOARDING.md). Don't skip it.
    }
    if not project.is_dir():
        return set()
    hits: set[str] = set()
    stack = [project]
    visited = 0
    while stack and visited < 2000:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            visited += 1
            if visited >= 2000:
                break
            if child.is_dir():
                if child.name in skip_dirs or child.name.startswith("."):
                    continue
                stack.append(child)
                continue
            if not child.is_file():
                continue
            stem = child.stem.lower()
            if not stem:
                continue
            for token in _TRANSLATION_INDICATOR_TOKENS:
                if token in stem:
                    hits.add(token)
    return hits


def _count_session_handoffs(project: Path) -> int:
    """Count numbered ``SESSION_<digits>_*.md`` files. Matches the
    same pattern orient uses for "is this a multi-session repo?"."""
    handoffs = project / "docs" / "handoffs"
    if not handoffs.is_dir():
        return 0
    pat = re.compile(r"^SESSION_\d+_.+\.md$")
    return sum(1 for p in handoffs.glob("SESSION_*.md") if p.is_file() and pat.match(p.name))


def check_translation_layer_doc(project: Path) -> CheckResult:
    """Soft warning when a project has multi-audience / stakeholder
    indicators but no TRANSLATION_LAYER doc.

    Status taxonomy:
    - ok       — TRANSLATION_LAYER.md present
    - skipped  — no multi-audience indicators detected
    - warning  — indicators present, doc missing

    Never blocking. The translation layer is the contract that says
    *same truth → different explanation, zero invention* across
    audiences. Without it, prose for stakeholders / executives /
    testers tends to drift toward invented progress, business
    impact, or customer value the source-of-truth never claimed.
    """
    if _has_translation_layer_doc(project):
        return CheckResult(
            id="translation_layer_doc",
            label="Translation layer (audience contract)",
            status="ok",
            detail="TRANSLATION_LAYER.md present",
        )

    triggered, reasons = _project_has_translation_indicators(project)
    if not triggered:
        return CheckResult(
            id="translation_layer_doc",
            label="Translation layer (audience contract)",
            status="skipped",
            detail=(
                "No multi-audience / stakeholder indicators detected; "
                "TRANSLATION_LAYER.md not required"
            ),
        )

    return CheckResult(
        id="translation_layer_doc",
        label="Translation layer (audience contract)",
        status="warning",
        detail=(
            "TRANSLATION_LAYER.md missing. Projects with multiple "
            "audiences, stakeholders, testers, or operators should "
            "document how to translate the same facts for each "
            "audience without inventing unsupported claims. "
            "Indicators: " + "; ".join(reasons)
        ),
        fix=[
            "Create docs/<APP>_TRANSLATION_LAYER.md (template ships with `context-kit init`)",
            "Document personas, translation modes, and truth-preservation rules so prose for each audience cites only source-of-truth facts.",
        ],
    )


# ---------------------------------------------------------------------------
# Orientation-drift checks
#
# These checks catch the classes of failure that mature repos accumulate
# inside their own context-kit orientation layer:
#
#   1. Conflicting "next task" pointers between the adopt-managed block
#      and a handwritten "Next session priority / Next task" section.
#   2. Handoff numbering gaps — start-here doc references SESSION_008
#      but handoffs/ only goes up to SESSION_003.
#   3. Lingering ``[adopt: please describe]`` placeholders.
#   4. Adopt-emitted "Next actions" that have gone stale (the user
#      already answered "Confirm backend/frontend boundaries" but adopt
#      keeps re-emitting it on every run).
#
# All four are warnings, never blocking. The point is to surface drift,
# not to gate work on it. Older projects that pre-date these checks
# should pass silently when no drift is present.
# ---------------------------------------------------------------------------


# Marker constants intentionally duplicated here (rather than imported
# from cli.adopt) so doctor stays a leaf module — adopt is large and
# pulls in dataclasses we don't need.
_ADOPT_START_MARKER = "<!-- context-kit:adopt:start -->"
_ADOPT_END_MARKER = "<!-- context-kit:adopt:end -->"

# The placeholder string adopt writes when the user hasn't supplied a
# project description / next-task. Worth surfacing once any have been
# left in long enough to drift.
_ADOPT_PLACEHOLDER_RE = re.compile(r"\[adopt:\s*please describe[^\]]*\]")

# Files we're willing to scan for placeholders. Every file adopt knows
# how to write into. Anything else is out of scope — keeps false
# positives down (and protects user notes that quote the placeholder).
_PLACEHOLDER_SCAN_PATHS = (
    "00-START-NEXT-SESSION.md",
    "CLAUDE.md",
    "AGENTS.md",
    "BUILD_PLAN.md",
    "docs/BUILD_PLAN.md",
)

# Doc-glob patterns for placeholder scans (PROJECT_WHAT_IT_IS.md and
# any *_WHAT_IT_IS.md adopt may have generated).
_PLACEHOLDER_SCAN_GLOBS = (
    "docs/*_WHAT_IT_IS.md",
    "docs/PROJECT_WHAT_IT_IS.md",
)

# Section headers handwritten authors use to override / supplement the
# adopt-managed "What's next". Match generously but case-sensitively
# on the leading "## " so we don't catch quoted prose.
_HANDWRITTEN_NEXT_SECTION_RES = (
    re.compile(r"^##\s+Next session priorit", re.IGNORECASE),
    re.compile(r"^##\s+Next session priority", re.IGNORECASE),
    re.compile(r"^##\s+Next task\b", re.IGNORECASE),
    re.compile(r"^##\s+Next priority\b", re.IGNORECASE),
    re.compile(r"^##\s+Next step\b", re.IGNORECASE),
    re.compile(r"^##\s+What's next\b", re.IGNORECASE),
    re.compile(r"^##\s+This session's priorities\b", re.IGNORECASE),
    re.compile(r"^##\s+Priorit", re.IGNORECASE),
)

# Adopt-emitted "Next actions" titles that go stale fastest in real
# repos. Conservative list — these are the ones the Freedom Ford
# audit specifically called out, plus a couple of close cousins from
# the adopt source. Each entry is the suggested-action title that
# adopt renders as a bullet/heading inside the managed block.
_STALE_ACTION_TITLES = (
    "Confirm backend/frontend boundaries",
    "Classify unrecognized directories",
    "Confirm mobile app structure",
    "Clarify project shape before coding",
    "Review workspace children",
)

# How many handoff jumps we tolerate between latest handoff and the
# session number the start-here doc references. One off-by-one is
# normal (next session N+1 hasn't been written yet). Two or more is
# the sign of a real gap.
_HANDOFF_GAP_TOLERANCE = 1

# Regex for SESSION_NNN tokens inside any markdown reference / heading.
# Matches both "SESSION_008" bare and inside path-like strings.
_SESSION_NUMBER_RE = re.compile(r"SESSION_(\d+)\b")


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _strip_managed_block(text: str) -> str:
    """Return ``text`` with every adopt-managed block removed.

    Used to isolate handwritten content. Multiple managed blocks (rare
    but legal) are all stripped. If a start marker has no matching end
    marker, the rest of the document is treated as managed — better to
    over-strip than to misread the user's content as adopt's.
    """
    out: list[str] = []
    cursor = 0
    while True:
        start = text.find(_ADOPT_START_MARKER, cursor)
        if start == -1:
            out.append(text[cursor:])
            return "".join(out)
        out.append(text[cursor:start])
        end = text.find(_ADOPT_END_MARKER, start + len(_ADOPT_START_MARKER))
        if end == -1:
            return "".join(out)
        cursor = end + len(_ADOPT_END_MARKER)


def _extract_managed_block(text: str) -> Optional[str]:
    """Return the *body* of the first adopt-managed block, or None.

    Body excludes the marker lines themselves so callers can grep
    headers without false matches on the markers.
    """
    start = text.find(_ADOPT_START_MARKER)
    if start == -1:
        return None
    end = text.find(_ADOPT_END_MARKER, start + len(_ADOPT_START_MARKER))
    if end == -1:
        return text[start + len(_ADOPT_START_MARKER):]
    return text[start + len(_ADOPT_START_MARKER):end]


def _section_body(text: str, header_res: tuple[re.Pattern[str], ...]) -> Optional[str]:
    """Return the body of the first section whose header matches any
    pattern in ``header_res``, or None.

    Body runs from the line after the header to the next ``##`` heading
    or end of text. Trailing whitespace is stripped; leading/internal
    whitespace is preserved so the caller can compare meaningfully.
    """
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        for pat in header_res:
            if pat.search(line):
                body_lines: list[str] = []
                for follow in lines[idx + 1:]:
                    if follow.startswith("## "):
                        break
                    body_lines.append(follow)
                return "\n".join(body_lines).strip()
    return None


def _normalize_for_compare(s: str) -> str:
    """Whitespace-collapse a markdown body for equality comparison."""
    return re.sub(r"\s+", " ", s).strip()


def check_next_task_consistency(project: Path) -> CheckResult:
    """Warn when 00-START-NEXT-SESSION.md has two disagreeing next-task pointers.

    Mature repos accumulate this: ``adopt`` keeps re-emitting its
    ``## What's next`` line inside the managed block, while a human
    rewrites priorities in a handwritten ``## Next session priorities``
    section. The two slowly diverge. Agents reading orient see one
    answer but the file claims another section is canonical.

    Detection rules:
    * The file must have an adopt-managed block with a ``## What's next``
      section inside it.
    * The handwritten content (managed blocks stripped) must contain a
      section whose header looks like a "next task" override (``Next
      session priorit*``, ``Next task``, ``Priorit*``, ``This session's
      priorities``, ``What's next``).
    * The two bodies, after whitespace-normalization, must differ
      meaningfully.

    Warning, never blocking — the file is still readable.
    """
    start_doc = project / "00-START-NEXT-SESSION.md"
    if not start_doc.is_file():
        return CheckResult(
            id="next_task_consistency",
            label="Next-task pointer consistency",
            status="skipped",
            detail="00-START-NEXT-SESSION.md not present",
        )

    text = _read_text(start_doc)
    if text is None:
        return CheckResult(
            id="next_task_consistency",
            label="Next-task pointer consistency",
            status="skipped",
            detail="Could not read 00-START-NEXT-SESSION.md",
        )

    managed = _extract_managed_block(text)
    if managed is None:
        return CheckResult(
            id="next_task_consistency",
            label="Next-task pointer consistency",
            status="skipped",
            detail="No adopt-managed block in 00-START-NEXT-SESSION.md",
        )

    managed_next = _section_body(managed, (re.compile(r"^##\s+What's next\b", re.IGNORECASE),))
    if not managed_next:
        return CheckResult(
            id="next_task_consistency",
            label="Next-task pointer consistency",
            status="skipped",
            detail='Adopt block has no "What\'s next" section to compare',
        )

    handwritten = _strip_managed_block(text)
    handwritten_next = _section_body(handwritten, _HANDWRITTEN_NEXT_SECTION_RES)
    if not handwritten_next:
        return CheckResult(
            id="next_task_consistency",
            label="Next-task pointer consistency",
            status="ok",
            detail='Single source for "next task" — adopt block only',
        )

    if _normalize_for_compare(managed_next) == _normalize_for_compare(handwritten_next):
        return CheckResult(
            id="next_task_consistency",
            label="Next-task pointer consistency",
            status="ok",
            detail="Adopt-managed and handwritten next-task pointers agree",
        )

    return CheckResult(
        id="next_task_consistency",
        label="Next-task pointer consistency",
        status="warning",
        detail=(
            "00-START-NEXT-SESSION.md has two disagreeing next-task pointers: "
            'the adopt-managed "## What\'s next" inside the block and a '
            'handwritten "Next session priorities" / "Next task" section '
            "outside it. Agents reading orient confidently surface one "
            "while the file claims another section is canonical."
        ),
        fix=[
            "Pick one as canonical. Either:",
            '  - delete the handwritten section and let adopt own "What\'s next", or',
            "  - delete the adopt-managed block (or update its --next-task on the next adopt run) so the handwritten section is the only pointer.",
        ],
    )


def _next_session_number_from_start_doc(project: Path) -> Optional[int]:
    """Best-effort extraction of the SESSION_NNN the start-here doc points at.

    Heuristic: read 00-START-NEXT-SESSION.md, find every ``SESSION_NNN``
    token, and return the *highest* number — the assumption is that
    when the file references multiple session IDs, the one farthest in
    the future is the "next" pointer (which is the one that needs to
    line up with the latest handoff). False positives are tolerable;
    this only feeds a warning.
    """
    start_doc = project / "00-START-NEXT-SESSION.md"
    text = _read_text(start_doc)
    if text is None:
        return None
    matches = _SESSION_NUMBER_RE.findall(text)
    if not matches:
        return None
    try:
        return max(int(m) for m in matches)
    except ValueError:
        return None


def _latest_handoff_number(project: Path) -> Optional[int]:
    """Return the highest numbered ``SESSION_NNN_*.md`` in ``docs/handoffs/``."""
    handoffs = project / "docs" / "handoffs"
    if not handoffs.is_dir():
        return None
    pat = re.compile(r"^SESSION_(\d+)_.+\.md$")
    nums: list[int] = []
    for p in handoffs.glob("SESSION_*.md"):
        if not p.is_file():
            continue
        m = pat.match(p.name)
        if m is None:
            continue
        try:
            nums.append(int(m.group(1)))
        except ValueError:
            continue
    return max(nums) if nums else None


def check_handoff_numbering(project: Path) -> CheckResult:
    """Warn if the start-here doc names a SESSION_NNN that's far ahead of the
    latest handoff on disk.

    Real-world failure: ``00-START-NEXT-SESSION.md`` says SESSION_008,
    but ``docs/handoffs/`` only goes up to SESSION_003. Either four
    handoffs are missing (drift) or the next-pointer is stale. Either
    way, the latest-handoff continuity rule is broken and an agent
    that reads orient will form the wrong picture of state-of-system.

    Skipped unless we can read both numbers. Warning when the gap is
    greater than ``_HANDOFF_GAP_TOLERANCE``. Never blocking.
    """
    numbers = state.get_handoff_numbers(project)
    missing = state.missing_handoff_numbers(numbers)
    if missing:
        formatted = ", ".join(f"SESSION_{n:03d}" for n in missing[:8])
        more = "" if len(missing) <= 8 else ", ..."
        return CheckResult(
            id="handoff_numbering",
            label="Handoff numbering continuity",
            status="warning",
            detail=f"Missing numbered handoff(s): {formatted}{more}",
            fix="Backfill missing handoffs from CHANGELOG.md / git log, or document the intentional numbering gap.",
        )

    next_num = _next_session_number_from_start_doc(project)
    latest_num = _latest_handoff_number(project)
    if next_num is None or latest_num is None:
        return CheckResult(
            id="handoff_numbering",
            label="Handoff numbering continuity",
            status="skipped",
            detail="Could not derive SESSION numbers from start-here / handoffs/",
        )

    gap = next_num - latest_num
    if gap <= _HANDOFF_GAP_TOLERANCE:
        return CheckResult(
            id="handoff_numbering",
            label="Handoff numbering continuity",
            status="ok",
            detail=(
                f"Start-here references SESSION_{next_num:03d}; "
                f"latest handoff is SESSION_{latest_num:03d} (gap {gap})"
            ),
        )

    return CheckResult(
        id="handoff_numbering",
        label="Handoff numbering continuity",
        status="warning",
        detail=(
            f"Handoff numbering gap: 00-START-NEXT-SESSION.md references "
            f"SESSION_{next_num:03d}, but the latest on-disk handoff is "
            f"SESSION_{latest_num:03d} ({gap} sessions missing). "
            "The latest handoff is supposed to represent state-of-system "
            "continuity — that contract is broken when intermediate "
            "handoffs go missing."
        ),
        fix=[
            "Backfill the missing handoffs from CHANGELOG.md / git log, or",
            f"Renumber the next-session pointer to SESSION_{latest_num + 1:03d}.",
        ],
    )


def check_start_handoff_conflict(project: Path) -> CheckResult:
    """Warn when start-here and latest handoff may point at different state."""
    start_session = state.get_start_session_number(project)
    latest = state.get_latest_handoff(project)
    if start_session is None or latest is None:
        return CheckResult(
            id="start_handoff_conflict",
            label="Start vs handoff verification",
            status="skipped",
            detail="Could not derive session number from start-here or latest handoff",
        )

    if start_session != latest.number:
        return CheckResult(
            id="start_handoff_conflict",
            label="Start vs handoff verification",
            status="warning",
            detail=(
                f"start-here references SESSION_{start_session:03d}; "
                f"latest handoff is {latest.token}"
            ),
            fix=(
                "Verify whether start-here intentionally points beyond the latest "
                "handoff. If so, document that; otherwise update start-here or "
                "write the missing handoff."
            ),
        )

    next_task = state.first_task_line(state.get_next_task(project)).lower()
    handoff_text = state.read_text(latest.path).lower()
    if next_task and next_task not in handoff_text:
        return CheckResult(
            id="start_handoff_conflict",
            label="Start vs handoff verification",
            status="warning",
            detail=(
                f"Verify {state.START_DOC} next task against "
                f"{latest.path.relative_to(project)}; the task text was not "
                "found verbatim in the latest handoff."
            ),
            fix=(
                "Confirm whether start-here intentionally supersedes the latest "
                "handoff. If so, document that; otherwise update the latest "
                "handoff or start-here so they agree."
            ),
        )

    return CheckResult(
        id="start_handoff_conflict",
        label="Start vs handoff verification",
        status="ok",
        detail=f"start-here and latest handoff both point at {latest.token}",
    )


def _scan_files_for_placeholders(project: Path) -> list[str]:
    """Return relative paths of files that contain at least one
    ``[adopt: please describe...]`` placeholder.

    Scans only the small set of files adopt knows how to write into.
    De-duplicated, sorted for stable output.
    """
    found: set[str] = set()
    for rel in _PLACEHOLDER_SCAN_PATHS:
        path = project / rel
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            continue
        if _ADOPT_PLACEHOLDER_RE.search(text):
            found.add(rel)
    for pattern in _PLACEHOLDER_SCAN_GLOBS:
        for path in project.glob(pattern):
            if not path.is_file():
                continue
            text = _read_text(path)
            if text is None:
                continue
            if _ADOPT_PLACEHOLDER_RE.search(text):
                try:
                    rel = str(path.relative_to(project))
                except ValueError:
                    rel = path.name
                found.add(rel)
    return sorted(found)


def check_adopt_placeholders(project: Path) -> CheckResult:
    """Warn if any ``[adopt: please describe ...]`` placeholders remain.

    Adopt writes these when the user hasn't supplied a project-summary
    or next-task on a `--write` run. They're meant to be filled in
    immediately. In practice they tend to linger, which silently
    erodes trust in the generated anchors — an agent reads the file
    and finds an unfilled placeholder where it expected real context.

    Warning, never blocking.
    """
    files = _scan_files_for_placeholders(project)
    if not files:
        return CheckResult(
            id="adopt_placeholders",
            label="Unresolved adopt placeholders",
            status="ok",
            detail="No `[adopt: please describe]` placeholders found",
        )

    return CheckResult(
        id="adopt_placeholders",
        label="Unresolved adopt placeholders",
        status="warning",
        detail=(
            f"`[adopt: please describe]` placeholder(s) remain in: "
            f"{', '.join(files)}. Adopt writes these when --project-summary "
            "or --next-task wasn't supplied; they're meant to be filled in, "
            "not left in. Lingering placeholders reduce trust in the "
            "generated anchors."
        ),
        fix=[
            "Edit each file and replace the placeholder with the real value.",
            "Or re-run adopt with --project-summary / --next-task / --notes "
            "to regenerate the managed blocks with real content.",
        ],
    )


def _stale_action_hits(project: Path) -> list[str]:
    """Return the stale-prone action titles that appear inside any
    adopt-managed block in the start-here doc or CLAUDE.md.

    Conservative — only checks the small set of files adopt manages.
    De-duplicated, sorted for stable output.
    """
    found: set[str] = set()
    for rel in ("00-START-NEXT-SESSION.md", "CLAUDE.md", "BUILD_PLAN.md", "docs/BUILD_PLAN.md"):
        path = project / rel
        if not path.is_file():
            continue
        text = _read_text(path)
        if text is None:
            continue
        managed = _extract_managed_block(text)
        if managed is None:
            continue
        for title in _STALE_ACTION_TITLES:
            if title in managed:
                found.add(title)
    return sorted(found)


def check_stale_generic_actions(project: Path) -> CheckResult:
    """Warn when adopt's "Next actions" still emit generic titles that
    have likely been answered.

    Adopt picks actions like "Confirm backend/frontend boundaries" or
    "Classify unrecognized directories" the *first* time it runs. They
    are useful immediately but become noise once the user has
    answered them — and adopt has no way to know they're answered, so
    every re-run keeps re-emitting them.

    Conservative warning. The user has to decide whether the action is
    still relevant or whether to clear it (by editing the managed
    block, or by passing the answer back into adopt via --notes /
    --project-summary).
    """
    titles = _stale_action_hits(project)
    if not titles:
        return CheckResult(
            id="stale_generic_actions",
            label="Stale adopt-emitted next actions",
            status="ok",
            detail="No generic adopt actions detected (or adopt block absent)",
        )

    return CheckResult(
        id="stale_generic_actions",
        label="Stale adopt-emitted next actions",
        status="warning",
        detail=(
            "Adopt-managed block still shows generic next-action title(s): "
            f"{', '.join(titles)}. These are useful on first init but "
            "become noise once answered — review whether they still apply."
        ),
        fix=[
            "If they're answered: edit the managed block to remove or "
            "replace them, or re-run adopt with --notes / --project-summary "
            "so subsequent runs reflect the answers.",
            "If they're still open: leave them but treat them as actionable, "
            "not informational.",
        ],
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _emit_json(results: list[CheckResult], project: Path) -> None:
    summary = {
        "ok": sum(1 for r in results if r.status == "ok"),
        "warnings": sum(1 for r in results if r.status == "warning"),
        "blocking": sum(1 for r in results if r.status == "blocking"),
        "skipped": sum(1 for r in results if r.status == "skipped"),
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "project_path": str(project),
        "summary": summary,
        "exit_code": _exit_code(results),
        "checks": [asdict(r) for r in results],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


_STATUS_PREFIX = {
    "ok":       "    ",
    "warning":  "  ! ",
    "blocking": "  X ",
    "skipped":  "  - ",
}


def _emit_human(results: list[CheckResult], project: Path) -> None:
    print("context-kit doctor — environment + setup diagnostics")
    print(f"project: {project}")
    print()

    by_status: dict[str, list[CheckResult]] = {
        "ok": [], "warning": [], "blocking": [], "skipped": []
    }
    for r in results:
        by_status[r.status].append(r)

    sections = [
        ("OK",        by_status["ok"]),
        ("Warnings",  by_status["warning"]),
        ("Blocking",  by_status["blocking"]),
        ("Skipped",   by_status["skipped"]),
    ]

    for label, items in sections:
        if not items:
            continue
        print(f"{label} ({len(items)})")
        for r in items:
            prefix = _STATUS_PREFIX[r.status]
            print(f"{prefix}{r.label}: {r.detail}")
            if r.fix:
                fix_list = r.fix if isinstance(r.fix, list) else [r.fix]
                for line in fix_list:
                    print(f"      {line}")
        print()

    fixes: list[str] = []
    for r in results:
        if r.status not in ("blocking", "warning") or not r.fix:
            continue
        fix_list = r.fix if isinstance(r.fix, list) else [r.fix]
        for line in fix_list:
            if line not in fixes:
                fixes.append(line)
    if fixes:
        print("Suggested next commands")
        for f in fixes[:10]:
            print(f"  {f}")
        print()

    rc = _exit_code(results)
    n_blocking = len(by_status["blocking"])
    n_warning = len(by_status["warning"])
    print(f"({n_blocking} blocking, {n_warning} warnings — exit {rc})")
