"""context-kit adopt — minimal v0.

Retrofits context-kit's docs layer onto an existing project. Detects a
basic stack from manifest files, asks the user two questions, and
generates the load-bearing docs (BUILD_PLAN.md, *_WHAT_IT_IS.md,
00-START-NEXT-SESSION.md, plus a CLAUDE.md augmentation).

This is the v0 from the SESSION_009 design proposal — proves the
concept end-to-end without the multi-stack handling, confidence
scoring, or recommend-stack integration described for the full
release. Source code is never modified; only docs are written.
"""

from __future__ import annotations

import argparse
import hashlib
import html as _html
import os
import sys
import tempfile
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Marker convention mirrors seed.py and inventory.py: anything inside
# the start/end markers is auto-generated and safe to overwrite on
# re-run; anything outside is human content and must be preserved.
START_MARKER = "<!-- context-kit:adopt:start -->"
END_MARKER = "<!-- context-kit:adopt:end -->"


@dataclass
class StackProfile:
    """What we detected about the project's stack.

    ``language`` is the *primary* language (the one the AI should
    treat as default). ``parts`` is non-empty for split monorepos
    where each subdir has its own stack — e.g.
    ``{"backend": "python", "frontend": "javascript"}``. When parts
    is populated the generators render a per-subdir stack table
    instead of a single-line summary.
    """

    language: str  # "javascript" | "python" | "unknown"
    signals: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # v0.1: per-subdir detection results. Populated only when the
    # repo root has no top-level manifest and one or more recognized
    # subdirectories (backend, frontend, etc.) carry their own.
    parts: dict[str, str] = field(default_factory=dict)
    # v0.1: which manifest file each part was detected from. Parallel
    # keys to ``parts``. Lets the BUILD_PLAN render "(detected from
    # backend/manage.py)" instead of just naming the language.
    part_signals: dict[str, str] = field(default_factory=dict)
    # v0.2: visibility-first fallback. Depth-1 child directories that
    # the classifier didn't pick up — by name, with whatever manifest-
    # shaped files and notable source extensions are inside. See
    # ``UnclassifiedSubdir`` and ``scan_unclassified_subdirs``.
    unclassified_subdirs: list[UnclassifiedSubdir] = field(default_factory=list)
    # v0.8: depth-2 walk inside known workspace containers (apps/,
    # packages/, services/, crates/, members/, workspaces/). Each
    # entry is one child project (e.g. apps/forge, apps/next). Pure
    # data — does NOT change classification: ``language``, ``parts``,
    # and ``unclassified_subdirs`` are computed exactly as in v0.7.
    # Renderers do not yet consume this field; v0.8 only gets the
    # data model right so a follow-up ship can teach the BUILD_PLAN
    # / HTML report / failure analyzer to use it.
    workspace_children: list[WorkspaceChild] = field(default_factory=list)
    # v0.8 Phase 4.5: when the root scan returns ``language ==
    # "unknown"`` but every non-trivial workspace child shares the
    # same strong Phase 3 stack label, ``detect_stack`` promotes
    # that label here. Renderers prefer it over the bare
    # "Unknown stack" line. Never set when language is "javascript"
    # or "python" — root detections stay authoritative.
    inferred_primary: Optional[str] = None


@dataclass
class UnclassifiedSubdir:
    """A depth-1 child directory the visibility-first scan surfaced.

    See SESSION_009_ADOPT.md §19 — "Never allow real project structure
    to be invisible." This is what the scanner produces for any
    non-hidden depth-1 child directory that wasn't classified into
    ``StackProfile.parts``. Classification stays narrow (it only
    reports what it can confidently call); visibility-first reports
    everything else by name so the user (and any AI session reading
    the generated docs) can't miss a subdir that adopt couldn't
    classify.

    Fields are intentionally descriptive, not classifying:
    - ``manifest_files``: filenames that *look like* manifests but
      adopt isn't claiming to know what they are.
    - ``notable_extensions``: count per file extension that's in
      ``NOTABLE_EXTENSIONS`` (capped scan; see MAX_FILES_PER_SUBDIR).
    - ``example_paths``: one example relative path per extension so
      the user / AI can one-keystroke navigate to a real file.
    - ``note``: optional "X files suggest Y; verify with user" hint
      derived from the dominant domain extension via DOMAIN_HINTS.
      Empty for generic-language-only subdirs (.py / .js / .ts) —
      the manifest filenames already tell that story.
    - ``is_empty``: dir exists but the scan found nothing inside.
      Worth surfacing explicitly (see example-name-service's empty
      ``api/`` placeholder in SESSION_009_ADOPT.md §19).
    """

    name: str
    manifest_files: list[str] = field(default_factory=list)
    notable_extensions: dict[str, int] = field(default_factory=dict)
    example_paths: dict[str, str] = field(default_factory=dict)
    note: Optional[str] = None
    # v0.2.x: lightweight pattern-based hint derived from a *combination*
    # of manifest filenames (e.g. package.json + vite.config.* +
    # tailwind.config.* -> "Vite + Tailwind web app"). Independent of
    # ``note`` (which is a per-extension hint). Both surface in renders
    # so the AI session and the human get the strongest available
    # signal. Not a full framework detector — see _manifest_hint.
    manifest_hint: Optional[str] = None
    # True only when the dir literally has zero files (rare — usually
    # an empty placeholder like example-name-service's ``api/``).
    is_empty: bool = False
    # Total file count seen during the scan (capped at MAX_FILES_PER_SUBDIR).
    # Lets the dry-run distinguish "truly empty" from "has files but
    # none with extensions we recognize" — the second case shows up for
    # dirs full of .json / .md / config files (e.g. example-django-app's
    # agents/ contains JSON dumps but no .py source).
    total_file_count: int = 0


@dataclass
class WorkspaceChild:
    """A child project found at depth-2 inside a known workspace
    container (apps/, packages/, services/, crates/, members/,
    workspaces/).

    v0.8 introduces this as pure data on ``StackProfile``. The point
    is to make depth-2 child projects visible to downstream code
    without flattening them into ``unclassified_subdirs`` (depth-1
    only) or rewriting the depth-1 classifier. The v0.8 ship does
    *not* change classification or rendering — that's a follow-up.

    Fields:
    - ``name``: container/child path (e.g. "apps/forge"). Always
      includes the container prefix so downstream code can
      distinguish "apps/foo" from "packages/foo".
    - ``manifest_files``: filenames at the immediate top of the
      child that look manifest-shaped (same definition as
      ``UnclassifiedSubdir.manifest_files``).
    - ``notable_extensions``: per-extension count from a depth-2
      walk inside the child, capped at ``MAX_FILES_PER_SUBDIR`` and
      filtered through the same generic-vs-domain threshold rules
      as the visibility scan.
    - ``hint``: a single best-effort label. Prefers the manifest
      pattern hint (Vite + Tailwind, Expo, etc.); falls back to the
      dominant DOMAIN_HINTS extension note. ``None`` when neither
      applies.
    """

    name: str
    manifest_files: list[str] = field(default_factory=list)
    notable_extensions: dict[str, int] = field(default_factory=dict)
    hint: Optional[str] = None


@dataclass
class AdoptionInputs:
    """The user-provided context we collect during adopt.

    ``project_description`` and ``next_step`` are the two
    interactive prompts (also settable via
    ``--project-summary`` / ``--next-task``). ``notes`` is a
    flag-only addition (``--notes``) for findings the user
    already discovered during a prior dry-run / probe pass —
    they're preserved verbatim in the Agent Launch Prompt and
    every generated doc so trust isn't lost when the user later
    runs ``--write`` with a refined summary.
    """

    project_description: str
    next_step: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Failure taxonomy (v0.2.x)
# ---------------------------------------------------------------------------
#
# Each detected issue during an adopt run is classified into one of a
# fixed set of failure types. The taxonomy is intentionally small and
# closed — additions require a code change. No dynamic categories, no
# AI-generated labels, no confidence scoring. Detectors are
# deterministic rules over StackProfile + plan and live in
# ``analyze_failures``. See SESSION_009_ADOPT.md §15 for the dogfood
# evidence each category was distilled from.

FAILURE_ROOT_SIGNAL_OVERRIDE = "ROOT_SIGNAL_OVERRIDE"
FAILURE_UNRECOGNIZED_ECOSYSTEM = "UNRECOGNIZED_ECOSYSTEM"
FAILURE_SILENT_SUBDIR_DROP = "SILENT_SUBDIR_DROP"
FAILURE_WRAPPER_DIRECTORY_INVISIBILITY = "WRAPPER_DIRECTORY_INVISIBILITY"
FAILURE_NOISE_DIRECTORY_POLLUTION = "NOISE_DIRECTORY_POLLUTION"
FAILURE_IDEMPOTENCY_RISK = "IDEMPOTENCY_RISK"
FAILURE_MISLEADING_CLASSIFICATION = "MISLEADING_CLASSIFICATION"
FAILURE_MISSING_FRAMEWORK_DETECTION = "MISSING_FRAMEWORK_DETECTION"
FAILURE_STRUCTURE_UNDERREPRESENTED = "STRUCTURE_UNDERREPRESENTED"
# v0.3 — proposed in SESSION_009_ADOPT.md §22 after the
# context-kit-dogfood-repos batch (example-web3-monorepo / expo-monorepo-example /
# turborepo-next-django-starter / flutter-monorepo-example) showed
# 3 of 5 monorepo clones emitting zero failure records under v0.2.x
# despite obvious depth-2 invisibility.
FAILURE_MONOREPO_DEPTH_LIMIT = "MONOREPO_DEPTH_LIMIT"

FAILURE_TYPES = frozenset({
    FAILURE_ROOT_SIGNAL_OVERRIDE,
    FAILURE_UNRECOGNIZED_ECOSYSTEM,
    FAILURE_SILENT_SUBDIR_DROP,
    FAILURE_WRAPPER_DIRECTORY_INVISIBILITY,
    FAILURE_NOISE_DIRECTORY_POLLUTION,
    FAILURE_IDEMPOTENCY_RISK,
    FAILURE_MISLEADING_CLASSIFICATION,
    FAILURE_MISSING_FRAMEWORK_DETECTION,
    FAILURE_STRUCTURE_UNDERREPRESENTED,
    FAILURE_MONOREPO_DEPTH_LIMIT,
})

FAILURE_SEVERITIES = ("low", "medium", "high")
FAILURE_SURFACE_AREAS = ("classification", "visibility", "safety", "UX")


@dataclass
class FailureRecord:
    """One labeled issue detected during an adopt run.

    Pure metadata — emitting a FailureRecord doesn't change adopt's
    classification or written output. The records surface in the
    "Diagnostic signals" section of the HTML report and a compact CLI
    summary so a reviewer can spot patterns without re-deriving them
    from the dry-run text every time.
    """

    failure_type: str       # one of FAILURE_TYPES
    severity: str           # one of FAILURE_SEVERITIES
    surface_area: str       # one of FAILURE_SURFACE_AREAS
    description: str        # 1-2 sentence summary
    detected_in: str        # subdir name or "root"
    example: str            # short concrete pointer (filename / path / name)


@dataclass
class PlannedFile:
    """One file the adopt run intends to create or augment.

    ``kind`` is "create" when the file doesn't exist yet, "augment"
    when we'll append a managed block to an existing file. We never
    overwrite a file outside its managed block.
    """

    path: Path
    content: str
    kind: str  # "create" | "augment"


# ---------------------------------------------------------------------------
# Layer 1: detection (read-only)
# ---------------------------------------------------------------------------


# v0.1: subdirs we'll look inside when the root has no manifest.
# Order matters — the first hit becomes the primary stack when no
# ``backend`` is detected (backend wins by convention; see _pick_primary).
RECOGNIZED_SUBDIRS = ("backend", "frontend", "web", "mobile", "api", "client", "server")


def _detect_in_dir(d: Path) -> tuple[str, list[str]]:
    """Return ``(language, signals)`` for a single directory.

    ``language`` is "javascript" | "python" | "rust" | "go" |
    "unknown". ``signals`` lists the manifest filenames found in
    ``d`` (for reporting; not prefixed with the directory). Mixed
    JS+Python in the same directory still resolves to JavaScript
    with a mixed-root note appended at the call site (Phase 5.1
    later overrides via source-dominance check).

    JS/Python take precedence over Rust/Go when multiple manifests
    coexist at root — keeps Phase 5.1's mixed-root resolution as
    the single source of truth for language tie-breaks.
    """
    signals: list[str] = []
    if (d / "package.json").is_file():
        signals.append("package.json")
    if (d / "manage.py").is_file():
        signals.append("manage.py")
    if (d / "requirements.txt").is_file():
        signals.append("requirements.txt")
    if (d / "pyproject.toml").is_file():
        signals.append("pyproject.toml")
    if (d / "go.mod").is_file():
        signals.append("go.mod")
    if (d / "Cargo.toml").is_file():
        signals.append("Cargo.toml")
    has_js = "package.json" in signals
    has_py = any(s in signals for s in ("manage.py", "requirements.txt", "pyproject.toml"))
    has_go = "go.mod" in signals
    has_rust = "Cargo.toml" in signals
    if has_js and has_py:
        return "javascript", signals  # caller decides whether to add a note
    if has_js:
        return "javascript", signals
    if has_py:
        return "python", signals
    if has_go:
        return "go", signals
    if has_rust:
        return "rust", signals
    return "unknown", signals


# v0.9 Phase 5.1 — mixed-root resolution. Used by detect_stack
# only when both JS and Python root manifests are present. The
# walk is bounded by these constants so even pathological repos
# (django/django itself surfaces ~377 .py at depth-2) resolve
# in well under a second.
_MIXED_ROOT_BUDGET = 5000           # max files inspected
_MIXED_ROOT_MIN_DOMINANT = 5        # winner needs at least this many
_MIXED_ROOT_RATIO = 3               # winner needs >= ratio * loser


def _root_source_evidence(repo: Path) -> dict[str, int]:
    """Shallow source-extension counts for mixed-root resolution.

    Walks ``repo`` to depth 2, skipping hidden directories and
    anything ``_is_noise_dir`` flags (venv variants, node_modules,
    dist/build, etc.). Counts only the five extensions that matter
    for distinguishing a Python primary from a JavaScript primary.

    Cost-bounded by ``_MIXED_ROOT_BUDGET``. Pure I/O — no other
    side effects.
    """
    counts: dict[str, int] = {
        ".py": 0, ".js": 0, ".ts": 0, ".tsx": 0, ".jsx": 0,
    }
    seen = 0
    try:
        for root, dirs, files in os.walk(repo):
            rel = Path(root).relative_to(repo)
            if len(rel.parts) > 2:
                dirs[:] = []
                continue
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and not _is_noise_dir(d)
            ]
            for name in files:
                seen += 1
                if seen > _MIXED_ROOT_BUDGET:
                    break
                ext = Path(name).suffix.lower()
                if ext in counts:
                    counts[ext] += 1
            if seen > _MIXED_ROOT_BUDGET:
                break
    except OSError:
        pass
    return counts


def _resolve_mixed_root(repo: Path,
                        signals: list[str]) -> tuple[str, str]:
    """Decide JS vs Python at root when both manifests are present.

    Counts shallow ``.py`` vs ``.js`` / ``.ts`` / ``.tsx`` / ``.jsx``
    evidence at depth ≤ 2. Picks the dominant side when one side has
    at least ``_MIXED_ROOT_MIN_DOMINANT`` files AND at least
    ``_MIXED_ROOT_RATIO`` × the other side's count. Otherwise falls
    back to JavaScript (preserves the v0 default for callers that
    haven't been audited) and notes the inconclusiveness.

    Returns ``(language, note)`` where note explains which side won
    and why. Pure modulo the underlying source walk.
    """
    counts = _root_source_evidence(repo)
    py = counts.get(".py", 0)
    js = sum(counts.get(e, 0) for e in (".js", ".ts", ".tsx", ".jsx"))
    py_signal = next(
        (s for s in signals
         if s in ("manage.py", "requirements.txt", "pyproject.toml")),
        "Python manifest",
    )
    if py >= _MIXED_ROOT_MIN_DOMINANT and py >= _MIXED_ROOT_RATIO * js:
        return ("python", (
            f"Mixed root manifests (package.json + {py_signal}); "
            f"Python primary based on source dominance "
            f"({py} .py files vs {js} .js/.ts/.tsx/.jsx files at "
            f"depth ≤ 2)."
        ))
    if js >= _MIXED_ROOT_MIN_DOMINANT and js >= _MIXED_ROOT_RATIO * py:
        return ("javascript", (
            f"Mixed root manifests (package.json + {py_signal}); "
            f"JavaScript primary based on source dominance "
            f"({js} .js/.ts/.tsx/.jsx files vs {py} .py files at "
            f"depth ≤ 2)."
        ))
    return ("javascript", (
        f"Mixed root manifests (package.json + {py_signal}); source "
        f"counts inconclusive ({py} .py vs {js} .js/.ts/.tsx/.jsx "
        f"at depth ≤ 2). Defaulting to JavaScript — Stack reality "
        f"confidence is downgraded to Medium because mixed-root "
        f"setups rarely behave as a single stack."
    ))


def _pick_primary(parts: dict[str, str]) -> str:
    """Backend wins by convention; otherwise first detected in scan order.

    The "backend wins" rule comes from the dogfood split-monorepo
    shape (example-web-app, example-tracker-app, etc.). Backend is where the
    domain logic lives, so the AI session's default frame is best
    anchored there. A user who disagrees can edit BUILD_PLAN.md.
    """
    if "backend" in parts and parts["backend"] != "unknown":
        return parts["backend"]
    for sub in RECOGNIZED_SUBDIRS:
        if parts.get(sub) and parts[sub] != "unknown":
            return parts[sub]
    return "unknown"


def detect_stack(repo: Path) -> StackProfile:
    """Detect the project's stack, root-first then one level deep.

    Order:
      1. Scan ``repo`` root. If any manifest is found there, return
         that profile and ignore subdirs (root wins; preserves v0
         behavior for single-stack repos like ai-content-studio).
      2. Otherwise, scan each recognized subdir
         (backend / frontend / web / mobile / api / client / server)
         for the same set of manifests. Populate ``parts`` per
         subdir. ``language`` becomes the primary (backend if
         present, else first detected, else unknown).

    Depth is capped at 1 by design. Microservice / Turborepo shapes
    (``apps/<name>/...``) are intentionally not handled yet — that's
    v0.2's job.
    """
    # Step 1: root scan. Existing v0 behavior.
    root_lang, root_signals = _detect_in_dir(repo)
    if root_signals:
        notes: list[str] = []
        # v0.9 Phase 5.1 — when both JS and Python root manifests
        # are present, walk shallow source evidence to decide which
        # side is the actual primary. v0 always picked JavaScript;
        # that produced the django/django dogfood failure where 198
        # .py files in django/ + 163 in tests/ silently lost to a
        # tooling-only root package.json.
        if (
            "package.json" in root_signals
            and any(s in root_signals for s in ("manage.py", "requirements.txt", "pyproject.toml"))
        ):
            root_lang, mixed_note = _resolve_mixed_root(repo, root_signals)
            notes.append(mixed_note)
        profile = StackProfile(language=root_lang, signals=root_signals, notes=notes)
        profile.unclassified_subdirs = scan_unclassified_subdirs(repo, set(profile.parts))
        profile.workspace_children = scan_workspace_children(repo)
        return profile

    # Step 2: one-level-deep scan into recognized subdirs only.
    parts: dict[str, str] = {}
    part_signals: dict[str, str] = {}
    aggregated_signals: list[str] = []
    for sub in RECOGNIZED_SUBDIRS:
        d = repo / sub
        if not d.is_dir():
            continue
        lang, sigs = _detect_in_dir(d)
        if not sigs:
            continue
        parts[sub] = lang
        # Surface the most informative signal per subdir (the first
        # match in the canonical priority of _detect_in_dir).
        part_signals[sub] = sigs[0]
        for s in sigs:
            aggregated_signals.append(f"{sub}/{s}")

    if parts:
        primary = _pick_primary(parts)
        notes = [
            "Split monorepo detected. Per-subdir stack listed below; "
            "deeper layouts (apps/<name>/...) are not yet handled."
        ]
        profile = StackProfile(
            language=primary,
            signals=aggregated_signals,
            notes=notes,
            parts=parts,
            part_signals=part_signals,
        )
        profile.unclassified_subdirs = scan_unclassified_subdirs(repo, set(profile.parts))
        profile.workspace_children = scan_workspace_children(repo)
        return profile

    # Nothing at root, nothing in recognized subdirs.
    profile = StackProfile(
        language="unknown",
        signals=[],
        notes=[
            "No package.json, manage.py, requirements.txt, or pyproject.toml "
            "found at repo root or in recognized subdirs "
            f"({', '.join(RECOGNIZED_SUBDIRS)})."
        ],
    )
    profile.unclassified_subdirs = scan_unclassified_subdirs(repo, set(profile.parts))
    profile.workspace_children = scan_workspace_children(repo)
    # v0.8 Phase 4.5 — only when root detection returned unknown:
    # if every non-trivial workspace child shares a single Phase 3
    # label that maps to one of the three inferable primaries
    # (Flutter / Solidity / Next.js), promote it. JS / Python root
    # detections are never overridden — the early returns above
    # already short-circuited those paths.
    profile.inferred_primary = _infer_primary_from_workspace(
        profile.workspace_children
    )
    return profile


def derive_project_title(repo: Path) -> str:
    """Use the directory basename as the project title (Title Case)."""
    raw = repo.resolve().name or "Project"
    # Replace common separators with spaces then title-case word-by-word.
    cleaned = raw.replace("-", " ").replace("_", " ").strip()
    return " ".join(w.capitalize() for w in cleaned.split()) or "Project"


# ---------------------------------------------------------------------------
# Layer 1.5: visibility-first fallback (v0.2, see SESSION_009_ADOPT.md §19)
# ---------------------------------------------------------------------------
#
# Core principle: never allow real project structure to be invisible.
# Classification (Layer 1) stays narrow; this layer reports what
# classification *missed* so an AI session reading the generated docs
# can't be unaware of (say) a contracts/ directory full of .sol files
# in a project the classifier called "JavaScript". See §19's worked
# examples for example-django-app, example-mobile-app, example-clarity-contract,
# example-name-service, and example-solidity-app.
#
# Per-ecosystem detection is deferred. The data tables below say what
# files *suggest* without committing to what they *are* — a deliberate
# choice to avoid the per-ecosystem-detector treadmill (Solidity, Move,
# Anchor, Cadence, Foundry, Hardhat, Brownie, Truffle, Reflex, Flutter,
# ...). Each ecosystem we'd otherwise need to support is one row in
# DOMAIN_HINTS.

