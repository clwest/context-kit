"""context-kit `inspect` subcommand: deterministic system map for any repo.

Where ``audit`` outsources inspection to an LLM (the prompt is the output)
and ``inventory`` reports fixed-schema counts for context-kit-native
projects, ``inspect`` reads an *arbitrary* repo and prints what's there:
primary stack, subsystems, framework signals, hot files, risk patterns,
likely-stale docs, and a short list of recommended next moves.

Read-only by contract: never modifies files, never invokes an AI, never
parses code as an AST. Filename / regex probes only.

v1 framework scope: Django + Next.js. Other ecosystems are detected as
their primary language but don't get framework-specific signal counts.

Monorepo handling: depth-1 child workspaces are detected by manifest
presence; framework probes run inside each child once. No deeper
recursion in v1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cli.hotpath import (
    IGNORED_DIR_NAMES,
    IGNORED_DIR_SUFFIXES,
    _collect_files,
    _with_sizes,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Manifests that anchor a stack at the directory they live in.
_MANIFESTS = {
    "pyproject.toml": "python",
    "setup.py": "python",
    "setup.cfg": "python",
    "requirements.txt": "python",
    "manage.py": "python-django",
    "package.json": "javascript",
    "next.config.js": "javascript-nextjs",
    "next.config.ts": "javascript-nextjs",
    "next.config.mjs": "javascript-nextjs",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "Gemfile": "ruby",
    "composer.json": "php",
    "hardhat.config.js": "smart-contract",
    "hardhat.config.ts": "smart-contract",
    "foundry.toml": "smart-contract",
}

# Common entry-point filenames for the brief "Entry points" section.
_ENTRY_POINT_HINTS = {
    "manage.py": "django-cli",
    "context_kit.py": "context-kit-cli",
    "wsgi.py": "django-wsgi",
    "asgi.py": "django-asgi",
    "main.py": "python-main",
    "server.js": "node-server",
    "app.js": "node-app",
    "Procfile": "process-manifest",
    "Dockerfile": "container-build",
}

# Tracked-virtualenv top-level directory names.
_TRACKED_VENV_NAMES = ("venv", ".venv", "venv_ml", "env", "ENV")

# Directory names that should never be tracked (build / cache / vendor).
_TRACKED_BUILD_NAMES = ("__pycache__", "node_modules", "dist", "build", ".pytest_cache", ".mypy_cache")

# Static-asset extensions that often hold oversized binaries.
_STATIC_ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
_STATIC_DIR_SEGMENTS = ("static", "public", "assets")

# Threshold (bytes) for flagging a static asset as "oversized".
_OVERSIZED_ASSET_BYTES = 5 * 1024 * 1024  # 5 MB

_INSPECT_SCOPES = (
    "core",
    "celery",
    "agents",
    "spiders",
    "docs-rag",
    "frontend",
    "deployment",
    "tests",
)

# How many hot files to include in the report by default.
_HOT_FILES_TOP_N = 5

# Markers that suggest a doc has a self-reported date.
_STALENESS_MARKERS = ("Last Updated:", "Generated:", "**Updated:**", "Last updated:")

# How old a self-reported date must be before we flag the doc as likely stale.
_STALE_DOC_AGE_DAYS = 30

# Regex passes — kept simple and bounded.
_DJANGO_URL_RE = re.compile(r"\b(?:re_)?path\s*\(", re.MULTILINE)
_DJANGO_TASK_RE = re.compile(r"@(?:shared_task|app\.task|celery\.task|celery_app\.task)\b")
_INSTALLED_APPS_RE = re.compile(r"INSTALLED_APPS\s*=\s*\[([^\]]+)\]", re.DOTALL)
_FRONTMATTER_DATE_RE = re.compile(r"^date:\s*(\d{4}-\d{2}-\d{2})", re.MULTILINE)
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FrameworkSignals:
    django: dict | None = None
    nextjs: dict | None = None

    def is_empty(self) -> bool:
        return self.django is None and self.nextjs is None


@dataclass
class Subsystem:
    path: str
    files: int
    bytes: int
    note: str
    primary_stack: list[str] = field(default_factory=list)
    framework_signals: FrameworkSignals = field(default_factory=FrameworkSignals)


@dataclass
class Risk:
    id: str
    severity: str  # "high" | "medium" | "low"
    summary: str
    evidence: list[str]


@dataclass
class StaleDoc:
    path: str
    evidence: str


@dataclass
class HotFile:
    path: str
    bytes: int


@dataclass
class DocumentationIntelligence:
    """Evidence that ``docs/`` is being used as an active AI memory /
    context layer rather than passive reference material.

    ``strength`` is the load-bearing field for both renderers and the
    recommendation engine:

    - ``none``  — no ``docs/`` folder, or no markdown under it
    - ``low``   — docs exist but no active-layer signals
    - ``medium`` — at least 2 active-layer signals OR significant scale
    - ``high``   — at least 2 signals AND scale (≥ 200 markdown files
      OR ≥ 50 session handoffs)

    ``medium`` and above render as a "Documentation Intelligence"
    section in the report; ``high`` additionally fires the
    ``review-docs-context-first`` recommendation.
    """
    markdown_file_count: int
    session_handoff_count: int
    anchor_docs: list[str]
    audit_folders: list[str]
    process_docs_present: bool
    rag_corpus_present: bool
    rag_corpus_paths: list[str]
    strength: str  # "none" | "low" | "medium" | "high"


@dataclass
class Recommendation:
    """A deterministic, signal-driven suggestion for what to do next.

    Recommendations are *not* commands — they're surfaced for the human
    or agent to consider, override, or ignore. Each carries a stable
    ``id`` so future feedback / override storage can target a specific
    suggestion without parsing prose. v1 has no override store; the
    structure is the contract for v2.
    """
    id: str
    suggestion: str
    why: str
    confidence: str  # "low" | "medium" | "high"


@dataclass
class InspectionResult:
    repo: str
    path: str
    scope: str | None
    head: dict | None  # {"sha": ..., "branch": ...}
    counts: dict  # {"tracked_files": int, "total_bytes": int}
    primary_stack: dict  # {"languages": [...], "frameworks": [...], "confidence": str, "manifests": [...]}
    subsystems: list[Subsystem]
    entry_points: list[dict]
    framework_signals: FrameworkSignals
    hot_files: list[HotFile]
    risks: list[Risk]
    stale_docs: list[StaleDoc]
    documentation_intelligence: DocumentationIntelligence
    recommendations: list[Recommendation]
    include_related: bool = False
    include_history: bool = False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_inspect(args: argparse.Namespace) -> int:
    project = Path(args.path).resolve() if args.path else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    scope = getattr(args, "scope", None)
    if scope is not None and scope not in _INSPECT_SCOPES:
        print(f"context-kit: unknown inspect scope `{scope}`. Valid scopes: {', '.join(_INSPECT_SCOPES)}.")
        return 2

    result = _inspect(
        project,
        depth=getattr(args, "depth", 2),
        scope=scope,
        include_related=getattr(args, "include_related", False),
        include_history=getattr(args, "include_history", False),
    )

    if getattr(args, "json", False):
        print(json.dumps(_to_json(result), indent=2, default=str))
    else:
        print(_render_text(result))
    return 0


# ---------------------------------------------------------------------------
# Inspection orchestration
# ---------------------------------------------------------------------------


def _inspect(
    project: Path,
    *,
    depth: int,
    scope: str | None = None,
    include_related: bool = False,
    include_history: bool = False,
) -> InspectionResult:
    files, _ = _collect_files(project)
    if scope is not None:
        files = _filter_inspect_scope_files(
            project,
            files,
            scope,
            include_related=include_related,
            include_history=include_history,
        )
    files = [path for path in files if _inspect_file_is_live(path, include_history=include_history)]
    sized = _with_sizes(files)
    total_bytes = sum(s for _, s in sized)

    head = _git_head(project)
    root_manifests = _detect_manifests_at(project) if scope is None else _detect_manifests_from_files(files)
    primary_stack = _classify_stack(root_manifests)

    workspaces = [] if scope is not None else _detect_workspaces(project, depth=depth)

    root_framework = _probe_frameworks(project, sized) if scope is None else _probe_frameworks_scoped(project, sized, set(files))

    subsystems = _build_subsystems(project, sized, workspaces)

    entry_points = _detect_entry_points(project, files if scope is not None else None)
    hot_files = _build_hot_files(sized, project)
    risks = _check_risks(project, sized, files if scope is not None else None)
    stale_docs = _check_stale_docs(project, files if scope is not None else None)
    doc_intel = _inspect_documentation_intelligence(project, files if scope is not None else None)
    recommendations = _build_recommendations(
        project=project,
        risks=risks,
        hot_files=hot_files,
        stale_docs=stale_docs,
        root_framework=root_framework,
        subsystems=subsystems,
        sized=sized,
        doc_intel=doc_intel,
    )

    return InspectionResult(
        repo=project.name,
        path=str(project),
        head=head,
        counts={"tracked_files": len(sized), "total_bytes": total_bytes},
        primary_stack=primary_stack,
        subsystems=subsystems,
        entry_points=entry_points,
        framework_signals=root_framework,
        hot_files=hot_files,
        risks=risks,
        stale_docs=stale_docs,
        documentation_intelligence=doc_intel,
        recommendations=recommendations,
        scope=scope,
        include_related=include_related if scope is not None else False,
        include_history=include_history if scope is not None else False,
    )


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_head(project: Path) -> dict | None:
    if not (project / ".git").exists():
        return None
    sha = _git_run(project, ["rev-parse", "--short", "HEAD"])
    branch = _git_run(project, ["rev-parse", "--abbrev-ref", "HEAD"])
    if sha is None and branch is None:
        return None
    return {"sha": sha, "branch": branch}


def _git_run(project: Path, args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            check=False,
            text=True,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


# ---------------------------------------------------------------------------
# Manifest / stack detection
# ---------------------------------------------------------------------------


def _detect_manifests_at(directory: Path) -> list[str]:
    """Return manifest filenames present in ``directory`` (non-recursive)."""
    found: list[str] = []
    for name in _MANIFESTS:
        if (directory / name).is_file():
            found.append(name)
    return found


def _detect_manifests_from_files(files: list[Path]) -> list[str]:
    found: list[str] = []
    for name in _MANIFESTS:
        if any(path.name == name for path in files):
            found.append(name)
    return found


def _classify_stack(manifests: list[str]) -> dict:
    """Translate a manifest list into a primary-stack summary."""
    languages: list[str] = []
    frameworks: list[str] = []
    for m in manifests:
        kind = _MANIFESTS[m]
        if kind == "python":
            if "python" not in languages:
                languages.append("python")
        elif kind == "python-django":
            if "python" not in languages:
                languages.append("python")
            if "django" not in frameworks:
                frameworks.append("django")
        elif kind == "javascript":
            if "javascript" not in languages:
                languages.append("javascript")
        elif kind == "javascript-nextjs":
            if "javascript" not in languages:
                languages.append("javascript")
            if "nextjs" not in frameworks:
                frameworks.append("nextjs")
        elif kind == "rust":
            if "rust" not in languages:
                languages.append("rust")
        elif kind == "go":
            if "go" not in languages:
                languages.append("go")
        elif kind == "ruby":
            if "ruby" not in languages:
                languages.append("ruby")
        elif kind == "php":
            if "php" not in languages:
                languages.append("php")
        elif kind == "smart-contract":
            if "smart-contract" not in frameworks:
                frameworks.append("smart-contract")

    confidence = "low"
    if manifests:
        confidence = "medium"
    if languages and frameworks:
        confidence = "high"
    if not manifests:
        confidence = "none"

    return {
        "languages": languages,
        "frameworks": frameworks,
        "confidence": confidence,
        "manifests": manifests,
    }


# ---------------------------------------------------------------------------
# Workspace detection (depth=1 only)
# ---------------------------------------------------------------------------


def _detect_workspaces(project: Path, *, depth: int) -> list[Path]:
    """Return depth-1 child directories that look like their own workspace."""
    if depth < 1:
        return []
    workspaces: list[Path] = []
    try:
        children = sorted(p for p in project.iterdir() if p.is_dir())
    except OSError:
        return []
    for child in children:
        name = child.name
        if name in IGNORED_DIR_NAMES:
            continue
        if any(name.endswith(sfx) for sfx in IGNORED_DIR_SUFFIXES):
            continue
        if name.startswith("."):
            continue
        if _detect_manifests_at(child):
            workspaces.append(child)
    return workspaces


# ---------------------------------------------------------------------------
# Framework probes — Django + Next.js only
# ---------------------------------------------------------------------------


def _probe_frameworks(scope: Path, sized: list[tuple[Path, int]]) -> FrameworkSignals:
    """Run framework probes scoped to ``scope`` (project root or a workspace
    child). Each probe is filename-pattern + light regex."""
    fs = FrameworkSignals()
    if (scope / "manage.py").is_file():
        fs.django = _probe_django(scope, sized)
    next_config = _has_any(scope, ["next.config.js", "next.config.ts", "next.config.mjs", "next.config.cjs"])
    if next_config:
        fs.nextjs = _probe_nextjs(scope)
    return fs


def _probe_frameworks_scoped(scope: Path, sized: list[tuple[Path, int]], allowed_paths: set[Path]) -> FrameworkSignals:
    fs = FrameworkSignals()
    allowed = [(p, s) for p, s in sized if p in allowed_paths]
    if any(p.name == "manage.py" for p, _ in allowed):
        fs.django = _probe_django(scope, allowed)
    if any(p.name in {"next.config.js", "next.config.ts", "next.config.mjs", "next.config.cjs"} for p, _ in allowed):
        fs.nextjs = _probe_nextjs_from_files(scope, [p for p, _ in allowed])
    return fs


def _has_any(directory: Path, names: list[str]) -> bool:
    return any((directory / n).is_file() for n in names)


def _probe_django(scope: Path, sized: list[tuple[Path, int]]) -> dict:
    """Cheap Django signal probe. Counts management commands, url patterns,
    task decorators, view files, model files; sniffs INSTALLED_APPS length."""
    scope_str = str(scope)

    # Files inside this scope only (not the parent project).
    in_scope = [p for p, _ in sized if str(p).startswith(scope_str + os.sep) or str(p) == scope_str]

    # Light filename-glob counters.
    mgmt_commands = sum(
        1 for p in in_scope
        if "management" in p.parts and "commands" in p.parts and p.suffix == ".py"
        and p.name not in ("__init__.py",)
    )
    view_files = sum(1 for p in in_scope if p.name.startswith("views") and p.suffix == ".py")
    model_files = sum(1 for p in in_scope if p.name.startswith("models") and p.suffix == ".py")
    urls_files = [p for p in in_scope if p.name.startswith("urls") and p.suffix == ".py"]
    tasks_files = [p for p in in_scope if p.name.startswith("tasks") and p.suffix == ".py"]
    settings_files = [p for p in in_scope if p.name.startswith("settings") and p.suffix == ".py"]

    url_patterns = _count_regex_in_files(urls_files, _DJANGO_URL_RE)
    tasks_count = _count_regex_in_files(tasks_files, _DJANGO_TASK_RE)
    apps_count = _count_installed_apps(settings_files)

    return {
        "apps": apps_count,
        "url_patterns": url_patterns,
        "tasks": tasks_count,
        "management_commands": mgmt_commands,
        "view_files": view_files,
        "model_files": model_files,
        "urls_files": len(urls_files),
    }


def _probe_nextjs(scope: Path) -> dict:
    """Count route files under ``app/`` and ``pages/`` (Next.js conventions)."""
    route_files = 0
    api_routes = 0

    app_dir = scope / "app"
    if app_dir.is_dir():
        for root, _, files in os.walk(app_dir):
            for name in files:
                if name in ("page.tsx", "page.ts", "page.jsx", "page.js"):
                    route_files += 1
                elif name in ("route.ts", "route.tsx", "route.js"):
                    api_routes += 1

    pages_dir = scope / "pages"
    if pages_dir.is_dir():
        for root, _, files in os.walk(pages_dir):
            for name in files:
                if name.endswith((".tsx", ".ts", ".jsx", ".js")):
                    rel = Path(root).relative_to(pages_dir)
                    if "api" in rel.parts:
                        api_routes += 1
                    else:
                        route_files += 1

    return {
        "route_files": route_files,
        "api_routes": api_routes,
    }


def _probe_nextjs_from_files(scope: Path, files: list[Path]) -> dict:
    route_files = 0
    api_routes = 0
    for path in files:
        try:
            rel = path.relative_to(scope)
        except ValueError:
            rel = path
        parts = rel.parts
        parents = parts[:-1]
        if path.name in ("page.tsx", "page.ts", "page.jsx", "page.js"):
            if "app" in parents or "pages" in parents:
                route_files += 1
        elif path.name in ("route.ts", "route.tsx", "route.js"):
            if "app" in parents or "api" in parents or "pages" in parents:
                api_routes += 1
    return {"route_files": route_files, "api_routes": api_routes}


def _count_regex_in_files(files: list[Path], pattern: re.Pattern) -> int:
    total = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(pattern.findall(text))
    return total


def _count_installed_apps(settings_files: list[Path]) -> int:
    """Sniff the largest INSTALLED_APPS list across settings files. Counts
    quoted strings inside the first matching block; doesn't try to merge
    extends / overrides across files."""
    best = 0
    for path in settings_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = _INSTALLED_APPS_RE.search(text)
        if not match:
            continue
        body = match.group(1)
        # Count quoted strings; tolerant of trailing commas / comments.
        count = len(re.findall(r"['\"][a-zA-Z0-9_.]+['\"]", body))
        if count > best:
            best = count
    return best


# ---------------------------------------------------------------------------
# Subsystem grouping
# ---------------------------------------------------------------------------


def _build_subsystems(
    project: Path,
    sized: list[tuple[Path, int]],
    workspaces: list[Path],
) -> list[Subsystem]:
    """Per-subsystem rollup. Each workspace gets its own framework probe;
    non-workspace top-level dirs get a file-count summary."""
    subsystems: list[Subsystem] = []

    # Bucket all tracked files by their depth-1 parent under project.
    buckets: dict[str, list[tuple[Path, int]]] = {}
    for path, size in sized:
        try:
            rel = path.relative_to(project)
        except ValueError:
            continue
        parts = rel.parts
        if not parts:
            continue
        top = parts[0]
        if len(parts) == 1:
            # File at root; skip from subsystem rollup.
            continue
        buckets.setdefault(top, []).append((path, size))

    # Workspaces first (probed); then bare directories sorted by size desc.
    workspace_names = {w.name for w in workspaces}

    for w in workspaces:
        bucket = buckets.get(w.name, [])
        size = sum(s for _, s in bucket)
        manifests = _detect_manifests_at(w)
        stack = _classify_stack(manifests)
        fs = _probe_frameworks(w, sized) if manifests else FrameworkSignals()
        subsystems.append(
            Subsystem(
                path=f"{w.name}/",
                files=len(bucket),
                bytes=size,
                note=_subsystem_note(stack, fs),
                primary_stack=stack["languages"] + stack["frameworks"],
                framework_signals=fs,
            )
        )

    # Bare (non-workspace) top-level dirs, by size descending, top 8.
    bare = []
    for top, bucket in buckets.items():
        if top in workspace_names:
            continue
        size = sum(s for _, s in bucket)
        bare.append((top, len(bucket), size))
    bare.sort(key=lambda t: t[2], reverse=True)
    for top, count, size in bare[:8]:
        subsystems.append(
            Subsystem(
                path=f"{top}/",
                files=count,
                bytes=size,
                note="",
                primary_stack=[],
                framework_signals=FrameworkSignals(),
            )
        )

    return subsystems


def _subsystem_note(stack: dict, fs: FrameworkSignals) -> str:
    parts: list[str] = []
    if stack["languages"]:
        parts.append("/".join(stack["languages"]))
    if stack["frameworks"]:
        parts.append("(" + ", ".join(stack["frameworks"]) + ")")
    if fs.django:
        d = fs.django
        bits = []
        if d["url_patterns"]:
            bits.append(f"{d['url_patterns']} url patterns")
        if d["tasks"]:
            bits.append(f"{d['tasks']} task decorators")
        if d["management_commands"]:
            bits.append(f"{d['management_commands']} mgmt cmds")
        if bits:
            parts.append("[" + ", ".join(bits) + "]")
    if fs.nextjs:
        n = fs.nextjs
        bits = []
        if n["route_files"]:
            bits.append(f"{n['route_files']} routes")
        if n["api_routes"]:
            bits.append(f"{n['api_routes']} api routes")
        if bits:
            parts.append("[" + ", ".join(bits) + "]")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def _detect_entry_points(project: Path, files: list[Path] | None = None) -> list[dict]:
    out: list[dict] = []
    selected = None if files is None else {p.resolve() for p in files}
    for name, kind in _ENTRY_POINT_HINTS.items():
        candidate = project / name
        if not candidate.is_file():
            continue
        if selected is not None and candidate.resolve() not in selected:
            continue
        out.append({"path": name, "kind": kind})
    return out


# ---------------------------------------------------------------------------
# Hot files (delegate to hotpath)
# ---------------------------------------------------------------------------


def _build_hot_files(sized: list[tuple[Path, int]], project: Path) -> list[HotFile]:
    ranked = sorted(sized, key=lambda fs: fs[1], reverse=True)[:_HOT_FILES_TOP_N]
    out: list[HotFile] = []
    for path, size in ranked:
        try:
            rel = str(path.relative_to(project))
        except ValueError:
            rel = str(path)
        out.append(HotFile(path=rel, bytes=size))
    return out


# ---------------------------------------------------------------------------
# Risk pattern checks
# ---------------------------------------------------------------------------


def _check_risks(
    project: Path,
    sized: list[tuple[Path, int]],
    files: list[Path] | None = None,
) -> list[Risk]:
    risks: list[Risk] = []

    risks.extend(_risk_tracked_venv(project, sized))
    risks.extend(_risk_tracked_env_file(project, sized))
    risks.extend(_risk_multiple_env_templates(project, files))
    risks.extend(_risk_oversized_static_assets(project, sized))
    risks.extend(_risk_tracked_build_artifacts(project, files))

    return risks


def _risk_tracked_venv(project: Path, sized: list[tuple[Path, int]]) -> list[Risk]:
    found: dict[str, list[str]] = {}
    for path, _ in sized:
        try:
            rel = path.relative_to(project)
        except ValueError:
            continue
        parts = rel.parts
        if parts and parts[0] in _TRACKED_VENV_NAMES:
            found.setdefault(parts[0], []).append(str(rel))
    out: list[Risk] = []
    for venv_name, evidence in found.items():
        out.append(
            Risk(
                id="tracked-venv",
                severity="high",
                summary=f"Virtualenv `{venv_name}/` is tracked in git ({len(evidence)} files).",
                evidence=evidence[:5],
            )
        )
    return out


def _risk_tracked_env_file(project: Path, sized: list[tuple[Path, int]]) -> list[Risk]:
    for path, _ in sized:
        try:
            rel = path.relative_to(project)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) == 1 and parts[0] == ".env":
            return [
                Risk(
                    id="tracked-env-file",
                    severity="high",
                    summary="`.env` is tracked in git — likely contains secrets.",
                    evidence=[".env"],
                )
            ]
    return []


def _risk_multiple_env_templates(project: Path, files: list[Path] | None = None) -> list[Risk]:
    templates: list[str] = []
    selected = None if files is None else {p.resolve() for p in files}
    try:
        for child in project.iterdir():
            if child.is_file() and child.name.startswith(".env.") and child.name not in (".env.local",):
                if selected is not None and child.resolve() not in selected:
                    continue
                templates.append(child.name)
    except OSError:
        return []
    if len(templates) >= 3:
        return [
            Risk(
                id="multiple-env-templates",
                severity="medium",
                summary=f"{len(templates)} `.env.*` template variants at root — likely duplication.",
                evidence=sorted(templates),
            )
        ]
    return []


def _risk_oversized_static_assets(project: Path, sized: list[tuple[Path, int]]) -> list[Risk]:
    offenders: list[tuple[str, int]] = []
    for path, size in sized:
        if size < _OVERSIZED_ASSET_BYTES:
            continue
        if path.suffix.lower() not in _STATIC_ASSET_SUFFIXES:
            continue
        try:
            rel = path.relative_to(project)
        except ValueError:
            continue
        if not any(seg in rel.parts for seg in _STATIC_DIR_SEGMENTS):
            continue
        offenders.append((str(rel), size))
    if not offenders:
        return []
    offenders.sort(key=lambda t: t[1], reverse=True)
    evidence = [f"{path} ({size / (1024 * 1024):.2f} MB)" for path, size in offenders[:5]]
    return [
        Risk(
            id="oversized-static-asset",
            severity="medium",
            summary=f"{len(offenders)} static asset(s) ≥ 5 MB — likely need optimization.",
            evidence=evidence,
        )
    ]


def _risk_tracked_build_artifacts(project: Path, files: list[Path] | None = None) -> list[Risk]:
    """Detect when build / cache / vendor directories are tracked in git.

    Can't reuse the ``sized`` list — ``cli.hotpath._collect_files`` filters
    these directory names out by design (so the file-size scan doesn't get
    polluted by ``node_modules/`` etc.). Run an independent probe: prefer
    ``git ls-files`` when in a git repo (gitignored dirs won't appear, so
    any matches are genuinely tracked); fall back to an unfiltered walk
    that just checks for directory existence."""
    found: dict[str, int] = {}

    scoped = None if files is None else {p.resolve() for p in files}

    if (project / ".git").exists():
        # `git ls-files` skips gitignored paths, so any hits here are
        # tracked content under one of the suspect directory names.
        out_text = _git_run(project, ["ls-files"])
        if out_text is not None:
            for line in out_text.splitlines():
                if scoped is not None:
                    candidate = (project / line).resolve()
                    if candidate not in scoped:
                        continue
                parts = Path(line).parts
                for part in parts[:-1]:
                    if part in _TRACKED_BUILD_NAMES:
                        found[part] = found.get(part, 0) + 1
                        break
    else:
        # No git: best-effort directory-existence check. Walks the
        # project tree without applying the IGNORED_DIR_NAMES filter
        # (because that filter would skip the very dirs we're looking
        # for).
        if files is not None:
            for path in files:
                parts = path.parts
                for part in parts[:-1]:
                    if part in _TRACKED_BUILD_NAMES:
                        found[part] = found.get(part, 0) + 1
                        break
        else:
            for root, dirs, _ in os.walk(project):
                root_parts = Path(root).parts
                # Don't descend into VCS dirs.
                if ".git" in root_parts:
                    dirs[:] = []
                    continue
                for name in list(dirs):
                    if name in _TRACKED_BUILD_NAMES:
                        full = Path(root) / name
                        file_count = sum(1 for _ in full.rglob("*") if _.is_file())
                        if file_count > 0:
                            found[name] = found.get(name, 0) + file_count

    out: list[Risk] = []
    for name, count in sorted(found.items()):
        out.append(
            Risk(
                id="tracked-build-artifacts",
                severity="medium",
                summary=f"`{name}/` directories are tracked in git ({count} files).",
                evidence=[name],
            )
        )
    return out


# ---------------------------------------------------------------------------
# Stale doc heuristic
# ---------------------------------------------------------------------------


def _check_stale_docs(project: Path, files: list[Path] | None = None) -> list[StaleDoc]:
    """Header-date grep on Markdown files at top-level + under docs/.
    Conservative: only flags docs whose self-reported date is parseable
    as ISO YYYY-MM-DD and is older than ``_STALE_DOC_AGE_DAYS``."""
    if files is None:
        candidates: list[Path] = []
        for parent in (project, project / "docs"):
            if not parent.is_dir():
                continue
            try:
                for child in parent.iterdir():
                    if child.is_file() and child.suffix == ".md":
                        candidates.append(child)
            except OSError:
                continue
    else:
        candidates = [path for path in files if path.suffix == ".md" and (path.name.endswith(".md"))]

    today = datetime.now(timezone.utc).date()
    stale: list[StaleDoc] = []
    for path in candidates:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:500]
        except OSError:
            continue

        date_str = None
        evidence_line = None

        fm = _FRONTMATTER_DATE_RE.search(head)
        if fm:
            date_str = fm.group(1)
            evidence_line = f"frontmatter date: {date_str}"

        if date_str is None:
            for marker in _STALENESS_MARKERS:
                idx = head.find(marker)
                if idx == -1:
                    continue
                segment = head[idx : idx + 80]
                m = _ISO_DATE_RE.search(segment)
                if m:
                    date_str = m.group(1)
                    evidence_line = segment.split("\n", 1)[0].strip()
                    break

        if date_str is None:
            continue

        try:
            doc_date = datetime.fromisoformat(date_str).date()
        except ValueError:
            continue
        age_days = (today - doc_date).days
        if age_days < _STALE_DOC_AGE_DAYS:
            continue

        try:
            rel = str(path.relative_to(project))
        except ValueError:
            rel = str(path)
        stale.append(StaleDoc(path=rel, evidence=f"{evidence_line} ({age_days} days old)"))

    return stale


# ---------------------------------------------------------------------------
# Documentation intelligence
# ---------------------------------------------------------------------------


# Folder name patterns under docs/ that suggest active audit / cleanup
# infrastructure (vs. passive reference docs).
_AUDIT_FOLDER_PATTERNS = ("audit", "cleanup")

# RAG corpus filenames worth flagging by name (the directory itself is
# also a signal regardless of contents).
_RAG_CORPUS_FILENAMES = ("corpus.jsonl", "corpus.json", "index.json", "index.jsonl")

# Scale thresholds used in the strength classifier.
_DOC_INTEL_SCALE_HIGH_MARKDOWN = 200
_DOC_INTEL_SCALE_HIGH_HANDOFFS = 50
_DOC_INTEL_HANDOFF_SIGNAL_MIN = 5


def _inspect_documentation_intelligence(project: Path, files: list[Path] | None = None) -> DocumentationIntelligence:
    """Probe ``docs/`` and ``.rag/`` for evidence that the repo treats
    documentation as active context / memory infrastructure (embedded,
    retrieved, or injected at runtime) rather than passive reference
    material.

    All probes are filename / directory-existence based — no parsing.
    """
    docs_dir = project / "docs"

    if files is None:
        markdown_count = 0
        if docs_dir.is_dir():
            for _, dirs, doc_files in os.walk(docs_dir):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES]
                markdown_count += sum(1 for n in doc_files if n.endswith(".md"))

        handoffs_dir = docs_dir / "handoffs"
        handoff_count = 0
        if handoffs_dir.is_dir():
            try:
                handoff_count = sum(1 for p in handoffs_dir.glob("SESSION_*.md") if p.is_file())
            except OSError:
                handoff_count = 0

        anchor_docs: list[str] = []
        if docs_dir.is_dir():
            try:
                for path in sorted(docs_dir.glob("*_WHAT_IT_IS.md")):
                    if path.is_file():
                        anchor_docs.append(str(path.relative_to(project)))
                for path in sorted(docs_dir.glob("*_INVENTORY.md")):
                    if path.is_file():
                        anchor_docs.append(str(path.relative_to(project)))
            except OSError:
                pass

        audit_folders: list[str] = []
        if docs_dir.is_dir():
            try:
                for child in sorted(docs_dir.iterdir()):
                    if not child.is_dir():
                        continue
                    if any(pat in child.name.lower() for pat in _AUDIT_FOLDER_PATTERNS):
                        audit_folders.append(str(child.relative_to(project)))
            except OSError:
                pass

        process_docs_present = (
            (docs_dir / "docs-pattern").is_dir()
            or (docs_dir / "process").is_dir()
            or (docs_dir / "patterns").is_dir()
        )

        rag_dir = project / ".rag"
        rag_corpus_present = False
        rag_corpus_paths: list[str] = []
        if rag_dir.is_dir():
            try:
                for child in sorted(rag_dir.iterdir()):
                    if child.is_file() and (
                        child.name in _RAG_CORPUS_FILENAMES
                        or child.suffix in (".jsonl", ".json")
                    ):
                        rag_corpus_paths.append(str(child.relative_to(project)))
                rag_corpus_present = bool(rag_corpus_paths)
            except OSError:
                pass
    else:
        markdown_files = [path for path in files if path.suffix.lower() == ".md" and ("docs" in path.parts or path.parent == project)]
        markdown_count = len(markdown_files)
        handoff_count = sum(1 for p in markdown_files if "handoffs" in p.parts and p.name.startswith("SESSION_"))
        anchor_docs = [str(p.relative_to(project)) for p in markdown_files if p.name.endswith(("_WHAT_IT_IS.md", "_INVENTORY.md"))]
        audit_folders = sorted({str(p.parent.relative_to(project)) for p in markdown_files if any(pat in p.parent.name.lower() for pat in _AUDIT_FOLDER_PATTERNS)})
        process_docs_present = any(
            any(part in {"docs-pattern", "process", "patterns"} for part in p.parts)
            for p in files
        )
        rag_corpus_paths = [str(p.relative_to(project)) for p in files if p.parts and p.parts[0] == ".rag" and p.is_file() and (p.name in _RAG_CORPUS_FILENAMES or p.suffix in (".jsonl", ".json"))]
        rag_corpus_present = bool(rag_corpus_paths)

    strength = _classify_doc_intel(
        markdown_count=markdown_count,
        handoff_count=handoff_count,
        anchor_docs=anchor_docs,
        audit_folders=audit_folders,
        process_docs_present=process_docs_present,
        rag_corpus_present=rag_corpus_present,
    )

    return DocumentationIntelligence(
        markdown_file_count=markdown_count,
        session_handoff_count=handoff_count,
        anchor_docs=anchor_docs,
        audit_folders=audit_folders,
        process_docs_present=process_docs_present,
        rag_corpus_present=rag_corpus_present,
        rag_corpus_paths=rag_corpus_paths,
        strength=strength,
    )


def _filter_inspect_scope_files(
    project: Path,
    files: list[Path],
    scope: str,
    *,
    include_related: bool = False,
    include_history: bool = False,
) -> list[Path]:
    selected: list[Path] = []
    for path in files:
        if _inspect_scope_matches(
            project,
            path,
            scope,
            include_related=include_related,
            include_history=include_history,
        ):
            selected.append(path)
    return selected


def _inspect_file_is_live(path: Path, *, include_history: bool = False) -> bool:
    role = _inspect_path_role(path)
    if role == "generated":
        return False
    if include_history:
        return True
    return role == "active"


def _inspect_path_role(path: Path) -> str:
    rel = path.as_posix()
    lowered = rel.lower()
    if _is_verification_output(path):
        return "generated"
    history_markers = {"archive", "archives", "historical", "history", "legacy", "old", "handoff", "handoffs", "session", "sessions", "case-studies", "case_studies"}
    external_markers = {"external", "externals", "reference", "references", "third-party", "third_party", "vendor", "imported", "imported-reference"}
    parts = set(Path(rel).parts)
    if parts & history_markers or any(token in lowered for token in ("session_", "handoff", "case-study", "case_study", "old-session", "old_sessions")):
        return "historical"
    if parts & external_markers or any(token in lowered for token in ("external-project-docs", "external-docs", "imported-reference", "reference", "references")):
        return "external"
    return "active"


def _is_verification_output(path: Path) -> bool:
    lowered = path.as_posix().lower()
    return "docs/verification/" in lowered or lowered.endswith("docs/verification/verify_report.md")


def _inspect_scope_matches(
    project: Path,
    path: Path,
    scope: str,
    *,
    include_related: bool = False,
    include_history: bool = False,
) -> bool:
    try:
        rel = path.relative_to(project).as_posix()
    except ValueError:
        rel = path.as_posix()
    lowered = rel.lower()
    name = path.name
    role = _inspect_path_role(path)

    if role == "generated":
        return False
    if role in {"historical", "external"} and not include_history:
        return False

    if scope == "core":
        return lowered.startswith("core/")

    if scope == "frontend":
        return lowered.startswith("frontend/")

    if scope == "tests":
        return lowered.startswith("tests/") or lowered.startswith("core/tests/")

    if scope == "deployment":
        if name in {"Dockerfile", "Procfile"}:
            return True
        if lowered in {".env.example", ".env.railway"} or lowered.startswith("railway/"):
            return True
        return include_related and ("deploy" in lowered or "deployment" in lowered or "railway" in lowered)

    if scope == "celery":
        if lowered in {"procfile", "core/celery.py", "core/schedulers.py"}:
            return True
        if lowered.startswith("core/tasks") and path.suffix == ".py":
            return True
        if lowered.startswith("core/management/commands/") and "celery" in name.lower():
            return True
        if lowered == "docs/topics/celery-workers.md":
            return True
        if include_related:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            lower_text = text.lower()
            return "celery" in lower_text or "periodictask" in lower_text or "beat_schedule" in lower_text
        if include_history:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            lower_text = text.lower()
            return "celery" in lower_text or "periodictask" in lower_text or "beat_schedule" in lower_text
        return False

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        text = ""
    lower_text = text.lower()

    if scope == "agents":
        if lowered.startswith("core/agents/") or lowered.startswith("agents/"):
            return True
        if lowered in {"docs/topics/agent-system.md", "docs/agents.md"}:
            return True
        if include_related:
            return "agent_map" in lower_text or "agent registry" in lower_text or "persistence" in lower_text
        if include_history:
            return "agent_map" in lower_text or "agent registry" in lower_text
        return False

    if scope == "spiders":
        if lowered.startswith("ai_core/spiders/") or lowered.startswith("spiders/"):
            return True
        if lowered in {"docs/topics/spider-network.md", "docs/spiders.md"}:
            return True
        if include_related:
            if lowered.startswith("frontend/"):
                return True
            return "spider registry" in lower_text or "spiderdata" in lower_text or "frontend" in lower_text
        if include_history:
            return "spider registry" in lower_text or "spiderdata" in lower_text
        return False

    if scope == "docs-rag":
        if lowered.startswith("docs/") or lowered.startswith(".rag/"):
            if any(seg in lowered for seg in ("static/", "assets/", "mobile/", "images/")):
                return include_related
            return True
        if include_related:
            return "rag" in lower_text or "corpus" in lower_text or "context" in lower_text or "index" in lowered
        if include_history:
            return "rag" in lower_text or "corpus" in lower_text or "context" in lower_text
        return False

    return False


def _classify_doc_intel(
    *,
    markdown_count: int,
    handoff_count: int,
    anchor_docs: list[str],
    audit_folders: list[str],
    process_docs_present: bool,
    rag_corpus_present: bool,
) -> str:
    """Strength classifier (deterministic).

    Counts distinct *types* of active-context signal (5 categories), then
    combines with scale (markdown count / handoff count) to produce one
    of ``none`` / ``low`` / ``medium`` / ``high``."""
    if markdown_count == 0:
        return "none"

    signal_count = sum([
        handoff_count >= _DOC_INTEL_HANDOFF_SIGNAL_MIN,
        bool(anchor_docs),
        bool(audit_folders),
        rag_corpus_present,
        process_docs_present,
    ])

    scale_high = (
        markdown_count >= _DOC_INTEL_SCALE_HIGH_MARKDOWN
        or handoff_count >= _DOC_INTEL_SCALE_HIGH_HANDOFFS
    )

    if signal_count == 0:
        return "low"
    if signal_count >= 2 and scale_high:
        return "high"
    if signal_count >= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


_RECOMMENDATIONS_MAX = 5


def _build_recommendations(
    *,
    project: Path,
    risks: list[Risk],
    hot_files: list[HotFile],
    stale_docs: list[StaleDoc],
    root_framework: FrameworkSignals,
    subsystems: list[Subsystem],
    sized: list[tuple[Path, int]],
    doc_intel: DocumentationIntelligence,
) -> list[Recommendation]:
    """Deterministic recommendation rules. Each rule fires only when its
    triggering signal is present; a rule that fires emits exactly one
    Recommendation. Rules are evaluated in priority order; the final
    list is capped at ``_RECOMMENDATIONS_MAX``.

    Recommendations are *not* commands — they're suggestions for the
    human or agent to consider. Each carries a stable ``id`` so a
    future override store can target it.
    """
    out: list[Recommendation] = []

    # 0. Documentation intelligence — fires before risk recs because a
    #    "do not delete docs without checking" warning has to land
    #    early enough to influence what other cleanup PRs touch.
    if doc_intel.strength == "high":
        out.append(Recommendation(
            id="review-docs-context-first",
            suggestion=(
                "Review the docs context layer before deleting, "
                "archiving, or refactoring documentation."
            ),
            why=(
                "Large structured docs systems may be embedded / "
                "retrieved by AI runtime workflows. Detected: "
                f"{doc_intel.markdown_file_count} markdown files under "
                f"docs/, {doc_intel.session_handoff_count} session "
                f"handoffs"
                + (", RAG corpus present" if doc_intel.rag_corpus_present else "")
                + "."
            ),
            confidence="high",
        ))

    # 1. High-severity risks dominate. Each gets its own targeted rec
    #    with a stable id derived from the risk id.
    for risk in risks:
        if risk.severity != "high":
            continue
        if risk.id == "tracked-venv":
            out.append(Recommendation(
                id="cleanup-tracked-venv",
                suggestion=(
                    "Run a targeted cleanup audit on the tracked virtualenv: "
                    "untrack with `git rm -r --cached <venv-dir>/` and add "
                    "the directory to `.gitignore`."
                ),
                why=risk.summary,
                confidence="high",
            ))
        elif risk.id == "tracked-env-file":
            out.append(Recommendation(
                id="rotate-and-untrack-env",
                suggestion=(
                    "Treat any tracked `.env` as compromised: rotate its "
                    "secrets, then untrack with "
                    "`git rm --cached .env` and gitignore the path."
                ),
                why=risk.summary,
                confidence="high",
            ))
        else:
            # Generic high-severity fallback, in case a future risk type
            # lands without a tailored recommendation.
            out.append(Recommendation(
                id=f"triage-{risk.id}",
                suggestion=f"Triage the high-severity risk `{risk.id}` before lower-priority work.",
                why=risk.summary,
                confidence="high",
            ))

    # 2. Audit workspace missing — gate on the project being substantive
    #    enough to be worth auditing (avoid noise on empty / scratch
    #    directories).
    audit_v1 = project / "docs" / "audit" / "AUDIT_V1.md"
    worth_auditing = (
        len(risks) > 0
        or not root_framework.is_empty()
        or any(s.framework_signals.django or s.framework_signals.nextjs for s in subsystems)
        or len(sized) > 100
    )
    if not audit_v1.is_file() and worth_auditing:
        out.append(Recommendation(
            id="scaffold-audit-workspace",
            suggestion=(
                "Consider running `context-kit audit --write` to scaffold "
                "an audit workspace under `docs/audit/` (paste-target for "
                "AUDIT_V1.md + a CLEANUP_PLAN.md template)."
            ),
            why=(
                "No `docs/audit/AUDIT_V1.md` found and the repo has signals "
                "worth auditing — scaffolding the workspace is a low-cost "
                "first step toward a P0/P1/P2 cleanup loop."
            ),
            confidence="medium",
        ))

    # 3. Multiple env templates — duplication review, not high severity
    #    but easy to fix and easy to validate.
    env_template_risk = next((r for r in risks if r.id == "multiple-env-templates"), None)
    if env_template_risk is not None:
        out.append(Recommendation(
            id="consolidate-env-templates",
            suggestion=(
                "Review the `.env.*` template variants and consolidate. "
                "Two is usually enough: `.env.example` (canonical local) "
                "and `.env.production.example` (or single deploy variant)."
            ),
            why=env_template_risk.summary,
            confidence="medium",
        ))

    # 4. Hot files / oversized assets — `hotpath` is the right next call
    #    to get the full leaderboard with thresholds and warnings. Only
    #    suggest when at least one file is multi-MB; otherwise the
    #    suggestion is noise.
    biggest = hot_files[0].bytes if hot_files else 0
    if biggest >= 1024 * 1024:  # ≥ 1 MB
        out.append(Recommendation(
            id="run-hotpath-leaderboard",
            suggestion=(
                "Consider running `context-kit hotpath` for the full "
                "file-size leaderboard with thresholds and warnings."
            ),
            why=(
                f"Largest tracked file is {_human_bytes(biggest)} "
                f"(`{hot_files[0].path}`); a full leaderboard helps "
                "prioritize what to optimize, untrack, or split."
            ),
            confidence="medium",
        ))

    # 5. Stale-doc heuristic — low confidence; the heuristic only catches
    #    ISO-formatted self-reported dates older than 30 days.
    if stale_docs:
        first = stale_docs[0]
        out.append(Recommendation(
            id="review-stale-docs",
            suggestion=(
                "Review the doc(s) flagged under \"Possibly stale docs\" — "
                "self-reported dates suggest they may be out of date."
            ),
            why=(
                f"{len(stale_docs)} doc(s) carry header dates older than "
                f"30 days (e.g. `{first.path}` — {first.evidence})."
            ),
            confidence="low",
        ))

    # 6. Multi-stack / monorepo hint — low-confidence call to break the
    #    audit into per-subsystem PRs rather than one big sweep. Only
    #    when at least two subsystems carry their own framework signals.
    framework_workspaces = sum(
        1
        for s in subsystems
        if (s.framework_signals.django or s.framework_signals.nextjs)
    )
    if framework_workspaces >= 2:
        out.append(Recommendation(
            id="consider-per-subsystem-audit",
            suggestion=(
                "Consider auditing each workspace child as its own PR "
                "rather than a single sweep — the framework signals "
                "differ enough that one cleanup plan won't fit all."
            ),
            why=(
                f"{framework_workspaces} workspace children carry "
                "distinct framework signals; mixing their cleanup tasks "
                "in one PR tends to balloon scope."
            ),
            confidence="low",
        ))

    return out[:_RECOMMENDATIONS_MAX]


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _render_text(r: InspectionResult) -> str:
    lines: list[str] = []
    lines.append("=== CONTEXT-KIT INSPECT ===")
    lines.append(f"Repo:           {r.repo}")
    lines.append(f"Path:           {r.path}")
    if r.scope is not None:
        lines.append(f"Scope:          {r.scope}")
        lines.append(f"Scope mode:     {'related' if r.include_related else 'strict'}")
    if r.head:
        lines.append(f"HEAD:           {r.head['sha']} (branch: {r.head['branch']})")
    else:
        lines.append("HEAD:           (not a git repo)")
    lines.append(f"Tracked files:  {r.counts['tracked_files']:,}")
    lines.append(f"Total size:     {_human_bytes(r.counts['total_bytes'])}")
    lines.append("")

    lines.append("## Primary stack")
    ps = r.primary_stack
    if ps["manifests"]:
        langs = ", ".join(ps["languages"]) or "(unknown)"
        frameworks = (" + " + ", ".join(ps["frameworks"])) if ps["frameworks"] else ""
        lines.append(f"  Languages: {langs}{frameworks}")
        lines.append(f"  Manifests: {', '.join(ps['manifests'])}")
        lines.append(f"  Confidence: {ps['confidence']}")
    else:
        lines.append("  (no manifests detected at root)")
    lines.append("")

    if r.subsystems:
        lines.append("## Subsystems")
        for s in r.subsystems:
            note = f"  {s.note}" if s.note else ""
            lines.append(f"  {s.path:<24} {s.files:>5} files  {_human_bytes(s.bytes):>9}{note}")
        lines.append("")

    if r.entry_points:
        lines.append("## Entry points")
        for ep in r.entry_points:
            lines.append(f"  {ep['path']:<24} {ep['kind']}")
        lines.append("")

    if not r.framework_signals.is_empty():
        lines.append("## Framework signals (root)")
        if r.framework_signals.django:
            d = r.framework_signals.django
            lines.append(
                f"  Django:    apps={d['apps']} models={d['model_files']} "
                f"url_patterns={d['url_patterns']} tasks={d['tasks']} "
                f"mgmt_commands={d['management_commands']} view_files={d['view_files']}"
            )
        if r.framework_signals.nextjs:
            n = r.framework_signals.nextjs
            lines.append(
                f"  Next.js:   route_files={n['route_files']} api_routes={n['api_routes']}"
            )
        lines.append("")

    if r.hot_files:
        lines.append(f"## Hot files (top {len(r.hot_files)}; full list: context-kit hotpath)")
        for hf in r.hot_files:
            lines.append(f"  {_human_bytes(hf.bytes):>9}  {hf.path}")
        lines.append("")

    if r.risks:
        lines.append("## Risk areas")
        for risk in r.risks:
            sev = {"high": "!", "medium": "*", "low": "·"}.get(risk.severity, "·")
            lines.append(f"  {sev} [{risk.id}] {risk.summary}")
            for ev in risk.evidence[:3]:
                lines.append(f"      - {ev}")
        lines.append("")

    if r.stale_docs:
        lines.append("## Possibly stale docs")
        for sd in r.stale_docs:
            lines.append(f"  {sd.path:<48} {sd.evidence}")
        lines.append("")

    if r.documentation_intelligence.strength in ("medium", "high"):
        di = r.documentation_intelligence
        lines.append("## Documentation Intelligence")
        lines.append(f"  Markdown files in docs/:    {di.markdown_file_count:,}")
        lines.append(f"  Session handoffs:           {di.session_handoff_count:,}")
        if di.anchor_docs:
            lines.append(
                f"  Anchor docs:                {', '.join(p.split('/')[-1] for p in di.anchor_docs)}"
            )
        if di.audit_folders:
            lines.append(
                f"  Audit/cleanup folders:      {', '.join(p.split('/')[-1] + '/' for p in di.audit_folders)}"
            )
        if di.process_docs_present:
            lines.append("  Process docs:               docs/docs-pattern/ (or similar)")
        if di.rag_corpus_present:
            lines.append(
                f"  RAG corpus:                 {', '.join(di.rag_corpus_paths) or '.rag/'}"
            )
        lines.append(f"  Strength:                   {di.strength}")
        lines.append("")
        lines.append(
            "  This repository appears to use documentation as an "
            "active context/memory layer."
        )
        lines.append("")
        lines.append(
            "  ! Caution: do not treat docs/ as disposable clutter "
            "without checking whether"
        )
        lines.append(
            "    docs are embedded, retrieved, or injected at runtime."
        )
        lines.append("")

    if r.recommendations:
        lines.append("## Recommended next moves")
        lines.append(
            "  Deterministic suggestions based on detected signals. "
            "Override or ignore as needed."
        )
        for i, rec in enumerate(r.recommendations, 1):
            lines.append(f"  {i}. [{rec.confidence}] {rec.suggestion}")
            lines.append(f"     why: {rec.why}")
            lines.append(f"     id:  {rec.id}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    if n < 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MB"
    return f"{n / (1024 * 1024 * 1024):.2f} GB"


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


def _to_json(r: InspectionResult) -> dict:
    return {
        "repo": r.repo,
        "path": r.path,
        "scope": r.scope,
        "include_related": r.include_related,
        "include_history": r.include_history,
        "head": r.head,
        "counts": r.counts,
        "primary_stack": r.primary_stack,
        "subsystems": [
            {
                "path": s.path,
                "files": s.files,
                "bytes": s.bytes,
                "note": s.note,
                "primary_stack": s.primary_stack,
                "framework_signals": {
                    "django": s.framework_signals.django,
                    "nextjs": s.framework_signals.nextjs,
                },
            }
            for s in r.subsystems
        ],
        "entry_points": r.entry_points,
        "framework_signals": {
            "django": r.framework_signals.django,
            "nextjs": r.framework_signals.nextjs,
        },
        "hot_files": [asdict(hf) for hf in r.hot_files],
        "risks": [asdict(rk) for rk in r.risks],
        "stale_docs": [asdict(sd) for sd in r.stale_docs],
        "documentation_intelligence": asdict(r.documentation_intelligence),
        "recommendations": [asdict(rc) for rc in r.recommendations],
    }
