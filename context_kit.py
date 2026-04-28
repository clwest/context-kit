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
    sub.add_parser(
        "audit",
        help="Print a structured audit prompt for an AI agent",
        description=(
            "Print a predefined prompt that instructs an AI to perform a "
            "deep audit of this repository: stale docs, duplicated logic, "
            "dead code, risky areas, runtime/doc inconsistencies — with "
            "P0/P1/P2 prioritization and a phased cleanup plan. Writes to "
            "stdout only; takes no arguments."
        ),
    )

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

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
