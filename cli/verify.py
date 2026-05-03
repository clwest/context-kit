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
_EVIDENCE_SCOPE_ORDER = (
    "runtime",
    "env",
    "canonical_docs",
    "supporting_docs",
    "active_docs",
    "historical_docs",
    "external_docs",
)
_ACTIVE_SCOPES = {"runtime", "active_docs", "env"}
_HISTORICAL_SCOPES = {"historical_docs", "external_docs"}
_TRACKED_ARTIFACT_PREFIXES = (
    "venv/",
    ".venv/",
    "venv_ml/",
    "frontend/dist/",
    "dist/",
    "build/",
    "node_modules/",
)
_DOC_COUNT_LABEL_PATTERNS = {
    "agents": r"agents?",
    "spiders": r"spiders?",
    "apis": r"apis?",
    "frontend pages": r"frontend\s+pages?",
}
_DOC_COUNT_STRONG_LABELS = {
    "agents": r"(?:total|registered|current|count)\s+agents?|agents?\s+count",
    "spiders": r"(?:total|registered|current|count)\s+spiders?|spiders?\s+count",
    "apis": r"(?:total|registered|current|count)\s+apis?|apis?\s+count",
    "frontend pages": r"(?:total|registered|current|count)\s+frontend\s+pages?|frontend\s+pages?\s+count",
}
_DOC_COUNT_CONTEXT_RE = re.compile(
    r"(?i)(?:^\s*#{1,6}\s*|^\s*[-*+]\s*|^\s*\|\s*|(?:\b(?:total|registered|current|count|agents|spiders|apis|frontend pages)\s*:))"
)
_DOC_COUNT_DIMENSIONS = ("total", "db_persona", "dormant", "provenance", "workspace", "category_table", "unknown")
_DOC_COUNT_SPIDER_SUBCOUNT_TERMS = (
    "working",
    "placeholder",
    "api key",
    "api keys",
    "need api keys",
    "needs api keys",
    "api-key",
    "api-keys",
    "status",
    "breakdown",
    "by category",
    "per category",
    "source",
    "sources",
    "subcount",
    "sub-count",
    "dormant",
    "inactive",
)
_DJANGO_SETTINGS_RE = re.compile(r"DJANGO_SETTINGS_MODULE", re.IGNORECASE)
_CELERY_OWNER_RE = re.compile(
    r"(?i)(?:beat_schedule\s*=|app\.conf\.beat_schedule|CELERY_BEAT_SCHEDULE|CELERY_BEAT_SCHEDULER|PeriodicTask\.objects|sync_celery_schedules)"
)
_CELERY_DOC_RE = re.compile(r"(?i)\b(celery beat|celery beat schedule|beat_schedule|CELERY_BEAT_SCHEDULE|CELERY_BEAT_SCHEDULER|PeriodicTask|sync_celery_schedules|app\.conf\.beat_schedule)\b")
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
    evidence_by_scope: dict[str, list[str]] = field(default_factory=dict)
    details: str = ""
    recommendation: str = ""


@dataclass
class VerificationReport:
    repo: str
    generated_at: str
    summary: dict
    findings: list[Finding]
    config_path: str | None = None
    canonical_docs_used: bool = False


@dataclass
class VerifyConfig:
    path: Path
    canonical_docs: list[str] = field(default_factory=list)
    active_doc_roots: list[str] = field(default_factory=list)
    historical_roots: list[str] = field(default_factory=list)
    generated_artifact_roots: list[str] = field(default_factory=list)


def run_verify(args: argparse.Namespace) -> int:
    project = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    report = collect_verification(
        project,
        include_archive=getattr(args, "include_archive", False),
        all_docs=getattr(args, "all_docs", False),
    )

    if getattr(args, "write", False):
        write_verification_report(project, report)

    if getattr(args, "json", False):
        print(json.dumps(asdict(report), indent=2, sort_keys=True))
    else:
        print(render_human_report(report))
    return 0


def collect_verification(project: Path, *, include_archive: bool = False, all_docs: bool = False) -> VerificationReport:
    config = _load_verify_config(project)
    files = _project_files(project)
    docs_files = [p for p in files if _is_doc_file(p)]
    env_files = [p for p in files if _is_env_file(p)]
    python_files = [p for p in files if p.suffix == ".py"]

    findings: list[Finding] = []
    findings.extend(_verify_django_settings(project, docs_files + env_files + python_files, include_archive=include_archive))
    findings.extend(_verify_celery_beat(project, docs_files + env_files + python_files, include_archive=include_archive))
    findings.extend(_verify_tracked_artifacts(project, config=config))
    findings.extend(_verify_doc_count_claims(project, docs_files, config=config, include_archive=include_archive, all_docs=all_docs))

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
        config_path=_rel_key(project, config.path) if config else None,
        canonical_docs_used=bool(config and config.canonical_docs and not all_docs),
    )


def render_human_report(report: VerificationReport) -> str:
    lines = [
        "# Verification Report",
        "",
        f"- Repo: `{report.repo}`",
        f"- Generated at: `{report.generated_at}`",
    ]
    if report.config_path:
        lines.append(f"- Config: `{report.config_path}`")
        lines.append(f"- Canonical docs used: `{str(report.canonical_docs_used).lower()}`")
    lines.extend([
        "",
        "## Summary",
        "",
    ])
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
            ])
            lines.extend(_render_finding_evidence(finding))
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


