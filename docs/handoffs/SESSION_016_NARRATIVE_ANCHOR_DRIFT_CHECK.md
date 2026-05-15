---
title: "Session 016 — narrative anchor freshness drift check"
date: 2026-05-15
status: shipped narrative-anchor-freshness doctor check + session-start drift sweep rule; orient runtime-state block landed pre-session in 7ca7240 / 85d82d1
---

# Session 016 — narrative anchor freshness drift check

## Why this handoff exists

A drift-prevention review from a sibling project surfaced four
recurring failure classes that the context-kit docs/anchors layer
should detect itself: stale processes, pending migrations,
frontmatter-date drift, and INVENTORY git-SHA mismatch. The first
two are app-level (Django) concerns. The last two are pattern-level
and belong in context-kit.

This session shipped the cheapest, highest-leverage piece —
narrative-anchor frontmatter-date drift as a new doctor check —
plus a one-line CLAUDE.md rule that codifies "every session starts
with a drift sweep" pointing at orient's existing
`## CURRENT RUNTIME STATE` block. INVENTORY git-SHA drift is
deferred until the inventory generator emits a SHA; `context-kit
handoff write` (rec 2 from the review) is deferred to a later
session.

## Current state

| Surface | Value |
|---|---|
| `pyproject.toml` version | `0.15.0` (unchanged) |
| Latest tag | `v0.15.0` |
| Branch | `main`, ahead of `origin/main` by 0 commits (uncommitted working tree) |
| Working tree | dirty — `CLAUDE.md`, `cli/doctor.py`, `cli/state.py`, `docs/CONTEXT_KIT_INVENTORY.md`, `tests/test_truth_state.py` |
| Tests | **1042 / 1042 passing** via `python3 -m unittest discover -s tests -t .` |
| Inventory | fresh — regenerated this session (821 → 1042 tests captured) |
| Doctor | 0 blocking, 5 warnings (see Known warnings) |

## What shipped between SESSION_015 and this session (pre-session)

Two commits on `main` resolved SESSION_015's scaffolded targets
before this session opened:

- `7ca7240` — `feat(orient): add current runtime state section`.
  `render_orient(...)` now emits the `## CURRENT RUNTIME STATE`
  block (both full and `--short`). The two failing tests in
  `TestOrientRuntimeState` pass.
- `85d82d1` — `fix(orient): respect canonical_docs when resolving
  source-of-truth anchors`. Follow-up to anchor discovery.

These are not new this session; they are recorded here so the
continuity ledger is honest. With them in place, the previous
"Truth / State Layer — orient side" line item is closed.

## What shipped in this session

### Narrative-anchor freshness check (new doctor check)

New warning-only check: `check_narrative_anchor_freshness`. Compares
the frontmatter date on `docs/*_WHAT_IT_IS.md` (accepts
`last_revised:`, `date:`, or `generated:`) against the latest
handoff's frontmatter `date:`. Equal or newer passes. Older warns.
Missing / unparseable dates skip.

**Why it matters.** The narrative anchor is the conceptual source
of truth. Every shipped handoff has the chance to invalidate
something it claims. When the anchor's date stops moving while
handoffs keep landing, agents reading orient form a stale picture.
This check is the earliest signal that narrative is decaying.

**Wiring.**

- `cli/state.py:25-30` — frontmatter-date field list and ISO date
  regex.
- `cli/state.py:206-256` — `parse_frontmatter_date`,
  `get_narrative_anchor_path`, `get_narrative_anchor_date`,
  `get_handoff_date`. All deterministic, dependency-free.
- `cli/doctor.py:99` — registered in `run_all_checks`.
- `cli/doctor.py:672-756` — `check_narrative_anchor_freshness`.
  Status taxonomy: ok / warning / skipped. Never blocking.
- `tests/test_truth_state.py` — `TestNarrativeAnchorFreshness`
  with 6 cases: no anchor, no anchor date, no handoff date, equal
  dates, anchor newer, anchor older (the warning path).

It fires on this repo right now:

```
! Narrative anchor freshness: narrative anchor
  (docs/CONTEXT_KIT_WHAT_IT_IS.md) dated 2026-04-25 is older than
  latest handoff (SESSION_015) dated 2026-05-07. Sessions have
  moved on; the anchor's frontmatter hasn't.
```

### Session-start drift sweep rule (CLAUDE.md)

`CLAUDE.md:62-67` — new load-bearing convention added at the top
of the "Load-bearing conventions" list:

> Every session starts with a drift sweep. Run `python3
> context_kit.py orient` and read the `## CURRENT RUNTIME STATE`
> block at the bottom. It surfaces stale inventory, test-count
> drift, narrative-anchor date drift, handoff numbering gaps, and
> start-vs-handoff text mismatches before you touch code. Fix
> anything load-bearing before claiming the next slice.

