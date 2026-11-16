---
title: "Session 021 — Codex continuity dogfood"
date: 2026-11-16
status: documentation-only continuity test
previous_handoff: ./SESSION_020_GUARDRAILS_SUBCOMMAND.md
---

# Session 021 — Codex continuity dogfood

## Purpose and evidence boundary

This session tested a Codex write task in a context-kit project using
`orient`, the anchors, the numbered handoff, and the next-session guide.
The task brief records the user's explanation that context-kit exists
because handoffs and other documentation were sometimes missed or
overwritten. It also records that the earlier bridge guidance now says
to follow context-kit workflows where applicable and not create parallel
documentation systems. Those bridge changes preceded this test; this
session did not implement or independently inspect them.

This dogfood task is documentation-only. The numbered handoff and
`00-START-NEXT-SESSION.md` are the canonical continuity artifacts; the
task's execution report is a concise checklist, not a replacement.

## Current state

- Package version `0.16.0`; latest local tag `v0.16.0`.
- At task start, branch `main` was at `75f1e5b`, zero commits ahead/behind
  the local `origin/main` reference (no fetch performed).
- The pre-existing README scope clarification distinguishes launching
  Codex and optional local Ollama chat from supervising agents. It was
  preserved during this task and included in the later documentation commit.
- Initial `orient`: inventory current; 1116 test definitions discovered;
  doctor 0 blocking, 3 warnings (missing PIPELINE, missing BEHAVIOR_LAYER,
  and the SESSION_005 numbering gap).
- Session 020 reported 1116 passing tests historically. This session did
  not run the unit test suite and makes no current passing-test claim.

## Changed docs

- Added this handoff and rewrote `00-START-NEXT-SESSION.md` to point here,
  correct current-state claims, and retain the existing queue in order.
- Updated `.context-kit/TASK_codex-continuity-dogfood.md` with task status
  and a dated execution checklist.
- `handoff write 21` restamps eligible anchor frontmatter; exact results
  and closing checks are recorded below. No manual inventory edits.

## First-pass checks and limits

- `python3 context_kit.py handoff write 21` — exit 0; restamped
  `docs/CONTEXT_KIT_WHAT_IT_IS.md` to `2026-11-16 (SESSION 21)`;
  skipped translation layer (no frontmatter). Calibration audit reported
  `(handoff has no `## Calibration moments` or `## AI Notes` section)`
  because there were no H3 subsections to audit. Matching H2 headings
  (including `## AI Notes`) are recognized, but entries are extracted from
  H3 subsections only. Bare prose under AI Notes yields no entries;
  the command's no-section message does not mean the H2 was unrecognized.
  No calibration entry was fabricated; TRUST_CALIBRATION was not modified.
- `python3 context_kit.py verify` — exit 0: VERIFIED 1, DOC_ONLY 4,
  CONFLICT 0, UNKNOWN 1. DOC_ONLY findings: agents, APIs, frontend pages,
  spiders count claims. UNKNOWN: Django settings module. VERIFIED:
  Celery beat schedule ownership. These findings were left unchanged.
- `python3 context_kit.py doctor` — exit 0: 10 OK, 0 blocking, 4 warnings,
  4 skipped. Warnings: stale inventory, missing PIPELINE, missing
  BEHAVIOR_LAYER, missing SESSION_005. Skips: Node.js, Expo SDK,
  file watcher/open-file limit (no package.json), next-task pointer
  consistency (no adopt-managed block).
- `python3 context_kit.py inventory --check` — exit 1:
  `context-kit: inventory is stale (regenerate with --write)`.
  Inventory was current at orientation and became stale during this
  documentation task; it was initially left unchanged. The authorized
  follow-up below closes this gap. No commands or features changed.
No unit tests, source/test edits, README edits, commits, pushes, or
publication were performed. Unrelated warnings/conflicts are left open.

## Next session priorities

### FIRST THING: decide on PIPELINE / BEHAVIOR_LAYER docs for context-kit itself

Preserve the decision from the existing start guide: write the two docs
or document the deliberate skip and teach doctor to suppress opted-out
checks. This test does not decide that question.

Then, in order: backfill SESSION_005; add the inventory git-SHA drift
check; stress-test fleet-network on a second instance; stress-test
spokesperson-corpus on a second instance. Details and carried bundling
context remain in `00-START-NEXT-SESSION.md`.

## AI Notes

Durable continuity here lives in the repository's established handoff and
start-guide workflow. Test discovery and historical test results must not
be presented as tests executed during this documentation task.


## Follow-up — 2026-11-16: generated inventory current

The user clarified that the new numbered handoff changes the generated
handoff count and authorized regeneration through the supported command.
`docs/CONTEXT_KIT_INVENTORY.md` was updated only by
`python3 context_kit.py inventory --write` (exit 0; reported updated).
The managed handoff count is now 20, including SESSION_021.

- Final `python3 context_kit.py inventory --check` — exit 0:
  `context-kit: inventory is current`.
- Final `python3 context_kit.py doctor` — exit 0: 11 OK, 0 blocking,
  3 warnings, 4 skipped. Remaining warnings: missing PIPELINE, missing
  BEHAVIOR_LAYER, missing SESSION_005. Skips remain Node.js, Expo SDK,
  file watcher/open-file limit (no package.json), and next-task pointer
  consistency (no adopt-managed block).
- `verify` was not rerun: the prior exit 0 with 0 conflicts remains the
  recorded verification result; this follow-up updates generated inventory
  and continuity records only.

Updated the start guide with final outcomes and appended a follow-up
checklist to the task file, preserving its original execution report.
The initial report's calibration interpretation is corrected above:
matching H2 sections are recognized; no H3 subsections means no entries.
No tests run, source changes, fabricated calibration entries,
TRUST_CALIBRATION edits, README edits, commits, pushes, or publication.
The existing FIRST THING and queued priorities remain in order.

After the dogfood task, the user requested a local commit. The context-kit
documentation and README scope clarification were committed together as
`docs: record Session 021 continuity dogfood`. The commit remains local;
it was not pushed. The post-commit inventory check caught the expected
tracked-file count increase from adding SESSION_021; inventory was regenerated
with `context-kit inventory --write` and now reports 170 tracked files and 20
handoffs. `inventory --check` passes, and the post-commit doctor reports 11 OK,
0 blocking, and the same 3 roadmap warnings.
