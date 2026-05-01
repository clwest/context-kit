---
title: "{{APP_TITLE}} — Runtime Flow Map"
status: stub
generated: {{DATE}}
companion_docs: ["{{APP_UPPER}}_WHAT_IT_IS.md", "{{APP_UPPER}}_INVENTORY.md"]
---

# {{APP_TITLE}} — Runtime Flow Map (PIPELINE.md)

> **Read-order note:** this doc is the runtime flow companion to the
> two-doc anchor pair (`{{APP_UPPER}}_WHAT_IT_IS.md` + `{{APP_UPPER}}_INVENTORY.md`).
> The anchors hold *what exists* and *what it is*. **PIPELINE.md holds
> *how requests actually move through the system*** — entry points, guard
> coverage, state writes, retrieval paths, post-processing order, and
> known operational hazards.
>
> When a guard, scrub, or filter exists on one path but not another,
> this doc is where the asymmetry must be visible. If it isn't, the
> next session will add a feature on path B and silently bypass the
> rule that path A enforces.

---

## Purpose

Most agent / LLM bugs come from one of these:

1. **Bypass drift** — a new entry point invokes the AI without going
   through the same guard rails as the canonical one.
2. **Scrub-stack reorder** — a post-processing step gets added
   before the step that depends on it; the output looks fine until a
   specific edge case surfaces it weeks later.
3. **State surface confusion** — durable facts get written to a
   per-turn metadata blob; turn-level diagnostics get written to a
   structured profile field. Both look reasonable in isolation.
4. **Allow-list silence** — a new field is added to a model and
   serializer, but a frontend / pipeline allow-list silently drops
   it, so the new value just disappears with no error.
5. **Asymmetric retrieval** — two retrieval paths share most filters
   but diverge on one. A new structural filter is added to one path
   only, and matching results across the system stop being
   consistent.

This file is the place those things become visible *before* they
become outages.

---

## Request / Execution Paths

Document every major entry point that invokes AI, agents, task runners,
or business logic. Use the template below for each one.

> **Replace the examples** with the real entry points for {{APP_TITLE}}.
> Keep the same shape so a returning AI session can scan them in
> parallel and spot asymmetry instantly.

> **Cross-reference guidance:** any endpoint listed in
> `{{APP_UPPER}}_INVENTORY.md` that invokes an **LLM**, an **agent
> system**, or a **task queue** should also appear here. The
> inventory tells you the endpoint exists; this doc tells you how its
> request actually moves through the guard, retrieval, and scrub
> stacks. (Guidance only — no automated enforcement.)

### Path 1: `<entry point name — replace>`

- **Entry point:** `<URL / signal / scheduled task / queue consumer>`
- **Handler:** `<file:line — view / consumer / handler function>`
- **Pre-logic / guards:** `<rate limit / auth / feature flag / quota / etc.>`
- **Core decision logic:** `<deterministic rules that run before any LLM call>`
- **AI/LLM role:** `<which model, what prompt template, what tool calls allowed>`
- **Post-processing / scrubs:** `<filters, redaction, normalization, persona overlay>`
- **State written:** `<which models / fields / tables / cache keys>`
- **Known bypass risks:** `<other entry points that hit similar logic but skip a step>`

### Path 2: `<replace>`

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
| `<entry point 1>` | ✅ / ⚠ / ✗ | ✅ / ⚠ / ✗ | ✅ / ⚠ / ✗ | ✅ / ⚠ / ✗ | ✅ / ⚠ / ✗ | `<gap or "none">` |
| `<entry point 2>` | | | | | | |

> **Rule:** a row that has ✗ in any column for a path that *should*
> share guard coverage with another path is a bypass risk. Either add
> the missing guard, or document explicitly *why* this path
> intentionally skips it.

---

## State Surfaces

The system has multiple durable surfaces. New facts must land in the
right one or they will silently disappear.

| Surface | Lifetime | Shape | What belongs here |
|---|---|---|---|
| **Session-level state** | Persists across turns within a session | Structured profile / state model fields | Durable facts about the user, the conversation context, decisions that affect future turns |
| **Per-turn / per-event metadata** | One turn, one event | Free-form JSON metadata field | Turn-level diagnostics, debug breadcrumbs, audit trails, scoring inputs |
| **Persistent model fields** | Forever (until explicitly mutated) | Typed model columns | Anything queried, indexed, or filtered |
| **Free-form audit metadata** | Forever, but unstructured | JSON metadata, log lines | Post-hoc analysis, never the source of truth for a query |

