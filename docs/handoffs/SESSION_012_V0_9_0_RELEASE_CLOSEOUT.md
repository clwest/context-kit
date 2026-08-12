---
title: "Session 012 — v0.9.0 ecosystem coverage release closeout"
date: 2026-04-27
status: v0.9.0 fully released to PyPI + GitHub
---

# Session 012 — v0.9.0 ecosystem coverage release closeout

## What shipped

**v0.9.0 is fully released.** All four release surfaces match:

- **Code on `origin/main`:** `3b140f3 chore(release): prepare 0.9.0`
- **PyPI:** [`contextkit-ai 0.9.0`](https://pypi.org/project/contextkit-ai/0.9.0/)
  published. Fresh-venv install verified end-to-end:
  `Name: contextkit-ai, Version: 0.9.0`, `context-kit adopt --help`
  runs.
- **Git tag:** `v0.9.0` (annotated, message
  "v0.9.0 — ecosystem coverage", points at `3b140f3`).
- **GitHub release:**
  https://github.com/clwest/context-kit/releases/tag/v0.9.0
  — both `.whl` (172,490 bytes) and `.tar.gz` (227,139 bytes)
  attached. Notes are the full CHANGELOG `[0.9.0]` block
  (130 lines, themed by ecosystem area).

**424/424 tests passing** at release.

## Key fixes in v0.9.0

This release was a single ecosystem-coverage milestone driven
by the SESSION_011 dogfood batch on real public repos. Five
planned phases shipped; one prep-caught determinism fix.

### Phase 5.1 — Django mixed-root correction
`fc57f0a` — when both root JavaScript (`package.json`) and
root Python manifests are present, walk depth-2 source evidence
(≤ 5000 files) and pick the dominant side. v0 always picked
JavaScript, which produced the django/django dogfood failure
where 1229 .py files silently lost to a tooling-only root
package.json. Stack reality confidence is also capped at
Medium for any mixed-root case.

### Phase 5.2 — Rust support
Part of `24cf600`. New language detection (`Cargo.toml` →
"rust"), new workspace child label ("Rust crate"), Phase 4.5
inferred-primary mapping ("Rust workspace"), Phase 4.2 project
type ("Rust workspace / library"). Rule fires only when Rust
IS the primary identity — JS / Python primary repos with
auxiliary Rust tooling (next.js's `crates/turbopack-*`) fall
through to the JS / Python rules instead.

### Phase 5.3 — Go support
Part of `24cf600`. Root `go.mod` → "go" language, new Phase
4.2 project type "Go project". No workspace-child Go rule;
Go workspaces are rare enough to defer.

### Phase 5.4 — Smart contract project type
Part of `24cf600`. New Phase 4.2 rule between Web3 dApp and
Full-stack web app. Fires on workspace Solidity, OR a depth-1
dir with ≥ 10 `.sol` files, OR root has hardhat / foundry /
truffle / brownie config (visible via failures-parameter).
`derive_project_type` signature extended to take optional
`failures` so the rule can read failure examples that aren't
tracked in `stack.signals`.

### Phase 5.5 — React Native vs Next.js correction
Part of `24cf600`. New Phase 3 label "React Native / mobile
framework" fires BEFORE the Next.js rule when mobile signals
are present (`metro.config.*`, `react-native.config.*`,
`Podfile`, `Gemfile`, `.swift`, `.kt`). Mobile app suite
generalized to fire on Flutter OR React Native workspace
signals.

### Determinism fix (caught during release prep)
`664f8ee` — derive_project_type's smart-contract rule picked
an arbitrary element from a Python set (`failure_examples &
_SMART_CONTRACT_ROOT_CONFIGS`) when more than one framework
config was at root. Set iteration is non-deterministic, so the
same project (e.g. openzeppelin-contracts with both
`hardhat.config.js` AND `foundry.toml`) would render different
reason text across adopt runs. Sorted the intersection
alphabetically; same project now produces the same reason
every run. Test went from flaky 2/5 to stable 5/5.

## Real-world dogfood before/after

  django:                JS app/tooling High  -> Python app/tooling Medium
  react-native:          Full-stack web app   -> Mobile app suite
  openzeppelin-contracts: JavaScript app/tooling -> Smart contract project
  ripgrep:               Unclear / Low        -> Rust workspace / library
  kubernetes:            Unclear / Low        -> Go project (High)
  transformers:          unchanged (Python / High)
  example-web3-monorepo:          unchanged (Web3 dApp)

Beneficial side effects on existing dogfood repos: aave-v3-core,
solidity-template, and v3-core all flipped from "JavaScript
app/tooling project" to "Smart contract project". next.js
correctly stays "Unclear project type" — it's a real JS+Rust
hybrid that doesn't fit any clean category, and the Rust-rule
guard prevents misclassifying it as a Rust project.

## Process notes from this release

- **PyPI propagation lag was longer than v0.8.0.** Default
  `pip install --no-cache-dir contextkit-ai==0.9.0` initially
  failed because pip's cached versions list still topped at
  `0.8.0`. `pip install --no-cache-dir --index-url
  https://pypi.org/simple/ contextkit-ai==0.9.0` worked
  immediately. Worth automating in any release tooling that
  tries to verify the upload before tagging.
- **Twine upload requires interactive terminal** for the API
  token prompt. The session's bash environment can't echo
  password input, so the user runs `! python3 -m twine upload
  dist/*` themselves. Documented for future release sessions.
- **Determinism flakes surface during release prep.** The
  smart-contract reason text only flaked because v0.9.0
  release prep ran the suite multiple times in a row to
  validate clean state. Worth running the suite ≥ 3 consecutive
  times during every release-prep checklist before considering
  it green.

## Known future ideas

Captured here so they don't get lost; none are committed work
yet. Each is independent and can ship in any order.

### Vyper as a first-class EVM language

Today the Smart-contract project type rule treats `.sol`
(Solidity) as the only contract evidence. Vyper (`.vy`) is a
real and growing EVM ecosystem with different semantics,
tooling (`brownie`, `ape`), and conventions. Bundling Vyper
under "Solidity / EVM smart contracts" would mislead users.

Suggested approach: new Phase 3 workspace child label "Vyper
contract" alongside "Solidity / EVM smart contracts"; new
Phase 4.5 inferred-primary; expand the Smart contract project
type rule to accept either signal. Reason text adapts to name
the language.

### Better Next.js hybrid classification

next.js currently lands in "Unclear project type" because it
has both Rust crates (Turbopack source) AND Next.js apps with
no clean primary identity. The current rule cascade has the
Rust-rule guard "Rust must be primary" which correctly
prevents a Rust-only mislabel — but leaves no positive label
for the JS+Rust hybrid case.

A "JavaScript framework with native engine" or "JS / Rust
hybrid" project type would catch this honestly. Risk: scope
creep — adopt's Phase 4.2 rule set is intentionally small and
adding too many hybrid types dilutes the signal.

### Release tooling for PyPI propagation / index verification

The two install-time gotchas above (cache lag + interactive
twine prompt) suggest a small `context-kit publish-check`
helper that:

- Polls `https://pypi.org/pypi/contextkit-ai/0.9.0/json` until
  it 200s, with a sane timeout.
- Runs the canonical-index `pip install` in a throwaway venv
  and asserts the version + entry point.
- Optionally chains into `git tag` + `git push origin <tag>` +
  `gh release create` so the full publish sequence is one
  command after twine succeeds.

### Real user feedback from Austin

Austin is the first non-author user lined up to try
`context-kit adopt` on real projects. Capture the friction
points, mislabels, and confusing copy verbatim — that's the
strongest signal for what to ship in v0.10.0+. Don't pre-empt
his findings with speculative work; wait for the actual
feedback session, then fold the results into the next handoff.

## Where state actually is right now

- **Branch:** `main`, up to date with `origin/main` (modulo
  this handoff commit).
- **Tests:** **424/424 passing** at release.
- **PyPI:** **0.9.0 published**.
- **`pyproject.toml`:** version `0.9.0`.
- **CHANGELOG.md:** `[0.9.0]` populated. `[Unreleased]` is
  empty (next entry will be `[0.10.0]`).
- **Tags:** `v0.7.0`, `v0.8.0`, `v0.9.0` all on `origin`.
- **GitHub releases:** all three published with assets.

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | this file (SESSION_012) |
| v0.9.0 dogfood-driven plan | `docs/handoffs/SESSION_011_V0_8_0_RELEASED_AND_DOGFOOD_BATCH_2.md` |
| v0.8.0 per-ship breakdown | `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` |
| v0.7.0 release context | `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` |
| Adopt code | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| Dogfood repos | `~/dev/context-kit-dogfood-repos/` |

## AI Notes

The v0.9.0 cycle reinforced the "consolidation reveals next
gaps" pattern — each release exposes the next layer of
"obvious to a human, currently invisible to adopt" cases
because the prior generation of output is finally clean
enough to make the gap visible. v0.7.0 dogfood revealed the
workspace-walking gap; v0.8.0 dogfood revealed the
ecosystem-coverage gap; v0.9.0 dogfood (when Austin runs it)
will reveal whatever comes next.

The determinism flake is the kind of bug that ONLY shows up
under release-prep stress (running the suite 5+ times in a
row). Worth keeping that as a discipline at every release
boundary even when it feels like overkill — set-iteration
non-determinism is a recurring trap in Python codebases that
do failure-set or label-set intersections.

`derive_project_type` is starting to grow rules that depend on
context outside `stack` and `reality` (failures, in v0.9.0).
Worth watching if a third "outside-input" rule appears — that
might be the signal to refactor toward a richer
`AdoptContext` object that bundles all the upstream
derivations cleanly, instead of growing the parameter list.
