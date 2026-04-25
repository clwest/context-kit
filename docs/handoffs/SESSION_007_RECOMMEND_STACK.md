---
title: "Session 007 — recommend-stack (beginner stack guidance)"
date: 2026-04-25
status: shipped
---

# Session 007 — `context-kit recommend-stack`

Stack guidance for non-technical builders. Deterministic, rules-based,
no LLM. Two entry points sharing one engine: a standalone command for
"give me an opinion" and a seed integration that auto-fills BUILD_PLAN.md
when the user's idea file omits `## Tech stack`.

## Origin

The use case the human named in the design conversation: a 67-year-old
with Parkinson's wants to build a medication tracking/reminder app. He
knows the problem intimately. He doesn't know whether to use React,
React Native, Flutter, or anything else. The existing `seed` command
required him to fill in `## Tech stack` himself, which is exactly the
kind of friction that stops a beginner from starting.

This session adds the missing rung on the ladder: the user names what
they want, context-kit recommends the right v0 stack with reasoning a
non-technical builder can act on.

## Architecture

`cli/recommend_stack.py` — one engine, two entry points.

**Data:**

- `Recommendation` dataclass: `stack`, `why`, `avoid_yet`, `risks`, `upgrade_when`
- `Rule` dataclass: `name`, `signals`, `priority`, `recommendation`,
  `is_modifier`, `note`
- `RULES`: 8 rules (6 primary + 2 modifier)
- `FALLBACK_RECOMMENDATION`: used when no rules match

**Engine:**

- `recommend(idea_text)` — substring + case-insensitive match;
  highest-priority non-modifier wins as primary; rest go to
  `also_detected` (capped at 3); modifiers can never be primary
- `format_human(idea_text, result)` — full human-readable output for
  stdout
- `format_for_build_plan(result)` — markdown body suitable for living
  inside an existing `## Tech stack` heading in BUILD_PLAN.md (uses
  h4 subheadings, includes attribution comment)

**Seed integration:**

`cli/seed.py::_render_build_plan_body` was a one-line "Tech stack"
section using `_section_or_placeholder`. Now: if the user's section
is present, use it verbatim. If missing, lazy-import
`recommend_stack` and call `format_for_build_plan(recommend(idea_text))`.
Same engine the standalone command uses, so the two paths can never
disagree. Dependency direction is **seed → recommend_stack**;
documented in module docstring.

## The 8 MVP rules

Per the design discussion, with the human's two refinements:

| Rule | Priority | Notes |
|---|---|---|
| `medication-reminders` | 10 | Explicit accessibility focus (large tap targets, simple language, high contrast, minimal screens, react-native-paper). Privacy framing: "Personal local-only use avoids most privacy/compliance complexity. If you later store/share health data for multiple users, talk to a lawyer." |
| `mobile-personal-tracking` | 8 | Kids fitness, journaling, habit tracking |
| `business-dashboard` | 8 | Admin tools, internal apps, single-user-first |
| `content-website` | 6 | Landing pages, blogs, portfolios |
| `local-automation` | 8 | Scripts, CLI, file processing |
| `web-api` | 7 | Backend services, REST/GraphQL APIs |
| `privacy-sensitive` (modifier) | 5 | Bias toward local-first; defer accounts |
| `simple-mvp` (modifier) | 3 | Explicit "no backend until you need it" |

The medication-reminders accessibility refinement and the
practical-not-scary privacy framing are locked in by the test
`TestToneOnPrivacyLanguage::test_medication_recommendation_uses_practical_privacy_framing`
— if either drifts, the test fails.

## Tests

35 new tests in `tests/test_recommend_stack.py`:

- 16 per-rule tests (8 rules × 2: matches expected text, doesn't
  match unrelated text)
- 6 engine tests (fallback when no match, modifier-only doesn't win
  as primary, priority ordering, modifier-never-primary, also-detected
  capping, case insensitivity, substring matching)
- 4 output tests (human format includes all sections, humble footer
  present, fallback used in no-match output, JSON valid + expected keys)
- 3 seed integration tests (Tech stack present → no auto-fill; missing
  + match → recommendation in BUILD_PLAN.md; missing + no match →
  fallback in BUILD_PLAN.md)
- 4 scenario tests (the 4 named in the design: medication reminder,
  kids fitness, business dashboard, automation script)
- 1 tone test (medication-reminders uses the practical-not-scary
  privacy framing)
