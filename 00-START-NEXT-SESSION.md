# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/handoffs/SESSION_018_SPOKESPERSON_CORPUS_PATTERN.md` — current continuity handoff
> 4. `docs/handoffs/SESSION_017_HANDOFF_WRITE_SUBCOMMAND.md` — prior session, handoff-write subcommand
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Package version:** `0.15.0` in `pyproject.toml` (unchanged; post-v0.15.0 work is unreleased).
- **Latest tag:** `v0.15.0`.
- **Branch:** `main` (SESSIONS 016–018 merged in from `feat/spokesperson-corpus-pattern`).
- **Tests:** **1076 / 1076 passing** via `python3 -m unittest discover -s tests -t .`.
- **Inventory:** fresh (regenerated at the end of SESSION_018 — 25 CLI subcommands, 28 cli modules, 17 handoffs, 1076 tests).
- **Doctor:** 0 blocking, 3 carried warnings — PIPELINE.md missing, BEHAVIOR_LAYER.md missing, SESSION_005 numbering gap. (Narrative-anchor freshness + test-count drift + start-vs-handoff drift cleared in SESSION_018.)
- **Latest handoff:** `SESSION_018` (`docs/handoffs/SESSION_018_SPOKESPERSON_CORPUS_PATTERN.md`).

## Next Task — in strict order

### FIRST THING: decide on PIPELINE / BEHAVIOR_LAYER docs for context-kit itself

Both warnings have been pending across SESSIONS 015 → 018. Either:

- **Write them.** `docs/CONTEXT_KIT_PIPELINE.md` (how `orient`, `doctor`, `handoff write`, `inventory` actually flow from invocation → output) and `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md` (voice + UI source-of-truth contract for `chat` and `inspect`). Templates ship in `cli/_pattern/templates/`.
- **Document the deliberate skip.** Add a short paragraph to `CLAUDE.md` or to the narrative anchor explaining why these two doc types don't apply to context-kit itself (no LLM pipeline runs server-side here; no persona surface), then teach `doctor` to suppress them when the project opts out.

Either path closes two of the three remaining doctor warnings. Pick one this session — repeatedly deferring this warning is itself a drift signal.

### Then: backfill SESSION_005 numbering gap

Cheapest clear is a placeholder:

```bash
$EDITOR docs/handoffs/SESSION_005_INTENTIONAL_GAP.md
```

One paragraph explaining the gap (cross-reference CHANGELOG / git log around that window). Or add a `Numbering gaps:` line in the narrative anchor calling out `SESSION_005` and teach `check_handoff_numbering` to suppress it.

### Then: INVENTORY git-SHA drift check (carried from SESSION_016)

Small change:

1. Modify `cli/inventory.py` to emit `<!-- Git SHA: <abbrev> -->` next to `<!-- Last generated: ... -->` inside the managed block.
2. Add a doctor check `check_inventory_git_sha` that compares the SHA in INVENTORY against current HEAD; warning when they differ.

Closes the second half of SESSION_016's rec 1.

### Then: stress-test the spokesperson-corpus pattern on a second project

The pattern bundled in SESSION_018 has only one worked instance (`unified-donkey-betz`). The CLI proposal at `docs/proposals/spokesperson-corpus-subcommand.md` recommends waiting for a second instance before locking the `context-kit spokesperson` API surface. Suggested next target: pick any sibling project with a public-facing surface and run the manual `cp -r` recipe, then capture which template shapes felt right vs forced.

## Carried context

The drift-prevention thread is now fully closed:

| Rec | What | Status |
|---|---|---|
| 1a | Narrative-anchor freshness doctor check | Done (SESSION 016) |
| 1b | INVENTORY git-SHA drift check | Carried above |
| 2  | `handoff write <N>` subcommand re-stamps anchors | Done (SESSION 017) |
| 3  | Promote calibration entries at handoff-write time | Done (SESSION 017, detect-and-report) |

SESSION_018's contribution was content (`cli/_pattern/spokesperson-corpus/`) plus housekeeping, not new infrastructure. The bundled sub-pattern shape is new and worth watching as more sub-patterns emerge.