> **Rule:**
> - Session-level **durable** facts → structured profile / state fields.
> - Turn-level **diagnostic / audit** facts → metadata.
>
> Mixing these is the most common silent bug. A "what did the user
> tell us?" question answered from per-turn metadata will be wrong as
> soon as the conversation has more than one turn.

---

## Allow-lists / Drop Zones

Some systems have allow-lists where new fields silently disappear if
not added. Document every such allow-list here. If a new model field
isn't propagating to the frontend or the prompt, this section is
where to look first.

### Allow-list: `<replace — e.g. "frontend chat payload">`

- **File / location:** `<path:line — serializer, schema, prompt builder, etc.>`
- **What it controls:** `<which fields are passed downstream>`
- **Failure mode if missed:** `<the new field exists in the model but the AI / UI never sees it; no error is raised>`

### Allow-list: `<replace>`

- File / location:
- What it controls:
- Failure mode if missed:

---

## Retrieval / Matching Paths

Most systems with semantic / structural retrieval have **more than one
path** that needs to stay in sync. Document each path's shared and
divergent filters.

### Path A: `<replace — e.g. "primary semantic match">`

- Filters applied: `<list>`

### Path B: `<replace — e.g. "fallback / structural match">`

- Filters applied: `<list>`

### Shared filters

- `<filter>` — applied in: A, B
- `<filter>` — applied in: A, B

### Filters only supported in one path

| Filter | Path A | Path B |
|---|---|---|
| `<filter name>` | ✅ | ✗ |

> **Rule:** when adding a new structural filter, **update every
> retrieval / matching path**. Asymmetric filters are how "the same
> question" returns different answers depending on which code path
> handled it.

---

## Post-Processing / Scrub Stack

Post-processing pipelines are **ordering-sensitive**. Document the
order, and for each step, note what it catches and *why it must
happen before / after specific other steps*.

1. **`<step name>`** — what it catches: `<…>`. Order constraint:
   `<must run before / after step X because …>`.
2. **`<step name>`** — what it catches: `<…>`. Order constraint:
   `<…>`.
3. **`<step name>`** — what it catches: `<…>`. Order constraint:
   `<…>`.

> **Rule:** if you add a new scrub step, **insert it deliberately in
> the order**, don't just append. The constraint comments above are
> load-bearing — they say *why* each step lives where it does.

---

## Operational Hazards

Real friction we've hit. Add new ones here as they're discovered.

- **Duplicate dev servers** — running two copies of the dev server on
  different ports leads to "fixed it once but the other one still
  has the old code" dead-ends. Always check for stale processes.
- **Stale worker processes** — Celery / RQ / Sidekiq workers cache
  imported code on startup. After a code change, restart workers, or
  the new code never runs.
- **Stale seed / reset conventions** — if there's a `reset.sh` /
  `make seed` / `flush_db` script, document the exact command.
  Half-reset states are worse than no reset.
- **Route bypasses** — alternate URLs, signals, or queue consumers
  that hit AI / business logic without going through the canonical
  guard stack. List them in *Request / Execution Paths* above.
- **Alternate endpoints invoking AI** — list every URL that ends up
  calling a language model, even indirectly (signals, scheduled
  tasks, webhook receivers, admin actions).
- **Test count baseline** — `<N>` tests passing as of `<DATE>`.
  Drops below this without an explanation are a regression.

---

## Drift Surfaces

A **drift surface** is a place where runtime behavior can quietly
diverge from what this doc claims. Listing them up front turns
"silent" failures into ones the next session can audit by reading.

Common drift surfaces in LLM / agent / task-driven systems:

- **Alternate entry points that bypass full guard coverage.** A
  second URL, a signal handler, a webhook receiver, or an admin
  action ends up calling the same model — but skips a rate limit,
  audit log, or persona overlay that the canonical entry point
  enforces.
- **Multiple retrieval / matching paths with inconsistent filters.**
  The same logical query is satisfied by two code paths (e.g.
  semantic search + structural fallback) and a new filter is added
  to one but not the other.
- **Allow-lists that silently drop fields.** A new model field is
  added to a serializer or prompt builder, but a downstream
  allow-list (frontend payload, prompt context map, log redactor)
  doesn't include it and the value vanishes with no error raised.