- 1 humble-footer test (output ends with the "context-kit doesn't
  care" disclaimer)

Total suite now: **202 tests** (was 167).

## Files changed

```
A  cli/recommend_stack.py                          ~520 lines
A  tests/test_recommend_stack.py                   ~440 lines, 35 tests
A  docs/handoffs/SESSION_007_RECOMMEND_STACK.md    this file
M  cli/seed.py                                     _render_build_plan_body
                                                   delegates to recommend_stack
                                                   when ## Tech stack missing
M  cli/bootstrap.py                                cli/recommend_stack.py in
                                                   RUNTIME_COPY
M  context_kit.py                                  recommend-stack subparser
                                                   + dispatcher
M  cli/_skills/context-kit/SKILL.md                "run recommend-stack when
                                                   user doesn't know what to
                                                   build with"
M  cli/_pattern/IDEA_SCHEMA.md                     Tech stack section now
                                                   explicitly optional;
                                                   workflow shows recommend-
                                                   stack as optional step 3
M  README.md                                       commands list +
                                                   recommend-stack options
                                                   table + seed-integration
                                                   note
M  CHANGELOG.md                                    Unreleased entry
M  docs/CONTEXT_KIT_INVENTORY.md                   regen
```

## Verification

```
unittest discover                  202/202 OK  (was 167)
inventory --check                  current
orient                             all 5 sections
hotpath                            STATUS OK
doctor                             0 blocking / 0-1 warnings (depending
                                   on inventory state at the moment)
recommend-stack on each scenario   primary matches expectation; output
                                   includes all 5 sections + humble footer
                                   + "next steps"
seed integration                   Tech stack present: BUILD_PLAN.md
                                   shows the user's content, no
                                   auto-suggestion marker
                                   Tech stack missing + medication
                                   idea: BUILD_PLAN.md shows the
                                   recommendation under "Tech stack"
                                   with the attribution note
                                   Tech stack missing + no match:
                                   BUILD_PLAN.md shows the fallback
                                   ("Python CLI or static HTML") with
                                   the same attribution note
```

## Design choices that held up

- **Both standalone command AND seed integration** with shared engine.
  The two paths can never drift. Same pattern as `inventory` /
  `inventory --json` / inventory-check-from-doctor.
- **Substring + case-insensitive matching.** False positives are rare
  in natural prose; trade-off chosen for simplicity over precision.
  Word-boundary matching deferred to v2 if it becomes a real problem.
- **One primary + capped also-detected.** Beginner-friendly: one
  recommendation to act on, with secondary signals annotated for
  context. Not a buffet of equally-weighted options.
- **Default fallback ("Python CLI or static HTML").** Never silent;
  always tell the user *something* useful, even if vague.
- **Opinionated-but-humble tone.** Every recommendation ends with:
  *"These are opinionated picks for a first-time builder. If you have
  a stack you already know, use that — context-kit doesn't care."*
  Locked in by a test.
- **Practical-not-scary privacy framing.** The medication-reminders
  rule's risks section uses the human's exact wording rather than
  HIPAA-flavored fear. Locked in by a test.
- **Accessibility as a stack concern, not a UI concern.** The
  medication-reminders rule names react-native-paper (an accessibility-
  focused component library) as part of the recommended stack, not
  as a footnote. Designing for tremors, low vision, or cognitive load
  has to be in the v0 plan, not deferred.

## Known follow-ups (not in scope this session)

- **Stack picks will go stale.** `LAST_REVIEWED = "2026-04-25"`
  constant flagged at the top of `recommend_stack.py`. Plan to audit
  rules at least once per quarter. Hardcoded version-free names
  ("Expo React Native", not "Expo SDK 51") help.
- **`recommend-stack --explain`** would let users see which signals
  matched which rules. Useful for debugging weird recommendations.
  Deferred to v2.
- **Rule extraction to data file** if community contributors show up
  wanting to add their own rules. Code-as-data was the right call
  for MVP.
- **Word-boundary matching** if false positives become a real problem.
  Not yet observed.
- **Localization.** Currently English-only. If the tool gets non-English
  users, signal strings would need translating.

## AI Notes

- Caught one trivial bug during test runs: the test asserted lowercase
  "auto-suggested" but the actual marker text used capital
  "Auto-suggested". Fixed the test (the marker text is the canonical
  form people will see in their BUILD_PLAN.md).
- The dependency direction question came up cleanly: doctor → inventory,
  seed → recommend_stack. Both feel right (the diagnostic / orchestrating
  command depending on the focused module, never inverted). Worth
  watching for future commands.
- This is the first session where the design discussion produced a
  recommendation that *is itself* an artifact of the tool — the
  medication-reminders rule's accessibility focus came from the human
  describing his Parkinson's-affected dad. Same provenance pattern as
  doctor's Munchkin App origins. Real-friction-driven design keeps
  paying off.
- AI-paced estimate at design-approval time: 15-20 minutes.
  Implementation took roughly that. The earlier calibration about
  AI-pace estimates being too high doesn't apply when the design has
  modest novelty (8 rules, each with a different recommendation
  body); each rule was its own small judgment call about what to
  recommend. Good calibration anchor for future sessions: rule-heavy
  features take time per rule even at AI pace.
