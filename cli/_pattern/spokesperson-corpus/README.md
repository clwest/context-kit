# Spokesperson Corpus Pattern

A reusable shape for turning a project's internal source-of-truth docs into a public-voice
markdown corpus that can be embedded into a spokesperson AI (Character OS, a chat widget,
a customer-support agent, anything that needs grounded knowledge of "what this is and how
to talk about it").

## What this pattern produces

A directory of small, embedding-friendly markdown files — one per concept the spokesperson
needs to know about (a product, a capability, a story beat, an FAQ entry). Each chunk:

- Stands alone (no cross-file context required to be quoted)
- Carries metadata in frontmatter (slug, section, status, sources)
- Separates **what the thing is** (facts) from **how to talk about it** (voice prose)
- Declares **off-limits** content explicitly (things the spokesperson must not claim)

The corpus is the input to whatever embedder / retrieval layer the spokesperson uses.
It is **not** itself the spokesperson — it's the knowledge the spokesperson is grounded in.

## When to use this

You have:

1. A project with real internal docs (narrative anchor + runtime inventory + handoffs)
2. A public-facing surface (product page, marketing site, chat widget) where an AI will
   represent the project to people who do not work on it
3. A need for that AI to sound consistent, cite facts that are actually true, and not
   leak internal codenames / session numbers / unshipped roadmap into public conversation

If any of those is missing, this pattern is overkill.

## When not to use this

- The project doesn't have a stable identity yet (pre-positioning) — finish positioning
  first, then come back
- The spokesperson is internal-only (engineers asking about the codebase) — use a code-RAG
  pattern instead; this is for outward-facing voice
- You have one product and one page of copy — just hand-write a system prompt

## The shape

```
spokesperson-corpus/
  README.md              — what the pattern is (this file)
  RECIPE.md              — step-by-step generation guide
  VOICE_GUIDE.md         — sanitization rules + tone vocabulary
  templates/
    _product.md          — product / capability chunk
    _story.md            — origin / pivot / company-arc chunk
    _faq.md              — anticipated Q&A
    _overview.md         — top-of-corpus elevator
    _facts.md            — verifiable numbers + claims for grounding
```

A filled-in **instance** of this pattern lives wherever the project keeps it (typical:
`docs/spokesperson/` in the project root). The instance is the corpus the spokesperson
ingests; the pattern is the shape the instance follows.

## How to seed a new project

1. `cp -r docs/docs-pattern/spokesperson-corpus <new-project>/docs/spokesperson/`
2. Open `RECIPE.md` and work through it section by section
3. Use `VOICE_GUIDE.md` to sanity-check every chunk before considering it done

The recipe assumes the project already has the
[two-doc anchor](../01_two_doc_anchor.md) (narrative + inventory) in place — that's the
source material this corpus is built from.

## What's in the instance

A typical instance ends up with **20–35 chunks** organized roughly as:

| Group | Typical count | Purpose |
|---|---|---|
| Overview + voice + structure | 3 | Elevator pitch, voice guide, top-level taxonomy (pillars / sections / tiers) |
| Products / capabilities | 10–20 | One chunk per product the public can buy or interact with |
| Engine / behind-the-scenes | 3–8 | Sanitized capability reveals — "the engine that powers X" without exposing internals |
| Story | 2–4 | Origin, pivot, what changed, why |
| Channels / publications | 0–6 | Newsletter, podcast, dossier — anything the studio publishes |
| FAQ | 1 | Anticipated questions (pricing, scope, what's real vs aspirational) |
| Facts | 1 | Verifiable numbers and claims, with citation back to source-of-truth |

Numbers will vary by project. A solo OSS tool might have 5 chunks; a multi-product studio
might have 40.

## Refresh cadence

The corpus drifts the moment the project ships something new. Bake a refresh step into
the same place you regenerate inventory / narrative anchor — typically end of session.

If the corpus is embedded in a downstream system (Character OS, a chat widget), re-ingestion
is also part of the refresh.

## How this pattern was distilled

Built first as a project-local pattern in unified-donkey-betz alongside the 24/7 Global AI
spokesperson — see that project's `docs/docs-pattern/spokesperson-corpus/` for the original
working spec and `docs/spokesperson/` for the first worked instance. Ported into context-kit
once the shape stabilized so any context-kit user can `cp -r` it into their project.

A proposed `context-kit spokesperson` CLI subcommand (`init` / `refresh` / `doctor`) is
described in `docs/proposals/spokesperson-corpus-subcommand.md` in the context-kit repo —
implementation pending.
