# Spokesperson Corpus — Generation Recipe

Step-by-step for turning a project's internal docs into a public-voice corpus the
spokesperson can be grounded in. Assumes you've already `cp -r`'d the pattern into
`<project>/docs/spokesperson/`.

## Inputs (gather these first)

The corpus pulls from sources you already have. Don't write them from scratch — pull,
sanitize, restructure.

| Source | What you take from it |
|---|---|
| **Narrative anchor** (`PLATFORM_WHAT_IT_IS.md` or equivalent) | TL;DR for the overview chunk · capability framing for engine chunks |
| **Runtime inventory** (`PLATFORM_INVENTORY.md` or equivalent) | Verifiable numbers for the facts chunk · grounding for claims |
| **Public taxonomy source** (e.g. `products.ts`, a CMS export, a marketing page) | One chunk per entry — names, taglines, elevator pitches, pricing |
| **Recent handoffs** (last 1-3 sessions) | Story chunks · what shipped recently · what's the current arc |
| **Brand voice doc** (if it exists) | Drop straight into `voice.md` chunk |

If the project doesn't have a narrative anchor, build that first. The corpus depends on it.

## The seven steps

### 1. Audience tier

Decide **before writing anything** who the spokesperson talks to. The voice and what gets
included differ sharply:

- **Public-everyone** (investors + customers + partners + curious visitors) — most
  conservative voice; no internal jargon; no unshipped roadmap; assume non-technical reader
- **Public-builders** (engineers, technical buyers) — can use stack-level detail; can
  reference architecture; still no internal codenames or session numbers
- **Operator-only** (paying customers / power users) — can reference unshipped features
  under NDA, can use product-specific shorthand

Write the tier into every chunk's frontmatter as `audience: <tier>`. Mixed-tier corpora are
possible but require explicit per-chunk tier and a guard in the retrieval layer.

### 2. Voice anchor

Pick one source-of-truth voice document and copy its full text into `01_voice.md`. This is
non-negotiable — the spokesperson needs the exact voice rules in its context, not your
paraphrase. If the brand voice lives in `products.ts` comments or a marketing site footer,
that's your anchor.

Voice anchor must answer:
- What's the tagline / motto?
- What three adjectives describe the voice?
- What vocabulary is banned? (Common bans: "AI-powered", "revolutionary", "leverage",
  "harness", "synergy", "game-changer")
- Are there typographic / numbering conventions? (Roman numerals, em dashes, sentence case)
- What's the proprietor's / founder's first-person framing, if any?

### 3. Overview chunk

A 200-400 word elevator that someone could read in 90 seconds and walk away knowing what
the project is. Pull from the narrative anchor's TL;DR section.

Structure:
- **One-sentence summary** (what it is, in plain English)
- **Why it exists** (the problem or gap)
- **What's shipped vs. what's coming** (honest tier: stable, demo-ready, in-development)
- **Where to go next** (URL, signup, repo, "ask the proprietor")

### 4. Product / capability chunks

One file per public entity. Use `templates/_product.md` as the shape. Source from the
public taxonomy export — most projects already have this somewhere (a `products.ts`, a
CMS export, a comparison table on the website).

For each product:
- Pull `tagline`, `elevator`, `features`, `pricing`, `status`, `url` straight from source
- Add a **"How to talk about it"** paragraph — this is new prose, written in the
  spokesperson voice, that the AI can quote when asked about this thing
- Add an **"Off-limits"** section listing what NOT to claim (unshipped features,
  prior pricing, deprecated names, internal codenames for this product)

### 5. Engine / behind-the-scenes chunks

For projects where the product is powered by something interesting behind the scenes
(monolith, agent network, model router, knowledge graph), write **sanitized capability
reveals** — the public version of what's under the hood.

Sanitization rules:
- Replace internal codename → "the engine" or "the studio's <function>"
- Replace stack details with capability framing ("an engine that watches 80 sources" vs
  "Scrapy spiders on a Celery worker pool")
- Replace internal counts with public-OK counts (verify against runtime inventory)
- Cut any reference to internal-only systems (CI infra, deploy targets, internal tools)

If the engine is genuinely private, write **one** chunk that acknowledges it exists and
declines to detail it — better than the spokesperson making something up.

### 6. Story chunks

Origin, pivot, "what changed" — the narrative beats people ask about. Source from
session handoffs and any company-history document.

Story chunks need:
- A clean timeline (year, season, milestone — not session numbers)
- The honest version of "what we changed and why" (especially around rebrand / pivot)
- An explicit list of "things the spokesperson should NOT volunteer" (old company name,
  old pricing, deprecated products) unless directly asked

### 7. FAQ + Facts

The last two chunks before publishing:

- **FAQ** — anticipate the 8-15 questions the spokesperson will actually field. Write the
  exact answer the spokesperson should give. Common categories: pricing, what's shipped,
  who's behind it, where to start, what makes it different, refund / cancellation, support.
- **Facts** — every verifiable number cited anywhere in the corpus, with a one-line
  citation back to source-of-truth (e.g. "80 spiders — source: PLATFORM_INVENTORY.md,
  generated 2026-05-21"). The spokesperson reads this when asked to defend a claim.

## Sanitization checklist (run on every chunk before merge)

- [ ] No session numbers, PR IDs, commit hashes
- [ ] No internal codenames (unless the codename is the public brand name)
- [ ] No stack jargon if audience is public-everyone (Celery, Django, ORM, FK, etc.)
- [ ] No unshipped roadmap unless audience is operator-only
- [ ] No comparisons to specific competitors (legal risk)
- [ ] No claims that aren't traceable to source-of-truth
- [ ] No "AI-powered" / "revolutionary" / banned vocabulary
- [ ] Tagline matches voice anchor exactly
- [ ] Pricing matches public taxonomy source exactly
- [ ] Off-limits section is non-empty (at minimum: "do not invent features")

## Refresh trigger

Re-run this recipe when any of:
- A new product / capability ships
- Pricing changes
- The brand voice doc changes
- A handoff captures a meaningful pivot or rebrand
- Runtime inventory shifts in ways that affect public facts (counts cited in chunks)

The refresh **must** include re-ingestion into the downstream spokesperson system,
otherwise the corpus drifts from what the spokesperson actually knows.

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Spokesperson claims unshipped features | Roadmap leaked into chunks | Tighten Step 4 off-limits |
| Spokesperson sounds generic / AI-tinted | Voice anchor too thin or paraphrased | Copy voice anchor verbatim, don't summarize |
| Spokesperson cites wrong pricing | Pricing was copied at write time, not pulled from source | Add a freshness check or pull-at-render |
| Spokesperson invents history | Story chunks too vague | Add specific dates / milestones to story chunks |
| Different chunks use different names for same thing | No naming-conventions section in voice anchor | Add a "canonical names" table to `01_voice.md` |