# Skip these in the depth-1 walk. Hidden dirs (anything starting with
# ".") are also skipped at the call site, which catches .venv / .git /
# .next / .nuxt / .turbo / .idea / .vscode / .cache / .coverage etc.
# without enumerating them here.
NOISE_EXACT = frozenset({
    "node_modules", "__pycache__",
    "dist", "build", "out", "target",
    "coverage", "htmlcov",
    "media",  # static media uploads — no source code worth surfacing
})

# Pattern-based noise: a directory whose name *starts with* one of these
# prefixes followed by EOL or a separator (-, _, .) is treated as a
# variant of the prefix. So "venv_ml", "venv-prod", "venv.old" all match
# the "venv" prefix, but "venvelope" doesn't (no separator after the
# prefix) and stays visible. Lesson from the example-monorepo dogfood
# where ``venv_ml/`` slipped past exact-name matching.
NOISE_PREFIXES = ("venv", "env", "pyenv", "virtualenv")

# Backwards-compat alias for code/tests that imported NOISE_DIRS in v0.2.
# Kept as the union of exact names for the most-common actual-name
# lookups; pattern-aware callers should use ``_is_noise_dir`` instead.
NOISE_DIRS = NOISE_EXACT | frozenset(NOISE_PREFIXES)


def _is_noise_dir(name: str) -> bool:
    """Pattern-aware noise-dir check. See NOISE_EXACT / NOISE_PREFIXES."""
    if name in NOISE_EXACT:
        return True
    for prefix in NOISE_PREFIXES:
        if name == prefix:
            return True
        if (name.startswith(prefix)
                and len(name) > len(prefix)
                and name[len(prefix)] in "-_."):
            return True
    return False

# Filenames we explicitly know are project-defining manifests. Used by
# both classification (Layer 1) and the visibility-first scan, but with
# different downstream effects: classification returns a language;
# visibility just reports presence.
KNOWN_MANIFEST_NAMES = frozenset({
    # JS/TS
    "package.json",
    # Python
    "manage.py", "requirements.txt", "pyproject.toml", "Pipfile", "rxconfig.py",
    # Mobile/native
    "pubspec.yaml", "Podfile",
    # Other ecosystems
    "Cargo.toml", "go.mod", "Gemfile",
    # Web3 / smart contracts
    "Clarinet.toml", "foundry.toml", "truffle-config.js",
    "hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs",
    "hardhat.config.mjs", "brownie-config.yaml",
    "Anchor.toml", "Move.toml", "flow.json",
    # Infra-shaped (worth flagging if alone in a subdir)
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile",
})

# Files that LOOK manifest-shaped but are noise (lock files, editor
# configs, linter configs). Filtered out so the unknown-but-present
# section stays signal-only.
NOT_MANIFEST_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "tsconfig.json", "jsconfig.json",
    "analysis_options.yaml",  # Dart analyzer
    ".eslintrc.json", ".prettierrc",
    "vercel.json",  # deploy config, not project-defining
})

# Generic-language extensions: surfaced only when they exceed
# MIN_SOURCE_FILES_TO_REPORT (3) so a stray .py file in a JS project
# doesn't add noise. Domain extensions (DOMAIN_HINTS below) surface at
# any count >= 1 because a single .sol or .clar file is meaningful.
GENERIC_EXTENSIONS = {
    ".py":  "Python",
    ".ts":  "TypeScript",
    ".tsx": "TSX",
    ".js":  "JavaScript",
    ".jsx": "JSX",
}

# Domain-specific extensions: ext -> "X files suggest Y" hint text.
# Adding a new ecosystem to visibility = one row here. Each row is
# data, not code — no detector functions, no classification logic
# behind these. The "verify with user" framing is load-bearing: adopt
# is making a hint, not a claim.
DOMAIN_HINTS = {
    ".sol":     ".sol files suggest Solidity / EVM smart contracts",
    ".clar":    ".clar files suggest Clarity / Stacks smart contracts",
    ".cdc":     ".cdc files suggest Cadence / Flow blockchain",
    ".cadence": ".cadence files suggest Cadence / Flow blockchain",
    ".circom":  ".circom files suggest zk-SNARK circuits (Circom)",
    ".move":    ".move files suggest Move smart contracts (Sui/Aptos)",
    ".cairo":   ".cairo files suggest Cairo / StarkNet",
    ".fc":      ".fc files suggest FunC / TON smart contracts",
    ".dart":    ".dart files suggest Dart / Flutter",
    ".rs":      ".rs files suggest Rust",
    ".go":      ".go files suggest Go",
    ".rb":      ".rb files suggest Ruby",
    ".swift":   ".swift files suggest Swift",
    ".kt":      ".kt files suggest Kotlin",
    ".scala":   ".scala files suggest Scala",
    ".ex":      ".ex files suggest Elixir",
    ".elm":     ".elm files suggest Elm",
    ".ipynb":   ".ipynb files suggest Jupyter notebooks (interactive Python)",
}

DOMAIN_LABELS = {
    ".sol": "Solidity", ".clar": "Clarity", ".cdc": "Cadence",
    ".cadence": "Cadence", ".circom": "Circom", ".move": "Move",
    ".cairo": "Cairo", ".fc": "FunC", ".dart": "Dart", ".rs": "Rust",
    ".go": "Go", ".rb": "Ruby", ".swift": "Swift", ".kt": "Kotlin",
    ".scala": "Scala", ".ex": "Elixir", ".elm": "Elm",
    ".ipynb": "Jupyter notebook",
}

# Cost bounds for the depth-2 walk. A project with 5,000 .py files
# in a single subdir would exhaust the count without these.
MIN_SOURCE_FILES_TO_REPORT = 3   # generic extensions need >= this to report
MAX_FILES_PER_SUBDIR = 200       # bail when a subdir scan exceeds this
MAX_DEPTH_INSIDE_SUBDIR = 2      # walk depth (1 = just immediate contents)


def _is_manifest_like(name: str) -> bool:
    """True iff ``name`` looks like a project-defining manifest.

    Conservative on purpose: explicit allow list + a couple of pattern
    rules + an explicit deny list. Lock files and editor configs are
    excluded so the unknown-but-present section stays signal-only.
    """
    if name in NOT_MANIFEST_NAMES:
        return False
    if name in KNOWN_MANIFEST_NAMES:
        return True
    # Pattern: top-level *.config.{js,ts,mjs,cjs} (next.config.mjs,
    # vite.config.ts, etc.) — these define the project's framework
    # and are worth surfacing.
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        if ext in ("js", "ts", "mjs", "cjs") and stem.endswith(".config"):
            return True
    # Pattern: any *.toml at top level. Catches future ecosystems
    # (foundry.toml is in KNOWN_MANIFEST_NAMES already, but a hypothetical
    # newproject.toml would be surfaced too).
    if name.endswith(".toml") and not name.startswith("."):
        return True
    return False


def _scan_subdir_contents(d: Path) -> tuple[list[str], dict[str, int], dict[str, str], int]:
    """Walk ``d`` to ``MAX_DEPTH_INSIDE_SUBDIR`` and return:
       (manifest filenames at depth 1, extension counts, example paths,
        total file count seen).

    Cost-bounded: stops after ``MAX_FILES_PER_SUBDIR`` files. Skips
    hidden dirs and ``NOISE_DIRS``. The total file count is reported
    so callers can distinguish "truly empty" from "has files but none
    with extensions we track".
    """
    manifests: list[str] = []
    ext_counts: dict[str, int] = {}
    example_paths: dict[str, str] = {}
    file_count = 0

    # Manifests are only meaningful at the immediate top of the subdir
    # (project-defining files don't typically nest 3 deep). Capture them
    # first, separately.
    try:
        for entry in d.iterdir():
            if entry.is_file() and _is_manifest_like(entry.name):
                manifests.append(entry.name)
    except OSError:
        return manifests, ext_counts, example_paths, file_count
    manifests.sort()

    # Then walk depth-2 for extension counts. os.walk + a file_count
    # cap keeps cost bounded on huge trees.
    try:
        for root, dirs, files in os.walk(d):
            rel = Path(root).relative_to(d)
            depth = len(rel.parts)
            if depth > MAX_DEPTH_INSIDE_SUBDIR:
                dirs[:] = []
                continue
            # Filter children we'll descend into.
            dirs[:] = [x for x in dirs if not _is_noise_dir(x) and not x.startswith(".")]
            for name in files:
                file_count += 1
                if file_count > MAX_FILES_PER_SUBDIR:
                    break
                ext = Path(name).suffix.lower()
                if not ext:
                    continue
                if ext in DOMAIN_HINTS or ext in GENERIC_EXTENSIONS:
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
                    if ext not in example_paths:
                        # Path relative to the repo root, anchored at
                        # the subdir's name. So a Foo.sol inside
                        # repo/contracts/Mocks/ surfaces as
                        # "contracts/Mocks/Foo.sol".
                        rel_path = (rel / name) if rel.parts else Path(name)
                        example_paths[ext] = str(Path(d.name) / rel_path)
            if file_count > MAX_FILES_PER_SUBDIR:
                break
    except OSError:
        pass

    return manifests, ext_counts, example_paths, file_count


def _manifest_hint(manifests: list[str]) -> Optional[str]:
    """Lightweight pattern hint from a combination of manifest filenames.

    Three patterns chosen from the example-monorepo dogfood, where
    pure Python+JS repos produced no DOMAIN_HINTS notes and the
    visual hierarchy collapsed to "everything is amber". These hints
    re-introduce some color contrast without being a full framework
    detector — that's still §15 backlog item #5.

    The patterns intentionally require the framework's *root config
    file* to be present (vite.config.*, tailwind.config.*,
    app.config.*, etc.), not just a guess from package.json deps. We
    don't open or parse files; we just check filename presence.
    """
    mset = set(manifests)
    has_pkg = "package.json" in mset
    has_vite = any(m.startswith("vite.config.") for m in mset)
    has_tw = any(m.startswith("tailwind.config.") for m in mset)
    has_expo = any(m.startswith("app.config.") for m in mset)
    if has_pkg and has_vite and has_tw:
        return ("Vite + Tailwind web app (likely frontend); "
                "verify with user")
    if has_pkg and has_expo:
        return "Expo / React Native mobile app; verify with user"
    if "requirements.txt" in mset:
        return ("Python subsystem with isolated dependencies "
                "(own requirements.txt); verify with user")
    return None


def _build_unclassified(name: str, manifests: list[str],
                        ext_counts: dict[str, int],
                        example_paths: dict[str, str],
                        total_file_count: int) -> UnclassifiedSubdir:
    """Apply reporting thresholds and pick a domain hint, if any."""
    # Filter generic extensions below the threshold; keep all domain
    # extensions at any count >= 1.
    reportable: dict[str, int] = {}
    for ext, count in ext_counts.items():
        if ext in DOMAIN_HINTS:
            reportable[ext] = count
        elif ext in GENERIC_EXTENSIONS and count >= MIN_SOURCE_FILES_TO_REPORT:
            reportable[ext] = count
    # Trim example paths to the extensions we kept.
    examples = {ext: p for ext, p in example_paths.items() if ext in reportable}
    # Pick a "dominant domain" hint if any domain ext is present.
    note = None
    domain_present = [ext for ext in reportable if ext in DOMAIN_HINTS]
    if domain_present:
        # Highest count wins; ties broken by sort order for determinism.
        domain_present.sort(key=lambda e: (-reportable[e], e))
        note = DOMAIN_HINTS[domain_present[0]] + "; verify with user"
    # is_empty means literally zero files in the scanned tree. A dir
    # with files of unrecognized extensions (.json, .md, .txt, ...) is
    # NOT empty — its file count surfaces via total_file_count so the
    # dry-run can distinguish "empty placeholder" from "has content
    # but none we can categorize".
    is_empty = total_file_count == 0 and not manifests
    return UnclassifiedSubdir(
        name=name,
        manifest_files=manifests,
        notable_extensions=reportable,
        example_paths=examples,
        note=note,
        manifest_hint=_manifest_hint(manifests),
        is_empty=is_empty,
        total_file_count=total_file_count,
    )


def scan_unclassified_subdirs(repo: Path,
                              already_classified: set[str]) -> list[UnclassifiedSubdir]:
    """Walk depth 1 of ``repo``; report what classification didn't.

    ``already_classified`` is the set of subdir names that
    ``detect_stack`` populated into ``StackProfile.parts``. Those are
    excluded — they're already named in the primary classification
    output. Hidden dirs and ``NOISE_DIRS`` are also skipped.

    The result is sorted by subdir name for deterministic output.
    """
    out: list[UnclassifiedSubdir] = []
    try:
        entries = sorted(repo.iterdir(), key=lambda e: e.name)
    except OSError:
        return out
    for entry in entries:
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith("."):
            continue
        if _is_noise_dir(name):
            continue
        if name in already_classified:
            continue
        manifests, ext_counts, examples, total_files = _scan_subdir_contents(entry)
        out.append(_build_unclassified(name, manifests, ext_counts, examples, total_files))
    return out


def scan_workspace_children(repo: Path) -> list[WorkspaceChild]:
    """Walk depth-2 inside known workspace containers; return children.

    v0.8 — additive depth-2 walk. Only enters directory names in
    ``_WORKSPACE_CONTAINERS`` (apps, packages, services, crates,
    members, workspaces) and walks exactly one level deeper. So
    ``apps/forge/`` is captured, but ``apps/forge/sub/`` is not.

    For each child, ``_scan_subdir_contents`` produces the manifests
    + extension counts (already capped at ``MAX_FILES_PER_SUBDIR``
    per child). Generic-vs-domain extension thresholds match the
    visibility-first scan so the data is shaped the same way.

    Empty children (no manifests, no notable extensions after
    threshold filtering) are dropped — they tell downstream code
    nothing useful and would only inflate the list.

    Hidden dirs and noise dirs are skipped at both the container
    and child level. Container-name dedup with classification is
    not needed because ``_WORKSPACE_CONTAINERS`` and
    ``RECOGNIZED_SUBDIRS`` don't overlap.

    The result is sorted by ``"<container>/<child>"`` for
    deterministic output.
    """
    out: list[WorkspaceChild] = []
    try:
        containers = sorted(repo.iterdir(), key=lambda e: e.name)
    except OSError:
        return out
    for container in containers:
        if not container.is_dir():
            continue
        cname = container.name
        if cname.startswith("."):
            continue
        if _is_noise_dir(cname):
            continue
        if cname not in _WORKSPACE_CONTAINERS:
            continue
        try:
            children = sorted(container.iterdir(), key=lambda e: e.name)
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            chname = child.name
            if chname.startswith("."):
                continue
            if _is_noise_dir(chname):
                continue
            manifests, ext_counts, _examples, _total = _scan_subdir_contents(child)
            # Apply the same threshold rules as the visibility scan:
            # domain extensions report at any count, generic
            # extensions only above MIN_SOURCE_FILES_TO_REPORT.
            reportable: dict[str, int] = {}
            for ext, count in ext_counts.items():
                if ext in DOMAIN_HINTS:
                    reportable[ext] = count
                elif ext in GENERIC_EXTENSIONS and count >= MIN_SOURCE_FILES_TO_REPORT:
                    reportable[ext] = count
            if not manifests and not reportable:
                # Empty placeholder child — nothing to report.
                continue
            # Single best-effort hint: framework manifest pattern
            # wins (Vite+Tailwind, Expo, etc.); else dominant
            # domain-extension hint.
            hint = _manifest_hint(manifests)
            if hint is None:
                domain_present = sorted(
                    [e for e in reportable if e in DOMAIN_HINTS],
                    key=lambda e: (-reportable[e], e),
                )
                if domain_present:
                    hint = DOMAIN_HINTS[domain_present[0]] + "; verify with user"
            out.append(WorkspaceChild(
                name=f"{cname}/{chname}",
                manifest_files=manifests,
                notable_extensions=reportable,
                hint=hint,
            ))
    return out


# ---------------------------------------------------------------------------
# Layer 2: generators (pure transforms)
# ---------------------------------------------------------------------------


def _classify_workspace_child(c: WorkspaceChild) -> Optional[str]:
    """Derive a short stack label for a single workspace child.

    v0.8 Phase 3 — *not* a full classifier. Only fires for the four
    obvious cases the user signed off on, in priority order:

    1. **Expo / React Native** — ``app.config.{js,ts,mjs,cjs}`` is
       uniquely Expo. Highest priority because it implies React
       Native rather than browser-Next.js.
    2. **Solidity / EVM** — ``foundry.toml`` or any ``.sol`` file.
    3. **Flutter / Dart** — ``pubspec.yaml`` or any ``.dart`` file.
    4. **Next.js / React** — ``next.config.*`` or ``package.json``
       with ``.tsx`` / ``.jsx`` source.

    Returns ``None`` for children that don't match any rule. The
    summary section is silent on those — better than guessing.

    Pure function over the workspace child; no I/O.
    """
    mset = set(c.manifest_files)
    exts = c.notable_extensions
    # v0.9 Phase 5.5 — mobile signals block the package.json+.tsx
    # fallback from misclassifying a React Native workspace as a
    # Next.js web app. Detected via configs that only mobile builds
    # produce (metro.config.*, react-native.config.*, Podfile,
    # Gemfile) and via .swift / .kt source files.
    has_mobile_config = (
        any(m.startswith("metro.config.") for m in mset)
        or any(m.startswith("react-native.config.") for m in mset)
        or "Podfile" in mset
        or "Gemfile" in mset
    )
    has_mobile_source = ".swift" in exts or ".kt" in exts
    if any(m.startswith("app.config.") for m in mset):
        return "Expo / React Native app"
    if "foundry.toml" in mset or ".sol" in exts:
        return "Solidity / EVM smart contracts"
    if "pubspec.yaml" in mset or ".dart" in exts:
        return "Flutter / Dart app"
    # v0.9 Phase 5.2 — Rust crate (workspace member or standalone).
    if "Cargo.toml" in mset or ".rs" in exts:
        return "Rust crate"
    # v0.9 Phase 5.5 — React Native workspace child. Fires on any
    # of the strong mobile-config signals (metro / react-native
    # config, Podfile, Gemfile) regardless of whether package.json
    # or .tsx are also present. Catches packages/react-native and
    # packages/rn-tester from the react-native dogfood failure.
    if has_mobile_config or has_mobile_source:
        return "React Native / mobile framework"
    if any(m.startswith("next.config.") for m in mset):
        return "Next.js / React web app"
    if "package.json" in mset and (".tsx" in exts or ".jsx" in exts):
        return "Next.js / React web app"
    return None


# v0.8 Phase 4.5 — workspace-aware primary detection. When the
# root scan returns "unknown", the inferred primary uses these
# Phase 3 child labels mapped to a slightly tighter primary form
# (drops "app" / "web app" suffixes that read odd as a primary
# stack label). Only three target labels per the spec — Expo and
# the future "package.json + .tsx" Next.js fallback are not
# inferred here to keep false-positive risk low.
_INFERRED_PRIMARY_BY_CHILD_LABEL: dict[str, str] = {
    "Flutter / Dart app":             "Flutter / Dart",
    "Solidity / EVM smart contracts": "Solidity / EVM smart contracts",
    "Next.js / React web app":        "Next.js / React",
    # v0.9 Phase 5.2 — Cargo workspaces without a root Cargo.toml are
    # rare in practice (most Rust workspaces declare members at root),
    # but the inference is correct + cheap when it fires.
    "Rust crate":                     "Rust workspace",
}


def _infer_primary_from_workspace(
    children: list[WorkspaceChild],
) -> Optional[str]:
    """Return an inferred primary-stack label, or ``None``.

    v0.8 Phase 4.5 — fires only when:
      1. There is at least one non-trivial workspace child.
         "Trivial" means ``package.json`` only with no notable
         extensions (typically a shared config package); these
         are excluded from the consistency check.
      2. Every non-trivial child has a Phase 3 stack label
         (``_classify_workspace_child`` returns non-None).
      3. All those labels are identical.
      4. That label is one of the three Phase 4.5 targets
         (Flutter / Solidity / Next.js).

    Mixed children, unknown children, or unsupported labels
    return ``None`` so the renderer falls back to the existing
    "Unknown stack" line. Pure function; no I/O.
    """
    if not children:
        return None
    labels: list[str] = []
    for c in children:
        is_trivial = (
            c.manifest_files == ["package.json"]
            and not c.notable_extensions
        )
        if is_trivial:
            continue
        label = _classify_workspace_child(c)
        if label is None:
            return None
        labels.append(label)
    if not labels:
        return None
    unique = set(labels)
    if len(unique) != 1:
        return None
    return _INFERRED_PRIMARY_BY_CHILD_LABEL.get(unique.pop())


def _workspace_stack_pairs(stack: StackProfile) -> list[tuple[str, str]]:
    """Return ``(child_name, stack_label)`` pairs for children with a label.

    Children that ``_classify_workspace_child`` returns ``None`` for
    are dropped — the workspace-stack summary stays trustworthy by
    only listing children whose stack is unambiguous from the
    Phase 3 signal set.
    """
    out: list[tuple[str, str]] = []
    for c in stack.workspace_children:
        label = _classify_workspace_child(c)
        if label is not None:
            out.append((c.name, label))
    return out


@dataclass
class AgentLaunchPrompt:
    """v0.10.0 Phase 6.1 — copy-paste prompt for an AI coding agent.

    Bundles context-kit's view of the project into one self-
    contained text block the user can paste as the first message
    to Claude / Cursor / etc. The prompt names what the project
    appears to be, the primary detection, the workspace
    structure, a type-specific first action, and the standard
    safety guardrails (don't change stack, don't run destructive
    commands, ask before broad refactors).
    """

    title: str            # always "Agent launch prompt"
    prompt_text: str      # the full copy-paste block
    confidence: str       # "low" | "medium" | "high" (mirrors reality)


@dataclass
class AdoptSummary:
    """Phase 4.4 — single consolidated summary card.

    Bundles the four Phase 3 + 4.x derivations (workspace stack
    pairs, stack reality, project type, suggested actions) into
    one read-once block. The four standalone sections that fed
    each input are removed from the rendered outputs to eliminate
    the visual fragmentation the dogfood revealed.

    Pure data — no I/O, no detection, no failure-taxonomy
    changes. Bundles existing objects rather than recomputing,
    so consistency with the standalone derivations is automatic.
    """

    project_type: "ProjectType"
    reality: "StackReality"
    workspace_pairs: list[tuple[str, str]] = field(default_factory=list)
    actions: list["SuggestedAction"] = field(default_factory=list)


@dataclass
class SuggestedAction:
    """Phase 4.3 suggested next action.

    Pure derivation — built from ``StackReality`` + ``ProjectType``
    + the already-detected ``unclassified_subdirs`` + the
    ``FailureRecord`` list. No new I/O, no AI calls, no extra
    ecosystem detection. The point is to give the human reader
    (and the AI session reading the docs) a short prioritized
    checklist to react to.
    """

    title: str
    reason: str
    priority: str  # "high" | "medium" | "low"


