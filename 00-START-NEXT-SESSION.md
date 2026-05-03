# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on counts)
> 3. `docs/handoffs/SESSION_014_V0_12_TO_CURRENT_TRUTH_RESTORE.md` — current continuity backfill
> 4. `docs/handoffs/SESSION_013_V0_10_TO_V0_11_2_BACKFILL.md` — prior backfill through `v0.11.2`
>
> When narrative and runtime disagree, runtime wins.

## Current State

- **Package version:** `0.15.0` in `pyproject.toml`.
- **Latest tag:** `v0.15.0`.
- **Tests:** **818 / 818 passing** via `python3 -m unittest discover -s tests -t .`.
- **Inventory:** regenerated in Session 014; `inventory --check` should be clean.
- **Latest handoff:** `SESSION_014`
  (`docs/handoffs/SESSION_014_V0_12_TO_CURRENT_TRUTH_RESTORE.md`).
- **Unreleased after `v0.15.0`:** pipeline, behavior-layer,
  translation-layer, `translation-init`, Live Chat Mode, and
  `orient --short` / doctor context-shape diagnostics.

## Next Task

Implement a Truth / State Layer for drift detection. The goal is to
prevent the truth-restore drift from recurring by making runtime state
visible during orientation and surfacing documentation inconsistencies
early.

Constraints:

- Do not change CLI behavior or arguments.
- Do not break existing tests.
- All new checks must be non-blocking warnings.
- Follow existing `doctor.py` and `orient.py` patterns.
- No external dependencies.

Scope:

1. Extend `context-kit doctor` with warning-only drift checks:
   version drift, test-count drift, inventory staleness, handoff
   continuity, and start-vs-handoff conflict.
2. Enhance `context-kit orient` output with a `CURRENT RUNTIME STATE`
   block showing version, actual test count, inventory status, latest
   handoff, next expected session, doctor warning count, and drift
   summary.
3. Add small shared helpers only if they keep the implementation
   simpler, such as `_get_current_version()`, `_get_actual_test_count()`,
   and `_get_latest_handoff()`.
4. Add tests for version mismatch detection, test-count mismatch
   detection, missing handoff continuity, orient runtime-state output,
   and drift vs no-drift scenarios.

Keep this deterministic and readable. Do not over-engineer.

The remaining pipeline / behavior-layer doctor warnings are still real,
but they are now secondary to this Truth / State Layer work.

## Verification Baseline

Run before making changes:

```bash
python3 -m unittest discover -s tests -t .
python3 context_kit.py doctor
python3 context_kit.py orient --short
```

## Do Not Touch

- Release tags or PyPI state.
- Unrelated repos or active dev servers.
- Broad refactors, especially `cli/adopt.py`, until the context-layer
  warnings are settled.
