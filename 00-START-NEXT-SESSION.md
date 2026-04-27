# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` — what last session shipped
> 4. `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` — v0.7.0 release context
> 5. `docs/proposals/SESSION_009_ADOPT.md` — full adopt design (deep reference)
>
> When any other doc disagrees with the above, the above wins.

---

## Where state actually is right now

**v0.8.0 is built and pushed to `origin/main` but NOT released.**
PyPI is still on **0.7.0**. The decision layer is complete:
twelve incremental ships across Phases 1–4.6 turn `adopt`'s
output into a single read-once "Adopt Summary" card with
context-aware suggested actions.

- **Branch:** `main`, up to date with `origin/main`.
- **Tests:** **407/407 passing.**
- **Inventory:** current.
- **PyPI:** still **0.7.0**. No v0.8.0 publish yet.
- **Version in `pyproject.toml`:** still `0.7.0` — needs bump
  before release prep.
- **CHANGELOG.md:** `[0.7.0]` is the latest entry. v0.8.0 block
  not written yet.
- **Tags:** `v0.7.0` is the latest. No `v0.8.0` tag yet.
- **GitHub release:** `v0.7.0` tag exists on `origin` but the
  release page itself was created in Session 009. No v0.8.0
  release.

## What v0.8.0 ships (one-line)

`context-kit adopt` gains a depth-2 workspace walk plus a derived
decision layer (Adopt Summary card with Type / Structure /
Reality / Next actions, all named to the concrete project's
content). Detection logic and failure taxonomy are unchanged.
Classification gains exactly one new behavior: workspace-aware
primary inference for Flutter / Solidity / Next.js when root
detection is unknown.

Per-ship breakdown lives in
`docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md`.

## Live dogfood snapshot (all 8 repos generating reports cleanly)

| repo | project type | next-action count |
|---|---|---|
| fns-monorepo | Web3 dApp | 3 |
| turborepo-next-django-starter | Full-stack web app | 3 |
| flutter-monorepo-example | Mobile app suite | 3 |
| expo-monorepo-example | Unclear project type | 1 |
| solidity-template | JavaScript app/tooling project | 1 |
| aave-v3-core | JavaScript app/tooling project | 1 |
| openzeppelin-contracts | JavaScript app/tooling project | 1 |
| v3-core | JavaScript app/tooling project | 1 |

## Next steps (in order)

1. **Final dogfood / visual review** of the 8 HTML reports.
   Regenerate with `python3 context_kit.py adopt <repo> --html
   --no-browser` from each dogfood dir, then `open` the report
   paths printed at the end. Look for: regression on plain
   non-monorepo repos, copy issues, broken Adopt Summary
   layout, missing dir names in actions.
2. **Decide whether v0.8.0 is release-ready.** Rough checklist:
   - Tests green (already true: 407/407).
   - Dogfood reports look right end-to-end.
   - No regression vs. v0.7.0 on plain repos.
   - The known limitation (single-Solidity-repo
     misclassification) is acceptable for v0.8 or worth one
     more ship first.
3. **If yes, release prep:**
   - Bump `pyproject.toml` version `0.7.0 → 0.8.0`.
   - Write `[0.8.0]` block in `CHANGELOG.md` mirroring the
     "What shipped" list in SESSION_010 handoff.
   - Build wheel + sdist; `twine check`.
   - Publish to PyPI; tag `v0.8.0`; push tag; create GitHub
     release attached to the tag (mirror the v0.7.0 process).

## Open design questions (deferred to v0.9+)

- **Single-Solidity-repo classification.** Hardhat / Foundry
  repos without an `apps/` workspace fall into the JS
  app/tooling bucket today. A future Phase 4.x rule could
  check root for `hardhat.config.*` / `foundry.toml` and
  override the project type.
- **Expo workspace inference.** Phase 4.5 deliberately leaves
  Expo out of the inferred-primary set (only Flutter /
  Solidity / Next.js). expo-monorepo-example currently shows
  "Unclear project type" as a result. Worth revisiting once
  Phase 3 has a stronger Expo signal than just `app.config.*`.
- **Framework detection inside manifests** (proposal §15 #5).
  Still deferred. Pairs naturally with the workspace-walking
  work now that depth-2 is in place.
- **`[adopt: please describe]` doctor check** (proposal §15 #6).
- **Wizard branch for adopt** (proposal §15 #7).

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` |
| v0.7.0 release context | `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` |
| Adopt code | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| Full adopt design | `docs/proposals/SESSION_009_ADOPT.md` |
| Recent commits | `git log --oneline -16` |
| Dogfood repos | `/Users/donkeyking/development/context-kit-dogfood-repos/` |

## Load-bearing reminder

`docs/CONTEXT_KIT_INVENTORY.md` is auto-generated from
`context-kit inventory --write`. Re-run it whenever code/test/doc
counts change so the runtime anchor stays accurate. CI (and the
project's own discipline) treats it as the source of truth — when
narrative docs disagree with the inventory, the inventory wins.
