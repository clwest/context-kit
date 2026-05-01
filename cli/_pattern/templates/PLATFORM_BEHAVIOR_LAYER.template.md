---
title: "<APP NAME> — Behavior Layer"
status: active
generated: YYYY-MM-DD
companion_docs: ["<APP>_WHAT_IT_IS.md", "<APP>_INVENTORY.md", "<APP>_PIPELINE.md"]
---

# <App Name> — Behavior Layer (BEHAVIOR_LAYER.md)

> **Read-order note:** companion to the two-doc anchor and PIPELINE.md.
> Anchors hold *what exists* and *what it is*. PIPELINE.md holds
> *how requests move*. **BEHAVIOR_LAYER.md holds *how responses
> sound, look, and respect prior turns*.**

---

## Purpose

Governs the behavior surface — voice, presentation, constraint
preservation, and the line between deterministic decisions and LLM
phrasing. Behavior bugs rarely throw errors; they drift.

---

## Voice / Tone Contract

### Persona

- Identity:
- Audience:
- Tone modifiers:

### Required phrasings

- ✅ <phrase>

### Forbidden phrasings (always paired with a positive replacement)

- ❌ <bad>  → ✅ <replacement>

### Tone per surface

| Surface | Tone | Length cap | Notes |
|---|---|---|---|
| <chat> | | | |
| <email> | | | |

---

## UI / Source-of-Truth Contract

> Rule: do not repeat rendered data in prose. If a structured
> component renders a value, prose must reference the component, not
> restate the value.

| Data type | Authoritative surface | LLM may | LLM must not |
|---|---|---|---|
| <type> | | reference | restate |

---

## Constraint Preservation Across Turns

| Constraint type | Lifetime | How it's carried | Example |
|---|---|---|---|
| <preference> | session | structured profile field | |
| <session bound> | session | session-level state | |

> Rule: a constraint that lasts beyond one turn lives in structured
> state, not in conversation history alone.

---

## Decision Authority Boundary

| Layer | Owns |
|---|---|
| Deterministic backend / services | Decision-making — eligibility, pricing, quotas, access, state |
| LLM phrasing | Language only — explain, guide, rephrase |

> Rule: the LLM must never create pricing, determine eligibility, or
> make commitments. The LLM may only explain, guide, or rephrase.

---

## Behavior Rules — GOOD / BAD Examples

### Rule: <name>

- ✅ GOOD: <example>
- ❌ BAD: <example>

---

## Small-Model Behavior Note

- Negative directives alone often fail; pair every "never X" with
  "instead, do Y" plus a worked example.
- Examples beat rules. A two-shot positive example outperforms a
  paragraph of constraints.
- Add a post-generation check for any load-bearing rule. Prompt-time
  alone is not enough.

> Rule: any behavior rule that is load-bearing for safety, accuracy,
> or compliance must have a post-generation check in addition to a
> prompt-time directive.

---

## Last Verified

- Date:
- Surfaces audited:
- Known active drift:
- Next recommended audit:
