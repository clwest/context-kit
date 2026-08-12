---
title: "Session 017 — handoff write subcommand"
date: 2026-05-15
status: shipped `context-kit handoff write <N>` covering drift-prevention recs 2 + 3 from SESSION_016
previous_handoff: ./SESSION_016_NARRATIVE_ANCHOR_DRIFT_CHECK.md
---

# Session 017 — handoff write subcommand

## Why this handoff exists

SESSION_016 deferred two drift-prevention recs as their own
session: **rec 2** — a `context-kit handoff write <N>`
subcommand that re-stamps every anchor doc's frontmatter in
one shot, and **rec 3** — promote calibration entries from
handoffs to `TRUST_CALIBRATION.md` at handoff-write time.

This session shipped both. Example-agent-os SESSION 158 (the
sibling project that surfaced the original drift class)
served as the live target.

## Current state

| Surface | Value |
|---|---|
| `pyproject.toml` version | `0.15.0` (unchanged; this is unreleased) |
| Latest tag | `v0.15.0` |
| Branch | `main`, ahead of `origin/main` by 1 commit (the SESSION_016 commit) |
| Working tree before this session | clean post-SESSION_016 |
| Tests | **1076 / 1076 passing** (1042 prior + 34 new this session) |
| Doctor | unchanged — 5 advisory warnings, 0 blocking |

## What shipped

### `cli/handoff.py` — new module (~430 lines)

The module owns two side-effects under a single CLI verb:

* **Re-stamp anchor docs** (rec 2). Discovers `docs/*_WHAT_IT_IS.md`,
  `*_PIPELINE.md`, `*_BEHAVIOR_LAYER.md`, `*_TRANSLATION_LAYER.md`,
  and `*_SESSION_START.md`. For each doc with anchor frontmatter:
  updates `last_revised: YYYY-MM-DD (SESSION NNN)` (inserts the
  field after `generated:` when missing); bumps `covers_sessions:`
  upper bound when the field is present. `*_INVENTORY.md` is
  deliberately excluded — it's managed by `inventory --write`.

* **Calibration drift detection** (rec 3). Parses the handoff
  for `## Calibration moments worth carrying` or `## AI Notes`,
  extracts subsections, fuzzy-matches their headlines against
  `TRUST_CALIBRATION.md` entries on the same date. Reports
  `✓ promoted` (matched) or `⚠ MISSING` (appears in handoff,
  not in TRUST_CALIBRATION). **Read-only on TRUST_CALIBRATION**
  — the translation from handoff prose to the canonical
  5-field shape is operator judgment, not deterministic.

Fuzzy matching: tokenize headline → lowercase → strip
stopwords (`the`, `a`, `ai`, `operator`, `session`, ...) and
digit-only tokens → require ≥ 0.4 overlap. The smoke test
against example-agent-os SESSION 158 matched all 3 calibration
moments correctly despite headline-shape differences between
handoff prose (`1. AI overstated "shipped" before operator
viewed the output`) and TRUST_CALIBRATION classification
(`AI confidently wrong (deliverable framing): "shipped" before
operator review`).

### `context_kit.py` — CLI wiring

New `handoff` group with one action: `handoff write <N>
[--project PATH] [--dry-run] [--date YYYY-MM-DD]`. Follows the
`inventory --write` / `seed --dry-run` shape. Exit codes:
0 always (calibration warnings advisory, matching `doctor`); 2
on bad input (project not a dir, handoff missing, N not int,
bad date format).

### `tests/test_handoff.py` — 34 new tests

Coverage:
* Frontmatter parse / set / insert / bump helpers — 8 tests.
* Anchor doc discovery (globs match, INVENTORY excluded,
  no-`docs/` dir gracefully empty) — 2 tests.
* Re-stamp semantics — 5 tests (last_revised + covers
  update; insert-after-`generated:`; skip no-frontmatter;
  skip no-anchor-fields; dry-run no-write; idempotency).
* Calibration extraction (two subsections; `## AI Notes`
  alias; empty when no section; fuzzy stopword/digit strip)
  — 4 tests.
* Calibration audit (matched + missing; no
  TRUST_CALIBRATION; different-date no-match) — 3 tests.
* Handoff discovery (3-digit pad; legacy 1-digit; missing;
  date extract; missing-date) — 5 tests.
* End-to-end run (clean exit; dry-run no-write; date
  override; bad date; missing handoff; non-int session) — 7
  tests.

`python3 -m unittest discover -s tests -t .` → **1076 OK**.

## Smoke test — example-agent-os SESSION 158

The original drift surface. Dry-run output:

