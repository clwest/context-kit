---
title: "{{APP_TITLE}} — Behavior Layer"
status: stub
generated: {{DATE}}
companion_docs: ["{{APP_UPPER}}_WHAT_IT_IS.md", "{{APP_UPPER}}_INVENTORY.md", "{{APP_UPPER}}_PIPELINE.md"]
---

# {{APP_TITLE}} — Behavior Layer (BEHAVIOR_LAYER.md)

> **Read-order note:** this doc is the **behavior** companion to the
> two-doc anchor pair and `{{APP_UPPER}}_PIPELINE.md`. Where the
> anchors hold *what exists* and PIPELINE holds *how requests move*,
> **BEHAVIOR_LAYER holds *how responses sound, look, and respect prior
> turns***.
>
> If your product has a chat surface, a voice agent, a persona-bearing
> component, or any UI that renders structured data alongside generated
> language, this doc is where the rules for *correct behavior* live —
> tone, presentation contracts, constraint preservation, and the
> boundary between deterministic decisions and LLM phrasing.
>
> Behavior bugs rarely throw errors. They look like "the system said
> the right thing but in the wrong tone", "the card and the prose
> disagreed about a price", or "the user said no X in turn 1 and the
> system asked again about X in turn 4". This doc is where those
> become catchable.

---

## Purpose

This file governs the **behavior surface** — the rules a response
must satisfy *in addition to* being correct. Most behavior bugs come
from one of these:

1. **Tone drift** — voice and persona slip across turns or surfaces.
   Each piece individually sounds fine; the cumulative effect is
   inconsistent.
2. **Source-of-truth conflict** — a UI component renders data
   authoritatively, and the LLM's prose paraphrases the same data
   differently. Two answers, one screen.
3. **Constraint loss across turns** — the user establishes a
   constraint ("don't suggest X", "I already told you Y"). Two turns
   later, the system violates it because the constraint wasn't
   carried forward.
4. **Decision-authority confusion** — the LLM is asked to decide
   pricing, eligibility, or commitments instead of explaining a
   decision the deterministic layer already made.
5. **Negative-directive failure** — instructions like "never do X" do
   not reliably steer smaller models. Without positive examples and
   a post-generation check, the rule fails silently.

---

## Voice / Tone Contract

Define the system's voice once, here. Every prompt, every UI string,
every confirmation flow must respect it.

### Persona

- **Identity:** `<one sentence — what the system is presenting itself as>`
- **Audience:** `<who's on the other end and what they expect>`
- **Tone modifiers:** `<short, scannable, friendly-but-precise / etc.>`

### Required phrasings

Phrases the system **must** prefer when applicable. These are the
positive examples — small models follow positive directives more
reliably than negative ones.

- ✅ `<phrase 1 — replace>`
- ✅ `<phrase 2 — replace>`

### Forbidden phrasings

Phrases the system **must not** produce. List them, but **always
pair with a positive replacement** so the model has somewhere to go.

- ❌ `<bad phrase>`  → ✅ `<replacement>`
- ❌ `<bad phrase>`  → ✅ `<replacement>`

### Tone per surface

If the system speaks across multiple surfaces (chat, email, voice,
push notifications), document the tone delta per surface in a single
table — drift between surfaces is the most common silent regression.

| Surface | Tone | Length cap | Notes |
|---|---|---|---|
| `<chat>` | | | |
| `<email>` | | | |
| `<voice>` | | | |

---

## UI / Source-of-Truth Contract

When the UI renders data and the LLM also speaks about it, exactly
one of them is authoritative. Pick which one, here, **per data type**.

### The rule: do not repeat rendered data in prose

If a structured component (card, table, badge, price tag, status
chip) renders a value, the surrounding prose must **reference** the
component, not **restate** the value. Restated values drift.

- ✅ "The card on the right shows the current status."
- ✅ "See the highlighted row for the next step."
- ❌ "Your status is *<value>*" *(when a status badge already shows it)*
- ❌ "The price is *<number>*" *(when a price tag already renders it)*

### Authoritative-surface table

| Data type | Authoritative surface | LLM may | LLM must not |
|---|---|---|---|
| `<e.g. pricing>` | structured component | reference, point at | restate the number |
| `<e.g. status>` | status badge | name the state | claim a different state |
| `<e.g. timestamps>` | rendered field | refer to "the time shown" | invent or paraphrase the value |
| `<e.g. user-typed input>` | the input field | quote it back verbatim | summarize / paraphrase |

> **Why it matters:** when prose restates rendered data, two
> surfaces drift independently. The user sees "$249" on a card and
> "$240" in a paragraph and trusts neither.

---

## Constraint Preservation Across Turns

Conversational systems lose constraints unless they're explicitly
carried forward. Document which constraints persist and how.

### Persistent constraints

| Constraint type | Lifetime | How it's carried | Example |
|---|---|---|---|
| User preferences (e.g. "no X") | session | structured profile field | user says "don't suggest X" → field set → all future prompts include the field |
| Session bounds (e.g. budget cap) | session | session-level state | turn 1 establishes cap → every subsequent decision respects it |
| Identity facts (e.g. role) | session | structured profile field | persona-aware responses use it |
| Per-turn diagnostic / debug | one turn | metadata only | does not affect future turns |