def _load_verify_config(project: Path) -> VerifyConfig | None:
    path = project / ".context-kit" / "verify.yaml"
    if not path.exists():
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    data: dict[str, list[str]] = {
        "canonical_docs": [],
        "active_doc_roots": [],
        "historical_roots": [],
        "generated_artifact_roots": [],
    }
    current_key: str | None = None
    for raw in lines:
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            current_key = key if key in data else None
            continue
        if current_key and re.match(r"^\s*-\s+", line):
            item = line.split("-", 1)[1].strip().strip("'\"")
            if item:
                data[current_key].append(_normalize_config_item(item))
    return VerifyConfig(path=path, **data)


def _normalize_config_item(text: str) -> str:
    value = text.replace("\\", "/").strip()
    if value.startswith("./"):
        value = value[2:]
    while value.startswith("/"):
        value = value[1:]
    return value


def _path_matches_spec(rel_path: str, spec: str) -> bool:
    normalized = _normalize_config_item(spec)
    if not normalized:
        return False
    if normalized.endswith("/"):
        return rel_path == normalized.rstrip("/") or rel_path.startswith(normalized)
    return rel_path == normalized or rel_path.startswith(normalized + "/")


def _path_matches_any_spec(rel_path: str, specs: list[str]) -> bool:
    return any(_path_matches_spec(rel_path, spec) for spec in specs)


def _doc_scope_for_path(path: Path, project: Path, config: VerifyConfig | None, *, all_docs: bool) -> str:
    rel = _rel_key(project, path)
    if _is_historical_doc_path(path, config):
        return "historical_docs"
    if _is_external_doc_path(path, config):
        return "external_docs"
    if config and config.canonical_docs and _path_matches_any_spec(rel, config.canonical_docs):
        return "canonical_docs"
    if config and config.canonical_docs and not all_docs:
        return "supporting_docs"
    if config and config.canonical_docs and all_docs:
        return "supporting_docs"
    return "active_docs"


def _is_historical_doc_path(path: Path, config: VerifyConfig | None) -> bool:
    rel = path.as_posix().replace("\\", "/")
    roots = config.historical_roots if config else []
    if roots and _path_matches_any_spec(rel, roots):
        return True
    lowered_parts = [part.lower() for part in path.parts]
    lowered_path = rel.lower()
    return any(
        marker in lowered_parts
        for marker in {"archive", "archives", "historical", "history", "legacy", "old", "handoff", "handoffs", "session", "sessions", "case-studies", "case_studies"}
    ) or any(token in lowered_path for token in ("session_", "handoff", "case-study", "case_study", "old-session", "old_sessions"))


def _is_external_doc_path(path: Path, config: VerifyConfig | None) -> bool:
    rel = path.as_posix().replace("\\", "/")
    roots = config.historical_roots if config else []
    if roots and any("external-project-docs" in _normalize_config_item(root) for root in roots):
        if _path_matches_any_spec(rel, [root for root in roots if "external-project-docs" in _normalize_config_item(root)]):
            return True
    lowered_parts = [part.lower() for part in path.parts]
    lowered_path = rel.lower()
    return any(
        marker in lowered_parts
        for marker in {"external", "externals", "reference", "references", "third-party", "third_party", "vendor", "imported", "imported-reference"}
    ) or any(token in lowered_path for token in ("external-project-docs", "external-docs", "imported-reference", "reference", "references"))


def _is_artifact_path(rel_path: str, roots: list[str]) -> bool:
    return any(_path_matches_spec(rel_path, root) for root in roots)


