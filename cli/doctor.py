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
friction (Munchkin App). See ``docs/handoffs/SESSION_006_DOCTOR.md``
for the receipts. The dependency direction is **doctor → inventory**;
never invert it.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

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