> **Rule:** a constraint that lasts beyond one turn lives in
> structured state, not in conversation history alone. Conversation
> history is the LLM's memory; structured state is *the system's*
> memory. Conversation history compresses, drops, and gets cut off
> by context windows. Structured state does not.

### Follow-up rules

- If the user established a constraint in any prior turn, the system
  must honor it without re-asking.
- If the user reverses a constraint, mark the prior one revoked
  rather than deleting it (audit trail).
- If a turn cannot satisfy a prior constraint, the system must say
  so explicitly — never silently violate.

---

## Decision Authority Boundary

This is the same line drawn in `{{APP_UPPER}}_PIPELINE.md`, restated
here for the behavior layer because it's the most-violated rule when
prompt engineers chase fluency.

| Layer | Owns |
|---|---|
| **Deterministic backend / services** | Decision-making — eligibility, pricing, quotas, access checks, state writes, choosing which prompt template to use |
| **LLM phrasing** | Language only — explaining a decision, guiding a user through a flow, rephrasing a deterministic output |

> **Rule:** the LLM **must never** create pricing, determine
> eligibility, or make commitments. The LLM **may only** explain,
> guide, or rephrase decisions made by the deterministic layer.
>
> If a prompt is asking the model to choose, decide, or commit, the
> entry point is wrong: route the decision through the deterministic
> layer first, then let the LLM phrase the result.

---

## Behavior Rules — GOOD / BAD Examples

Concrete examples carry more steering signal than negative
directives, especially for smaller models. Add real GOOD/BAD pairs
for each rule. Replace the placeholders below with examples from
your system.

### Rule: respect prior constraints

> **Context:** in turn 1 the user said *"please don't suggest <X>"*.
> In turn 3, they ask *"any other ideas?"*

- ✅ **GOOD:** `"Here are a few options that fit what you mentioned earlier — none involve <X>."`
- ❌ **BAD:** `"Here's a great <X>-based suggestion!"`  *(violates the prior constraint silently)*

### Rule: do not restate rendered data

> **Context:** the UI shows a status badge reading "<state>".

- ✅ **GOOD:** `"The status badge above shows where this stands. Here's what to do next."`
- ❌ **BAD:** `"Your status is <state>. Here's what to do next."`  *(restates rendered data; drifts the next time the badge updates)*

### Rule: stay inside decision authority

> **Context:** user asks *"can I get a discount?"*

- ✅ **GOOD:** `"Discounts come from our pricing system — let me check what's currently available for your case."`  *(then call the deterministic check; phrase the result)*
- ❌ **BAD:** `"Sure, I can give you 10% off."`  *(LLM made a commitment the deterministic layer never authorized)*

### Rule: persona consistency across surfaces

- ✅ **GOOD:** chat, email, and push notifications all use the same first-person voice and the same name for the system.
- ❌ **BAD:** chat says *"I'll help you with that"*; email says *"Our team will reach out"*; push says *"You'll be contacted"*. Three voices, same product.

---

## Small-Model Behavior Note

If any prompt in this system targets a smaller / faster / cheaper
model (the kind used for routing, classification, or fast first-pass
generation), be aware:

- **Negative directives alone often fail.** "Never do X" steers
  larger models well; smaller ones drift back into X under pressure.
  Always pair "never do X" with "instead, do Y" plus a worked example.
- **Examples beat rules.** A two-shot positive example will outperform
  a paragraph of constraints for the same model size.
- **Add a post-generation check.** When a constraint is load-bearing
  (e.g. "must not invent prices"), enforce it after generation, not
  only inside the prompt. Possible checks: regex against a known-bad
  pattern, structural validator, deterministic re-derivation of any
  number the model claimed.
- **Keep prompts short.** Long instruction blocks compete with the
  user input for attention. Smaller models are particularly
  sensitive.

> **Rule:** any behavior rule in this doc that is *load-bearing for
> safety, accuracy, or compliance* must have a **post-generation
> check** in addition to a prompt-time directive. Prompt-time alone
> is not enough.

---

## Last Verified

- **Date:** {{DATE}}
- **Surfaces audited:** `<list — e.g. "chat, email, voice; not yet: push notifications">`
- **Known active drift:** `<anything in voice / source-of-truth / constraint-preservation that hasn't been resolved>`
- **Next recommended audit:** `<date or trigger — e.g. "before next persona change", "on next prompt template revision">`

---

## Generic example (delete after replacing with your real surfaces)

> A small worked example so the shape of the doc is unambiguous.
> Replace it before shipping with patterns from {{APP_TITLE}}.

Imagine a product with a structured "summary card" component and a
chat surface that talks about the same data:

- The card renders: title, status badge, three action buttons.
- The chat says things like: *"The card above summarizes where you
  are. The first button is the recommended next step — tap it when
  you're ready, or ask me anything about the other options."*

That sentence is on-spec because:

1. It **references** the card rather than restating the rendered values.
2. It uses **persona-consistent language** ("you're ready", "ask me anything") that matches the rest of the system.
3. It does **not** make a commitment ("the first button *is* the recommended next step" — the deterministic layer already decided that, the chat is just naming it).
4. It honors any **prior constraint** by not re-asking what was already established.

A version that fails on each axis — and which the BAD examples
above guard against — would restate the rendered values, switch
voice, invent a recommendation, and ignore prior turns.
