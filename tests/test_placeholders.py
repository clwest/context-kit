"""Tests for context-kit placeholder derivation and substitution.

Run from the repo root:

    python3 -m unittest discover -s tests -t .
"""

from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

# Make the repo root importable when tests run via `unittest discover`.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.placeholders import apply_placeholders, derive_placeholders, _slugify  # noqa: E402


class TestDerivePlaceholders(unittest.TestCase):
    def test_two_word_title(self):
        p = derive_placeholders("My App")
        self.assertEqual(p["APP"], "My App")
        self.assertEqual(p["APP_SLUG"], "my-app")
        self.assertEqual(p["APP_UPPER"], "MY_APP")
        self.assertEqual(p["APP_TITLE"], "My App")

    def test_kebab_input_unchanged(self):
        p = derive_placeholders("donkey-betz")
        self.assertEqual(p["APP_SLUG"], "donkey-betz")
        self.assertEqual(p["APP_UPPER"], "DONKEY_BETZ")
        self.assertEqual(p["APP_TITLE"], "Donkey Betz")

    def test_two_words_lowercase_with_space_become_hyphenated_slug(self):
        # The user-reported wizard verification bug hinged on "stress test"
        # producing the folder ``stress-test``. Lock that exact mapping in
        # so any future slug refactor that breaks it fails loudly here, and
        # so the wizard's mirror of this rule has a name to match against.
        p = derive_placeholders("stress test")
        self.assertEqual(p["APP_SLUG"], "stress-test")

    def test_camel_case_splits_at_boundary(self):
        p = derive_placeholders("MyApp")
        self.assertEqual(p["APP_SLUG"], "my-app")
        self.assertEqual(p["APP_UPPER"], "MY_APP")
        self.assertEqual(p["APP_TITLE"], "My App")

    def test_duplicate_separators_collapse(self):
        p = derive_placeholders("too   many--spaces")
        self.assertEqual(p["APP_SLUG"], "too-many-spaces")
        self.assertEqual(p["APP_UPPER"], "TOO_MANY_SPACES")

    def test_underscore_separators_normalize_to_hyphens(self):
        p = derive_placeholders("my_awesome_app")
        self.assertEqual(p["APP_SLUG"], "my-awesome-app")
        self.assertEqual(p["APP_UPPER"], "MY_AWESOME_APP")

    def test_leading_and_trailing_whitespace_stripped(self):
        p = derive_placeholders("  My App  ")
        self.assertEqual(p["APP_SLUG"], "my-app")
        self.assertEqual(p["APP"], "My App")  # .strip() applied to raw input

    def test_leading_digits_preserved_in_slug(self):
        p = derive_placeholders("3rd Time")
        self.assertEqual(p["APP_SLUG"], "3rd-time")
        self.assertEqual(p["APP_UPPER"], "3RD_TIME")
        self.assertEqual(p["APP_TITLE"], "3rd Time")

    def test_edge_separators_stripped(self):
        p = derive_placeholders("---app---")
        self.assertEqual(p["APP_SLUG"], "app")

    def test_unicode_falls_back_gracefully(self):
        # Non-ASCII chars are normalized via the non-alphanumeric rule:
        # any run of [^a-zA-Z0-9]+ collapses to a single hyphen.
        p = derive_placeholders("café app")
        self.assertEqual(p["APP_SLUG"], "caf-app")

    def test_single_word_input(self):
        p = derive_placeholders("solo")
        self.assertEqual(p["APP_SLUG"], "solo")
        self.assertEqual(p["APP_UPPER"], "SOLO")
        self.assertEqual(p["APP_TITLE"], "Solo")

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError):
            derive_placeholders("")

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            derive_placeholders("   ")

    def test_only_non_alphanumeric_raises(self):
        with self.assertRaises(ValueError):
            derive_placeholders("!!!")

    def test_date_fields_match_today(self):
        p = derive_placeholders("X Y")
        self.assertRegex(p["DATE"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(p["DATE"], date.today().isoformat())
        self.assertEqual(p["YEAR"], str(date.today().year))


class TestApplyPlaceholders(unittest.TestCase):
    def test_simple_replace(self):
        self.assertEqual(
            apply_placeholders("hello {{APP}}", {"APP": "world"}),
            "hello world",
        )

    def test_multiple_distinct_keys(self):
        out = apply_placeholders("{{APP}} on {{DATE}}", {"APP": "hi", "DATE": "2026-04-21"})
        self.assertEqual(out, "hi on 2026-04-21")

    def test_unknown_placeholder_left_alone(self):
        out = apply_placeholders("{{APP}} and {{NOT_MAPPED}}", {"APP": "X"})
        self.assertEqual(out, "X and {{NOT_MAPPED}}")

    def test_empty_mapping_is_noop(self):
        self.assertEqual(apply_placeholders("{{X}}", {}), "{{X}}")

    def test_repeated_placeholder_all_replaced(self):
        out = apply_placeholders("{{X}} and {{X}}", {"X": "yes"})
        self.assertEqual(out, "yes and yes")


class TestSlugifyInternals(unittest.TestCase):
    """_slugify is semi-private but documented; guard against regressions."""

    def test_camel_case_boundary(self):
        self.assertEqual(_slugify("MyApp"), "my-app")

    def test_all_uppercase_stays_together(self):
        # No lowercase-to-uppercase transition, so the rule doesn't fire.
        self.assertEqual(_slugify("ACMEOrg"), "acmeorg")

    def test_digit_to_letter_boundary(self):
        # lookbehind [a-z0-9] + lookahead [A-Z] inserts a split here.
        self.assertEqual(_slugify("abc123ABC"), "abc123-abc")

    def test_mixed_separators(self):
        self.assertEqual(_slugify("foo.bar baz_qux"), "foo-bar-baz-qux")


if __name__ == "__main__":
    unittest.main()
