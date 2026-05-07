#!/usr/bin/env python3
"""context-kit — scaffold AI-friendly project context infrastructure.

Usage:
    python3 context_kit.py init "My App"          # scaffold a new project
    python3 context_kit.py start                   # launch onboarding server

Run ``python3 context_kit.py <command> --help`` for per-command options.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

# Make the `cli` package importable regardless of how this file is invoked.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-kit",
        description=(
            "context-kit scaffolds and runs the context infrastructure AI "
            "projects need: a narrative anchor, a runtime-derived inventory, "
            "drift detection, session handoffs, and collaboration conventions."
        ),
        epilog="See docs/docs-pattern/ inside any generated project for the full guide.",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # init
    init = sub.add_parser(
        "init",
        help="Scaffold a new project with the context-kit pattern",
        description=(
            "Create a new project with the context-kit pattern in place: "
            "starter docs, teaching material, and optional Python scaffold."
        ),
    )
    init.add_argument("name", help='App name, e.g. "My App" or "my-app"')
    init.add_argument(
        "--target",
        default=None,
        help="Target directory (default: ./<slug-of-name>)",
    )
    init.add_argument(
        "--with-scaffold",
        action="store_true",
        help="Include the optional Python scaffold (verifier, index builder).",
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files at the target.",
    )
    init.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file output.",
    )

    # start
    start = sub.add_parser(
        "start",
        help="Launch the onboarding server for the current project",
        description=(
            "Launch a small localhost server that shows first-session "
            "onboarding for the current project. Run from inside a generated "
            "project directory."
        ),
    )
    start.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    start.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port (default: OS-picked free port)",
    )
    start.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't auto-open the browser.",
    )

    # orient
    orient = sub.add_parser(
        "orient",
        help="Print the assembled session-start orientation report",
        description=(
            "Assemble the current project's authoritative session-start "
            "context into a single plain-text report: the start-here doc, "
            "the two-doc anchor, the latest handoff, and pointers to the "
            "pattern guide. This is what the context-kit Claude skill calls."
        ),
    )
    orient.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    orient.add_argument(
        "--short",
        action="store_true",
        help=(
            "Print a compact summary instead of the full report. "
            "Useful for repeated re-orientation mid-session: source-of-truth "
            "order, session-start doc (if present), latest handoff, "
            "next-task pointer, and a doctor warning summary — no anchor "
            "previews."
        ),
    )

    # chat
    chat = sub.add_parser(
        "chat",
        help="Send the current orient prompt to local Ollama or start a REPL",
        description=(
            "Assemble the current project's context-kit orient prompt, send it "
            "to a local Ollama model, and either print a one-shot response or "
            "keep an interactive REPL open. Uses the existing session-start "
            "orientation as the system message."
        ),
    )
    chat.add_argument(
        "prompt",
        nargs="*",
        help="Prompt text to send. If omitted in a terminal, starts interactive chat; if piped, reads stdin once.",
    )
    chat.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    chat.add_argument(
        "--model",
        default=None,
        help="Ollama model name (default: OLLAMA_MODEL env var or llama3)",
    )
    chat.add_argument(
        "--user",
        default=None,
        metavar="NAME",
        help="Apply persona-aware startup framing from TRANSLATION_LAYER.md when available.",
    )
    chat.add_argument(
        "--include-inspect",
        action="store_true",
        help="Append machine-derived inspect output to the system message",
    )
    chat.add_argument(
        "--include-capabilities",
        action="store_true",
        help="Append deterministic capability summary to the system message",
    )
    chat.add_argument(
        "--include-doctor",
        action="store_true",
        help="Append a startup snapshot of `context-kit doctor` output to the system message",
    )
    chat.add_argument(
        "--include-hotpath",
        action="store_true",
        help="Append a startup snapshot of `context-kit hotpath` output to the system message",
    )
    chat.add_argument(
        "--include-behavior",
        action="store_true",
        help="Append a startup snapshot of `context-kit behavior` output to the system message",
    )
    chat.add_argument(
        "--capabilities-format",
        default="shortlist",
        choices=["full", "compact", "shortlist"],
        help="Capability summary format injected into chat (default: shortlist)",
    )
    chat.add_argument(
        "--debug-prompt",
        action="store_true",
        help="Print the resolved system prompt details before contacting Ollama",
    )
    chat.add_argument(
        "--prompt-soft-threshold",
        type=int,
        default=20000,
        help="Warn when the assembled system prompt exceeds this many characters (default: 20000)",
    )
    chat.add_argument(
        "--no-prime",
        action="store_true",
        help="Disable the initial grounding exchange before interactive chat",
    )
    chat.add_argument(
        "--no-task-wrapper",
        action="store_true",
        help="Send raw user text without the per-turn task wrapper",
    )
    chat.add_argument(
        "--no-auto-context",
        action="store_true",
        help="Disable deterministic query routing for optional context blocks",
    )
    chat.add_argument(
        "--planner-mode",
        action="store_true",
        help="Use a minimal command-planner prompt for human-in-the-loop repo inspection",
    )
    chat.add_argument(
        "--planner-prefer-git",
        action="store_true",
        help="Prefer git commands over context-kit commands in planner mode",
    )

    # hotpath
    hotpath = sub.add_parser(
        "hotpath",
        help="Show the largest files most likely to dominate AI context",
        description=(
            "Read-only file-size dashboard. Prefers git-tracked files when "
            "in a git repo; falls back to a recursive walk. Always exits 0 "
            "— warnings are advisory and meant for the agent (or human) to "
            "decide whether to start a fresh session, narrow focus, or "
            "split a large file."
        ),
    )
    hotpath.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    hotpath.add_argument(
        "--single-threshold-kb",
        type=int,
        default=50,
        help="Warn on any single file larger than this many KB (default: 50)",
    )
    hotpath.add_argument(
        "--top-count",
        type=int,
        default=10,
        help="How many of the largest files to list (default: 10)",
    )
    hotpath.add_argument(
        "--top-threshold-kb",
        type=int,
        default=200,
        help="Warn when the top-N sum exceeds this many KB (default: 200)",
    )

    # inventory
    inventory = sub.add_parser(
        "inventory",
        help="Generate a runtime-derived inventory of the project",
        description=(
            "Generate runtime-derived inventory facts (CLI subcommands, "
            "guide docs, templates, tests, package metadata, hot-path "
            "summary, etc.) and update only the managed block inside "
            "docs/CONTEXT_KIT_INVENTORY.md. Three modes: --write updates "
            "the file, --check exits 0 only if the block is current, "
            "--json prints machine-readable output."
        ),
    )
    inventory.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    inventory_mode = inventory.add_mutually_exclusive_group()
    inventory_mode.add_argument(
        "--write",
        action="store_true",
        help="Update the managed block in docs/CONTEXT_KIT_INVENTORY.md",
    )
    inventory_mode.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 only if the managed block is current; 1 if stale",
    )
    inventory_mode.add_argument(
        "--json",
        action="store_true",
        help="Print the inventory as JSON to stdout (no file changes)",
    )

    # seed
    seed = sub.add_parser(
        "seed",
        help="Turn a structured idea file into project context (5 files)",
        description=(
            "Read a markdown idea file (see docs/docs-pattern/IDEA_SCHEMA.md "
            "for the format) and populate the project's narrative anchor, "
            "start-here doc, bootstrap handoff, product topic, and "
            "BUILD_PLAN.md. Deterministic; no LLM. Managed-block markers "
            "(<!-- context-kit:seed:start --> / :end -->) keep human "
            "content outside them safe across re-runs."
        ),
    )
    seed.add_argument(
        "idea",
        help="Path to the markdown idea file (e.g. ./idea.md)",
    )
    seed.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    seed.add_argument(
        "--force",
        action="store_true",
        help="Overwrite seed-owned content even when it would otherwise be skipped",
    )
    seed.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Print what would change; don't write any files",
    )

    # doctor
    doctor = sub.add_parser(
        "doctor",
        help="Read-only environment + setup diagnostics",
        description=(
            "Run a fixed set of read-only checks: Python version, git, "
            "context-kit project structure, Node.js, Expo SDK + config, "
            "file-watcher / ulimit pressure, and inventory freshness. "
            "Exits 1 only if a blocking issue is found; warnings never "
            "affect the exit code."
        ),
    )
    doctor.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )

    # recommend-stack
    rec = sub.add_parser(
        "recommend-stack",
        help="Suggest a beginner-friendly stack from a structured idea file",
        description=(
            "Read a markdown idea file and recommend a v0 stack — opinionated, "
            "deterministic, no LLM. Always exits 0; this is advisory. "
            "When `seed` runs and the idea file has no `## Tech stack` section, "
            "seed calls into this same engine to populate BUILD_PLAN.md."
        ),
    )
    rec.add_argument(
        "idea",
        help="Path to the markdown idea file (e.g. ./idea.md)",
    )
    rec.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )

    # adopt (v0)
    adopt = sub.add_parser(
        "adopt",
        help="Retrofit context-kit docs onto an existing project (v0)",
        description=(
            "Detect basic stack (JavaScript / Python / unknown) from "
            "manifest files, ask two questions, and generate the "
            "load-bearing docs (BUILD_PLAN.md, *_WHAT_IT_IS.md, "
            "00-START-NEXT-SESSION.md, plus a CLAUDE.md augmentation). "
            "Source code is never modified. Dry-run by default; "
            "pass --write to actually create files."
        ),
    )
    adopt.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root (default: current working directory)",
    )
    adopt.add_argument(
        "--write",
        action="store_true",
        help="Apply the plan; without this, adopt prints what would happen",
    )
    adopt.add_argument(
        "--html",
        action="store_true",
        help=(
            "Also generate a static HTML review report (single file, no "
            "server). Default destination is /tmp; pass --html-out PATH to "
            "override. Auto-opens in the browser unless --no-browser is set."
        ),
    )
    adopt.add_argument(
        "--html-out",
        dest="html_out",
        default=None,
        metavar="PATH",
        help=(
            "Explicit destination for the HTML report (implies --html). "
            "Default keeps the source tree untouched by writing to /tmp."
        ),
    )
    adopt.add_argument(
        "--no-browser",
        dest="no_browser",
        action="store_true",
        help="Don't auto-open the HTML report in the browser (tests / headless / CI).",
    )
    adopt.add_argument(
        "--project-summary",
        dest="project_summary",
        default=None,
        metavar="TEXT",
        help=(
            "One-sentence project summary. If passed, adopt does not "
            "prompt for 'In one sentence, what is this project?'. The "
            "value is reused everywhere the project description is "
            "needed (BUILD_PLAN, PROJECT_WHAT_IT_IS, CLAUDE.md, "
            "Agent Launch Prompt)."
        ),
    )
    adopt.add_argument(
        "--next-task",
        dest="next_task",
        default=None,
        metavar="TEXT",
        help=(
            "What the next AI session should help with. If passed, "
            "adopt does not prompt for 'What should the next AI "
            "session help with?'. Reused in BUILD_PLAN, "
            "00-START-NEXT-SESSION.md, the Agent Launch Prompt, and "
            "the CLI / HTML preview."
        ),
    )
    adopt.add_argument(
        "--notes",
        dest="notes",
        default=None,
        metavar="TEXT",
        help=(
            "Discovered notes / context from a prior dry-run or "
            "inspection pass. Flag-only (never prompted). When "
            "provided, the notes are preserved verbatim under a "
            "'DISCOVERED NOTES / CONTEXT' section in the Agent "
            "Launch Prompt and a 'Discovered notes' section in "
            "BUILD_PLAN.md, 00-START-NEXT-SESSION.md, and the "
            "CLAUDE.md managed block — so refining "
            "--project-summary on a later --write pass doesn't "
            "lose findings from earlier inspection. Multi-line "
            "notes preserve line breaks."
        ),
    )

    # audit
    audit = sub.add_parser(
        "audit",
        help="Print a structured audit prompt for an AI agent",
        description=(
            "Print a predefined prompt that instructs an AI to perform a "
            "deep audit of this repository: stale docs, duplicated logic, "
            "dead code, risky areas, runtime/doc inconsistencies — with "
            "P0/P1/P2 prioritization and a phased cleanup plan. With "
            "--write, also scaffold docs/audit/AUDIT_V1.md and "
            "docs/audit/CLEANUP_PLAN.md (never overwriting existing files)."
        ),
    )
    audit.add_argument(
        "--write",
        action="store_true",
        help="Scaffold docs/audit/ with empty AUDIT_V1.md + CLEANUP_PLAN.md",
    )

    # audit-response
    audit_response = sub.add_parser(
        "audit-response",
        help="Heuristically audit a chat response against the current orientation",
        description=(
            "Read a saved chat response, compare its claim-like sentences to "
            "the current project orientation, and emit a markdown groundedness "
            "audit. First version is a structured manual scaffold, not an LLM."
        ),
    )
    audit_response.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    audit_response.add_argument(
        "--input",
        required=True,
        help="Path to the saved model response text file",
    )
    audit_response.add_argument(
        "--output",
        default=None,
        help="Optional path to write the markdown audit report",
    )

    # fix
    fix = sub.add_parser(
        "fix",
        help="Print the phased cleanup plan from docs/audit/ as actionable steps",
        description=(
            "Read docs/audit/AUDIT_V1.md + docs/audit/CLEANUP_PLAN.md and "
            "print the phased cleanup plan as an execution-ready outline. "
            "Read-only: never modifies files, never invokes an AI, never "
            "executes any printed step. Exits 1 if the workspace isn't "
            "initialized or still carries scaffold placeholders."
        ),
    )
    fix_mode = fix.add_mutually_exclusive_group()
    fix_mode.add_argument(
        "--phase",
        type=int,
        metavar="N",
        help="Print only phase N",
    )
    fix_mode.add_argument(
        "--next",
        dest="next_step",
        action="store_true",
        help="Print only the next step (first bullet of the first phase with steps)",
    )

    # inspect
    inspect = sub.add_parser(
        "inspect",
        help="Print a deterministic markdown system map for any repo",
        description=(
            "Read an arbitrary repo and print machine-derived facts as a "
            "markdown report: project identity, detected stack, commands, "
            "file-tree summary, route and model hints, environment hints, "
            "context-kit docs status, and warnings/unknowns. Read-only by "
            "contract: never modifies files, never invokes an AI, never "
            "executes project code."
        ),
    )
    inspect.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Project root to inspect (default: current working directory)",
    )
    inspect.add_argument(
        "--project",
        default=None,
        help="Project root to inspect (default: current working directory)",
    )
    inspect.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )
    inspect.add_argument(
        "--format",
        default="markdown",
        choices=["markdown"],
        help="Output format (markdown only in v1)",
    )
    inspect.add_argument(
        "--output",
        default=None,
        help="Optional path to write the markdown report",
    )
    inspect.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Directory walk depth for monorepo / workspace child detection (default: 2)",
    )
    inspect.add_argument(
        "--scope",
        help="Restrict inspection to a named scope (core, celery, agents, spiders, docs-rag, frontend, deployment, tests)",
    )
    inspect.add_argument(
        "--include-history",
        action="store_true",
        help="Include historical/external docs in scoped inspection",
    )
    inspect.add_argument(
        "--include-related",
        action="store_true",
        help="Include broader related paths for the selected scope",
    )

    # capabilities
    capabilities = sub.add_parser(
        "capabilities",
        help="Generate a deterministic capability summary from inspect facts",
        description=(
            "Generate a markdown capability summary directly from inspect's "
            "structured implementation facts. No LLM is used."
        ),
    )
    capabilities.add_argument(
        "--project",
        default=None,
        help="Project root to inspect (default: current working directory)",
    )
    capabilities.add_argument(
        "--output",
        default=None,
        help="Write the markdown summary to this file as well as stdout",
    )
    capabilities.add_argument(
        "--format",
        default="full",
        choices=["full", "compact", "shortlist"],
        help="Output format (default: full)",
    )
    capabilities.add_argument(
        "--scope",
        default=None,
        help="Restrict capability extraction to a named inspect scope (core, celery, agents, spiders, docs-rag, frontend, deployment, tests)",
    )
    capabilities.add_argument(
        "--include-history",
        action="store_true",
        help="Include historical/external docs in scoped inspection",
    )
    capabilities.add_argument(
        "--include-related",
        action="store_true",
        help="Include broader related paths for the selected scope",
    )
    capabilities.add_argument(
        "--include-tests",
        action="store_true",
        help="Include test/fixture evidence and label it as non-implementation",
    )
    capabilities.add_argument(
        "--include-detectors",
        action="store_true",
        help="Include detector/self-analysis evidence and label it as non-project implementation",
    )

    # coverage
    coverage = sub.add_parser(
        "coverage",
        help="Map which tracked files are covered, skipped, or still unclassified",
        description=(
            "Walk tracked files and classify them into runtime/source, "
            "docs-active, docs-historical, tests, generated/artifact, "
            "config/deployment, or unknown. This is a coverage map, not a "
            "correctness proof. Read-only by default."
        ),
    )
    coverage.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to inspect (default: current working directory)",
    )
    coverage.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )
    coverage.add_argument(
        "--scope",
        help="Restrict coverage to a named inspect scope (core, celery, agents, spiders, docs-rag, frontend, deployment, tests)",
    )

    # behavior
    behavior = sub.add_parser(
        "behavior",
        help="Map behavioral risk surfaces in tracked files",
        description=(
            "Walk tracked files and identify files that look behaviorally risky "
            "using simple text probes: orchestration files, task/scheduler "
            "entrypoints, registries, dynamic imports, dispatch/router code, "
            "database writes, API calls, filesystem writes, subprocess/shell "
            "execution, broad exception swallowing, and TODO/FIXME markers. "
            "Read-only by default; this is a risk map, not proof."
        ),
    )
    behavior.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to inspect (default: current working directory)",
    )
    behavior.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )
    behavior.add_argument(
        "--scope",
        help="Restrict behavior scanning to a named inspect scope (core, celery, agents, spiders, docs-rag)",
    )

    # connections
    connections = sub.add_parser(
        "connections",
        help="Audit wiring between backend routes, frontend/mobile clients, tasks, agents, and spiders",
        description=(
            "Walk tracked files and look for connection surfaces: Django urls.py "
            "routes, DRF views/viewsets, serializers, frontend/mobile API calls, "
            "Celery task references, management commands, agent maps, and spider "
            "registries. This is a wiring audit, not a correctness proof."
        ),
    )
    connections.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to inspect (default: current working directory)",
    )
    connections.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )
    connections.add_argument(
        "--scope",
        help="Restrict connection scanning to a named subsystem (backend, frontend, mobile, agents, spiders, celery)",
    )

    # verify
    verify = sub.add_parser(
        "verify",
        help="Check whether key repo claims are verified, doc-only, conflicting, or unknown",
        description=(
            "Read docs plus code/config files and produce a deterministic "
            "verification report for a small set of high-value claims: "
            "Django settings module ownership, Celery beat schedule "
            "ownership, tracked generated artifacts, and common count "
            "claims in docs. Read-only by default; --write stores the "
            "report in docs/verification/VERIFY_REPORT.md."
        ),
    )
    verify.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root to verify (default: current working directory)",
    )
    verify.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON to stdout",
    )
    verify.add_argument(
        "--include-archive",
        action="store_true",
        help="Include archive and historical docs in primary scoring",
    )
    verify.add_argument(
        "--all-docs",
        action="store_true",
        help="Scan all active docs for count claims instead of canonical docs only",
    )
    verify.add_argument(
        "--write",
        action="store_true",
        help="Write or refresh docs/verification/VERIFY_REPORT.md",
    )

    # exec
    exec_cmd = sub.add_parser(
        "exec",
        help="Render docs/audit/CLEANUP_PLAN.md as an execution-ready AI prompt",
        description=(
            "Read docs/audit/AUDIT_V1.md + docs/audit/CLEANUP_PLAN.md and "
            "print a structured execution prompt (Goal / Context / "
            "Instructions / Phase tasks / Constraints / Output expectations) "
            "that an AI agent can run against. Read-only: never modifies "
            "files, never invokes an AI, never executes any printed step. "
            "Exits 1 if the workspace isn't initialized or still carries "
            "scaffold placeholders."
        ),
    )
    exec_mode = exec_cmd.add_mutually_exclusive_group()
    exec_mode.add_argument(
        "--phase",
        type=int,
        metavar="N",
        help="Print prompt for phase N only",
    )
    exec_mode.add_argument(
        "--next",
        dest="next_step",
        action="store_true",
        help="Print prompt for the next single step only",
    )

    # translation-init
    translation_init = sub.add_parser(
        "translation-init",
        help="Print a structured prompt for an AI to populate the project's TRANSLATION_LAYER doc",
        description=(
            "Print a predefined prompt that instructs an AI agent to read "
            "the project's source-of-truth (WHAT_IT_IS / INVENTORY / "
            "PIPELINE / BEHAVIOR_LAYER / latest handoff), interview the "
            "user about real audiences, write a populated "
            "docs/<APP>_TRANSLATION_LAYER.md, verify nothing was invented, "
            "and switch into the named persona's mode for the rest of the "
            "session. Read-only by contract: never modifies files, never "
            "invokes an AI, never overwrites a hand-edited translation "
            "layer doc."
        ),
    )
    del translation_init  # parser registration is the side effect

    # codex
    codex = sub.add_parser(
        "codex",
        help="Prepare and launch the Codex startup flow",
        description=(
            "Prepare the same startup prompt as start-codex, ensure the "
            "verification scaffold exists, and best-effort launch Codex "
            "or provide paste-ready output."
        ),
    )
    codex.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    codex.add_argument(
        "--user",
        default=None,
        metavar="NAME",
        help="Apply persona-aware startup framing from TRANSLATION_LAYER.md when available.",
    )
    codex.add_argument(
        "--mode",
        choices=("design", "execute"),
        default="design",
        help="Startup prompt mode (default: design).",
    )
    codex.add_argument(
        "--model",
        choices=("cheap", "heavy"),
        default=None,
        help="Add a prompt-only model hint; does not invoke or configure an API model.",
    )
    codex.add_argument(
        "--short",
        action="store_true",
        help="Print the compact startup prompt instead of the full prompt.",
    )
    codex.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print the generated startup prompt before launching Codex.",
    )
    codex_mode = codex.add_mutually_exclusive_group()
    codex_mode.add_argument(
        "--interactive",
        action="store_true",
        help="Launch Codex interactively and paste the copied startup prompt manually.",
    )
    codex_mode.add_argument(
        "--exec",
        dest="exec",
        action="store_true",
        help="Run a one-shot Codex exec session with the startup prompt.",
    )

    # start-codex
    start_codex = sub.add_parser(
        "start-codex",
        help="Print a ready-to-copy Codex startup prompt for this project",
        description=(
            "Read current runtime state, doctor warnings, latest handoff, "
            "and the next task from 00-START-NEXT-SESSION.md, then print "
            "a deterministic startup prompt for Codex. Read-only: never "
            "modifies files and never invokes an AI."
        ),
    )
    start_codex.add_argument(
        "--project",
        default=None,
        help="Project root (default: current working directory)",
    )
    start_codex.add_argument(
        "--user",
        default=None,
        metavar="NAME",
        help="Apply persona-aware startup framing from TRANSLATION_LAYER.md when available.",
    )
    start_codex.add_argument(
        "--mode",
        choices=("design", "execute"),
        default="design",
        help="Startup prompt mode (default: design).",
    )
    start_codex.add_argument(
        "--model",
        choices=("cheap", "heavy"),
        default=None,
        help="Add a prompt-only model hint; does not invoke or configure an API model.",
    )
    start_codex.add_argument(
        "--short",
        action="store_true",
        help="Print the compact startup prompt instead of the full prompt.",
    )

    # refactor (group)
    from cli.refactor import add_subparser as _add_refactor_subparser
    _add_refactor_subparser(sub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        # Imported lazily so generated projects — which ship only the
        # subset of cli/ in RUNTIME_COPY — don't crash on the other
        # subcommands. If bootstrap is unavailable, the user is most
        # likely running this from inside a generated project; tell
        # them where to go.
        try:
            from cli.bootstrap import run_init
        except ImportError:
            sys.stderr.write(
                "error: `init` is not available in this context.\n"
                "You appear to be running context-kit from inside a generated "
                "project, which only ships the runtime subcommands. To create "
                "a new project, install the full package (`pip install contextkit-ai`) "
                "and run `context-kit init` from anywhere.\n"
            )
            return 2
        return run_init(args)

    if args.command == "start":
        from cli.server import run_start
        return run_start(args)

    if args.command == "orient":
        from cli.orient import run_orient
        return run_orient(args)

    if args.command == "chat":
        from cli.chat import run_chat
        return run_chat(args)

    if args.command == "hotpath":
        from cli.hotpath import run_hotpath
        return run_hotpath(args)

    if args.command == "inventory":
        from cli.inventory import run_inventory
        return run_inventory(args)

    if args.command == "seed":
        from cli.seed import run_seed
        return run_seed(args)

    if args.command == "doctor":
        from cli.doctor import run_doctor
        return run_doctor(args)

    if args.command == "recommend-stack":
        from cli.recommend_stack import run_recommend_stack
        return run_recommend_stack(args)

    if args.command == "adopt":
        from cli.adopt import run_adopt
        return run_adopt(args)

    if args.command == "audit":
        from cli.audit import run_audit
        return run_audit(args)

    if args.command == "audit-response":
        from cli.audit_response import run_audit_response
        return run_audit_response(args)

    if args.command == "fix":
        from cli.fix import run_fix
        return run_fix(args)

    if args.command == "exec":
        from cli.exec import run_exec
        return run_exec(args)

    if args.command == "inspect":
        from cli.inspect import run_inspect
        return run_inspect(args)

    if args.command == "capabilities":
        from cli.capabilities import run_capabilities
        return run_capabilities(args)

    if args.command == "coverage":
        from cli.coverage import run_coverage
        return run_coverage(args)

    if args.command == "behavior":
        from cli.behavior import run_behavior
        return run_behavior(args)

    if args.command == "connections":
        from cli.connections import run_connections
        return run_connections(args)

    if args.command == "verify":
        from cli.verify import run_verify
        return run_verify(args)

    if args.command == "codex":
        from cli.start_codex import run_codex
        return run_codex(args)

    if args.command == "refactor":
        from cli.refactor import run_refactor
        return run_refactor(args)

    if args.command == "translation-init":
        from cli.translation_init import run_translation_init
        return run_translation_init(args)

    if args.command == "start-codex":
        from cli.start_codex import run_start_codex
        return run_start_codex(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
