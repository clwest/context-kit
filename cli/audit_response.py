"""Heuristic groundedness audit for ``context-kit chat`` outputs.

This first version is intentionally manual-scaffold style: it extracts
claim-like units from a response, compares them against the current
orientation text, and produces a markdown report for human review.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from .orient import render_orient

CLAIM_CLASSIFICATIONS = (
    "grounded",
    "unsupported",
    "speculative",
    "contradicted",
    "unclear",
)

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|(?:\d+\.))\s+(.*\S)\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def run_audit_response(args: argparse.Namespace) -> int:
    project = _resolve_project_path(getattr(args, "project", None))
    if project is None:
        return 2

    response_path = Path(args.input).expanduser().resolve()
    response_text = response_path.read_text(encoding="utf-8")
    orientation = render_orient(project, short=False)
    claims = extract_claims(response_text)
    rows = [
        classify_claim(claim, orientation)
        for claim in claims
    ]
    report = render_report(response_path, claims, rows, orientation)

    output_path = getattr(args, "output", None)
    if output_path:
        out_path = Path(output_path).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")

    print(report)
    return 0


def extract_claims(text: str) -> list[str]:
    claims: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        joined = " ".join(part.strip() for part in paragraph if part.strip()).strip()
        paragraph.clear()
        if not joined:
            return
        pieces = _SENTENCE_SPLIT_RE.split(joined)
        for piece in pieces:
            piece = piece.strip()
            if piece:
                claims.append(piece)

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush_paragraph()
            continue
        match = _BULLET_RE.match(line)
        if match:
            flush_paragraph()
            claims.append(match.group(1).strip())
            continue
        paragraph.append(line)

    flush_paragraph()
    return claims


def classify_claim(claim: str, orientation: str) -> dict[str, str]:
    claim_norm = _normalize(claim)
    orient_norm = _normalize(orientation)
    classification = _classify_claim(claim, claim_norm, orient_norm)
    evidence = _build_evidence(claim, classification, orientation, claim_norm, orient_norm)
    rewrite = _suggested_rewrite(claim, classification)
    return {
        "claim": claim,
        "classification": classification,
        "evidence": evidence,
        "rewrite": rewrite,
    }


def _classify_claim(claim: str, claim_norm: str, orient_norm: str) -> str:
    if _is_grounded(claim_norm, orient_norm):
        return "grounded"
    if _is_contradicted(claim_norm, orient_norm):
        return "contradicted"
    if _is_speculative(claim_norm):
        return "speculative"
    if _is_unclear(claim_norm):
        return "unclear"
    return "unsupported"


def _is_grounded(claim_norm: str, orient_norm: str) -> bool:
    if not claim_norm:
        return False
    if claim_norm in orient_norm or orient_norm in claim_norm:
        return True

    claim_tokens = _significant_tokens(claim_norm)
    if len(claim_tokens) < 3:
        return False

    orient_tokens = set(_significant_tokens(orient_norm))
    overlap = [token for token in claim_tokens if token in orient_tokens]
    return len(overlap) >= max(3, len(claim_tokens) - 1)


def _is_speculative(claim_norm: str) -> bool:
    if "chatbot" in claim_norm or "chat surface" in claim_norm or "voice agent" in claim_norm:
        return True
    if "could be applied" in claim_norm or "can be applied" in claim_norm or "might be applied" in claim_norm:
        return True
    if "future" in claim_norm or "potential" in claim_norm:
        return True
    if "for example" in claim_norm or "could help" in claim_norm or "may be used" in claim_norm:
        return True
    return False


def _is_contradicted(claim_norm: str, orient_norm: str) -> bool:
    if ("hand edited" in claim_norm or "manually edited" in claim_norm) and (
        "regenerable" in orient_norm or "runtime derived" in orient_norm or "runtime anchor" in orient_norm
    ):
        return True
    if "manual edit" in claim_norm and (
        "regenerable" in orient_norm or "runtime derived" in orient_norm or "runtime anchor" in orient_norm
    ):
        return True
    return False


def _is_unclear(claim_norm: str) -> bool:
    if len(claim_norm) < 8:
        return True
    if claim_norm in {"it", "this", "that", "these", "those"}:
        return True
    if len(_significant_tokens(claim_norm)) < 2:
        return True
    return False


def _build_evidence(
    claim: str,
    classification: str,
    orientation: str,
    claim_norm: str,
    orient_norm: str,
) -> str:
    if classification == "grounded":
        snippet = _find_snippet(orientation, claim)
        if snippet:
            return f"Found matching orientation text: {snippet}"
        return "Strong lexical overlap with the current orientation."
    if classification == "contradicted":
        if "hand-edited" in claim_norm:
            return "Orientation describes the inventory as runtime-derived/regenerable, which conflicts with a hand-edited claim."
        if "manual edit" in claim_norm:
            return "Orientation treats the inventory as runtime-derived/regenerable, not as a manual source of truth."
        return "The claim conflicts with a direct orientation rule."
    if classification == "speculative":
        return "The wording points to a possible future application or tentative use case, but the current orientation does not document it."
    if classification == "unclear":
        return "The claim is too vague to map confidently to the current orientation."
    return "No direct match found in the current orientation."


def _suggested_rewrite(claim: str, classification: str) -> str:
    if classification == "grounded":
        return claim
    if classification == "contradicted":
        return "Rephrase to match the orientation's runtime-derived, source-of-truth framing."
    if classification == "speculative":
        return "Frame this as a possible use case and note that it is not documented in the current orientation."
    if classification == "unclear":
        return "Make the claim more specific, or tie it to an explicit line from the orientation."
    return "Add a citation to the orientation or rewrite this as a qualified possibility."


def render_report(
    response_path: Path,
    claims: list[str],
    rows: list[dict[str, str]],
    orientation: str,
) -> str:
    counts = {name: 0 for name in CLAIM_CLASSIFICATIONS}
    for row in rows:
        counts[row["classification"]] += 1

    lines: list[str] = []
    lines.append("# context-kit response audit")
    lines.append("")
    lines.append(f"- Response: `{response_path}`")
    lines.append("- Scope: heuristic/manual scaffold; human review required.")
    lines.append("- Orientation: current `context-kit orient` output.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| total claims | grounded | unsupported | speculative | contradicted |")
    lines.append("|---|---:|---:|---:|---:|")
    lines.append(
        f"| {len(claims)} | {counts['grounded']} | {counts['unsupported']} | {counts['speculative']} | {counts['contradicted']} |"
    )
    lines.append("")
    lines.append("## Claims")
    lines.append("")
    lines.append("| Claim | Classification | Evidence / why | Suggested safer rewrite |")
    lines.append("|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| {_escape_md(row['claim'])} | {row['classification']} | {_escape_md(row['evidence'])} | {_escape_md(row['rewrite'])} |"
        )
    lines.append("")
    lines.append("## Orientation Used")
    lines.append("")
    lines.append("```text")
    lines.append(orientation.rstrip())
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _normalize(text: str) -> str:
    lowered = text.lower().strip()
    lowered = _PUNCT_RE.sub(" ", lowered)
    return _SPACE_RE.sub(" ", lowered).strip()


def _significant_tokens(text: str) -> list[str]:
    tokens = [token for token in _normalize(text).split() if token and token not in {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "it", "is", "are", "be", "this", "that"}]
    return tokens


def _find_snippet(haystack: str, needle: str) -> str:
    hay_norm = _normalize(haystack)
    nee_norm = _normalize(needle)
    if nee_norm and nee_norm in hay_norm:
        for line in haystack.splitlines():
            if nee_norm in _normalize(line):
                return line.strip()

    needle_tokens = _significant_tokens(needle)
    if not needle_tokens:
        return ""

    best_line = ""
    best_score = 0
    for line in haystack.splitlines():
        line_tokens = set(_significant_tokens(line))
        score = sum(1 for token in needle_tokens if token in line_tokens)
        if score > best_score:
            best_score = score
            best_line = line.strip()
    if best_score >= max(2, len(needle_tokens) // 2):
        return best_line
    return ""


def _escape_md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def _resolve_project_path(project_value: str | None) -> Path | None:
    project = Path(project_value).expanduser().resolve() if project_value else Path.cwd().resolve()
    if not project.exists():
        sys.stderr.write(f"error: --project path does not exist: {project}\n")
        return None
    if not project.is_dir():
        sys.stderr.write(f"error: --project path is not a directory: {project}\n")
        return None
    if not _looks_like_context_kit_project(project):
        sys.stderr.write(
            f"error: --project path does not look like a context-kit project: {project}\n"
            "  Expected to find '00-START-NEXT-SESSION.md' or 'docs/docs-pattern/' here.\n"
        )
        return None
    return project


def _looks_like_context_kit_project(project: Path) -> bool:
    return (project / "00-START-NEXT-SESSION.md").is_file() or (project / "docs" / "docs-pattern").is_dir()
