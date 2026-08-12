"""Tests for the structure of ``CHAT_BEHAVIOR_PREAMBLE``.

The preamble is a system prompt injected into every context-kit chat
session. Its wording is behavior-shaping: changing it changes what the
LLM does. These tests act as a tripwire so future edits are deliberate:

- The full preamble length is pinned (approximately, with a small band)
  so accidental deletions or additions get flagged.
- A representative rule from each named section is present, in order.

These are structural tests, not exact-content tests — the goal is to
catch dropped sections without making trivial edits painful.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cli.chat import (  # noqa: E402
    CHAT_BEHAVIOR_PREAMBLE,
    _PREAMBLE_HEADER,
    _PREAMBLE_EVIDENCE_SEPARATION,
    _PREAMBLE_CITATIONS,
    _PREAMBLE_CAPABILITY_CONTRACT,
    _PREAMBLE_ANTI_MARKETING,
    _PREAMBLE_CAPABILITY_INTERPRETATION,
    _PREAMBLE_LIVE_STATE,
    _PREAMBLE_NO_EXECUTION,
    _PREAMBLE_TURN_DISCIPLINE,
    _PREAMBLE_PERSONA,
)


class TestChatPreambleStructure(unittest.TestCase):
    def test_preamble_is_nonempty_and_bounded(self):
        # Snapshot length ~11k chars at the time of refactor. Allow a
        # ±20% band so ordinary edits pass but wholesale deletions or
        # duplications fire.
        length = len(CHAT_BEHAVIOR_PREAMBLE)
        self.assertGreater(length, 8000, f"preamble shrank drastically: {length} chars")
        self.assertLess(length, 14000, f"preamble grew drastically: {length} chars")

    def test_preamble_starts_with_header_and_ends_with_finalizer(self):
        self.assertTrue(
            CHAT_BEHAVIOR_PREAMBLE.startswith("You are running inside context-kit chat mode."),
            "preamble no longer starts with the header line",
        )
        self.assertTrue(
            CHAT_BEHAVIOR_PREAMBLE.endswith("Do not invent repo facts or stats."),
            "preamble no longer ends with the anti-hallucination finalizer",
        )

    def test_every_section_is_nonempty(self):
        sections = [
            ("HEADER", _PREAMBLE_HEADER),
            ("EVIDENCE_SEPARATION", _PREAMBLE_EVIDENCE_SEPARATION),
            ("CITATIONS", _PREAMBLE_CITATIONS),
            ("CAPABILITY_CONTRACT", _PREAMBLE_CAPABILITY_CONTRACT),
            ("ANTI_MARKETING", _PREAMBLE_ANTI_MARKETING),
            ("CAPABILITY_INTERPRETATION", _PREAMBLE_CAPABILITY_INTERPRETATION),
            ("LIVE_STATE", _PREAMBLE_LIVE_STATE),
            ("NO_EXECUTION", _PREAMBLE_NO_EXECUTION),
            ("TURN_DISCIPLINE", _PREAMBLE_TURN_DISCIPLINE),
            ("PERSONA", _PREAMBLE_PERSONA),
        ]
        for name, section in sections:
            with self.subTest(section=name):
                self.assertGreater(len(section), 0, f"section {name} is empty")

    def test_each_section_appears_in_order(self):
        # A representative canary line per section — order matters because
        # the preamble is assembled as ``"\n".join(section1 + section2 + ...)``.
        canaries = [
            "You are running inside context-kit chat mode.",                                 # HEADER
            "Machine-detected repo facts may only come from",                                # EVIDENCE_SEPARATION
            "Never invent file:line citations.",                                             # CITATIONS
            "Capability-question hard constraint:",                                          # CAPABILITY_CONTRACT
            "Do not infer business value",                                                   # ANTI_MARKETING
            "Use MACHINE-DERIVED REPO INSPECTION for details only when capabilities",        # CAPABILITY_INTERPRETATION
            "If the user asks about live repo state",                                        # LIVE_STATE
            "You cannot execute shell commands",                                             # NO_EXECUTION
            "Answer the user's current question directly.",                                  # TURN_DISCIPLINE
            "Audience adaptation changes framing only",                                      # PERSONA
        ]
        cursor = 0
        for canary in canaries:
            with self.subTest(canary=canary):
                idx = CHAT_BEHAVIOR_PREAMBLE.find(canary, cursor)
                self.assertGreaterEqual(
                    idx,
                    cursor,
                    f"canary {canary!r} not found after position {cursor} — section reordering suspected",
                )
                cursor = idx + len(canary)

    def test_all_rules_are_present_by_count(self):
        # Sanity check: preamble line count equals the sum of section lengths.
        total_rules = sum(
            len(section)
            for section in (
                _PREAMBLE_HEADER,
                _PREAMBLE_EVIDENCE_SEPARATION,
                _PREAMBLE_CITATIONS,
                _PREAMBLE_CAPABILITY_CONTRACT,
                _PREAMBLE_ANTI_MARKETING,
                _PREAMBLE_CAPABILITY_INTERPRETATION,
                _PREAMBLE_LIVE_STATE,
                _PREAMBLE_NO_EXECUTION,
                _PREAMBLE_TURN_DISCIPLINE,
                _PREAMBLE_PERSONA,
            )
        )
        line_count = CHAT_BEHAVIOR_PREAMBLE.count("\n") + 1
        self.assertEqual(
            line_count,
            total_rules,
            f"preamble line count ({line_count}) != sum of section lengths ({total_rules})",
        )


if __name__ == "__main__":
    unittest.main()
