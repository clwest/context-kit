---
title: "Session 011 — v0.8.0 released + dogfood batch 2 findings"
date: 2026-04-27
status: v0.8.0 released to PyPI + GitHub; dogfood batch 2 informs v0.9.0 scope
---

# Session 011 — v0.8.0 released + dogfood batch 2

## What shipped

**v0.8.0 is fully released.** All four release surfaces match:

- **Code on `origin/main`:** `203226c chore(release): prepare 0.8.0`
- **PyPI:** [`contextkit-ai 0.8.0`](https://pypi.org/project/contextkit-ai/0.8.0/)
  published. Fresh-venv `pip install contextkit-ai==0.8.0` works
  end-to-end after the typical 1–5 minute index-propagation lag.
- **Git tag:** `v0.8.0` (annotated, message
  "v0.8.0 — adopt decision layer", points at `203226c`).
- **GitHub release:**
  https://github.com/clwest/context-kit/releases/tag/v0.8.0
  — both `.whl` (168,918 bytes) and `.tar.gz` (219,933 bytes)
  attached.

The full per-ship breakdown of v0.8.0 is in
`docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md`. The
release-prep diff (CHANGELOG, README, SKILL, version bump) is
in commit `203226c`.

## Dogfood batch 2 — 7 real-world public repos

Run read-only against a fresh batch of well-known projects in
`~/dev/context-kit-dogfood-repos/`:

  openzeppelin-contracts, ripgrep, next.js, transformers,
  django, react-native, kubernetes

All seven runs completed without errors or crashes. HTML reports
stayed under 50 KB even on next.js (30 workspace children) and
kubernetes (95+ .go files in `cmd/`, 175+ in `pkg/`).

### Results matrix

| repo | detected stack | project type | confidence | actions | notes |
|---|---|---|---|---|---|
| openzeppelin-contracts | JS / Node | JavaScript app/tooling | Medium | 1 | wrong type — clearly Solidity library |
| ripgrep | Unknown | Unclear | Low | 3 | 10 Rust crates surfaced; no Rust signal in adopt |
| next.js | JS / Node | Unclear | Medium | 2 | 30 workspace children render cleanly |
| transformers | Python | Python app/tooling | High | 1 | clean and correct |
| django | **JS / Node** | **JavaScript app/tooling** | **High** | 1 | confidently wrong — JS picked over Python at root |
| react-native | JS / Node | **Full-stack web app** | Medium | 3 | wrong type — Phase 3 over-eager Next.js rule + Phase 4.2 Rule 2 misfire |
| kubernetes | Unknown | Unclear | Low | 2 | clean render of 95+/175+ .go counts; no Go signal |

### Three biggest failure modes (informs v0.9.0 scope)

1. **Django: confidently wrong primary classification.** Root has
   both `package.json` (probably for docs) and Python manifests.
   v0 classifier picks JS first when both are present. Stack
   reality reports "Single-stack project / High" — the worst
   outcome (confidently wrong). The mixed-stack `note` is the
   only signal a reader gets that something is off, and it's
   easy to skim past.

2. **react-native: wrong project type from over-eager Phase 3.**
   `packages/react-native` has `package.json + .tsx` files →
   Phase 3 labels it "Next.js / React web app". `scripts/` has
   `.py` files → `python_anywhere == True`. Phase 4.2 Rule 2
   (Python + Next.js → Full-stack web app) fires. React Native
   is a mobile framework, not a Next.js + Django stack.
   `packages/rn-tester` even surfaces `Gemfile + Podfile +
   .swift` — clear mobile signals that the type rule misses.

3. **openzeppelin-contracts: no Smart-contract library type.**
   189 `.sol` files in `contracts/` + `hardhat.config.js` +
   `foundry.toml` at root. Adopt sees ALL of it (UNRECOGNIZED_
   ECOSYSTEM + MISLEADING_CLASSIFICATION fire correctly, the
   diagnostic signals carry the truth). But Project Type still
   says "JavaScript app/tooling" because the Phase 4.2 rule
   set has no entry for "Solidity library without an apps/
   workspace".

### Three modeling gaps (informs v0.9.0 scope)

1. **No Rust ecosystem signal.** Cargo.toml + `.rs` is in
   DOMAIN_HINTS but not a Phase 3 / Phase 4.2 rule. ripgrep's
   10 crates render cleanly under Workspace children but the
   primary stack stays Unknown.
2. **No Go ecosystem signal.** Same shape. kubernetes's 95+
   `.go` files in `cmd/` + 175+ in `pkg/` get hint lines but
   no primary or project-type promotion.
3. **No Smart-contract library project type.** Listed above as
   the openzeppelin failure mode, but it's also a clean rule
   to write: if root has `hardhat.config.*` OR `foundry.toml`
   AND a depth-1 dir with many `.sol` files, → "Smart
   contract library".

### What the dogfood validated

- **Adopt Summary consolidation (Phase 4.4) holds up at scale.**
  next.js (30 workspace children, 38 needs-clarification) and
  kubernetes (7 needs-clarification with 100s of .go files) both
  produce a tight one-screen summary card.
- **Workspace children rendering is the most useful section on
  language-unsupported workspaces** (ripgrep crates, next.js
  Rust crates). Even when adopt can't classify the project,
  the depth-2 walk surfaces concrete child names.
- **Context-aware actions (Phase 4.6) name real things.**
  react-native gets `packages/assets` and
  `packages/babel-plugin-codegen` named in "Review workspace
  children". openzeppelin gets all 7 needs-clarification dirs
  in "Classify unrecognized directories".
- **No regressions vs. v0.7.0** on the original 5 dogfood repos
  (example-web3-monorepo, turborepo, flutter, expo, solidity-template).

### What batch 2 says about v0.9.0 scope

A "v0.9.0 ecosystem coverage" milestone targeting the three
modeling gaps + the django/react-native fixtures would close the
visible-to-humans-but-invisible-to-adopt cases this batch
revealed. None of these are regressions from v0.8.0 or
earlier — they're the next layer of "obvious gaps" the v0.8.0
decision layer made obvious *because* the report is now coherent
enough to expose them.

Suggested v0.9.0 spec:

- **Phase 5.1 — Rust workspace signal.** New Phase 3 rule for
  `Cargo.toml` (root or workspace child); new Phase 4.5
  inferred-primary target ("Rust workspace / library"); new
  Phase 4.2 project type "Rust app/tooling project".
- **Phase 5.2 — Go signal.** Same pattern with `go.mod`. The
  inferred-primary case is the most important since `go.mod`
  doesn't show up in workspace containers — it's typically at
  root, and adopt's classifier just doesn't recognize it.
- **Phase 5.3 — Smart-contract library project type.** Phase 4.2
  rule keyed off `hardhat.config.*` / `foundry.toml` at root +
  many `.sol` files in any depth-1 dir → "Smart contract
  library / project". Closes openzeppelin's mislabel.
- **Phase 5.4 — django mixed-root fix.** When v0's mixed-stack
  note fires (root has both JS and Python manifests), drop
  Stack reality confidence to Medium AND consider promoting
  the python primary if the depth-1 source-extension count
  for `.py` heavily outweighs `.js`/`.ts`. (Or simpler:
  always prefer Python over JS at root when both are present;
  v0 chose the opposite for historical reasons.)
- **Phase 5.5 — react-native fix.** Tighten the Phase 3
  Next.js fallback rule (`package.json + .tsx`) so it doesn't
  fire when mobile signals are present (Podfile / Gemfile in
  the same child, or `react-native.config.js`).

### Two new test fixtures recommended

1. **react-native (synthesized).** Locks in the
   mobile-vs-web fix; no other fixture covers a `package.json
   + .tsx` workspace child that is NOT a Next.js project.
2. **django (synthesized).** Locks in the mixed-root-language
   behavior; no other fixture covers a project with both a
   root `package.json` for tooling and a clear Python primary.

## Where state actually is right now

- **Branch:** `main`, up to date with `origin/main` (modulo
  this handoff commit).
- **Tests:** **407/407 passing** (unchanged from v0.8.0 prep).
- **Inventory:** regenerated as part of this handoff.
- **PyPI:** **0.8.0 published**.
- **`pyproject.toml`:** version `0.8.0`.
- **CHANGELOG.md:** `[0.8.0]` populated. `[Unreleased]` is
  empty (next entry will be `[0.9.0]`).
- **Tags:** `v0.7.0` and `v0.8.0` both on `origin`.
- **GitHub releases:** v0.7.0 and v0.8.0 both published.

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | this file (SESSION_011) |
| v0.8.0 per-ship breakdown | `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md` |
| v0.7.0 release context | `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` |
| Adopt code | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| Dogfood repos | `~/dev/context-kit-dogfood-repos/` |
| v0.8.0 dogfood HTML reports (latest run) | `/var/folders/.../T/contextkit-adopt-report-*.html` |

## AI Notes

The "Adopt Summary consolidation reveals the next layer of
gaps" pattern was strong this session. v0.7.0 dogfood revealed
the workspace-walking gap; v0.8.0 dogfood revealed the
ecosystem-coverage gap (Rust/Go/Solidity-library). Each release
unlocks a new "this is obvious to a human" set of failure modes
that the prior generation of output couldn't expose because it
was too noisy or fragmented.

The django + react-native cases are the most instructive: both
have CORRECT signals in the diagnostic-signals section that
adopt then ignores when computing project type. The fix isn't
better detection — it's letting the failure taxonomy inform the
project-type rule cascade. That's a small, specific code change
worth doing in v0.9.0 even before the broader ecosystem-coverage
work.
