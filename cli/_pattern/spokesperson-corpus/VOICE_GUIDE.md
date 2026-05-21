# Voice Guide — Spokesperson Corpus

The guide to writing chunks that sound like the project, not like a generic AI assistant.
Use this when filling in templates and reviewing chunks before merge.

## The two-layer rule

Every chunk has **facts** (verifiable, traceable to source-of-truth) and **voice**
(prose the spokesperson can quote). Keep them separated in the chunk structure — never
mix a factual claim into the voice paragraph without it also appearing in the structured
facts section. If the spokesperson is asked to defend a claim, it should be quoting
something that exists in `Quick facts` or `90_facts.md`, not paraphrasing a vibe.

## Sanitization (always)

These transformations apply to every chunk regardless of audience tier.

### Names

| If the source says | The corpus uses |
|---|---|
| Internal codename (e.g. "u-d-b", "old-product-name") | "the engine" / "the studio" / the current public brand name |
| Previous brand (pre-rebrand) | Only in the origin story chunk, framed as past tense |
| Internal team nicknames | Job titles or omit entirely |
| Specific employee names | Job titles unless person has consented to public attribution |

### Numbers

Only cite numbers that:
1. Appear in the runtime inventory or another regenerable source, and
2. Have a source line you can drop into `90_facts.md`

If a number can't survive that test, paraphrase ("dozens", "more than a hundred",
"north of a thousand"). It is better to say "more than a hundred" than to cite "147"
and be wrong six months later.

### Stack jargon

For `audience: public-everyone` chunks, replace stack-level terms with capability framing:

| Don't say | Say instead |
|---|---|
| "Celery worker pool" | "background job system" |
| "Django ORM" | "the data layer" |
| "pgvector embeddings" | "semantic search" / "AI-grounded retrieval" |
| "Redis cache" | "the cache layer" |
| "Scrapy spider" | "source watcher" / "ingestion source" |
| "function-calling agentic loop" | "the agent's tool-use system" |
| "WebSocket consumer" | "real-time channel" |

For `audience: public-builders` chunks, stack-level terms are allowed but should still be
quick to skim — assume the reader knows what Django is, not what the project's specific
Django modules do.

### Banned vocabulary (default deny list)

- "AI-powered"
- "Revolutionary"
- "Game-changer" / "game-changing"
- "Leverage" (as a verb, when "use" would do)
- "Harness" (as a verb)
- "Synergy" / "synergistic"
- "Best-in-class" / "world-class" (unless backed by a citable ranking)
- "Cutting-edge" / "bleeding-edge"
- "Unleash" / "unlock potential"
- "Robust" (overused, says nothing)
- "Solution" (used as a noun for a product — say "product" or the product's name)

Projects may extend this list in their `01_voice.md`. They may not shorten it without
deliberate override; if a banned word is genuinely the right word in a specific chunk,
flag it in a comment.

## Voice anchor (per-project)

The project's `01_voice.md` chunk is the authoritative voice source. The voice guide here
gives the **defaults**; the project's voice anchor gives the **specifics**. The anchor
must include:

- Tagline / motto (exact text)
- Three voice adjectives (e.g. "editorial, declarative, confident")
- Voice persona (proprietor, founder, studio, anonymous narrator)
- Tone register (formal, casual, technical, lyrical)
- Typographic conventions (Roman numerals, em dashes, ALL CAPS for section headers, etc.)
- Sentence-level dos and don'ts with examples
- Canonical names table (preferred name per concept)

A chunk that contradicts the project's voice anchor takes precedence to the voice anchor.
Update the chunk, not the anchor — the anchor is the cross-chunk consistency rule.

## Audience tiers

### `public-everyone`

- Reader assumes nothing technical
- No stack jargon, no acronyms without expansion
- No comparisons to other products by name
- No unshipped roadmap, no aspirational claims
- No internal counts or metrics that aren't on a public page somewhere

This is the default for marketing-site / sales / first-touch surfaces.

### `public-builders`

- Reader is technical (engineer, technical founder, technical buyer)
- Stack-level detail allowed; assume reader knows the major frameworks
- Architecture diagrams or links to them allowed
- Still no internal codenames, session numbers, or pre-announce roadmap
- Comparisons to other tools allowed if factual ("we use X but most folks use Y")

This is the tier for docs, integrations pages, technical landing pages.

### `operator-only`

- Reader is a paying customer or under NDA
- Unshipped features under NDA allowed (mark explicitly)
- Internal counts allowed
- Still no other-customer specifics, no internal team gossip

This is the tier for in-app help, customer-portal docs, support chat.

## Structural conventions

### Chunk size

- Target 200-600 words per chunk
- Hard cap 1,200 words — split if longer
- One concept per chunk — if you find yourself writing "and also X", X gets its own chunk

### Frontmatter (required on every chunk)

```yaml
---
title: <human-readable name>
slug: <kebab-case-id>
section: <Overview | Voice | Pillars | Suite | Vertical | Lab | Channel | Engine | Story | FAQ | Facts>
status: <shipped | demo-ready | in-development | concept | story | reference>
audience: <public-everyone | public-builders | operator-only>
voice: editorial   # or whatever the project's voice anchor declares
sources: [<list of source files / PRs / docs this chunk derives from>]
updated: <YYYY-MM-DD>
---
```

### Internal structure (product / capability chunks)

```markdown
# <display name>

**Tagline.** <one sentence matching voice anchor>

## What it is
<2-3 sentence elevator>

## Who it's for
<plain-English audience>

## What it does
- <feature>
- <feature>
- ...

## How to talk about it
<1-2 paragraph spokesperson-voice prose, ready to read aloud>

## Quick facts
- Pricing: <range or free or "ask">
- Status: <plain English status>
- Find it: <URL or "ask the proprietor">

## Off-limits
- <thing not to claim>
- <thing not to claim>
```

The **How to talk about it** section is the only place where the spokesperson voice goes.
Everything else is structured facts.

The **Off-limits** section is mandatory and must be non-empty. At minimum:
`- Do not invent features not listed above`.

### Internal structure (story chunks)

```markdown
# <story beat>

**The arc.** <one-sentence framing>

## What happened
<paragraph or timeline>

## Why it matters
<paragraph — the spokesperson's "so what"

## How to talk about it
<spokesperson voice — what to say if asked>

## Off-limits
- Do not volunteer this story unless directly asked
- <other constraints>
```

### Internal structure (FAQ)

```markdown
# Frequently asked

## <Question>?
<Answer — 1-3 sentences, in voice>

## <Question>?
<Answer>

...
```

## The off-limits section is mandatory

Every chunk has an off-limits section. This is the most important guard against
hallucination. The pattern of "what the spokesperson should not say" is what keeps it
from making things up when a user pushes on a topic.

Default off-limits items every chunk inherits:
1. Do not invent features
2. Do not quote pricing not in `Quick facts`
3. Do not name specific competitors
4. Do not promise timelines for unshipped work

Add chunk-specific items beyond these.

## Review before merge

A chunk is ready when:

- [ ] Frontmatter complete
- [ ] No banned vocabulary
- [ ] All cited numbers exist in `90_facts.md` with source line
- [ ] Voice paragraph would read out loud without making the writer wince
- [ ] Off-limits section is non-empty and chunk-specific
- [ ] If a competitor / contemporary is named, it's accurate and non-disparaging
- [ ] Audience tier in frontmatter matches the writing level

If the chunk fails any of these, fix the chunk — don't relax the rule.
