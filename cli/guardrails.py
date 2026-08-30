"""context-kit ``guardrails`` subcommand: a portable CI drift gate.

Extracted from the ``unified-donkey-betz`` guardrails pack, which was a
harness of 8 checks built around ``context-kit inspect`` + ``verify``.
Six of those checks were UDB-specific (Postgres tag on every Procfile
entry, ORM shape signatures, DOC-AUTOGEN markers on named docs). Only
the runner and two of the checks are portable — the rest belong in
each repo's own plug-in file. This module is that portable core.

The two built-in checks are:

- ``verify-conflicts`` — runs ``context-kit verify`` in-process and
  fails if any finding has ``status == "CONFLICT"``. ``DOC_ONLY``
  findings are surfaced as advisory. This is the check that closes
  the doc-vs-runtime drift loop.
- ``tracked-generated-paths`` — reads ``.context-kit/guardrails.yaml``
  for a list of git-tracked path patterns that should never be in
  git (build outputs, index caches, generated artifacts) and fails
  if ``git ls-files`` returns any of them.

Repo-specific checks land in ``.context-kit/guardrails.py`` next to
the config. If that file exists and exposes ``CHECKS: list[Check]``,
those checks are appended to the built-in set. See the docstring on
``Check`` for the plug-in contract.

The design rule carried over intact from UDB: **a check that cannot
run in an environment must be advisory in that environment and strict
where it can run — and the difference must be visible in the
invocation, not hidden in the code.** Downgrade checks via
``--advisory NAME`` on the CLI (repeatable). CI invocations name the
checks they downgrade in the workflow file, so a reader of the
invocation sees exactly what's advisory.

Zero runtime dependencies. Cross-platform: subprocess calls always
use ``list[str]`` args, path handling is ``pathlib``, no reliance on
POSIX-only shell behavior.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib.util
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from cli.verify import collect_verification

CONFIG_DIR = ".context-kit"
CONFIG_FILE = "guardrails.yaml"
PLUGIN_FILE = "guardrails.py"
WORKFLOW_TARGET = ".github/workflows/repo-guardrails.yml"


# ---------------------------------------------------------------------------
# Result + Check types
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Outcome of running a single check.

    ``blocking`` is True when the check found a real problem AND the check
    is strict. When a check has been downgraded to advisory via
    ``--advisory NAME``, the runner clears ``blocking`` before reporting.
    """

    name: str
    ok: bool
    messages: list[str] = field(default_factory=list)
    blocking: bool = False
    detail: str = ""


@dataclass
class Check:
    """A guardrail check the runner will invoke.

    ``fn(project: Path) -> CheckResult`` — pure w.r.t. the project tree.
    The runner passes the resolved project root; the function does the
    rest. ``strict_by_default`` is False when the check is inherently
    non-portable — e.g. a DB-gated freshness check. Non-strict checks
    still run and report; they never block.

    Plug-in checks are simple: define a callable, wrap it in ``Check``,
    and put a list of them in ``.context-kit/guardrails.py`` as::

        from cli.guardrails import Check, CheckResult
        CHECKS = [Check(name="my-check", fn=my_check_fn)]
    """

    name: str
    fn: Callable[[Path], CheckResult]
    strict_by_default: bool = True
    description: str = ""


# ---------------------------------------------------------------------------
# Config loading — deliberately minimal YAML subset, zero deps
# ---------------------------------------------------------------------------


def _parse_yaml_list(text: str, key: str) -> list[str]:
    """Extract a list under ``key:`` from a tiny YAML subset.

    Recognizes only ``key:\\n  - value`` block form and lines starting
    with ``#`` as comments. Enough for the guardrails config (which is
    a couple of flat lists). Full YAML would require a dependency.
    """
    items: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not in_block:
            if stripped.rstrip(":") == key and stripped.endswith(":"):
                in_block = True
            continue
        # In the block. A non-indented, non-list line ends it.
        if not line.startswith((" ", "\t")):
            break
        if stripped.startswith("- "):
            items.append(stripped[2:].strip().strip('"').strip("'"))
    return items


def load_forbidden_paths(project: Path) -> list[str]:
    """Read ``.context-kit/guardrails.yaml`` for ``forbidden_paths``.

    Returns [] when the file is absent. That is the correct default —
    a repo without config only gets the ``verify-conflicts`` check.
    """
    cfg = project / CONFIG_DIR / CONFIG_FILE
    if not cfg.is_file():
        return []
    return _parse_yaml_list(cfg.read_text(encoding="utf-8", errors="replace"), "forbidden_paths")


# ---------------------------------------------------------------------------
# Built-in checks
# ---------------------------------------------------------------------------