This codifies the discipline the orient runtime-state block was
built for. Until now the discipline existed in agent muscle memory
but wasn't named.

### Inventory regenerated

`docs/CONTEXT_KIT_INVENTORY.md` — refreshed via `inventory --write`.
Test count drift (821 vs 1036) and inventory staleness warnings
both cleared as a result. The fresh inventory now records 1042
tests (1036 prior + 6 added this session).

## Known warnings (after this session)

`python3 context_kit.py doctor` exits 0 with 5 warnings:

1. **Pipeline / runtime flow map** — `docs/CONTEXT_KIT_PIPELINE.md`
   missing. Carried from SESSION_015.
2. **Behavior layer** — `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md`
   missing. Carried from SESSION_015.
3. **Handoff numbering continuity** — `SESSION_005` is missing.
   Pre-existing gap; backfill or document.
4. **Start vs handoff verification** — start-here next task not
   found verbatim in latest handoff. Will need to clear when
   `00-START-NEXT-SESSION.md` is rewritten below.
5. **Narrative anchor freshness** — the new check, fires on the
   repo itself. Clear by reviewing `CONTEXT_KIT_WHAT_IT_IS.md`
   against SESSION_015 + this handoff, updating any drifted
   content, then bumping the `generated:` date.

None are blocking. The new warning is intentional self-application
of the check we just shipped.

## What deferred (not done; documented for the next session)

- **INVENTORY git-SHA drift check** (rec 1 second half). Needs the
  inventory generator to emit a SHA into the managed block first.
  Then doctor can compare against current HEAD. Both halves are
  small; keep them in one session to avoid touching `inventory.py`
  twice.
- **`context-kit handoff write` subcommand** (rec 2). Would
  scaffold the handoff skeleton and re-stamp `last_revised:` /
  `generated:` across anchor docs atomically. Removes the
  forgetting surface that drove this whole drift-prevention thread.
  Bigger scope (touches several docs in one shot) — own session.
- **Promote calibration entries to TRUST_CALIBRATION on
  handoff-write** (rec 3). Tied to rec 2. Skip until rec 2 ships.

## Recommended next work

In strict order:

1. **Decide on the narrative anchor.** Either update
   `docs/CONTEXT_KIT_WHAT_IT_IS.md` content where it has drifted
   from SESSION_015 + SESSION_016, then bump `generated:` to today,
   or rubber-stamp the date with no content change. Either way,
   the new doctor warning clears.
2. **Backfill or document the SESSION_005 gap.** Lowest-effort
   remaining warning. Either write a placeholder
   `SESSION_005_*.md` that names what got skipped (and why), or
   add a one-line note to the narrative anchor that 005 is a
   deliberate gap.
3. **Decide on PIPELINE / BEHAVIOR_LAYER docs** for context-kit
   itself. The chat surface raised the value of the behavior
   layer; deferring this longer reduces signal on the chat work.
4. **INVENTORY git-SHA emit + check** (rec 1 second half). Small
   change to `cli/inventory.py` to write `<!-- Git SHA: <abbrev>
   -->` next to `Last generated:`, plus a matching doctor check.
   Should be one tight session.

After that, the four-rec drift-prevention list from the
sibling-project review is half-done; `context-kit handoff write`
(rec 2) is the obvious next big slice.

## Verification baseline

Run before making changes, then again after:

```bash
python3 -m unittest discover -s tests -t .
python3 context_kit.py doctor
python3 context_kit.py orient --short
python3 context_kit.py inventory --check
```

Expected today: 1042 / 1042 tests, 0 blocking doctor checks, 5
warnings (the five listed above), orient short-mode includes
`## CURRENT RUNTIME STATE`, inventory `--check` exits 0.

## Do not touch

- Release tags or PyPI state. No release until the deferred items
  above are decided.
- `cli/adopt.py` refactor — still on hold.
- Unrelated repos or active dev servers.

## AI Notes

I came in expecting to scaffold a brand-new `context-kit drift`
subcommand because the sibling-project review framed it that way.
Reading the doctor source changed that read — four of the five
proposed drift checks were already there. The honest move was to
fold the genuinely-new check (frontmatter date drift) into doctor
and skip the new subcommand, rather than build a parallel surface
that mostly duplicates doctor. The user agreed when I surfaced it.

One pattern worth flagging for the next agent: the orient
`## CURRENT RUNTIME STATE` block now exists, but `CLAUDE.md` never
told anyone to read it. The new "session starts with a drift
sweep" line plugs that gap. If we keep adding drift checks to
doctor, that line is the thing that turns the checks into actual
behavior — without it, the warnings just sit there.

Calibration note: I almost recommended the user commit + push at
the end of this session and only stopped because they hadn't
asked for it. Sticking to the "wire up the handoff" scope was
correct — committing post-handoff is a different decision.
