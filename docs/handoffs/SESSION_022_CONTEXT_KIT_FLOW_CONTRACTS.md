---
title: "Session 022 — context-kit flow contracts"
date: 2026-11-16
status: documentation-only
previous_handoff: ./SESSION_021_CODEX_CONTINUITY_DOGFOOD.md
---

# Session 022 — context-kit flow contracts

## Decision and evidence

Wrote both [pipeline](../CONTEXT_KIT_PIPELINE.md) and
[behavior layer](../CONTEXT_KIT_BEHAVIOR_LAYER.md). Real runtime surfaces
justify them: chat sends context/history to configurable Ollama, inspect
collects deterministic evidence, and orientation/diagnostics/inventory/handoff
have distinct report and write contracts. Doctor explicitly recommends both.
The generic templates supplied structure; web UI and business-decision
placeholders were replaced with terminal/report contracts.

Before editing, ran `python3 context_kit.py orient` (exit 0) and read
CLAUDE.md, start guide, narrative/runtime/translation anchors and Session 021.
Source evidence: `context_kit.py`, `cli/orient.py`, `cli/chat.py`,
`cli/ollama.py`, `cli/inspect.py`, `cli/doctor.py`, `cli/inventory.py`,
`cli/handoff.py`, `cli/start_codex.py`, and both
`cli/_pattern/templates/PLATFORM_{PIPELINE,BEHAVIOR_LAYER}.template.md` files.
Runtime wins over template assumptions: no chat output validator exists;
optional reports may be generated lazily, then cached. Prompt rules alone
are not proof of compliant model responses or local-only data handling.

## Changed files

- Added `docs/CONTEXT_KIT_PIPELINE.md` and `docs/CONTEXT_KIT_BEHAVIOR_LAYER.md`.
- Updated narrative anchor read order and corrected its obsolete manual-inventory description; closing command re-stamped frontmatter.
- Updated `00-START-NEXT-SESSION.md` with this decision and preserved remaining priority order.
- Updated `README.md` endpoint/data handling wording and `CLAUDE.md` source order/generated inventory descriptions in the narrow closing follow-up.
- Refreshed `docs/CONTEXT_KIT_INVENTORY.md` with the required generator.
- Added this numbered handoff and completed `.context-kit/TASK_context-kit-flow-contract-docs.md` as the execution record.

## Checks

- `python3 context_kit.py orient`: exit 0 before edits; surfaced the two missing-doc warnings and existing SESSION_005 gap.
- `python3 context_kit.py handoff write 22`: exit 0; narrative anchor re-stamped, new docs already at Session 22, translation skipped (no frontmatter). Calibration audit reported no entries (AI Notes has no subsections to promote).
- `python3 context_kit.py inventory --write`: exit 0, updated managed block (21 numbered handoffs).
- `python3 context_kit.py inventory --check`: exit 0, inventory current.
- `python3 context_kit.py verify`: exit 0; 1 VERIFIED, 4 DOC_ONLY, 0 CONFLICT, 1 UNKNOWN. The beat-schedule heuristic matches detector/test text; this does not establish a running Celery service. UNKNOWN is Django settings module; unrelated findings preserved.
- Initial `python3 context_kit.py doctor`: exit 0; 12 OK, 0 blocking, 2 warnings, 4 skipped. The new handoff wording triggered start/handoff mismatch; aligned it to the start guide before final check.

- Final `python3 context_kit.py doctor`: exit 0; 13 OK, 0 blocking, 1 warning (SESSION_005 gap), 4 skipped. Both missing-doc warnings and the start/handoff mismatch are cleared.
- Follow-up `python3 context_kit.py inventory --check`: exit 0, current.
- `git diff --check`: exit 0; local Markdown link checks passed for the two new contracts, narrative anchor and this handoff.

## Closing entry-point follow-up — 2026-11-16

README now states the localhost default, remote-capable `OLLAMA_BASE_URL`
override, and transmission of context/conversation to the configured endpoint.
CLAUDE now places pipeline/behavior after inventory and describes its generated
managed block. Start-guide state includes both entry-point corrections; the
SESSION_005 first priority and subsequent queue are unchanged.

Reran the required commands after these edits:

- `python3 context_kit.py handoff write 22`: exit 0; all three frontmatter anchors unchanged at Session 22; translation skipped (no frontmatter); calibration audit found no subsections to promote (reported no calibration/AI Notes section).
- `python3 context_kit.py inventory --write`: exit 0, inventory updated.
- `python3 context_kit.py inventory --check`: exit 0, inventory current.
- `python3 context_kit.py verify`: exit 0; 1 VERIFIED, 4 DOC_ONLY, 0 CONFLICT, 1 UNKNOWN (Django settings module).
- `python3 context_kit.py doctor`: exit 0; 13 OK, 0 blocking, 1 warning (SESSION_005 gap), 4 skipped.
- `git diff --check`: exit 0. No tests run; no source edits, commit, push or publication.

## Final consistency polish — 2026-11-16

Added the translation-layer audience contract before the latest handoff in
CLAUDE's read order. Clarified that both Codex prompt-preparation commands
may create missing verification config. Replaced the nested priority heading
with a standalone SESSION_005 heading and ordered remaining queue; order is
unchanged. Updated start-guide state and appended the task execution report.

Final checks: `git diff --check` exit 0; `python3 context_kit.py inventory
--check` exit 0 (current); `python3 context_kit.py verify` exit 0
(1 VERIFIED, 4 DOC_ONLY, 0 CONFLICT, 1 UNKNOWN: Django settings module);
`python3 context_kit.py doctor` exit 0 (13 OK, 0 blocking, 1 warning:
SESSION_005 gap, 4 skipped). No tests, source edits, commit, push or publication.

## Not run and scope

No unit test suite, model request, external Codex launch, or implementation
change. No commit, push or publication. Initial `git status --short` was empty;
all task changes are documentation. Existing SESSION_005 gap is deferred,
not silently repaired. No unrelated diagnostic findings were fixed.

## Next-session priorities

### FIRST THING: backfill SESSION_005 numbering gap

1. Inventory git-SHA drift check from Session 016.
2. Second fleet-network worked instance.
3. Second spokesperson-corpus worked instance.

## AI Notes

The distinction between model instructions and enforced behavior is central
here: chat asks for strict evidence handling but prints returned text without
a factual scrub. No new calibration incident was identified for promotion.
