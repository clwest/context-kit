"""context-kit `start` subcommand: localhost onboarding server.

Two pages:

- ``/``        — the existing project-view onboarding page (when the user
                 already has an init'd context-kit project)
- ``/wizard``  — the beginner wizard (when the user has nothing yet, or
                 has scaffolded but not seeded)
- ``/audit``   — the read-only audit dashboard (inspect + verify for v1)

Plus three small JSON APIs the wizard calls into:

- ``GET  /api/state``                              — classify cwd
- ``POST /api/idea``                                — write idea.md
- ``GET  /api/check?step={init|seed}&project_dir`` — verify a CLI step ran

And a small audit API surface:

- ``GET  /api/audit/state``                        — dashboard metadata
- ``POST /api/audit/run``                          — run a read-only audit
- ``GET  /api/audit/report?format=json``           — fetch the last report

The wizard writes only ``idea.md``. Every CLI step (`init`, `seed`,
`doctor`) is copy-paste — the wizard polls the filesystem to verify
they ran before advancing.

Standard library only — no external dependencies.
"""

from __future__ import annotations

import argparse
import html
import http.server
import importlib.resources as resources
import json
import os
import re
import socket
import sys
import urllib.parse
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Single-page onboarding template. Placeholders use ``{{NAME}}`` syntax so
# the substitution matches the rest of context-kit.
ONBOARDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Welcome to your {{PROJECT_TITLE}} project</title>
<style>
  :root {
    --bg: #0f1117;
    --panel: #151822;
    --border: #262a35;
    --text: #e5e7eb;
    --muted: #9ca3af;
    --accent: #6ee7b7;
    --danger: #f87171;
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #fafbfc;
      --panel: #ffffff;
      --border: #e5e7eb;
      --text: #111827;
      --muted: #6b7280;
      --accent: #059669;
      --danger: #dc2626;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  .wrap { max-width: 780px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }
  h1 { font-size: 1.9rem; margin: 0 0 .25rem; letter-spacing: -0.01em; }
  .tag { color: var(--muted); font-size: .9rem; margin-bottom: 1rem; }
  .project-root {
    font-family: var(--mono);
    font-size: .8rem;
    color: var(--muted);
    word-break: break-all;
    margin-bottom: 2rem;
  }
  section {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
  }
  h2 { font-size: 1.1rem; margin: 0 0 .75rem; }
  p { margin: .25rem 0 .75rem; }
  ul, ol { margin: .25rem 0; padding-left: 1.25rem; }
  li { margin: .3rem 0; }
  code {
    font-family: var(--mono);
    background: var(--border);
    padding: .1rem .35rem;
    border-radius: 4px;
    font-size: .9em;
  }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
  .do h2 { color: var(--accent); }
  .dont h2 { color: var(--danger); }
  .missing { color: var(--muted); font-size: .85em; }
  footer { color: var(--muted); font-size: .85rem; margin-top: 2rem; }
  kbd {
    font-family: var(--mono);
    background: var(--border);
    border-radius: 4px;
    padding: .05rem .4rem;
    font-size: .85em;
  }
</style>
</head>
<body>
  <div class="wrap">
    <h1>Welcome to your {{PROJECT_TITLE}} project</h1>
    <div class="tag">Powered by <strong>context-kit</strong> &mdash; first-session onboarding</div>
    <div class="project-root">{{PROJECT_ROOT}}</div>

    <section>
      <h2>First Steps</h2>
      <ol>
        <li>Open <code>00-START-NEXT-SESSION.md</code>.</li>
        <li>Read the <em>SOURCE OF TRUTH</em> section at the top.</li>
        <li>Begin your first AI session with that file in the assistant's context.</li>
      </ol>
    </section>

    <section>
      <h2>Why this exists</h2>
      <p>context-kit helps you maintain context across AI sessions by separating
      <em>narrative truth</em> from <em>runtime truth</em> and enforcing
      structure that future AI sessions can rely on. Without it, docs drift,
      the AI hallucinates confidently, and every new session starts from cold.</p>
    </section>

    <div class="grid">
      <section class="do">
        <h2>Do</h2>
        <ul>
          <li>Keep docs structured (use subdirectories under <code>docs/</code>).</li>
          <li>Write a session handoff at every session <em>end</em>, not next session's start.</li>
          <li>Use the inventory as runtime truth when docs disagree.</li>
          <li>Let the AI push back when something looks wrong.</li>
        </ul>
      </section>
      <section class="dont">
        <h2>Don't</h2>
        <ul>
          <li>Duplicate numbers across multiple docs.</li>
          <li>Trust stale data &mdash; re-run the verifier before citing.</li>
          <li>Skip session handoffs &mdash; zero exceptions, ever.</li>
          <li>Delete docs to &ldquo;clean up clutter.&rdquo; Archive instead.</li>
        </ul>
      </section>
    </div>

    <section>
      <h2>Key Files</h2>
      <ul>
        {{KEY_FILES_LIST}}
      </ul>
    </section>

    <section>
      <h2>Next commands</h2>
      <ul>
        <li><code>open 00-START-NEXT-SESSION.md</code> &mdash; or read it in your editor</li>
        <li><code>ls docs/docs-pattern/</code> &mdash; the full teaching guide</li>
        <li>If you bootstrapped with <code>--with-scaffold</code>:
            <code>python3 scaffold/python/build_docs_index.py</code></li>
      </ul>
    </section>

    <footer>
      Running at <code>{{URL}}</code> &mdash; press <kbd>Ctrl+C</kbd> in the terminal to stop.
    </footer>
  </div>
</body>
</html>
"""


def _find_project_title(project_root: Path) -> str:
    """Extract the project's display title from the narrative anchor doc."""
    for md in sorted(project_root.glob("docs/*_WHAT_IT_IS.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        if not match:
            continue
        title_match = re.search(
            r'^title:\s*"?([^"\n]+?)"?\s*$', match.group(1), re.MULTILINE
        )
        if title_match:
            # Strip common narrative-doc suffix like " — What It Actually Is".
            return re.sub(r"\s*[—-].*$", "", title_match.group(1)).strip()
    return project_root.name


def _key_files(project_root: Path) -> list[tuple[str, bool]]:
    """Return the canonical key-file list with presence flags."""
    entries: list[tuple[str, bool]] = []

    # Root-level entry points.
    for name in ("00-START-NEXT-SESSION.md", "CLAUDE.md"):
        entries.append((name, (project_root / name).exists()))

    # Discovered anchor docs (generic fallback if none present).
    whats = sorted(project_root.glob("docs/*_WHAT_IT_IS.md"))
    invs = sorted(project_root.glob("docs/*_INVENTORY.md"))
    if whats:
        for md in whats:
            entries.append((f"docs/{md.name}", True))
    else:
        entries.append(("docs/<APP>_WHAT_IT_IS.md", False))
    if invs:
        for md in invs:
            entries.append((f"docs/{md.name}", True))
    else:
        entries.append(("docs/<APP>_INVENTORY.md", False))

    # Remaining canonical paths.
    more = [
        ("docs/topics/", (project_root / "docs" / "topics").is_dir()),
        ("docs/handoffs/", (project_root / "docs" / "handoffs").is_dir()),
        ("docs/TRUST_CALIBRATION.md", (project_root / "docs" / "TRUST_CALIBRATION.md").exists()),
        ("docs/docs-pattern/", (project_root / "docs" / "docs-pattern").is_dir()),
    ]
    entries.extend(more)
    return entries


def _render_html(project_root: Path, url: str) -> str:
    title = html.escape(_find_project_title(project_root))
    file_items: list[str] = []
    for name, exists in _key_files(project_root):
        safe_name = html.escape(name)
        if exists:
            file_items.append(f"<li><code>{safe_name}</code></li>")
        else:
            file_items.append(
                f'<li><code>{safe_name}</code> '
                f'<span class="missing">(not yet created)</span></li>'
            )
    return (
        ONBOARDING_HTML
        .replace("{{PROJECT_TITLE}}", title)
        .replace("{{PROJECT_ROOT}}", html.escape(str(project_root)))
        .replace("{{URL}}", html.escape(url))
        .replace("{{KEY_FILES_LIST}}", "\n        ".join(file_items))
    )


def _pick_port(preferred: int, host: str) -> int:
    """Return a bindable port. Honor ``preferred`` if free, else OS-picks."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, preferred))
        except OSError:
            s.bind((host, 0))
        return s.getsockname()[1]


def _detect_project_state(cwd: Path) -> str:
    """Classify the project at ``cwd`` for wizard branching.

    Returns one of:
      - ``"none"``      no context-kit markers found
      - ``"scaffold"``  init'd, ``state: scaffold`` frontmatter
      - ``"seeded"``    seed has run (frontmatter ``state: seeded``)
      - any other state value the user has written into the frontmatter
    """
    start = cwd / "00-START-NEXT-SESSION.md"
    if not start.is_file():
        return "none"
    try:
        text = start.read_text(encoding="utf-8")
    except OSError:
        return "none"
    if not text.startswith("---\n"):
        return "scaffold"  # init'd but no frontmatter (older template)
    end_idx = text.find("\n---\n", 4)
    if end_idx < 0:
        return "scaffold"
    fm = text[4:end_idx]
    for line in fm.splitlines():
        s = line.strip()
        if s.startswith("state:"):
            return s[len("state:"):].strip() or "scaffold"
    return "scaffold"


def _scan_for_projects(cwd: Path) -> list:
    """Find immediate child dirs of ``cwd`` that look like context-kit projects.

    A directory qualifies when it contains ``00-START-NEXT-SESSION.md``
    (the marker every ``context-kit init`` writes). For each match we
    report which milestone files exist plus a ``suggested_step`` so a
    fresh browser tab opened by ``context-kit start`` can offer to
    resume from disk instead of forcing the user back to Step 1.

    Hidden dirs and common build/dependency folders are skipped to keep
    the wizard's "we found a project" prompt signal-only.
    """
    cwd = cwd.resolve()
    projects: list = []
    skip_names = {
        "node_modules", "__pycache__", "venv", ".venv",
        "dist", "build", ".git", ".idea", ".vscode",
    }
    try:
        entries = sorted(cwd.iterdir())
    except OSError:
        return projects
    for child in entries:
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in skip_names:
            continue
        start_doc = child / "00-START-NEXT-SESSION.md"
        if not start_doc.is_file():
            continue
        has_idea = (child / "idea.md").is_file()
        has_build_plan = (child / "docs" / "BUILD_PLAN.md").is_file()
        # Map filesystem milestones to wizard step numbers:
        #   BUILD_PLAN.md present  -> seed has run -> land on doctor (step 8)
        #   only init has run      -> land on recommend-stack/seed (step 6)
        suggested = 8 if has_build_plan else 6
        projects.append({
            "folder": child.name,
            "path": str(child),
            "has_idea_md": has_idea,
            "has_start_doc": True,
            "has_build_plan": has_build_plan,
            "suggested_step": suggested,
        })
    return projects


def _safe_project_path(cwd: Path, requested: str) -> Path:
    """Resolve ``requested`` relative to ``cwd``; reject traversal.

    Raises ``ValueError`` if the resolved path escapes ``cwd``.
    """
    cwd = cwd.resolve()
    if requested in ("", ".", "./"):
        return cwd
    candidate = (cwd / requested).resolve()
    try:
        candidate.relative_to(cwd)
    except ValueError as exc:
        raise ValueError(
            f"path {requested!r} resolves outside the project root {cwd}"
        ) from exc
    return candidate


def _load_wizard_html() -> Optional[str]:
    """Read the bundled wizard HTML from the cli package's ``_static`` dir.

    Returns ``None`` when the asset isn't present (e.g., in a generated
    project's reduced ``cli`` package). Callers should fall back to
    redirecting the user at ``/`` in that case.
    """
    try:
        return (resources.files("cli") / "_static" / "wizard.html").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


def _load_audit_html() -> Optional[str]:
    """Read the bundled audit HTML from the cli package's ``_static`` dir."""
    try:
        return (resources.files("cli") / "_static" / "audit.html").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


def _render_audit_html(project_root: Path, url: str) -> str:
    """Render the audit dashboard HTML, or a friendly fallback if absent."""
    body = _load_audit_html()
    if body is None:
        return (
            "<!doctype html><meta charset=utf-8>"
            "<title>Audit dashboard not available</title>"
            "<body style='font-family:system-ui;max-width:42rem;margin:3rem auto;padding:0 1rem'>"
            "<h1>Audit dashboard not available</h1>"
            "<p>The audit dashboard ships in the installed <code>contextkit-ai</code> package "
            "but is not available in this runtime copy.</p>"
            f"<p><strong>Project:</strong> <code>{html.escape(str(project_root))}</code></p>"
            f"<p><strong>URL:</strong> <code>{html.escape(url)}</code></p>"
            "</body>"
        )
    return (
        body
        .replace("{{PROJECT_ROOT}}", html.escape(str(project_root)))
        .replace("{{URL}}", html.escape(url))
    )


def _audit_supported_commands() -> tuple[str, ...]:
    return ("inspect", "coverage", "behavior", "connections", "verify", "doctor")


def _audit_supported_scopes() -> tuple[str, ...]:
    from cli.inspect import _INSPECT_SCOPES
    from cli.connections import _CONNECTION_SCOPES

    scopes = list(_INSPECT_SCOPES)
    for scope in _CONNECTION_SCOPES:
        if scope not in scopes:
            scopes.append(scope)
    return tuple(scopes)


def _audit_supported_audiences() -> tuple[str, ...]:
    return ("developer", "founder", "business")


def _audit_command_scopes(command: str) -> tuple[str, ...]:
    from cli.inspect import _INSPECT_SCOPES

    if command in {"inspect", "coverage", "behavior"}:
        return _INSPECT_SCOPES
    if command == "connections":
        from cli.connections import _CONNECTION_SCOPES

        return _CONNECTION_SCOPES
    return ()


def _audit_reality_issues(findings: list[dict], command: str) -> list[dict]:
    issues: list[dict] = []
    for finding in findings:
        finding_command = command if command != "full" else str(finding.get("command", ""))
        if command == "inspect":
            severity = str(finding.get("severity", "")).lower()
            title = str(finding.get("title", "")).lower()
            details = str(finding.get("details", "")).lower()
            category = str(finding.get("category", "")).lower()
            if severity not in {"low", "advisory"} or any(token in " ".join((title, details, category)) for token in ("fallback", "degraded", "failure", "dynamic reference")):
                issues.append(finding)
        elif finding_command == "verify":
            status = str(finding.get("status", "")).upper()
            if status != "VERIFIED":
                issues.append(finding)
        elif finding_command == "doctor":
            status = str(finding.get("status", "")).lower()
            if status and status != "ok":
                issues.append(finding)
        elif finding_command in {"coverage", "behavior", "connections"}:
            issues.append(finding)
        else:
            issues.append(finding)
    return issues


def _audit_impact(finding: dict, command: str) -> str:
    command = command if command != "full" else str(finding.get("command", ""))
    text = " ".join(
        str(finding.get(key, ""))
        for key in ("category", "title", "details", "recommendation")
    ).lower()
    route_role = str(finding.get("route_role", "")).lower()

    if "missing backend endpoint" in text or (
        command == "connections" and str(finding.get("category", "")).lower() == "missing_target" and "backend endpoint" in str(finding.get("title", "")).lower()
    ):
        return "High impact: a backend endpoint is referenced by clients but no matching route was found."
    if any(token in text for token in ("failure", "failed")):
        return "High impact: failure metadata suggests a broken or missing integration."
    if any(token in text for token in ("fallback", "degraded")):
        return "Medium impact: fallback or degraded metadata suggests a partially broken integration."
    if "dynamic reference" in text or str(finding.get("category", "")).lower() == "unknown_dynamic_reference":
        return "Low impact: the reference is dynamic and needs manual confirmation."
    if str(finding.get("category", "")).lower() == "orphaned_route" and route_role in {"admin", "health", "monitoring", "internal_api", "docs"}:
        return "Advisory impact: this backend route is intentionally internal, operational, or documentation-facing."

    if command == "inspect":
        severity = str(finding.get("severity", "")).lower()
        if severity == "high":
            return "High impact: likely to block correct operation or create user-facing breakage."
        if severity == "medium":
            return "Medium impact: likely to create a visible or operational gap."
        if severity in {"advisory", "low"}:
            return "Advisory impact: useful for cleanup or confirmation, but not immediately blocking."
        return "Low impact: cleanup or informational follow-up."
    if command in {"coverage", "behavior"}:
        severity = str(finding.get("severity", "")).lower()
        if severity == "high":
            return "High impact: this surface looks likely to hide a real implementation or wiring issue."
        if severity == "medium":
            return "Medium impact: this surface deserves review before it becomes a user-facing gap."
        return "Low impact: informational follow-up."
    if command == "connections":
        severity = str(finding.get("severity", "")).lower()
        if severity == "high":
            return "High impact: likely to block correct operation or create user-facing breakage."
        if severity == "medium":
            return "Medium impact: likely to create a visible or operational gap."
        return "Advisory impact: useful for cleanup or confirmation, but not immediately blocking."
    if command == "doctor":
        status = str(finding.get("status", "")).lower()
        if status == "blocking":
            return "High impact: this blocking environment issue prevents a reliable setup."
        if status == "warning":
            return "Medium impact: this warning is worth addressing before it becomes friction."
        return "Low impact: informational follow-up."
    status = str(finding.get("status", "")).upper()
    if status == "CONFLICT":
        return "High impact: runtime and docs disagree, so downstream decisions may be wrong."
    if status == "DOC_ONLY":
        return "Medium impact: the claim is documented but not verified in code/config."
    if status == "UNKNOWN":
        return "Low impact: the claim still needs evidence before it can be trusted."
    return "Low impact: confirmed and not currently blocking."


def _audit_rank(finding: dict, command: str) -> int:
    command = command if command != "full" else str(finding.get("command", ""))
    if command == "inspect":
        order = {"high": 0, "medium": 1, "advisory": 2, "low": 3}
        return order.get(str(finding.get("severity", "")).lower(), 4)
    if command in {"coverage", "behavior", "connections"}:
        order = {"high": 0, "medium": 1, "advisory": 2, "low": 3}
        return order.get(str(finding.get("severity", "")).lower(), 4)
    if command == "doctor":
        order = {"blocking": 0, "warning": 1, "skipped": 2, "ok": 3}
        return order.get(str(finding.get("status", "")).lower(), 4)
    order = {"CONFLICT": 0, "DOC_ONLY": 1, "UNKNOWN": 2, "VERIFIED": 3}
    return order.get(str(finding.get("status", "")).upper(), 4)


def _audit_critical_issues(findings: list[dict], command: str) -> list[dict]:
    issues = _audit_reality_issues(findings, command)
    return sorted(
        [
            {
                **finding,
                "impact": _audit_impact(finding, command),
            }
            for finding in issues
        ],
        key=lambda item: _audit_rank(item, command),
    )

def _audit_fix_plan_markdown(report: dict) -> str:
    translation = report.get("translation") or {}
    fix_plan = translation.get("fix_plan") or report.get("fix_plan") or _audit_fix_plan(report)
    issues = translation.get("critical_issues") or report.get("critical_issues") or _audit_critical_issues(report.get("findings", []), str(report.get("command", "")))
    lines = [
        "# Fix Plan",
        "",
        f"- Command: `{report.get('command', '')}`",
        f"- Scope: `{report.get('scope') or ''}`",
        f"- Generated at: `{report.get('generated_at', '')}`",
        "",
        "## Critical Issues",
    ]
    if not issues:
        lines.append("_No critical issues._")
    else:
        for issue in issues:
            lines.append(f"- **{issue.get('title', issue.get('id', 'issue'))}**")
            if issue.get("impact"):
                lines.append(f"  - Impact: {issue['impact']}")
            if issue.get("details"):
                lines.append(f"  - Evidence: {issue['details']}")
    lines.extend(["", "## Fix Order"])
    steps = fix_plan.get("steps", [])
    if not steps:
        lines.append("_No ordered fixes available._")
    else:
        for step in steps:
            lines.append(f"{step.get('step', '?')}. {step.get('title', 'Issue')}")
            if step.get("impact"):
                lines.append(f"   - Impact: {step['impact']}")
            if step.get("evidence"):
                lines.append(f"   - Evidence: {step['evidence']}")
            if step.get("action"):
                lines.append(f"   - Action: {step['action']}")
    lines.extend(["", "## Codex Prompt", "", "```text", fix_plan.get("codex_prompt", "").rstrip(), "```"])
    return "\n".join(lines).rstrip() + "\n"


def _audit_summary_lines(summary: dict, command: str) -> list[str]:
    if command == "verify":
        by_status = summary.get("by_status", {})
        return [
            f"{status}: {by_status.get(status, 0)}"
            for status in ("VERIFIED", "DOC_ONLY", "CONFLICT", "UNKNOWN")
        ]
    lines = []
    for key in ("tracked_files", "total_bytes", "primary_stack", "files_with_signals", "top_signal_categories"):
        if key in summary:
            lines.append(f"{key}: {summary[key]}")
    if not lines:
        lines.append("No summary details available.")
    return lines


def _audit_fix_plan(report: dict) -> dict:
    command = str(report.get("command", "inspect"))
    critical = _audit_critical_issues(report.get("findings", []), command)
    steps: list[dict] = []
    for idx, issue in enumerate(critical, start=1):
        steps.append({
            "step": idx,
            "title": issue.get("title") or issue.get("id") or "Issue",
            "impact": issue.get("impact", ""),
            "action": issue.get("recommendation") or "Investigate and resolve the issue.",
            "evidence": issue.get("details") or ", ".join(issue.get("evidence", [])),
        })
    prompt_lines = [
        "You are Codex helping fix the highest-priority issues from a read-only context-kit audit.",
        f"Audit command: {report.get('command', '')}",
        f"Scope: {report.get('scope') or '(none)'}",
        "",
        "Critical issues:",
    ]
    if steps:
        for step in steps:
            prompt_lines.append(f"- {step['step']}. {step['title']} — {step['impact']}")
    else:
        prompt_lines.append("- None. Confirm the repo is in good shape and summarize the next safe checks.")
    prompt_lines.extend([
        "",
        "Instructions:",
        "1. Work in order.",
        "2. Start with the highest-impact issue.",
        "3. Keep changes read-only until you have a concrete fix plan.",
        "4. Prefer small, reversible edits.",
        "5. Report what changed, what remains open, and any follow-up checks.",
    ])
    return {
        "summary": {
            "critical_count": len(steps),
            "command": report.get("command"),
            "scope": report.get("scope"),
        },
        "steps": steps,
        "codex_prompt": "\n".join(prompt_lines).rstrip() + "\n",
    }


def _audit_normalize_audience(audience: str | None) -> str:
    normalized = (audience or "developer").strip().lower()
    if normalized not in _audit_supported_audiences():
        raise ValueError(f"unknown audit audience: {audience!r}")
    return normalized


def _audit_audience_label(audience: str) -> str:
    return {
        "developer": "technical",
        "founder": "strategic",
        "business": "business-facing",
    }.get(audience, "technical")


def _audit_audience_impact_text(finding: dict, audience: str) -> str:
    raw = str(finding.get("impact") or "").strip()
    command = str(finding.get("command", ""))
    if command == "full":
        command = str(finding.get("command_source", finding.get("command", "")))
    category = str(finding.get("category", "")).lower()
    title = str(finding.get("title", "")).lower()
    route_role = str(finding.get("route_role", "")).lower()
    severity = str(finding.get("severity", finding.get("status", ""))).lower()

    if not raw:
        if command == "doctor":
            raw = "This setup signal needs review."
        elif command == "connections":
            raw = "This wiring signal needs review."
        else:
            raw = "This signal needs review."

    if "missing backend endpoint" in title or (category == "missing_target" and "backend endpoint" in title):
        if audience == "founder":
            return "High business impact: a customer or internal journey may fail because a linked backend route is missing."
        if audience == "business":
            return "High operational impact: a visible workflow can fail when the client points at a route that does not exist."
        return "High technical impact: the client references a backend route that the server does not expose."

    if any(token in " ".join((title, raw, category)) for token in ("fallback", "degraded", "failure")):
        if audience == "founder":
            return "Medium business impact: the product may be relying on a degraded path, which can hide reliability issues."
        if audience == "business":
            return "Medium operational impact: the system appears to be using a fallback or degraded path."
        return "Medium technical impact: the current path looks degraded or may be masking a failure."

    if "dynamic reference" in title or category == "unknown_dynamic_reference":
        if audience == "founder":
            return "Low business impact: this needs human confirmation, but it is not yet a blocker."
        if audience == "business":
            return "Low operational impact: this is a confirmation item rather than an immediate blocker."
        return "Low technical impact: the reference is dynamic and needs manual confirmation."

    if category == "orphaned_route" and route_role in {"admin", "health", "monitoring", "internal_api", "docs"}:
        if audience == "founder":
            return "Advisory impact: this route is likely operational or internal, so it does not look customer-facing."
        if audience == "business":
            return "Advisory impact: this looks like an internal or support route rather than a direct customer risk."
        return "Advisory impact: this route is intentionally internal, operational, or documentation-facing."

    if audience == "founder":
        if severity == "high":
            return f"High business impact: {raw}"
        if severity == "medium":
            return f"Medium business impact: {raw}"
        return f"Low business impact: {raw}"
    if audience == "business":
        if severity == "high":
            return f"High operational impact: {raw}"
        if severity == "medium":
            return f"Medium operational impact: {raw}"
        return f"Low operational impact: {raw}"
    return raw


def _audit_audience_explanation(finding: dict, audience: str) -> str:
    title = str(finding.get("title") or finding.get("id") or "Issue")
    details = str(finding.get("details", "")).strip()
    command = str(finding.get("command", ""))
    if audience == "founder":
        prefix = "This is a product or delivery risk"
    elif audience == "business":
        prefix = "This is an operational or commercial risk"
    else:
        prefix = "This is a technical issue"
    if command == "connections" and "Missing backend endpoint" in title:
        prefix = {
            "developer": "The client points to a route the server does not expose.",
            "founder": "A key workflow may break because the client calls a route that does not exist.",
            "business": "A user-facing or internal workflow may break because the route is missing.",
        }.get(audience, prefix)
    if details:
        return f"{prefix}. Evidence: {details}"
    return f"{prefix}."


def _audit_audience_tone(audience: str) -> str:
    return {
        "developer": "technical",
        "founder": "strategic",
        "business": "business-facing",
    }.get(audience, "technical")


def _audit_findings_text(findings: list[dict]) -> str:
    return " ".join(
        " ".join(
            str(finding.get(key, ""))
            for key in ("category", "title", "details", "recommendation", "impact")
        )
        for finding in findings
    ).lower()


def _audit_detect_external_config_issues(findings: list[dict]) -> bool:
    text = _audit_findings_text(findings)
    return any(token in text for token in (
        "config", "configuration", "env", "environment", "settings", "secrets", "credentials",
        "deployment", "manifest", "docker", "kubernetes", "helm", "toml", "yaml", "yml", "json", "ini",
    ))


def _audit_detect_failure_or_degraded_states(findings: list[dict]) -> bool:
    text = _audit_findings_text(findings)
    return any(token in text for token in ("failure", "failed", "degraded", "degradation", "fallback", "broken"))


def _audit_risk_level(report: dict) -> str:
    findings = report.get("critical_issues") or _audit_critical_issues(report.get("findings", []), str(report.get("command", "")))
    critical_count = len(findings)
    external_config = _audit_detect_external_config_issues(findings)
    degraded = _audit_detect_failure_or_degraded_states(findings)

    if critical_count >= 3:
        return "High"

    score = 0
    if critical_count >= 2:
        score += 2
    elif critical_count == 1:
        score += 1

    if external_config:
        score += 1
    if degraded:
        score += 2

    if score >= 3:
        return "High"
    if score >= 1:
        return "Medium"
    return "Low"


def _audit_recommendation_for_risk(risk_level: str) -> str:
    return {
        "High": "Fix before production.",
        "Medium": "Plan and address before the next release.",
        "Low": "Monitor and address during normal maintenance.",
    }.get(risk_level, "Monitor and address during normal maintenance.")


def _audit_summary_description(audience: str, risk_level: str, critical_count: int, external_config: bool, degraded: bool) -> str:
    if audience == "founder":
        base = "This is a product risk summary."
        if risk_level == "High":
            risk_text = "The audit shows high product risk that could affect customers or delivery."
        elif risk_level == "Medium":
            risk_text = "The audit shows material product risk that should be handled before the next release."
        else:
            risk_text = "The audit shows limited product risk and mostly maintenance-level follow-up."
    elif audience == "business":
        base = "This is an operational risk summary."
        if risk_level == "High":
            risk_text = "The audit shows high operational risk that could affect reliability or support load."
        elif risk_level == "Medium":
            risk_text = "The audit shows material operational risk that should be resolved before the next release."
        else:
            risk_text = "The audit shows limited operational risk and mostly routine follow-up."
    else:
        base = "This is a technical risk summary."
        if risk_level == "High":
            risk_text = "The audit shows blocking technical gaps that should be fixed before production."
        elif risk_level == "Medium":
            risk_text = "The audit shows meaningful technical gaps that should be addressed soon."
        else:
            risk_text = "The audit shows limited technical risk and mostly cleanup work."

    extras: list[str] = [f"{critical_count} critical issue(s)."]
    if external_config:
        extras.append("External config issues are present.")
    if degraded:
        extras.append("Failure or degraded states were detected.")
    return f"{base} {risk_text} {' '.join(extras)}".strip()


def _audit_executive_summary(report: dict, audience: str) -> dict:
    findings = report.get("critical_issues") or _audit_critical_issues(report.get("findings", []), str(report.get("command", "")))
    critical_count = len(findings)
    risk_level = _audit_risk_level(report)
    external_config = _audit_detect_external_config_issues(findings)
    degraded = _audit_detect_failure_or_degraded_states(findings)
    description = _audit_summary_description(audience, risk_level, critical_count, external_config, degraded)
    return {
        "critical_count": critical_count,
        "risk_level": risk_level,
        "description": description,
        "recommendation": _audit_recommendation_for_risk(risk_level),
        "audience": audience,
        "tone": _audit_audience_tone(audience),
        "external_config_issues": external_config,
        "degraded_states": degraded,
    }


def _audit_translate_fix_prompt(report: dict, audience: str, critical: list[dict], steps: list[dict]) -> str:
    if audience == "founder":
        intro = "You are Codex helping resolve the highest-priority product and delivery risks from a read-only context-kit audit."
        focus = "Focus on customer impact, delivery risk, and quick wins."
    elif audience == "business":
        intro = "You are Codex helping resolve the highest-priority operational and commercial risks from a read-only context-kit audit."
        focus = "Focus on business impact, operational risk, and practical remediation."
    else:
        intro = "You are Codex helping fix the highest-priority issues from a read-only context-kit audit."
        focus = "Focus on technical correctness, small reversible changes, and implementation order."

    prompt_lines = [
        intro,
        f"Audience: {audience}",
        f"Audit command: {report.get('command', '')}",
        f"Scope: {report.get('scope') or '(none)'}",
        "",
        "Critical issues:",
    ]
    if steps:
        for step in steps:
            prompt_lines.append(f"- {step['step']}. {step['title']} — {step['impact']}")
    elif critical:
        for idx, issue in enumerate(critical, start=1):
            prompt_lines.append(f"- {idx}. {issue.get('title', issue.get('id', 'Issue'))} — {issue.get('impact', '')}")
    else:
        prompt_lines.append("- None. Confirm the repo is in good shape and summarize the next safe checks.")
    prompt_lines.extend([
        "",
        "Instructions:",
        "1. Work in order.",
        "2. Start with the highest-impact issue.",
        "3. Keep changes read-only until you have a concrete fix plan.",
        "4. Prefer small, reversible edits.",
        "5. Report what changed, what remains open, and any follow-up checks.",
        f"Tone: {focus}",
    ])
    return "\n".join(prompt_lines).rstrip() + "\n"


def _audit_translate_report(report: dict, audience: str | None) -> dict:
    normalized = _audit_normalize_audience(audience)
    critical = report.get("critical_issues") or _audit_critical_issues(report.get("findings", []), str(report.get("command", "")))
    fix_plan = report.get("fix_plan") or _audit_fix_plan(report)
    executive_summary = _audit_executive_summary(report, normalized)
    translated_critical = [
        {
            **issue,
            "command_source": issue.get("command", report.get("command", "")),
            "explanation": _audit_audience_explanation({**issue, "command": issue.get("command", report.get("command", ""))}, normalized),
            "impact": _audit_audience_impact_text({**issue, "command": issue.get("command", report.get("command", "")), "command_source": report.get("command", "")}, normalized),
            "tone": _audit_audience_tone(normalized),
        }
        for issue in critical
    ]
    translated_steps = [
        {
            **step,
            "command_source": step.get("command", report.get("command", "")),
            "explanation": _audit_audience_explanation({**step, "command": step.get("command", report.get("command", ""))}, normalized),
            "impact": _audit_audience_impact_text({**step, "command": step.get("command", report.get("command", "")), "command_source": report.get("command", "")}, normalized),
            "tone": _audit_audience_tone(normalized),
            "action": step.get("action") or "Investigate and resolve the issue.",
        }
        for step in fix_plan.get("steps", [])
    ]
    translated_fix_plan = {
        **fix_plan,
        "steps": translated_steps,
        "codex_prompt": _audit_translate_fix_prompt(report, normalized, translated_critical, translated_steps),
    }
    translation = {
        "audience": normalized,
        "executive_summary": executive_summary,
        "critical_issues": translated_critical,
        "fix_plan": translated_fix_plan,
        "summary": {
            "critical_count": len(translated_critical),
            "audience": normalized,
            "tone": _audit_audience_tone(normalized),
            "risk_level": executive_summary["risk_level"],
            "recommendation": executive_summary["recommendation"],
        },
    }
    return {
        **report,
        "audience": normalized,
        "risk_level": executive_summary["risk_level"],
        "translation": translation,
    }


def _normalize_audit_inspect(project: Path, options: dict) -> dict:
    from cli.inspect import _inspect, _to_json as _inspect_to_json

    result = _inspect(
        project,
        depth=options.get("depth", 2),
        scope=options.get("scope"),
        include_related=options.get("include_related", False),
        include_history=options.get("include_history", False),
    )
    raw_json = _inspect_to_json(result)
    findings = [
        {
            "id": risk["id"],
            "title": risk["summary"],
            "severity": risk["severity"],
            "status": risk["severity"],
            "impact": _audit_impact(risk, "inspect"),
            "details": "; ".join(risk.get("evidence", [])),
            "evidence": risk.get("evidence", []),
            "recommendation": next(
                (rec["suggestion"] for rec in raw_json.get("recommendations", []) if rec["id"] == risk["id"]),
                "",
            ),
        }
        for risk in raw_json.get("risks", [])
    ]
    warnings = [
        rec["suggestion"]
        for rec in raw_json.get("recommendations", [])[:5]
        if rec.get("suggestion")
    ]
    report = {
        "command": "inspect",
        "scope": options.get("scope"),
        "status": "warning" if findings else "ok",
        "summary": {
            **raw_json.get("counts", {}),
            "primary_stack": raw_json.get("primary_stack", {}),
            "risk_count": len(findings),
            "recommendation_count": len(warnings),
        },
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "inspect"),
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": raw_json if options.get("include_raw_json", False) else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _normalize_audit_verify(project: Path, options: dict) -> dict:
    from cli.verify import collect_verification

    report = collect_verification(
        project,
        include_archive=options.get("include_archive", False),
        all_docs=options.get("all_docs", False),
    )
    raw_json = asdict(report)
    findings = [
        {
            "id": finding["id"],
            "title": finding["title"],
            "status": finding["status"],
            "severity": finding["status"].lower(),
            "impact": _audit_impact(finding, "verify"),
            "details": finding.get("details", ""),
            "evidence": finding.get("evidence", []),
            "recommendation": finding.get("recommendation", ""),
        }
        for finding in raw_json.get("findings", [])
    ]
    warnings = [
        f"{finding['status']}: {finding['title']}"
        for finding in raw_json.get("findings", [])
        if finding.get("status") != "VERIFIED"
    ]
    report = {
        "command": "verify",
        "scope": None,
        "status": "warning" if findings else "ok",
        "summary": raw_json.get("summary", {}),
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "verify"),
        "warnings": warnings,
        "generated_at": raw_json.get("generated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": raw_json if options.get("include_raw_json", False) else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _normalize_audit_coverage(project: Path, options: dict) -> dict:
    from cli.coverage import _coverage

    scope = options.get("scope")
    raw_json = _coverage(project, scope=scope)
    findings: list[dict] = []
    summary = raw_json.get("summary", {})
    unknown_files = int(summary.get("unknown_files", 0) or 0)
    unknown_bytes = int(summary.get("unknown_bytes", 0) or 0)
    coverage_pct = float(summary.get("coverage_files_pct", 0.0) or 0.0)
    if unknown_files:
        severity = "high" if unknown_bytes >= 50_000 or coverage_pct < 80 else "medium"
        findings.append({
            "id": "coverage-unknown-files",
            "title": "Unclassified files remain",
            "severity": severity,
            "status": severity,
            "category": "unknown_coverage",
            "details": f"{unknown_files} files ({unknown_bytes} bytes) are still unclassified.",
            "evidence": [row["path"] for row in raw_json.get("unclassified_hot_files", [])[:5]],
            "recommendation": "Classify the remaining files or confirm they are intentionally outside the audit surface.",
        })
    for row in raw_json.get("by_top_directory", [])[:3]:
        if row.get("files", 0):
            findings.append({
                "id": f"coverage-unknown-dir:{row['path']}",
                "title": "Unknown directory hotspot",
                "severity": "medium",
                "status": "medium",
                "category": "unknown_coverage",
                "details": f"{row['path']} has {row.get('files', 0)} unclassified files.",
                "evidence": [f"{row['path']}: {row.get('files', 0)} files"],
                "recommendation": "Review the directory and decide whether it should be covered by inventory heuristics.",
            })
    report = {
        "command": "coverage",
        "scope": scope,
        "status": "warning" if findings else "ok",
        "summary": summary,
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "coverage"),
        "warnings": [f"Coverage remaining: {coverage_pct:.1f}%"] if findings else [],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": raw_json if options.get("include_raw_json", False) else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _normalize_audit_behavior(project: Path, options: dict) -> dict:
    from cli.behavior import collect_behavior, _to_json as _behavior_to_json

    scope = options.get("scope")
    raw_report = collect_behavior(project, scope=scope)
    raw_json = _behavior_to_json(raw_report)
    findings: list[dict] = []
    for item in raw_json.get("top_files", []):
        if not item.get("categories"):
            continue
        score = int(item.get("risk_score", 0) or 0)
        severity = "high" if score >= 4 else "medium" if score >= 2 else "advisory"
        findings.append({
            "id": f"behavior:{item['path']}",
            "title": item["path"],
            "severity": severity,
            "status": severity,
            "category": "behavior_risk",
            "details": ", ".join(item.get("categories", [])),
            "evidence": item.get("evidence", []),
            "recommendation": "Review the file for orchestration, dispatch, or mutation risk.",
        })
    report = {
        "command": "behavior",
        "scope": scope,
        "status": "warning" if findings else "ok",
        "summary": raw_json.get("summary", {}),
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "behavior"),
        "warnings": [rec["suggestion"] for rec in raw_json.get("recommendations", [])[:5] if rec.get("suggestion")],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": raw_json if options.get("include_raw_json", False) else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _normalize_audit_connections(project: Path, options: dict) -> dict:
    from cli.connections import collect_connections, _to_json as _connections_to_json

    scope = options.get("scope")
    raw_report = collect_connections(project, scope=scope)
    raw_json = _connections_to_json(raw_report)
    findings = [
        {
            **item,
            "impact": _audit_impact(item, "connections"),
            "severity": item.get("severity", "advisory"),
            "status": item.get("severity", "advisory"),
        }
        for item in raw_json.get("findings", [])
    ]
    report = {
        "command": "connections",
        "scope": scope,
        "status": "warning" if findings else "ok",
        "summary": raw_json.get("summary", {}),
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "connections"),
        "warnings": [
            finding["details"]
            for finding in findings
            if finding.get("severity") in {"medium", "advisory"}
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": raw_json if options.get("include_raw_json", False) else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _normalize_audit_doctor(project: Path, options: dict) -> dict:
    from cli.doctor import run_all_checks

    checks = run_all_checks(project)
    raw_json = {
        "project_path": str(project),
        "summary": {
            "ok": sum(1 for r in checks if r.status == "ok"),
            "warnings": sum(1 for r in checks if r.status == "warning"),
            "blocking": sum(1 for r in checks if r.status == "blocking"),
            "skipped": sum(1 for r in checks if r.status == "skipped"),
        },
        "exit_code": 1 if any(r.status == "blocking" for r in checks) else 0,
        "checks": [asdict(r) for r in checks],
    }
    findings: list[dict] = []
    for item in raw_json["checks"]:
        if item.get("status") == "ok":
            continue
        findings.append({
            "id": item["id"],
            "title": item["label"],
            "status": item["status"],
            "severity": item["status"],
            "category": "doctor_check",
            "details": item["detail"],
            "evidence": item.get("fix", []) if isinstance(item.get("fix"), list) else ([item["fix"]] if item.get("fix") else []),
            "recommendation": "; ".join(item.get("fix", [])) if isinstance(item.get("fix"), list) else (item.get("fix") or ""),
        })
    report = {
        "command": "doctor",
        "scope": None,
        "status": "warning" if findings else "ok",
        "summary": raw_json["summary"],
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "doctor"),
        "warnings": [finding["details"] for finding in findings if finding.get("status") == "warning"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": raw_json if options.get("include_raw_json", False) else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _audit_run_full(project: Path, payload: dict) -> dict:
    scope = payload.get("scope")
    audience = payload.get("audience")
    include_raw_json = bool(payload.get("include_raw_json", False))
    run_order = [
        ("inspect", {"depth": payload.get("depth", 2), "include_history": bool(payload.get("include_history", False)), "include_related": bool(payload.get("include_related", False)), "include_raw_json": include_raw_json}),
        ("coverage", {"include_raw_json": include_raw_json}),
        ("behavior", {"include_raw_json": include_raw_json}),
        ("connections", {"include_raw_json": include_raw_json}),
        ("verify", {"include_archive": bool(payload.get("include_archive", False)), "all_docs": bool(payload.get("all_docs", False)), "include_raw_json": include_raw_json}),
    ]
    reports: dict[str, dict] = {}
    for command, options in run_order:
        command_payload = {"command": command, **options}
        if command in {"inspect", "coverage", "behavior", "connections"} and scope is not None:
            if command == "connections":
                from cli.connections import _CONNECTION_SCOPES

                if scope in _CONNECTION_SCOPES:
                    command_payload["scope"] = scope
            else:
                from cli.inspect import _INSPECT_SCOPES

                if scope in _INSPECT_SCOPES:
                    command_payload["scope"] = scope
        if audience is not None:
            command_payload["audience"] = audience
        reports[command] = _audit_run(project, command_payload)

    findings: list[dict] = []
    warnings: list[str] = []
    for command in ("inspect", "coverage", "behavior", "connections", "verify"):
        report = reports[command]
        for finding in report.get("findings", []):
            findings.append({**finding, "command": command})
        warnings.extend([f"{command}: {warning}" for warning in report.get("warnings", [])])

    summary = {
        "commands": {
            command: reports[command].get("summary", {})
            for command in ("inspect", "coverage", "behavior", "connections", "verify")
        },
        "findings_total": len(findings),
        "critical_count": len(_audit_critical_issues(findings, "full")),
    }
    report = {
        "command": "full",
        "scope": scope,
        "status": "warning" if findings else "ok",
        "summary": summary,
        "findings": findings,
        "critical_issues": _audit_critical_issues(findings, "full"),
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "raw_json": reports if include_raw_json else None,
    }
    report["fix_plan"] = _audit_fix_plan(report)
    return report


def _audit_run(project: Path, payload: dict) -> dict:
    command = payload.get("command", "inspect")
    audience = payload.get("audience")
    if command not in _audit_supported_commands():
        if command == "full":
            return _audit_translate_report(_audit_run_full(project, payload), audience)
        raise ValueError(f"unknown audit command: {command!r}")

    scope = payload.get("scope")
    if command == "inspect":
        if scope is not None and scope not in _audit_command_scopes("inspect"):
            raise ValueError(f"unknown inspect scope: {scope!r}")
        return _audit_translate_report(_normalize_audit_inspect(project, {
            "depth": payload.get("depth", 2),
            "scope": scope,
            "include_history": bool(payload.get("include_history", False)),
            "include_related": bool(payload.get("include_related", False)),
            "include_raw_json": bool(payload.get("include_raw_json", False)),
        }), audience)

    if command == "verify":
        if scope is not None:
            raise ValueError("verify does not support scope")
        return _audit_translate_report(_normalize_audit_verify(project, {
            "include_archive": bool(payload.get("include_archive", False)),
            "all_docs": bool(payload.get("all_docs", False)),
            "include_raw_json": bool(payload.get("include_raw_json", False)),
        }), audience)

    if scope is not None and scope not in _audit_command_scopes(command):
        raise ValueError(f"unknown {command} scope: {scope!r}")

    if command == "coverage":
        return _audit_translate_report(_normalize_audit_coverage(project, {
            "scope": scope,
            "include_raw_json": bool(payload.get("include_raw_json", False)),
        }), audience)
    if command == "behavior":
        return _audit_translate_report(_normalize_audit_behavior(project, {
            "scope": scope,
            "include_raw_json": bool(payload.get("include_raw_json", False)),
        }), audience)
    if command == "connections":
        return _audit_translate_report(_normalize_audit_connections(project, {
            "scope": scope,
            "include_raw_json": bool(payload.get("include_raw_json", False)),
        }), audience)
    if command == "doctor":
        if scope is not None:
            raise ValueError("doctor does not support scope")
        return _audit_translate_report(_normalize_audit_doctor(project, {
            "include_raw_json": bool(payload.get("include_raw_json", False)),
        }), audience)

    if scope is not None:
        raise ValueError("verify does not support scope")
    return _audit_translate_report(_normalize_audit_verify(project, {
        "include_archive": bool(payload.get("include_archive", False)),
        "all_docs": bool(payload.get("all_docs", False)),
        "include_raw_json": bool(payload.get("include_raw_json", False)),
    }), audience)


def _audit_report_json(report: dict | None) -> dict:
    if report is None:
        raise LookupError("no audit report has been generated yet")
    return report


def _audit_report_markdown(report: dict) -> str:
    translation = report.get("translation") or {}
    if translation:
        report = {
            **report,
            "critical_issues": translation.get("critical_issues") or report.get("critical_issues"),
            "fix_plan": translation.get("fix_plan") or report.get("fix_plan"),
        }
    lines = [
        "# Audit Report",
        "",
        f"- Command: `{report.get('command', '')}`",
        f"- Scope: `{report.get('scope') or ''}`",
        f"- Status: `{report.get('status', '')}`",
        f"- Generated at: `{report.get('generated_at', '')}`",
        "",
    ]
    if translation.get("executive_summary"):
        exec_summary = translation["executive_summary"]
        lines.extend([
            "## Executive Summary",
            "",
            f"- Risk Level: `{exec_summary.get('risk_level', '')}`",
            f"- Critical Issues: `{exec_summary.get('critical_count', 0)}`",
            f"- Recommendation: {exec_summary.get('recommendation', '')}",
            f"- Summary: {exec_summary.get('description', '')}",
            "",
        ])
    lines.extend([
        "## Summary",
        "",
    ])
    for line in _audit_summary_lines(report.get("summary", {}), str(report.get("command", ""))):
        lines.append(f"- {line}")
    lines.extend(["", "## Findings"])
    findings = report.get("findings", [])
    if not findings:
        lines.append("_No findings._")
    else:
        for finding in findings:
            lines.append(f"- **{finding.get('title', finding.get('id', 'finding'))}**")
            if finding.get("details"):
                lines.append(f"  - {finding['details']}")
    lines.extend(["", "## Critical Issues"])
    issues = report.get("critical_issues") or _audit_critical_issues(findings, str(report.get("command", "")))
    if not issues:
        lines.append("_No critical issues._")
    else:
        for issue in issues[:10]:
            lines.append(f"- **{issue.get('title', issue.get('id', 'issue'))}**")
            if issue.get("impact"):
                lines.append(f"  - Impact: {issue['impact']}")
            if issue.get("details"):
                lines.append(f"  - {issue['details']}")
    fix_plan = report.get("fix_plan")
    if fix_plan:
        lines.extend(["", "## Fix Plan", ""])
        for step in fix_plan.get("steps", []):
            lines.append(f"{step.get('step', '?')}. {step.get('title', 'Issue')}")
            if step.get("impact"):
                lines.append(f"   - Impact: {step['impact']}")
            if step.get("action"):
                lines.append(f"   - Action: {step['action']}")
        lines.extend(["", "## Codex Prompt", "", "```text", fix_plan.get("codex_prompt", "").rstrip(), "```"])
    return "\n".join(lines).rstrip() + "\n"


class _OnboardingHandler(http.server.BaseHTTPRequestHandler):
    """Routes:

    - ``/``, ``/index.html``               existing project-view page
    - ``/wizard``                          beginner wizard HTML
    - ``/audit``                           read-only audit dashboard
    - ``GET  /api/state``                  JSON classify cwd
    - ``GET  /api/check?step=...&...``     JSON poll filesystem
    - ``POST /api/idea``                   write idea.md to a project subdir
    - ``GET  /api/audit/state``            audit dashboard metadata
    - ``POST /api/audit/run``              run inspect / verify audits
    - ``GET  /api/audit/report``           fetch the last audit report

    Per-route handler context lives on ``self.server``:
    - ``onboarding_html``  pre-rendered HTML for ``/``
    - ``wizard_html``      pre-loaded HTML for ``/wizard`` (or fallback)
    - ``audit_html``       pre-loaded HTML for ``/audit`` (or fallback)
    - ``cwd``              the cwd ``run_start`` was invoked from
    - ``audit_report``     last generated audit report dict, if any
    """

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._send_html(getattr(self.server, "onboarding_html", ""))
            return
        if path == "/wizard":
            wizard = getattr(self.server, "wizard_html", None)
            if wizard:
                self._send_html(wizard)
            else:
                # No wizard available (running from a generated project's
                # local cli/ which doesn't ship _static/). Send a friendly
                # redirect-style note rather than 404.
                self._send_html(
                    "<!doctype html><meta charset=utf-8>"
                    "<title>Wizard not available</title>"
                    "<body style='font-family:system-ui;max-width:40rem;"
                    "margin:3rem auto;padding:0 1rem'>"
                    "<h1>Wizard not available here</h1>"
                    "<p>The beginner wizard ships in the installed "
                    "<code>contextkit-ai</code> package but not in a "
                    "generated project's local copy. <a href='/'>Open the "
                    "project view instead</a>.</p></body>"
                )
            return
        if path == "/audit":
            audit = getattr(self.server, "audit_html", None)
            if audit:
                self._send_html(audit)
            else:
                cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
                self._send_html(_render_audit_html(cwd, getattr(self.server, "audit_url", "/audit")))
            return
        if path == "/api/state":
            self._handle_api_state()
            return
        if path == "/api/check":
            params = urllib.parse.parse_qs(query)
            self._handle_api_check(params)
            return
        if path == "/api/audit/state":
            self._handle_api_audit_state()
            return
        if path == "/api/audit/report":
            params = urllib.parse.parse_qs(query)
            self._handle_api_audit_report(params)
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802 — http.server API
        path, _, _ = self.path.partition("?")
        if path == "/api/idea":
            self._handle_api_idea()
            return
        if path == "/api/audit/run":
            self._handle_api_audit_run()
            return
        self.send_error(404, "Not Found")

    # ---- handlers -----------------------------------------------------

    def _handle_api_state(self) -> None:
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        state = _detect_project_state(cwd)
        if state == "none":
            suggested = "welcome"
        elif state == "scaffold":
            suggested = "recommend-stack"
        else:
            suggested = "open-existing"
        self._send_json({
            "cwd": str(cwd),
            "project_state": state,
            "suggested_step": suggested,
            "detected_projects": _scan_for_projects(cwd),
        })

    def _handle_api_audit_state(self) -> None:
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        last = getattr(self.server, "audit_report", None)
        self._send_json({
            "cwd": str(cwd),
            "default_path": ".",
            "supported_audiences": list(_audit_supported_audiences()),
            "supported_commands": list(_audit_supported_commands()),
            "supported_scopes": list(_audit_supported_scopes()),
            "last_run": {
                key: last.get(key)
                for key in ("command", "scope", "audience", "risk_level", "status", "generated_at", "summary")
            } if isinstance(last, dict) else None,
        })

    def _handle_api_audit_run(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error_json(400, "invalid Content-Length")
            return
        if length < 0 or length > 256_000:
            self._send_error_json(400, "request body must be 0..256000 bytes")
            return
        payload: dict
        if length == 0:
            payload = {}
        else:
            try:
                payload = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                self._send_error_json(400, "request body is not valid JSON")
                return
        if not isinstance(payload, dict):
            self._send_error_json(400, "request body must be a JSON object")
            return
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        path_value = payload.get("path", ".")
        if not isinstance(path_value, str):
            self._send_error_json(400, "path must be a string")
            return
        try:
            target = _safe_project_path(cwd, path_value)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        if not target.is_dir():
            self._send_error_json(400, f"{target} is not a directory")
            return
        try:
            report = _audit_run(target, payload)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        self.server.audit_report = report  # type: ignore[attr-defined]
        self._send_json(report)

    def _handle_api_audit_report(self, params: dict) -> None:
        fmt = (params.get("format") or ["json"])[0]
        report = getattr(self.server, "audit_report", None)
        try:
            report = _audit_report_json(report)
        except LookupError as exc:
            self._send_error_json(404, str(exc))
            return
        if fmt == "json":
            self._send_json(report)
            return
        if fmt == "markdown":
            body = _audit_report_markdown(report)
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if fmt == "fix-plan-md":
            body = _audit_fix_plan_markdown(report)
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        self._send_error_json(400, f"unsupported format: {fmt!r}")

    def _handle_api_idea(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error_json(400, "invalid Content-Length")
            return
        if length <= 0 or length > 256_000:
            self._send_error_json(400, "request body must be 1..256000 bytes")
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_error_json(400, "request body is not valid JSON")
            return
        project_dir = payload.get("project_dir", "")
        content = payload.get("content", "")
        if not isinstance(project_dir, str) or not isinstance(content, str):
            self._send_error_json(400, "project_dir and content must be strings")
            return
        if not content.strip():
            self._send_error_json(400, "content is empty")
            return
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        try:
            target_dir = _safe_project_path(cwd, project_dir)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "idea.md"
            tmp = target.with_suffix(".md.tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            self._send_error_json(500, f"failed to write idea.md: {exc}")
            return
        self._send_json({"written": True, "path": str(target)})

    def _handle_api_check(self, params: dict) -> None:
        step = (params.get("step") or [""])[0]
        project_dir = (params.get("project_dir") or ["."])[0]
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        try:
            target_dir = _safe_project_path(cwd, project_dir)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        if step == "init":
            target_file = target_dir / "00-START-NEXT-SESSION.md"
            satisfied = target_file.is_file()
            reason = (
                f"00-START-NEXT-SESSION.md present in {target_dir}"
                if satisfied
                else f"00-START-NEXT-SESSION.md not found in {target_dir}"
            )
        elif step == "seed":
            target_file = target_dir / "docs" / "BUILD_PLAN.md"
            satisfied = target_file.is_file()
            reason = (
                f"docs/BUILD_PLAN.md present in {target_dir}"
                if satisfied
                else f"docs/BUILD_PLAN.md not found in {target_dir}"
            )
        else:
            self._send_error_json(400, f"unknown step: {step!r} (expected init|seed)")
            return
        self._send_json({"satisfied": satisfied, "reason": reason})

    # ---- low-level send helpers --------------------------------------

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - shadow OK
        # Silence the default per-request access log. Parameter names must
        # match ``BaseHTTPRequestHandler.log_message`` exactly; ``del``
        # marks them intentionally unused.
        del format, args


def run_start(args: argparse.Namespace) -> int:
    """Entry point for the ``start`` subcommand dispatched from context_kit.py."""
    project_root = Path.cwd().resolve()

    port = _pick_port(args.port, args.host)
    base_url = f"http://{args.host}:{port}"
    body = _render_html(project_root, base_url + "/")
    wizard_body = _load_wizard_html()
    audit_body = _render_audit_html(project_root, base_url + "/audit")

    # Decide which page to open in the browser. If we're in a fresh dir
    # (no project markers), the wizard is the right beginner entry. If
    # a project is already seeded, open the existing project view.
    state = _detect_project_state(project_root)
    if state in ("none", "scaffold") and wizard_body:
        landing_path = "/wizard"
    else:
        landing_path = "/"
    landing_url = base_url + landing_path

    # Only warn when the user landed on the project view but the dir
    # doesn't actually look like a project. (When the wizard is opening,
    # "no project here yet" is the expected state, not a warning.)
    if landing_path == "/" and state == "none":
        sys.stderr.write(
            f"warning: {project_root} does not look like a context-kit project "
            f"(no 00-START-NEXT-SESSION.md or docs/docs-pattern/ found). "
            f"Continuing anyway.\n"
        )

    server = http.server.HTTPServer((args.host, port), _OnboardingHandler)
    # Attach handler context (read in the request handler off self.server).
    server.onboarding_html = body  # type: ignore[attr-defined]
    server.wizard_html = wizard_body  # type: ignore[attr-defined]
    server.audit_html = audit_body  # type: ignore[attr-defined]
    server.audit_url = base_url + "/audit"  # type: ignore[attr-defined]
    server.audit_report = None  # type: ignore[attr-defined]
    server.cwd = project_root  # type: ignore[attr-defined]

    print(f"context-kit: server running at {base_url}")
    print(f"context-kit: opening {landing_url}")
    print("context-kit: press Ctrl+C to stop.")

    if not args.no_browser:
        try:
            webbrowser.open(landing_url)
        except Exception:  # pragma: no cover — webbrowser is best-effort
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncontext-kit: shutting down.")
    finally:
        server.server_close()

    return 0
