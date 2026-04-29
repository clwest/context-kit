"""Tests for the ``cli`` package's ``__version__`` resolution.

The constant is sourced via ``importlib.metadata.version()`` so the
installed-package version is always the single source of truth. But
``cli/__init__.py`` runs at *every* import of any subcommand, including
the CI scenario where the repo is checked out without ``pip install``
— and ``importlib.metadata`` raises ``PackageNotFoundError`` when the
package isn't installed.

These tests lock in the fallback so a future refactor can't quietly
re-break CI for source-only checkouts.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cli  # noqa: E402
from importlib.metadata import PackageNotFoundError  # noqa: E402


class TestCliVersion(unittest.TestCase):
    def test_version_attribute_exists(self):
        self.assertTrue(hasattr(cli, "__version__"))

    def test_version_is_non_empty_string(self):
        self.assertIsInstance(cli.__version__, str)
        self.assertTrue(cli.__version__.strip(), "cli.__version__ should not be empty")

    def test_source_checkout_falls_back_to_sentinel(self):
        """When ``importlib.metadata.version()`` raises (package not
        installed — the CI scenario), ``cli/__init__.py`` must fall
        back rather than crash. Re-imports the module under a patched
        ``version()`` to simulate the source-only environment."""
        # Drop cached cli module so the import re-executes
        # ``cli/__init__.py``'s top-level code.
        cached = sys.modules.pop("cli", None)
        try:
            with patch(
                "importlib.metadata.version",
                side_effect=PackageNotFoundError("contextkit-ai"),
            ):
                fresh = importlib.import_module("cli")
                # Sentinel must be a non-empty PEP 440-valid string.
                self.assertIsInstance(fresh.__version__, str)
                self.assertTrue(fresh.__version__.strip())
                # And it must clearly not look like a real release.
                self.assertIn("source", fresh.__version__.lower())
        finally:
            # Restore the real module so subsequent tests in the suite
            # see the production version constant, not the patched one.
            if cached is not None:
                sys.modules["cli"] = cached
            else:
                # If cli wasn't cached (unlikely), force a fresh real import.
                sys.modules.pop("cli", None)
                importlib.import_module("cli")


if __name__ == "__main__":
    unittest.main()
