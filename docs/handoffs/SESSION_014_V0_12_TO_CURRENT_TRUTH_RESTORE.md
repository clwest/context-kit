---
title: "Session 014 — v0.12.0 → current truth restore"
date: 2026-05-02
status: backfill handoff covering v0.12.0 through v0.15.0 plus unreleased context-layer work
---

# Session 014 — v0.12.0 → current truth restore

## Why this handoff exists

`SESSION_013` restored truth through `v0.11.2`, but the repo kept
shipping. Releases `v0.12.0`, `v0.13.0`, `v0.14.0`, and `v0.15.0`
landed, then additional pipeline / behavior / translation-layer work
landed after the `v0.15.0` tag. `00-START-NEXT-SESSION.md` still
pointed at the old `v0.11.2` state, so `orient` loaded stale direction.

This handoff backfills the missing continuity from `CHANGELOG.md`,
`git log`, and current runtime inventory. Treat it as the current
handoff until a later session supersedes it.

## Current state

| Surface | Value |
|---|---|
| `pyproject.toml` version | `0.15.0` |
| Latest tag | `v0.15.0` |
| Current branch | `main` |
| Tests | **804 / 804 passing** via `python3 -m unittest discover` |
| Inventory | regenerated during this session |
| CLI subcommands | 15: `adopt`, `audit`, `doctor`, `exec`, `fix`, `hotpath`, `init`, `inspect`, `inventory`, `orient`, `recommend-stack`, `refactor`, `seed`, `start`, `translation-init` |
| Tracked files | 116 in the current uncommitted review state (`git ls-files`) |

## What shipped after SESSION_013

### v0.12.0 — audit execution loop

The audit prompt became a workflow. `context-kit audit --write`
scaffolds `docs/audit/AUDIT_V1.md` and
`docs/audit/CLEANUP_PLAN.md`; `context-kit fix` reads the filled
cleanup plan; `context-kit exec` turns selected phases or next steps
into constrained AI execution prompts.

Also shipped:

- Numbered latest-handoff selection in `orient`, fixing lexicographic
  drift on `SESSION_999_*` vs `SESSION_1098_*` and ignoring
  non-numbered `SESSION_*` files.
- Team-reporting tone in AI-facing prompts.
- `scripts/track_engagement.py` and gitignored `metrics/` for private
  PyPI / GitHub engagement snapshots.
- `docs/WORKFLOWS_REAL_WORLD.md`, documenting a real audit → fix →
  exec → execute run.

### v0.13.0 — deterministic inspect

Added `context-kit inspect`, a read-only repo mapper that reports
primary stack, depth-1 workspace children, framework signals, entry
points, hot files, risk patterns, stale-doc heuristics, and
recommendations. It is deterministic filesystem / regex inspection,
not an LLM audit.

Also fixed source-only checkouts: `cli.__version__` now falls back to
`0.0.0+source` when package metadata is unavailable, so CI and fresh
clones can import `cli` without installing the wheel first.

### v0.14.0 — audit / inspect bridge + documentation intelligence

`audit` now nudges agents to run `inspect` first when available, so
audits can be grounded in deterministic structure. `inspect` gained
Documentation Intelligence: detection of docs as an active context /
memory layer via anchor docs, handoffs, audit folders, process docs,
and RAG corpus signals.

The recommendation engine gained `review-docs-context-first` for repos
where documentation scale indicates it may be active AI memory
infrastructure.

### v0.15.0 — refactor progress tracking

Added the `refactor` command group with `context-kit refactor track`.
It reports deterministic progress for long-running Python module
extraction work: total / migrated / remaining item counts, percentage
complete, destination breakdown, top remaining domains from an
optional plan, and estimated PR count.

The v1 detectors are `function`, `class`, and `celery-task`; output
formats are `text` and deterministic `json`. The feature is read-only
by contract.

### Unreleased after v0.15.0 — context-layer scaffolds

Several commits after `v0.15.0` add the next layer of context-kit docs
and diagnostics:

- `PIPELINE.md` support: scaffolding, `orient` discovery, `doctor`
  warnings when LLM / agent / task indicators exist without a runtime
  flow map, and stronger template language around entry points,
  guards, retrieval, and post-processing.
- `BEHAVIOR_LAYER.md` support: scaffolding, `orient` discovery, and
  `doctor` warnings for chat / voice / persona-bearing surfaces.
  This doc owns voice, source-of-truth display rules, constraint
  preservation, decision boundaries, and post-generation checks.
- `TRANSLATION_LAYER.md` support: scaffolding, `orient` discovery,
  `doctor` warnings for multi-audience / stakeholder projects, and
  a `translation-init` static-prompt command that guides an AI agent
  through populating the audience contract without inventing facts.
- Live Chat Mode in the translation layer: per-persona trigger
  phrases, prohibited jargon, substitutions, refusal rules, and
  grounding rules for non-technical personas.
- `orient --short`: compact re-orientation showing source-of-truth
  order, optional session-start / translation-layer filenames,
  latest handoff, next-task excerpt, and doctor warning summary.
- `doctor` matured from environment checks into context-shape
  diagnostics: inventory freshness, handoff numbering, next-task
  consistency, missing pipeline / behavior / translation docs, adopt
  placeholders, and stale generic actions.

## Known warnings and intentional gaps

- `context-kit doctor` currently warns that this repo has no
  `PIPELINE.md` and no `BEHAVIOR_LAYER.md`.
- The warning is expected until the project owner decides whether
  context-kit itself should add repo-owned `docs/CONTEXT_KIT_PIPELINE.md`
  and `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md`, or whether the warnings
  should be intentionally skipped / documented for this repo.
- No `TRANSLATION_LAYER.md` warning currently fires for this repo.
- The repo has no local frontend/backend app; active dev servers on
  the machine belong to another workspace and are out of scope.

## What changed in this truth-restore session

- Regenerated `docs/CONTEXT_KIT_INVENTORY.md` from current runtime
  state.
- Added this continuity handoff.
- Rewrote `00-START-NEXT-SESSION.md` to point at current truth instead
  of the stale `v0.11.2` / `SESSION_013` framing.
- Updated the inventory's human-written release and subcommand
  narrative so it no longer contradicts the auto-generated block.

## Recommended next work

1. Decide whether to add `docs/CONTEXT_KIT_PIPELINE.md` and
   `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md` to this repo, or explicitly
   document why context-kit skips those optional layers for itself.
2. If adding them, keep the first pass narrow: map CLI entry points,
   prompt-printing commands, scaffold-writing commands, read-only
   commands, and the "LLM is language layer only" behavior contract.
3. Re-run `context-kit doctor`, `context-kit orient --short`, and the
   unit suite after that decision.
4. Do not start the adopt refactor or new feature work until doctor
   warnings are either closed or intentionally documented.

## AI Notes

The code is healthier than the docs were: current tests pass and the
package metadata is coherent, but session continuity lagged four tagged
releases plus several unreleased context-layer commits. This is exactly
the failure mode context-kit exists to prevent, so the durable follow-up
is not another feature; it is deciding how the repo should satisfy its
own pipeline / behavior-layer expectations.
