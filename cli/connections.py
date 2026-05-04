"""context-kit `connections` subcommand: wiring / integrity audit scaffold.

This is a read-only wiring report. It does not prove correctness; it
only checks whether built subsystems appear to be connected across
backend routes, frontend/mobile API calls, Celery task references,
agent registries, and spider registries.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cli.hotpath import _collect_files, _with_sizes


_CONNECTION_SCOPES = ("backend", "frontend", "mobile", "agents", "spiders", "celery")
_DISCLAIMER = "This is a wiring audit, not a correctness proof."
_SEVERITY_ORDER = ("high", "medium", "advisory")

_BACKEND_PREFIXES = ("core/", "backend/", "app/", "api/")
_FRONTEND_PREFIXES = ("frontend/", "web/", "client/", "ui/")
_MOBILE_PREFIXES = ("mobile/", "android/", "ios/", "react-native/", "react_native/")
_AGENT_PREFIXES = ("core/agents/", "agents/")
_SPIDER_PREFIXES = ("ai_core/spiders/", "spiders/")
_CELERY_PREFIXES = ("core/celery.py", "core/tasks", "core/schedulers.py")

_ROUTE_RE = re.compile(r"""(?i)\b(?:path|re_path|url)\s*\(\s*(?:r)?(['"])(?P<route>.+?)\1""")
_FETCH_RE = re.compile(r"(?i)\b(fetch|axios\.(?:get|post|put|patch|delete|request)|client\.(?:get|post|put|patch|delete|request)|http(?:Client)?\.(?:get|post|put|patch|delete|request)|apiClient\.(?:get|post|put|patch|delete|request)|requests\.(?:get|post|put|patch|delete|request)|send_task|signature)\s*\(")
_URL_LITERAL_RE = re.compile(r"""(['"])(?P<url>/(?:[^'"]+)|https?://[^'"]+)\1""")
_TASK_DEF_DECORATOR_RE = re.compile(r"(?i)@(?:shared_task|app\.task|celery(?:_app)?\.task)\b")
_TASK_DEF_NAME_RE = re.compile(r"(?i)name\s*=\s*['\"](?P<name>[^'\"]+)['\"]")
_DEF_RE = re.compile(r"(?i)^\s*def\s+(?P<name>[A-Za-z_]\w*)\s*\(")
_TASK_REF_RE = re.compile(r"""(?i)\b(?:send_task|signature)\s*\(\s*['"](?P<name>[^'"]+)['"]|task\s*:\s*['"](?P<task>[^'"]+)['"]""")
_REGISTRY_DEF_LINE_RE = re.compile(r"(?i)^\s*(?P<name>AGENT_MAP|agent_map|AGENT_REGISTRY|registry|REGISTRY|SpiderData|SPIDER_MAP|spider_map|spider_registry)\s*=\s*\{(?P<body>.*)$")
_REGISTRY_REF_RE = re.compile(r"(?i)\b(?P<name>AGENT_MAP|agent_map|AGENT_REGISTRY|registry|REGISTRY|SpiderData|SPIDER_MAP|spider_map|spider_registry)\s*(?:\.get\s*\(\s*|\[\s*)(['\"])(?P<key>[^'\"]+)\2")
_MAIN_RE = re.compile(r"(?i)\bdef\s+main\s*\(")
_HANDLE_RE = re.compile(r"(?i)\bdef\s+handle\s*\(")
_DISPATCH_RE = re.compile(r"(?i)\bdef\s+(?:dispatch|route|router|controller)\w*\s*\(")


@dataclass
class ConnectionFinding:
    id: str
    title: str
    severity: str
    category: str
    evidence: list[str] = field(default_factory=list)
    details: str = ""
    recommendation: str = ""


@dataclass
class ConnectionReport:
    repo: str
    path: str
    scope: str | None
    disclaimer: str
    summary: dict
    findings: list[ConnectionFinding]
    backend_routes: list[dict]
    frontend_endpoints: list[dict]
    mobile_endpoints: list[dict]


def run_connections(args: argparse.Namespace) -> int:
    project = Path(args.path).resolve() if getattr(args, "path", None) else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    scope = getattr(args, "scope", None)
    if scope is not None and scope not in _CONNECTION_SCOPES:
        print(f"context-kit: unknown connections scope `{scope}`. Valid scopes: {', '.join(_CONNECTION_SCOPES)}.")
        return 2

    report = collect_connections(project, scope=scope)
    if getattr(args, "json", False):
        print(json.dumps(_to_json(report), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 0


def collect_connections(project: Path, *, scope: str | None = None) -> ConnectionReport:
    files = _collect_files(project)[0]
    if scope is not None:
        files = [path for path in files if _connection_scope_matches(project, path, scope)]

    sized = _with_sizes(files)
    backend_routes: list[dict] = []
    frontend_endpoints: list[dict] = []
    mobile_endpoints: list[dict] = []
    task_defs: dict[str, str] = {}
    task_refs: list[dict] = []
    agent_defs: dict[str, str] = {}
    agent_refs: list[dict] = []
    spider_defs: dict[str, str] = {}
    spider_refs: list[dict] = []
    dynamic_refs: list[dict] = []

    for path, _size in sized:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel = _rel(project, path)
        backend_routes.extend(_extract_backend_routes(rel, text))
        frontend_refs = _extract_endpoint_refs(rel, text, kind="frontend")
        mobile_refs = _extract_endpoint_refs(rel, text, kind="mobile")
        frontend_endpoints.extend(frontend_refs)
        mobile_endpoints.extend(mobile_refs)
        dynamic_refs.extend([ref for ref in frontend_refs + mobile_refs if ref["endpoint"] == "<dynamic>"])
        task_defs.update(_extract_task_defs(rel, text))
        task_refs.extend(_extract_task_refs(rel, text))
        agent_defs.update(_extract_registry_defs(rel, text, kind="agents"))
        agent_refs.extend(_extract_registry_refs(rel, text, kind="agents"))
        spider_defs.update(_extract_registry_defs(rel, text, kind="spiders"))
        spider_refs.extend(_extract_registry_refs(rel, text, kind="spiders"))

    findings: list[ConnectionFinding] = []

    backend_matches = defaultdict(list)
    for route in backend_routes:
        route_text = route["route"]
        matched_refs = [ref for ref in frontend_endpoints + mobile_endpoints if _route_matches(route_text, ref["endpoint"])]
        if matched_refs:
            backend_matches[route_text].extend(matched_refs)
        else:
            findings.append(
                ConnectionFinding(
                    id=f"orphaned-route:{route_text}",
                    title="Orphaned backend route",
                    severity="medium",
                    category="orphaned_route",
                    evidence=[f"{route['file']}: {route_text}"],
                    details=f"No frontend/mobile reference matched backend route `{route_text}`.",
                    recommendation="Either wire a client to this route or confirm it is intentionally backend-only.",
                )
            )

    for ref in frontend_endpoints + mobile_endpoints:
        if ref["endpoint"] == "<dynamic>":
            continue
        if any(_route_matches(route["route"], ref["endpoint"]) for route in backend_routes):
            continue
        severity = "advisory" if ref["file"].startswith("docs/") else "high"
        category = "docs_only_claim" if severity == "advisory" else "missing_target"
        title = "Docs-only endpoint claim" if severity == "advisory" else "Missing backend endpoint"
        recommendation = (
            "Update the docs claim or add the backend route it describes."
            if severity == "advisory"
            else "Implement the endpoint or fix the client call to target an existing backend route."
        )
        findings.append(
            ConnectionFinding(
                id=f"{category}:{ref['endpoint']}",
                title=title,
                severity=severity,
                category=category,
                evidence=[f"{ref['file']}: {ref['endpoint']}"],
                details=f"No backend route matched `{ref['endpoint']}`.",
                recommendation=recommendation,
            )
        )

    if dynamic_refs:
        unique_dynamic_files = sorted({f"{ref['file']}: {ref['line']}" for ref in dynamic_refs})
        findings.append(
            ConnectionFinding(
                id="unknown-dynamic-reference",
                title="Unknown dynamic reference",
                severity="advisory",
                category="unknown_dynamic_reference",
                evidence=unique_dynamic_files[:5],
                details=f"{len(dynamic_refs)} dynamic endpoint references could not be matched statically.",
                recommendation="Follow the call site manually or add a stable endpoint string to the client.",
            )
        )

    for ref in task_refs:
        if ref["name"] in task_defs:
            continue
        findings.append(
            ConnectionFinding(
                id=f"task-missing:{ref['name']}",
                title="Missing task definition",
                severity="high",
                category="missing_target",
                evidence=[f"{ref['file']}: {ref['name']}"],
                details=f"Task reference `{ref['name']}` has no matching @shared_task / @app.task definition.",
                recommendation="Define the task or update the reference to an existing task name.",
            )
        )

    for ref in agent_refs:
        if ref["name"] in agent_defs:
            continue
        findings.append(
            ConnectionFinding(
                id=f"agent-missing:{ref['name']}",
                title="Missing agent registry entry",
                severity="high",
                category="missing_target",
                evidence=[f"{ref['file']}: {ref['name']}"],
                details=f"Agent reference `{ref['name']}` has no matching registry entry.",
                recommendation="Add the agent to the registry or update the reference to a registered agent.",
            )
        )

    for ref in spider_refs:
        if ref["name"] in spider_defs:
            continue
        findings.append(
            ConnectionFinding(
                id=f"spider-missing:{ref['name']}",
                title="Missing spider registry entry",
                severity="high",
                category="missing_target",
                evidence=[f"{ref['file']}: {ref['name']}"],
                details=f"Spider reference `{ref['name']}` has no matching registry entry.",
                recommendation="Add the spider to the registry or update the reference to a registered spider.",
            )
        )

    findings.sort(key=lambda item: (_severity_rank(item.severity), item.category, item.id))
    summary = {
        "total_files_scanned": len(sized),
        "backend_routes": len(backend_routes),
        "frontend_endpoints": len(frontend_endpoints),
        "mobile_endpoints": len(mobile_endpoints),
        "orphaned_backend_routes": sum(1 for f in findings if f.category == "orphaned_route"),
        "missing_backend_endpoints": sum(1 for f in findings if f.category == "missing_target" and f.title == "Missing backend endpoint"),
        "docs_only_claims": sum(1 for f in findings if f.category == "docs_only_claim"),
        "unknown_dynamic_references": sum(1 for f in findings if f.category == "unknown_dynamic_reference"),
        "task_refs_missing_definition": sum(1 for f in findings if f.id.startswith("task-missing:")),
        "agent_refs_missing_entry": sum(1 for f in findings if f.id.startswith("agent-missing:")),
        "spider_refs_missing_entry": sum(1 for f in findings if f.id.startswith("spider-missing:")),
        "findings_total": len(findings),
    }
    return ConnectionReport(
        repo=project.name,
        path=str(project),
        scope=scope,
        disclaimer=_DISCLAIMER,
        summary=summary,
        findings=findings,
        backend_routes=backend_routes,
        frontend_endpoints=frontend_endpoints,
        mobile_endpoints=mobile_endpoints,
    )


def _extract_backend_routes(file_path: str, text: str) -> list[dict]:
    if not file_path.endswith("urls.py"):
        return []
    out: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        match = _ROUTE_RE.search(line)
        if not match:
            continue
        route = _normalize_route(match.group("route"))
        if not route:
            continue
        out.append({"file": file_path, "line": line_no, "route": route, "evidence": f"{line_no}: {line.strip()}"})
    return out


def _extract_endpoint_refs(file_path: str, text: str, *, kind: str) -> list[dict]:
    out: list[dict] = []
    call_context = _is_client_surface(file_path, kind)
    for line_no, line in enumerate(text.splitlines(), start=1):
        lower = line.lower()
        if not any(token in lower for token in ("fetch(", "axios.", "client.", "httpclient", "apiclient", "requests.", "send_task(", "signature(")):
            continue
        urls = [m.group("url") for m in _URL_LITERAL_RE.finditer(line) if _looks_like_endpoint(m.group("url"))]
        if urls:
            if call_context or file_path.startswith("docs/"):
                source_kind = kind if call_context else "docs"
                for url in urls:
                    out.append(
                        {
                            "file": file_path,
                            "line": line_no,
                            "endpoint": _normalize_endpoint(url),
                            "kind": source_kind,
                            "evidence": f"{line_no}: {line.strip()}",
                        }
                    )
            continue
        if call_context and any(token in lower for token in ("fetch(", "axios.", "client.", "httpclient", "apiclient", "requests.")):
            out.append(
                {
                    "file": file_path,
                    "line": line_no,
                    "endpoint": "<dynamic>",
                    "kind": kind,
                    "evidence": f"{line_no}: {line.strip()}",
                }
            )
    return out


def _extract_task_defs(file_path: str, text: str) -> dict[str, str]:
    if not file_path.endswith(".py"):
        return {}
    module = _module_name(file_path)
    defs: dict[str, str] = {}
    lines = text.splitlines()
    pending = False
    explicit_name: str | None = None
    for idx, line in enumerate(lines):
        if _TASK_DEF_DECORATOR_RE.search(line):
            pending = True
            m = _TASK_DEF_NAME_RE.search(line)
            explicit_name = m.group("name") if m else None
            continue
        if pending:
            m = _DEF_RE.search(line)
            if not m:
                continue
            func = m.group("name")
            name = explicit_name or f"{module}.{func}"
            defs[name] = file_path
            defs[func] = file_path
            pending = False
            explicit_name = None
    return defs


def _extract_task_refs(file_path: str, text: str) -> list[dict]:
    out: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in _TASK_REF_RE.finditer(line):
            name = match.group("name") or match.group("task")
            if not name:
                continue
            out.append({"file": file_path, "line": line_no, "name": name, "evidence": f"{line_no}: {line.strip()}"})
    return out


def _extract_registry_defs(file_path: str, text: str, *, kind: str) -> dict[str, str]:
    names = _agent_registry_names() if kind == "agents" else _spider_registry_names()
    defs: dict[str, str] = {}
    lines = text.splitlines()
    capture = False
    current_name = None
    brace_depth = 0
    for line in lines:
        if not capture:
            m = _REGISTRY_DEF_LINE_RE.search(line)
            if not m or m.group("name") not in names:
                continue
            capture = True
            current_name = m.group("name")
            brace_depth = line.count("{") - line.count("}")
            defs.update(_extract_string_dict_keys(line, file_path))
            if brace_depth <= 0:
                capture = False
                current_name = None
            continue
        defs.update(_extract_string_dict_keys(line, file_path))
        brace_depth += line.count("{") - line.count("}")
        if brace_depth <= 0:
            capture = False
            current_name = None
    return defs


def _extract_registry_refs(file_path: str, text: str, *, kind: str) -> list[dict]:
    out: list[dict] = []
    names = _agent_registry_names() if kind == "agents" else _spider_registry_names()
    pattern = re.compile(r"(?i)\b(?P<name>" + "|".join(map(re.escape, names)) + r")\s*(?:\.get\s*\(\s*|\[\s*)(['\"])(?P<key>[^'\"]+)\2")
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            out.append({"file": file_path, "line": line_no, "name": match.group("key"), "evidence": f"{line_no}: {line.strip()}"})
    return out


def _extract_string_dict_keys(line: str, file_path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in re.finditer(r"""(['"])(?P<key>[^'"]+)\1\s*:""", line):
        out[match.group("key")] = file_path
    return out


def _route_matches(route: str, endpoint: str) -> bool:
    if endpoint == "<dynamic>":
        return False
    a = _normalize_endpoint(route)
    b = _normalize_endpoint(endpoint)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/")


def _normalize_route(route: str) -> str:
    route = route.strip()
    route = route.lstrip("r").strip()
    if route.startswith("^"):
        route = route[1:]
    if route.endswith("$"):
        route = route[:-1]
    route = re.sub(r"<[^>]+>", "*", route)
    route = re.sub(r"\(\?P<[^>]+>[^)]+\)", "*", route)
    route = re.sub(r"[\\\[\]\(\)\?\+\|]", "", route)
    route = route.replace(".*", "")
    route = route.replace("*", "")
    route = re.sub(r"/{2,}", "/", route)
    route = route.strip()
    if not route.startswith("/"):
        route = "/" + route
    if route != "/" and route.endswith("/*"):
        route = route[:-2] + "/"
    if route != "/" and not route.endswith("/"):
        route += "/"
    return route


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip()
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        endpoint = re.sub(r"^https?://[^/]+", "", endpoint)
    if "?" in endpoint:
        endpoint = endpoint.split("?", 1)[0]
    if "#" in endpoint:
        endpoint = endpoint.split("#", 1)[0]
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    endpoint = re.sub(r"/{2,}", "/", endpoint)
    if endpoint != "/" and endpoint.endswith("/"):
        endpoint = endpoint[:-1]
    return endpoint


def _looks_like_endpoint(url: str) -> bool:
    return url.startswith("/") or url.startswith("http://") or url.startswith("https://")


def _connection_scope_matches(project: Path, path: Path, scope: str) -> bool:
    try:
        rel = path.relative_to(project).as_posix()
    except ValueError:
        rel = path.as_posix()
    lowered = rel.lower()
    name = path.name.lower()

    if scope == "backend":
        return lowered.startswith(_BACKEND_PREFIXES) or name in {"manage.py", "urls.py", "views.py", "viewsets.py", "serializers.py", "models.py"}
    if scope == "frontend":
        return lowered.startswith(_FRONTEND_PREFIXES) or name.endswith((".js", ".jsx", ".ts", ".tsx"))
    if scope == "mobile":
        return lowered.startswith(_MOBILE_PREFIXES) or name.endswith((".dart", ".swift", ".kt", ".java"))
    if scope == "agents":
        return lowered.startswith(_AGENT_PREFIXES) or lowered in {"docs/topics/agent-system.md", "docs/agents.md"}
    if scope == "spiders":
        return lowered.startswith(_SPIDER_PREFIXES) or lowered in {"docs/topics/spider-network.md", "docs/spiders.md"}
    if scope == "celery":
        return lowered.startswith(_CELERY_PREFIXES) or lowered.startswith("core/management/commands/") or name == "procfile"
    return False


def _is_client_surface(file_path: str, kind: str) -> bool:
    lowered = file_path.lower()
    if kind == "frontend":
        return lowered.startswith(_FRONTEND_PREFIXES)
    if kind == "mobile":
        return lowered.startswith(_MOBILE_PREFIXES)
    if kind == "backend":
        return lowered.startswith(_BACKEND_PREFIXES)
    if kind == "docs":
        return lowered.startswith("docs/")
    return False


def _agent_registry_names() -> list[str]:
    return ["AGENT_MAP", "agent_map", "AGENT_REGISTRY", "registry", "REGISTRY"]


def _spider_registry_names() -> list[str]:
    return ["SpiderData", "SPIDER_MAP", "spider_map", "spider_registry", "registry", "REGISTRY"]


def _module_name(file_path: str) -> str:
    module = file_path
    if module.endswith(".py"):
        module = module[:-3]
    module = module.replace("/", ".")
    if module.endswith(".__init__"):
        module = module[: -len(".__init__")]
    return module


def _severity_rank(severity: str) -> int:
    try:
        return _SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(_SEVERITY_ORDER)


def _rel(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path)


def _render_text(report: ConnectionReport) -> str:
    lines = [
        "=== CONTEXT-KIT CONNECTIONS ===",
        f"Repo:           {report.repo}",
        f"Path:           {report.path}",
        "",
        report.disclaimer,
        "",
        "## Summary",
        f"  Files scanned:           {report.summary['total_files_scanned']:,}",
        f"  Backend routes:          {report.summary['backend_routes']:,}",
        f"  Frontend endpoints:      {report.summary['frontend_endpoints']:,}",
        f"  Mobile endpoints:        {report.summary['mobile_endpoints']:,}",
        f"  Findings:                {report.summary['findings_total']:,}",
        "",
        "## Risk areas",
    ]
    if not report.findings:
        lines.append("  _No connection gaps found._")
    else:
        for finding in report.findings[:5]:
            lines.append(f"  [{finding.severity}] {finding.title}: {finding.details}")
            for evidence in finding.evidence[:2]:
                lines.append(f"       - {evidence}")
    lines.append("")
    lines.append("## Orphaned backend routes")
    orphaned = [f for f in report.findings if f.category == "orphaned_route"]
    if orphaned:
        for finding in orphaned[:5]:
            lines.append(f"  {finding.details}")
    else:
        lines.append("  _None._")
    lines.append("")
    lines.append("## Missing backend endpoints")
    missing = [f for f in report.findings if f.category == "missing_target"]
    if missing:
        for finding in missing[:5]:
            lines.append(f"  [{finding.severity}] {finding.details}")
    else:
        lines.append("  _None._")
    return "\n".join(lines).rstrip() + "\n"


def _to_json(report: ConnectionReport) -> dict:
    return {
        "repo": report.repo,
        "path": report.path,
        "scope": report.scope,
        "disclaimer": report.disclaimer,
        "summary": report.summary,
        "findings": [asdict(item) for item in report.findings],
        "backend_routes": report.backend_routes,
        "frontend_endpoints": report.frontend_endpoints,
        "mobile_endpoints": report.mobile_endpoints,
    }
