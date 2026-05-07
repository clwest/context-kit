---
title: "Session 015 — post-v0.15.0 feature burst handoff"
date: 2026-05-07
status: continuity handoff covering 41 commits shipped after SESSION_014; Truth/State Layer doctor side done, orient side remaining
---

# Session 015 — post-v0.15.0 feature burst handoff

## Why this handoff exists

`SESSION_014` restored truth through `v0.15.0` and queued the
Truth / State Layer as the next task. Between then and now, **41
commits** landed on `main` (now pushed to `origin/main`) covering
five distinct feature tracks plus the doctor half of the
Truth / State Layer. The work continued past the point where the
handoff was written, so this session restores continuity and points
the next session at the remaining surface.

No new release tag yet — `pyproject.toml` is still `0.15.0`. All
post-v0.15.0 work is unreleased.

## Current state

| Surface | Value |
|---|---|
| `pyproject.toml` version | `0.15.0` (unchanged) |
| Latest tag | `v0.15.0` |
| Branch | `main`, in sync with `origin/main` |
| Working tree | clean |
| Tests | **1016 / 1018 passing** via `python3 -m unittest discover -s tests -t .` |
| Test count delta vs inventory | inventory still reports 821; doctor flags this as drift |
| Inventory freshness | **stale** — `context-kit inventory --check` exits non-zero |
| Doctor | 0 blocking, 6 warnings (see "Known warnings" below) |

The two failing tests both live in
`tests/test_truth_state.py::TestOrientRuntimeState`:

- `test_full_orient_includes_runtime_state_block`
- `test_short_orient_includes_runtime_state_block`

Both fail on the same assertion: `## CURRENT RUNTIME STATE` is not
yet emitted by `orient` (full or `--short`). These are the
scaffolded targets for the remaining next-task work — they are
**not regressions**.

## What shipped after SESSION_014

### Truth / State Layer — doctor side (complete)

`context-kit doctor` matured into a real drift detector. The
warning-only checks now in place and covered by tests:

- **Test-count drift** — compares `unittest` discovery against the
  inventory's `Tests collected` count.
- **Inventory freshness** — flags when the inventory auto-block is
  older than the most recently changed file under tracked source.
- **Handoff continuity** — flags missing numbered handoffs in the
  `SESSION_NNN_*` sequence.
- **Start vs handoff verification** — flags when the next-task text
  in `00-START-NEXT-SESSION.md` is not present in the latest
  handoff (worded as "verification needed", not "wrong").
- **Version drift** — covered by `TestVersionDrift` (passes today
  because docs and `pyproject.toml` agree).

The matching tests in `tests/test_truth_state.py` pass.

### Truth / State Layer — orient side (remaining)

`render_orient(...)` and `render_orient(..., short=True)` do **not
yet** emit the `## CURRENT RUNTIME STATE` block. The two failing
tests are the contract for that block:

- Full orient: must include `## CURRENT RUNTIME STATE`.
- Short orient: must include `## CURRENT RUNTIME STATE`.

The block should show — at minimum — current version, actual test
count, inventory status, latest handoff, next expected session,
doctor warning count, and a drift summary (per the next-task scope
in the previous start-here doc). Implementation hint: reuse the
helpers the doctor side already produces; do not re-shell out to
`unittest discover` from `orient` (slow). Read `pyproject.toml` for
the version and the inventory auto-block for the recorded test
count, then compare against a cheap re-discovery if affordable.

### `verify` command (new, truth-state evidence layer)

Multi-commit sequence (`9c36230` → `39c1d6e`) introduced
`context-kit verify`: scope-aware, evidence-driven validation of
quantitative claims in canonical docs (counts of agents, services,
spiders, etc.). It excludes self-generated reports, has scope-aware
evidence matching, count-claim and precision-claim detectors, and
Celery split-ownership awareness. `.context-kit/verify.yaml` is the
source map; the project guidance in `CLAUDE.md` already says
"verification config wins for doc claims."

### Codex wrapper + interactive launch

`context-kit codex` and `context-kit start-codex` now default to
launching Codex interactively with inherited terminal IO. Flags
exposed: `--short`, `--exec`, `--mode=execute|design`,
`--print-prompt`, etc. Tests in
`tests/test_truth_state.py::TestStartCodex` cover the parsing,
fallback when the binary is missing, and `verify.yaml`
preservation.

### `inspect` — scoped mode + coverage classification

`context-kit inspect` gained a scoped mode (path filtering, JSON
scope metadata, strict/related modes) and a coverage classifier
that recognizes RAG / docs-rag / asset folders and reports
tracked-file coverage. The behavioral risk map output was refined
in the same series.

### Connection integrity audit (new feature)

A multi-commit feature (`6e72c21` → `0b5c541`) that audits whether
frontend routes / API calls and backend routes are reachable from
each other. It includes route-role classification on orphan
findings, false-positive reduction, scoped frontend audits that
load the matching backend routes, FastAPI decorator route
extraction, and suppression of global orphan routes in scoped
mode.

### Audit dashboard improvements

The audit dashboard report-style refresh shipped:
audience-aware translation layer, executive summary + risk
scoring, report-style framing, and agent-handoff export from the
dashboard.

### Drift-prevention instructions across agent surfaces

`109188e` made drift-prevention rules explicit across the
agent-facing surfaces (skill, prompts, templates) so agents see the
"runtime wins / inventory wins / verify wins" rules without having
to re-derive them.

### Ollama chat mode (the big recent surface)

A long sub-series (`f54dbb6` → `2567601`) added a local Ollama
chat mode with progressive grounding. Commits roughly in order:

- `f54dbb6` — base `chat` command + `cli/chat.py` + `cli/ollama.py`
  with live context behavior.
- `de722d5` — response audit scaffold + project path support.
- `1ebc77f` — repo-inspection grounding inside chat.
- `32216aa` — chat prompt debugging + compact orientation.
- `e04adff` — conversational discipline rules.
- `735faac` — deterministic capability shortlist for grounding.
- `99d2900` — tightened inspect + capability grounding.
- `99085ba` — selective per-turn context routing.
- `2567601` — **`--planner-mode` and `--planner-prefer-git`**:
  minimal command-planner system prompt, tiny task wrapper, no
  assistant-history retention, separate debug-prompt path. Useful
  for human-in-the-loop "what should I run next" inspection.

37 chat tests cover the surface end to end.

## Known warnings and intentional gaps

`context-kit doctor` currently reports 6 warnings:

1. **Test count drift** — runtime 1018 vs inventory 821. Fix by
   regenerating the inventory; this is a stale-doc symptom, not a
   real drift.
2. **Inventory staleness** — same root cause; regenerate.
3. **PIPELINE.md missing** — open question per SESSION_014:
   either add `docs/CONTEXT_KIT_PIPELINE.md` or document why
   context-kit skips it.
4. **BEHAVIOR_LAYER.md missing** — same open question. The new
   chat surface arguably *demands* one now, since the chat
   preamble + planner contract + persona behavior all live in
   code instead of docs.
5. **Handoff numbering continuity** — `SESSION_005` is missing.
   Pre-existing gap; backfill or document.
6. **Start vs handoff verification** — once this handoff lands and
   `00-START-NEXT-SESSION.md` is updated, this should clear.

None are blocking. Items 1–2 are the cheapest to clear and should
happen before the orient runtime-state work starts.

## What changed in this handoff session

- Committed the in-progress planner-mode chat work as `2567601`
  ("Add planner mode to chat for command-only inspection") — 240
  insertions / 6 deletions across `cli/chat.py`, `context_kit.py`,
  `tests/test_chat.py`. Working tree was dirty when the session
  started; this commit closed it.
- Pushed `e726204..2567601` (41 commits) to `origin/main`. Repo
  is now clean and in sync.
- Wrote this handoff (`SESSION_015`).
- Will rewrite `00-START-NEXT-SESSION.md` to point at this
  handoff and at the orient runtime-state block as the literal
  next task.

No code beyond the planner-mode commit changed in this session.
Inventory was **not** regenerated — flagged in the next-task list.

## Recommended next work

In strict order:

1. **Regenerate the inventory.** Run
   `python3 context_kit.py inventory --write`, verify
   `inventory --check` is clean, and commit. This silences two of
   the six doctor warnings and makes test-count drift detection
   meaningful again.
2. **Implement the orient `## CURRENT RUNTIME STATE` block** so
   `tests/test_truth_state.py::TestOrientRuntimeState` passes.
   Stay inside the constraints from the previous next-task scope:
   no CLI argument changes, warning-only, deterministic, no new
   external dependencies. Reuse the doctor-side helpers.
3. **Close the start-vs-handoff verification warning** by
   confirming this handoff's "next task" matches whatever the new
   `00-START-NEXT-SESSION.md` says.
4. **Decide on PIPELINE / BEHAVIOR_LAYER docs** for this repo.
   The chat surface raised the value of writing a behavior layer
   for context-kit itself — voice, source-of-truth display rules,
   and constraint preservation are all real concerns now.
5. Only after the above: cut a `v0.16.0` release covering the
   verify command, the inspect scoped mode, the connection
   integrity audit, the chat surface, and the Truth / State Layer.

## AI Notes

The repo is in better shape than the inventory implies. The
test suite added ~200 tests since the inventory was last written
and nothing regressed. The two failing tests are not bugs — they
are next-task contracts already authored.

Pattern observation worth keeping: the chat surface accumulated a
lot of behavior in code (preamble, planner contract, persona
rules, query routing) without a corresponding behavior-layer
doc. That is the exact failure mode the Truth / State Layer is
designed to prevent. The right move next session is to do the
small mechanical work (inventory regen + orient block) first so
the drift-detection signal becomes trustworthy, then make the
larger judgement call about PIPELINE / BEHAVIOR_LAYER docs with
clean signal in hand.
