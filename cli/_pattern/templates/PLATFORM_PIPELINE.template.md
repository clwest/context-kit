---
title: "<APP NAME> — Runtime Flow Map"
status: active
generated: YYYY-MM-DD
companion_docs: ["<APP>_WHAT_IT_IS.md", "<APP>_INVENTORY.md"]
---

# <App Name> — Runtime Flow Map (PIPELINE.md)

> **Read-order note:** companion to the two-doc anchor pair. The
> anchors hold *what exists* and *what it is*. **PIPELINE.md holds
> *how requests actually move through the system*** — entry points,
> guard coverage, state writes, retrieval paths, post-processing
> order, and operational hazards.

---

## Purpose

This file maps real execution paths so a returning AI session
(or a new contributor) can spot bypass drift, scrub-stack reorder
bugs, and asymmetric retrieval before they ship.

---

## Request / Execution Paths

> **Cross-reference guidance:** any endpoint in `<APP>_INVENTORY.md`
> that invokes an LLM, an agent system, or a task queue should also
> appear here. (Guidance only — no automated enforcement.)

### Path 1: <entry point name>

- Entry point:
- Handler:
- Pre-logic / guards:
- Core decision logic:
- AI/LLM role:
- Post-processing / scrubs:
- State written:
- Known bypass risks:

### Path 2: <entry point name>

- Entry point:
- Handler:
- Pre-logic / guards:
- Core decision logic:
- AI/LLM role:
- Post-processing / scrubs:
- State written:
- Known bypass risks:

---

## Guard Coverage Matrix

| Entry point | Pre-LLM guards | Deterministic business rules | LLM call | Post-LLM scrubs | Metadata / audit logging | Known gaps |
|---|---|---|---|---|---|---|
| `<path 1>` | | | | | | |
| `<path 2>` | | | | | | |

---

## State Surfaces

- **Session-level durable facts** → structured profile / state fields.
- **Turn-level diagnostic / audit facts** → metadata.

| Surface | Lifetime | Shape | What belongs here |
|---|---|---|---|
| Session-level state | | | |
| Per-turn metadata | | | |
| Persistent model fields | | | |
| Free-form audit metadata | | | |

---

## Allow-lists / Drop Zones

### Allow-list: <name>

- File / location:
- What it controls:
- Failure mode if missed:

---

## Retrieval / Matching Paths

### Path A: <name>

- Filters applied:

### Path B: <name>

- Filters applied:

### Shared filters

### Filters only supported in one path

> Rule: when adding a new structural filter, update every retrieval / matching path.

---

## Post-Processing / Scrub Stack

1. <step name> — what it catches: <…>. Order constraint: <…>.
2. <step name> — what it catches: <…>. Order constraint: <…>.

---

## Operational Hazards

- Duplicate dev servers
- Stale worker processes
- Stale seed / reset conventions
- Route bypasses
- Alternate endpoints invoking AI
- Test count baseline: <N> tests as of <DATE>

---

## Drift Surfaces

Places where runtime behavior can silently diverge from this doc:

- Alternate entry points that bypass full guard coverage
- Multiple retrieval / matching paths with inconsistent filters
- Allow-lists that silently drop fields
- External schedulers / orphaned tasks (no PT row, no caller, still firing)
- Thin delegator tasks relying on downstream logging
- Module-load / import-order dependencies

> Rule: every drift surface must either be covered in the Guard
> Coverage Matrix, or explicitly marked as external / unmanaged.

---

## Decision Authority

| Layer | Responsibility |
|---|---|
| Deterministic backend / services | Decision making — eligibility, pricing, quotas, access, state |
| LLM | Language only — explain, guide, rephrase |

> Rule: the LLM must never create pricing, determine eligibility, or
> make commitments. The LLM may only explain, guide, or rephrase.

---

## Last Verified

- Date:
- Test count:
- Known active gaps:
- Next recommended audit:
