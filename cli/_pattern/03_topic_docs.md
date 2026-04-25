---
title: "Embeddable Topic Docs"
status: active
---

# Embeddable Topic Docs

The hand-maintained `docs/topics/<subsystem>.md` files are the platform's second-most-important doc surface (after the two-doc anchor). They're designed to be **embedded** — chunked, vectorized, and injected into LLM context on every AI session.

**If the AI can't see it, it doesn't exist.** A doc that only lives in a human's head isn't documentation; it's folklore.

---

## The Pattern

Create `docs/topics/` and put one doc per subsystem in it. On this platform:

```
docs/topics/
    personal-assistant.md        # PA GPT-5.2 function calling
    content-pipeline.md          # ClaimsPack → reviewers → PublishGate
    agent-system.md              # AGENT_MAP agents, routing, provenance
    initiative-pipeline.md       # 5-stage workflow
    celery-workers.md            # worker processes, queues
    body-systems.md              # 9 health-monitoring systems
    spider-network.md            # data ingestion
    stock-intelligence.md        # stock dashboard
    frontend.md                  # workspace tabs, routes
    infrastructure.md            # Django, Redis, PostgreSQL
```

One doc = one subsystem. Don't let a single `topics/` doc cover two subsystems — chunk it into two files.

---

## Per-Doc Structure

Optimized for embedding (semantic search on short, dense chunks):

```markdown
---
title: "<Subsystem Name>"
status: active
updated: YYYY-MM-DD
---

# <Subsystem Name>

<One-paragraph summary — this is what the embedding will match against first>

## Current Stats
| Metric | Value |
|---|---|
| Item count | N |
| Lines of code | N |
| ... | ... |

## Architecture
<2-5 short paragraphs, each headed by a subsystem name>

## Key Files
| File | Purpose |
|---|---|

## Known Issues / Drift
<honest list of what's broken, missing, or degrading>

## Related
- `docs/<other-topic>.md`
- `docs/PLATFORM_INVENTORY.md`
```

**Length target:** 100–250 lines. Long enough to be useful, short enough that one chunk covers one concept.

---

## The Indexer

In this repo: `python manage.py build_docs_index`. Outputs:
- `docs/INDEX.md` — human-readable table-of-contents for every doc (auto-regenerated)
- `docs/_index.json` — machine-readable manifest with headings, cross-refs, metadata

The indexer is what turns a pile of markdown into **searchable, embeddable context**. Key properties:
- Walks `docs/` recursively
- Extracts headings, links, frontmatter
- Produces an embeddable chunk per heading
- Tracks cross-references between docs (graph)
- Writes a stable JSON for downstream embedding

On this platform, `_index.json` is consumed by the PA's enrichment pipeline — when a user asks a question, the PA retrieves relevant chunks and injects them as context before calling the LLM.

---

## The Commit Hook

Your memory (`MEMORY.md`) already has this rule:

> **Docs index:** ALWAYS run `python manage.py build_docs_index` and commit `docs/INDEX.md` + `docs/_index.json` after any code changes — they get embedded and injected into the system.

On a new app, enforce this via a pre-commit hook or CI check. Without it, the embedded context lags behind the code and the AI answers yesterday's questions.

---

## Embeddable vs Reference docs

There are two kinds of docs. Don't mix them:

| Kind | Lives in | Written how | Purpose |
|---|---|---|---|
| **Embeddable** | `docs/topics/` | Short, dense, scannable | Injected into LLM context — the AI *reads* these |
| **Reference** | `docs/current/` | Long, auto-generated | Humans grep these — too long to embed |

`docs/current/MODELS.md` on this platform is 10,000+ lines — dumps every Django model with every field. Not embeddable. Humans use it to answer "what are the fields on SelfBlog?" The AI uses `docs/topics/content-pipeline.md` to understand *what SelfBlog is for*.

---

## The Mistake We Made

For the first ~800 sessions on this platform, topic docs were free-form. Some were 50 lines, some 800. Some had stats tables, most didn't. The embedding results were uneven — semantic search would hit a long rambling doc and miss a short precise one, because the long doc had more chunks.

Fix: **standardize the template**. Every topic doc now starts with stats table → architecture → files → known issues. Embeddings match the structured opening paragraphs first, the table rows second, and the architecture paragraphs third. Predictable.

---

## Anti-patterns

- **Topic doc for a file that doesn't exist yet.** If the subsystem isn't real, don't document it. Aspirational docs lie to the embedding layer.
- **Topic doc that references only itself.** If it doesn't point at `PLATFORM_INVENTORY.md` + related topic docs, the AI can't navigate outward.
- **Topic doc with exact live counters.** Drifts fast, pollutes embeddings with wrong numbers. Use `~values` + "live counter" annotations.
- **Updating 10 topic docs to fix one stat.** Add a `DOC-POINTER-V1` header at the top instead (see `06_dos_and_donts.md` DO #7).

---

## Directory layout in this repo

```
docs/topics/<subsystem>.md        # one per subsystem
docs/current/<AUTO_GEN>.md        # machine-generated references
docs/INDEX.md                     # auto-regenerated TOC
docs/_index.json                  # auto-regenerated manifest
core/management/commands/
    build_docs_index.py           # indexer
```

---

*The embedded context is the AI's world. Curate it like you'd curate the brain of a new hire.*