def _verify_django_settings(project: Path, files: list[Path], *, include_archive: bool = False) -> list[Finding]:
    evidence_by_scope = _new_scope_evidence_map()
    values_by_scope: dict[str, set[str]] = {scope: set() for scope in _EVIDENCE_SCOPE_ORDER}

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
            scope = _scope_for_path(path)
            evidence_by_scope[scope].add(rel)
            if value:
                values_by_scope[scope].add(value)

    evidence = _flatten_scope_evidence(evidence_by_scope)
    if not evidence:
        return [_make_finding(
            id="django-settings-module",
            title="Django settings module",
            status="UNKNOWN",
            category="runtime/doc claim",
            details="No `DJANGO_SETTINGS_MODULE` evidence was found in docs/env files or runtime entrypoints.",
            recommendation="Add a clearly declared settings module in runtime files or document the module path in a load-bearing doc.",
        )]

    runtime_values = _scope_values(values_by_scope, {"runtime"})
    active_values = _scope_values(values_by_scope, {"active_docs", "env"})
    historical_values = _scope_values(values_by_scope, _HISTORICAL_SCOPES)

    if runtime_values:
        if active_values and runtime_values != active_values:
            return [_make_finding(
                id="django-settings-module",
                title="Django settings module",
                status="CONFLICT",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=f"Docs/env mention {sorted(active_values)}, but runtime entrypoints mention {sorted(runtime_values)}.",
                recommendation="Pick one settings module as the source of truth and update the other references to match.",
            )]
        primary_values = runtime_values
        if include_archive:
            primary_values |= active_values | historical_values
        if len(primary_values) > 1:
            return [_make_finding(
                id="django-settings-module",
                title="Django settings module",
                status="CONFLICT",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=_build_doc_runtime_details(active_values or runtime_values, historical_values, include_archive=include_archive),
                recommendation="Pick one settings module as the source of truth and update the other references to match.",
            )]
        details = f"Runtime entrypoints confirm `{sorted(runtime_values)[0]}`."
        if historical_values and historical_values != runtime_values and not include_archive:
            details += f" Historical docs drift to {sorted(historical_values)}."
        return [_make_finding(
            id="django-settings-module",
            title="Django settings module",
            status="VERIFIED",
            category="runtime/doc claim",
            evidence_by_scope=evidence_by_scope,
            details=details,
            recommendation="Keep runtime declarations stable and re-run verify after any settings-module move.",
        )]

    if active_values:
        if len(active_values) > 1:
            return [_make_finding(
                id="django-settings-module",
                title="Django settings module",
                status="CONFLICT",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=_build_doc_runtime_details(active_values, historical_values, include_archive=include_archive),
                recommendation="Pick one settings module as the source of truth and update the other references to match.",
            )]
        if include_archive and historical_values and historical_values != active_values:
            return [_make_finding(
                id="django-settings-module",
                title="Django settings module",
                status="CONFLICT",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=_build_doc_runtime_details(active_values, historical_values, include_archive=include_archive),
                recommendation="Pick one settings module as the source of truth and update the other references to match.",
            )]
        return [_make_finding(
            id="django-settings-module",
            title="Django settings module",
            status="DOC_ONLY",
            category="runtime/doc claim",
            evidence_by_scope=evidence_by_scope,
            details=f"Docs/env mention {sorted(active_values)}, but no runtime entrypoint confirmation was found.",
            recommendation="Add or check runtime entrypoints so the declared settings module is actually wired up.",
        )]

    if historical_values:
        if include_archive and len(historical_values) > 1:
            return [_make_finding(
                id="django-settings-module",
                title="Django settings module",
                status="CONFLICT",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=f"Historical docs mention multiple settings modules: {sorted(historical_values)}.",
                recommendation="Keep historical references for context, but add a live runtime declaration if the claim still matters.",
            )]
        details = (
            f"Historical docs mention multiple settings modules: {sorted(historical_values)}."
            if len(historical_values) > 1
            else f"Historical docs mention `{sorted(historical_values)[0]}` but no active runtime evidence was found."
        )
        return [_make_finding(
            id="django-settings-module",
            title="Django settings module",
            status="DOC_ONLY",
            category="runtime/doc claim",
            evidence_by_scope=evidence_by_scope,
            details=details + (" Historical docs are drift only unless include-archive is enabled." if len(historical_values) > 1 else ""),
            recommendation="Keep historical references for context, but add a live runtime declaration if the claim still matters.",
        )]

    return [_make_finding(
        id="django-settings-module",
        title="Django settings module",
        status="UNKNOWN",
        category="runtime/doc claim",
        evidence_by_scope=evidence_by_scope,
        details="Evidence existed, but no concrete module value could be extracted.",
        recommendation="State the settings module explicitly in docs/env or runtime so it can be verified deterministically.",
    )]


