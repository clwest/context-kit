"""context-kit CLI package.

Subcommands live in sibling modules and are dispatched from
``context_kit.py`` at the repo root:

- ``cli.bootstrap`` — ``init`` (scaffold a new project)
- ``cli.server``    — ``start`` (onboarding server)
- ``cli.placeholders`` — shared placeholder derivation + substitution
"""

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
