"""context-kit `behavior` subcommand: behavioral risk map.

This is a read-only audit scaffold. It does not claim correctness; it
only identifies files that *look* behaviorally risky by simple filename /
line-text probes: orchestration size, task/scheduler entrypoints, registry
maps, dynamic imports, dispatch/router functions, database writes,
external API calls, filesystem writes, subprocess / shell execution,
broad exception swallowing, and TODO/FIXME markers.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cli.hotpath import _collect_files, _with_sizes
from cli.inspect import _INSPECT_SCOPES, _inspect_scope_matches


_RISK_ORDER = (
    "large_orchestration",
    "entrypoint",
    "task_or_scheduler",
    "registry_or_dispatch",
    "dynamic_import_or_getattr",
    "state_mutation",
    "db_write_or_transaction",
    "external_api",
    "filesystem_write",
    "subprocess_or_shell",
    "broad_exception_swallow",
    "todo_or_temporary",
)

_TASK_RE = re.compile(r"(?i)(@shared_task\b|@(?:app|celery(?:_app)?)\.task\b|beat_schedule\b|PeriodicTask\b|sync_celery_schedules\b)")
_REGISTRY_RE = re.compile(r"(?i)\b(AGENT_MAP|agent\s+map|registry|tool[_\s-]?registry|router|dispatch|dispatcher|tool[_\s-]?dispatch|route[_\s-]?map)\b")
_DYNAMIC_RE = re.compile(r"(?i)\b(importlib|import_module|__import__|getattr\s*\(|setattr\s*\()")
_DB_RE = re.compile(
    r"(?i)(transaction\.atomic|\.save\s*\(|\.delete\s*\(|\.bulk_create\s*\(|\.update_or_create\s*\(|\.create\s*\(|\.update\s*\(|\.objects\.(?:create|update|get_or_create|update_or_create)|\.execute\s*\()"
)
_STATE_MUTATION_RE = re.compile(
    r"(?i)(^\s*global\s+\w+\b|^\s*[A-Z_][A-Z0-9_]*\s*=\s*(?:\{\}|\[\]|set\(\)|dict\(\)|list\(\)|\{.*\}|\[.*\])\s*$|^\s*[A-Za-z_][A-Za-z0-9_]*(?:cache|registry|singleton|state)\w*\s*=\s*.+)"
)
_API_RE = re.compile(r"(?i)\b(requests|httpx|aiohttp|urllib\.request|urllib3|openai|fetch\s*\()\b")
_FS_RE = re.compile(
    r"(?i)(\.write_text\s*\(|\.write_bytes\s*\(|open\s*\(|\.touch\s*\(|mkdir\s*\(|shutil\.(?:copy|copy2|move|rmtree)\s*\()"
)
_SUBPROCESS_RE = re.compile(r"(?i)(subprocess\.|os\.system\s*\(|shell\s*=\s*True|Popen\s*\(|run\s*\()")
_BROAD_EXCEPT_RE = re.compile(r"(?i)^(?:\s*except\s*:|\s*except\s+(?:Exception|BaseException)\b)")
_TODO_RE = re.compile(r"(?i)\b(TODO|FIXME|HACK|TEMP|TEMPORARY|XXX)\b")
_MAIN_RE = re.compile(r"(?i)\bdef\s+main\s*\(")
_HANDLE_RE = re.compile(r"(?i)\bdef\s+handle\s*\(")
_DISPATCH_DEF_RE = re.compile(r"(?i)\bdef\s+(?:dispatch|route|router|controller)\w*\s*\(")
_LARGE_FILE_LINE_THRESHOLD = 220
_LARGE_FILE_BYTES_THRESHOLD = 12_000
_DISCLAIMER = "This is a heuristic risk map, not a correctness audit."


@dataclass
class BehaviorFile:
    path: str
    size_bytes: int
    risk_score: int
    entrypoint: bool = False
    categories: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class BehaviorRecommendation:
    id: str
    suggestion: str
    why: str
    confidence: str


@dataclass
class BehaviorReport:
    repo: str
    path: str
    scope: str | None
    disclaimer: str
    scoring: str
    summary: dict
    risk_categories: dict[str, int]
    entrypoints: int
    files: list[BehaviorFile]
    top_files: list[BehaviorFile]
    recommendations: list[BehaviorRecommendation]


def run_behavior(args: argparse.Namespace) -> int:
    project = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    scope = getattr(args, "scope", None)
    if scope is not None and scope not in _INSPECT_SCOPES:
        print(f"context-kit: unknown behavior scope `{scope}`. Valid scopes: {', '.join(_INSPECT_SCOPES)}.")
        return 2

    report = collect_behavior(project, scope=scope)
    if getattr(args, "json", False):
        print(json.dumps(_to_json(report), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 0


def collect_behavior(project: Path, *, scope: str | None = None) -> BehaviorReport:
    files = _collect_files(project)[0]
    if scope is not None:
        files = [path for path in files if _inspect_scope_matches(project, path, scope)]

    sized = _with_sizes(files)
    risky_files: list[BehaviorFile] = []
    category_counts: Counter[str] = Counter()
    entrypoint_count = 0

    for path, size in sized:
        categories, evidence, entrypoint = _scan_behavior_file(path)
        if not categories:
            if not entrypoint:
                continue
        categories = sorted(set(categories), key=_risk_sort_key)
        if _looks_like_large_orchestration(path, size, categories):
            categories = sorted(set(categories) | {"large_orchestration"}, key=_risk_sort_key)
            evidence.append(f"size={size} bytes suggests orchestration surface")
        if entrypoint:
            categories = sorted(set(categories) | {"entrypoint"}, key=_risk_sort_key)
            entrypoint_count += 1
        risky_files.append(
            BehaviorFile(
                path=_rel(project, path),
                size_bytes=size,
                risk_score=len(categories),
                entrypoint=entrypoint,
                categories=categories,
                evidence=_dedupe(evidence)[:5],
            )
        )
        for category in categories:
            category_counts[category] += 1

    risky_files.sort(key=lambda item: (item.risk_score, item.size_bytes, item.path), reverse=True)
    top_files = risky_files[:5]
    recommendations = _recommendations(scope=scope, files=top_files, counts=category_counts)
    summary = {
        "total_files_scanned": len(sized),
        "files_with_signals": len(risky_files),
        "entrypoint_files": entrypoint_count,
        "top_files_count": len(top_files),
        "top_signal_categories": len(category_counts),
    }
    return BehaviorReport(
        repo=project.name,
        path=str(project),
        scope=scope,
        summary=summary,
        risk_categories=dict(sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))),
        entrypoints=entrypoint_count,
        files=risky_files,
        top_files=top_files,
        recommendations=recommendations,
        disclaimer=_DISCLAIMER,
        scoring="risk_score is the number of distinct risk categories detected for a file",
    )


def _scan_behavior_file(path: Path) -> tuple[list[str], list[str], bool]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return [], [], False

    categories: set[str] = set()
    evidence: list[str] = []
    entrypoint = _is_entrypoint_file(path, text)

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        matched: list[str] = []
        if _TASK_RE.search(line):
            matched.append("task_or_scheduler")
        if _REGISTRY_RE.search(line):
            matched.append("registry_or_dispatch")
        if _DYNAMIC_RE.search(line):
            matched.append("dynamic_import_or_getattr")
        if _DB_RE.search(line):
            matched.append("db_write_or_transaction")
        if _STATE_MUTATION_RE.search(line):
            matched.append("state_mutation")
        if _API_RE.search(line):
            matched.append("external_api")
        if _FS_RE.search(line):
            matched.append("filesystem_write")
        if _SUBPROCESS_RE.search(line):
            matched.append("subprocess_or_shell")
        if _BROAD_EXCEPT_RE.search(line):
            matched.append("broad_exception_swallow")
        if _TODO_RE.search(line):
            matched.append("todo_or_temporary")
        if matched:
            for category in matched:
                categories.add(category)
            evidence.append(f"{line_no}: {_trim(line)}")

    return list(categories), evidence, entrypoint


def _is_entrypoint_file(path: Path, text: str) -> bool:
    lowered = path.as_posix().lower()
    name = path.name.lower()
    if name == "manage.py":
        return True
    if name == "procfile":
        return True
    if lowered.startswith("core/management/commands/"):
        return True
    if lowered.startswith("management/commands/"):
        return True
    if "celery" in lowered and (name.endswith(".py") or "worker" in lowered):
        if _TASK_RE.search(text):
            return True
    if _MAIN_RE.search(text) or _HANDLE_RE.search(text) or _DISPATCH_DEF_RE.search(text):
        return True
    if any(token in lowered for token in ("router", "controller", "view", "views", "route")) and (".py" in lowered or lowered.endswith((".js", ".ts", ".tsx", ".jsx"))):
        return True
    return False


def _looks_like_large_orchestration(path: Path, size_bytes: int, categories: list[str]) -> bool:
    if not categories:
        return False
    if size_bytes < _LARGE_FILE_BYTES_THRESHOLD:
        return False
    if not any(category in categories for category in _RISK_ORDER if category != "todo_or_temporary"):
        return False
    lowered = path.as_posix().lower()
    return any(token in lowered for token in ("task", "scheduler", "dispatch", "router", "orchestrator", "bridge", "sync", "manage", "command"))


def _recommendations(*, scope: str | None, files: list[BehaviorFile], counts: Counter[str]) -> list[BehaviorRecommendation]:
    if not files:
        target = scope or "core"
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion=f"Start with `{target}` and inspect the largest entrypoint or orchestration file first.",
                why="No behavioral signals were found in the scanned files, so the safest next audit target is the active subsystem scope.",
                confidence="low",
            )
        ]

    dominant = next((category for category, _ in counts.most_common(1)), None)
    if dominant == "task_or_scheduler":
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion="Audit Celery/task/scheduler entrypoints first.",
                why="The scan found task or scheduler surfaces, which often hide runtime side effects and scheduling drift.",
                confidence="high",
            )
        ]
    if dominant == "registry_or_dispatch":
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion="Audit registry and dispatch/router code first.",
                why="The scan found registry or dispatch surfaces, which tend to concentrate dynamic routing and behavior branching.",
                confidence="high",
            )
        ]
    if dominant == "db_write_or_transaction":
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion="Audit database write and transaction boundaries first.",
                why="The scan found write-heavy paths, which are the highest-risk places for silent data changes.",
                confidence="medium",
            )
        ]
    if dominant == "subprocess_or_shell":
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion="Audit subprocess and shell execution paths first.",
                why="The scan found command execution surfaces, which are riskier than pure read-only code paths.",
                confidence="medium",
            )
        ]
    if dominant == "external_api":
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion="Audit external API integration paths first.",
                why="The scan found outbound network calls, which are common failure and drift points.",
                confidence="medium",
            )
        ]
    if dominant == "filesystem_write":
        return [
            BehaviorRecommendation(
                id="behavior-next-target",
                suggestion="Audit filesystem write paths first.",
                why="The scan found file mutation surfaces, which can change runtime state and generated outputs.",
                confidence="medium",
            )
        ]
    return [
        BehaviorRecommendation(
            id="behavior-next-target",
            suggestion=f"Inspect `{files[0].path}` first.",
            why="It is the highest-scoring behavioral risk surface in the current scan.",
            confidence="medium",
        )
    ]


def _render_text(report: BehaviorReport) -> str:
    lines = [
        "=== CONTEXT-KIT BEHAVIOR ===",
        f"Repo:           {report.repo}",
        f"Path:           {report.path}",
        "",
        report.disclaimer,
    ]
    if report.scope is not None:
        lines.append(f"Scope:          {report.scope}")
        lines.append("Scope mode:     strict")
    lines.append(report.scoring)
    lines.extend(["", "## Summary"])
    lines.append(f"  Files scanned:       {report.summary['total_files_scanned']:,}")
    lines.append(f"  Files with signals:  {report.summary['files_with_signals']:,}")
    lines.append(f"  Entrypoint files:    {report.summary['entrypoint_files']:,}")
    lines.append(f"  Risk categories:     {report.summary['top_signal_categories']:,}")
    lines.append("")

    lines.append("## Risk categories")
    if not report.risk_categories:
        lines.append("  _No behavioral risk signals found._")
    else:
        for name, count in report.risk_categories.items():
            lines.append(f"  {name:<28} {count:>5}")

    lines.append("")
    lines.append("## Top risky files")
    if not report.top_files:
        lines.append("  _No risky files found._")
    else:
        for item in report.top_files:
            lines.append(f"  {item.risk_score:>3}  {item.path}  [{', '.join(item.categories)}]")
            for evidence in item.evidence[:2]:
                lines.append(f"       - {evidence}")

    lines.append("")
    lines.append("## Recommended next audit target")
    for rec in report.recommendations[:1]:
        lines.append(f"  {rec.suggestion}")
        lines.append(f"  Why: {rec.why}")

    return "\n".join(lines).rstrip() + "\n"


def _risk_sort_key(name: str) -> int:
    try:
        return _RISK_ORDER.index(name)
    except ValueError:
        return len(_RISK_ORDER)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _trim(text: str, limit: int = 120) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _rel(project: Path, path: Path) -> str:
    # Emit POSIX-style forward slashes so machine-readable output
    # (JSON ``top_files``, evidence strings, deterministic markdown) is
    # identical across Linux, macOS, and Windows. Filesystem operations
    # still use native paths — only the *emitted* string is normalized.
    try:
        return path.relative_to(project).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _to_json(report: BehaviorReport) -> dict:
    return {
        "repo": report.repo,
        "path": report.path,
        "scope": report.scope,
        "disclaimer": report.disclaimer,
        "scoring": report.scoring,
        "summary": report.summary,
        "risk_categories": report.risk_categories,
        "entrypoints": report.entrypoints,
        "files": [asdict(item) for item in report.files],
        "top_files": [asdict(item) for item in report.top_files],
        "recommendations": [asdict(item) for item in report.recommendations],
    }
