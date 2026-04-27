# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. `docs/handoffs/SESSION_011_V0_8_0_RELEASED_AND_DOGFOOD_BATCH_2.md` — what last session shipped + dogfood findings
> 4. `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` — v0.8.0 per-ship breakdown
> 5. `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` — v0.7.0 release context
> 6. `docs/proposals/SESSION_009_ADOPT.md` — full adopt design (deep reference)
>
> When any other doc disagrees with the above, the above wins.

---

## Where state actually is right now

**v0.8.0 is fully released.** Live on PyPI, tagged `v0.8.0` on
`origin`, GitHub release attached. Ready for v0.9.0 work.

- **Latest commit:** `203226c chore(release): prepare 0.8.0` —
  matches `origin/main` (modulo the SESSION_011 handoff commit
  that lands with this doc).
- **Tests:** **407/407 passing.**
- **Inventory:** current.
- **PyPI:** **0.8.0 published.** `pip install
  contextkit-ai==0.8.0` works in a fresh venv.
- **`pyproject.toml`:** `0.8.0`.
- **CHANGELOG.md:** `[0.8.0]` populated; `[Unreleased]` is
  empty and ready for the next bump.
- **Tags / releases:** `v0.7.0` and `v0.8.0` both on `origin`
  with GitHub release pages.

## What v0.8.0 delivered (one-line)

`context-kit adopt` got a depth-2 workspace walk plus a derived
decision layer (Adopt Summary card with Type / Structure /
Reality / Next actions). Detection logic and failure taxonomy
unchanged. One new classification behavior: workspace-aware
primary inference for Flutter / Solidity / Next.js when root
detection is unknown.

## What batch 2 dogfood revealed (informs v0.9.0)

Seven public repos exercised in
`/Users/donkeyking/development/context-kit-dogfood-repos/`:
openzeppelin-contracts, ripgrep, next.js, transformers, django,
react-native, kubernetes. **No regressions, no crashes, all
reports stayed under 50 KB.** What surfaced were *modeling
gaps*, not bugs:

- **django** ends up as `JavaScript app/tooling project / High
  confidence` because the v0 classifier picks JS over Python at
  root when both are present. Confidently wrong.
- **react-native** ends up as `Full-stack web app` because
  Phase 3's `package.json + .tsx` rule misfires on
  `packages/react-native` (a mobile framework, not a web app).
- **openzeppelin-contracts** ends up as `JavaScript app/tooling
  project` even though every diagnostic signal correctly
  identifies it as a Solidity smart-contract library.
- **ripgrep** and **kubernetes** stay `Unknown / Unclear`
  because Cargo.toml / go.mod aren't in the Phase 3 / Phase
  4.2 rule set.

Full per-repo breakdown + reproducible HTML report paths in
SESSION_011.

## Suggested v0.9.0 scope

**Theme: "ecosystem coverage."** Add the rules that v0.8.0's
clean reports made obviously missing.

- **Phase 5.1 — Rust signal.** New Phase 3 rule for `Cargo.toml`
  + `.rs`; new Phase 4.5 inferred-primary "Rust workspace /
  library"; new Phase 4.2 type "Rust app/tooling project".
- **Phase 5.2 — Go signal.** Same shape with `go.mod`. Critical
  for kubernetes and many infra-style repos.
- **Phase 5.3 — Smart-contract library type.** Phase 4.2 rule
  keyed off `hardhat.config.*` / `foundry.toml` at root +
  `.sol` files. Closes openzeppelin's mislabel.
- **Phase 5.4 — django mixed-root fix.** When v0's mixed-stack
  note fires, drop Stack reality confidence to Medium AND
  consider promoting Python over JS when source-extension
  count heavily favors Python.
- **Phase 5.5 — react-native fix.** Tighten Phase 3 Next.js
  rule (`package.json + .tsx`) to NOT fire when mobile signals
  are present (Podfile / Gemfile in the same child or
  `react-native.config.js`).

Two new test fixtures recommended (synthesized, not real
clones): **react-native-shape** and **django-shape**. Both lock
in fixes for failures that no current fixture covers.

## Process notes for next session

- **Don't ship a v0.8.1.** v0.8.0 is stable and shipped — the
  modeling gaps above aren't regressions, they're the next
  layer of work. Skip straight to v0.9.0 planning + ships.
- **The django/react-native fixes are small and specific** —
  worth doing first as they unblock confidently-wrong outputs
  on real-world projects. The Rust/Go ecosystem signals are
  bigger but less urgent (those reports are honestly Unknown,
  not confidently wrong).

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | `docs/handoffs/SESSION_011_V0_8_0_RELEASED_AND_DOGFOOD_BATCH_2.md` |
| v0.8.0 per-ship breakdown | `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` |
| v0.7.0 release context | `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` |
| Adopt code | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| Adopt design | `docs/proposals/SESSION_009_ADOPT.md` |
| Dogfood repos | `/Users/donkeyking/development/context-kit-dogfood-repos/` |
| Recent commits | `git log --oneline -16` |

## Load-bearing reminder

`docs/CONTEXT_KIT_INVENTORY.md` is auto-generated from
`context-kit inventory --write`. Re-run it whenever code/test/doc
counts change so the runtime anchor stays accurate. CI (and the
project's own discipline) treats it as the source of truth — when
narrative docs disagree with the inventory, the inventory wins.
