"""context-kit CLI package.

Subcommands live in sibling modules and are dispatched from
``context_kit.py`` at the repo root:

- ``cli.bootstrap`` — ``init`` (scaffold a new project)
- ``cli.server``    — ``start`` (onboarding server)
- ``cli.placeholders`` — shared placeholder derivation + substitution
"""

from importlib.metadata import version

__version__ = version("contextkit-ai")