@dataclass
class ProjectType:
    """Phase 4.2 derived project-type label.

    Pure summary built from ``StackProfile`` + ``StackReality`` —
    no detection, no classification logic, no fresh I/O. Designed
    to give the AI session and the human reader a one-line answer
    to "what kind of project is this?" without having to interpret
    primary stack + workspace signals separately.

    Six fixed labels for now (see ``derive_project_type``); rule
    cascade is deterministic and additions require a code change.
    """

    label: str        # short human-readable category
    confidence: str   # "low" | "medium" | "high" (lowercase per spec)
    reason: str       # one-sentence rationale


@dataclass
class StackReality:
    """Phase 4.1 derived assessment of the project's stack shape.

    Pure summary — no detection, no classification logic. Built from
    the existing primary classification, the Phase 3 workspace stack
    summary, and the failure taxonomy. Helps a reader (human or AI
    session) decide *how much to trust* the primary classification
    line before making changes.
    """

    assessment: str  # "Single-stack project" | "Mixed workspace project" | "Unclear project shape"
    confidence: str  # "High" | "Medium" | "Low"
    why: str
    primary: str            # readable primary stack label, recap of _stack_summary
    workspace_signals: list[str] = field(default_factory=list)


def derive_stack_reality(stack: StackProfile,
                         failures: list[FailureRecord]) -> StackReality:
    """Apply Phase 4.1 rules and return a ``StackReality``.

    Rules in priority order:

    1. ``stack.language == 'unknown'`` — *Unclear project shape* / Low.
       Primary detection failed; the reader needs to clarify what's
       there before adopt's other outputs are useful.
    2. Workspace-stack summary non-empty — *Mixed workspace project*
       / Medium. The primary label captures only root tooling; child
       projects carry their own distinct stacks.
    3. ``stack.parts`` non-empty (v0.1 split monorepo with recognized
       subdir names backend/frontend/...) — *Mixed workspace project*
       / Medium. Same shape, different surfacing.
    4. ROOT_SIGNAL_OVERRIDE or MISLEADING_CLASSIFICATION fires —
       *Single-stack project* / Medium with a why that flags the
       framework underselling.
    5. Default — *Single-stack project* / High.

    Pure function. No I/O.
    """
    primary = _stack_summary(stack)
    pairs = _workspace_stack_pairs(stack)
    workspace_signals = sorted({label for _, label in pairs})

    # v0.8 Phase 4.5 — when root detection is unknown but
    # workspace inference produced a primary label, treat it as
    # a real primary classification. The Mixed / Single rules
    # below take over from the Unclear path. Without inference,
    # unknown still falls into Unclear / Low.
    if stack.language == "unknown" and stack.inferred_primary is None:
        signal_subs, data_only_subs = _partition_unclassified(stack)
        clar_count = len(signal_subs) + len(data_only_subs)
        if clar_count >= 1:
            why = (
                f"No project-defining manifest at root; {clar_count} "
                f"candidate director{'y' if clar_count == 1 else 'ies'} "
                f"need{'s' if clar_count == 1 else ''} clarification."
            )
        else:
            why = ("No project-defining manifest at root and no signal "
                   "directories surfaced.")
        return StackReality(
            assessment="Unclear project shape",
            confidence="Low",
            why=why,
            primary=primary,
            workspace_signals=workspace_signals,
        )

    # v0.8 Phase 4.5 — inferred-primary case. By definition
    # workspace children are non-empty and consistent, so there
    # are no DIFFERENT-from-primary stacks below. Treat as
    # Single-stack (workspace-distributed) at Medium confidence.
    if stack.inferred_primary is not None:
        n_children = len(stack.workspace_children)
        return StackReality(
            assessment="Single-stack project",
            confidence="Medium",
            why=(
                f"No root manifest detected; primary stack inferred "
                f"from {n_children} workspace child project"
                f"{'s' if n_children != 1 else ''}, all of which "
                f"share the same stack signal."
            ),
            primary=primary,
            workspace_signals=workspace_signals,
        )

    if pairs:
        n_children = len(pairs)
        sig_str = ", ".join(workspace_signals)
        why = (
            f"Root manifest set the primary label, but {n_children} "
            f"workspace child project{'s' if n_children != 1 else ''} carry "
            f"their own distinct stack label{'s' if len(workspace_signals) != 1 else ''} "
            f"({sig_str}) not yet part of primary classification."
        )
        return StackReality(
            assessment="Mixed workspace project",
            confidence="Medium",
            why=why,
            primary=primary,
            workspace_signals=workspace_signals,
        )

    if stack.parts:
        names = sorted(stack.parts.keys())
        labels = sorted({_lang_label(lang) for lang in stack.parts.values()})
        why = (
            f"Recognized subdirs ({', '.join(names)}) carry distinct "
            f"stacks ({', '.join(labels)})."
        )
        return StackReality(
            assessment="Mixed workspace project",
            confidence="Medium",
            why=why,
            primary=primary,
            workspace_signals=workspace_signals,
        )

    misleading = any(
        f.failure_type in (
            FAILURE_ROOT_SIGNAL_OVERRIDE,
            FAILURE_MISLEADING_CLASSIFICATION,
        )
        for f in failures
    )
    if misleading:
        return StackReality(
            assessment="Single-stack project",
            confidence="Medium",
            why=("Root manifest matches a single stack, but a stronger "
                 "framework signal at root suggests the primary label "
                 "may undersell the actual stack."),
            primary=primary,
            workspace_signals=workspace_signals,
        )
    # v0.9 Phase 5.1 — mixed-root JS+Python at root never claims
    # High confidence regardless of which side won the source-
    # dominance check. Even when the dominance call is clear-cut,
    # mixed-root setups in practice often have hidden glue (build
    # tooling, CI, generated code) that the single-stack frame
    # underserves; Medium is the honest ceiling.
    has_js_root = "package.json" in stack.signals
    has_py_root = any(
        s in stack.signals
        for s in ("manage.py", "requirements.txt", "pyproject.toml")
    )
    if has_js_root and has_py_root:
        return StackReality(
            assessment="Single-stack project",
            confidence="Medium",
            why=("Root has both JavaScript and Python manifests; "
                 "primary chosen by source-file dominance at depth ≤ 2. "
                 "Mixed-root setups rarely behave as a single stack in "
                 "practice — verify the choice before relying on it."),
            primary=primary,
            workspace_signals=workspace_signals,
        )
    return StackReality(
        assessment="Single-stack project",
        confidence="High",
        why=("Root manifest matches a single stack and no workspace "
             "containers were found."),
        primary=primary,
        workspace_signals=workspace_signals,
    )


# v0.9 Phase 5.4 — smart-contract framework configs that imply a
# Solidity primary even when classification picked plain JS.
_SMART_CONTRACT_ROOT_CONFIGS = frozenset({
    "hardhat.config.js", "hardhat.config.ts",
    "hardhat.config.mjs", "hardhat.config.cjs",
    "foundry.toml", "truffle-config.js",
    "brownie-config.yaml",
})

# v0.9 Phase 5.4 — minimum .sol file count in a depth-1 subdir
# before adopt is willing to call the project a Smart contract
# project on Solidity content alone.
_SMART_CONTRACT_MIN_SOL_FILES = 10


def derive_project_type(stack: StackProfile,
                        reality: StackReality,
                        failures: Optional[list[FailureRecord]] = None) -> ProjectType:
    """Apply Phase 4.2 / 5.x deterministic rules; return a ``ProjectType``.

    Rules in priority order (more specific first):

    1. Solidity + Next.js workspace signals -> "Web3 dApp" / medium
    2. Smart contract evidence (workspace Solidity, ``contracts/``
       heavy with .sol, or root has hardhat/foundry/truffle/brownie
       config) and NO Next.js -> "Smart contract project" / medium
    3. Python/Django anywhere + Next.js workspace -> "Full-stack web
       app" / medium
    4. Mobile signals (Flutter or React Native workspace) and no
       web/contract signals -> "Mobile app suite" / medium
    5. Rust signal at root or in workspace -> "Rust workspace /
       library" / medium
    6. Go signal at root -> "Go project" / medium
    7. Single primary JavaScript with no parts and no workspace
       children -> "JavaScript app/tooling project" / medium
    8. Single primary Python with no parts and no workspace
       children -> "Python app/tooling project" / medium
    9. Catch-all -> "Unclear project type" / low

    ``failures`` (optional) lets the smart-contract rule see
    MISLEADING_CLASSIFICATION / UNRECOGNIZED_ECOSYSTEM examples so
    root configs like ``hardhat.config.js`` can promote the type
    even when the file isn't tracked in stack.signals. Pure
    function; reason text adapts per rule.
    """
    failures = failures or []
    failure_examples = {f.example for f in failures}
    signals = set(reality.workspace_signals)
    has_solidity = "Solidity / EVM smart contracts" in signals
    has_nextjs = "Next.js / React web app" in signals
    has_flutter = "Flutter / Dart app" in signals
    has_react_native = "React Native / mobile framework" in signals
    has_rust_child = "Rust crate" in signals

    python_anywhere = (
        stack.language == "python"
        or "python" in stack.parts.values()
        or any("manage.py" in u.manifest_files
               for u in stack.unclassified_subdirs)
        or any(".py" in u.notable_extensions
               for u in stack.unclassified_subdirs)
    )

    # v0.10.x — v0.1 split-monorepo Full-stack signal. The
    # workspace-based has_nextjs check above only fires when a
    # Phase 3 workspace child carries the Next.js label; it
    # misses the classic backend/ + frontend/ split monorepo
    # (example-contract-app, example-web-app, etc.). Recognize that
    # shape via the stack.parts table directly: a Python
    # backend role AND a JavaScript frontend role.
    _BACKEND_ROLES = ("backend", "server", "api")
    _FRONTEND_ROLES = ("frontend", "web", "client")
    py_backend_part = next(
        (r for r in _BACKEND_ROLES if stack.parts.get(r) == "python"),
        None,
    )
    js_frontend_part = next(
        (r for r in _FRONTEND_ROLES if stack.parts.get(r) == "javascript"),
        None,
    )
    has_full_stack_via_parts = bool(py_backend_part and js_frontend_part)

    # Phase 5.4 — smart-contract evidence collection. Three sources:
    # workspace Solidity child, depth-1 dir with many .sol files, or
    # a root smart-contract framework config (visible via failure
    # examples since stack.signals only carries the four classifier-
    # tracked manifests).
    # Sort so the picked config is deterministic when more than
    # one smart-contract framework lives at root (e.g. openzeppelin
    # has both hardhat.config.js AND foundry.toml). Without this,
    # set iteration order leaks into the reason text and the same
    # project would render different copy across runs.
    sc_root_configs = sorted(failure_examples & _SMART_CONTRACT_ROOT_CONFIGS)
    sc_root_config = sc_root_configs[0] if sc_root_configs else None
    heavy_sol_dir = next(
        (u for u in stack.unclassified_subdirs
         if u.notable_extensions.get(".sol", 0)
         >= _SMART_CONTRACT_MIN_SOL_FILES),
        None,
    )
    has_smart_contract = bool(
        has_solidity or sc_root_config or heavy_sol_dir
    )

    # ---- Rule 1: Web3 dApp (Solidity + Next.js) ----
    if has_solidity and has_nextjs:
        return ProjectType(
            label="Web3 dApp",
            confidence="medium",
            reason=("Workspace combines Solidity / EVM smart contracts "
                    "with a Next.js / React web app."),
        )

    # ---- Rule 2: Smart contract project (no Next.js) ----
    if has_smart_contract and not has_nextjs:
        bits: list[str] = []
        if sc_root_config:
            bits.append(f"root has {sc_root_config}")
        if heavy_sol_dir:
            cnt = heavy_sol_dir.notable_extensions[".sol"]
            bits.append(f"{heavy_sol_dir.name}/ contains {cnt} .sol files")
        if has_solidity:
            sol_kids = [
                name for name, lang in _workspace_stack_pairs(stack)
                if lang == "Solidity / EVM smart contracts"
            ]
            if sol_kids:
                bits.append(
                    f"workspace child(ren) {', '.join(sol_kids)} "
                    f"contain Solidity contracts"
                )
        evidence = "; ".join(bits) if bits else "Solidity content detected"
        return ProjectType(
            label="Smart contract project",
            confidence="medium",
            reason=(
                f"{evidence}. Primary is on-chain code; any frontend "
                f"is secondary."
            ),
        )

    # ---- Rule 3: Full-stack web app ----
    # Two paths:
    #   (a) workspace contains a Next.js child AND there's a
    #       Python signal anywhere (turborepo + Django shape).
    #   (b) v0.1 split-monorepo with a Python backend role
    #       (backend/server/api) AND a JavaScript frontend role
    #       (frontend/web/client). Catches example-contract-app /
    #       example-web-app / example-tracker-app / example-pilot-app etc.
    if (python_anywhere and has_nextjs) or has_full_stack_via_parts:
        if has_full_stack_via_parts:
            reason = (
                f"Recognized split monorepo with a Python backend "
                f"({py_backend_part}/) and a JavaScript frontend "
                f"({js_frontend_part}/)."
            )
        else:
            reason = (
                "Python (likely Django) backend plus a Next.js / "
                "React frontend in the workspace."
            )
        return ProjectType(
            label="Full-stack web app",
            confidence="medium",
            reason=reason,
        )

    # ---- Rule 4: Mobile app suite (Flutter or React Native, no web/contract) ----
    if (has_flutter or has_react_native) and not has_solidity and not has_nextjs:
        mobile_kids = [
            name for name, lang in _workspace_stack_pairs(stack)
            if lang in ("Flutter / Dart app",
                        "React Native / mobile framework")
        ]
        if mobile_kids:
            sample = ", ".join(mobile_kids[:3])
            extra = (
                f" Detected {sample}."
                if len(mobile_kids) <= 3
                else f" Detected {sample} (and "
                     f"{len(mobile_kids) - 3} more)."
            )
        else:
            extra = ""
        if has_react_native and not has_flutter:
            kind = "React Native"
        elif has_flutter and not has_react_native:
            kind = "Flutter / Dart"
        else:
            kind = "Flutter and React Native"
        return ProjectType(
            label="Mobile app suite",
            confidence="medium",
            reason=(
                f"Workspace contains {kind} app workspace(s).{extra}"
            ),
        )

    # ---- Rule 5: Rust workspace / library ----
    # Fires only when Rust is the primary identity: either root
    # has Cargo.toml OR root detection is unknown and the
    # workspace has Rust crates. JS / Python primary repos that
    # happen to have auxiliary Rust tooling (e.g. next.js's
    # crates/turbopack-*) fall through to the JS/Python rules
    # below — Rust isn't their identity.
    rust_is_primary = (
        stack.language == "rust"
        or (stack.language == "unknown" and has_rust_child)
    )
    if rust_is_primary and not has_smart_contract:
        rust_kids = [
            name for name, lang in _workspace_stack_pairs(stack)
            if lang == "Rust crate"
        ]
        if rust_kids:
            sample = ", ".join(rust_kids[:3])
            kid_clause = (
                f" Workspace crates: {sample}"
                + (f" (and {len(rust_kids) - 3} more)."
                   if len(rust_kids) > 3 else ".")
            )
        else:
            kid_clause = ""
        return ProjectType(
            label="Rust workspace / library",
            confidence="medium",
            reason=(
                f"Cargo.toml at root or Rust crate(s) in the "
                f"workspace.{kid_clause}"
            ),
        )

    # ---- Rule 6: Go project ----
    if stack.language == "go":
        return ProjectType(
            label="Go project",
            confidence="medium",
            reason=("Root go.mod detected; primary is a Go project "
                    "(library, CLI, or service)."),
        )

    # ---- Rule 7: Single primary JavaScript ----
    if (stack.language == "javascript"
            and not stack.parts
            and not stack.workspace_children):
        return ProjectType(
            label="JavaScript app/tooling project",
            confidence="medium",
            reason=("Single root JavaScript / Node manifest with no "
                    "workspace containers."),
        )

    # ---- Rule 8: Single primary Python ----
    if (stack.language == "python"
            and not stack.parts
            and not stack.workspace_children):
        return ProjectType(
            label="Python app/tooling project",
            confidence="medium",
            reason=("Single root Python manifest with no workspace "
                    "containers."),
        )

    # ---- Catch-all ----
    workspace_str = (", ".join(reality.workspace_signals)
                     if reality.workspace_signals else "none")
    return ProjectType(
        label="Unclear project type",
        confidence="low",
        reason=(
            f"No deterministic rule matched. Primary detection: "
            f"{reality.primary}; workspace signals: {workspace_str}."
        ),
    )


def _project_type_block_dryrun(ptype: ProjectType) -> list[str]:
    """The "Project type" block for the CLI dry-run output."""
    return [
        "",
        "Project type:",
        f"  - Label: {ptype.label}",
        f"  - Confidence: {ptype.confidence}",
        f"  - Reason: {ptype.reason}",
    ]


def _project_type_markdown(ptype: ProjectType) -> list[str]:
    """The "Project type" section for Markdown docs (BUILD_PLAN + CLAUDE)."""
    return [
        "",
        "### Project type",
        "",
        f"- **Label:** {ptype.label}",
        f"- **Confidence:** {ptype.confidence}",
        f"- **Reason:** {ptype.reason}",
    ]


# Constants for the suggested-actions cap (Phase 4.3).
_MAX_SUGGESTED_ACTIONS = 5


def derive_suggested_actions(
    stack: StackProfile,
    reality: StackReality,
    project_type: ProjectType,
    failures: list[FailureRecord],
) -> list[SuggestedAction]:
    """Apply the deterministic rules; return up to 5 actions.

    v0.8 Phase 4.6 — context-aware refinement of the Phase 4.3
    rules. Each action's reason now names the concrete things the
    user should inspect (workspace child paths, needs-clarification
    dir names, etc.) instead of generic prose. The rule cascade,
    dedup-by-title, priority-sort, and 5-cap invariants are
    unchanged from Phase 4.3.

    Pure function. No I/O.
    """
    failure_types = {f.failure_type for f in failures}
    pairs = _workspace_stack_pairs(stack)
    out: list[SuggestedAction] = []

    def children_with_label(label: str) -> list[str]:
        return [name for name, lang in pairs if lang == label]

    # Web3 dApp — name the Solidity vs frontend children.
    if project_type.label == "Web3 dApp":
        sol_children = children_with_label("Solidity / EVM smart contracts")
        web_children = children_with_label("Next.js / React web app")
        bits: list[str] = []
        if sol_children:
            bits.append(
                f"{', '.join(sol_children)} appears to contain "
                f"Solidity contracts"
            )
        if web_children:
            bits.append(
                f"{', '.join(web_children)} appears to contain the "
                f"frontend"
            )
        prefix = "; ".join(bits) + ". " if bits else ""
        out.append(SuggestedAction(
            title="Confirm smart-contract + frontend boundary",
            reason=(
                f"Smart-contract workspace(s) and frontend "
                f"workspace(s) appear separate. {prefix}"
                f"Confirm how contracts are built/deployed and how "
                f"the frontend consumes them."
            ),
            priority="high",
        ))

    # Mobile app suite — name the Flutter children.
    if project_type.label == "Mobile app suite":
        flutter_children = children_with_label("Flutter / Dart app")
        if flutter_children:
            sample = " and ".join(flutter_children[:2])
            extra = (
                f" Detected {sample}."
                if len(flutter_children) <= 2
                else f" Detected {sample} (and "
                     f"{len(flutter_children) - 2} more)."
            )
        else:
            extra = ""
        out.append(SuggestedAction(
            title="Confirm mobile app structure",
            reason=(
                f"Multiple Flutter/Dart app workspaces were detected. "
                f"Confirm which apps are primary, shared, or "
                f"experimental.{extra}"
            ),
            priority="high",
        ))

    # Full-stack web app — refined boundary copy.
    if project_type.label == "Full-stack web app":
        out.append(SuggestedAction(
            title="Confirm backend/frontend boundaries",
            reason=(
                "Backend and frontend code appear to live in separate "
                "workspaces. Confirm API ownership, local dev startup "
                "order, and deployment boundaries."
            ),
            priority="medium",
        ))

    if reality.confidence == "Low":
        out.append(SuggestedAction(
            title="Clarify project shape before coding",
            reason=("Adopt couldn't infer the project shape; clarifying "
                    "upfront avoids misleading downstream output."),
            priority="high",
        ))

    # Needs-clarification dirs — name them, cap at 3 with overflow phrasing.
    signal_subs, data_only_subs = _partition_unclassified(stack)
    clar_dirs = (
        [u.name + "/" for u in signal_subs]
        + [u.name + "/" for u in data_only_subs]
    )
    if clar_dirs:
        if len(clar_dirs) <= 3:
            reason = f"Confirm the role of: {', '.join(clar_dirs)}."
        else:
            first3 = ", ".join(clar_dirs[:3])
            reason = (
                f"Confirm the role of {len(clar_dirs)} unclassified "
                f"directories, starting with: {first3}."
            )
        out.append(SuggestedAction(
            title="Classify unrecognized directories",
            reason=reason,
            priority="medium",
        ))

    # Workspace depth — name child workspaces when known.
    if FAILURE_MONOREPO_DEPTH_LIMIT in failure_types:
        all_children = [name for name, _ in pairs]
        if all_children:
            sample = " and ".join(all_children[:2])
            reason = (
                f"adopt surfaced child workspaces but does not yet "
                f"fold them into primary classification. Review "
                f"workspace children such as {sample}."
            )
        else:
            reason = (
                "adopt surfaced child workspaces but does not yet "
                "fold them into primary classification."
            )
        out.append(SuggestedAction(
            title="Review workspace children",
            reason=reason,
            priority="high",
        ))

    if FAILURE_IDEMPOTENCY_RISK in failure_types:
        out.append(SuggestedAction(
            title="Preserve existing context docs before writing",
            reason=("One or more adopt-managed files already exist "
                    "without our markers. Adopt will skip them to "
                    "protect your hand-written content."),
            priority="high",
        ))

    # Catch-all clean-project action — only when no other rules fired.
    if not out:
        out.append(SuggestedAction(
            title="Run adopt with --write when ready",
            reason=("Detection looks clean and no clarification "
                    "directories surfaced. Re-run with --write to "
                    "apply the plan."),
            priority="low",
        ))

    # Deduplicate by title, preserving first occurrence.
    seen: set[str] = set()
    deduped: list[SuggestedAction] = []
    for a in out:
        if a.title in seen:
            continue
        seen.add(a.title)
        deduped.append(a)

    # Stable sort by priority (high > medium > low); ties keep
    # insertion order so the rule list above is the visual default.
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    deduped.sort(key=lambda a: priority_rank.get(a.priority, 3))

    return deduped[:_MAX_SUGGESTED_ACTIONS]


