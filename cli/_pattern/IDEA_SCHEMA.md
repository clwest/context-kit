---
title: "Idea file schema for `context-kit seed`"
status: stable
schema_version: 1
---

# Idea file schema

`context-kit seed idea.md` reads a structured markdown file and turns
it into the load-bearing parts of your project context. This document
is the format that command parses.

The format is plain markdown with a single H1 (the title) and a fixed
set of H2 sections. Headings are case-insensitive and tolerant of
trailing punctuation (`?`, `.`, `!`).

## Minimum viable idea file

```markdown
# Project Idea

## What are we building?

A small tool that does X for Y.
```

That's enough — every other section is optional. Seed will populate
the project's anchor docs with what you give it and use clear
placeholders where you didn't.

## Full schema

```markdown
# Project Idea

## What are we building?

<one-paragraph TL;DR — required>

## Who is it for?

<the audience — optional>

## Problem

<what it solves — optional>

## Core features

<bulleted list usually — optional>

## Tech stack

<languages, frameworks, services — optional. If you omit this section,
`context-kit seed` will call `recommend-stack` and bake an
opinionated v0 stack pick into `docs/BUILD_PLAN.md` for you. Beginners:
leave it out. You can always edit BUILD_PLAN.md afterward.>

## First milestone

<the thing you ship in session 1 — optional>

## What not to build yet

<scope discipline — optional>

## Open questions

<things to figure out — optional>
```

## Heading variations seed accepts

You can write naturally. These all map to the same canonical key:

| Canonical | Aliases |
|---|---|
| `what` | "What are we building", "What it is", "What we're building", "What we make" |
| `who` | "Who is it for", "Who it's for", "Audience" |
| `problem` | "Problem", "The Problem", "What problem" |
| `features` | "Core features", "Features", "What it does" |
| `stack` | "Tech stack", "Stack", "Tech" |
| `milestone` | "First milestone", "Milestone", "First ship", "First cut" |
| `non_goals` | "What not to build yet", "Non-goals", "Out of scope", "Not yet" |
| `questions` | "Open questions", "Questions", "Things to figure out" |

Trailing `?`, `.`, or `!` is stripped before matching.

## What happens to unrecognized headings

Don't worry about writing the headings exactly. Anything seed doesn't
recognize is preserved verbatim under an "Other notes" section in
`docs/BUILD_PLAN.md`, and seed prints an info line so you know what
fell through.

```markdown
## Inspiration

The way `make` works — declarative, no magic.

## Risks

If we get popular, the watch path approach won't scale.
```

These two will land in `docs/BUILD_PLAN.md` under "Other notes" with
their original headings preserved.

## What seed produces

For each run of `context-kit seed idea.md`, the following five files
are populated:

| File | Seed-owned section |
|---|---|
| `docs/<APP>_WHAT_IT_IS.md` | TL;DR + "What we're deliberately not building yet" |
| `00-START-NEXT-SESSION.md` | "FIRST THING — first milestone" + "Queued Investigations" |
| `docs/handoffs/SESSION_001_IDEA_BOOTSTRAP.md` | The full file (write-once history) |
| `docs/topics/product.md` | Product framing (what / who / problem) |
| `docs/BUILD_PLAN.md` | Full structured plan + "Implementation notes" stub for you |

Seed-owned content lives between markers:

```markdown
<!-- context-kit:seed:start -->
... seed-generated content; do not edit by hand ...
<!-- context-kit:seed:end -->
```

Anything outside the markers is yours forever. Re-running seed updates
content inside the markers; it never touches what's outside them.

## What seed deliberately does NOT touch

- `docs/<APP>_INVENTORY.md` — that's owned by `context-kit inventory`.
  Run `context-kit inventory --write` after seed.
- The 8 numbered guide docs in `docs/docs-pattern/`.
- Bundled skills in `.claude/skills/`.
- Any `docs/handoffs/SESSION_NNN_*.md` for `N >= 2`.
- `00-START-NEXT-SESSION.md` after a real session-end handoff has been
  written. (Detected via the `state:` frontmatter — `scaffold` =
  fresh, `seeded` = seed has run, anything else = the human has taken
  over and seed will refuse without `--force`.)

## Workflow

```bash
# 1. Scaffold
context-kit init "My App"
cd my-app

# 2. Write your idea
$EDITOR idea.md

# 3. (Optional) Get a stack opinion before seeding
context-kit recommend-stack idea.md

# 4. Seed (will auto-fill Tech stack if you omitted it)
context-kit seed idea.md

# 5. Refresh the runtime anchor
context-kit inventory --write

# 6. Verify the agent sees what it needs
context-kit orient

# 7. Build
claude  # or your AI tool of choice
```

## Re-running seed

Seed is idempotent: same `idea.md` → same output. If you edit
`idea.md` and re-run, only the seed-owned content updates. Your
edits outside the markers, and your `Implementation notes` section
in `BUILD_PLAN.md`, survive untouched.

The one exception is `SESSION_001_IDEA_BOOTSTRAP.md` — it's a
historical record, written once. If your project genuinely pivots,
write `SESSION_NNN_PIVOT.md` yourself; seed never invents history.

Use `--force` to override the safety checks (overwrite handoff,
re-seed `00-START` regardless of frontmatter state). Use `--dry-run`
to preview without writing.

## Schema versioning

Each managed block records `Schema version: 1`. When the schema
evolves later, the renderer can detect older blocks and either
upgrade in place or warn.
