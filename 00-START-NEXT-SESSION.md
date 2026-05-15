# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/handoffs/SESSION_016_NARRATIVE_ANCHOR_DRIFT_CHECK.md` — current continuity handoff
> 4. `docs/handoffs/SESSION_015_POST_V0_15_FEATURE_BURST.md` — prior session, post-v0.15.0 feature burst
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Package version:** `0.15.0` in `pyproject.toml` (unchanged; post-v0.15.0 work is unreleased).
- **Latest tag:** `v0.15.0`.
- **Branch:** `main`. Uncommitted working tree from SESSION_016: `CLAUDE.md`, `cli/doctor.py`, `cli/state.py`, `docs/CONTEXT_KIT_INVENTORY.md`, `tests/test_truth_state.py` plus the new handoff + this file.
- **Tests:** **1042 / 1042 passing** via `python3 -m unittest discover -s tests -t .`.
- **Inventory:** fresh — `inventory --check` exits 0.
- **Doctor:** 0 blocking, 5 warnings (Pipeline doc missing, Behavior layer doc missing, SESSION_005 gap, start-vs-handoff text, narrative-anchor freshness).
- **Latest handoff:** `SESSION_016` (`docs/handoffs/SESSION_016_NARRATIVE_ANCHOR_DRIFT_CHECK.md`).

## Next Task — in strict order

### FIRST THING: commit the SESSION_016 working tree

Five source files + the new handoff + this start-here are
uncommitted. Stage and commit them as one logical unit
("Add narrative-anchor freshness drift check + session-start
sweep rule") before doing anything else. Do **not** force push.
Do **not** push at all unless the user explicitly asks.

```bash
git status
# expected: 7 modified/added files, all listed above
git add CLAUDE.md cli/doctor.py cli/state.py \
        docs/CONTEXT_KIT_INVENTORY.md tests/test_truth_state.py \
        docs/handoffs/SESSION_016_NARRATIVE_ANCHOR_DRIFT_CHECK.md \
        00-START-NEXT-SESSION.md
git commit -m "Add narrative-anchor freshness drift check + session-start sweep rule"
```

### Then: clear the narrative-anchor freshness warning

The check we just added fires on this repo. Two options:

1. Read `docs/CONTEXT_KIT_WHAT_IT_IS.md` against
   `SESSION_015` + `SESSION_016` and update any content that has
   actually drifted (e.g. references to inventory being
   hand-maintained — it isn't; the auto-block has been generated
   for months). Then bump frontmatter `generated:` to today.
2. If review shows the body is still accurate, rubber-stamp the
   `generated:` date with no content change.

Either way, `python3 context_kit.py doctor` should drop from 5
warnings to 4.

### Then: backfill or document the SESSION_005 gap

The doctor `Handoff numbering continuity` warning has been there
for many sessions. Cheapest clear: write a placeholder
`docs/handoffs/SESSION_005_INTENTIONAL_GAP.md` that names the
session number and a one-paragraph explanation (refer to
CHANGELOG / git log around that period). Or add a one-line note to
the narrative anchor calling out the deliberate gap.

### Then: decide on PIPELINE / BEHAVIOR_LAYER docs

The chat surface raised the value of writing a behavior layer for
context-kit itself — voice rules, source-of-truth display
contract, constraint preservation. Either write
`docs/CONTEXT_KIT_BEHAVIOR_LAYER.md` (and the matching
`PIPELINE.md`), or document the decision to skip them so future
sessions stop re-surfacing the warning.

### Then: ship the INVENTORY git-SHA drift check

The second half of drift-prevention rec 1 (deferred from
SESSION_016). Small change:

1. Modify `cli/inventory.py` to emit `<!-- Git SHA: <abbrev>
   -->` next to the existing `<!-- Last generated: ... -->` line
   in the managed block.
2. Add `check_inventory_git_sha_drift(project)` to
   `cli/doctor.py` — warns when the recorded SHA differs from
   current HEAD by more than N commits, or when uncommitted
   changes exist alongside a recorded SHA.
3. Tests in `tests/test_doctor.py` covering fresh / stale /
   no-SHA paths.

Should fit in one session.

## Verification Baseline

Run before making changes, then again after:

```bash
python3 -m unittest discover -s tests -t .
python3 context_kit.py doctor
python3 context_kit.py orient --short
python3 context_kit.py inventory --check
```

Expected today: 1042 / 1042 tests, 0 blocking, 5 warnings (or 4
once the narrative anchor is touched), orient short-mode includes
`## CURRENT RUNTIME STATE`, `inventory --check` exits 0.

## Do Not Touch

- Release tags or PyPI state. No release until the deferred items
  in SESSION_016's AI Notes are resolved.
- The `cli/adopt.py` refactor — still on hold.
- Force-push or `git reset --hard` of any kind without explicit
  user direction.
- Unrelated repos or active dev servers.
