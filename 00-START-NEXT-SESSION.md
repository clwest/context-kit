# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/CONTEXT_KIT_PIPELINE.md` — runtime flow map
> 4. `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md` — terminal/report contract
> 5. `docs/CONTEXT_KIT_TRANSLATION_LAYER.md` — audience contract
> 6. `docs/handoffs/SESSION_023_SESSION_005_GAP_CLOSED.md` — current continuity handoff
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Version:** `0.16.0`; documentation-only completion of Sessions 022 and 023.
- **Decision:** historical gap note records only evidence supported by Sessions 004, 006 and the changelog; original Session 005 details remain unavailable.
- **Working tree / delivery:** all intended documentation staged on `main`; commit and push pending after successful checks. The prior environment restrictions are cleared.
- **Tests:** `python3 -m unittest discover -s tests -t .` exited 0: `Ran 1116 tests in 10.815s`, `OK`, including the three live-server classes blocked in the prior attempt.
- **Checks:** inventory current (175 tracked files, 23 handoffs); verify exit 0 (1 VERIFIED, 4 DOC_ONLY, 0 CONFLICT, 1 UNKNOWN); doctor exit 0 (14 OK, 0 blocking, 0 warnings, 4 skipped); staged and working diff whitespace checks pass.
- **Latest handoff:** `SESSION_023`; includes the preserved Session 022 pipeline/behavior contracts and README/CLAUDE corrections.

## Next Task — in strict order

### FIRST THING: INVENTORY git-SHA drift check (carried from SESSION_016)

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
