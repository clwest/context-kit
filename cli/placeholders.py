"""Placeholder derivation and substitution for context-kit.

A single user-provided app name (e.g. "Example App") is the source of truth;
every other form (APP_UPPER, APP_SLUG, APP_TITLE) is derived mechanically so
callers never hand-maintain the variants.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Mapping


def derive_placeholders(app_name: str) -> dict[str, str]:
    """Derive all placeholder variants from a single app name.

    Examples:
        >>> derive_placeholders("example-app")["APP_UPPER"]
        'EXAMPLE_APP'
        >>> derive_placeholders("MyApp")["APP_TITLE"]
        'My App'
        >>> derive_placeholders("two words")["APP_SLUG"]
        'two-words'
    """
    app = app_name.strip()
    if not app:
        raise ValueError("App name cannot be empty")

    slug = _slugify(app)
    if not slug:
        raise ValueError(f"Could not derive a valid slug from: {app!r}")

    constant = slug.replace("-", "_").upper()
    title = " ".join(w.capitalize() for w in slug.split("-") if w)
    today = date.today().isoformat()

    return {
        "APP": app,
        "APP_SLUG": slug,
        "APP_UPPER": constant,
        "APP_TITLE": title,
        "DATE": today,
        "YEAR": today[:4],
    }


def _slugify(name: str) -> str:
    """Normalize 'My App' / 'MyApp' / 'my_app' / 'My-App' -> 'my-app'."""
    # Insert boundary between camelCase transitions: 'MyApp' -> 'My-App'.
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name)
    # Any run of non-alphanumerics collapses to a single hyphen.
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s)
    return s.strip("-").lower()


def apply_placeholders(text: str, placeholders: Mapping[str, str]) -> str:
    """Replace every ``{{KEY}}`` occurrence in ``text`` with its mapped value."""
    for key, value in placeholders.items():
        text = text.replace("{{" + key + "}}", value)
    return text
