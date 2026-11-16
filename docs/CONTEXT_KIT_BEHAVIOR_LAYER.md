---
title: "context-kit — Behavior Layer"
status: active
generated: 2026-11-16
last_revised: 2026-11-16 (SESSION 23)
---

# context-kit — Behavior Layer

This is the terminal/report response contract. Read with the
[pipeline](CONTEXT_KIT_PIPELINE.md), [narrative anchor](CONTEXT_KIT_WHAT_IT_IS.md),
[inventory](CONTEXT_KIT_INVENTORY.md), and
[translation layer](CONTEXT_KIT_TRANSLATION_LAYER.md).
The chat rules below are instructions in [chat.py](../cli/chat.py), not
post-generation guarantees. [ollama.py](../cli/ollama.py) validates response
shape, not truth or adherence to those instructions.

## Voice and task discipline

Normal chat is instructed to answer the current question directly and
concisely, avoid repeated onboarding, treat a multipart message as one task,
and stop when finished. Audience explanations must not become simulated
conversations unless requested. The live conversation defines what the user
is doing now; the documented next task must not replace that context.

`--user` searches the translation document for the first case-insensitive
substring match on a line. A match injects requested/matched persona lines
and framing rules, rather than the full translation document. Missing matches
add no persona context. Persona changes tone and priorities only: facts,
confidence, speculation labels and execution limits stay fixed. Fall back
to neutral explanation if adaptation requires unsupported implications.

Planner mode instead requests `SUMMARY:` and `COMMAND:`, exactly one proposed
command, at most three summary bullets after pasted output, or
`COMMAND: none`. It prefers context-kit commands (git with the planner option).
This is model-generated advice, not command execution or validated syntax.

## Terminal / report source-of-truth contract

These surfaces have no graphical components. The template's UI/prose split
therefore becomes a report/evidence boundary: explanation may summarize
rendered facts while preserving their source, confidence and limits.

| Claim | Authoritative input | Response contract |
|---|---|---|
| Repository meaning and priorities | Project orientation / canonical docs | Label orientation-only claims as documented, not detected |
| Machine-detected fact | Injected inspection with concrete path/route/model/env/manifest evidence | Include evidence; use only supplied line numbers, otherwise cite the path alone |
| Capability when deterministic summary exists | DETERMINISTIC CAPABILITY SUMMARY | Use only that section, preserving confidence and reason; command names are not product promises |
| Current changes or test status | Explicit git/status/log/diff/test output injected or pasted | State snapshot limits; absent evidence does not mean no changes |
| Unsupported assertion | Neither orientation nor inspection supports it | Label speculation or unknown |

For capability questions the hard contract requests command name, literal
detected type, evidence and confidence, without surrounding narrative.
Present the recommended shortlist first unless the user requests shortlist-only
mode; retain high-confidence entries unless the user narrows the request.
Do not synthesize capability promises from framework detection or command
names. Preserve Reason and Confidence from the summary exactly. The persona
preamble also contains a broader implementation/orientation/inference ordering;
when a deterministic capability summary exists, its explicit hard constraint
is the narrower applicable instruction. There is no runtime output validator.

Route evidence supports endpoint presence and may *suggest* a capability; it
does not establish payment completion, security, business logic correctness or
passing tests. Request/response models describe shape. Marketing claims about
productivity, orchestration or intelligence require their own evidence.

## Execution and live-state limits

Chat has no shell/tool execution loop, repository browsing, or file-fetch
facility. Deterministic context collectors run in Python around the model
request; the model cannot invoke them. Required responses include:

- Command request: “I can’t run commands from inside this chat. You can run:
  <suggested command>”. Never fabricate terminal output.
- Live-state request without explicit evidence: “I can’t verify live repo
  state from the injected startup context.” Suggest `git status`,
  `git log --oneline -5`, `context-kit inspect --project <path>`, or
  `context-kit capabilities --project <path> --format shortlist` as relevant.
  Suggest a test command only if known.
- Supported inference: “Route evidence suggests…” with the actual path or
  supplied citation, rather than a claim that the feature works end to end.

Optional evidence is generated at startup or lazily on first routed use and
then cached, as detailed in the pipeline. It is not live surveillance. Users
can paste fresh output for discussion. External Codex launched by `codex` has
its own agent/tool permissions; chat's limits do not describe that process.

## Conversation constraints and lifetime

Normal interactive mode carries constraints through conversation history,
not a structured durable preference store. It retains user tasks and assistant
responses; planner mode retains user tasks without assistant replies.
Turn evidence is injected for that request only. `/reset` clears history and
restores the original system message and optional priming; it keeps cached
reports/persona. `/orient` displays fresh short orientation without refreshing
the model bundle. `/help` lists controls; `/exit`, `/quit`, and EOF end chat.
A new process rebuilds context; no saved conversation is implemented here.

## Inspect presentation and uncertainty

[inspect.py](../cli/inspect.py) produces deterministic Markdown by default,
also written by `--output`; `--json` emits a structured result instead and
bypasses Markdown output-file handling. The formats are different renderings,
not identical schemas: Markdown additionally assembles identity, command,
route/model/env hints and warnings, then embeds a legacy summary.

The report covers identity/HEAD, stack indicators, commands, tree, route and
structured implementation hints, model/data and environment hints, docs status,
possibly stale docs, warnings/unknowns and recommended next moves. Its result
also carries subsystems, file sizes, framework signals and risk records.
Evidence includes paths and detected syntax; risk severity is high/medium/low,
recommendation confidence is low/medium/high, and stack confidence may be
`none`, low, medium or high. Documentation strength (`none`, low, medium, high)
is a separate heuristic, not a correctness score. Recommendations retain
suggestion, why and stable id and may be overridden or ignored.

Unknowns and “not detected” describe detector coverage, not proven absence.
Filename/regex probes and scope/history filters can miss implementations.
Suggested test commands and parsed test counts are not test execution.
“No major unknowns detected by the static pass” is not a clean security bill.
Inspect is a repository map, not an LLM/security correctness audit.

## Last verified

2026-11-16, Session 022: implementation review, not a model-compliance test.
Prompt rules can fail, including on small models; there is no post-generation
check for these behavioral constraints. Exact deterministic checks and remaining
findings are in the [handoff](handoffs/SESSION_022_CONTEXT_KIT_FLOW_CONTRACTS.md).