def _suggested_actions_block_dryrun(
    actions: list[SuggestedAction],
) -> list[str]:
    """The "Suggested next actions" block for the CLI dry-run."""
    if not actions:
        return []
    out = ["", f"Suggested next actions ({len(actions)}):"]
    for a in actions:
        out.append(f"  - [{a.priority}] {a.title}")
        out.append(f"      Reason: {a.reason}")
    return out


def _suggested_actions_markdown(
    actions: list[SuggestedAction],
) -> list[str]:
    """The "Suggested next actions" section for Markdown docs."""
    if not actions:
        return []
    out = ["", f"### Suggested next actions ({len(actions)})", ""]
    for a in actions:
        out.append(f"- **[{a.priority}] {a.title}** — {a.reason}")
    return out


def derive_adopt_summary(
    stack: StackProfile,
    reality: StackReality,
    project_type: ProjectType,
    actions: list[SuggestedAction],
) -> AdoptSummary:
    """Bundle Phase 3 + 4.x derivations into a single ``AdoptSummary``.

    Pure aggregation — re-uses the upstream derivations rather
    than recomputing. Workspace pairs come from the same Phase 3
    helper the standalone Workspace stack section used; actions
    are taken as-is (already deduped + sorted + capped at 5 by
    ``derive_suggested_actions``).
    """
    return AdoptSummary(
        project_type=project_type,
        reality=reality,
        workspace_pairs=_workspace_stack_pairs(stack),
        actions=list(actions),
    )


def _adopt_summary_block_dryrun(summary: AdoptSummary) -> list[str]:
    """The "Adopt Summary" block for the CLI dry-run.

    Single section with four sub-blocks (Type / Structure /
    Reality / Next actions). Compact layout — meant to be the
    one piece of summary text the reader scans before diving
    into details.
    """
    pt = summary.project_type
    r = summary.reality
    out = ["", "Adopt Summary"]
    # Type
    out.append(f"  Type:        {pt.label} ({pt.confidence})")
    # Structure
    if summary.workspace_pairs:
        out.append("  Structure:")
        name_w = max(len(n) for n, _ in summary.workspace_pairs)
        for name, label in summary.workspace_pairs:
            out.append(f"    - {name.ljust(name_w)}  -> {label}")
    else:
        out.append("  Structure:  no workspace child projects detected")
    # Reality
    out.append(
        f"  Reality:     {r.assessment} (confidence: {r.confidence})"
    )
    out.append(f"               Why: {r.why}")
    # Next actions
    if summary.actions:
        out.append(f"  Next actions ({len(summary.actions)}):")
        for a in summary.actions:
            out.append(f"    - [{a.priority}] {a.title}")
    return out


def _adopt_summary_markdown(summary: AdoptSummary) -> list[str]:
    """The "Adopt Summary" section for Markdown docs."""
    pt = summary.project_type
    r = summary.reality
    out = ["", "## Adopt Summary", ""]
    out.append(f"**Type:** {pt.label} ({pt.confidence})")
    out.append("")
    out.append("**Structure:**")
    if summary.workspace_pairs:
        out.append("")
        for name, label in summary.workspace_pairs:
            out.append(f"- `{name}` → {label}")
    else:
        out.append("")
        out.append("- No workspace child projects detected.")
    out.append("")
    out.append(
        f"**Reality:** {r.assessment} (confidence: {r.confidence}). "
        f"_{r.why}_"
    )
    out.append("")
    out.append(f"**Next actions ({len(summary.actions)}):**")
    out.append("")
    for a in summary.actions:
        out.append(f"- **[{a.priority}] {a.title}** — {a.reason}")
    return out


def _agent_first_action_for(project_type: ProjectType,
                            summary: AdoptSummary) -> str:
    """Type-specific recommended-first-action paragraph.

    Names the concrete child workspaces or files the agent
    should look at first. Falls back to a generic "read the
    manifests + entry points" line for project types that don't
    have a tailored rule yet.
    """
    label = project_type.label
    pairs = summary.workspace_pairs

    def kids_with(target_label: str) -> list[str]:
        return [n for n, lang in pairs if lang == target_label]

    if label == "Web3 dApp":
        sol = kids_with("Solidity / EVM smart contracts")
        web = kids_with("Next.js / React web app")
        sol_ref = ", ".join(sol) if sol else "the smart-contract workspace(s)"
        web_ref = ", ".join(web) if web else "the frontend workspace(s)"
        return (
            f"Inspect the contract/frontend boundary first.\n"
            f"- Read {sol_ref} to understand the contract layout, "
            f"build process, and deployment.\n"
            f"- Read {web_ref} to understand how the frontend "
            f"consumes the contracts.\n"
            f"- Confirm how the two communicate (ABIs, hooks, "
            f"environment variables) before changing either side."
        )

    if label == "Smart contract project":
        sol_kids = kids_with("Solidity / EVM smart contracts")
        sol_clause = (
            f"Read the workspace child(ren) "
            f"({', '.join(sol_kids)}) for the contract source."
            if sol_kids
            else "Read the contracts/ directory (or wherever .sol "
                 "files live) for the contract source."
        )
        return (
            f"Inspect the smart-contract layout first.\n"
            f"- {sol_clause}\n"
            f"- Read the deployment / build configuration "
            f"(hardhat.config.*, foundry.toml, truffle-config.js, "
            f"or brownie-config.yaml) to understand how contracts "
            f"are compiled, tested, and deployed.\n"
            f"- Confirm what's deployed where (mainnet / testnet "
            f"addresses, network config) before making changes."
        )

    if label == "Full-stack web app":
        return (
            "Inspect the backend/frontend boundary first.\n"
            "- Read the backend code to understand the API "
            "surface, models, and ownership.\n"
            "- Read the frontend workspace to see how it "
            "consumes the backend.\n"
            "- Confirm the local-dev startup order (which side "
            "starts first, on what ports) and the deployment "
            "boundary."
        )

    if label == "Mobile app suite":
        mobile = kids_with("Flutter / Dart app") + kids_with(
            "React Native / mobile framework")
        if mobile:
            sample = ", ".join(mobile[:3])
            extra = (f" (and {len(mobile) - 3} more)"
                     if len(mobile) > 3 else "")
            kids_clause = (
                f"Read each app workspace ({sample}{extra}) to "
                f"understand which apps are primary, shared, or "
                f"experimental."
            )
        else:
            kids_clause = (
                "Read each mobile app workspace to understand "
                "which apps are primary, shared, or experimental."
            )
        return (
            f"Inspect the app workspaces and shared modules first.\n"
            f"- {kids_clause}\n"
            f"- Read shared / platform-specific modules to see "
            f"what's reused across apps.\n"
            f"- Confirm the build / run setup (Xcode, Android "
            f"Studio, or CLI) before touching anything."
        )

    if label == "Rust workspace / library":
        rust_kids = kids_with("Rust crate")
        if rust_kids:
            sample = ", ".join(rust_kids[:3])
            extra = (f" (and {len(rust_kids) - 3} more)"
                     if len(rust_kids) > 3 else "")
            kids_clause = (
                f"Read each crate ({sample}{extra}) to understand "
                f"the architecture and how they depend on each "
                f"other."
            )
        else:
            kids_clause = (
                "Read each crate to understand the architecture "
                "and how they depend on each other."
            )
        return (
            f"Inspect the crates and entrypoint first.\n"
            f"- Read root Cargo.toml to find the workspace "
            f"members and the project's external dependencies.\n"
            f"- {kids_clause}\n"
            f"- Identify the binary or library entrypoint(s) "
            f"before making changes."
        )

    if label == "Go project":
        return (
            "Inspect go.mod, cmd/, and pkg/ first.\n"
            "- Read go.mod to understand the module path and "
            "external dependencies.\n"
            "- Read cmd/ to find the binary entrypoints (each "
            "subdirectory is typically one binary).\n"
            "- Read pkg/ (or internal/) to understand the "
            "package layout before touching anything."
        )

    if label == "Unclear project type":
        return (
            "Do not write code yet. Infer the project shape "
            "first.\n"
            "- Perform a structured read-through of the "
            "repository (README, main files, routing, "
            "configs) to infer the system on your own.\n"
            "- Read any generated docs and the user's project "
            "description for additional signal.\n"
            "- Only ask the user for clarification after this "
            "inspection, and only for specific gaps that "
            "cannot be determined from the codebase."
        )

    # Generic fallback for JS app/tooling, Python app/tooling,
    # and any project type added later without a tailored rule.
    return (
        "Inspect the project layout before writing code.\n"
        "- Read the project's manifests (package.json / "
        "pyproject.toml / etc.) to understand dependencies and "
        "entry points.\n"
        "- Read the major modules to learn the architecture.\n"
        "- Propose a concrete first task before making changes."
    )


def _format_notes_block(notes: str) -> str:
    """Render user-supplied notes as a single bullet block.

    Single-line notes become ``"- {line}"``. Multi-line notes
    keep their line breaks: the first line gets the ``"- "``
    prefix and subsequent lines are indented two spaces so they
    render as a continuation of the same bullet in markdown
    while still reading naturally in plain text. Used by the
    Agent Launch Prompt and the three doc generators that
    surface notes.

    Returns the empty string when ``notes`` is empty or
    whitespace-only — callers use that to decide whether to
    render the notes section at all.
    """
    text = notes.rstrip()
    if not text.strip():
        return ""
    lines = text.splitlines() or [text]
    if len(lines) == 1:
        return f"- {lines[0]}"
    indented = "\n".join(f"  {line}" for line in lines[1:])
    return f"- {lines[0]}\n{indented}"


def derive_agent_launch_prompt(
    stack: StackProfile,
    reality: StackReality,
    project_type: ProjectType,
    summary: AdoptSummary,
    inputs: Optional[AdoptionInputs] = None,
) -> AgentLaunchPrompt:
    """Build a copy-paste prompt for an AI coding agent.

    v0.10.0 Phase 6.1 — pure derivation. The output is a single
    self-contained text block the user can paste as the first
    message to their AI agent (Claude Code, Cursor, Aider, etc.)
    after running ``context-kit adopt``.

    ``inputs`` (optional) carries the two answers the user
    provided during adopt — either via the interactive prompts
    or the ``--project-summary`` / ``--next-task`` flags. When
    provided, a USER CONTEXT block surfaces them verbatim so the
    agent sees both adopt's derived view and the human's framing
    in one place. Defaults to a placeholder so existing test
    callers that don't thread inputs still work.

    Confidence mirrors ``reality.confidence`` (lowercased) — if
    adopt isn't sure about the project shape, the prompt isn't
    sure either.
    """
    if summary.workspace_pairs:
        struct_lines = "\n".join(
            f"- {name} → {label}"
            for name, label in summary.workspace_pairs
        )
    else:
        struct_lines = "- No workspace child projects detected."

    first_action = _agent_first_action_for(project_type, summary)

    # USER CONTEXT — the human's two answers verbatim. Empty
    # answers fall back to the canonical placeholder so the
    # agent sees the marker (and the soft framing applies).
    placeholder = "[adopt: please describe]"
    user_desc_for_prompt = (
        inputs.project_description.strip() if inputs else ""
    ) or placeholder
    user_next_for_prompt = (
        inputs.next_step.strip() if inputs else ""
    ) or placeholder

    # DISCOVERED NOTES / CONTEXT — opt-in (--notes flag).
    # Surfaces verbatim findings the user gathered during a
    # prior dry-run / probe pass so the agent doesn't lose them
    # when the user later runs --write. Section is omitted
    # entirely when notes are empty.
    notes_text = inputs.notes if inputs else ""
    notes_block = _format_notes_block(notes_text)
    notes_section = (
        "DISCOVERED NOTES / CONTEXT\n"
        "The user provided these notes from prior inspection "
        "or context:\n"
        f"{notes_block}\n"
        "\n"
    ) if notes_block else ""

    prompt_text = (
        "You are working in a project that context-kit just "
        "adopted. Before writing any code, do the following.\n"
        "\n"
        "WHAT THIS PROJECT APPEARS TO BE\n"
        f"{project_type.label} ({project_type.confidence} "
        f"confidence)\n"
        f"Reasoning: {project_type.reason}\n"
        "\n"
        "USER CONTEXT (provided during adopt)\n"
        f"- Project (per the user): {user_desc_for_prompt}\n"
        f"- Next task (per the user): {user_next_for_prompt}\n"
        "\n"
        f"{notes_section}"
        "PRIMARY DETECTION\n"
        f"{reality.primary}\n"
        "\n"
        "WORKSPACE / PROJECT STRUCTURE\n"
        f"{struct_lines}\n"
        "\n"
        "RECOMMENDED FIRST ACTION\n"
        f"{first_action}\n"
        "\n"
        "HOW TO APPROACH THIS REPO\n"
        "If the project structure is not immediately clear, or the "
        "confidence shown above is low, do a structured read-through "
        "before proposing tasks: start with entry points (README, "
        "main files, routing, configs), map the system (API, "
        "frontend, integrations, data flow), and call out "
        "inconsistencies, risks, or missing pieces you find.\n"
        "\n"
        "If confidence is medium, do a quick inspection first — read "
        "the README, the top-level structure, and one or two main "
        "files — then decide whether the project needs deeper "
        "analysis or whether you can move directly to a concrete "
        "first task.\n"
        "\n"
        "If the structure IS clear and confidence is high, skip the "
        "read-through and go directly to identifying the "
        "highest-value next task — don't pad the response with "
        "unnecessary inspection steps.\n"
        "\n"
        "WHAT TO PRIORITIZE\n"
        "Prefer identifying real risks, inconsistencies, missing "
        "wiring, or unused / incomplete features over surface-level "
        "tasks. Do not default to documentation updates unless the "
        "user explicitly asked for them.\n"
        "\n"
        "SAFETY INSTRUCTIONS\n"
        "- If generated docs exist, read BUILD_PLAN.md, "
        "PROJECT_WHAT_IT_IS.md, and CLAUDE.md before making "
        "changes. If they do not exist yet, read README, "
        "package/manifests, and inspect the detected project "
        "structure first.\n"
        "- Do not change the project's stack (e.g. swapping "
        "frameworks, languages, or build tools) without asking "
        "the user first.\n"
        "- Do not run destructive commands (rm -rf, force-push, "
        "drop database, schema deletes, etc.).\n"
        "- Ask before broad refactors that touch more than 3-5 "
        "files.\n"
        "- If the generated docs are missing, do not treat that "
        "as an error; continue with repo inspection and propose "
        "the first safe task.\n"
        "\n"
        "TO PRESERVE THIS CONTEXT\n"
        "After your initial inspection, end your response with a "
        "short copy-paste command the user can run to persist "
        "this context:\n"
        "\n"
        "  context-kit adopt . --write \\\n"
        "    --project-summary \"<refined one-sentence project "
        "summary>\" \\\n"
        "    --next-task \"<recommended next task>\" \\\n"
        "    --notes \"<key findings from this inspection>\"\n"
        "\n"
        "When filling in the placeholders:\n"
        "- Keep notes concise but specific. Include real risks, "
        "missing wiring, stale docs, dirty git state, or "
        "incomplete features.\n"
        "- Do not include secrets, tokens, or credentials in "
        "any value.\n"
        "- Escape quotes (\\\") inside values, or rephrase to "
        "avoid quotes.\n"
        "- If no meaningful findings exist, omit --notes.\n"
        "- Do not run the command yourself — emit it for the "
        "user to copy.\n"
        "\n"
        "When you're ready to begin work, summarize what you "
        "read and propose a concrete first task."
    )

    return AgentLaunchPrompt(
        title="Agent launch prompt",
        prompt_text=prompt_text,
        confidence=reality.confidence.lower(),
    )


def _agent_launch_prompt_block_dryrun(
    prompt: AgentLaunchPrompt,
) -> list[str]:
    """The "Agent launch prompt" block for the CLI dry-run.

    Surrounds the copy-paste body with delimiter lines so a
    human (or a downstream tool) can extract the prompt cleanly
    from the dry-run output.
    """
    out = [
        "",
        f"=== AGENT LAUNCH PROMPT ({prompt.confidence} confidence) ===",
        "Copy-paste the block below into your AI coding agent "
        "as the first message:",
        "",
    ]
    out.extend(prompt.prompt_text.splitlines())
    out.append("")
    out.append("=== END AGENT LAUNCH PROMPT ===")
    return out


def _agent_launch_prompt_markdown(
    prompt: AgentLaunchPrompt,
) -> list[str]:
    """The "Agent launch prompt" section for Markdown docs.

    Wraps the prompt in a ``text`` code fence so it survives
    Markdown rendering and copies cleanly out of any viewer.
    """
    return [
        "",
        "## Agent launch prompt",
        "",
        f"Copy-paste this into your AI coding agent (Claude Code, "
        f"Cursor, Aider, etc.) as the first message. Confidence: "
        f"{prompt.confidence}.",
        "",
        "```text",
        prompt.prompt_text,
        "```",
    ]


def _stack_reality_block_dryrun(reality: StackReality) -> list[str]:
    """The "Stack reality" derived-summary block for the CLI dry-run.

    Always emitted (every project has a reality assessment). Compact
    indented bullet list under a header, mirrors the user's spec
    output format.
    """
    out = ["", "Stack reality:"]
    out.append(f"  - Primary detection: {reality.primary}")
    if reality.workspace_signals:
        out.append(
            f"  - Workspace signals: "
            f"{', '.join(reality.workspace_signals)}"
        )
    out.append(f"  - Assessment: {reality.assessment}")
    out.append(f"  - Confidence: {reality.confidence}")
    out.append(f"  - Why: {reality.why}")
    return out


def _stack_reality_markdown(reality: StackReality) -> list[str]:
    """The "Stack reality" section for Markdown docs (BUILD_PLAN + CLAUDE).

    Always emitted. Bold-bullet format mirrors ``_workspace_stack_markdown``.
    """
    out = ["", "### Stack reality", ""]
    out.append(f"- **Primary detection:** {reality.primary}")
    if reality.workspace_signals:
        out.append(
            f"- **Workspace signals:** "
            f"{', '.join(reality.workspace_signals)}"
        )
    out.append(f"- **Assessment:** {reality.assessment}")
    out.append(f"- **Confidence:** {reality.confidence}")
    out.append(f"- **Why:** {reality.why}")
    return out


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _lang_label(lang: str) -> str:
    if lang == "javascript":
        return "JavaScript / Node.js"
    if lang == "python":
        return "Python"
    if lang == "rust":
        return "Rust"
    if lang == "go":
        return "Go"
    return "Unknown"


def _stack_summary(stack: StackProfile) -> str:
    """Single-line summary used in dry-run output and the CLAUDE.md block.

    For split monorepos this returns a one-line "Split: backend=Python,
    frontend=JavaScript" form so the CLI dry-run report stays compact;
    the Markdown generators use ``_stack_table`` instead for the
    longer rendering inside docs.
    """
    if stack.parts:
        items = ", ".join(
            f"{sub}={_lang_label(lang)}" for sub, lang in stack.parts.items()
        )
        return f"Split monorepo — {items}"
    if stack.language == "javascript":
        return "JavaScript / Node.js (detected from package.json)"
    if stack.language == "python":
        sig = next(
            (s for s in stack.signals if s in ("manage.py", "requirements.txt", "pyproject.toml")),
            "manifest",
        )
        return f"Python (detected from {sig})"
    if stack.language == "rust":
        return "Rust (detected from Cargo.toml)"
    if stack.language == "go":
        return "Go (detected from go.mod)"
    # v0.8 Phase 4.5: when root detection returned "unknown" but
    # workspace inference produced a label, surface it instead of
    # the bare "Unknown stack" line. The "(inferred from workspace
    # children)" suffix is load-bearing — it tells the reader the
    # primary label came from a different evidence source than
    # the JS / Python lines above.
    if stack.inferred_primary is not None:
        return f"{stack.inferred_primary} (inferred from workspace children)"
    return "Unknown stack — no manifest detected"


def _format_unclassified_for_dryrun(u: UnclassifiedSubdir) -> list[str]:
    """One subdir's lines for the CLI dry-run "Unknown but present" block.

    Format mirrors the §19 worked examples — one heading line per
    subdir followed by indented manifest / source / note lines.
    Returns a list of strings; caller joins with newlines.
    """
    head = f"  {u.name}/"
    indent = " " * (len(head) + 2)
    lines: list[str] = []
    if u.is_empty:
        lines.append(f"{head}  empty")
        return lines
    if u.manifest_files:
        lines.append(f"{head}  manifests: {', '.join(u.manifest_files)}")
        head = " " * len(head)
    # Sort extensions: domain first (interesting), then generic, both
    # ordered by descending count for readability.
    domain = sorted([e for e in u.notable_extensions if e in DOMAIN_HINTS],
                    key=lambda e: (-u.notable_extensions[e], e))
    generic = sorted([e for e in u.notable_extensions if e in GENERIC_EXTENSIONS],
                     key=lambda e: (-u.notable_extensions[e], e))
    src_parts: list[str] = []
    for ext in domain + generic:
        count = u.notable_extensions[ext]
        example = u.example_paths.get(ext)
        ex_clause = f" (e.g. {example})" if example else ""
        src_parts.append(f"{count} {ext} files{ex_clause}")
    if src_parts:
        lines.append(f"{head}  source:    {src_parts[0]}")
        for extra in src_parts[1:]:
            lines.append(f"{indent}{extra}")
        head = " " * len(head)
    elif u.total_file_count > 0 and not u.manifest_files:
        # Has files but none of recognized type — common for dirs full
        # of .json/.md/.yml. Avoids the misleading "EMPTY" label.
        lines.append(
            f"{head}  source:    {u.total_file_count} files "
            f"(no recognized source extensions)"
        )
        head = " " * len(head)
    if u.note:
        lines.append(f"{head}  note:      {u.note}")
        head = " " * len(head)
    if u.manifest_hint:
        lines.append(f"{head}  hint:      {u.manifest_hint}")
    return lines


def _is_data_only_subdir(u: UnclassifiedSubdir) -> bool:
    """True iff ``u`` has only the 'no recognized source extensions' signal.

    Lesson from the example-monorepo dogfood: large repos generated
    24 cards reading "N files (no recognized source extensions)" — all
    visually identical, all crowding out the cards with real signal.
    The renderers group these into a single collapsible "Data /
    content / non-code directories" section so the high-signal cards
    breathe.
    """
    return (
        not u.manifest_files
        and not u.notable_extensions
        and not u.is_empty
        and u.total_file_count > 0
        and u.note is None
        and u.manifest_hint is None
    )