```
Anchor doc frontmatter:
  unchanged          docs/EXAMPLE_AGENT_OS_WHAT_IT_IS.md (already at 2026-05-15 (SESSION 158))
  would restamp   docs/EXAMPLE_AGENT_OS_PIPELINE.md (last_revised: (missing) → 2026-05-15 (SESSION 158))
  would restamp   docs/EXAMPLE_AGENT_OS_BEHAVIOR_LAYER.md (last_revised: (missing) → 2026-05-15 (SESSION 158))
  would restamp   docs/EXAMPLE_AGENT_OS_TRANSLATION_LAYER.md (last_revised: (missing) → 2026-05-15 (SESSION 158))
  would restamp   docs/EXAMPLE_AGENT_OS_SESSION_START.md (last_revised: (missing) → 2026-05-15 (SESSION 158))

Calibration promotion check (read-only):
  ✓ promoted   1. AI overstated "shipped" before operator viewed the output
  ✓ promoted   2. Avatar voice × lip-sync quality is a real operational axis
  ✓ promoted   3. R9's hardcoded $0.08/min placeholder was accurate enough
```

This proves out the original drift hypothesis: across
example-agent-os's 50+ sessions, only the `WHAT_IT_IS.md` anchor
got its `last_revised:` field stamped. Four secondary anchors
(`PIPELINE`, `BEHAVIOR_LAYER`, `TRANSLATION_LAYER`,
`SESSION_START`) had been silently sitting with `generated:
2026-01-01` and no `last_revised:` at all. The new subcommand
caught all four in one invocation.

Live write against the sibling project landed all four
re-stamps. Operator will commit those changes separately in
example-agent-os.

## Doctor coverage status

Doctor's `check_narrative_anchor_freshness` (SESSION_016) and
this session's `handoff write` are complementary:

* `doctor` — runs at session **start**, reports whether the
  narrative anchor's date is older than the latest handoff.
  Warning-only.
* `handoff write` — runs at session **end**, atomically
  re-stamps every anchor doc's date. Removes the forgetting
  surface that produces the drift in the first place.

The two together close the rec 1 / rec 2 / rec 3 thread from
the original drift-prevention review.

## Known warnings (after this session)

Unchanged from SESSION_016:

1. Pipeline / runtime flow map — `docs/CONTEXT_KIT_PIPELINE.md`
   missing.
2. Behavior layer — `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md`
   missing.
3. Handoff numbering continuity — `SESSION_005` gap.
4. Start vs handoff verification — start-here next-task
   text not in latest handoff. Will need to clear when
   `00-START-NEXT-SESSION.md` is rewritten this commit.
5. Narrative anchor freshness — `CONTEXT_KIT_WHAT_IT_IS.md`
   still dated to SESSION_015's window. Carried.

None are blocking. SESSION_016's deferred items still
deferred: INVENTORY git-SHA drift check, narrative anchor
freshness clear.

## Recommended next work

In rough order:

1. **Clear the narrative-anchor freshness warning** for
   context-kit itself. Now that `handoff write` exists, the
   discipline is: bump the anchor's `generated:` / add
   `last_revised:` whenever a session changes the body. The
   subcommand doesn't yet apply to the project that *runs* it
   (no `--self` mode); applying it manually here is the
   smallest path. Cleanest fix: run the subcommand from inside
   context-kit's own directory (`python3 context_kit.py
   handoff write 17 --project .`) after writing this handoff.
2. **INVENTORY git-SHA drift check** (rec 1 second half from
   SESSION_016). Modify `inventory.py` to emit `<!-- Git SHA:
   <abbrev> -->` next to `<!-- Last generated: ... -->`, then
   add a doctor check that compares against current HEAD.
3. **Pipeline / Behavior Layer docs for context-kit itself**.
   Either write them or document the decision to skip. The
   warnings have outlived their value as long as they keep
   being acknowledged-but-deferred.

## Files changed in this commit

* `cli/handoff.py` — new
* `context_kit.py` — added `handoff` subparser + dispatch
* `tests/test_handoff.py` — new
* `00-START-NEXT-SESSION.md` — rewritten for SESSION 018
* `docs/handoffs/SESSION_017_HANDOFF_WRITE_SUBCOMMAND.md` — this file
* `CLAUDE.md` — pointed at this handoff

## AI Notes

`handoff write` is the first context-kit subcommand whose
write side touches *multiple* project docs in one shot.
Previous write commands (`inventory --write`, `seed`,
`adopt --write`) each own a single managed block in a single
file. The frontmatter re-stamp here lives outside any managed
block — it edits raw YAML keys directly. Two precautions made
this safe:

* The re-stamp is narrowly scoped. Only `last_revised:` and
  `covers_sessions:` get touched; everything else passes
  through untouched. Docs without anchor-shape frontmatter
  are skipped silently, not normalized.
* The TRUST_CALIBRATION side is intentionally read-only. The
  alternative — auto-appending skeleton entries — looked
  attractive but would generate operator work (each stub
  needs the canonical 5-field shape applied) without
  removing the underlying judgment. Detect-and-report
  surfaces the drift without inviting more.

The fuzzy headline match (≥ 0.4 token overlap with
stopword/digit strip) is the most heuristic part of the
module. The example-agent-os SESSION 158 smoke test happened to
match all 3 entries cleanly; pathological cases (very short
headlines, e.g. `### x`) will still produce false negatives.
That's the safe failure mode — a missed match reads as
`⚠ MISSING`, which the operator can either dismiss or use as
a prompt to verify TRUST_CALIBRATION manually. No
silently-wrong matches.