- **External schedulers / orphaned tasks.** A task is registered
  with the task runner but has no `PeriodicTask` row, no in-code
  beat schedule, and no caller — yet still runs because an external
  system (cron, k8s CronJob, a managed scheduler) fires it. Its
  fate is invisible to the codebase.
- **Thin delegator tasks relying on downstream logging.** The task
  body is `return _impl_X()` with no logger calls of its own; all
  observability lives inside the helper. If the helper is moved or
  refactored, the delegator silently loses logging.
- **Module-load / import-order dependencies.** A sibling module
  imports a name that's only available after the home module's
  bottom-of-file re-export block runs. Working today, fragile
  forever — a single reordering can flip it from working to
  partially-initialized-module ImportError.

> **Rule:** every drift surface here must either:
> - **be covered in the Guard Coverage Matrix** (with the asymmetry
>   spelled out and an explicit decision recorded), or
> - **be explicitly marked as external / unmanaged** (e.g. "scheduled
>   by external cron — not orchestrated by this codebase").
>
> No surface listed here may live in a "we'll figure it out later"
> state. Either claim it or disclaim it.

---

## Decision Authority

The line between **deterministic logic** (services, business rules,
database queries) and **language generation** (the LLM) is the most
important boundary in any AI-assisted product. Conflating them is
how systems quote impossible prices, promise things they can't
deliver, and grant access they shouldn't.

| Layer | Responsibility |
|---|---|
| **Deterministic backend / services** | Decision making — eligibility, pricing, quotas, rate limits, access checks, state writes, choosing which prompt template to use. |
| **LLM** | Language only — explaining a decision, guiding a user through a flow, rephrasing a deterministic output for tone or accessibility. |

> **Rule:** the LLM **must never**:
> - create pricing
> - determine eligibility
> - make commitments (deals, refunds, guarantees, SLAs, deadlines)
>
> The LLM **may only**:
> - explain a decision the deterministic layer already made
> - guide the user through a flow whose outcomes are bounded by the
>   deterministic layer
> - rephrase content for tone, length, or accessibility

If a request appears to ask the LLM to make a decision in any of the
forbidden categories above, the entry point is wrong: route it
through the deterministic layer first, and use the LLM to explain
the result.

---

## Last Verified

- **Date:** {{DATE}}
- **Test count:** `<replace — current passing test count>`
- **Known active gaps:** `<list anything in Guard Coverage Matrix marked ⚠ or ✗ that hasn't been resolved>`
- **Next recommended audit:** `<date or trigger — e.g. "before next release", "on next prompt template change">`

---

## Generic example (delete after replacing with your real paths)

> A small worked example so the shape of the doc is unambiguous. It's
> deliberately generic — replace it before shipping.

### Path 1: Canonical chat endpoint

- **Entry point:** `POST /chat/message/`
- **Handler:** `views/chat.py:ChatMessageView.post`
- **Pre-logic / guards:** auth required, daily quota check, rate
  limit per user, feature flag `chat_v2`
- **Core decision logic:** select system prompt by user persona,
  apply current policy overlay
- **AI/LLM role:** OpenAI gpt-4o-mini with tool calls limited to
  `lookup_*` family
- **Post-processing / scrubs:** PII redaction → persona-tone
  overlay → length cap → audit-log write
- **State written:** `ChatMessage`, `ChatSession.last_seen_at`,
  `UserProfile.style_preferences`
- **Known bypass risks:** see Path 2 below — alternate `/items/<id>/ask/`
  endpoint reaches the same model with a *different* guard set.

### Path 2: Alternate AI entry point

- **Entry point:** `POST /items/<id>/ask/`
- **Handler:** `views/items.py:ItemAskView.post`
- **Pre-logic / guards:** auth required — **no quota check, no rate
  limit** ⚠
- **Core decision logic:** uses item's stored prompt template
- **AI/LLM role:** same model as Path 1
- **Post-processing / scrubs:** PII redaction only — **no persona
  overlay, no audit log write** ⚠
- **State written:** `ItemAsk` — but **not** `UserProfile`
- **Known bypass risks:** this *is* the bypass. The Guard Coverage
  Matrix should make this asymmetry obvious so the next session
  decides explicitly whether to (a) add the missing guards or
  (b) document why this path is intentionally lighter.
