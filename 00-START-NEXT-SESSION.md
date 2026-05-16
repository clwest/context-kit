# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/handoffs/SESSION_017_HANDOFF_WRITE_SUBCOMMAND.md` — current continuity handoff
> 4. `docs/handoffs/SESSION_016_NARRATIVE_ANCHOR_DRIFT_CHECK.md` — prior session, narrative-anchor freshness check
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Package version:** `0.15.0` in `pyproject.toml` (unchanged; post-v0.15.0 work is unreleased).
- **Latest tag:** `v0.15.0`.
- **Branch:** `main`, ahead of `origin/main` by 1 commit (the SESSION_016 commit). The SESSION_017 commit is uncommitted in the working tree: `cli/handoff.py`, `tests/test_handoff.py`, `context_kit.py`, `CLAUDE.md`, the new handoff, this start-here.
- **Tests:** **1076 / 1076 passing** via `python3 -m unittest discover -s tests -t .`.
- **Inventory:** stale — needs regen (SESSION_017 added 34 tests; the inventory still records 1042).
- **Doctor:** 0 blocking, 5 warnings — unchanged from SESSION_016 (Pipeline doc missing, Behavior layer doc missing, SESSION_005 gap, start-vs-handoff text drift, narrative-anchor freshness).
- **Latest handoff:** `SESSION_017` (`docs/handoffs/SESSION_017_HANDOFF_WRITE_SUBCOMMAND.md`).

## Next Task — in strict order

### FIRST THING: commit the SESSION_017 working tree

```bash
cd /Users/donkeyking/development/context-kit
git status
# expected: 6 modified/added files (handoff.py, test_handoff.py, context_kit.py, CLAUDE.md, the new handoff, this start-here)
git add cli/handoff.py tests/test_handoff.py context_kit.py CLAUDE.md \
        docs/handoffs/SESSION_017_HANDOFF_WRITE_SUBCOMMAND.md \
        00-START-NEXT-SESSION.md
git commit -m "Add `context-kit handoff write` for session-end anchor re-stamp + calibration audit"
```

Do **not** push unless the operator explicitly asks.

### Then: dogfood the new subcommand against context-kit

The narrative-anchor freshness warning fires on this repo
itself. Now that `handoff write` exists, clear the warning the
same way every other project should:

```bash
python3 context_kit.py handoff write 17 --project .
python3 context_kit.py inventory --write   # 34 new tests need to land in inventory
python3 context_kit.py doctor              # confirm freshness warning cleared
```

Stamps `CONTEXT_KIT_WHAT_IT_IS.md` (and the other anchors if
they exist) with `last_revised: 2026-05-15 (SESSION 17)`.
Inventory refresh closes the test-count drift.

### Then: INVENTORY git-SHA drift check

Deferred from SESSION_016. Small change:

1. Modify `cli/inventory.py` to emit `<!-- Git SHA: <abbrev>
   -->` next to the existing `<!-- Last generated: ... -->`
   line inside the managed block.
2. Add a doctor check `check_inventory_git_sha` that
   compares the SHA in INVENTORY against current HEAD.
   Warning when they differ (the operator may have intended
   the drift; warning surfaces the gap).

This closes the second half of SESSION_016's rec 1.

### Then: decide on PIPELINE / BEHAVIOR_LAYER docs

Both have been pending across SESSIONS 015, 016, 017. Either
write `docs/CONTEXT_KIT_PIPELINE.md` and
`docs/CONTEXT_KIT_BEHAVIOR_LAYER.md`, or document the
decision to skip them in `CLAUDE.md` so future sessions stop
re-surfacing the warnings.

### Then: backfill or document the SESSION_005 gap

The doctor `Handoff numbering continuity` warning has been
there for many sessions. Cheapest clear: write a placeholder
`docs/handoffs/SESSION_005_INTENTIONAL_GAP.md` that names the
session number and a one-paragraph explanation (refer to
CHANGELOG / git log around that period). Or add a one-line
note to the narrative anchor calling out the deliberate gap.

## Drift-prevention thread — done

SESSION_016 + SESSION_017 close the original drift-prevention
review out of character-os:

| Rec | What | Status |
|---|---|---|
| 1a | Narrative-anchor freshness doctor check | Done (SESSION 016) |
| 1b | INVENTORY git-SHA drift check | Deferred (queued above) |
| 2 | `handoff write <N>` subcommand re-stamps anchors | **Done (SESSION 017)** |
| 3 | Promote calibration entries at handoff-write time | **Done (SESSION 017, detect-and-report)** |

The detect-and-report shape for rec 3 (vs auto-append-stubs)
was a deliberate design call — see SESSION 017's AI Notes.