def _workspace_covered_containers(stack: StackProfile) -> set[str]:
    """Container names already represented by entries in workspace_children.

    v0.8 dedup helper. When ``apps/forge`` and ``apps/next`` appear in
    ``workspace_children``, the depth-1 view of ``apps/`` in
    ``unclassified_subdirs`` becomes a redundant — and often
    misleading — second-rendering of the same data (the per-container
    counts cap at ``MAX_FILES_PER_SUBDIR`` and don't agree with the
    per-child counts). Renderers use this set to suppress the
    container row from "Unknown but present" so each workspace shape
    is described exactly once.
    """
    covered: set[str] = set()
    for c in stack.workspace_children:
        head, sep, _ = c.name.partition("/")
        if sep:
            covered.add(head)
    return covered


def _partition_unclassified(stack: StackProfile) -> tuple[list[UnclassifiedSubdir], list[UnclassifiedSubdir]]:
    """Return (signal_subdirs, data_only_subdirs) preserving order.

    Subdirs whose names appear as workspace-container heads in
    ``stack.workspace_children`` are filtered out — the per-child
    rendering supersedes the container row. See
    ``_workspace_covered_containers``.
    """
    covered = _workspace_covered_containers(stack)
    signal: list[UnclassifiedSubdir] = []
    data_only: list[UnclassifiedSubdir] = []
    for u in stack.unclassified_subdirs:
        if u.name in covered:
            continue
        (data_only if _is_data_only_subdir(u) else signal).append(u)
    return signal, data_only


def _unknown_present_block_dryrun(stack: StackProfile) -> list[str]:
    """The "Unknown but present" section for the CLI dry-run output.

    Splits into "signal" subdirs (with manifests / notable extensions /
    empties / hints) and "data-only" subdirs (just a file count) so the
    high-signal output isn't visually swamped on large repos.

    Returns an empty list when there's nothing to surface so callers
    don't have to gate on it.
    """
    if not stack.unclassified_subdirs:
        return []
    signal, data_only = _partition_unclassified(stack)
    if not signal and not data_only:
        # All depth-1 candidates were workspace containers already
        # surfaced via workspace_children (v0.8 dedup) — nothing
        # left for this section to say.
        return []
    out = ["", "Needs clarification (depth 1):"]
    for u in signal:
        out.extend(_format_unclassified_for_dryrun(u))
    if data_only:
        # Compact one-line summary so the CLI doesn't repeat the
        # "N files (no recognized source extensions)" pattern N times.
        names = ", ".join(f"{u.name}/ ({u.total_file_count})" for u in data_only)
        out.append("")
        out.append(
            f"  Data / content / non-code dirs ({len(data_only)}): {names}"
        )
    return out


def _workspace_stack_block_dryrun(stack: StackProfile) -> list[str]:
    """The "Workspace stack" derived-summary block for the CLI dry-run.

    v0.8 Phase 3 — surfaces ``_workspace_stack_pairs`` as a compact
    aligned list right after the "Detected stack:" line so the AI
    session sees per-child stack labels at the top, before scanning
    the full Workspace children section. Silent when no labelled
    children exist.
    """
    pairs = _workspace_stack_pairs(stack)
    if not pairs:
        return []
    out = ["", "Workspace stack:"]
    name_width = max(len(n) for n, _ in pairs)
    for name, label in pairs:
        out.append(f"  {name.ljust(name_width)}  -> {label}")
    return out


def _workspace_stack_markdown(stack: StackProfile) -> list[str]:
    """The "Workspace stack" derived-summary section for Markdown docs.

    Used by both BUILD_PLAN.md and the CLAUDE managed block. Short,
    bullet-per-child format. Silent when no labelled children exist.
    """
    pairs = _workspace_stack_pairs(stack)
    if not pairs:
        return []
    out = [
        "",
        "### Workspace stack",
        "",
        "Derived stack labels for the depth-2 child projects. The",
        "primary classification line above is unchanged — this is a",
        "read-only summary based on each child's manifest / extension",
        "signals.",
        "",
    ]
    for name, label in pairs:
        out.append(f"- **{name}** → {label}")
    return out


def _workspace_children_block_dryrun(stack: StackProfile) -> list[str]:
    """The "Workspace children" section for the CLI dry-run output.

    v0.8 — additive surface for ``StackProfile.workspace_children``.
    One line per child: name padded to a common column, then a
    parenthesized compact summary of the child's manifest filenames
    and (if any) the leading clause of its hint. Empty list when no
    workspace children, so callers can ``for line in ...`` without
    an outer guard.

    Header carries the count so the section is scannable at a glance
    (matches the "Diagnostic signals (N):" pattern).
    """
    if not stack.workspace_children:
        return []
    out = ["", f"Workspace children ({len(stack.workspace_children)}):"]
    name_width = max(len(c.name) for c in stack.workspace_children)
    for c in stack.workspace_children:
        bits: list[str] = []
        if c.manifest_files:
            bits.append(", ".join(c.manifest_files))
        if c.hint:
            # First clause before "; verify with user" — same compact
            # treatment used for hint-badge in the HTML summary.
            bits.append(c.hint.split(";")[0].strip())
        suffix = f"  ({', '.join(bits)})" if bits else ""
        out.append(f"  {c.name.ljust(name_width)}{suffix}")
    return out


def _format_unclassified_for_markdown(u: UnclassifiedSubdir) -> str:
    """One subdir's bullet for the Markdown 'Unknown but present' lists.

    Used by both BUILD_PLAN.md and the CLAUDE.md augment block. Returns
    a single multiline string; caller wraps in a markdown list context.
    """
    if u.is_empty:
        return f"- **{u.name}/** — empty (no files in scanned tree)."
    parts: list[str] = []
    if u.manifest_files:
        man_str = ", ".join(f"`{m}`" for m in u.manifest_files)
        parts.append(f"contains {man_str}")
    domain = sorted([e for e in u.notable_extensions if e in DOMAIN_HINTS],
                    key=lambda e: (-u.notable_extensions[e], e))
    generic = sorted([e for e in u.notable_extensions if e in GENERIC_EXTENSIONS],
                     key=lambda e: (-u.notable_extensions[e], e))
    for ext in domain + generic:
        count = u.notable_extensions[ext]
        example = u.example_paths.get(ext)
        ex_clause = f" (example: `{example}`)" if example else ""
        parts.append(f"{count} `{ext}` files{ex_clause}")
    if not parts and u.total_file_count > 0:
        parts.append(
            f"{u.total_file_count} files (no recognized source extensions — "
            f"may be config / data / docs)"
        )
    body = "; ".join(parts) if parts else "no recognized files"
    line = f"- **{u.name}/** — {body}."
    if u.note:
        line += f" {u.note}."
    if u.manifest_hint:
        line += f" *{u.manifest_hint}.*"
    return line


def _unknown_present_markdown(stack: StackProfile) -> list[str]:
    """The full "Unknown but present" section for the Markdown docs.

    Splits into "signal" subdirs and a compact "data / content /
    non-code" footer so long lists of low-signal entries don't bury
    the high-signal ones in BUILD_PLAN.md / CLAUDE.md.

    Returns an empty list when there's nothing to surface so the
    section is silently omitted on clean projects.
    """
    if not stack.unclassified_subdirs:
        return []
    signal, data_only = _partition_unclassified(stack)
    if not signal and not data_only:
        # v0.8 dedup: all candidates were workspace containers
        # already surfaced via workspace_children. Section omitted.
        return []
    out = [
        "",
        "### Needs clarification",
        "",
        "These directories contain files adopt can see, but it cannot",
        "confidently identify their role yet. Confirm what they are",
        "before making changes.",
        "",
    ]
    for u in signal:
        out.append(_format_unclassified_for_markdown(u))
    if data_only:
        names = ", ".join(f"`{u.name}/`" for u in data_only)
        out += [
            "",
            f"**Data / content / non-code directories ({len(data_only)}):** "
            f"{names}",
            "",
            "_These contain files but none with extensions adopt categorizes "
            "as source (likely config / data / documentation). Listed compactly "
            "so the high-signal directories above stay visible._",
        ]
    return out


def _workspace_children_markdown(stack: StackProfile) -> list[str]:
    """The "Workspace children" section for BUILD_PLAN.md.

    v0.8 — short by design: names + hints only. Manifest details and
    extension counts live in the HTML report and CLI dry-run; this
    section is meant to be skimmable, not exhaustive. Returns an
    empty list when there are no workspace children so the section
    is omitted on classified-only / non-monorepo projects.
    """
    if not stack.workspace_children:
        return []
    n = len(stack.workspace_children)
    out = [
        "",
        f"### Workspace children ({n})",
        "",
        "`adopt` walked one level deeper (depth-2) inside known",
        "workspace containers (`apps/`, `packages/`, ...) and surfaced",
        "these child projects. Names + hints only — see the CLI",
        "dry-run or the `--html` report for full per-child detail.",
        "",
    ]
    for c in stack.workspace_children:
        if c.hint:
            out.append(f"- **{c.name}** — *{c.hint}*")
        else:
            out.append(f"- **{c.name}**")
    return out


def _stack_table(stack: StackProfile) -> list[str]:
    """Multi-line markdown rendering of the stack for BUILD_PLAN / CLAUDE.

    Returns a list of lines (no trailing newline). For split monorepos
    this is a bullet list per subdir; for single-stack repos this is
    the same one-line string ``_stack_summary`` returns.
    """
    if not stack.parts:
        return [_stack_summary(stack)]
    lines: list[str] = []
    for sub, lang in stack.parts.items():
        sig = stack.part_signals.get(sub)
        from_clause = f" (detected from `{sub}/{sig}`)" if sig else ""
        lines.append(f"- **{sub.capitalize()}:** {_lang_label(lang)}{from_clause}")
    return lines


def _wrap_in_managed_block(content: str) -> str:
    """Wrap generated content in adopt's managed-block markers.

    Re-runs of ``adopt --write`` replace everything between the start
    and end markers and preserve everything outside. This is what
    makes BUILD_PLAN.md / PROJECT_WHAT_IT_IS.md / 00-START-NEXT-SESSION.md
    safe to re-generate without destroying user edits — exactly the
    safety gap the example-monorepo dogfood exposed (the existing
    00-START doc would have been clobbered).

    The brief explainer at the top is part of the managed content
    (refreshed on every re-run) so it stays accurate to whatever the
    current adopt version says.
    """
    explainer = (
        "<!-- This block is managed by `context-kit adopt`. "
        "Edits between the markers are overwritten on re-run. "
        "Edits outside the markers are preserved. -->"
    )
    return (
        f"{START_MARKER}\n{explainer}\n\n{content.rstrip()}\n\n{END_MARKER}\n"
    )


def generate_build_plan(stack: StackProfile, inputs: AdoptionInputs, title: str,
                        *, reality: Optional[StackReality] = None,
                        project_type: Optional[ProjectType] = None,
                        actions: Optional[list[SuggestedAction]] = None,
                        summary: Optional[AdoptSummary] = None,
                        agent_prompt: Optional[AgentLaunchPrompt] = None) -> str:
    """The minimum BUILD_PLAN.md a freshly-adopted project needs.

    The strengthened first prompt (Step 8 of the wizard) tells agents
    to read this file before writing code, so it has to carry real
    signal even in v0.

    ``reality`` is the v0.8 Phase 4.1 derived assessment. When
    provided, a "Stack reality" section is rendered below the
    workspace stack summary. Callers that don't compute reality
    (older tests, ad-hoc rendering) can omit it and the section
    is silently skipped.
    """
    body = [
        f"# {title} — Build Plan",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "> Review the [adopt: please describe] sections before relying on this.",
        "",
        "## What this project is",
        "",
        inputs.project_description.strip() or "[adopt: please describe]",
        "",
    ]
    # v0.10.x — Discovered notes (opt-in via --notes). Sits
    # between "What this project is" and "Tech stack" so a
    # reader meets the user's own framing before the
    # auto-detected scaffolding. Section is omitted when
    # notes are empty.
    notes_block = _format_notes_block(inputs.notes)
    if notes_block:
        body += [
            "## Discovered notes",
            "",
            "The user provided these notes from prior inspection "
            "or context:",
            "",
            notes_block,
            "",
        ]
    body += [
        "## Tech stack",
        "",
    ]
    body += _stack_table(stack)
    if stack.signals:
        body.append("")
        body.append("Manifest files seen: " + ", ".join(f"`{s}`" for s in stack.signals))
    if stack.notes:
        body.append("")
        for note in stack.notes:
            body.append(f"> Note: {note}")
    # v0.8 Phase 4.4: single consolidated Adopt Summary card sits
    # above everything except the primary "Tech stack" line. The
    # standalone Phase 3 / 4.1 / 4.2 / 4.3 sections (Workspace
    # stack, Stack reality, Project type, Suggested next actions)
    # are NOT rendered separately anymore — the summary carries
    # all four in one read-once block. Phase 4.4 helper functions
    # remain in the module so direct callers (and a future debug
    # mode) can still build them, but the persisted-doc renderer
    # only emits the summary.
    if summary is not None:
        body += _adopt_summary_markdown(summary)
    # v0.10.0 Phase 6.1: Agent launch prompt sits directly under
    # the Adopt Summary so the user can grab it without scrolling.
    if agent_prompt is not None:
        body += _agent_launch_prompt_markdown(agent_prompt)
    # v0.2: visibility-first. Only added when there's something
    # unclassified to surface — clean classified projects still get
    # the same compact tech-stack section as v0.1.
    body += _unknown_present_markdown(stack)
    # v0.8: depth-2 workspace children (apps/<child>, packages/<child>,
    # ...). Short by design — names + hints only. Silent when none.
    body += _workspace_children_markdown(stack)
    body += [
        "",
        "## Next milestone",
        "",
        inputs.next_step.strip() or "[adopt: please describe]",
        "",
        "## What NOT to change without asking",
        "",
        "- The detected stack above. If the AI proposes switching frameworks,",
        "  ask first.",
        "- Any code outside this `docs/` tree. `adopt` is read-only against",
        "  source.",
        "",
    ]
    # v0.2.x: idempotency. Wrap in adopt-managed markers so re-runs of
    # ``--write`` refresh content inside the markers and preserve any
    # user prose added outside them.
    return _wrap_in_managed_block("\n".join(body))


