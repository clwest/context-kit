# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/handoffs/SESSION_019_FLEET_NETWORK_PATTERN.md` — current continuity handoff
> 4. `docs/handoffs/SESSION_018_SPOKESPERSON_CORPUS_PATTERN.md` — prior session, sibling sub-pattern bundle
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Package version:** `0.15.0` in `pyproject.toml` (unchanged; post-v0.15.0 work is unreleased).
- **Latest tag:** `v0.15.0`.
- **Branch:** `main`. SESSION_019 commit pending push (or already pushed depending on operator).
- **Tests:** **1076 / 1076 passing** via `python3 -m unittest discover -s tests -t .`.
- **Inventory:** fresh — regenerated at the end of SESSION_019 to absorb the four new fleet-network bundle files.
- **Doctor:** 0 blocking, 3 carried warnings — PIPELINE.md missing, BEHAVIOR_LAYER.md missing, SESSION_005 numbering gap. (Test count, inventory freshness, narrative anchor freshness, start-vs-handoff all cleared.)
- **Latest handoff:** `SESSION_019` (`docs/handoffs/SESSION_019_FLEET_NETWORK_PATTERN.md`).

## Next Task — in strict order

### FIRST THING: decide on PIPELINE / BEHAVIOR_LAYER docs for context-kit itself

Pending across SESSIONS 015 → 019 — five sessions of deliberate defer is itself a drift signal. Either:

- **Write them.** `docs/CONTEXT_KIT_PIPELINE.md` (how `orient`, `doctor`, `handoff write`, `inventory`, the bundled sub-patterns flow from invocation → output) and `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md` (voice + UI source-of-truth contract for `chat` and `inspect`). Templates ship in `cli/_pattern/templates/`.
- **Document the deliberate skip.** Add a short paragraph to `CLAUDE.md` or the narrative anchor explaining why these two doc types don't apply to context-kit itself (no LLM pipeline runs server-side; no persona surface), then teach `doctor` to suppress them when the project opts out.

The cost of repeatedly carrying these is now visible — every session's handoff has to acknowledge them. Pick one this session. The decision matters more than the choice.

### Then: backfill SESSION_005 numbering gap

Cheapest clear is a placeholder:

```bash
$EDITOR docs/handoffs/SESSION_005_INTENTIONAL_GAP.md
```

One paragraph explaining the gap (cross-reference CHANGELOG / git log around 2026-02 or whenever that window was). Or add a `Numbering gaps:` line in the narrative anchor and teach `check_handoff_numbering` to suppress it.

### Then: INVENTORY git-SHA drift check (carried from SESSION_016)

Small change:

1. Modify `cli/inventory.py` to emit `<!-- Git SHA: <abbrev> -->` next to `<!-- Last generated: ... -->` inside the managed block.
2. Add a doctor check `check_inventory_git_sha` that compares the SHA in INVENTORY against current HEAD; warning when they differ.

Closes the second half of SESSION_016's rec 1.

### Then: stress-test the fleet-network pattern on a second instance

The CLI proposal at `docs/proposals/fleet-network-subcommand.md` explicitly gates implementation on a second worked instance (different operator/OS/stack mix). Suggested target: a sibling project on a different laptop, or a setup that doesn't include Docker Desktop (the multi-network caveat is Docker-Desktop-specific and may not generalize).

### Then: stress-test the spokesperson-corpus pattern on a second instance

Same validation gate from SESSION_018. Currently only one worked instance (`example-monorepo`). Run the manual `cp -r` recipe against any sibling project with a public-facing AI surface and capture which template shapes felt right vs forced.

## Carried context — sub-pattern bundling workflow

SESSIONS 018 + 019 establish a deliberate workflow for new
sub-patterns:

| Step | What happens | Example |
|---|---|---|
| 1 | Pattern emerges in a sibling project as a worked instance | example-monorepo session 158 (spokesperson), example-monorepo session 1117 (fleet-network) |
| 2 | Sibling distills it into `docs/docs-pattern/<name>/` | example-monorepo/docs/docs-pattern/spokesperson-corpus/, fleet-network/ |
| 3 | context-kit lifts it into `cli/_pattern/<name>/` so `init` ships it | SESSION_018 (spokesperson), SESSION_019 (fleet-network) |
| 4 | Proposal doc captures the future CLI surface | docs/proposals/spokesperson-corpus-subcommand.md, fleet-network-subcommand.md |
| 5 | Wait for a second worked instance | (gate, not yet crossed for either) |
| 6 | Ship the CLI subcommand | (not yet done for either) |

This shape doesn't need a guide doc yet — two data points isn't a pattern — but worth watching as a third sub-pattern emerges.
