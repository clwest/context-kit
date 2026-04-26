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
      Worth surfacing explicitly (see flow-name-service's empty
      ``api/`` placeholder in SESSION_009_ADOPT.md §19).
    """

    name: str
    manifest_files: list[str] = field(default_factory=list)
    notable_extensions: dict[str, int] = field(default_factory=dict)
    example_paths: dict[str, str] = field(default_factory=dict)
    note: Optional[str] = None
    # True only when the dir literally has zero files (rare — usually
    # an empty placeholder like flow-name-service's ``api/``).
    is_empty: bool = False
    # Total file count seen during the scan (capped at MAX_FILES_PER_SUBDIR).
    # Lets the dry-run distinguish "truly empty" from "has files but
    # none with extensions we recognize" — the second case shows up for
    # dirs full of .json / .md / config files (e.g. dbao-studio's
    # agents/ contains JSON dumps but no .py source).
    total_file_count: int = 0


@dataclass
class AdoptionInputs:
    """The two answers we collect from the user."""

    project_description: str
    next_step: str


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

    ``language`` is "javascript" | "python" | "unknown". ``signals``
    lists the manifest filenames found in ``d`` (for reporting; not
    prefixed with the directory). Mixed JS+Python in the same
    directory still resolves to JavaScript with a multi-stack note
    appended at the call site.
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
    has_js = "package.json" in signals
    has_py = any(s in signals for s in ("manage.py", "requirements.txt", "pyproject.toml"))
    if has_js and has_py:
        return "javascript", signals  # caller decides whether to add a note
    if has_js:
        return "javascript", signals
    if has_py:
        return "python", signals
    return "unknown", signals


def _pick_primary(parts: dict[str, str]) -> str:
    """Backend wins by convention; otherwise first detected in scan order.

    The "backend wins" rule comes from the dogfood split-monorepo
    shape (focus-flow, dealflowtracker, etc.). Backend is where the
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
        # Preserve the v0 "mixed JS+Python at root" honest note.
        if (
            "package.json" in root_signals
            and any(s in root_signals for s in ("manage.py", "requirements.txt", "pyproject.toml"))
        ):
            notes.append(
                "Detected both JavaScript and Python manifests at root. "
                "v0 reports JavaScript and notes Python presence; "
                "multi-stack handling is planned for a later release."
            )
        profile = StackProfile(language=root_lang, signals=root_signals, notes=notes)
        profile.unclassified_subdirs = scan_unclassified_subdirs(repo, set(profile.parts))
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
# examples for dbao-studio, donkey_betz_world, clarity-timelock,
# flow-name-service, and tornado-core.
#
# Per-ecosystem detection is deferred. The data tables below say what
# files *suggest* without committing to what they *are* — a deliberate
# choice to avoid the per-ecosystem-detector treadmill (Solidity, Move,
# Anchor, Cadence, Foundry, Hardhat, Brownie, Truffle, Reflex, Flutter,
# ...). Each ecosystem we'd otherwise need to support is one row in
# DOMAIN_HINTS.

# Skip these in the depth-1 walk. Hidden dirs (anything starting with
# ".") are also skipped at the call site.
NOISE_DIRS = frozenset({
    "node_modules", "__pycache__", "venv", ".venv", "env",
    "dist", "build", "out", "target",
    "coverage", ".coverage", "htmlcov",
    ".git", ".idea", ".vscode", ".cache", ".next", ".nuxt", ".turbo",
    "media",  # static media uploads — no source code worth surfacing
})

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
            dirs[:] = [x for x in dirs if x not in NOISE_DIRS and not x.startswith(".")]
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
        if name in NOISE_DIRS:
            continue
        if name in already_classified:
            continue
        manifests, ext_counts, examples, total_files = _scan_subdir_contents(entry)
        out.append(_build_unclassified(name, manifests, ext_counts, examples, total_files))
    return out


# ---------------------------------------------------------------------------
# Layer 2: generators (pure transforms)
# ---------------------------------------------------------------------------


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _lang_label(lang: str) -> str:
    if lang == "javascript":
        return "JavaScript / Node.js"
    if lang == "python":
        return "Python"
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
    return lines


def _unknown_present_block_dryrun(stack: StackProfile) -> list[str]:
    """The "Unknown but present" section for the CLI dry-run output.

    Returns an empty list when there's nothing to surface so callers
    don't have to gate on it. The caller is expected to join lines and
    print as a contiguous block.
    """
    if not stack.unclassified_subdirs:
        return []
    out = ["", "Unknown but present (depth 1):"]
    for u in stack.unclassified_subdirs:
        out.extend(_format_unclassified_for_dryrun(u))
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
    return line