def _verify_celery_beat(project: Path, files: list[Path], *, include_archive: bool = False) -> list[Finding]:
    evidence_by_scope = _new_scope_evidence_map()
    docs_sources_by_scope: dict[str, set[str]] = {scope: set() for scope in _EVIDENCE_SCOPE_ORDER}
    schedule_sources: set[str] = set()
    db_store_sources: set[str] = set()
    bridge_sources: set[str] = set()
    routing_sources: set[str] = set()
    doc_split_claim = False
    doc_exclusive_settings_claim = False
    doc_exclusive_celery_claim = False

    for path in files:
        text = _read_text(path)
        if not text:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _CELERY_DOC_RE.search(line):
                rel = _rel(project, path, line_no)
                scope = _scope_for_path(path)
                if path.suffix == ".py" and _is_celery_runtime_signal_line(line):
                    evidence_by_scope[scope].add(rel)
                    if scope in _ACTIVE_SCOPES:
                        docs_sources_by_scope[scope].update(_extract_sources_from_line(line))
                    if _is_celery_static_schedule_line(line):
                        schedule_sources.add(_normalize_source(path))
                    if _is_celery_db_store_line(line):
                        db_store_sources.add(_normalize_source(path))
                    if _is_celery_bridge_line(line):
                        bridge_sources.add(_normalize_source(path))
                    if _is_celery_routing_line(line, path):
                        routing_sources.add(_normalize_source(path))
                elif path.suffix != ".py":
                    evidence_by_scope[scope].add(rel)
                    if scope in _ACTIVE_SCOPES:
                        docs_sources_by_scope[scope].update(_extract_sources_from_line(line))
                if path.suffix != ".py" and scope in _ACTIVE_SCOPES:
                    lowered = line.lower()
                    if "split" in lowered and "celery" in lowered:
                        doc_split_claim = True
                    if (
                        "settings.py" in lowered
                        and "beat schedule" in lowered
                        and any(token in lowered for token in ("owns", "owns the", "source of truth", "exclusive", "dead code", "is the owner"))
                    ):
                        doc_exclusive_settings_claim = True
                    if "celery.py" in lowered and any(token in lowered for token in ("dead code", "obsolete", "not used", "exclusive", "only")):
                        doc_exclusive_celery_claim = True
                    if "primary static" in lowered or "runtime store" in lowered or "sync" in lowered or "bridge" in lowered:
                        doc_split_claim = True

    evidence = _flatten_scope_evidence(evidence_by_scope)
    if not evidence and not schedule_sources and not db_store_sources and not bridge_sources and not routing_sources:
        return [_make_finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="UNKNOWN",
            category="runtime/doc claim",
            details="No Celery beat schedule or scheduler evidence was found.",
            recommendation="Add a clear schedule owner or a doc note that explains where the beat schedule is defined.",
        )]

    owner_sources = schedule_sources
    active_doc_sources = _scope_values(docs_sources_by_scope, {"active_docs", "env"})
    historical_doc_sources = _scope_values(docs_sources_by_scope, _HISTORICAL_SCOPES)
    split_runtime_supported = bool(schedule_sources and (db_store_sources or bridge_sources or routing_sources))
    split_runtime_supported = split_runtime_supported and bool(db_store_sources or bridge_sources)
    routing_supported = bool(routing_sources)

    if doc_exclusive_settings_claim or doc_exclusive_celery_claim:
        if owner_sources:
            return [_make_finding(
                id="celery-beat-schedule",
                title="Celery beat schedule ownership",
                status="CONFLICT",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=f"Docs/env claim exclusive ownership in {sorted(active_doc_sources or historical_doc_sources)}, but code defines the static schedule in {sorted(owner_sources)} and also shows split-owner signals in {sorted(db_store_sources | bridge_sources | routing_sources)}.",
                recommendation="Describe the split ownership model accurately or update the exclusive-ownership claim.",
            )]
        return [_make_finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="CONFLICT",
            category="runtime/doc claim",
            evidence_by_scope=evidence_by_scope,
            details=f"Docs/env claim exclusive ownership in {sorted(active_doc_sources or historical_doc_sources)}, but no matching exclusive runtime owner was found.",
            recommendation="Describe the split ownership model accurately or update the exclusive-ownership claim.",
        )]

    if active_doc_sources:
        if doc_split_claim and split_runtime_supported:
            details = "Docs/env describe split Celery ownership and runtime evidence supports a static schedule source, DB store, bridge command, and routing/config owner."
            if owner_sources:
                details += f" Static schedule source: {sorted(owner_sources)}."
            if db_store_sources:
                details += f" DB store: {sorted(db_store_sources)}."
            if bridge_sources:
                details += f" Bridge/bootstrap: {sorted(bridge_sources)}."
            if routing_sources:
                details += f" Routing/config: {sorted(routing_sources)}."
            if historical_doc_sources and historical_doc_sources != active_doc_sources:
                details += f" Historical docs drift to {sorted(historical_doc_sources)}."
            return [_make_finding(
                id="celery-beat-schedule",
                title="Celery beat schedule ownership",
                status="VERIFIED",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=details,
                recommendation="Keep the split ownership model documented and re-run verify if the balance changes.",
            )]

        if owner_sources:
            details = f"Docs/env mention {sorted(active_doc_sources)}, but code defines the static schedule in {sorted(owner_sources)}."
            if split_runtime_supported:
                details += f" Additional split-owner signals were found in {sorted(db_store_sources | bridge_sources | routing_sources)}."
                return [_make_finding(
                    id="celery-beat-schedule",
                    title="Celery beat schedule ownership",
                    status="VERIFIED",
                    category="runtime/doc claim",
                    evidence_by_scope=evidence_by_scope,
                    details=details,
                    recommendation="Keep the split ownership model documented and re-run verify if the balance changes.",
                )]
            if historical_doc_sources and include_archive and historical_doc_sources != active_doc_sources:
                return [_make_finding(
                    id="celery-beat-schedule",
                    title="Celery beat schedule ownership",
                    status="CONFLICT",
                    category="runtime/doc claim",
                    evidence_by_scope=evidence_by_scope,
                    details=details + f" Historical docs also mention {sorted(historical_doc_sources)}.",
                    recommendation="Describe the split ownership model accurately or update the exclusive-ownership claim.",
                )]
            return [_make_finding(
                id="celery-beat-schedule",
                title="Celery beat schedule ownership",
                status="VERIFIED",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=details,
                recommendation="Keep the split ownership model documented and re-run verify if the balance changes.",
            )]

        if split_runtime_supported:
            details = "Docs/env mention split Celery ownership and runtime evidence supports the model."
            if db_store_sources:
                details += f" DB store: {sorted(db_store_sources)}."
            if bridge_sources:
                details += f" Bridge/bootstrap: {sorted(bridge_sources)}."
            if routing_sources:
                details += f" Routing/config: {sorted(routing_sources)}."
            return [_make_finding(
                id="celery-beat-schedule",
                title="Celery beat schedule ownership",
                status="VERIFIED",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=details,
                recommendation="Keep the split ownership model documented and re-run verify if the balance changes.",
            )]

        if owner_sources:
            details = f"Docs/env mention {sorted(active_doc_sources)}, but no matching split runtime evidence was found."
            return [_make_finding(
                id="celery-beat-schedule",
                title="Celery beat schedule ownership",
                status="DOC_ONLY",
                category="runtime/doc claim",
                evidence_by_scope=evidence_by_scope,
                details=details,
                recommendation="Confirm the split ownership model in code or update the docs if the claim is stale.",
            )]

    if owner_sources:
        details = f"Code defines the beat schedule in {sorted(owner_sources)}."
        if split_runtime_supported:
            details += f" Split-owner runtime signals were also found in {sorted(db_store_sources | bridge_sources | routing_sources)}."
        if historical_doc_sources and historical_doc_sources != owner_sources:
            details += f" Historical docs drift to {sorted(historical_doc_sources)}."
        return [_make_finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="VERIFIED",
            category="runtime/doc claim",
            evidence_by_scope=evidence_by_scope,
            details=details,
            recommendation="Keep the schedule centralized and re-run verify if ownership changes.",
        )]

    if historical_doc_sources:
        details = (
            f"Historical docs mention split Celery ownership {sorted(historical_doc_sources)} but no active runtime confirmation was found."
            if len(historical_doc_sources) > 1
            else f"Historical docs mention `{sorted(historical_doc_sources)[0]}` but no active runtime confirmation was found."
        )
        return [_make_finding(
            id="celery-beat-schedule",
            title="Celery beat schedule ownership",
            status="DOC_ONLY",
            category="runtime/doc claim",
            evidence_by_scope=evidence_by_scope,
            details=details + (" Historical docs are drift only unless include-archive is enabled." if len(historical_doc_sources) > 1 else ""),
            recommendation="Keep historical references for context, but add a live runtime declaration if the claim still matters.",
        )]

    return [_make_finding(
        id="celery-beat-schedule",
        title="Celery beat schedule ownership",
        status="UNKNOWN",
        category="runtime/doc claim",
        details="Celery beat configuration tokens were found, but no concrete owner could be determined.",
        recommendation="Make the owner explicit in code or docs so the schedule can be verified deterministically.",
    )]


