# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. `docs/handoffs/SESSION_012_V0_9_0_RELEASE_CLOSEOUT.md` — what last session shipped + future ideas
> 4. `docs/handoffs/SESSION_011_V0_8_0_RELEASED_AND_DOGFOOD_BATCH_2.md` — v0.9.0 dogfood-driven plan
> 5. `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` — v0.8.0 per-ship breakdown
> 6. `docs/proposals/SESSION_009_ADOPT.md` — full adopt design (deep reference)
>
> When any other doc disagrees with the above, the above wins.

---

## Where state actually is right now

**v0.9.0 is fully released.** Live on PyPI, tagged `v0.9.0` on
`origin`, GitHub release attached. Nothing pending.

- **Latest commit:** `3b140f3 chore(release): prepare 0.9.0` —
  matches `origin/main` (modulo this handoff commit).
- **Tests:** **424/424 passing.**
- **Inventory:** current.
- **PyPI:** **0.9.0 published.** `pip install --no-cache-dir
  --index-url https://pypi.org/simple/ contextkit-ai==0.9.0`
  works in a fresh venv. (Default index-url version listing
  may lag by 1–10 minutes after a release; the explicit
  `--index-url` form bypasses cache.)
- **`pyproject.toml`:** `0.9.0`.
- **CHANGELOG.md:** `[0.9.0]` populated; `[Unreleased]` empty.
- **Tags / releases:** v0.7.0, v0.8.0, v0.9.0 — all on
  `origin` with GitHub release pages.

## What v0.9.0 delivered (one-line)

`context-kit adopt` got an ecosystem-coverage milestone: Rust
support, Go support, a Smart contract project type, mixed-root
JS/Python source-dominance correction, and a React Native vs
Next.js disambiguation. The v0.8.0 decision-layer machinery
(Adopt Summary card with Type / Structure / Reality / Next
actions) carries the new behavior with no UI changes; the
failure taxonomy is unchanged.

## Live dogfood snapshot (after v0.9.0)

| repo | detection | project type |
|---|---|---|
| django | Python (pyproject.toml) | Python app/tooling project |
| react-native | JavaScript / Node.js | Mobile app suite |
| openzeppelin-contracts | JavaScript / Node.js | Smart contract project |
| ripgrep | Rust (Cargo.toml) | Rust workspace / library |
| kubernetes | Go (go.mod) | Go project |
| transformers | Python (pyproject.toml) | Python app/tooling project |
| fns-monorepo | JavaScript / Node.js | Web3 dApp |
| flutter-monorepo-example | Flutter / Dart (inferred) | Mobile app suite |
| turborepo-next-django-starter | JavaScript / Node.js | Full-stack web app |
| aave-v3-core | JavaScript / Node.js | Smart contract project |
| solidity-template | JavaScript / Node.js | Smart contract project |
| v3-core | JavaScript / Node.js | Smart contract project |
| next.js | JavaScript / Node.js | Unclear project type |
| expo-monorepo-example | JavaScript / Node.js | Unclear project type |

## Suggested next session focus (no commitment yet)

**Wait for Austin's real-user feedback before scoping v0.10.0.**
The v0.9.0 dogfood was internal-only. Real adoption will surface
friction the dogfood can't simulate. Don't pre-empt it with
speculative work.

In parallel (low-risk while waiting):

1. **Vyper as a first-class EVM language.** New Phase 3 label
   "Vyper contract" alongside Solidity; expand Smart contract
   project type rule to accept either signal. See SESSION_012
   AI Notes for the suggested approach.
2. **Better Next.js hybrid classification.** next.js currently
   stays "Unclear project type" honestly but unhelpfully.
   Either invent a "JavaScript framework with native engine"
   project type or accept the current behavior as the
   long-term answer. Decide before the next dogfood batch.
3. **Release tooling.** The PyPI propagation lag + interactive
   twine prompt have bitten two releases now. A small
   `context-kit publish-check` helper that polls PyPI's JSON
   API and runs the canonical-index install in a throwaway
   venv would close the loop and make the next release
   one-command after twine.

## Process notes from v0.9.0

- **Always run the test suite ≥ 3 consecutive times during
  release prep.** v0.9.0's smart-contract reason text was
  flaky (Python set-iteration non-determinism) and only
  surfaced because release prep ran the suite multiple times.
  Caught + fixed pre-publish; would have shipped if release
  prep had stopped at one green run.
- **PyPI install verification:** use `--index-url
  https://pypi.org/simple/` to bypass cache propagation lag.
  The default `pip install` may show stale versions for up to
  ~10 minutes after upload.

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | `docs/handoffs/SESSION_012_V0_9_0_RELEASE_CLOSEOUT.md` |
| v0.8.0 dogfood + v0.9.0 plan | `docs/handoffs/SESSION_011_V0_8_0_RELEASED_AND_DOGFOOD_BATCH_2.md` |
| v0.8.0 per-ship breakdown | `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` |
| v0.7.0 release context | `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` |
| Adopt code | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| Adopt design | `docs/proposals/SESSION_009_ADOPT.md` |
| Dogfood repos | `/Users/donkeyking/development/context-kit-dogfood-repos/` |
| Recent commits | `git log --oneline -16` |

## Load-bearing reminder

`docs/CONTEXT_KIT_INVENTORY.md` is auto-generated from
`context-kit inventory --write`. Re-run it whenever
code/test/doc counts change so the runtime anchor stays
accurate. CI (and the project's own discipline) treats it as
the source of truth — when narrative docs disagree with the
inventory, the inventory wins.