def generate_what_it_is(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    body = [
        f"# {title} — What It Is",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "> The narrative anchor for this project. Refine the description below",
        "> as the project's mental model sharpens.",
        "",
        "## In one paragraph",
        "",
        inputs.project_description.strip() or "[adopt: please describe]",
        "",
        "## Stack",
        "",
    ]
    body += _stack_table(stack)
    body += [
        "",
        "## Why it exists",
        "",
        "[adopt: please describe — adopt cannot infer the original motivation.]",
        "",
        "## Who it's for",
        "",
        "[adopt: please describe — adopt cannot infer the audience.]",
        "",
    ]
    return _wrap_in_managed_block("\n".join(body))


def generate_start_here(inputs: AdoptionInputs, title: str,
                        *,
                        agent_prompt: Optional[AgentLaunchPrompt] = None) -> str:
    # Frontmatter MUST stay at the top of the file outside the
    # managed-block markers — cli/server.py::_detect_project_state
    # reads ``text.startswith("---\\n")`` to recognize the wizard's
    # project state. Wrap only the body in markers.
    frontmatter = (
        "---\n"
        "state: scaffold\n"
        f"date: {_today()}\n"
        "---\n"
    )
    body: list[str] = [
        f"# Next session — {title}",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "",
    ]
    # v0.10.x — Agent Launch Prompt as the canonical session
    # opener. Sits ABOVE "What's next" so it's the first
    # actionable thing a user sees in the file. The same prompt
    # also lives in CLAUDE.md's managed block; this copy is for
    # convenience (one-keystroke copy from the start-here doc).
    if agent_prompt is not None:
        body += [
            "## Agent Launch Prompt",
            "",
            "Paste this into Claude Code, Cursor, or any AI coding "
            "agent to start safely.",
            "",
            "```text",
            agent_prompt.prompt_text,
            "```",
            "",
        ]
    body += [
        "## What's next",
        "",
        inputs.next_step.strip() or "[adopt: please describe]",
        "",
    ]
    # v0.10.x — Discovered notes (opt-in via --notes). Sits
    # between "What's next" and "How to start the session" so
    # the agent reads the user's own findings before following
    # the start-here checklist.
    notes_block = _format_notes_block(inputs.notes)
    if notes_block:
        body += [
            "## Discovered notes",
            "",
            "The user provided these notes from prior inspection "
            "or context:",
            "",
            notes_block,
            "",
        ]
    body += [
        "## How to start the session",
        "",
        "1. Read `docs/BUILD_PLAN.md` — confirm the stack matches reality.",
        "2. Read `docs/PROJECT_WHAT_IT_IS.md` (or your project's *_WHAT_IT_IS.md).",
        "3. Note any `[adopt: please describe]` placeholders — these mark "
        "context the user hasn't filled in yet. **Do not block on them for "
        "read-only inspection.** Proceed with the recommended first action "
        "from CLAUDE.md if it's safe and read-only. Only ask the user "
        "before making decisions that depend on the missing context.",
        "4. Then begin the work above.",
        "",
    ]
    return frontmatter + "\n" + _wrap_in_managed_block("\n".join(body))


def generate_claude_block(stack: StackProfile, inputs: AdoptionInputs, title: str,
                          *, reality: Optional[StackReality] = None,
                          project_type: Optional[ProjectType] = None,
                          actions: Optional[list[SuggestedAction]] = None,
                          summary: Optional[AdoptSummary] = None,
                          agent_prompt: Optional[AgentLaunchPrompt] = None) -> str:
    """The managed block we append (or insert) into CLAUDE.md.

    Wrapped in markers so re-running ``adopt`` updates these facts in
    place without disturbing surrounding human-written content.

    ``reality`` is the v0.8 Phase 4.1 stack reality assessment. When
    provided, a "Stack reality" H3 is added inside the managed
    block alongside the workspace stack summary so the AI session
    sees the same self-contained assessment that BUILD_PLAN carries.
    """
    lines = [
        START_MARKER,
        "",
        "## Project facts (auto-detected)",
        "",
        f"_Generated by `context-kit adopt` on {_today()}. Re-runs update this block in place._",
        "",
        f"- **Project:** {title}",
    ]
    if stack.parts:
        # Split monorepo: render the per-subdir table inline so the
        # AI session sees each component's stack as a discrete fact.
        lines.append("- **Stack:**")
        for line in _stack_table(stack):
            lines.append(f"  {line}")
    else:
        lines.append(f"- **Stack:** {_stack_summary(stack)}")
    if stack.signals:
        lines.append(f"- **Manifests seen:** {', '.join(f'`{s}`' for s in stack.signals)}")
    # v0.2: visibility-first surfaces unclassified subdirs in CLAUDE.md
    # too, so an AI session reading the entry-point doc can't miss
    # them. Same content as BUILD_PLAN's "Unknown but present" but
    # rendered as bullets under a new H3 inside the managed block.
    # v0.8 Phase 4.4: single Adopt Summary section replaces the
    # standalone Phase 3 / 4.1 / 4.2 / 4.3 sections (Workspace
    # stack, Stack reality, Project type, Suggested next actions)
    # inside the managed block. Same content, one card.
    if summary is not None:
        lines += _adopt_summary_markdown(summary)
    # v0.10.0 Phase 6.1: Agent launch prompt also lands inside the
    # CLAUDE managed block so re-runs refresh it in place.
    if agent_prompt is not None:
        lines += _agent_launch_prompt_markdown(agent_prompt)
    if stack.unclassified_subdirs:
        lines += _unknown_present_markdown(stack)
    # v0.8: workspace children get a compact mention in the CLAUDE
    # managed block too — the AI session reading the entry point
    # should know about depth-2 child projects without having to
    # cross-read BUILD_PLAN.md. Tighter format than BUILD_PLAN's
    # version since CLAUDE blocks are scanned, not skimmed.
    if stack.workspace_children:
        n = len(stack.workspace_children)
        lines += ["", f"### Workspace children ({n})", ""]
        for c in stack.workspace_children:
            if c.hint:
                lines.append(f"- **{c.name}** — *{c.hint}*")
            else:
                lines.append(f"- **{c.name}**")
    lines += [
        "",
        "### What the user told adopt",
        "",
        f"- **What this project is:** {inputs.project_description.strip() or '[adopt: please describe]'}",
        f"- **What's next:** {inputs.next_step.strip() or '[adopt: please describe]'}",
        "",
    ]
    # v0.10.x — Discovered notes (opt-in via --notes). Inside
    # the managed block so re-running adopt --write refreshes
    # them in place (the trust-preservation goal: a refined
    # --project-summary doesn't blow away findings from the
    # earlier dry-run pass).
    notes_block = _format_notes_block(inputs.notes)
    if notes_block:
        lines += [
            "### Discovered notes",
            "",
            "The user provided these notes from prior inspection "
            "or context:",
            "",
            notes_block,
            "",
        ]
    lines += [
        "### Rule for this session",
        "",
        "- Always read `docs/BUILD_PLAN.md` before choosing a stack or writing",
        "  code. The detected stack above is the source of truth — do not",
        "  switch frameworks without asking.",
        "- `[adopt: please describe]` placeholders mark context the user",
        "  hasn't filled in yet. **Do not block read-only inspection on them.**",
        "  Proceed with the recommended first action above if it's safe and",
        "  read-only. Only ask the user before making decisions (writes,",
        "  refactors, framework choices) that depend on the missing context.",
        "",
        END_MARKER,
    ]
    return "\n".join(lines)


def generate_claude_md_fresh(stack: StackProfile, inputs: AdoptionInputs, title: str,
                             *, reality: Optional[StackReality] = None,
                             project_type: Optional[ProjectType] = None,
                             actions: Optional[list[SuggestedAction]] = None,
                             summary: Optional[AdoptSummary] = None,
                             agent_prompt: Optional[AgentLaunchPrompt] = None) -> str:
    """Full CLAUDE.md when none exists yet.

    Mirrors the shape of cli/_starter/root/CLAUDE.md but tighter — we
    don't ship the full template at adopt time because the user hasn't
    seen the docs-pattern yet. They'll get the full thing if they
    later run ``context-kit init . --force``.
    """
    block = generate_claude_block(stack, inputs, title, reality=reality,
                                  project_type=project_type,
                                  actions=actions, summary=summary,
                                  agent_prompt=agent_prompt)
    return "\n".join([
        f"# CLAUDE / AGENTS — {title}",
        "",
        f"> Generated by `context-kit adopt` on {_today()}. AI session entry point.",
        "",
        "## Read this first",
        "",
        "**If you're an AI agent starting a session here:** the "
        "**Agent Launch Prompt** in this file's managed block "
        "below (also in `00-START-NEXT-SESSION.md`) is the "
        "canonical first message for your session. Use it as the "
        "session opener, then follow its recommended first action.",
        "",
        "For deeper context as you work:",
        "",
        "1. `docs/BUILD_PLAN.md` — the stack and what NOT to change.",
        "2. `docs/PROJECT_WHAT_IT_IS.md` (or `docs/<slug>_WHAT_IT_IS.md`) — what this is and why.",
        "3. `00-START-NEXT-SESSION.md` — the current session priority.",
        "",
        "If you see `[adopt: please describe]` anywhere, that's context the "
        "user hasn't filled in yet — **do not block read-only inspection on "
        "these placeholders.** Proceed with the recommended first action "
        "below if it's safe and read-only. Only ask the user before making "
        "decisions (writes, refactors, framework choices) that depend on "
        "the missing context.",
        "",
        block,
        "",
    ])


# ---------------------------------------------------------------------------
# Layer 2.5: HTML renderer (SESSION_009_ADOPT.md §21)
# ---------------------------------------------------------------------------
#
# A single self-contained HTML report for adopt's dry-run output.
# Pure function from (StackProfile, AdoptionInputs, plan, repo) -> str.
# All disk writes and webbrowser.open() calls happen in run_adopt; the
# renderer itself touches nothing.
#
# Hard contracts (locked in §21):
# - inline CSS, vanilla JS only (collapse via <details>, copy via tiny
#   handler). Same constraint as cli/_static/wizard.html.
# - no server, no HTTP endpoints, no edit/apply actions.
# - source tree untouched by default (run_adopt picks /tmp by default).
# - additive — CLI dry-run stdout is byte-equal with or without --html.


def _default_html_path(repo: Path) -> Path:
    """Stable temp path keyed to the repo's resolved cwd.

    Same project -> same filename -> overwrite in place. Different
    projects on the same machine don't collide. /tmp keeps the
    project's source tree untouched (the load-bearing rule from §21).
    """
    digest = hashlib.sha1(str(repo.resolve()).encode("utf-8")).hexdigest()[:8]
    return Path(tempfile.gettempdir()) / f"contextkit-adopt-report-{digest}.html"


def _esc(s: str) -> str:
    """HTML-escape user-supplied content (description, next_step, paths)."""
    return _html.escape(s, quote=True)


def render_adopt_html(repo: Path, stack: StackProfile,
                      inputs: AdoptionInputs,
                      plan: list,
                      write_mode: bool,
                      failures: Optional[list] = None,
                      reality: Optional[StackReality] = None,
                      project_type: Optional[ProjectType] = None,
                      actions: Optional[list[SuggestedAction]] = None,
                      summary: Optional[AdoptSummary] = None,
                      agent_prompt: Optional[AgentLaunchPrompt] = None) -> str:
    """Build the full self-contained HTML report.

    Six sections per §21:
      1. Header band
      2. Detection summary card
      3. Classified parts card (only when parts non-empty)
      4. Unknown but present (main visual focus, collapsible items)
      5. What adopt would write (with expand-to-preview per file)
      6. Suggested next action CTA
    """
    title = derive_project_title(repo)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ---- Section 2: detection summary ----
    if stack.parts:
        det_label = "Split monorepo"
        det_color = "ok"
    elif stack.language == "unknown":
        # v0.8 Phase 4.5: when workspace inference produced a
        # primary, surface it here too — otherwise the Detection
        # card silently disagrees with the rest of the report
        # (Adopt Summary, Reality, Project type all reflect
        # inference; this card is the only holdout that didn't).
        if stack.inferred_primary is not None:
            det_label = (
                f"{stack.inferred_primary} "
                f"(inferred from workspace children)"
            )
            det_color = "ok"
        else:
            det_label = "Unknown stack"
            det_color = "warn"
    else:
        det_label = _lang_label(stack.language)
        det_color = "ok"
    detection_html = [
        f'<section class="card card-{det_color}">',
        '  <h2>Detection</h2>',
        f'  <p class="lede">{_esc(det_label)}</p>',
    ]
    if stack.signals:
        sig_html = ", ".join(f"<code>{_esc(s)}</code>" for s in stack.signals)
        detection_html.append(f"  <p class=\"meta\">Signals: {sig_html}</p>")
    if stack.notes:
        for note in stack.notes:
            detection_html.append(f"  <p class=\"note\">{_esc(note)}</p>")
    detection_html.append("</section>")

    # ---- Section 3: classified parts (only when split) ----
    parts_html: list[str] = []
    if stack.parts:
        parts_html = [
            '<section class="card">',
            '  <h2>Classified parts</h2>',
            '  <ul class="parts">',
        ]
        for sub, lang in stack.parts.items():
            sig = stack.part_signals.get(sub)
            from_clause = (
                f' <span class="dim">(<code>{_esc(sub)}/{_esc(sig)}</code>)</span>'
                if sig else ""
            )
            parts_html.append(
                f'    <li><strong>{_esc(sub.capitalize())}:</strong> '
                f'{_esc(_lang_label(lang))}{from_clause}</li>'
            )
        parts_html += ['  </ul>', '</section>']

    # ---- Section 3.5: Adopt Summary (v0.8 Phase 4.4) ----
    # Single consolidated card replacing the four separate Phase 3
    # / 4.1 / 4.2 / 4.3 cards (Workspace stack, Stack reality,
    # Project type, Suggested next actions). Sits directly under
    # Detection so the reader gets one read-once block at the top.
    # The standalone helpers (workspace_stack_html, reality_html,
    # project_type_html, actions_html) are kept available below as
    # empty lists for assembly compatibility but are no longer
    # populated.
    summary_html: list[str] = []
    if summary is not None:
        pt = summary.project_type
        r = summary.reality
        # Color the card by reality confidence (proxies overall
        # how-much-to-trust signal).
        sum_card = {"High": "card-ok", "Medium": "card-warn",
                    "Low": "card-warn"}.get(r.confidence, "card-warn")
        summary_html = [
            f'<section class="card {sum_card}">',
            '  <h2>Adopt Summary</h2>',
            '  <div class="summary-grid">',
            # Type
            '    <div class="summary-block">',
            '      <h3>Type</h3>',
            f'      <p><strong>{_esc(pt.label)}</strong> '
            f'<span class="dim">({_esc(pt.confidence)})</span></p>',
            '    </div>',
            # Structure
            '    <div class="summary-block">',
            '      <h3>Structure</h3>',
        ]
        if summary.workspace_pairs:
            summary_html.append('      <ul class="parts">')
            for name, label in summary.workspace_pairs:
                summary_html.append(
                    f'        <li><code>{_esc(name)}</code> → '
                    f'{_esc(label)}</li>'
                )
            summary_html.append('      </ul>')
        else:
            summary_html.append(
                '      <p class="dim">No workspace child projects detected.</p>'
            )
        summary_html.append('    </div>')
        # Reality
        summary_html += [
            '    <div class="summary-block">',
            '      <h3>Reality</h3>',
            f'      <p><strong>{_esc(r.assessment)}</strong> '
            f'<span class="dim">(confidence: {_esc(r.confidence)})</span></p>',
            f'      <p class="dim">{_esc(r.why)}</p>',
            '    </div>',
        ]
        # Next actions
        summary_html.append('    <div class="summary-block">')
        summary_html.append(
            f'      <h3>Next actions ({len(summary.actions)})</h3>'
        )
        if summary.actions:
            summary_html.append('      <ul class="parts">')
            for a in summary.actions:
                summary_html.append(
                    f'        <li><strong>[{_esc(a.priority)}] '
                    f'{_esc(a.title)}</strong> — {_esc(a.reason)}</li>'
                )
            summary_html.append('      </ul>')
        summary_html.append('    </div>')
        summary_html += ['  </div>', '</section>']

    # ---- Section 3.6: Agent launch prompt (v0.10.0 Phase 6.1) ----
    # Sits directly under the Adopt Summary card so the user can
    # grab the prompt without scrolling past the rest of the
    # report. Plain <pre> block + a single copy button — no
    # fancy UI per spec ("This is great, but I want to plug it
    # into my Agent and go").
    agent_prompt_html: list[str] = []
    if agent_prompt is not None:
        ap_card = {"high": "card-ok", "medium": "card-warn",
                   "low": "card-warn"}.get(agent_prompt.confidence,
                                           "card-warn")
        agent_prompt_html = [
            f'<section class="card {ap_card}">',
            f'  <h2>{_esc(agent_prompt.title)}</h2>',
            f'  <p class="meta">Copy-paste this into your AI '
            f'coding agent (Claude Code, Cursor, Aider, etc.) '
            f'as the first message. Confidence: '
            f'<strong>{_esc(agent_prompt.confidence)}</strong>.</p>',
            f'  <pre class="prompt-block" '
            f'id="agent-launch-prompt-text">'
            f'<code>{_esc(agent_prompt.prompt_text)}</code></pre>',
            '  <button class="copy" '
            'data-copy-target="agent-launch-prompt-text">'
            'Copy prompt</button>',
            '</section>',
        ]

    # ---- Phase 3 / 4.x standalone sections — REMOVED in 4.4 ----
    # The Workspace stack, Stack reality, Project type, and
    # Suggested next actions cards are now folded into Adopt
    # Summary above. Empty lists kept for assembly compatibility
    # so the existing out.extend(...) calls below stay valid.
    # v0.8 Phase 4.4 — the four standalone Phase 3 / 4.x card
    # blocks below are still computed (a future debug mode can
    # surface them), but the assembly at the end of this function
    # no longer extends them into ``out``. Adopt Summary above
    # carries the same content in a single card.
    workspace_stack_html: list[str] = []
    ws_stack_pairs = _workspace_stack_pairs(stack)
    if ws_stack_pairs:
        workspace_stack_html = [
            '<section class="card card-ok">',
            '  <h2>Workspace stack</h2>',
            '  <p class="meta">Derived stack labels for depth-2 child '
            'projects. Primary classification above is unchanged — '
            'this is a read-only summary based on each child\'s '
            'manifest / extension signals.</p>',
            '  <ul class="parts">',
        ]
        for name, label in ws_stack_pairs:
            workspace_stack_html.append(
                f'    <li><strong>{_esc(name)}</strong> → {_esc(label)}</li>'
            )
        workspace_stack_html += ['  </ul>', '</section>']

    # ---- Section 3.75: stack reality (v0.8 Phase 4.1) ----
    # Always rendered when reality is provided — every project has
    # an assessment. Card color reflects confidence: ok / warn / warn
    # for High / Medium / Low so the reader gets a visual signal of
    # how much to trust the primary classification line.
    reality_html: list[str] = []
    if reality is not None:
        conf_card = {"High": "card-ok", "Medium": "card-warn",
                     "Low": "card-warn"}.get(reality.confidence, "card-warn")
        reality_html = [
            f'<section class="card {conf_card}">',
            '  <h2>Stack reality</h2>',
            '  <ul class="parts">',
            f'    <li><strong>Primary detection:</strong> '
            f'{_esc(reality.primary)}</li>',
        ]
        if reality.workspace_signals:
            reality_html.append(
                f'    <li><strong>Workspace signals:</strong> '
                f'{_esc(", ".join(reality.workspace_signals))}</li>'
            )
        reality_html += [
            f'    <li><strong>Assessment:</strong> '
            f'{_esc(reality.assessment)}</li>',
            f'    <li><strong>Confidence:</strong> '
            f'{_esc(reality.confidence)}</li>',
            f'    <li><strong>Why:</strong> {_esc(reality.why)}</li>',
            '  </ul>',
            '</section>',
        ]

    # ---- Section 3.85: project type (v0.8 Phase 4.2) ----
    # Sits right after Stack reality so the reader sees "what is
    # this project, really?" answered twice — once as the
    # assessment/confidence/why triad, once as a single human-
    # readable label. Card color tracks confidence the same way
    # Stack reality does.
    _project_type_html: list[str] = []
    if project_type is not None:
        pt_card = {"high": "card-ok", "medium": "card-warn",
                   "low": "card-warn"}.get(project_type.confidence, "card-warn")
        _project_type_html = [
            f'<section class="card {pt_card}">',
            '  <h2>Project type</h2>',
            '  <ul class="parts">',
            f'    <li><strong>Label:</strong> '
            f'{_esc(project_type.label)}</li>',
            f'    <li><strong>Confidence:</strong> '
            f'{_esc(project_type.confidence)}</li>',
            f'    <li><strong>Reason:</strong> '
            f'{_esc(project_type.reason)}</li>',
            '  </ul>',
            '</section>',
        ]

    # ---- Section 3.9: suggested next actions (v0.8 Phase 4.3) ----
    # Prioritized checklist derived from the rest of the analysis.
    # Sits right after Project type so the reader's natural flow
    # is "what is this -> what should I do about it" before the
    # report's detailed sections (clarification dirs, plan,
    # detected issues).
    actions_html: list[str] = []
    if actions:
        # Color the section by the highest priority present.
        priorities = {a.priority for a in actions}
        if "high" in priorities:
            act_card = "card-warn"
        elif "medium" in priorities:
            act_card = "card-warn"
        else:
            act_card = "card-ok"
        actions_html = [
            f'<section class="card {act_card}">',
            f'  <h2>Suggested next actions ({len(actions)})</h2>',
            '  <ul class="parts">',
        ]
        for a in actions:
            actions_html.append(
                f'    <li><strong>[{_esc(a.priority)}] '
                f'{_esc(a.title)}</strong> — {_esc(a.reason)}</li>'
            )
        actions_html += ['  </ul>', '</section>']

    # ---- Section 4: needs clarification (formerly Unknown but present) ----
    # v0.2.x: split into "signal" (manifests / extensions / hints / empty)
    # vs "data-only" (just a file count, no recognized signals). The
    # signal cards render individually; the data-only ones get
    # collapsed into a single "Data / content / non-code" block at the
    # bottom so a 70-card output (example-monorepo) doesn't bury the
    # high-signal directories under a wall of identical "N files (no
    # recognized source extensions)" cards.
    signal_subdirs, data_only_subdirs = _partition_unclassified(stack)
    unknown_html: list[str] = []
    # v0.8 dedup: the section may be empty after filtering out
    # workspace containers covered by workspace_children. Gate on
    # the partitioned lists, not the raw unclassified_subdirs field.
    if signal_subdirs or data_only_subdirs:
        unknown_html = [
            '<section class="card card-warn">',
            '  <h2>Needs clarification</h2>',
            '  <p class="meta">These directories contain files adopt can see, '
            'but it cannot confidently identify their role yet. Confirm what '
            'they are before making changes. Click each to expand.</p>',
        ]
        for u in signal_subdirs:
            # One <details> block per subdir. Native collapse, no JS.
            # v0.8 polish: same dir-head/dir-name/dir-meta layout as
            # workspace-children cards so the directory name reads as
            # the card header rather than blending into the metadata.
            summary_bits: list[str] = []
            if u.manifest_files:
                summary_bits.append(
                    f"manifests: {', '.join(_esc(m) for m in u.manifest_files)}"
                )
            domain_exts = sorted(
                [e for e in u.notable_extensions if e in DOMAIN_HINTS],
                key=lambda e: (-u.notable_extensions[e], e)
            )
            generic_exts = sorted(
                [e for e in u.notable_extensions if e in GENERIC_EXTENSIONS],
                key=lambda e: (-u.notable_extensions[e], e)
            )
            for ext in domain_exts + generic_exts:
                summary_bits.append(f"{u.notable_extensions[ext]}{_esc(ext)}")
            if u.is_empty:
                summary_bits.append("empty")
            elif not summary_bits and u.total_file_count > 0:
                summary_bits.append(f"{u.total_file_count} files (no recognized source extensions)")
            summary_text = " · ".join(summary_bits) if summary_bits else "(no signals)"
            ubp_hint_badge = (
                f' <span class="hint-badge">'
                f'{_esc(u.manifest_hint.split(";")[0])}</span>'
                if u.manifest_hint else ""
            )
            unknown_html.append(
                f'  <details class="unc"><summary>'
                f'<div class="dir-head">'
                f'<span class="dir-name">{_esc(u.name)}/</span>'
                f'{ubp_hint_badge}'
                f'</div>'
                f'<div class="dir-meta">{summary_text}</div>'
                '</summary>'
            )
            # Body contents.
            unknown_html.append('    <div class="unc-body">')
            if u.manifest_files:
                m_str = ", ".join(f"<code>{_esc(m)}</code>" for m in u.manifest_files)
                unknown_html.append(f'      <p><strong>Manifest files:</strong> {m_str}</p>')
            if domain_exts or generic_exts:
                unknown_html.append('      <p><strong>Source extensions:</strong></p>')
                unknown_html.append('      <ul>')
                for ext in domain_exts + generic_exts:
                    count = u.notable_extensions[ext]
                    example = u.example_paths.get(ext)
                    ex_part = (
                        f' — example: <code>{_esc(example)}</code>'
                        if example else ""
                    )
                    unknown_html.append(
                        f'        <li>{count} <code>{_esc(ext)}</code> file'
                        f'{"s" if count != 1 else ""}{ex_part}</li>'
                    )
                unknown_html.append('      </ul>')
            elif u.total_file_count > 0:
                unknown_html.append(
                    f'      <p class="dim">{u.total_file_count} files in scanned tree, '
                    f'but none with extensions adopt categorizes (likely config / data / docs).</p>'
                )
            elif u.is_empty:
                unknown_html.append('      <p class="dim">Directory exists but contains no files.</p>')
            if u.note:
                unknown_html.append(f'      <p class="hint">{_esc(u.note)}</p>')
            if u.manifest_hint:
                unknown_html.append(
                    f'      <p class="hint">{_esc(u.manifest_hint)}</p>'
                )
            unknown_html.append('    </div>')
            unknown_html.append('  </details>')
        # Data-only subdirs: one collapsible holding the lot, so the
        # high-signal cards above stay visually dominant.
        if data_only_subdirs:
            unknown_html.append(
                '  <details class="unc unc-dataonly">'
                f'<summary><strong>Data / content / non-code directories'
                f'</strong> <span class="dim">'
                f'({len(data_only_subdirs)} hidden by default)</span>'
                '</summary>'
                '    <div class="unc-body">'
                '      <p class="dim">These directories contain files but '
                'none with extensions adopt categorizes as source — likely '
                'config, data, generated content, or documentation. '
                'Listed compactly so the high-signal directories above stay '
                'visible.</p>'
                '      <ul>'
            )
            for u in data_only_subdirs:
                unknown_html.append(
                    f'        <li><code>{_esc(u.name)}/</code> '
                    f'<span class="dim">— {u.total_file_count} files</span></li>'
                )
            unknown_html.append('      </ul>')
            unknown_html.append('    </div>')
            unknown_html.append('  </details>')
        unknown_html.append('</section>')

    # ---- Section 4.25: workspace children (v0.8) ----
    # Depth-2 children of known workspace containers (apps/<child>,
    # packages/<child>, ...). Reuses the .unc / .unc-body styling
    # from the unknown-but-present section since the visual shape
    # is the same. Trivial children (only `package.json`, no notable
    # extensions) render as a non-collapsible row — clicking adds
    # nothing the summary didn't already say. Hint shown once via
    # the summary badge; not duplicated inside the body.
    workspace_html: list[str] = []
    if stack.workspace_children:
        n = len(stack.workspace_children)
        workspace_html = [
            '<section class="card">',
            f'  <h2>Workspace children ({n})</h2>',
            '  <p class="meta">Depth-2 walk inside known workspace '
            'containers (<code>apps/</code>, <code>packages/</code>, '
            '<code>services/</code>, <code>crates/</code>, '
            '<code>members/</code>, <code>workspaces/</code>). '
            'Click each to expand. Pure data — adopt\'s primary '
            'classification is unchanged.</p>',
        ]
        for c in stack.workspace_children:
            wsc_domain = sorted(
                [e for e in c.notable_extensions if e in DOMAIN_HINTS],
                key=lambda e: (-c.notable_extensions[e], e)
            )
            wsc_generic = sorted(
                [e for e in c.notable_extensions if e in GENERIC_EXTENSIONS],
                key=lambda e: (-c.notable_extensions[e], e)
            )
            summary_bits: list[str] = []
            if c.manifest_files:
                summary_bits.append(
                    f"manifests: {', '.join(_esc(m) for m in c.manifest_files)}"
                )
            for ext in wsc_domain + wsc_generic:
                summary_bits.append(f"{c.notable_extensions[ext]}{_esc(ext)}")
            summary_text = " · ".join(summary_bits) if summary_bits else "(no signals)"
            hint_badge = (
                f' <span class="hint-badge">'
                f'{_esc(c.hint.split(";")[0])}</span>'
                if c.hint else ""
            )
            # Trivial child: nothing in the body would beat the
            # summary, so render a non-collapsible div instead of
            # a <details> with an empty disclosure.
            trivial = (
                c.manifest_files == ["package.json"]
                and not c.notable_extensions
            )
            # Name is rendered as its own block so the user can
            # scan child names down the left edge of the report.
            # Manifests / extensions render as a smaller dim line
            # underneath. Hint badge sits inline next to the name.
            if trivial:
                workspace_html.append(
                    f'  <div class="unc unc-trivial">'
                    f'<div class="dir-head">'
                    f'<span class="dir-name">{_esc(c.name)}</span>'
                    f'{hint_badge}'
                    f'</div>'
                    f'<div class="dir-meta">{summary_text}</div>'
                    f'</div>'
                )
                continue
            workspace_html.append(
                f'  <details class="unc"><summary>'
                f'<div class="dir-head">'
                f'<span class="dir-name">{_esc(c.name)}</span>'
                f'{hint_badge}'
                f'</div>'
                f'<div class="dir-meta">{summary_text}</div>'
                '</summary>'
            )
            workspace_html.append('    <div class="unc-body">')
            if c.manifest_files:
                m_str = ", ".join(f"<code>{_esc(m)}</code>" for m in c.manifest_files)
                workspace_html.append(
                    f'      <p><strong>Manifest files:</strong> {m_str}</p>'
                )
            if wsc_domain or wsc_generic:
                workspace_html.append('      <p><strong>Source extensions:</strong></p>')
                workspace_html.append('      <ul>')
                for ext in wsc_domain + wsc_generic:
                    count = c.notable_extensions[ext]
                    workspace_html.append(
                        f'        <li>{count} <code>{_esc(ext)}</code> file'
                        f'{"s" if count != 1 else ""}</li>'
                    )
                workspace_html.append('      </ul>')
            # Hint already shown via .hint-badge in the summary —
            # don't repeat inside the expanded body.
            workspace_html.append('    </div>')
            workspace_html.append('  </details>')
        workspace_html.append('</section>')

    # ---- Section 4.5: detected issues (v0.2.x failure taxonomy) ----
    # Pure metadata — adopt's classification, plan, and writes are
    # unchanged. The section is silently omitted on clean projects.
    failures = failures or []
    failures_html: list[str] = []
    if failures:
        # Severity -> CSS class for the badge color.
        sev_class = {"high": "sev-high", "medium": "sev-medium", "low": "sev-low"}
        failures_html = [
            '<section class="card card-warn">',
            '  <h2>Diagnostic signals</h2>',
            '  <p class="meta">Signals from adopt\'s internal failure '
            'taxonomy. These help explain classification limits and '
            'review priorities; they do not mean the project is '
            'broken.</p>',
        ]
        # Order: high severity first, then by failure_type for stable
        # rendering across runs.
        ordered = sorted(failures, key=lambda f: (
            {"high": 0, "medium": 1, "low": 2}.get(f.severity, 3),
            f.failure_type,
            f.detected_in,
        ))
        for f in ordered:
            cls = sev_class.get(f.severity, "sev-low")
            failures_html.append(
                f'  <details class="failure"><summary>'
                f'<span class="badge {cls}">{_esc(f.severity)}</span> '
                f'<code>{_esc(f.failure_type)}</code> '
                f'<span class="dim">— {_esc(f.detected_in)} '
                f'<span class="surface">[{_esc(f.surface_area)}]</span></span>'
                f'</summary>'
                f'    <div class="failure-body">'
                f'      <p>{_esc(f.description)}</p>'
                f'      <p class="dim">Example: <code>{_esc(f.example)}</code></p>'
                f'    </div>'
                f'  </details>'
            )
        failures_html.append('</section>')

    # ---- Section 5: plan with previews ----
    plan_html = ['<section class="card">', '  <h2>What adopt would write</h2>']
    verb_prefix = "Will " if write_mode else "Would "
    for p in plan:
        rel_path = p.path.relative_to(repo).as_posix() if p.path.is_relative_to(repo) else Path(p.path).as_posix()
        badge_cls = "badge-create" if p.kind == "create" else "badge-augment"
        badge_text = f"{verb_prefix}{p.kind}"
        plan_html.append(
            f'  <details class="planfile"><summary>'
            f'<span class="badge {badge_cls}">{_esc(badge_text)}</span> '
            f'<code>{_esc(rel_path)}</code>'
            f'</summary>'
            f'<pre class="preview"><code>{_esc(p.content)}</code></pre>'
            f'</details>'
        )
    plan_html.append('</section>')

    # ---- Section 6: suggested next action ----
    needs_inputs = (not inputs.project_description.strip()) or (not inputs.next_step.strip())
    if write_mode:
        cta_class = "card-ok"
        cta_title = "Done — files written."
        cta_body = (
            '<p>Open your AI tool against this project. If you use Claude '
            'Code, run <code>claude</code> in this folder, then paste:</p>'
            '<div class="cmd"><span id="primer">'
            'Read CLAUDE.md, docs/BUILD_PLAN.md, and docs/*_WHAT_IT_IS.md. '
            'Summarize the project, confirm the stack, then begin implementing '
            'version 1. Do not change the stack without asking.</span>'
            '<button class="copy" data-copy-target="primer">Copy</button></div>'
        )
    elif needs_inputs:
        cta_class = "card-warn"
        cta_title = "Fill in description and next step before --write"
        cta_body = (
            '<p>One or both of the prompts adopt asked you ("What is this '
            'project?" / "What are you trying to do next?") was empty. The '
            'generated docs would land mostly as placeholder text. Re-run '
            'with non-empty answers, then add <code>--write</code> when '
            'the report looks right.</p>'
        )
    else:
        cmd = f"context-kit adopt {repo} --write"
        cta_class = "card-ok"
        cta_title = "Looks good — run with --write"
        cta_body = (
            '<p>The plan above looks ready. Run this in your terminal '
            'to apply it:</p>'
            f'<div class="cmd"><span id="cta-cmd">{_esc(cmd)}</span>'
            '<button class="copy" data-copy-target="cta-cmd">Copy</button></div>'
            '<p class="dim">After it writes, the generated docs will '
            'contain a few <code>[adopt: please describe]</code> hints '
            'where adopt couldn\'t infer details (the project\'s "why" '
            'and audience). Fill those in before running an AI session '
            'against the project.</p>'
        )
    cta_html = [
        f'<section class="card cta {cta_class}">',
        f'  <h2>{_esc(cta_title)}</h2>',
        f'  {cta_body}',
        '</section>',
    ]

    # ---- Header band ----
    header_html = [
        '<header>',
        f'  <h1>{_esc(title)}</h1>',
        f'  <p class="cwd"><code>{_esc(str(repo))}</code></p>',
        f'  <p class="meta">Generated by <code>context-kit adopt</code> · {_esc(when)}</p>',
        '</header>',
    ]

    # ---- Inline styles + JS (no external assets) ----
    style = """
    :root {
      --bg: #0f1117; --panel: #151822; --panel-2: #1c2030;
      --border: #262a35; --text: #e5e7eb; --muted: #9ca3af;
      --accent: #6ee7b7; --accent-strong: #10b981;
      --warn: #fbbf24; --warn-strong: #b45309;
      --danger: #f87171;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, "Roboto Mono", monospace;
    }
    @media (prefers-color-scheme: light) {
      :root {
        --bg: #fafbfc; --panel: #ffffff; --panel-2: #f3f4f6;
        --border: #e5e7eb; --text: #111827; --muted: #6b7280;
        --accent: #059669; --accent-strong: #047857;
        --warn: #b45309; --warn-strong: #92400e;
        --danger: #dc2626;
      }
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
      background: var(--bg); color: var(--text);
    }
    .wrap { max-width: 720px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }
    header { margin-bottom: 1.5rem; }
    header h1 { font-size: 1.6rem; margin: 0 0 .25rem; letter-spacing: -0.01em; }
    header .cwd { color: var(--muted); font-size: .9rem; margin: .25rem 0; }
    header .meta { color: var(--muted); font-size: .85rem; margin: .25rem 0; }
    .card {
      background: var(--panel); border: 1px solid var(--border); border-left: 4px solid var(--border);
      border-radius: 10px; padding: 1.25rem 1.5rem; margin-bottom: 1rem;
    }
    .card-ok { border-left-color: var(--accent-strong); }
    .card-warn { border-left-color: var(--warn); }
    .card-danger { border-left-color: var(--danger); }
    h2 { font-size: 1.15rem; margin: 0 0 .75rem; }
    .lede { font-size: 1.1rem; margin: .25rem 0 .5rem; }
    .meta { color: var(--muted); font-size: .9rem; margin: .25rem 0; }
    .note { color: var(--muted); font-size: .9rem; margin: .35rem 0; font-style: italic; }
    .dim { color: var(--muted); }
    .hint { color: var(--warn-strong); font-size: .9rem; margin: .5rem 0; }
    code { font-family: var(--mono); background: var(--border); padding: .1rem .35rem; border-radius: 4px; font-size: .9em; }
    .parts { padding-left: 1.25rem; margin: .25rem 0; }
    .parts li { margin: .25rem 0; }
    details.unc, details.planfile {
      background: var(--panel-2); border: 1px solid var(--border);
      border-radius: 6px; padding: .55rem .85rem; margin: .5rem 0;
    }
    details.unc summary, details.planfile summary {
      cursor: pointer; user-select: none; font-size: .95rem;
    }
    /* Directory cards (v0.8 polish): the directory / child-project
       name is the load-bearing label of every card in the
       Unknown-but-present and Workspace-children sections, so it
       gets its own block-level line above the metadata. Bolder
       weight + accent color + slightly larger font lets the eye
       scan names down the left edge of the section without
       expanding cards. The dir-meta line beneath stays muted. */
    .dir-head {
      display: flex; align-items: baseline; gap: .55rem;
      flex-wrap: wrap; margin-bottom: .15rem;
    }
    .dir-name {
      font-family: var(--mono); font-weight: 700; font-size: 1.05rem;
      color: var(--accent-strong); letter-spacing: -0.005em;
    }
    .dir-meta {
      display: block; color: var(--muted); font-size: .85rem;
      font-family: var(--mono); margin-top: .15rem;
    }
    /* Override the legacy code.dirname rule so any caller still
       using that class picks up the same prominent treatment. */
    details.unc summary code.dirname {
      font-weight: 700; font-size: 1.05rem; color: var(--accent-strong);
    }
    .unc-trivial { padding: .55rem .85rem; }
    /* v0.10.0 Phase 6.1 — agent launch prompt block. Plain
       monospace, scrollable when long, sized so the entire
       prompt fits without dwarfing the rest of the report. */
    .prompt-block {
      background: var(--panel-2); border: 1px solid var(--border);
      border-radius: 6px; padding: .85rem 1rem;
      font-family: var(--mono); font-size: .82rem;
      white-space: pre-wrap; word-break: break-word;
      max-height: 30rem; overflow-y: auto; margin: .75rem 0;
    }
    .unc-body { margin-top: .75rem; padding-top: .5rem; border-top: 1px solid var(--border); font-size: .9rem; }
    .unc-body ul { padding-left: 1.25rem; margin: .25rem 0; }
    pre.preview {
      background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
      padding: .85rem 1rem; font-family: var(--mono); font-size: .82rem;
      overflow-x: auto; white-space: pre-wrap; word-break: break-word;
      max-height: 24rem; overflow-y: auto; margin: .75rem 0 0;
    }
    .badge {
      display: inline-block; padding: .1rem .55rem; border-radius: 4px;
      font-size: .75rem; font-weight: 600; letter-spacing: .02em; text-transform: uppercase;
      margin-right: .5rem;
    }
    .badge-create { background: rgba(16, 185, 129, .15); color: var(--accent-strong); }
    .badge-augment { background: rgba(251, 191, 36, .18); color: var(--warn-strong); }
    .hint-badge {
      display: inline-block; margin-left: .5rem;
      padding: .05rem .5rem; border-radius: 4px;
      font-size: .75rem; font-weight: 600; letter-spacing: .01em;
      background: rgba(251, 191, 36, .18); color: var(--warn-strong);
    }
    .sev-high   { background: rgba(248, 113, 113, .18); color: var(--danger); }
    .sev-medium { background: rgba(251, 191, 36, .18); color: var(--warn-strong); }
    .sev-low    { background: var(--border); color: var(--muted); }
    details.failure {
      background: var(--panel-2); border: 1px solid var(--border);
      border-radius: 6px; padding: .55rem .85rem; margin: .5rem 0;
    }
    details.failure summary { cursor: pointer; user-select: none; font-size: .95rem; }
    .failure-body { margin-top: .55rem; padding-top: .5rem; border-top: 1px solid var(--border); font-size: .9rem; }
    .surface { color: var(--muted); font-size: .8rem; font-style: italic; }
    .cta h2 { font-size: 1.25rem; }
    .cmd {
      background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px;
      padding: .65rem .85rem; font-family: var(--mono); font-size: .9rem;
      display: flex; align-items: center; justify-content: space-between;
      gap: .5rem; margin: .75rem 0;
    }
    .cmd .copy {
      flex-shrink: 0; background: var(--border); color: var(--text);
      padding: .25rem .55rem; font-size: .8rem; font-weight: 400;
      border: none; border-radius: 4px; cursor: pointer; font: inherit;
    }
    footer { color: var(--muted); font-size: .8rem; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border); }
    """

    js = """
    document.body.addEventListener('click', async (e) => {
      const btn = e.target.closest('.copy');
      if (!btn) return;
      const targetId = btn.getAttribute('data-copy-target');
      if (!targetId) return;
      const el = document.getElementById(targetId);
      if (!el) return;
      try {
        await navigator.clipboard.writeText(el.textContent);
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = orig; }, 1200);
      } catch (err) { /* ignore */ }
    });
    """

    out = [
        '<!doctype html>',
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_esc(title)} · adopt review</title>',
        f'<style>{style}</style>',
        '</head><body><div class="wrap">',
    ]
    out.extend(header_html)
    out.extend(detection_html)
    out.extend(parts_html)
    # v0.8 Phase 4.4 — the four standalone Phase 3 / 4.x cards
    # are folded into Adopt Summary; not extended into the final
    # output. summary_html is rendered above unknown_html so the
    # reader sees the consolidated assessment first.
    out.extend(summary_html)
    # v0.10.0 Phase 6.1 — Agent launch prompt sits directly under
    # the Adopt Summary so the copy-paste block is the second
    # thing the reader sees.
    out.extend(agent_prompt_html)
    out.extend(unknown_html)
    out.extend(workspace_html)
    out.extend(failures_html)
    out.extend(plan_html)
    out.extend(cta_html)
    out.append(
        '<footer>'
        'Static review report from <code>context-kit adopt --html</code>. '
        'Read-only — to apply this plan or change inputs, re-run the CLI. '
        'Re-runs against the same project overwrite this file in place.'
        '</footer>'
    )
    out.append('</div>')
    out.append(f'<script>{js}</script>')
    out.append('</body></html>')
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Layer 3: materializer (the only thing that touches disk)
# ---------------------------------------------------------------------------