def _verify_tracked_artifacts(project: Path, *, config: VerifyConfig | None = None) -> list[Finding]:
    tracked = _git_tracked_files(project)
    if tracked is None:
        return []

    artifact_roots = list(_TRACKED_ARTIFACT_PREFIXES)
    if config:
        artifact_roots.extend(root if root.endswith("/") else f"{root}/" for root in config.generated_artifact_roots)

    offenders = []
    for path in tracked:
        rel = _rel_key(project, path)
        if _is_artifact_path(rel, artifact_roots):
            offenders.append(rel)

    if not offenders:
        return []

    offenders.sort()
    return [_make_finding(
        id="tracked-generated-artifacts",
        title="Tracked generated artifacts",
        status="CONFLICT",
        category="repo hygiene",
        evidence_by_scope={"runtime": set(offenders)},
        details="Generated or build-output paths are tracked in git, which conflicts with the usual ignore-and-regenerate workflow.",
        recommendation="Untrack these paths, add or tighten ignore rules, and regenerate them only as build artifacts.",
    )]


def _verify_doc_count_claims(
    project: Path,
    doc_files: list[Path],
    *,
    config: VerifyConfig | None = None,
    include_archive: bool = False,
    all_docs: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []
    for label in _DOC_COUNT_LABEL_PATTERNS:
        claims_by_scope: dict[str, dict[str, dict[str, set[str]]]] = {
            scope: {dimension: {} for dimension in _DOC_COUNT_DIMENSIONS}
            for scope in _EVIDENCE_SCOPE_ORDER
        }
        evidence_by_scope = _new_scope_evidence_map()
        for path in doc_files:
            text = _read_text(path)
            if not text:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                entries = _extract_doc_count_entries(line, label)
                if not entries:
                    continue
                rel = _rel(project, path, line_no)
                scope = _doc_scope_for_path(path, project, config, all_docs=all_docs)
                evidence_by_scope[scope].add(rel)
                for value, dimension in entries:
                    claims_by_scope[scope][dimension].setdefault(value, set()).add(rel)
        if not any(
            claims_by_scope[scope][dimension]
            for scope in _EVIDENCE_SCOPE_ORDER
            for dimension in _DOC_COUNT_DIMENSIONS
        ):
            continue
        canonical_total = _scope_dimension_value_set(claims_by_scope, {"canonical_docs"}, "total")
        supporting_total = _scope_dimension_value_set(claims_by_scope, {"supporting_docs"}, "total")
        active_total = _scope_dimension_value_set(claims_by_scope, {"active_docs"}, "total")
        historical_total = _scope_dimension_value_set(claims_by_scope, _HISTORICAL_SCOPES, "total")
        active_unknown = _scope_dimension_value_set(claims_by_scope, {"active_docs"}, "unknown")
        active_other_dims = _scope_dimension_value_set(claims_by_scope, {"active_docs"}, {"db_persona", "dormant", "provenance", "workspace", "category_table"})
        status = "DOC_ONLY"
        if config and config.canonical_docs:
            scoring_values = canonical_total if not all_docs else canonical_total | supporting_total
        else:
            scoring_values = active_total
        total_dimension = "total"
        if include_archive:
            scoring_values = scoring_values | historical_total
        if scoring_values and len(scoring_values) > 1:
            status = "CONFLICT"

        title = f"{label.title()} count claims"
        display_values = sorted({value for scope in _EVIDENCE_SCOPE_ORDER for value in claims_by_scope[scope][total_dimension].keys()}, key=int)
        chosen_values = sorted(scoring_values or historical_total or supporting_total or active_total, key=int)
        if status == "CONFLICT":
            details = f"Docs claim multiple {label} total counts: {display_values}."
            recommendation = f"Pick one {label} count, update stale docs, and keep the strongest source of truth in a single place."
        else:
            chosen = chosen_values[0] if chosen_values else None
            if config and config.canonical_docs and canonical_total and supporting_total and supporting_total != canonical_total and not all_docs:
                details = f"Canonical docs mention `{chosen}`, while supporting docs drift to {sorted(supporting_total, key=int)}."
            elif config and config.canonical_docs and not canonical_total and supporting_total:
                details = f"Supporting docs mention `{chosen}`; canonical docs did not claim this total."
            elif historical_total and not (canonical_total or active_total or supporting_total):
                if len(historical_total) > 1:
                    details = f"Historical drift mentions multiple {label} total counts: {sorted(historical_total, key=int)}."
                else:
                    details = f"Historical drift mentions `{chosen}` and no runtime source was checked for this claim."
            else:
                if config and config.canonical_docs and not all_docs and canonical_total:
                    details = f"Canonical docs mention a single {label} total count (`{chosen}`) and no runtime source was checked for this claim."
                else:
                    if chosen is not None:
                        details = f"Docs mention a single {label} total count (`{chosen}`) and no runtime source was checked for this claim."
                    else:
                        details = f"Docs mention only subordinate {label} counts and no runtime source was checked for this claim."
                if historical_total:
                    details += f" Historical docs still mention {sorted(historical_total, key=int)}."
                if active_other_dims:
                    details += f" Subordinate dimensions mention {sorted(active_other_dims, key=int)}."
                if active_unknown:
                    details += f" Additional advisory counts mention {sorted(active_unknown, key=int)}."
            recommendation = f"Treat the `{chosen}` claim as documentation-only until a runtime source is added."
        findings.append(_make_finding(
            id=f"doc-count-{label.replace(' ', '-')}",
            title=title,
            status=status,
            category="documentation claim",
            evidence_by_scope=evidence_by_scope,
            details=details,
            recommendation=recommendation,
        ))
    return findings


def _project_files(project: Path) -> list[Path]:
    files: dict[str, Path] = {}

    tracked = _git_tracked_files(project)
    if tracked is not None:
        for path in tracked:
            if not _is_relevant_candidate(path):
                continue
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
    if _is_verification_output(path):
        return False
    if _is_doc_or_env_file(path) or path.suffix == ".py":
        return True
    if _is_deploy_template(path):
        return True
    return False


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
            if "PeriodicTask" in module and "objects" not in line:
                continue
            sources.add(_normalize_source_text(module))
    return sources


def _is_celery_schedule_owner_line(line: str) -> bool:
    return bool(_CELERY_OWNER_RE.search(line))


def _is_celery_runtime_signal_line(line: str) -> bool:
    lowered = line.lower()
    return (
        "beat_schedule" in lowered
        or "app.conf.beat_schedule" in lowered
        or "celery_beat_schedule" in lowered
        or "periodictask.objects" in lowered
        or "periodictask" in lowered
        or "sync_celery_schedules" in lowered
        or "celery_task_routes" in lowered
        or "celery_beat_scheduler" in lowered
        or "django-celery-beat" in lowered
        or "database scheduler" in lowered
        or "scheduler" in lowered and "celery" in lowered
    )


def _is_celery_static_schedule_line(line: str) -> bool:
    lowered = line.lower()
    return "beat_schedule" in lowered or "app.conf.beat_schedule" in lowered or "celery_beat_schedule" in lowered


def _is_celery_db_store_line(line: str) -> bool:
    lowered = line.lower()
    return "periodictask.objects" in lowered or "django-celery-beat" in lowered or "periodictask" in lowered


def _is_celery_bridge_line(line: str) -> bool:
    lowered = line.lower()
    return "sync_celery_schedules" in lowered or "bootstrap" in lowered or "repair rows" in lowered or "materializ" in lowered


def _is_celery_routing_line(line: str, path: Path) -> bool:
    lowered = line.lower()
    return "celery_task_routes" in lowered or "celery_beat_scheduler" in lowered or path.name == "settings.py" or path.name.endswith("settings.py")


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


def _is_verification_output(path: Path) -> bool:
    parts = path.parts
    if "docs" not in parts:
        return False
    try:
        docs_idx = parts.index("docs")
    except ValueError:
        return False
    tail = parts[docs_idx + 1 :]
    if not tail:
        return False
    if tail[0] != "verification":
        return False
    return True


def _new_scope_evidence_map() -> dict[str, set[str]]:
    return {scope: set() for scope in _EVIDENCE_SCOPE_ORDER}


def _flatten_scope_evidence(evidence_by_scope: dict[str, set[str]]) -> list[str]:
    return sorted({item for items in evidence_by_scope.values() for item in items})


def _scope_values(values_by_scope: dict[str, set[str]], scopes: set[str] | tuple[str, ...] | list[str]) -> set[str]:
    values: set[str] = set()
    for scope in scopes:
        values.update(values_by_scope.get(scope, set()))
    return values


def _scope_value_set(values_by_scope: dict[str, dict[str, set[str]]], scopes: set[str] | tuple[str, ...] | list[str]) -> set[str]:
    values: set[str] = set()
    for scope in scopes:
        values.update(values_by_scope.get(scope, {}).keys())
    return values


def _scope_dimension_value_set(
    claims_by_scope: dict[str, dict[str, dict[str, set[str]]]],
    scopes: set[str] | tuple[str, ...] | list[str],
    dimensions: str | set[str] | tuple[str, ...] | list[str],
) -> set[str]:
    if isinstance(dimensions, str):
        dims = {dimensions}
    else:
        dims = set(dimensions)
    values: set[str] = set()
    for scope in scopes:
        scope_claims = claims_by_scope.get(scope, {})
        for dimension in dims:
            values.update(scope_claims.get(dimension, {}).keys())
    return values


def _scope_for_path(path: Path) -> str:
    if _is_runtime_settings_path(path):
        return "runtime"
    if _is_env_file(path) or _is_deploy_template(path):
        return "env"
    if _is_doc_file(path):
        lowered_parts = [part.lower() for part in path.parts]
        lowered_path = path.as_posix().lower()
        name = path.name.lower()
        if any(
            marker in lowered_parts
            for marker in {"archive", "archives", "historical", "history", "legacy", "old", "handoff", "handoffs", "session", "sessions", "case-studies", "case_studies"}
        ) or any(token in lowered_path for token in ("session_", "handoff", "case-study", "case_study", "old-session", "old_sessions")):
            return "historical_docs"
        if any(
            marker in lowered_parts
            for marker in {"external", "externals", "reference", "references", "third-party", "third_party", "vendor", "imported", "imported-reference"}
        ) or any(token in lowered_path for token in ("external-project-docs", "external-docs", "imported-reference", "reference", "references")):
            return "external_docs"
        return "active_docs"
    return "runtime"


def _is_deploy_template(path: Path) -> bool:
    lowered = path.as_posix().lower()
    if path.suffix.lower() not in {".yaml", ".yml", ".toml", ".json"}:
        return False
    markers = (
        "deploy",
        "deployment",
        "compose",
        "docker-compose",
        "render",
        "railway",
        "vercel",
        "fly",
        "heroku",
        "kubernetes",
        "k8s",
    )
    return any(marker in lowered for marker in markers)


def _is_doc_count_claim_line(line: str, label: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if re.match(r"^\s*(?:#{1,6}\s*)?\d+(?:\.\d+)*[.)]\s+", stripped):
        return False
    if not _DOC_COUNT_CONTEXT_RE.search(stripped):
        return False
    label_re = _DOC_COUNT_LABEL_PATTERNS[label]
    if re.search(rf"(?i)\b{label_re}\b", stripped):
        return True
    return False


def _extract_doc_count_entries(line: str, label: str) -> list[tuple[str, str]]:
    stripped = line.strip()
    entries: list[tuple[str, str]] = []
    if not stripped:
        return entries
    table_row = _is_doc_count_table_row(stripped)
    table_cells = _doc_count_table_cells(stripped) if table_row else None
    if not _is_doc_count_claim_line(stripped, label) and not table_row:
        return entries
    label_re = _DOC_COUNT_LABEL_PATTERNS[label]
    strong_label_re = _DOC_COUNT_STRONG_LABELS[label]
    strong_patterns = (
        rf"(?i)\b(?:{strong_label_re})\b\s*[:|\-]?\s*(\d{{1,3}})\b",
        rf"(?i)\b(\d{{1,3}})\b\s*[:|\-]?\s*\b{strong_label_re}\b",
        rf"(?i)\|\s*(?:total|registered|current|count|{label_re})\s*\|\s*(\d{{1,3}})\s*\|",
        rf"(?i)\|\s*(\d{{1,3}})\s*\|\s*(?:total|registered|current|count|{label_re})\s*\|",
    )
    weak_patterns = (
        rf"(?i)\b{label_re}\b\s*[:|\-]?\s*(\d{{1,3}})\b",
        rf"(?i)\b(\d{{1,3}})\b\s*[:|\-]?\s*\b{label_re}\b",
    )
    for pattern in strong_patterns:
        for match in re.finditer(pattern, stripped):
            value = match.group(1)
            if _is_valid_doc_count_value(value):
                entries.append((value, _classify_doc_count_dimension(stripped, label, strong=True, table_row=table_row, table_cells=table_cells)))
    for pattern in weak_patterns:
        for match in re.finditer(pattern, stripped):
            value = match.group(1)
            if _is_valid_doc_count_value(value) and int(value) >= 10:
                entries.append((value, _classify_doc_count_dimension(stripped, label, strong=False, table_row=table_row, table_cells=table_cells)))
    if not entries and table_row:
        for value in _extract_doc_count_table_values(stripped):
            entries.append((value, _classify_doc_count_dimension(stripped, label, strong=False, table_row=True, table_cells=table_cells)))
    return entries


def _extract_doc_count_table_values(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    values: list[str] = []
    for cell in cells:
        if re.fullmatch(r"\d{1,3}", cell) and _is_valid_doc_count_value(cell):
            values.append(cell)
    return values


def _is_doc_count_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and "|" in stripped


def _doc_count_table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_doc_count_summary_table_row(line: str, label: str, cells: list[str] | None = None) -> bool:
    cells = cells or _doc_count_table_cells(line)
    if not cells:
        return False
    numeric_indexes = [index for index, cell in enumerate(cells) if re.fullmatch(r"\d{1,3}", cell or "")]
    if len(numeric_indexes) != 1:
        return False
    label_re = _DOC_COUNT_LABEL_PATTERNS[label]
    strong_label_re = _DOC_COUNT_STRONG_LABELS[label]
    has_label_cell = any(
        re.fullmatch(rf"(?i)(?:{strong_label_re}|{label_re})", cell.strip())
        for cell in cells
    )
    if not has_label_cell:
        return False
    lowered = " ".join(cells).lower()
    return not any(term in lowered for term in _DOC_COUNT_SPIDER_SUBCOUNT_TERMS)


def _classify_doc_count_dimension(
    line: str,
    label: str,
    *,
    strong: bool,
    table_row: bool = False,
    table_cells: list[str] | None = None,
) -> str:
    lowered = line.lower()
    if table_row:
        if _is_doc_count_summary_table_row(line, label, table_cells):
            return "total"
        return "category_table"
    if label == "spiders":
        if any(term in lowered for term in _DOC_COUNT_SPIDER_SUBCOUNT_TERMS):
            return "unknown"
        if strong or any(token in lowered for token in ("across", "summary", "index", "total", "registered", "current", "count")):
            return "total"
        if re.search(rf"(?i)\b{_DOC_COUNT_LABEL_PATTERNS[label]}\b", lowered):
            return "total"
        return "unknown"
    if strong or any(token in lowered for token in ("agent_map", "agent-map", "agmap", "code agent", "code-agent", "headline", "primary agents", "current agents", "total agents")):
        return "total"
    if any(token in lowered for token in ("persona", "db", "database")):
        return "db_persona"
    if any(token in lowered for token in ("dormant", "inactive", "sleeping")):
        return "dormant"
    if "provenance" in lowered:
        return "provenance"
    if "workspace" in lowered:
        return "workspace"
    return "unknown"


def _is_valid_doc_count_value(value: str) -> bool:
    if not value or value == "000":
        return False
    if not value.isdigit():
        return False
    if len(value) > 3:
        return False
    if value != "0" and value.startswith("0"):
        return False
    return True


def _make_finding(
    *,
    id: str,
    title: str,
    status: str,
    category: str,
    details: str,
    recommendation: str,
    evidence_by_scope: dict[str, set[str]] | None = None,
) -> Finding:
    if evidence_by_scope is None:
        evidence_by_scope = _new_scope_evidence_map()
    normalized_by_scope = {
        scope: sorted(items)
        for scope, items in evidence_by_scope.items()
        if items
    }
    return Finding(
        id=id,
        title=title,
        status=status,
        category=category,
        evidence=_flatten_scope_evidence(evidence_by_scope),
        evidence_by_scope=normalized_by_scope,
        details=details,
        recommendation=recommendation,
    )


def _render_finding_evidence(finding: Finding) -> list[str]:
    lines = ["- Evidence:"]
    if "canonical_docs" in finding.evidence_by_scope or "supporting_docs" in finding.evidence_by_scope:
        canonical_items = _grouped_evidence_items(finding.evidence_by_scope, {"canonical_docs"}) + _grouped_evidence_items(finding.evidence_by_scope, {"runtime", "env"})
        supporting_items = _grouped_evidence_items(finding.evidence_by_scope, {"supporting_docs"})
        historical_items = _grouped_evidence_items(finding.evidence_by_scope, _HISTORICAL_SCOPES)
        lines.extend(_render_scope_group("Canonical evidence", canonical_items, "canonical"))
        lines.extend(_render_scope_group("Supporting drift", supporting_items, "supporting"))
        lines.extend(_render_scope_group("Historical drift", historical_items, "historical"))
        if not canonical_items and not supporting_items and not historical_items:
            lines.append("  - None")
        return lines

    primary_items = _grouped_evidence_items(finding.evidence_by_scope, {"runtime", "active_docs", "env"})
    historical_items = _grouped_evidence_items(finding.evidence_by_scope, _HISTORICAL_SCOPES)
    lines.extend(_render_scope_group("Primary evidence", primary_items, "primary"))
    lines.extend(_render_scope_group("Historical drift", historical_items, "historical"))
    if not primary_items and not historical_items:
        lines.append("  - None")
    return lines


def _render_scope_group(title: str, items: list[tuple[str, str]], label: str) -> list[str]:
    if not items:
        return []
    lines = [f"  - {title}:"]
    for scope, item in items[:5]:
        lines.append(f"    - [{scope}] {item}")
    remaining = len(items) - min(len(items), 5)
    if remaining > 0:
        lines.append(f"    - +{remaining} more {label} matches")
    return lines


def _grouped_evidence_items(evidence_by_scope: dict[str, list[str]], scopes: set[str]) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for scope in _EVIDENCE_SCOPE_ORDER:
        if scope not in scopes:
            continue
        for item in evidence_by_scope.get(scope, []):
            items.append((scope, item))
    return items


def _build_doc_runtime_details(active_values: set[str], historical_values: set[str], *, include_archive: bool) -> str:
    details = f"Docs/env mention {sorted(active_values)}, but no runtime entrypoint confirmation was found."
    if historical_values and (include_archive or historical_values != active_values):
        details += f" Historical docs mention {sorted(historical_values)}."
    return details
