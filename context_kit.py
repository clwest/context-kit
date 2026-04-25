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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        starter_root = REPO_ROOT / "starter"
        if not starter_root.exists():
            sys.stderr.write(
                "error: `init` requires the context-kit source repo "
                "(starter/ not found next to context_kit.py).\n"
                "You appear to be running context-kit from inside a generated "
                "project. To create a new project, run `init` from the "
                "context-kit source repo instead.\n"
            )
            return 2
        # Imported lazily so generated projects (which ship only server.py)
        # don't crash on `context_kit.py start`.
        from cli.bootstrap import run_init
        return run_init(args)

    if args.command == "start":
        from cli.server import run_start
        return run_start(args)

    if args.command == "orient":
        from cli.orient import run_orient
        return run_orient(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