def check_verify_conflicts(project: Path) -> CheckResult:
    """Fail on any CONFLICT finding from ``context-kit verify``.

    DOC_ONLY findings are surfaced as advisory messages but do not fail
    the check. This matches the strict-mode behavior of the original
    UDB script.
    """
    try:
        report = collect_verification(project)
    except Exception as exc:  # pragma: no cover — defensive
        return CheckResult(
            name="verify-conflicts",
            ok=False,
            blocking=True,
            messages=[f"context-kit verify raised {type(exc).__name__}: {exc}"],
            detail="verify subsystem failed to run",
        )

    conflicts = [f for f in report.findings if f.status == "CONFLICT"]
    doc_only = [f for f in report.findings if f.status == "DOC_ONLY"]

    messages: list[str] = []
    for f in conflicts:
        messages.append(f"CONFLICT: {f.title} — {f.details or f.recommendation}")
    for f in doc_only:
        messages.append(f"DOC_ONLY (advisory): {f.title}")

    ok = not conflicts
    detail = f"{len(conflicts)} conflict(s), {len(doc_only)} doc-only"
    return CheckResult(
        name="verify-conflicts",
        ok=ok,
        blocking=not ok,
        messages=messages or ["no CONFLICT findings"],
        detail=detail,
    )


def _git_ls_files(project: Path, patterns: list[str]) -> list[str]:
    """Return the intersection of git-tracked files with ``patterns``.

    Uses ``git ls-files`` first (respects .gitignore + tracks pathspecs);
    falls back to fnmatch-across-walk when the project is not a git
    repo, so ``guardrails run`` still gives useful output before ``git
    init``. Empty result when no matches.
    """
    if (project / ".git").exists() and shutil.which("git"):
        try:
            proc = subprocess.run(
                ["git", "ls-files", "--", *patterns],
                cwd=str(project),
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                return [ln for ln in proc.stdout.splitlines() if ln.strip()]
        except OSError:
            pass

    # Fallback: walk the tree and match patterns. Skips common heavy dirs.
    skip = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache"}
    hits: list[str] = []
    for path in project.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        rel = path.relative_to(project).as_posix()
        if any(fnmatch.fnmatch(rel, pat) for pat in patterns):
            hits.append(rel)
    return sorted(hits)


def check_tracked_generated_paths(project: Path) -> CheckResult:
    """Fail if any path in ``forbidden_paths`` is git-tracked.

    Reads the pattern list from ``.context-kit/guardrails.yaml``. When
    the config file is absent OR the list is empty, the check is a
    no-op and reports OK — a repo that has not declared any forbidden
    paths has nothing to police here.
    """
    patterns = load_forbidden_paths(project)
    if not patterns:
        return CheckResult(
            name="tracked-generated-paths",
            ok=True,
            blocking=False,
            messages=[
                f"no {CONFIG_DIR}/{CONFIG_FILE} forbidden_paths list — check is a no-op"
            ],
            detail="no configured patterns",
        )
    tracked = _git_ls_files(project, patterns)
    if tracked:
        messages = [f"tracked: {path}" for path in tracked]
        return CheckResult(
            name="tracked-generated-paths",
            ok=False,
            blocking=True,
            messages=messages,
            detail=f"{len(tracked)} tracked generated path(s)",
        )
    return CheckResult(
        name="tracked-generated-paths",
        ok=True,
        blocking=False,
        messages=[f"no matches for {len(patterns)} configured pattern(s)"],
        detail="clean",
    )


BUILTIN_CHECKS: list[Check] = [
    Check(
        name="verify-conflicts",
        fn=check_verify_conflicts,
        description="Fail on CONFLICT findings from `context-kit verify`.",
    ),
    Check(
        name="tracked-generated-paths",
        fn=check_tracked_generated_paths,
        description="Fail if configured forbidden paths are git-tracked.",
    ),
]


# ---------------------------------------------------------------------------
# Plug-in loading
# ---------------------------------------------------------------------------


def load_plugin_checks(project: Path) -> list[Check]:
    """Import ``.context-kit/guardrails.py`` if present and return its ``CHECKS``.

    The plug-in file is imported under a synthetic module name so it does
    not collide with any real ``guardrails`` module on the path. Import
    errors are surfaced as a single failing Check named
    ``plugin-load`` so a broken plug-in cannot silently drop checks.
    """
    plugin = project / CONFIG_DIR / PLUGIN_FILE
    if not plugin.is_file():
        return []

    module_name = "_context_kit_guardrails_plugin"
    spec = importlib.util.spec_from_file_location(module_name, plugin)
    if spec is None or spec.loader is None:
        return [_plugin_error(f"could not build importlib spec for {plugin}")]

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        return [_plugin_error(f"{plugin} raised {type(exc).__name__}: {exc}")]

    checks = getattr(module, "CHECKS", None)
    if checks is None:
        return [_plugin_error(f"{plugin} does not define a CHECKS list")]
    if not isinstance(checks, list) or not all(isinstance(c, Check) for c in checks):
        return [_plugin_error(f"{plugin} CHECKS must be list[Check]")]
    return list(checks)


def _plugin_error(message: str) -> Check:
    def _fail(_: Path) -> CheckResult:
        return CheckResult(
            name="plugin-load",
            ok=False,
            blocking=True,
            messages=[message],
            detail="plug-in failed to load",
        )
    return Check(name="plugin-load", fn=_fail)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_checks(
    project: Path,
    *,
    advisory: Optional[list[str]] = None,
    only: Optional[list[str]] = None,
) -> list[CheckResult]:
    """Run built-in + plug-in checks and return their results.

    ``advisory`` names checks that should not block even when they fail.
    ``only`` restricts the run to the named checks (built-in + plug-in).
    Unknown names in either list are surfaced as a warning result so a
    typo in a workflow file does not silently disable a check.
    """
    advisory_set = set(advisory or [])
    only_set = set(only or [])

    all_checks = list(BUILTIN_CHECKS) + load_plugin_checks(project)
    known_names = {c.name for c in all_checks} | {"plugin-load"}

    results: list[CheckResult] = []

    for missing in sorted(advisory_set - known_names):
        results.append(CheckResult(
            name=f"unknown:{missing}",
            ok=True,
            blocking=False,
            messages=[f"--advisory named unknown check `{missing}` (no such check)"],
            detail="unknown check name",
        ))
    for missing in sorted(only_set - known_names):
        results.append(CheckResult(
            name=f"unknown:{missing}",
            ok=True,
            blocking=False,
            messages=[f"--only named unknown check `{missing}` (no such check)"],
            detail="unknown check name",
        ))

    for check in all_checks:
        if only_set and check.name not in only_set:
            continue
        result = check.fn(project)
        if result.name in advisory_set:
            if not result.ok:
                result.messages.insert(0, f"(advisory: `{result.name}` downgraded — will not block)")
            result.blocking = False
        results.append(result)

    return results


def _render_report(results: list[CheckResult], project: Path, *, strict: bool) -> str:
    lines: list[str] = []
    lines.append(f"context-kit guardrails (strict={'on' if strict else 'off'})")
    lines.append(f"Repository: {project}")
    lines.append("")
    for result in results:
        marker = "OK " if result.ok else "FAIL"
        block = " [blocking]" if result.blocking else ""
        lines.append(f"[{marker}] {result.name} — {result.detail}{block}")
        for msg in result.messages:
            lines.append(f"    {msg}")
    lines.append("")
    failures = [r for r in results if r.blocking and strict]
    if failures:
        lines.append("FAIL summary")
        for r in failures:
            lines.append(f"- {r.name}")
    else:
        lines.append("PASS summary")
        lines.append("- No blocking guardrail rules were triggered.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Install action — copy the workflow template into the repo
# ---------------------------------------------------------------------------


def _read_workflow_template() -> str:
    from importlib import resources
    tmpl = resources.files("cli") / "_static" / "guardrails" / "workflow_template.yml"
    return tmpl.read_text(encoding="utf-8")


def run_install_workflow(project: Path, *, force: bool) -> int:
    dst = project / WORKFLOW_TARGET
    if dst.exists() and not force:
        print(f"context-kit: {WORKFLOW_TARGET} already exists — pass --force to overwrite.")
        return 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(_read_workflow_template(), encoding="utf-8")
    print(f"Wrote {dst.relative_to(project)}")
    return 0


# ---------------------------------------------------------------------------
# argparse entry point
# ---------------------------------------------------------------------------


def run_guardrails(args: argparse.Namespace) -> int:
    project = Path(getattr(args, "project", None) or Path.cwd()).resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    action = getattr(args, "guardrails_action", None) or "run"

    if action == "install-workflow":
        return run_install_workflow(project, force=bool(getattr(args, "force", False)))

    # default action: run
    advisory = list(getattr(args, "advisory", None) or [])
    only = list(getattr(args, "only", None) or [])
    strict = bool(getattr(args, "strict", True))

    results = run_checks(project, advisory=advisory, only=only)
    print(_render_report(results, project, strict=strict))

    if not strict:
        return 0
    return 1 if any(r.blocking for r in results) else 0
