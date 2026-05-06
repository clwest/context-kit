"""Deterministic capability summaries derived from inspect facts."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path

from .inspect import _inspect, _resolve_inspect_project

_CAPABILITY_MEANINGS = {
    "auth": "Detected route group for auth-related endpoints.",
    "sessions/chat": "Detected route group for session chat endpoints.",
    "founder_projects/export": "Detected route group for founder/project management endpoints.",
    "tier_config": "Detected config evidence for tier limits and enforcement knobs.",
    "data/models": "Detected model definitions in the codebase.",
    "config/env": "Detected environment and deployment configuration evidence.",
    "stripe/checkout": "Detected route group for Stripe checkout endpoints.",
    "stripe/webhook": "Detected route group for Stripe webhook endpoints.",
    "orient": "Detected CLI command for project orientation rendering.",
    "inspect": "Detected CLI command for static repo inspection.",
    "capabilities": "Detected CLI command for deterministic capability summaries.",
    "chat": "Detected CLI command for local, project-grounded chat mode.",
    "doctor": "Detected CLI command for read-only environment diagnostics.",
    "inventory": "Detected CLI command for runtime-derived inventory generation.",
    "audit-response": "Detected CLI command for response groundedness auditing.",
    "init": "Detected CLI command for project initialization scaffolding.",
    "adopt": "Detected CLI command for retrofitting context-kit docs onto existing projects.",
    "seed": "Detected CLI command for structured idea seeding.",
    "hotpath": "Detected CLI command for hot-file and context-dominance reporting.",
    "coverage": "Detected CLI command for file coverage classification.",
    "behavior": "Detected CLI command for behavior-surface analysis.",
    "connections": "Detected CLI command for connection inventory reporting.",
    "verify": "Detected CLI command for verification checks.",
    "exec": "Detected CLI command for executing a defined task prompt.",
    "audit": "Detected CLI command for audit prompt generation.",
    "fix": "Detected CLI command for phased cleanup planning.",
    "recommend-stack": "Detected CLI command for stack recommendation from structured ideas.",
    "start": "Detected CLI command for serving an onboarding UI.",
    "translation-init": "Detected CLI command for translation-layer initialization.",
    "codex": "Detected CLI command for Codex startup wiring.",
    "start-codex": "Detected CLI command for Codex startup wiring.",
    "refactor": "Detected CLI command for refactor assistance.",
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
    "orient": "Explicit CLI command registration and module entrypoint detected.",
    "inspect": "Explicit CLI command registration and module entrypoint detected.",
    "capabilities": "Explicit CLI command registration and module entrypoint detected.",
    "chat": "Explicit CLI command registration and module entrypoint detected.",
    "doctor": "Explicit CLI command registration and module entrypoint detected.",
    "inventory": "Explicit CLI command registration and module entrypoint detected.",
    "audit-response": "Explicit CLI command registration and module entrypoint detected.",
    "init": "Explicit CLI command registration and module entrypoint detected.",
    "adopt": "Explicit CLI command registration and module entrypoint detected.",
    "seed": "Explicit CLI command registration and module entrypoint detected.",
    "hotpath": "Explicit CLI command registration and module entrypoint detected.",
    "coverage": "Explicit CLI command registration and module entrypoint detected.",
    "behavior": "Explicit CLI command registration and module entrypoint detected.",
    "connections": "Explicit CLI command registration and module entrypoint detected.",
    "verify": "Explicit CLI command registration and module entrypoint detected.",
    "exec": "Explicit CLI command registration and module entrypoint detected.",
    "audit": "Explicit CLI command registration and module entrypoint detected.",
    "fix": "Explicit CLI command registration and module entrypoint detected.",
    "recommend-stack": "Explicit CLI command registration and module entrypoint detected.",
    "start": "Explicit CLI command registration and module entrypoint detected.",
    "translation-init": "Explicit CLI command registration and module entrypoint detected.",
    "codex": "Explicit CLI command registration and module entrypoint detected.",
    "start-codex": "Explicit CLI command registration and module entrypoint detected.",
    "refactor": "Explicit CLI command registration and module entrypoint detected.",
}

_CAPABILITY_SAFE_DESCRIPTIONS = {
    "connections": "The repo exposes a connections CLI command.",
    "recommend-stack": "The repo exposes a recommend-stack CLI command.",
    "verify": "The repo exposes a verify CLI command.",
    "exec": "The repo exposes an exec CLI command.",
    "codex": "The repo exposes a codex CLI command.",
    "start-codex": "The repo exposes a start-codex CLI command.",
}

_CAPABILITY_FORBIDDEN_EXTRAPOLATIONS = {
    "connections": "Do not infer collaboration, relationship mapping, business value, automation, or workflow impact from the command name alone.",
    "recommend-stack": "Do not infer architecture intelligence, automatic architecture selection, or optimization from the command name alone.",
    "verify": "Do not infer correctness guarantees, formal verification, or runtime test status from the command name alone.",
    "exec": "Do not infer workflow orchestration, automated execution, or operational impact from the command name alone.",
    "codex": "Do not infer an autonomous coding agent or general AI autonomy from the command name alone.",
    "start-codex": "Do not infer an autonomous coding agent or general AI autonomy from the command name alone.",
}

_CLI_CAPABILITIES = {
    "orient",
    "inspect",
    "capabilities",
    "chat",
    "doctor",
    "inventory",
    "audit-response",
    "init",
    "adopt",
    "seed",
    "hotpath",
    "coverage",
    "behavior",
    "connections",
    "verify",
    "exec",
    "audit",
    "fix",
    "recommend-stack",
    "start",
    "translation-init",
    "codex",
    "start-codex",
    "refactor",
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
    report = render_capabilities_markdown(
        project,
        result.files,
        result,
        format=getattr(args, "format", "full"),
        include_tests=getattr(args, "include_tests", False),
        include_detectors=getattr(args, "include_detectors", False),
    )

    output_path = getattr(args, "output", None)
    if output_path:
        out_path = Path(output_path).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")

    print(report)
    return 0


def render_capabilities_markdown(
    project: Path,
    files: list[Path],
    inspect_result,
    *,
    format: str = "full",
    include_tests: bool = False,
    include_detectors: bool = False,
) -> str:
    from .inspect import _collect_structured_implementation_facts

    facts = _collect_structured_implementation_facts(project, files)
    grouped: OrderedDict[str, dict[str, list[str] | bool]] = OrderedDict()
    for fact in facts:
        capability = str(fact.get("capability", "unknown"))
        evidence = [str(item) for item in fact.get("evidence", []) if str(item).strip()]
        if not evidence:
            continue
        classified = [(item, _classify_evidence_source(item)) for item in evidence]
        has_test_evidence = any(source == "test_fixture" for _, source in classified)
        has_detector_evidence = any(source == "detector_logic" for _, source in classified)
        evidence = [
            item
            for item, source in classified
            if source == "implementation"
            or (include_tests and source == "test_fixture")
            or (include_detectors and source == "detector_logic")
        ]
        if not evidence:
            continue
        entry = grouped.setdefault(
            capability,
            {
                "evidence": [],
                "heuristic": False,
                "has_test_evidence": False,
                "has_detector_evidence": False,
            },
        )
        entry["evidence"].extend(evidence)
        if has_test_evidence:
            entry["has_test_evidence"] = True
        if has_detector_evidence:
            entry["has_detector_evidence"] = True
        if capability not in {"config/env"}:
            entry["heuristic"] = True

    if format == "compact":
        return _render_compact_capabilities_markdown(
            project,
            inspect_result,
            grouped,
            include_tests=include_tests,
            include_detectors=include_detectors,
        )
    if format == "shortlist":
        return _render_shortlist_capabilities_markdown(
            project,
            inspect_result,
            grouped,
            include_tests=include_tests,
            include_detectors=include_detectors,
        )

    lines: list[str] = []
    lines.append("# context-kit capabilities")
    lines.append("")
    lines.append("> Deterministic capability summary derived from inspect structured implementation facts.")
    lines.append("")
    lines.extend(_capability_answer_contract_lines())
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
        lines.append("- No implementation capabilities detected from non-test source paths.")
    else:
        for capability, payload in grouped.items():
            evidence = list(dict.fromkeys(payload["evidence"]))
            lines.append(f"### {capability}")
            if payload.get("heuristic"):
                lines.append("- Capability label is heuristic.")
            if capability in _CLI_CAPABILITIES:
                lines.extend(_literal_cli_capability_lines(capability, evidence))
            else:
                meaning = _CAPABILITY_MEANINGS.get(capability)
                if meaning:
                    lines.append(f"- Meaning: {meaning}")
            confidence, reason = _capability_confidence(capability, evidence)
            lines.append(f"- Confidence: {confidence}")
            lines.append(f"- Reason: {reason}")
            if include_tests and payload.get("has_test_evidence"):
                lines.append("- Test/fixture evidence — not implementation.")
            if include_detectors and payload.get("has_detector_evidence"):
                lines.append("- Detector logic evidence — not project implementation.")
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
    *,
    include_tests: bool = False,
    include_detectors: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("# context-kit capabilities")
    lines.append("")
    lines.append("> Compact capability summary derived from inspect structured implementation facts.")
    lines.append("")
    lines.extend(_capability_answer_contract_lines())
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
        lines.append("- No implementation capabilities detected from non-test source paths.")
        return "\n".join(lines).rstrip() + "\n"

    shortlist = _build_recommended_shortlist(compact_items)
    if shortlist:
        lines.append("## Recommended capability shortlist")
        lines.append("")
    for capability, evidence, confidence, reason in shortlist:
        lines.append(f"### {capability}")
        if capability in _CLI_CAPABILITIES:
            lines.extend(_literal_cli_capability_lines(capability, evidence))
        else:
            meaning = _CAPABILITY_MEANINGS.get(capability)
            if meaning:
                lines.append(f"- Meaning: {meaning}")
        lines.append(f"- Confidence: {confidence}")
        lines.append(f"- Reason: {reason}")
        if include_tests and any(_classify_evidence_source(item) == "test_fixture" for item in evidence):
            lines.append("- Test/fixture evidence — not implementation.")
        if include_detectors and any(_classify_evidence_source(item) == "detector_logic" for item in evidence):
            lines.append("- Detector logic evidence — not project implementation.")
        lines.append("- Best evidence:")
        for item in evidence[:3]:
            lines.append(f"  - {item}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def _render_shortlist_capabilities_markdown(
    project: Path,
    inspect_result,
    grouped: OrderedDict[str, dict[str, list[str] | bool]],
    *,
    include_tests: bool = False,
    include_detectors: bool = False,
) -> str:
    lines: list[str] = []
    lines.append("# context-kit capabilities")
    lines.append("")
    lines.append("> Shortlist capability summary derived from inspect structured implementation facts.")
    lines.append("")
    lines.extend(_capability_answer_contract_lines())
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
        "orient",
        "inspect",
        "capabilities",
        "chat",
        "doctor",
        "inventory",
        "audit-response",
        "init",
        "adopt",
        "seed",
        "hotpath",
        "coverage",
        "behavior",
        "connections",
        "verify",
        "exec",
        "audit",
        "fix",
        "recommend-stack",
        "start",
        "translation-init",
        "codex",
        "start-codex",
        "refactor",
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
        lines.append("- No implementation capabilities detected from non-test source paths.")
        return "\n".join(lines).rstrip() + "\n"

    for capability, evidence, confidence, reason in compact_items:
        lines.append(f"### {capability}")
        if capability in _CLI_CAPABILITIES:
            lines.extend(_literal_cli_capability_lines(capability, evidence))
        else:
            meaning = _CAPABILITY_MEANINGS.get(capability)
            if meaning:
                lines.append(f"- Meaning: {meaning}")
        lines.append(f"- Confidence: {confidence}")
        lines.append(f"- Reason: {reason}")
        if include_tests and any(_classify_evidence_source(item) == "test_fixture" for item in evidence):
            lines.append("- Test/fixture evidence — not implementation.")
        if include_detectors and any(_classify_evidence_source(item) == "detector_logic" for item in evidence):
            lines.append("- Detector logic evidence — not project implementation.")
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
        "orient",
        "inspect",
        "capabilities",
        "chat",
        "doctor",
        "inventory",
        "audit-response",
        "init",
        "adopt",
        "seed",
        "hotpath",
        "coverage",
        "behavior",
        "connections",
        "verify",
        "exec",
        "audit",
        "fix",
        "recommend-stack",
        "start",
        "translation-init",
        "codex",
        "start-codex",
        "refactor",
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


def _literal_cli_capability_lines(capability: str, evidence: list[str]) -> list[str]:
    lines = [
        f"- command_name: `{capability}`",
        "- command_type: CLI command",
        "- detected_entrypoint:",
    ]
    for item in evidence[:3]:
        lines.append(f"  - {item}")
    lines.append(f"- literal description: The repo exposes a CLI command named `{capability}`.")
    forbidden = _CAPABILITY_FORBIDDEN_EXTRAPOLATIONS.get(capability)
    if forbidden:
        lines.append(f"- forbidden extrapolations: {forbidden}")
    return lines


def _capability_answer_contract_lines() -> list[str]:
    return [
        "## Capability answer contract",
        "",
        "- For capability questions, answer only from the Recommended capability shortlist when it is present.",
        "- Do not synthesize from orientation, repo inspection, stack/framework detection, or command presence.",
        "- If the user says \"use only the capability shortlist\", ignore everything except evidence lines already present in the shortlist.",
        "- Use answer shape: command name, literal detected type, evidence, confidence.",
        "- No narrative paragraph before or after.",
        "- Do not infer unused code detection, optimization suggestions, maintainability analysis, performance analysis, modularization analysis, or architecture recommendations unless they are explicitly listed here.",
    ]


def _capability_confidence(capability: str, evidence: list[str]) -> tuple[str, str]:
    joined = "\n".join(evidence).lower()
    if capability in {
        "orient",
        "inspect",
        "capabilities",
        "chat",
        "doctor",
        "inventory",
        "audit-response",
        "init",
        "adopt",
        "seed",
        "hotpath",
        "coverage",
        "behavior",
        "connections",
        "verify",
        "exec",
        "audit",
        "fix",
        "recommend-stack",
        "start",
        "translation-init",
        "codex",
        "start-codex",
        "refactor",
    }:
        if len(evidence) >= 2:
            return "high", _CAPABILITY_REASONS[capability]
        return "medium", "CLI command evidence detected, but broader behavior is not fully verified."
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
    if capability in {
        "orient",
        "inspect",
        "capabilities",
        "chat",
        "doctor",
        "inventory",
        "audit-response",
        "init",
        "adopt",
        "seed",
        "hotpath",
        "coverage",
        "behavior",
        "connections",
        "verify",
        "exec",
        "audit",
        "fix",
        "recommend-stack",
        "start",
        "translation-init",
        "codex",
        "start-codex",
        "refactor",
    }:
        return evidence
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


def _classify_evidence_source(evidence: str) -> str:
    path = evidence.split(":", 1)[0].strip()
    if not path:
        return "implementation"
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in {"tests", "test", "__tests__"} for part in parts):
        return "test_fixture"
    name = parts[-1]
    if (
        name.startswith("test_")
        or name.startswith("test.")
        or name.endswith("_test.py")
        or ".test." in name
        or name.endswith(".spec")
        or name.endswith(".spec.py")
        or ".spec." in name
    ):
        return "test_fixture"
    if _is_detector_logic_evidence(normalized, evidence):
        return "detector_logic"
    return "implementation"


def _is_detector_logic_evidence(normalized_path: str, evidence: str) -> bool:
    if not normalized_path.startswith("cli/"):
        return False
    content = evidence.split(":", 1)[-1].strip().lower()
    detector_signals = (
        "markers =",
        "_select_compact_evidence",
        "_capability_confidence",
        "render_capabilities_markdown",
        "_collect_structured_implementation_facts",
        "_group_fastapi_route_capabilities",
        "_group_tier_config_capabilities",
        "_group_model_capabilities",
        "_group_env_capabilities",
        "_route_capability_label",
        "capability summary",
        "if any(token in item",
        "re.compile(",
    )
    return any(marker in content for marker in detector_signals)
