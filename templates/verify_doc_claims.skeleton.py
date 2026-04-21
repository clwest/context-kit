"""
Skeleton: Doc-vs-Reality Verifier Framework

Copy this file into your project as `your_project/services/doc_claim_verification.py`.
Adapt imports to your stack (replace `your_project` with your backend package name).

Usage:

    from your_project.services.doc_claim_verification import register_claim, ClaimResult

    @register_claim(
        doc="CLAUDE.md",
        claim_id="agent_count",
        description="CLAUDE.md: '83 agents in AGENT_MAP'",
    )
    def verify_agent_count():
        from your_project.agent_router import AGENT_MAP
        expected = 83
        actual = len(AGENT_MAP)
        return ClaimResult.build(
            doc="CLAUDE.md",
            claim_id="agent_count",
            description="CLAUDE.md: '83 agents in AGENT_MAP'",
            expected=expected,
            actual=actual,
            severity="ok" if expected == actual else "medium",
            fix_suggestion=f"Update CLAUDE.md to '{actual} agents'",
        )

Then:

    python manage.py verify_doc_claims --only-drift
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

# -----------------------------------------------------------------------------
# ClaimResult
# -----------------------------------------------------------------------------

SEVERITY_ORDER = ["ok", "low", "medium", "high", "critical", "error"]


@dataclass
class ClaimResult:
    doc: str
    claim_id: str
    description: str
    expected: Any
    actual: Any
    severity: str  # ok | low | medium | high | critical | error
    note: str = ""
    fix_suggestion: str = ""

    @classmethod
    def build(
        cls,
        doc: str,
        claim_id: str,
        description: str,
        expected: Any,
        actual: Any,
        severity: Optional[str] = None,
        note: str = "",
        fix_suggestion: str = "",
    ) -> "ClaimResult":
        if severity is None:
            # Auto-compute: match -> ok, else medium (override per-claim when relevant)
            severity = "ok" if expected == actual else "medium"
        return cls(
            doc=doc,
            claim_id=claim_id,
            description=description,
            expected=expected,
            actual=actual,
            severity=severity,
            note=note,
            fix_suggestion=fix_suggestion,
        )

    @property
    def is_drift(self) -> bool:
        return self.severity != "ok"


# -----------------------------------------------------------------------------
# Registry + decorator
# -----------------------------------------------------------------------------

_REGISTRY: List[Callable[[], ClaimResult]] = []


def register_claim(doc: str, claim_id: str, description: str):
    """
    Decorator that registers a verifier in the global registry.

    The decorated function must be zero-arg and return a ClaimResult.
    """
    def decorator(fn: Callable[[], ClaimResult]):
        # Attach metadata so the runner can annotate crashed verifiers
        fn._doc = doc
        fn._claim_id = claim_id
        fn._description = description
        _REGISTRY.append(fn)
        return fn
    return decorator


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

def run_all(
    doc_filter: Optional[str] = None,
    only_drift: bool = False,
) -> List[ClaimResult]:
    """
    Execute all registered verifiers. Exceptions are trapped as severity='error'.
    """
    results: List[ClaimResult] = []
    for fn in _REGISTRY:
        if doc_filter and fn._doc != doc_filter:
            continue
        try:
            result = fn()
        except Exception as exc:
            result = ClaimResult(
                doc=fn._doc,
                claim_id=fn._claim_id,
                description=fn._description,
                expected="<verifier crashed>",
                actual=str(exc),
                severity="error",
                note=traceback.format_exc()[:500],
                fix_suggestion="Fix the verifier or the underlying system it checks.",
            )
        if only_drift and not result.is_drift:
            continue
        results.append(result)
    return results


# -----------------------------------------------------------------------------
# Summarize
# -----------------------------------------------------------------------------

def summarize(results: List[ClaimResult]) -> dict:
    """Rollup by severity and by doc. Returned as plain dict for JSON-friendly output."""
    by_severity = {sev: 0 for sev in SEVERITY_ORDER}
    by_doc: dict[str, dict[str, int]] = {}

    for r in results:
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
        bucket = by_doc.setdefault(r.doc, {"ok": 0, "drift": 0, "error": 0})
        if r.severity == "ok":
            bucket["ok"] += 1
        elif r.severity == "error":
            bucket["error"] += 1
        else:
            bucket["drift"] += 1

    return {
        "total": len(results),
        "by_severity": by_severity,
        "by_doc": by_doc,
    }


# -----------------------------------------------------------------------------
# Auto-discovery: import the module(s) where @register_claim decorators live.
# Adapt this to your project structure.
# -----------------------------------------------------------------------------

def autodiscover():
    """
    Import modules that contain @register_claim decorated functions.
    Replace the example below with your project's claim modules.

    Example for Django (uncomment + adapt):

        # from django.apps import apps
        # for app in apps.get_app_configs():
        #     try:
        #         __import__(f"{app.name}.doc_claims")
        #     except ImportError:
        #         pass

    Example direct-import pattern (uncomment + adapt):

        # from your_project import doc_claims  # noqa: F401
    """
    return None


# -----------------------------------------------------------------------------
# CLI entrypoint skeleton (for Django: register in core/management/commands/)
# -----------------------------------------------------------------------------

def _cli_main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Verify doc claims against runtime.")
    parser.add_argument("--doc", help="Filter to a single doc (e.g. CLAUDE.md)")
    parser.add_argument("--only-drift", action="store_true", help="Hide ok results")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--fail-on-drift", action="store_true",
                        help="Exit non-zero if any drift is found")
    parser.add_argument("--list", action="store_true",
                        help="List registered claims without running")
    args = parser.parse_args(argv)

    autodiscover()

    if args.list:
        for fn in _REGISTRY:
            print(f"  [{fn._doc}] {fn._claim_id} — {fn._description}")
        return 0

    results = run_all(doc_filter=args.doc, only_drift=args.only_drift)
    summary = summarize(results)

    if args.format == "json":
        print(json.dumps(
            {
                "results": [r.__dict__ for r in results],
                "summary": summary,
            },
            indent=2,
            default=str,
        ))
    else:
        # Grouped-by-doc text output
        by_doc: dict[str, list[ClaimResult]] = {}
        for r in results:
            by_doc.setdefault(r.doc, []).append(r)
        for doc, claims in sorted(by_doc.items()):
            print(f"\n── {doc} ──")
            for c in claims:
                marker = {
                    "ok": "✓",
                    "low": "·",
                    "medium": "●",
                    "high": "▲",
                    "critical": "■",
                    "error": "✗",
                }.get(c.severity, "?")
                print(f"  {marker} [{c.severity:>8}] {c.claim_id}")
                print(f"      claim: {c.description}")
                print(f"      expected: {c.expected!r}")
                print(f"      actual:   {c.actual!r}")
                if c.note:
                    print(f"      note:     {c.note}")
                if c.fix_suggestion:
                    print(f"      fix:      {c.fix_suggestion}")

        # Summary footer
        print("\n── Summary ──")
        print(f"  total: {summary['total']}")
        for sev in SEVERITY_ORDER:
            n = summary["by_severity"].get(sev, 0)
            if n:
                print(f"  {sev:>10}: {n}")
        print("\n  by doc:")
        for doc, counts in sorted(summary["by_doc"].items()):
            print(f"    {doc:<40} ok={counts['ok']:>2}  drift={counts['drift']:>2}  error={counts['error']:>2}")

    if args.fail_on_drift:
        drift_count = sum(1 for r in results if r.is_drift)
        if drift_count:
            return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_cli_main(sys.argv[1:]))
