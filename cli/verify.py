"""context-kit `verify` subcommand: lightweight claim truth/status checks.

Deterministic, read-only by default, and intentionally conservative.
The verifier does not parse full ASTs and does not invoke any LLMs.
It looks for a small set of high-value claims that can be checked with
simple text / file / git probes:

- Django settings module ownership
- Celery beat schedule ownership
- tracked generated artifacts in git
- docs-only count claims for a few common repo metrics

The report is designed to be readable in terminal form and also to be
written into a managed markdown block at
``docs/verification/VERIFY_REPORT.md``.
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

START_MARKER = "<!-- context-kit:verification:start -->"
END_MARKER = "<!-- context-kit:verification:end -->"
DEFAULT_REPORT_REL = Path("docs/verification/VERIFY_REPORT.md")
SCHEMA_VERSION = 1
_IMPLEMENTATION_FILE = Path(__file__).resolve()

_INTRO = (
    "\n\n<!-- The block below was added by `context-kit verify --write`. -->\n"
    "<!-- It will be regenerated on every `--write`. Edit outside the markers freely. -->\n\n"
)

_STATUS_ORDER = ("VERIFIED", "DOC_ONLY", "CONFLICT", "UNKNOWN")
_TRACKED_ARTIFACT_PREFIXES = (
    "venv/",
    ".venv/",
    "venv_ml/",
    "frontend/dist/",
    "dist/",
    "build/",
    "node_modules/",
)
_DOC_COUNT_PATTERNS = {
    "agents": re.compile(r"\b(\d+)\s+agents?\b", re.IGNORECASE),
    "spiders": re.compile(r"\b(\d+)\s+spiders?\b", re.IGNORECASE),
    "apis": re.compile(r"\b(\d+)\s+apis?\b", re.IGNORECASE),
    "frontend pages": re.compile(r"\b(\d+)\s+frontend\s+pages?\b", re.IGNORECASE),
}
_DJANGO_SETTINGS_RE = re.compile(r"DJANGO_SETTINGS_MODULE", re.IGNORECASE)
_BEAT_RE = re.compile(
    r"(?i)\b(beat_schedule|celery beat|celery beat schedule|CELERY_BEAT_SCHEDULE|CELERY_BEAT_SCHEDULER|app\.conf\.beat_schedule)\b"
)
_PATH_OR_MODULE_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|pyi|toml|yaml|yml|json|md))|(?P<module>\b[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w+)+\b)"
)
_DJANGO_SETTINGS_VALUE_RE = re.compile(
    r"DJANGO_SETTINGS_MODULE\s*(?:=|:)\s*['\"]?([A-Za-z_][\w.]*?)['\"]?(?:\s|$|[,#])"
)


@dataclass
class Finding:
    id: str
    title: str
    status: str
    category: str
    evidence: list[str] = field(default_factory=list)
    details: str = ""
    recommendation: str = ""


@dataclass
class VerificationReport:
    repo: str
    generated_at: str
    summary: dict
    findings: list[Finding]


def run_verify(args: argparse.Namespace) -> int:
    project = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    report = collect_verification(project)

    if getattr(args, "write", False):
        write_verification_report(project, report)

    if getattr(args, "json", False):
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_human_report(report))
    return 0


def collect_verification(project: Path) -> VerificationReport:
    files = _project_files(project)
    docs_files = [p for p in files if _is_doc_file(p)]
    env_files = [p for p in files if _is_env_file(p)]
    python_files = [p for p in files if p.suffix == ".py"]

    findings: list[Finding] = []
    findings.extend(_verify_django_settings(project, docs_files + env_files + python_files))
    findings.extend(_verify_celery_beat(project, docs_files + env_files + python_files))
    findings.extend(_verify_tracked_artifacts(project))
    findings.extend(_verify_doc_count_claims(project, docs_files))

    findings.sort(key=lambda f: (_STATUS_ORDER.index(f.status), f.category, f.title))

    summary = {
        "total": len(findings),
        "by_status": {status: sum(1 for finding in findings if finding.status == status) for status in _STATUS_ORDER},
    }
    return VerificationReport(
        repo=str(project),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        summary=summary,
        findings=findings,
    )


def render_human_report(report: VerificationReport) -> str:
    lines = [
        "# Verification Report",
        "",
        f"- Repo: `{report.repo}`",
        f"- Generated at: `{report.generated_at}`",
        "",
        "## Summary",
        "",
    ]
    for status in _STATUS_ORDER:
        lines.append(f"- {status}: {report.summary['by_status'].get(status, 0)}")

    grouped: dict[str, list[Finding]] = {status: [] for status in _STATUS_ORDER}
    for finding in report.findings:
        grouped.setdefault(finding.status, []).append(finding)

    for status in _STATUS_ORDER:
        lines.extend(["", f"## {status}"])
        if not grouped.get(status):
            lines.append("")
            lines.append("_No findings._")
            continue
        for finding in grouped[status]:
            lines.extend([
                "",
                f"### {finding.title}",
                f"- Status: `{finding.status}`",
                f"- Category: `{finding.category}`",
                "- Evidence:",
            ])
            if finding.evidence:
                for item in finding.evidence:
                    lines.append(f"  - {item}")
            else:
                lines.append("  - None")
            lines.extend([
                f"- Details: {finding.details}",
                f"- Recommended next action: {finding.recommendation}",
            ])
    lines.append("")
    return "\n".join(lines)


def write_verification_report(project: Path, report: VerificationReport, report_path: Path | None = None) -> tuple[Path, str]:
    if report_path is None:
        report_path = project / DEFAULT_REPORT_REL

    block_body = render_human_report(report)
    new_block = f"{START_MARKER}\n{block_body}\n{END_MARKER}"

    if not report_path.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            "# Verification Report\n"
            "\n"
            "This file is partly auto-generated. Everything between the markers below is regenerated by "
            "`context-kit verify --write`.\n"
            f"{new_block}\n",
            encoding="utf-8",
        )
        return report_path, "created"

    existing = report_path.read_text(encoding="utf-8")
    if START_MARKER in existing and END_MARKER in existing:
        report_path.write_text(_replace_block(existing, new_block), encoding="utf-8")
        return report_path, "updated"

    sep = "" if existing.endswith("\n") else "\n"
    report_path.write_text(existing + sep + _INTRO + new_block + "\n", encoding="utf-8")
    return report_path, "appended-block"


def _replace_block(existing: str, new_block: str) -> str:
    pre, _, after_start = existing.partition(START_MARKER)
    _, _, post = after_start.partition(END_MARKER)
    return pre + new_block + post


def _verify_django_settings(project: Path, files: list[Path]) -> list[Finding]:
    docs_evidence: list[str] = []
    runtime_evidence: list[str] = []
    docs_values: set[str] = set()
    runtime_values: set[str] = set()

    for path in files:
        if path.suffix == ".py" and path.name not in {"manage.py", "asgi.py", "wsgi.py", "celery.py"} and not path.name.endswith((".asgi.py", ".wsgi.py", ".celery.py")):
            continue
        if path.suffix != ".py" and not _is_doc_or_env_file(path):
            continue
        text = _read_text(path)
        if not text or "DJANGO_SETTINGS_MODULE" not in text:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "DJANGO_SETTINGS_MODULE" not in line:
                continue
            value = _extract_settings_module(line)
            rel = _rel(project, path, line_no)
            if _is_runtime_settings_path(path):
                runtime_evidence.append(rel)
                if value:
                    runtime_values.add(value)
            else:
                docs_evidence.append(rel)
                if value:
                    docs_values.add(value)

    evidence = sorted({*docs_evidence, *runtime_evidence})
    if not evidence:
        return [Finding(
            id="django-settings-module",
            title="Django settings module",
            status="UNKNOWN",
            category="runtime/doc claim",
            evidence=[],
            details="No `DJANGO_SETTINGS_MODULE` evidence was found in docs/env files or runtime entrypoints.",
            recommendation="Add a clearly declared settings module in runtime files or document the module path in a load-bearing doc.",
        )]

    if docs_values and runtime_values:
        if len(docs_values | runtime_values) == 1:
            value = next(iter(docs_values | runtime_values))
            return [Finding(
                id="django-settings-module",
                title="Django settings module",
                status="VERIFIED",
                category="runtime/doc claim",
                evidence=evidence,
                details=f"Docs/env and runtime agree on `{value}`.",
                recommendation="Keep docs/env and runtime aligned if the settings module changes.",
            )]
        return [Finding(
            id="django-settings-module",
            title="Django settings module",
            status="CONFLICT",
            category="runtime/doc claim",
            evidence=evidence,
            details=f"Docs/env mention {sorted(docs_values)}, but runtime entrypoints mention {sorted(runtime_values)}.",
            recommendation="Pick one settings module as the source of truth and update the other references to match.",
        )]

    if runtime_values:
        return [Finding(
            id="django-settings-module",
            title="Django settings module",
            status="VERIFIED",
            category="runtime/doc claim",
            evidence=evidence,
            details=f"Runtime entrypoints confirm `{sorted(runtime_values)[0]}`.",
            recommendation="Keep runtime declarations stable and re-run verify after any settings-module move.",
        )]

    if docs_values:
        return [Finding(
            id="django-settings-module",
            title="Django settings module",
            status="DOC_ONLY",
            category="runtime/doc claim",
            evidence=evidence,
            details=f"Docs/env mention {sorted(docs_values)}, but no runtime entrypoint confirmation was found.",
            recommendation="Add or check runtime entrypoints so the declared settings module is actually wired up.",
        )]

    return [Finding(
        id="django-settings-module",
        title="Django settings module",
        status="UNKNOWN",
        category="runtime/doc claim",
        evidence=evidence,
        details="Evidence existed, but no concrete module value could be extracted.",
        recommendation="State the settings module explicitly in docs/env or runtime so it can be verified deterministically.",
    )]


def _verify_celery_beat(project: Path, files: list[Path]) -> list[Finding]:
    docs_lines: list[str] = []
    docs_sources: set[str] = set()
    code_lines: list[str] = []
    schedule_sources: set[str] = set()
    scheduler_sources: set[str] = set()

    for path in files:
        text = _read_text(path)
        if not text:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _BEAT_RE.search(line):
                rel = _rel(project, path, line_no)
                if _is_doc_or_env_file(path):
                    docs_lines.append(rel)
                    docs_sources.update(_extract_sources_from_line(line))
                elif path.suffix == ".py":
                    code_lines.append(rel)
                    if "beat_schedule" in line or "CELERY_BEAT_SCHEDULE" in line or "app.conf.beat_schedule" in line:
                        schedule_sources.add(_normalize_source(path))
                    if "CELERY_BEAT_SCHEDULER" in line:
                        scheduler_sources.add(_normalize_source(path))

    evidence = sorted({*docs_lines, *code_lines})
    if not evidence and not schedule_sources and not scheduler_sources:
        return [Finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="UNKNOWN",
            category="runtime/doc claim",
            evidence=[],
            details="No Celery beat schedule or scheduler evidence was found.",
            recommendation="Add a clear schedule owner or a doc note that explains where the beat schedule is defined.",
        )]

    owner_sources = schedule_sources
    if docs_sources and owner_sources:
        if docs_sources & owner_sources:
            chosen = sorted(docs_sources & owner_sources)[0]
            return [Finding(
                id="celery-beat-schedule",
                title="Celery beat schedule ownership",
                status="VERIFIED",
                category="runtime/doc claim",
                evidence=evidence,
                details=f"Docs/env and code both point at `{chosen}` as the beat schedule source.",
                recommendation="Keep the documented owner and code owner in sync whenever the beat schedule moves.",
            )]
        return [Finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="CONFLICT",
            category="runtime/doc claim",
            evidence=evidence,
            details=f"Docs/env mention {sorted(docs_sources)}, but code defines the schedule in {sorted(owner_sources)}.",
            recommendation="Decide which file owns the schedule and update the docs to match the actual code path.",
        )]

    if owner_sources:
        return [Finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="VERIFIED",
            category="runtime/doc claim",
            evidence=evidence,
            details=f"Code defines the beat schedule in {sorted(owner_sources)}.",
            recommendation="Keep the schedule centralized and re-run verify if ownership changes.",
        )]

    if docs_sources:
        return [Finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="DOC_ONLY",
            category="runtime/doc claim",
            evidence=evidence,
            details=f"Docs/env mention {sorted(docs_sources)}, but no schedule-definition code was found.",
            recommendation="Confirm the schedule is implemented in code, or update the docs if the claim is stale.",
        )]

    return [Finding(
        id="celery-beat-schedule",
        title="Celery beat schedule ownership",
        status="UNKNOWN",
        category="runtime/doc claim",
        evidence=evidence,
        details="Celery beat configuration tokens were found, but no concrete owner could be determined.",
        recommendation="Make the owner explicit in code or docs so the schedule can be verified deterministically.",
    )]


def _verify_tracked_artifacts(project: Path) -> list[Finding]:
    tracked = _git_tracked_files(project)
    if tracked is None:
        return []

    offenders = []
    for path in tracked:
        rel = _rel_key(project, path)
        if any(rel == prefix.rstrip("/") or rel.startswith(prefix) for prefix in _TRACKED_ARTIFACT_PREFIXES):
            offenders.append(rel)

    if not offenders:
        return []

    offenders.sort()
    return [Finding(
        id="tracked-generated-artifacts",
        title="Tracked generated artifacts",
        status="CONFLICT",
        category="repo hygiene",
        evidence=offenders,
        details="Generated or build-output paths are tracked in git, which conflicts with the usual ignore-and-regenerate workflow.",
        recommendation="Untrack these paths, add or tighten ignore rules, and regenerate them only as build artifacts.",
    )]


def _verify_doc_count_claims(project: Path, doc_files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for label, pattern in _DOC_COUNT_PATTERNS.items():
        values: dict[str, set[str]] = {}
        evidence: set[str] = set()
        for path in doc_files:
            text = _read_text(path)
            if not text:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                match = pattern.search(line)
                if not match:
                    continue
                value = match.group(1)
                values.setdefault(value, set()).add(_rel(project, path, line_no))
                evidence.add(_rel(project, path, line_no))
        if not values:
            continue
        unique_values = sorted(values.keys(), key=int)
        status = "CONFLICT" if len(unique_values) > 1 else "DOC_ONLY"
        title = f"{label.title()} count claims"
        details = (
            f"Docs claim multiple {label} counts: {unique_values}."
            if status == "CONFLICT"
            else f"Docs mention a single {label} count (`{unique_values[0]}`) and no runtime source was checked for this claim."
        )
        recommendation = (
            f"Pick one {label} count, update stale docs, and keep the strongest source of truth in a single place."
            if status == "CONFLICT"
            else f"Treat the `{unique_values[0]}` claim as documentation-only until a runtime source is added."
        )
        findings.append(Finding(
            id=f"doc-count-{label.replace(' ', '-')}",
            title=title,
            status=status,
            category="documentation claim",
            evidence=sorted(evidence),
            details=details,
            recommendation=recommendation,
        ))
    return findings


def _project_files(project: Path) -> list[Path]:
    files: dict[str, Path] = {}

    tracked = _git_tracked_files(project)
    if tracked is not None:
        for path in tracked:
            files[_rel_key(project, path)] = path

    for path in _walk_files(project):
        if not _is_relevant_candidate(path):
            continue
        files.setdefault(_rel_key(project, path), path)

    if files:
        return [files[key] for key in sorted(files.keys())]
    return _walk_files(project)


def _git_tracked_files(project: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "ls-files"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    paths = [project / line.strip() for line in result.stdout.splitlines() if line.strip()]
    return paths


def _walk_files(project: Path) -> list[Path]:
    files: list[Path] = []
    ignore = {".git", "__pycache__", "node_modules", ".venv", "venv", "venv_ml", "dist", "build"}
    for root, dirs, names in os.walk(project):
        dirs[:] = [d for d in dirs if d not in ignore]
        base = Path(root)
        for name in names:
            files.append(base / name)
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeError):
        return ""


def _is_doc_file(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown", ".rst"}


def _is_env_file(path: Path) -> bool:
    name = path.name.lower()
    return name == ".env" or name.startswith(".env.") or name.endswith(".env")


def _is_doc_or_env_file(path: Path) -> bool:
    return _is_doc_file(path) or _is_env_file(path)


def _is_relevant_candidate(path: Path) -> bool:
    try:
        if path.resolve() == _IMPLEMENTATION_FILE:
            return False
    except OSError:
        pass
    return _is_doc_or_env_file(path) or path.suffix == ".py"


def _is_runtime_settings_path(path: Path) -> bool:
    name = path.name
    return name in {"manage.py", "asgi.py", "wsgi.py", "celery.py"} or name.endswith((".asgi.py", ".wsgi.py", ".celery.py"))


def _extract_settings_module(line: str) -> str | None:
    match = _DJANGO_SETTINGS_VALUE_RE.search(line)
    if match:
        return match.group(1)
    tokens = re.findall(r"['\"]([A-Za-z_][\w.]*)['\"]", line)
    for token in reversed(tokens):
        if token != "DJANGO_SETTINGS_MODULE":
            return token
    return None


def _extract_sources_from_line(line: str) -> set[str]:
    sources: set[str] = set()
    for match in _PATH_OR_MODULE_RE.finditer(line):
        if match.group("path"):
            sources.add(_normalize_source_text(match.group("path")))
        elif match.group("module"):
            module = match.group("module")
            if ".conf." in module or module.endswith(".beat_schedule") or module.upper().startswith("CELERY_"):
                continue
            sources.add(_normalize_source_text(module))
    return sources


def _normalize_source(path: Path) -> str:
    return path.as_posix()


def _normalize_source_text(text: str) -> str:
    if text.endswith((".py", ".pyi", ".toml", ".yaml", ".yml", ".json", ".md")):
        return text.replace("\\", "/")
    if "." in text and "/" not in text and not text.upper().startswith("CELERY_") and ".conf." not in text and not text.endswith(".beat_schedule"):
        return text.replace(".", "/") + ".py"
    return text


def _rel(project: Path, path: Path, line_no: int) -> str:
    try:
        rel = path.relative_to(project)
    except ValueError:
        rel = path
    return f"{rel.as_posix()}:{line_no}"


def _rel_key(project: Path, path: Path) -> str:
    try:
        rel = path.relative_to(project)
    except ValueError:
        rel = path
    return rel.as_posix()
