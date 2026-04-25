---
title: "<APP NAME> — What It Actually Is"
status: active
generated: YYYY-MM-DD
companion_doc: <APP>_INVENTORY.md
---

# <App Name> — What It Actually Is

> **Read-order note:** this doc is the conceptual/narrative companion to
> [`<APP>_INVENTORY.md`](<APP>_INVENTORY.md). The inventory is runtime-derived
> and regenerable (via `python manage.py generate_platform_inventory`) — it
> tells you *what exists right now*. This doc tells you *what it all is,
> why it exists, and how it fits together*. Numbers cited here are accurate
> at time of writing (YYYY-MM-DD); regenerate the inventory for a fresh snapshot.

---

## TL;DR — One Sentence

<One-sentence pitch. What the app is, who it's for, what it does.>

**Scale:** <rough LOC, model count, worker count — approximations only>.

---

## Table of Contents

1. [The Core Idea](#the-core-idea)
2. [The Layered Architecture](#the-layered-architecture)
3. [The Unique Stuff (The IP)](#the-unique-stuff-the-ip)
4. [Current State Honesty](#current-state-honesty)
5. [How to Navigate](#how-to-navigate)
6. [Glossary](#glossary)

---

## The Core Idea

<3–6 sentences. What this system is at the level your grandma could understand.>

<Distinguish what it IS from what it isn't. Example: "It's not a CRM. It's a
multi-agent intelligence platform that happens to store customer data.">

---

## The Layered Architecture

### Layer 1 — <Data / Ingestion / etc>

<One paragraph describing this layer>

| Component | Count | Purpose |
|---|---|---|

**Key files:**
- `<path/to/file.py>` — <one-line purpose>

### Layer 2 — <Reasoning / Agents / etc>

<One paragraph>

**Key files:**
- `<path/to/file.py>`

### Layer 3 — <Pipelines / Workflows / etc>

...

### Layer N — <Frontend / UI / etc>

...

---

## The Unique Stuff (The IP)

<What makes this platform distinctive vs off-the-shelf. Bullets. This is
what you'd show an investor or a new engineer in the first 10 minutes.>

### 1. <Unique capability #1>
<2–4 sentences — what it is, why it matters>

### 2. <Unique capability #2>

### 3. <Unique capability #3>

<Aim for 5–10 genuine differentiators. If you can't find 5, you don't have
enough IP to justify the narrative doc yet — just use the inventory.>

---

## Current State Honesty

### Working well (as of <date>)

- <Subsystem A>
- <Subsystem B>
- <Subsystem C>

### Stale or drifting

- <What's known-broken>
- <What's partially migrated>
- <Where docs lag>

### Known issues queued for follow-up

- <Bug #1 — brief description + severity>
- <Bug #2>
- <Bug #3>

**Live drift report:** `python manage.py verify_doc_claims --only-drift`.

---

## How to Navigate

### The docs to know
1. **[`docs/<APP>_INVENTORY.md`](<APP>_INVENTORY.md)** — runtime truth. Regenerable. Single source of truth when other docs disagree.
2. **[`docs/<APP>_WHAT_IT_IS.md`](<APP>_WHAT_IT_IS.md)** — this doc. Conceptual narrative.
3. **[`CLAUDE.md`](../CLAUDE.md)** or `AGENTS.md` — AI session entry point.
4. **[`00-START-NEXT-SESSION.md`](../00-START-NEXT-SESSION.md)** — current priorities per session.
5. **[`docs/topics/`](topics/)** — subsystem deep-dives.
6. **[`docs/handoffs/`](handoffs/)** — session-by-session build history.

### The commands to remember

```bash
# Regenerate the inventory (runtime snapshot)
python manage.py generate_platform_inventory

# Check which docs disagree with reality
python manage.py verify_doc_claims --only-drift

# Rebuild the docs search/embedding index
python manage.py build_docs_index
```

### Asking the AI assistant

```bash
<app-specific assistant invocation>
```

### Restarting the platform

```bash
<app-specific restart commands>
```

---

## Glossary

| Term | Meaning |
|---|---|
| **<Term>** | <One-line explanation> |
| **<Term>** | <One-line explanation> |

<Alphabetize. Include every term that's platform-specific jargon. New team
members will thank you.>

---

*Last revised: <date>. When this doc drifts from reality, regenerate
`<APP>_INVENTORY.md` first — that's always authoritative.*
