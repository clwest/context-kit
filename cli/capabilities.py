"""Deterministic capability summaries derived from inspect facts."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path

from .inspect import _inspect, _resolve_inspect_project

_CAPABILITY_MEANINGS = {
    "auth": "Route evidence suggests user registration, login, and current-user lookup.",
    "sessions/chat": "Route evidence suggests chat messages are supported inside mentor sessions.",
    "founder_projects/export": "Route evidence suggests founder/project export or project management endpoints.",
    "tier_config": "Config evidence suggests tier limits, allowed modes, token limits, and session/message enforcement.",
    "data/models": "Model evidence suggests schema or ORM/domain model definitions.",
    "config/env": "Config evidence suggests environment, deployment, or container configuration.",
    "stripe/checkout": "Route evidence suggests Stripe checkout support.",
    "stripe/webhook": "Route evidence suggests Stripe webhook handling.",
}

_CAPABILITY_REASONS = {
    "auth": "Explicit register/login/current-user routes detected.",
    "sessions/chat": "Explicit chat route inside session resource detected.",
    "founder_projects/export": "Route evidence suggests founder/project management endpoints.",
    "tier_config": "Config evidence suggests tier limits, allowed modes, token limits, and session/message enforcement, but runtime enforcement is not verified.",
    "data/models": "Model evidence suggests ORM/domain models are defined, but runtime behavior is not verified.",
    "config/env": "Env keys and Dockerfiles detected, but runtime deployment is not verified.",
    "stripe/checkout": "Stripe checkout route detected, but payment flow completion is not verified.",
    "stripe/webhook": "Stripe webhook route detected, but webhook processing behavior is not verified.",
}


def run_capabilities(args: argparse.Namespace) -> int:
    project = _resolve_inspect_project(args)
    if project is None:
        return 2

    result = _inspect(
        project,
        depth=getattr(args, "depth", 2),
        scope=getattr(args, "scope", None),
        include_related=getattr(args, "include_related", False),
        include_history=getattr(args, "include_history", False),
    )
    report = render_capabilities_markdown(project, result.files, result, format=getattr(args, "format", "full"))

    output_path = getattr(args, "output", None)
    if output_path:
        out_path = Path(output_path).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")

    print(report)
    return 0


def render_capabilities_markdown(project: Path, files: list[Path], inspect_result, *, format: str = "full") -> str:
    from .inspect import _collect_structured_implementation_facts

    facts = _collect_structured_implementation_facts(project, files)
    grouped: OrderedDict[str, dict[str, list[str] | bool]] = OrderedDict()
    for fact in facts:
        capability = str(fact.get("capability", "unknown"))
        evidence = [str(item) for item in fact.get("evidence", []) if str(item).strip()]
        if not evidence:
            continue
        entry = grouped.setdefault(capability, {"evidence": [], "heuristic": False})
        entry["evidence"].extend(evidence)
        if capability not in {"config/env"}:
            entry["heuristic"] = True

    if format == "compact":
        return _render_compact_capabilities_markdown(project, inspect_result, grouped)
    if format == "shortlist":
        return _render_shortlist_capabilities_markdown(project, inspect_result, grouped)

    lines: list[str] = []
    lines.append("# context-kit capabilities")
    lines.append("")
    lines.append("> Deterministic capability summary derived from inspect structured implementation facts.")
    lines.append("")
    lines.append("## Project identity")
    lines.append("")
    lines.append(f"- Project path: `{project}`")
    lines.append(f"- Project name: `{project.name}`")
    if inspect_result.head:
        lines.append(f"- Git branch: `{inspect_result.head.get('branch') or '(unknown)'}`")
        lines.append(f"- Latest commit hash: `{inspect_result.head.get('sha') or '(unknown)'}`")
    else:
        lines.append("- Git branch: not available")
        lines.append("- Latest commit hash: not available")
    lines.append("")

    lines.append("## Capability summary")
    lines.append("")
    if not grouped:
        lines.append("- No structured implementation facts were detected.")
    else:
        for capability, payload in grouped.items():
            evidence = list(dict.fromkeys(payload["evidence"]))
            lines.append(f"### {capability}")
            if payload.get("heuristic"):
                lines.append("- Capability label is heuristic.")
            meaning = _CAPABILITY_MEANINGS.get(capability)
            if meaning:
                lines.append(f"- Meaning: {meaning}")
            confidence, reason = _capability_confidence(capability, evidence)
            lines.append(f"- Confidence: {confidence}")
            lines.append(f"- Reason: {reason}")
            lines.append("- Evidence:")
            for item in evidence:
                lines.append(f"  - {item}")
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()

    return "\n".join(lines).rstrip() + "\n"


def _render_compact_capabilities_markdown(
    project: Path,
    inspect_result,
    grouped: OrderedDict[str, dict[str, list[str] | bool]],
) -> str:
    lines: list[str] = []
    lines.append("# context-kit capabilities")
    lines.append("")
    lines.append("> Compact capability summary derived from inspect structured implementation facts.")
    lines.append("")
    lines.append("## Project identity")
    lines.append("")
    lines.append(f"- Project path: `{project}`")
    lines.append(f"- Project name: `{project.name}`")
    if inspect_result.head:
        lines.append(f"- Git branch: `{inspect_result.head.get('branch') or '(unknown)'}`")
        lines.append(f"- Latest commit hash: `{inspect_result.head.get('sha') or '(unknown)'}`")
    else:
        lines.append("- Git branch: not available")
        lines.append("- Latest commit hash: not available")
    lines.append("")
    lines.append("## Capability summary")
    lines.append("")

    compact_items: list[tuple[str, list[str], str, str]] = []
    for capability, payload in grouped.items():
        if capability == "data/models":
            continue
        evidence = _select_compact_evidence(capability, list(dict.fromkeys(payload["evidence"])))
        if not evidence:
            continue
        confidence, reason = _capability_confidence(capability, evidence)
        compact_items.append((capability, evidence, confidence, reason))

    if not compact_items:
        lines.append("- No structured implementation facts were detected.")
        return "\n".join(lines).rstrip() + "\n"

    shortlist = _build_recommended_shortlist(compact_items)
    if shortlist:
        lines.append("## Recommended capability shortlist")
        lines.append("")
        for capability, evidence, confidence, reason in shortlist:
            lines.append(f"### {capability}")
            meaning = _CAPABILITY_MEANINGS.get(capability)
            if meaning:
                lines.append(f"- Meaning: {meaning}")
            lines.append(f"- Confidence: {confidence}")
            lines.append(f"- Reason: {reason}")
            lines.append("- Best evidence:")
            for item in evidence[:3]:
                lines.append(f"  - {item}")
            lines.append("")
        if lines and lines[-1] == "":
            lines.pop()
        lines.append("")

    for capability, evidence, confidence, reason in compact_items:
        lines.append(f"### {capability}")
        meaning = _CAPABILITY_MEANINGS.get(capability)
        if meaning:
            lines.append(f"- Meaning: {meaning}")
        lines.append(f"- Confidence: {confidence}")
        lines.append(f"- Reason: {reason}")
        lines.append("- Best evidence:")
        for item in evidence:
            lines.append(f"  - {item}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def _render_shortlist_capabilities_markdown(
    project: Path,
    inspect_result,
    grouped: OrderedDict[str, dict[str, list[str] | bool]],
) -> str:
    lines: list[str] = []
    lines.append("# context-kit capabilities")
    lines.append("")
    lines.append("> Shortlist capability summary derived from inspect structured implementation facts.")
    lines.append("")
    lines.append("## Project identity")
    lines.append("")
    lines.append(f"- Project path: `{project}`")
    lines.append(f"- Project name: `{project.name}`")
    if inspect_result.head:
        lines.append(f"- Git branch: `{inspect_result.head.get('branch') or '(unknown)'}`")
        lines.append(f"- Latest commit hash: `{inspect_result.head.get('sha') or '(unknown)'}`")
    else:
        lines.append("- Git branch: not available")
        lines.append("- Latest commit hash: not available")
    lines.append("")
    lines.append("## Recommended capability shortlist")
    lines.append("")

    compact_items: list[tuple[str, list[str], str, str]] = []
    shortlist_order = [
        "auth",
        "sessions/chat",
        "founder_projects/export",
        "stripe/checkout",
        "stripe/webhook",
        "tier_config",
        "config/env",
    ]
    for capability in shortlist_order:
        payload = grouped.get(capability)
        if payload is None:
            continue
        evidence = _select_compact_evidence(capability, list(dict.fromkeys(payload["evidence"])))
        if not evidence:
            continue
        confidence, reason = _capability_confidence(capability, evidence)
        if confidence not in {"high", "medium"}:
            continue
        compact_items.append((capability, evidence, confidence, reason))

    if not compact_items:
        lines.append("- No structured implementation facts were detected.")
        return "\n".join(lines).rstrip() + "\n"

    for capability, evidence, confidence, reason in compact_items:
        lines.append(f"### {capability}")
        meaning = _CAPABILITY_MEANINGS.get(capability)
        if meaning:
            lines.append(f"- Meaning: {meaning}")
        lines.append(f"- Confidence: {confidence}")
        lines.append(f"- Reason: {reason}")
        lines.append("- Best evidence:")
        for item in evidence[:3]:
            lines.append(f"  - {item}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def _build_recommended_shortlist(
    compact_items: list[tuple[str, list[str], str, str]],
) -> list[tuple[str, list[str], str, str]]:
    shortlist_order = [
        "auth",
        "sessions/chat",
        "founder_projects/export",
        "stripe/checkout",
        "stripe/webhook",
        "tier_config",
        "config/env",
    ]
    by_capability = {capability: (capability, evidence, confidence, reason) for capability, evidence, confidence, reason in compact_items}
    shortlist: list[tuple[str, list[str], str, str]] = []
    for capability in shortlist_order:
        item = by_capability.get(capability)
        if item is None:
            continue
        _, evidence, confidence, _ = item
        if confidence not in {"high", "medium"}:
            continue
        shortlist.append(item)
    return shortlist


def _capability_confidence(capability: str, evidence: list[str]) -> tuple[str, str]:
    joined = "\n".join(evidence).lower()
    if capability == "auth":
        if any(token in joined for token in ("register", "login", "users/me")) and len(evidence) >= 2:
            return "high", _CAPABILITY_REASONS[capability]
        return "medium", "Route evidence suggests auth-related endpoints, but the full auth flow is not verified."
    if capability == "sessions/chat":
        return "high", _CAPABILITY_REASONS[capability]
    if capability == "tier_config":
        return "medium", _CAPABILITY_REASONS[capability]
    if capability == "config/env":
        return "medium", _CAPABILITY_REASONS[capability]
    if capability == "stripe/checkout":
        return "medium", _CAPABILITY_REASONS[capability]
    if capability == "stripe/webhook":
        return "medium", _CAPABILITY_REASONS[capability]
    if capability == "founder_projects/export":
        if len(evidence) >= 3:
            return "high", "Multiple founder/project management endpoints detected."
        return "medium", _CAPABILITY_REASONS[capability]
    if capability == "data/models":
        if len(evidence) >= 2:
            return "high", "Multiple explicit model/class signals detected."
        return "medium", _CAPABILITY_REASONS[capability]
    return "low", "Capability label is broad or ambiguous; evidence is naming-based only."


def _select_compact_evidence(capability: str, evidence: list[str]) -> list[str]:
    route_evidence = [item for item in evidence if "@app." in item or "@router." in item]
    if capability in {"auth", "sessions/chat", "founder_projects/export", "stripe/checkout", "stripe/webhook"}:
        return route_evidence or evidence
    if capability == "tier_config":
        preferred = [
            item
            for item in evidence
            if any(token in item for token in ("allowed_modes", "max_sessions_per_day", "max_response_tokens", "max_messages_per_session"))
        ]
        return preferred or route_evidence or evidence
    if capability == "config/env":
        preferred = [item for item in evidence if ".env" in item or "Dockerfile" in item or "compose" in item]
        return preferred or evidence
    if capability == "data/models":
        base_model = [item for item in evidence if "BaseModel" in item or "DeclarativeBase" in item or "declarative_base" in item]
        return base_model[:1]
    return route_evidence or evidence[:1]
