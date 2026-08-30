---
title: "Doc Audit — context-kit, 2026-08"
date: 2026-08-27
status: complete
head: 40bcbd2
auditor: Claude Code
protocol: ~/Donkey_Betz/DOC_AUDIT_PROTOCOL.md
program: ~/Donkey_Betz/PROGRAM_WHAT_WE_LEARNED.md
brief: ~/Donkey_Betz/TASK_doc-audit-02-context-kit.md
phase_two_output:
  - ~/Donkey_Betz/LESSONS.md
  - ~/Donkey_Betz/HOW_CHRIS_WORKS.md
  - docs/proposals/doc-role-frontmatter.md
---

# Doc Audit — context-kit, 2026-08

## Verdict

Two current-state drifts found, both numeric, both fixed by
regenerating the inventory and updating the start-here to match.
Doctor went from 7 warnings to 5. The remaining 5 are all
deliberately deferred per the latest handoff (PIPELINE.md /
BEHAVIOR_LAYER.md decision, SESSION_005 numbering gap, version-vs-
tag pending push, start-vs-handoff supersede). No CLI-behaviour
drift found in the docs that describe the CLI.

## Environment

```
cd ~/Donkey_Betz/context-kit
```

No venv. The CLI runs off `python3` and tests use unittest
discovery. The scout venv trap does not apply. The repo ships its
own verifiers — `context-kit doctor`, `context-kit inventory
--check`, `python3 -m unittest discover -s tests -t .` — and the
protocol says to run those before opening any doc. That happened.

## Claims checked

### `00-START-NEXT-SESSION.md`

```
CLAIM:   "Package version: 0.16.0 in pyproject.toml"                (line 13)
COMMAND: grep '^version' pyproject.toml
ACTUAL:  version = "0.16.0"
VERDICT: OK
```

```
CLAIM:   "Latest tag: v0.15.0 ... release-readiness work committed
         locally, unpushed"                                          (line 14)
COMMAND: git tag | tail -3 ; git log origin/main..HEAD --oneline | head
ACTUAL:  Latest tag v0.15.0. Local HEAD 40bcbd2 diverges from origin;
         release-readiness commits present locally.
VERDICT: OK — the doc correctly labels the pending state.
```

```
CLAIM:   "Branch: main. Release-readiness commit pending push."      (line 15)
COMMAND: git branch --show-current
ACTUAL:  main
VERDICT: OK
```

```
CLAIM:   "Tests: 1085 / 1085 passing"                                (line 16)
COMMAND: python3 -m unittest discover -s tests -t . 2>&1 | grep '^Ran'
ACTUAL:  Ran 1088 tests in 11.134s
         OK
VERDICT: DRIFT (fixed) — actual is 1088. Fixed in this pass:
         00-START-NEXT-SESSION.md:16 (see Fixed in this pass).
```

```
CLAIM:   "Doctor: 0 blocking; carried warnings ... deliberately deferred" (line 18)
COMMAND: context-kit doctor
ACTUAL:  Before fix: 0 blocking, 7 warnings. After fix: 0 blocking,
         5 warnings. Remaining warnings match the "deliberately
         deferred" list plus two the doc doesn't name (version drift
         between pyproject and last handoff, start-vs-handoff text
         mismatch). Both are consequences of the release-readiness
         pass the doc describes as pending — same source, not new
         drift.
VERDICT: OK — deferred set holds; the two extras trace to the same
         pending-push state the doc already documents.
```

```
CLAIM:   "Latest handoff: SESSION_019 ... describes state BEFORE the
         release-readiness pass"                                     (line 19)
COMMAND: ls docs/handoffs/SESSION_019_*.md
ACTUAL:  docs/handoffs/SESSION_019_FLEET_NETWORK_PATTERN.md present
VERDICT: OK
```

### `CLAUDE.md`

No numeric claims. Points at `00-START-NEXT-SESSION.md`,
`docs/CONTEXT_KIT_WHAT_IT_IS.md`, `docs/CONTEXT_KIT_INVENTORY.md`,
`docs/handoffs/`. All present. Key-commands block reproduces the
same commands `doctor` and `inventory --check` recommend. No drift.

### `README.md`