def _unknown_present_markdown(stack: StackProfile) -> list[str]:
    """The full "Unknown but present" section for the Markdown docs.

    Returns an empty list when there's nothing to surface so the
    section is silently omitted on clean projects.
    """
    if not stack.unclassified_subdirs:
        return []
    out = [
        "",
        "### Unknown but present",
        "",
        "The following directories exist and contain notable files but",
        "`adopt` does not yet recognize their type. An AI session reading",
        "this should ask the user what these are before writing code that",
        "touches them.",
        "",
    ]
    for u in stack.unclassified_subdirs:
        out.append(_format_unclassified_for_markdown(u))
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


def generate_build_plan(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    """The minimum BUILD_PLAN.md a freshly-adopted project needs.

    The strengthened first prompt (Step 8 of the wizard) tells agents
    to read this file before writing code, so it has to carry real
    signal even in v0.
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
    # v0.2: visibility-first. Only added when there's something
    # unclassified to surface — clean classified projects still get
    # the same compact tech-stack section as v0.1.
    body += _unknown_present_markdown(stack)
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
    return "\n".join(body)


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
    return "\n".join(body)


def generate_start_here(inputs: AdoptionInputs, title: str) -> str:
    body = [
        "---",
        "state: scaffold",
        f"date: {_today()}",
        "---",
        "",
        f"# Next session — {title}",
        "",
        f"> Generated by `context-kit adopt` on {_today()}.",
        "",
        "## What's next",
        "",
        inputs.next_step.strip() or "[adopt: please describe]",
        "",
        "## How to start the session",
        "",
        "1. Read `docs/BUILD_PLAN.md` — confirm the stack matches reality.",
        "2. Read `docs/PROJECT_WHAT_IT_IS.md` (or your project's *_WHAT_IT_IS.md).",
        "3. If you see `[adopt: please describe]` markers, fill them in or ask the user.",
        "4. Then begin the work above.",
        "",
    ]
    return "\n".join(body)


def generate_claude_block(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    """The managed block we append (or insert) into CLAUDE.md.

    Wrapped in markers so re-running ``adopt`` updates these facts in
    place without disturbing surrounding human-written content.
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
    if stack.unclassified_subdirs:
        lines += _unknown_present_markdown(stack)
    lines += [
        "",
        "### What the user told adopt",
        "",
        f"- **What this project is:** {inputs.project_description.strip() or '[adopt: please describe]'}",
        f"- **What's next:** {inputs.next_step.strip() or '[adopt: please describe]'}",
        "",
        "### Rule for this session",
        "",
        "- Always read `docs/BUILD_PLAN.md` before choosing a stack or writing",
        "  code. The detected stack above is the source of truth — do not",
        "  switch frameworks without asking.",
        "",
        END_MARKER,
    ]
    return "\n".join(lines)


def generate_claude_md_fresh(stack: StackProfile, inputs: AdoptionInputs, title: str) -> str:
    """Full CLAUDE.md when none exists yet.

    Mirrors the shape of cli/_starter/root/CLAUDE.md but tighter — we
    don't ship the full template at adopt time because the user hasn't
    seen the docs-pattern yet. They'll get the full thing if they
    later run ``context-kit init . --force``.
    """
    block = generate_claude_block(stack, inputs, title)
    return "\n".join([
        f"# CLAUDE / AGENTS — {title}",
        "",
        f"> Generated by `context-kit adopt` on {_today()}. AI session entry point.",
        "",
        "## Read this first",
        "",
        "1. `docs/BUILD_PLAN.md` — the stack and what NOT to change.",
        "2. `docs/PROJECT_WHAT_IT_IS.md` (or `docs/<slug>_WHAT_IT_IS.md`) — what this is and why.",
        "3. `00-START-NEXT-SESSION.md` — the current session priority.",
        "",
        "If you see `[adopt: please describe]` anywhere, ask the user to fill",
        "it in before writing code that depends on the missing context.",
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
                      write_mode: bool) -> str:
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
        det_label = "Unknown stack"
        det_color = "warn"
    else:
        det_label = _lang_label(stack.language)
        det_color = "ok"
    detection_html = [
        f'<section class="card card-{det_color}">',
        f'  <h2>Detection</h2>',
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

    # ---- Section 4: unknown but present (THE main focus) ----
    unknown_html: list[str] = []
    if stack.unclassified_subdirs:
        unknown_html = [
            '<section class="card card-warn">',
            '  <h2>Unknown but present</h2>',
            '  <p class="meta">Directories adopt found but couldn\'t classify. '
            'Click each to expand. The hint lines are *suggestions* — '
            'verify with what you know about the project.</p>',
        ]
        for u in stack.unclassified_subdirs:
            # One <details> block per subdir. Native collapse, no JS.
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
            summary = " · ".join(summary_bits) if summary_bits else "(no signals)"
            unknown_html.append(
                f'  <details class="unc"><summary>'
                f'<code class="dirname">{_esc(u.name)}/</code> '
                f'<span class="dim">{summary}</span>'
                f'</summary>'
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
            unknown_html.append('    </div>')
            unknown_html.append('  </details>')
        unknown_html.append('</section>')

    # ---- Section 5: plan with previews ----
    plan_html = ['<section class="card">', '  <h2>What adopt would write</h2>']
    verb_prefix = "Will " if write_mode else "Would "
    for p in plan:
        rel_path = str(p.path.relative_to(repo)) if p.path.is_relative_to(repo) else str(p.path)
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
    details.unc summary code.dirname { font-weight: 600; }
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
    out.extend(unknown_html)
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


def plan_files(
    repo: Path,
    stack: StackProfile,
    inputs: AdoptionInputs,
) -> list[PlannedFile]:
    """Build the list of files we'd create or augment, without writing."""
    title = derive_project_title(repo)
    plan: list[PlannedFile] = []

    plan.append(PlannedFile(
        path=repo / "docs" / "BUILD_PLAN.md",
        content=generate_build_plan(stack, inputs, title),
        kind="create",
    ))
    # v0 uses a fixed filename (``PROJECT_WHAT_IT_IS.md``) rather than
    # the slug-based ``<APP>_WHAT_IT_IS.md`` the rest of context-kit
    # uses. Keeps the v0 output predictable and sidesteps the "temp
    # dir name leaks into a docs filename" footgun. The full release
    # can switch to slug-based naming once we add the project-name
    # prompt promised in the design.
    plan.append(PlannedFile(
        path=repo / "docs" / "PROJECT_WHAT_IT_IS.md",
        content=generate_what_it_is(stack, inputs, title),
        kind="create",
    ))
    plan.append(PlannedFile(
        path=repo / "00-START-NEXT-SESSION.md",
        content=generate_start_here(inputs, title),
        kind="create",
    ))

    claude_path = repo / "CLAUDE.md"
    if claude_path.is_file():
        plan.append(PlannedFile(
            path=claude_path,
            content=generate_claude_block(stack, inputs, title),
            kind="augment",
        ))
    else:
        plan.append(PlannedFile(
            path=claude_path,
            content=generate_claude_md_fresh(stack, inputs, title),
            kind="create",
        ))
    return plan


def _augment_claude_md(existing: str, block: str) -> str:
    """Append (or replace) the managed block in CLAUDE.md.

    Preserves all human content outside markers. If the markers
    already exist, we replace what's between them; otherwise we
    append the block to the end of the file.
    """
    if START_MARKER in existing and END_MARKER in existing:
        head, _, rest = existing.partition(START_MARKER)
        _, _, tail = rest.partition(END_MARKER)
        return head.rstrip() + "\n\n" + block + "\n" + tail.lstrip("\n")
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + "\n" + block + "\n"


def apply_plan(plan: list[PlannedFile], dry_run: bool) -> list[str]:
    """Execute the plan; return per-file action verbs ("create"/"augment"/"would create"/"would augment").

    Source code is never touched. Only docs/* and root-level CLAUDE.md /
    00-START-NEXT-SESSION.md are written.
    """
    actions: list[str] = []
    for item in plan:
        verb_prefix = "would " if dry_run else ""
        if item.kind == "augment" and item.path.is_file():
            verb = f"{verb_prefix}augment"
            if not dry_run:
                existing = item.path.read_text(encoding="utf-8")
                merged = _augment_claude_md(existing, item.content)
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
    prompt_fn: Callable[[str], str] = input,
    description: Optional[str] = None,
    next_step: Optional[str] = None,
) -> AdoptionInputs:
    """Ask the two questions. Tests inject ``prompt_fn`` and overrides."""
    if description is None:
        description = prompt_fn("What is this project? ").strip()
    if next_step is None:
        next_step = prompt_fn("What are you trying to do next? ").strip()
    return AdoptionInputs(
        project_description=description,
        next_step=next_step,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_adopt(args: argparse.Namespace) -> int:
    repo = Path(getattr(args, "path", ".") or ".").resolve()
    if not repo.is_dir():
        sys.stderr.write(f"context-kit: not a directory: {repo}\n")
        return 1

    stack = detect_stack(repo)
    inputs = collect_inputs(
        description=getattr(args, "description", None),
        next_step=getattr(args, "next_step", None),
    )
    plan = plan_files(repo, stack, inputs)

    write = bool(getattr(args, "write", False))
    actions = apply_plan(plan, dry_run=not write)

    print(f"context-kit adopt — {'WRITE' if write else 'DRY RUN'}")
    print(f"target: {repo}")
    print()
    print(f"Detected stack: {_stack_summary(stack)}")
    if stack.notes:
        for note in stack.notes:
            print(f"  note: {note}")
    # v0.2: visibility-first. Surface unclassified subdirs between the
    # stack line and the plan so the user reads them before scanning
    # the file list. Silent when there's nothing to surface.
    for line in _unknown_present_block_dryrun(stack):
        print(line)
    print()
    print("Plan:")
    for line in actions:
        print(line)
    print()
    if not write:
        print("Re-run with --write to apply this plan.")
    else:
        print("Done. Review the [adopt: please describe] sections before")
        print("running your AI tool against this project.")

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
                render_adopt_html(repo, stack, inputs, plan, write_mode=write),
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
