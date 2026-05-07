# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/handoffs/SESSION_015_POST_V0_15_FEATURE_BURST.md` — current continuity handoff
> 4. `docs/handoffs/SESSION_014_V0_12_TO_CURRENT_TRUTH_RESTORE.md` — prior backfill through `v0.15.0`
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Package version:** `0.15.0` in `pyproject.toml` (unchanged; post-v0.15.0 work is unreleased).
- **Latest tag:** `v0.15.0`.
- **Branch:** `main`, in sync with `origin/main`. Working tree clean.
- **Tests:** **1016 / 1018 passing** via `python3 -m unittest discover -s tests -t .`.
- **The 2 failing tests are scaffolded targets, not regressions:**
  - `tests/test_truth_state.py::TestOrientRuntimeState::test_full_orient_includes_runtime_state_block`
  - `tests/test_truth_state.py::TestOrientRuntimeState::test_short_orient_includes_runtime_state_block`
- **Inventory:** stale (`inventory --check` fails). Doctor reports 6 warnings, 0 blocking.
- **Latest handoff:** `SESSION_015` (`docs/handoffs/SESSION_015_POST_V0_15_FEATURE_BURST.md`).

## Next Task — in strict order

### FIRST THING: regenerate the inventory

```bash
python3 context_kit.py inventory --write
python3 context_kit.py inventory --check   # should now exit 0
```

Commit it as its own commit. This clears two doctor warnings
(test-count drift, inventory staleness) and makes the
Truth / State Layer signal meaningful for the next step.

### Then: finish the Truth / State Layer (orient side)

The doctor side of the Truth / State Layer is already complete and
passing. The remaining work is the `orient` `## CURRENT RUNTIME
STATE` block. The two failing tests in
`tests/test_truth_state.py::TestOrientRuntimeState` are the contract.

Both `render_orient(project)` and `render_orient(project, short=True)`
must emit a `## CURRENT RUNTIME STATE` section. Minimum content:

- Current package version (read from `pyproject.toml`).
- Actual test count.
- Inventory status (fresh / stale).
- Latest handoff filename.
- Next expected session number.
- Doctor warning count.
- Drift summary (one line per drift category).

Constraints (carried forward from the prior next-task scope):

- Do not change CLI behavior or arguments.
- Do not break existing tests.
- All new checks must be non-blocking warnings.
- Follow existing `cli/doctor.py` and `cli/orient.py` patterns.
- No external dependencies.
- Reuse the doctor-side helpers. Do not re-shell `unittest discover`
  from inside `orient` — read the inventory's recorded test count and
  optionally compare against a cheap re-discovery.

### Then: close the loop

1. Re-run the verification baseline below.
2. Confirm `00-START-NEXT-SESSION.md` and the latest handoff agree
   on the "next task" so the **start vs handoff verification**
   doctor warning clears.
3. Decide on `docs/CONTEXT_KIT_PIPELINE.md` and
   `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md` for this repo (the new
   chat surface raised the value of the behavior layer).
4. Only after the above: plan a `v0.16.0` release covering verify,
   scoped inspect, connection integrity audit, chat surface, and
   the Truth / State Layer.

## Verification Baseline

Run before making changes, then again after:

```bash
python3 -m unittest discover -s tests -t .
python3 context_kit.py doctor
python3 context_kit.py orient --short
python3 context_kit.py inventory --check
```

## Do Not Touch

- Release tags or PyPI state. No release until the orient block
  lands and the inventory is regenerated.
- The `cli/adopt.py` refactor — still on hold until context-layer
  warnings settle.
- Unrelated repos or active dev servers.
- Broad refactors of any kind during this session.