def _plan_managed_doc(path: Path, content: str) -> PlannedFile:
    """Plan one of the three new marker-managed docs (BUILD_PLAN.md,
    PROJECT_WHAT_IT_IS.md, 00-START-NEXT-SESSION.md).

    Three outcomes:
    - file doesn't exist -> CREATE the marker-wrapped content
    - file exists with adopt markers -> AUGMENT (refresh inside markers)
    - file exists WITHOUT adopt markers -> SKIP (assumed hand-written;
      adopt is not authorized to clobber)

    The third outcome is the load-bearing safety case from the
    example-monorepo dogfood: an existing 00-START-NEXT-SESSION.md
    that v0.2 would have overwritten on --write. SKIP makes adopt
    safe to re-run on any project, including legacy ones with their
    own hand-written copies of these files.
    """
    if not path.is_file():
        return PlannedFile(path=path, content=content, kind="create")
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        return PlannedFile(path=path, content="", kind="skip")
    if START_MARKER in existing and END_MARKER in existing:
        return PlannedFile(path=path, content=content, kind="augment")
    return PlannedFile(path=path, content="", kind="skip")


def plan_files(
    repo: Path,
    stack: StackProfile,
    inputs: AdoptionInputs,
    *,
    reality: Optional[StackReality] = None,
    project_type: Optional[ProjectType] = None,
    actions: Optional[list[SuggestedAction]] = None,
    summary: Optional[AdoptSummary] = None,
    agent_prompt: Optional[AgentLaunchPrompt] = None,
) -> list[PlannedFile]:
    """Build the list of files we'd create / augment / skip, without writing.

    All four target files now use marker-managed content (v0.2.x):
    - CLAUDE.md: existing augment-or-create-fresh logic. If the file
      exists without adopt markers, the managed block is *appended*
      (CLAUDE.md is the AI session entry-point, so adding our block
      is value-add even on hand-written files).
    - BUILD_PLAN.md / PROJECT_WHAT_IT_IS.md / 00-START-NEXT-SESSION.md:
      ``_plan_managed_doc`` — CREATE if absent, AUGMENT if our markers
      already exist, SKIP if the file exists without markers (don't
      clobber hand-written content).

    ``reality`` is the v0.8 Phase 4.1 derived assessment. When
    provided, BUILD_PLAN.md and CLAUDE.md inherit it so the same
    self-contained Stack reality block lands in every output path.
    """
    title = derive_project_title(repo)
    plan: list[PlannedFile] = []

    plan.append(_plan_managed_doc(
        repo / "docs" / "BUILD_PLAN.md",
        generate_build_plan(stack, inputs, title, reality=reality,
                            project_type=project_type, actions=actions,
                            summary=summary, agent_prompt=agent_prompt),
    ))
    # v0 uses a fixed filename (``PROJECT_WHAT_IT_IS.md``) rather than
    # the slug-based ``<APP>_WHAT_IT_IS.md`` the rest of context-kit
    # uses. Keeps the v0 output predictable and sidesteps the "temp
    # dir name leaks into a docs filename" footgun. The full release
    # can switch to slug-based naming once we add the project-name
    # prompt promised in the design.
    plan.append(_plan_managed_doc(
        repo / "docs" / "PROJECT_WHAT_IT_IS.md",
        generate_what_it_is(stack, inputs, title),
    ))
    plan.append(_plan_managed_doc(
        repo / "00-START-NEXT-SESSION.md",
        generate_start_here(inputs, title, agent_prompt=agent_prompt),
    ))

    claude_path = repo / "CLAUDE.md"
    if claude_path.is_file():
        plan.append(PlannedFile(
            path=claude_path,
            content=generate_claude_block(stack, inputs, title, reality=reality,
                                          project_type=project_type,
                                          actions=actions, summary=summary,
                                          agent_prompt=agent_prompt),
            kind="augment",
        ))
    else:
        plan.append(PlannedFile(
            path=claude_path,
            content=generate_claude_md_fresh(stack, inputs, title, reality=reality,
                                             project_type=project_type,
                                             actions=actions, summary=summary,
                                             agent_prompt=agent_prompt),
            kind="create",
        ))
    return plan


def _apply_managed_block(existing: str, new_content: str) -> str:
    """Splice the marker block from ``new_content`` into ``existing``.

    Two cases:
    - Markers already in ``existing``: replace everything between them
      (and DROP any prelude/postlude in ``new_content`` outside its own
      markers — the existing file's prelude is what the user has, and
      we preserve it verbatim).
    - Markers absent in ``existing``: append the marker block to the
      end of ``existing``.

    Either way, content OUTSIDE the markers in ``existing`` is preserved
    byte-for-byte (modulo head .rstrip() / tail .lstrip("\\n") that
    normalize surrounding whitespace). This is the load-bearing safety
    primitive for v0.2.x idempotency: re-running ``adopt --write``
    against a project where the user has hand-edited prose around the
    managed block keeps the user's edits intact.

    The prelude-stripping behavior matters specifically for the
    00-START-NEXT-SESSION.md case: ``generate_start_here`` returns
    ``frontmatter + marker_block``, and on augment we must NOT
    re-paste the frontmatter (it's already in the existing file's
    ``head``). Without this, the YAML frontmatter would double on
    every steady-state re-run.
    """
    # Normalize: extract just the START..END marker block from
    # new_content. Anything in new_content before START_MARKER or
    # after END_MARKER is irrelevant for augment-mode (the existing
    # file's outside-markers content is the canonical version).
    if START_MARKER in new_content and END_MARKER in new_content:
        _, _, after_start = new_content.partition(START_MARKER)
        between, _, _ = after_start.partition(END_MARKER)
        new_block = START_MARKER + between + END_MARKER
    else:
        new_block = new_content

    if START_MARKER in existing and END_MARKER in existing:
        head, _, rest = existing.partition(START_MARKER)
        _, _, tail = rest.partition(END_MARKER)
        head_stripped = head.rstrip()
        tail_stripped = tail.lstrip("\n")
        # When the file IS the marker block (no head/tail), don't
        # prepend ``\n\n`` or append extra blank lines — the augment
        # output must be byte-identical to a fresh create on
        # idempotent re-runs.
        head_part = (head_stripped + "\n\n") if head_stripped else ""
        tail_part = ("\n\n" + tail_stripped) if tail_stripped else "\n"
        return head_part + new_block.rstrip() + tail_part
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + "\n" + new_block.rstrip() + "\n"


# Backwards-compat alias for any external callers that imported the
# pre-v0.2.x name. The new general name is _apply_managed_block.
_augment_claude_md = _apply_managed_block


def apply_plan(plan: list[PlannedFile], dry_run: bool) -> list[str]:
    """Execute the plan; return per-file action verbs.

    Action kinds (``would `` prefix when dry_run=True):
    - **create**: file doesn't exist; write ``content`` whole.
    - **augment**: file exists with adopt markers (or, for CLAUDE.md,
      exists at all); splice ``content`` into the managed block via
      ``_apply_managed_block``. Content outside markers is preserved.
    - **skip**: file exists without adopt markers AND isn't CLAUDE.md.
      Do not touch — the user's hand-written file stays intact.

    Source code is never touched. Only docs/* and the two root-level
    docs (CLAUDE.md, 00-START-NEXT-SESSION.md) are written.
    """
    actions: list[str] = []
    for item in plan:
        verb_prefix = "would " if dry_run else ""
        if item.kind == "skip":
            actions.append(
                f"  {verb_prefix}skip       {item.path}  "
                f"(exists without adopt markers — not safe to overwrite)"
            )
            continue
        if item.kind == "augment" and item.path.is_file():
            verb = f"{verb_prefix}augment"
            if not dry_run:
                existing = item.path.read_text(encoding="utf-8")
                merged = _apply_managed_block(existing, item.content)
                item.path.write_text(merged, encoding="utf-8")
        else:
            # "create" path — also fires for "augment" when the file
            # is missing, which can happen if CLAUDE.md vanishes
            # between plan() and apply().
            verb = f"{verb_prefix}create"
            if not dry_run:
                item.path.parent.mkdir(parents=True, exist_ok=True)
                item.path.write_text(item.content, encoding="utf-8")
        actions.append(f"  {verb:<14} {item.path}")
    return actions


# ---------------------------------------------------------------------------
# Interactive prompts
# ---------------------------------------------------------------------------


def collect_inputs(
    prompt_fn: Optional[Callable[[str], str]] = None,
    description: Optional[str] = None,
    next_step: Optional[str] = None,
    notes: Optional[str] = None,
) -> AdoptionInputs:
    """Ask the two questions exactly once each.

    v0.10.x — wording sharpened so the user understands what the
    answer is for. Each question is asked at most once per adopt
    run; the resulting answers are reused by every downstream
    renderer (BUILD_PLAN, PROJECT_WHAT_IT_IS, CLAUDE.md,
    00-START-NEXT-SESSION.md, Agent Launch Prompt, CLI / HTML
    previews). Callers that already have the answers (CLI flags
    ``--project-summary`` / ``--next-task``, tests, the wizard)
    pass them as overrides and no prompt fires.

    ``notes`` (v0.10.x ``--notes`` flag) is opt-in and never
    prompted — when omitted, the resulting ``AdoptionInputs.notes``
    is the empty string and downstream renderers omit the
    notes section entirely.

    ``prompt_fn`` defaults to ``builtins.input`` resolved at call
    time (NOT capture-at-import) so tests can monkey-patch
    ``builtins.input`` without re-binding this default.
    """
    if prompt_fn is None:
        prompt_fn = input
    if description is None:
        description = prompt_fn(
            "In one sentence, what is this project? "
        ).strip()
    if next_step is None:
        next_step = prompt_fn(
            "What should the next AI session help with? "
        ).strip()
    return AdoptionInputs(
        project_description=description,
        next_step=next_step,
        notes=(notes or ""),
    )


# ---------------------------------------------------------------------------
# Failure detection (v0.2.x)
# ---------------------------------------------------------------------------
#
# Deterministic rules over StackProfile + plan that emit FailureRecord
# entries from the fixed taxonomy. Pure additive metadata — does NOT
# change classification, plan, or any written output. Each detector is
# a small predicate; multiple detectors can fire for the same project.

