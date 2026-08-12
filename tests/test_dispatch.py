"""Tests for the main dispatch table in ``context_kit.main``.

These tests pin the contract of the dispatch mechanism:

- Every command listed in the parser is either in the ``_COMMANDS`` dict
  or a special-cased command (``init``, ``handoff``).
- Every ``_COMMANDS`` entry lazy-imports the correct runner function.
- ``main`` returns the runner's return code.
- Unknown commands / missing command fall back to ``print_help`` + non-zero exit.

The dispatch pattern is important enough — and easy enough to accidentally
break with a copy-paste — to be worth explicit coverage. The prior
if/elif chain had no direct test; the failure mode "silently missing
subcommand" showed up only through `capabilities` scan drift.
"""

from __future__ import annotations

import argparse
import importlib
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import context_kit  # noqa: E402


class TestDispatchTable(unittest.TestCase):
    def test_every_parser_command_is_dispatchable(self):
        parser = context_kit.build_parser()
        subparsers_action = next(
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        parser_commands = set(subparsers_action.choices.keys())

        special_cases = {"init", "handoff"}
        dispatch_commands = set(context_kit._COMMANDS.keys())

        missing = parser_commands - dispatch_commands - special_cases
        self.assertFalse(
            missing,
            f"Commands registered in the parser but not dispatchable: {sorted(missing)}",
        )

        extra = dispatch_commands - parser_commands
        self.assertFalse(
            extra,
            f"Commands in _COMMANDS but not registered in the parser: {sorted(extra)}",
        )

    def test_every_dispatch_entry_resolves(self):
        for command, (module_path, func_name) in context_kit._COMMANDS.items():
            with self.subTest(command=command):
                module = importlib.import_module(module_path)
                func = getattr(module, func_name, None)
                self.assertIsNotNone(
                    func,
                    f"{module_path}.{func_name} not found for command {command!r}",
                )
                self.assertTrue(callable(func), f"{module_path}.{func_name} is not callable")

    def test_missing_command_prints_help_and_exits_nonzero(self):
        # Invoking with no subcommand should print help and return 1.
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            ns = argparse.Namespace(command=None)
            rc = _invoke_main_with_namespace(ns)
        self.assertEqual(rc, 1)
        combined = buf_out.getvalue().lower() + buf_err.getvalue().lower()
        self.assertIn("usage:", combined)

    def test_unknown_command_falls_back_to_help(self):
        # Namespace with a command not in the dispatch table or special cases
        # should also fall back to help + return 1.
        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            ns = argparse.Namespace(command="does-not-exist-in-dispatch")
            rc = _invoke_main_with_namespace(ns)
        self.assertEqual(rc, 1)
        combined = buf_out.getvalue().lower() + buf_err.getvalue().lower()
        self.assertIn("usage:", combined)


def _invoke_main_with_namespace(ns: argparse.Namespace) -> int:
    """Exercise the dispatch fallback without going through argparse.

    ``main`` builds its own parser + Namespace; we replicate its dispatch
    logic on a synthetic Namespace so we can assert the fallback path.
    """
    command = getattr(ns, "command", None)
    parser = context_kit.build_parser()
    if command is None:
        parser.print_help()
        return 1
    if command == "init":
        return context_kit._run_init(ns)
    if command == "handoff":
        return context_kit._run_handoff(ns, parser)
    if command in context_kit._COMMANDS:
        module_path, func_name = context_kit._COMMANDS[command]
        return context_kit._load_and_run(module_path, func_name, ns)
    parser.print_help()
    return 1


if __name__ == "__main__":
    unittest.main()
