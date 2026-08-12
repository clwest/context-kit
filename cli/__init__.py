"""context-kit CLI package.

Subcommands live in sibling modules and are dispatched from
``context_kit.py`` at the repo root:

- ``cli.bootstrap`` — ``init`` (scaffold a new project)
- ``cli.server``    — ``start`` (onboarding server)
- ``cli.placeholders`` — shared placeholder derivation + substitution
"""

import sys
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("contextkit-ai")
except PackageNotFoundError:
    # Source checkout without `pip install` (e.g. CI running tests directly,
    # or `python3 context_kit.py` from a fresh clone). The package isn't
    # installed, so importlib.metadata can't find it. The CLI itself doesn't
    # need this constant — it's only here for callers reading
    # ``cli.__version__``. Use a sentinel that's PEP 440-valid and obviously
    # not a real release.
    __version__ = "0.0.0+source"


def _configure_stdio_utf8() -> None:
    """Force UTF-8 encoding on stdout/stderr so CLI output is portable.

    Runs once at package-import time so any caller — the ``context-kit``
    entry point, tests that call ``run_*`` directly, or downstream tools
    that import from ``cli`` — sees UTF-8-capable streams. Without this,
    Windows consoles default to cp1252 and ``print("≤")`` raises
    UnicodeEncodeError mid-output.

    Best-effort: streams that don't expose ``reconfigure`` (older Python
    build, redirected BytesIO, closed handle) are skipped silently. Uses
    ``errors='replace'`` so a truly un-mappable character prints as ``?``
    instead of crashing the command.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (LookupError, ValueError, OSError):
            pass


_configure_stdio_utf8()