# Manifest filenames that imply an ECOSYSTEM adopt's classifier doesn't
# yet handle (different language family entirely). Distinct from
# ``_FRAMEWORK_MANIFESTS`` below which are framework names *within* a
# language we DO classify.
_ECOSYSTEM_MANIFESTS = {
    "Clarinet.toml":     "Clarity / Stacks",
    "foundry.toml":      "Foundry / Solidity",
    "Anchor.toml":       "Anchor / Solana",
    "Move.toml":         "Move (Sui/Aptos)",
    "flow.json":         "Flow blockchain",
    "pubspec.yaml":      "Flutter / Dart",
    "Cargo.toml":        "Rust",
    "go.mod":            "Go",
    "Gemfile":           "Ruby",
    # v0.3 — root-level Dart monorepo manifest.
    # See SESSION_009_ADOPT.md §22 (root-level UNRECOGNIZED_ECOSYSTEM
    # extension): the v0.2.x detector loop only checked subdir
    # manifest_files, so a project with melos.yaml at root and
    # nothing else fired no failure record. Adding melos here lets
    # the new root-scan path label it.
    "melos.yaml":        "Dart / Flutter monorepo (Melos)",
}

# Manifest filenames that imply a SPECIFIC FRAMEWORK on a language adopt
# already classifies. Their presence means the classifier's label
# undersells the project (e.g. Truffle reads as plain "JavaScript").
_FRAMEWORK_MANIFESTS = {
    "truffle-config.js":     "Truffle",
    "hardhat.config.js":     "Hardhat",
    "hardhat.config.ts":     "Hardhat",
    "hardhat.config.mjs":    "Hardhat",
    "hardhat.config.cjs":    "Hardhat",
    "brownie-config.yaml":   "Brownie",
    "rxconfig.py":           "Reflex",
    "manage.py":             "Django",
}

# Combined "strong framework signal" set — a subdir containing any of
# these has stronger evidence than a generic root package.json /
# requirements.txt. Used for ROOT_SIGNAL_OVERRIDE.
_STRONG_FRAMEWORK_MANIFESTS = (
    frozenset(_ECOSYSTEM_MANIFESTS) | frozenset(_FRAMEWORK_MANIFESTS)
)

# Threshold for NOISE_DIRECTORY_POLLUTION — projects with this many
# data-only dirs are noisy enough to flag as a UX concern even after
# the v0.2.x grouping (35 in example-monorepo; 1 in example-solidity-app).
_NOISE_POLLUTION_THRESHOLD = 5

# Threshold for STRUCTURE_UNDERREPRESENTED — number of signal subdirs
# (manifests or notable extensions) before the classification line is
# considered to undersell the project's surface area.
_STRUCTURE_UNDERREPRESENTED_THRESHOLD = 3

# v0.3 — workspace-container subdir names. A non-noise depth-1 subdir
# matching one of these likely contains child projects below adopt's
# scan depth. Used by MONOREPO_DEPTH_LIMIT. See SESSION_009_ADOPT.md §22.
_WORKSPACE_CONTAINERS = frozenset({
    "apps", "packages", "services", "crates", "members", "workspaces",
})

# v0.3 — threshold for MONOREPO_DEPTH_LIMIT. A workspace container
# either has at least this many source files (collapsed across child
# projects via the existing depth-2 walk) OR has at least one
# example-path indicating content nested below the container's
# immediate root (path containing two or more "/" separators since
# adopt's example paths are anchored at the subdir name).
_MONOREPO_DEPTH_FILE_THRESHOLD = 10


def analyze_failures(repo: Path, stack: StackProfile,
                     plan: list) -> list[FailureRecord]:
    """Apply the deterministic detection rules; return the failure set.

    Pure function — no I/O, no mutation. Caller passes the already-
    computed ``stack`` and ``plan``; analyzer reads, never modifies.
    Multiple FailureRecord entries can fire for the same project; the
    same failure_type can appear at most once per ``detected_in``
    target so a 70-subdir repo doesn't get 70 cards of the same type.
    """
    out: list[FailureRecord] = []

    # ROOT_SIGNAL_OVERRIDE — root won classification but a subdir has
    # a strictly stronger framework manifest (manage.py, foundry.toml,
    # Clarinet.toml, etc.). example-django-app is the canonical case.
    if stack.signals and not stack.parts:
        for u in stack.unclassified_subdirs:
            strong = next(
                (m for m in u.manifest_files
                 if m in _STRONG_FRAMEWORK_MANIFESTS),
                None,
            )
            if strong:
                out.append(FailureRecord(
                    failure_type=FAILURE_ROOT_SIGNAL_OVERRIDE,
                    severity="high",
                    surface_area="classification",
                    description=(
                        f"Root manifest won classification "
                        f"({_lang_label(stack.language)}), but "
                        f"{u.name}/ contains {strong} — a stronger "
                        f"framework signal. The primary stack label "
                        f"may be misleading."
                    ),
                    detected_in=u.name,
                    example=f"{u.name}/{strong}",
                ))
                break  # one card is enough; no need to spam per-subdir

    # UNRECOGNIZED_ECOSYSTEM — a subdir has a manifest from an entire
    # language family adopt doesn't classify. example-clarity-contract,
    # example-mobile-app (mobile/), example-solidity-app, etc.
    seen_eco_dirs: set[str] = set()
    for u in stack.unclassified_subdirs:
        for m in u.manifest_files:
            if m in _ECOSYSTEM_MANIFESTS and u.name not in seen_eco_dirs:
                out.append(FailureRecord(
                    failure_type=FAILURE_UNRECOGNIZED_ECOSYSTEM,
                    severity="medium",
                    surface_area="classification",
                    description=(
                        f"{u.name}/{m} indicates "
                        f"{_ECOSYSTEM_MANIFESTS[m]}, an ecosystem "
                        f"adopt's classifier doesn't yet handle. "
                        f"Visibility-first surfaces it; classification "
                        f"label stays generic."
                    ),
                    detected_in=u.name,
                    example=f"{u.name}/{m}",
                ))
                seen_eco_dirs.add(u.name)
                break

    # UNRECOGNIZED_ECOSYSTEM (root extension, v0.3) — same label,
    # same severity, but for ecosystem manifests at the project root
    # rather than inside an unclassified subdir. flutter-monorepo's
    # melos.yaml at root was the motivating case (see §22): the file
    # is visible (manifest-shaped) but the v0.2.x detector loop only
    # checked unclassified_subdirs[*].manifest_files, never root files.
    # Fires at most once for the root regardless of how many ecosystem
    # manifests are present, mirroring the per-subdir dedup above.
    try:
        for entry in repo.iterdir():
            if (entry.is_file()
                    and entry.name in _ECOSYSTEM_MANIFESTS):
                out.append(FailureRecord(
                    failure_type=FAILURE_UNRECOGNIZED_ECOSYSTEM,
                    severity="medium",
                    surface_area="classification",
                    description=(
                        f"{entry.name} at the project root indicates "
                        f"{_ECOSYSTEM_MANIFESTS[entry.name]}, an "
                        f"ecosystem adopt's classifier doesn't yet "
                        f"handle. Visibility surfaces nothing more "
                        f"useful for root-level files."
                    ),
                    detected_in="root",
                    example=entry.name,
                ))
                break
    except OSError:
        pass

    # SILENT_SUBDIR_DROP — a recognized subdir name (backend, frontend,
    # web, mobile, api, client, server) appears in unclassified_subdirs
    # with content. Classification scan saw the name but couldn't
    # classify the manifests inside. example-mobile-app's mobile/.
    for u in stack.unclassified_subdirs:
        if (u.name in RECOGNIZED_SUBDIRS
                and (u.notable_extensions or u.manifest_files)):
            example = (
                u.manifest_files[0] if u.manifest_files
                else next(iter(u.notable_extensions), "")
            )
            out.append(FailureRecord(
                failure_type=FAILURE_SILENT_SUBDIR_DROP,
                severity="high",
                surface_area="visibility",
                description=(
                    f"Recognized subdir {u.name}/ has content "
                    f"({u.total_file_count} files) but adopt's classifier "
                    f"didn't pick it up — visibility-first is the only "
                    f"reason it appears in this report at all."
                ),
                detected_in=u.name,
                example=f"{u.name}/{example}",
            ))

    # WRAPPER_DIRECTORY_INVISIBILITY — root has nothing AND the
    # actual project lives one level down under a NON-recognized name.
    # example-clarity-contract's timelocked-wallet/.
    if stack.language == "unknown":
        signal_subs = [
            u for u in stack.unclassified_subdirs
            if (not _is_data_only_subdir(u)
                and not u.is_empty
                and u.name not in RECOGNIZED_SUBDIRS
                and (u.manifest_files or u.notable_extensions))
        ]
        if len(signal_subs) == 1:
            u = signal_subs[0]
            example = (
                u.manifest_files[0] if u.manifest_files
                else next(iter(u.example_paths.values()), u.name)
            )
            out.append(FailureRecord(
                failure_type=FAILURE_WRAPPER_DIRECTORY_INVISIBILITY,
                severity="high",
                surface_area="visibility",
                description=(
                    f"Root has no classifier signal and the actual "
                    f"project lives under {u.name}/. Adopt's depth-1 "
                    f"scan surfaces the contents but classification "
                    f"can't reach inside the wrapper."
                ),
                detected_in=u.name,
                example=f"{u.name}/{example}" if "/" not in example else example,
            ))

    # NOISE_DIRECTORY_POLLUTION — many data-only subdirs even after
    # the v0.2.x grouping. example-monorepo had 35.
    data_only = [u for u in stack.unclassified_subdirs
                 if _is_data_only_subdir(u)]
    if len(data_only) >= _NOISE_POLLUTION_THRESHOLD:
        out.append(FailureRecord(
            failure_type=FAILURE_NOISE_DIRECTORY_POLLUTION,
            severity="low",
            surface_area="UX",
            description=(
                f"{len(data_only)} directories contain files but no "
                f"recognized source extensions. They're already grouped "
                f"into a single collapsible, but the volume itself "
                f"signals a project where reviewing the report needs "
                f"care."
            ),
            detected_in="root",
            example=", ".join(u.name + "/" for u in data_only[:3]),
        ))

    # IDEMPOTENCY_RISK — any plan item is "skip" (file exists without
    # adopt markers; we won't touch it). Surfaces user-content safety.
    for p in plan:
        if p.kind != "skip":
            continue
        try:
            rel = p.path.relative_to(repo).as_posix()
        except ValueError:
            rel = Path(p.path).as_posix()
        out.append(FailureRecord(
            failure_type=FAILURE_IDEMPOTENCY_RISK,
            severity="medium",
            surface_area="safety",
            description=(
                f"{p.path.name} already exists without adopt's managed "
                f"markers. Adopt will skip it to protect your hand-"
                f"written content; the doc's content also won't appear "
                f"in your AI-session entry-points until you let adopt "
                f"manage the file."
            ),
            detected_in="root",
            example=rel,
        ))

    # MISLEADING_CLASSIFICATION — root classified as plain JS/Python
    # but root contains a more specific framework config file
    # (truffle, hardhat, foundry, brownie, rxconfig). Label undersells.
    # Note: stack.signals only carries the four classifier-recognized
    # manifests, so we scan the root directly here for framework files
    # the classifier doesn't track.
    if stack.language in ("javascript", "python") and not stack.parts:
        framework_in_root: Optional[str] = None
        try:
            for entry in repo.iterdir():
                if entry.is_file() and entry.name in _FRAMEWORK_MANIFESTS:
                    framework_in_root = entry.name
                    break
        except OSError:
            pass
        if framework_in_root:
            out.append(FailureRecord(
                failure_type=FAILURE_MISLEADING_CLASSIFICATION,
                severity="medium",
                surface_area="classification",
                description=(
                    f"Classification reads as plain "
                    f"{_lang_label(stack.language)}, but root contains "
                    f"{framework_in_root} ("
                    f"{_FRAMEWORK_MANIFESTS[framework_in_root]}). "
                    f"The label undersells the project's actual stack."
                ),
                detected_in="root",
                example=framework_in_root,
            ))

    # MISSING_FRAMEWORK_DETECTION — any framework manifest is present
    # but adopt doesn't extract the framework name into its label.
    # Differs from MISLEADING_CLASSIFICATION: this fires for SUBDIR
    # framework manifests too, not just root.
    seen_fw_dirs: set[str] = set()
    for u in stack.unclassified_subdirs:
        for m in u.manifest_files:
            if m in _FRAMEWORK_MANIFESTS and u.name not in seen_fw_dirs:
                out.append(FailureRecord(
                    failure_type=FAILURE_MISSING_FRAMEWORK_DETECTION,
                    severity="low",
                    surface_area="classification",
                    description=(
                        f"{u.name}/{m} is a framework manifest "
                        f"({_FRAMEWORK_MANIFESTS[m]}) adopt doesn't "
                        f"yet read. Framework name doesn't appear in "
                        f"BUILD_PLAN's stack section."
                    ),
                    detected_in=u.name,
                    example=f"{u.name}/{m}",
                ))
                seen_fw_dirs.add(u.name)
                break

    # STRUCTURE_UNDERREPRESENTED — classifier produced 0 or 1 parts
    # but ≥3 unclassified subdirs carry real signal. The Detection
    # line significantly understates the project's surface area.
    signal_subdirs = [
        u for u in stack.unclassified_subdirs
        if u.notable_extensions or u.manifest_files
    ]
    if (len(signal_subdirs) >= _STRUCTURE_UNDERREPRESENTED_THRESHOLD
            and len(stack.parts) <= 1):
        out.append(FailureRecord(
            failure_type=FAILURE_STRUCTURE_UNDERREPRESENTED,
            severity="medium",
            surface_area="visibility",
            description=(
                f"{len(signal_subdirs)} subdirs carry real signal "
                f"(manifests or source files), but only "
                f"{len(stack.parts)} appear in the primary "
                f"classification. An AI session reading just the "
                f"Detection line would underestimate the project's "
                f"surface."
            ),
            detected_in="root",
            example="; ".join(
                u.name + "/" for u in signal_subdirs[:3]
            ),
        ))

    # MONOREPO_DEPTH_LIMIT (v0.3) — a workspace-container subdir
    # (apps/, packages/, services/, crates/, members/, workspaces/)
    # contains substantial content but adopt's depth-1 scan can't
    # enter the child projects. example-web3-monorepo, expo-monorepo-example,
    # turborepo-next-django-starter all hit this. See §22.
    #
    # Detection signal: workspace-container name + EITHER
    #   (a) >= MONOREPO_DEPTH_FILE_THRESHOLD source files seen via
    #       the depth-2 walk inside the container, OR
    #   (b) any example-path showing content nested below the
    #       container's immediate root (path with >=2 separators
    #       since example_paths are anchored at the subdir name).
    # The empty-apps/ false-positive guard falls out of (a) and (b)
    # both being false on a directory with no files.
    #
    # Fires once per workspace-container subdir. Since
    # unclassified_subdirs lists each name at most once, no explicit
    # dedup is needed in the loop.
    for u in stack.unclassified_subdirs:
        if u.name not in _WORKSPACE_CONTAINERS:
            continue
        total_signal_files = sum(u.notable_extensions.values())
        has_child_subdir_content = any(
            p.count("/") >= 2 for p in u.example_paths.values()
        )
        if (total_signal_files < _MONOREPO_DEPTH_FILE_THRESHOLD
                and not has_child_subdir_content):
            continue
        # Pick the deepest example path as the representative — the
        # one that most clearly shows the depth-2-or-deeper structure.
        deepest = max(
            u.example_paths.values(),
            key=lambda p: p.count("/"),
            default=f"{u.name}/",
        )
        out.append(FailureRecord(
            failure_type=FAILURE_MONOREPO_DEPTH_LIMIT,
            severity="high",
            surface_area="visibility",
            description=(
                f"{u.name}/ is a workspace container. Child workspaces "
                f"are surfaced (and labeled in the workspace stack "
                f"summary) but not yet part of primary classification."
            ),
            detected_in=u.name,
            example=deepest,
        ))

    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_adopt(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "path", ".") or ".").resolve()
    if not repo.is_dir():
        sys.stderr.write(f"context-kit: not a directory: {repo}\n")
        return 1

    stack = detect_stack(repo)
    # v0.10.x — accept the new CLI flag names (--project-summary
    # / --next-task) AND the legacy attribute names that test
    # namespaces still set (description / next_step). New flags
    # take precedence when both are present.
    desc_override = (
        getattr(args, "project_summary", None)
        or getattr(args, "description", None)
    )
    next_override = (
        getattr(args, "next_task", None)
        or getattr(args, "next_step", None)
    )
    # v0.10.x — --notes is flag-only (never prompted). When
    # absent, the resulting inputs.notes is "" and every
    # downstream renderer omits the notes section entirely.
    notes_override = getattr(args, "notes", None)
    inputs = collect_inputs(
        description=desc_override,
        next_step=next_override,
        notes=notes_override,
    )

    # v0.8 Phase 4.1 — two-pass failure analysis. Pass 1 derives
    # the failures set with an empty plan so the StackReality
    # assessment (which depends on ROOT_SIGNAL_OVERRIDE /
    # MISLEADING_CLASSIFICATION but never on plan content) can be
    # built BEFORE plan_files. Pass 2 re-runs after plan_files so
    # IDEMPOTENCY_RISK (the only plan-dependent detector) surfaces
    # in the final dry-run / HTML output.
    prelim_failures = analyze_failures(repo, stack, [])
    reality = derive_stack_reality(stack, prelim_failures)
    project_type = derive_project_type(stack, reality, prelim_failures)
    # v0.8 Phase 4.3 — IDEMPOTENCY_RISK is plan-dependent, so we
    # need a prelim plan to know whether that rule should fire in
    # suggested_actions. The prelim plan content gets thrown away;
    # only its skip/create/augment kinds matter here.
    prelim_plan = plan_files(repo, stack, inputs, reality=reality,
                             project_type=project_type)
    failures = analyze_failures(repo, stack, prelim_plan)
    suggested = derive_suggested_actions(stack, reality, project_type, failures)
    # v0.8 Phase 4.4 — single Adopt Summary bundles workspace stack
    # pairs + reality + project type + actions into one card that
    # replaces the four standalone Phase 3 / 4.x cards in CLI,
    # HTML, BUILD_PLAN, and CLAUDE.
    summary = derive_adopt_summary(stack, reality, project_type, suggested)
    # v0.10.0 Phase 6.1 — derive the agent launch prompt from the
    # already-built summary. Pure aggregation; lives next to the
    # other derive_*() calls so it ships with the rest of the
    # decision layer.
    agent_prompt = derive_agent_launch_prompt(stack, reality,
                                              project_type, summary,
                                              inputs=inputs)
    # Final plan with summary + agent prompt threaded into the
    # persisted docs.
    plan = plan_files(repo, stack, inputs, reality=reality,
                      project_type=project_type, actions=suggested,
                      summary=summary, agent_prompt=agent_prompt)

    write = bool(getattr(args, "write", False))
    actions = apply_plan(plan, dry_run=not write)

    print(f"context-kit adopt — {'WRITE' if write else 'DRY RUN'}")
    print(f"target: {repo}")
    print()
    print(f"Detected stack: {_stack_summary(stack)}")
    if stack.notes:
        for note in stack.notes:
            print(f"  note: {note}")
    # v0.8 Phase 4.4 — single Adopt Summary block replaces the
    # standalone Phase 3 / 4.1 / 4.2 / 4.3 prints. Same content,
    # one read-once section.
    for line in _adopt_summary_block_dryrun(summary):
        print(line)
    # v0.10.0 Phase 6.1 — Agent launch prompt directly under the
    # Adopt Summary block. Delimited so the user (or a tool) can
    # extract the prompt cleanly.
    for line in _agent_launch_prompt_block_dryrun(agent_prompt):
        print(line)
    # v0.2: visibility-first. Surface unclassified subdirs between the
    # stack line and the plan so the user reads them before scanning
    # the file list. Silent when there's nothing to surface.
    for line in _unknown_present_block_dryrun(stack):
        print(line)
    # v0.8: workspace children (depth-2). Compact one-line-per-child
    # summary; silent when no workspace_children present.
    for line in _workspace_children_block_dryrun(stack):
        print(line)
    print()
    print("Plan:")
    for line in actions:
        print(line)
    # v0.2.x: compact failure summary at the end of the dry-run.
    # Pure metadata — additive, not a behavior change. Silent when
    # no failures detected. Detail lives in --html.
    if failures:
        print()
        print(f"Diagnostic signals ({len(failures)}):")
        print("  Signals from adopt's internal failure taxonomy. "
              "These help explain classification")
        print("  limits and review priorities; they do not mean the "
              "project is broken.")
        # Stable order: high severity first, then by failure_type.
        ordered = sorted(failures, key=lambda f: (
            {"high": 0, "medium": 1, "low": 2}.get(f.severity, 3),
            f.failure_type, f.detected_in,
        ))
        for f in ordered:
            print(
                f"  {f.severity:<6} {f.failure_type:<34} "
                f"{f.detected_in}  ({f.example})"
            )
    print()
    if not write:
        print("Re-run with --write to apply this plan.")
    else:
        # v0.10.x — make the Agent Launch Prompt the canonical
        # post-write next step. The full prompt was already
        # printed above (between Adopt Summary and Plan); this
        # footer points the user back to it AND tells them the
        # same prompt is also persisted in 00-START-NEXT-SESSION.md
        # for later reference.
        print("Done. Generated docs are in place.")
        print()
        print("Next step: paste the Agent Launch Prompt above into "
              "your AI coding agent")
        print("(Claude Code, Cursor, Aider, etc.). The same prompt "
              "is saved in")
        print("00-START-NEXT-SESSION.md under 'Agent Launch Prompt' "
              "for later reference.")
        print()
        print("Placeholders like [adopt: please describe] mark "
              "context the user hasn't")
        print("filled in yet — they don't block read-only "
              "inspection. Fill them in")
        print("before relying on derived guidance for "
              "code-changing decisions.")

    # ---- §21: --html static review report (purely additive) ----
    # The CLI dry-run output above is byte-identical with or without
    # --html. Generation happens after, never displaces or modifies
    # the existing flow.
    html_requested = bool(getattr(args, "html", False)) or bool(getattr(args, "html_out", None))
    if html_requested:
        explicit_out = getattr(args, "html_out", None)
        out_path = Path(explicit_out) if explicit_out else _default_html_path(repo)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                render_adopt_html(repo, stack, inputs, plan,
                                  write_mode=write, failures=failures,
                                  reality=reality,
                                  project_type=project_type,
                                  actions=suggested,
                                  summary=summary,
                                  agent_prompt=agent_prompt),
                encoding="utf-8",
            )
        except OSError as exc:
            sys.stderr.write(f"context-kit: failed to write HTML report: {exc}\n")
            # Don't fail the whole run — the CLI output already succeeded.
            return 0
        print()
        print(f"HTML report: {out_path}")
        if not getattr(args, "no_browser", False):
            try:
                webbrowser.open(out_path.as_uri())
            except Exception:  # noqa: BLE001 — browser open is best-effort
                pass
    return 0