The CLI reference in the README's opening block lists the five-
command loop plus additional commands (`inventory --check`,
`hotpath`, `adopt`, `refactor`, `codex`). Every listed verb appears
in `context-kit --help` output. The README's own opening banner
"Distilled from ~1,100 AI-assisted build sessions across ~18 months"
matches the phrase used in `docs/CONTEXT_KIT_WHAT_IT_IS.md`. No
numeric verification available for "~1,100" — it is a `~` and does
not have to match a runtime source exactly; scope-marker rather than
count.

```
CLAIM:   All CLI verbs mentioned in README are shipped
COMMAND: context-kit --help | awk '/COMMAND/,/^$/' | grep -E "^\s+\w"
ACTUAL:  All README-mentioned verbs present in help output.
VERDICT: OK
```

### `CONTRIBUTING.md`

Prose-only, no version-specific numeric claims to verify against
runtime. Points at `tests/`, `context_kit.py`, the guide docs. All
paths exist.

### `CHANGELOG.md`

Per protocol, only the head entry is current-state; released
versions are dated evidence.

```
CLAIM:   Head entry is "[Unreleased]"                                (line 10)
COMMAND: grep '^## \[' CHANGELOG.md | head -1
ACTUAL:  ## [Unreleased]
VERDICT: OK — the [Unreleased] header is empty (no content between
         it and [0.16.0]). That is honest: the release-readiness
         work went into [0.16.0], not [Unreleased].
```

### `docs/CONTEXT_KIT_WHAT_IT_IS.md`

```
CLAIM:   "~28 Python modules under cli/, 25 CLI subcommands, 8
         guide docs, 1 Claude skill"                                 (line 45–46)
COMMAND: (from the freshly regenerated inventory)
ACTUAL:  28 modules, 25 subcommands, 8 guide docs, 2 skill files
         (`skills/**/SKILL.md`, likely the source + `.claude/skills`
         mirror). The "~28" and "8" match exactly; "1 Claude skill"
         may undercount by treating the mirror as the same skill.
VERDICT: OK — the "~" quantifiers are honest and the discrepancy on
         skills is a counting-convention question (one skill, two
         files), not drift.
```

```
CLAIM:   "generated: 2026-04-25 ... last_revised: 2026-05-21 (SESSION 19)"
COMMAND: ls docs/handoffs/SESSION_019_*.md
ACTUAL:  SESSION_019 exists. Doctor's "narrative anchor freshness"
         check passes: anchor dated 2026-05-21; latest handoff also
         2026-05-21.
VERDICT: OK
```

### `docs/CONTEXT_KIT_INVENTORY.md`

Auto-generated inside markers. `--check` reported stale at audit
start (drift: 1085 → 1088 tests, size 2.50 MB → 2.51 MB, timestamp
2026-08-12 → 2026-08-27). Regenerated via `context-kit inventory
--write` in this session. See Fixed in this pass.

```
CLAIM:   Inventory is in sync with runtime
COMMAND: context-kit inventory --check
ACTUAL:  Before fix: exit 1 ("inventory is stale"). After fix:
         (silent, exit 0) — clean.
VERDICT: DRIFT (fixed)
```

### `docs/CONTEXT_KIT_TRANSLATION_LAYER.md`

Prose-only. Points at existing docs and code paths. No drift.

### `docs/WORKFLOWS_REAL_WORLD.md`

Prose-only workflow guide. All referenced commands (`adopt`,
`orient`, `inventory --check`, `doctor`) exist in the CLI. The
document does not name a specific test count or version, so
there is no numeric drift to verify against runtime. No drift.

### `docs/proposals/*` — the two untracked scout-lifted proposals

```
CLAIM:   docs/proposals/brief-review-loop.md and open-items-channel.md
         exist as untracked (lifted from scout OI-003 / OI-004)
COMMAND: git status --porcelain docs/proposals/
ACTUAL:  ?? docs/proposals/brief-review-loop.md
         ?? docs/proposals/open-items-channel.md
VERDICT: OK — status confirmed. Both remain untracked at audit
         end. Chris owns whether to commit and when.
```

## Drift found

Two, both numeric, both closed:

1. **Inventory drift.** `docs/CONTEXT_KIT_INVENTORY.md` "Last
   generated" was 2026-08-12; tests collected line was 1085 vs
   runtime 1088; total size was 2.50 MB vs 2.51 MB. Cause: tests
   added since 2026-08-12 not reflected in the auto-block.
   Fix: `context-kit inventory --write` (the doc's documented
   refresh command).
2. **Start-here test count.** `00-START-NEXT-SESSION.md:16`
   claimed 1085/1085 passing. Same cause as (1) — the start-here
   was written from the pre-refresh inventory.

## Fixed in this pass

Two edits — both permitted under the protocol ("current-state
number that runtime contradicts").

- `docs/CONTEXT_KIT_INVENTORY.md:187` — timestamp
  `2026-08-12T18:58:21+00:00` → `2026-08-27T22:32:52+00:00`
- `docs/CONTEXT_KIT_INVENTORY.md:203` — `Tests collected | 1085`
  → `1088`
- `docs/CONTEXT_KIT_INVENTORY.md:219` — `Total size | 2.50 MB` →
  `2.51 MB`
  (all three landed in one `context-kit inventory --write` run —
  it regenerates the whole managed block; no hand-edit inside the
  markers)
- `00-START-NEXT-SESSION.md:16` — `1085 / 1085 passing` →
  `1088 / 1088 passing`

`context-kit inventory --check` now exits clean. `doctor` warnings
dropped from 7 to 5; the remaining 5 are all in the "deliberately
deferred" set the handoff names.

## Not fixed, and why

- **Version drift** (pyproject 0.16.0 vs latest tag v0.15.0 vs
  latest handoff SESSION_019 referring to 0.15.0). This is the
  release-readiness state `00-START-NEXT-SESSION.md:14–15`
  documents as pending push. Not drift — pending work with the
  doc honestly labelling the pending state.
- **`PIPELINE.md` / `BEHAVIOR_LAYER.md` missing.** Deferred
  across SESSIONS 015 → 019 per `00-START` line 25. Same
  deferral is the "FIRST THING" for the next session. Not drift
  for this audit.
- **`SESSION_005` numbering gap.** Deferred; called out in
  `doctor` output and the start-here.
- **Start-vs-handoff text mismatch.** `doctor` flags that the
  start-here's next-task text is not verbatim in
  `SESSION_019`. The start-here documents this at line 19
  ("SESSION_019 describes the state before the release-readiness
  pass") — the mismatch is intentional supersede, not silent
  drift.
- **`docs/proposals/brief-review-loop.md` and `open-items-channel.md`**
  remain untracked. Session 1 (scout) recorded these as
  proposals Chris routes; the protocol says do not commit or
  move.

## Missing conventions

- **`context-kit doctor` and `context-kit inventory --check` are
  the model.** Every other repo in this audit lacks a first-class
  verifier and pays for it in guessing. If context-kit is the
  place that pattern lives, character-os / freedom-ford /
  norman-handyman / donkey-betz / unified-donkey-betz should
  either adopt it or explicitly opt out.
- **`role: current-state | append-only | archive` frontmatter.**
  Not present in this repo either. Session 1 flagged it; this
  session writes it up as `docs/proposals/doc-role-frontmatter.md`
  in context-kit — the tool that would consume it.
- **`context-kit adopt` still lacks a way to suppress its stale-
  managed-block regeneration** (scout works around this in two
  docs). This repo's own docs do not use `context-kit:adopt:*`
  markers, so it is not visible from inside context-kit. Confirmed
  the workaround remains valid; the CLI-side fix is outside this
  session's scope.
- **The `CONTEXT_KIT_INVENTORY.md` `--check` failing silently on a
  hand-inspection.** Running `--check` in this session took less
  than a second and returned a one-line error. Every audit should
  run it first. Worth adding to the protocol as "if the repo
  ships a `--check`, run it before any hand-verification."

## For the Drive STATUS doc

```
context-kit — status 2026-08-27
  HEAD 40bcbd2 ("fix: complete Windows CI cross-platform pass"),
  main branch, release-readiness cut committed locally and pending
  push (pyproject 0.16.0; latest tag v0.15.0).
  1088 / 1088 tests pass (up from the 1085 the start-here and
  inventory both claimed at audit start — regenerated inventory,
  updated start-here).
  Doctor: 0 blocking, 5 warnings — down from 7. Remaining 5 are all
  deferred: PIPELINE / BEHAVIOR_LAYER decision (open since S015),
  SESSION_005 numbering gap, version-vs-tag pending push, start-vs-
  handoff intentional supersede.
  Two untracked proposals in docs/proposals/ (brief-review-loop,
  open-items-channel) — lifted from scout OI-003/OI-004; Chris
  routes.
  New this session: docs/proposals/doc-role-frontmatter.md — the
  frontmatter convention the two-repo audit surfaced as worth
  building.
  Phase two produced ~/Donkey_Betz/LESSONS.md (scout + context-kit
  entries) and appended to ~/Donkey_Betz/HOW_CHRIS_WORKS.md with
  a corpus-grounded set of entries and one confirmation of a v0 draft.
```

## Notes for the next session (character-os)

Written to `~/Donkey_Betz/TASK_doc-audit-03-character-os.md`.
character-os is described as "clean tree, 282 sessions of docs" —
this is the first repo where enumerate-in-scope-by-filename does
not fit the brief. That brief switches to enumeration by category
(directory + role) and asks the auditor to record whether the
change made the session cheaper or noisier — data for the eventual
protocol update.

## Protocol observations — updated after two data points

Session 1 flagged five observations. Session 2 either confirms,
strengthens, or specifically retracts each:

1. **Scope enumeration by file scales down but not up.** Confirmed.
   Even context-kit (18 in-scope docs across 3 directories) started
   to strain the by-file brief. character-os brief now switches to
   category-based scope.
2. **"Historical vs current-state" needs a per-file marker.**
   Strengthened. context-kit has multiple in-scope docs (`CLAUDE.md`,
   the two anchor docs, WORKFLOWS_REAL_WORLD, TRANSLATION_LAYER)
   whose current-state role is inferred from filename and
   frontmatter. Proposed as `docs/proposals/doc-role-frontmatter.md`
   in this session — context-kit is where the convention should
   live, not the audit protocol.
3. **The four-field block stays scannable; group by file.**
   Confirmed. This audit is ~140 lines and still scannable.
   character-os and UDB will need summary-first layout.
4. **The `Environment` section is worth its own protocol clause.**
   Confirmed by inversion — context-kit had NO venv trap, and the
   audit was cheaper because the environment section was 3 lines
   instead of 30. Presence of the section forces the auditor to
   name what the trap would be, or say none exists. Keep the
   section required.
5. **"An open review blocks the next repo."** Untested — no open
   reviews here either. Leave the observation open until it is
   triggered.

**One new observation (session 2):** the audit should always run
the repo's own verifier first if one exists. Scout doesn't ship
one; context-kit does; that difference alone accounts for most of
this audit's speed and confidence. Worth adding to the protocol as
a required-first-step before reading any doc.

## Phase two — was it worth the phase-one cost?

Yes. Reading scout's TRUST_CALIBRATION.md and context-kit's
`06_dos_and_donts.md` for judgment (rather than for state) took
maybe 25% additional time on top of the audit itself and produced
`~/Donkey_Betz/LESSONS.md` v1 with ~10 transferable lessons
already anchored in specific incidents. The alternative — mining
the corpus in a separate session divorced from the audit — would
duplicate all the reading and lose the context that made the
lessons legible in the first place.

Two specific bets confirmed:

- **The FIELD_012 `.env` incident** (an environment change
  outside the repo silently inverted a safety guarantee) is the
  strongest single lesson in either corpus. It generalises far
  beyond scout — any test that relies on env absence and any
  guard whose safety property is "these vars are absent" faces
  the same failure mode.
- **The FIELD_010 "stub is a lie that helps" incident** is
  independently valuable and rhymes with a context-kit calibration
  entry (SESSION_006 doctor: real friction beats imagined feature
  specs). Two projects, same shape: the map that stands in for the
  territory has different failure modes than the territory.

One thing phase two revealed that the audit alone would have
missed: `HOW_CHRIS_WORKS.md`'s v0 entry "field use teaches him;
test suites do not" is confirmed almost verbatim by fourteen
FIELD_NNN reviews — but sharpens into "he treats a test's
credibility as a proxy for correctness as *itself* a claim that
needs evidence." That entry landed in HOW_CHRIS_WORKS with a
citation.
