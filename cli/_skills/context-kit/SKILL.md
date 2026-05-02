---
name: context-kit
description: Use at the start of every session in a context-kit project (any repo with a 00-START-NEXT-SESSION.md or docs/docs-pattern/ folder). Loads the project's authoritative orientation — start-here doc, narrative + runtime anchors, latest handoff — so the agent acts on real project state instead of guessing. Invoke before writing code, answering project questions, or modifying docs in such a project.
---

# context-kit — session orientation skill

You are about to do work in a project that uses the **context-kit pattern**.
Before you write code, propose changes, or answer questions about the project,
you must orient yourself against the project's own source-of-truth files.

The pattern's load-bearing rule is **runtime wins**: when narrative docs and
runtime-derived state disagree, the runtime side is correct.

## Step 1 — Run orient

From the project root, run:

```bash
context-kit orient
```

Or if `context-kit` is not on PATH:

```bash
python3 context_kit.py orient
```

This prints, in priority order:

1. **Source of truth** — which docs are authoritative, in which order
2. **Start here** — the current session's priorities (`00-START-NEXT-SESSION.md`)
3. **Anchors** — narrative anchor (`*_WHAT_IT_IS.md`) and runtime anchor (`*_INVENTORY.md`)
4. **Latest handoff** — what the previous session shipped
5. **The pattern** — pointers to the framework guide
6. **What to do now** — the discipline that keeps future sessions cheap

Read the entire output. Do not skim. The whole point of this skill is to
spend the tokens *now* so you don't burn far more guessing later.

## Step 2 — Anchor on what you read

After reading the orient output:

- **Trust the runtime anchor** (`*_INVENTORY.md`) over the narrative anchor
  (`*_WHAT_IT_IS.md`) when they disagree. Trust both over your priors.
- **Trust the latest handoff** for what state the project is actually in.
- **The start-here doc tells you what comes next** — if it names a "FIRST
  THING", that is the literal first thing you do.

## Step 3 — Behave like the pattern expects

While working in the project:

- **Don't invent stats.** If you need a number (count of agents, services,
  routes, anything quantitative) and it is not in the inventory, say so
  out loud rather than guessing. Suggest regenerating the inventory if a
  generator exists.
- **Don't trust narrative docs as runtime state.** A doc saying "we have
  83 agents" is a *claim*, not a fact. The inventory or a verifier is the
  fact.
- **End the session by writing the next handoff.** Append to
  `docs/handoffs/` as `SESSION_NNN_<slug>.md` and overwrite
  `00-START-NEXT-SESSION.md` with the next session's priorities.
  This is not optional — it is what makes the *next* session cheap.
- **Push back when asked to do something that contradicts the anchors.**
  The collaboration rule is "AI drafts, human edits, AI is expected to
  push back when framing looks wrong."

## Optional — run seed before orient on a fresh project

If the project's `00-START-NEXT-SESSION.md` frontmatter shows
`state: scaffold` *and* there's an `idea.md` (or similar structured
idea file) at the project root, the user hasn't seeded yet. Suggest:

```bash
context-kit seed idea.md
```

This populates the narrative anchor's TL;DR, the start-here doc's
first milestone, a bootstrap handoff, a product-framing topic, and a
`BUILD_PLAN.md` from the idea file. After that, `orient` will surface
real intent instead of empty stubs. Deterministic — no LLM calls.

If `state:` is `seeded` or anything other than `scaffold`, the
project has already moved past the seed step; don't re-suggest it.

## Optional — run recommend-stack when the user doesn't know what to build with

If the user has a clear *what* but vague or empty *tech stack* in their
idea file (or hasn't started one), suggest:

```bash
context-kit recommend-stack idea.md
```

It returns an opinionated v0 stack pick: what to use, why, what not to
add yet, when to upgrade. Deterministic, no LLM. Designed for
beginners who can describe the problem but not the implementation.

If the user runs `seed` next and their idea file has no `## Tech stack`
section, `seed` calls this same engine automatically and bakes the
recommendation into `docs/BUILD_PLAN.md`.

## Optional — run translation-init to populate the audience contract

If the user asks you to "explain this to <person>", "translate this
for <stakeholder>", "operate as <persona>", or "populate the
translation layer", and the project has
`docs/<APP>_TRANSLATION_LAYER.md` still on default scaffold values
(generic Builder / Operator / Executive / Tester personas, the
`/api/admin/*` example), run:

```bash
context-kit translation-init
```

It prints a structured five-step recipe that tells you exactly how
to:

1. Read source-of-truth (anchors + latest handoff).
2. Interview the user about real audiences, decision authority, and
   one concrete fact to translate.
3. Write a populated `docs/<APP>_TRANSLATION_LAYER.md` with real
   personas, real translation modes, and a real worked example
   drawn from source-of-truth.
4. Verify zero invention — every claim traces back.
5. Confirm with the user, then switch into the named persona's
   mode for the rest of the session.

The CLI does not call an LLM. It hands you the recipe; you execute
it. After the doc is populated, it auto-loads via `orient` on every
future session — switching into a persona's mode becomes one
sentence at session start.

If the existing translation layer doc has already been hand-edited
away from defaults, do **not** overwrite it. Propose specific
amendments instead.

## Live chat mode for non-technical personas

If `docs/<APP>_TRANSLATION_LAYER.md` exists and contains a
`## Live Chat Mode` section with one or more per-persona blocks,
**this is a runtime contract on you**, not just doc content.

The contract activates the moment one of these happens:

- A user identifies as a named persona — *"Hi, I'm Jessica"*,
  *"This is Jessica"*, or any trigger phrase listed in that
  persona's block.
- The user explicitly says *"operate as <persona>"*.
- A previous message in the session has already activated it.

When active:

1. **Honor every prohibition** in that persona's block — no code
   blocks, no file paths, no framework / library / language names,
   no acronyms unless the persona used them first, no jargon words
   listed in their block.
2. **Apply every substitution** in their table for the rest of the
   session.
3. **Use the refusal rule** when a truthful answer needs prohibited
   words: *"I can't answer that cleanly without using technical
   words — want a higher-level version, or the technical version
   just this once?"* Don't invent analogies that aren't grounded in
   source-of-truth.
4. **Restate the active persona** at the top of every reply so the
   contract isn't lost across long exchanges.
5. **Stay in character** until the user explicitly drops it. A
   technical question in mid-conversation is not permission to
   break — use the refusal rule instead.

The Truth Preservation Rules still apply. Chat mode changes
vocabulary and format, never facts. If a fact isn't in
source-of-truth, the chat-mode reply still has to hedge or refuse.

If the persona the user named has *no* chat-mode block (a
builder / engineer persona), no flip is needed — operate in their
translation mode (technical bullets / business-impact paragraph /
executive brief / QA checklist) and code / paths / framework names
are fine.

## Optional — run doctor when something feels off in the environment

If the user is hitting build/run errors that look like environment
issues (EMFILE, "command not found", Expo Go won't connect, Python
version mismatch, etc.) suggest:

```bash
context-kit doctor
```

It runs read-only checks against Python, git, Node.js, Expo SDK +
config, file-watcher / `ulimit` pressure, and the project's own
context-kit structure. Exits 1 only on **blocking** issues; warnings
are advisory.

Use `--json` to pipe the result somewhere structured.

## Optional — run hotpath when scope feels large

If the orient output reveals a project with many or very long anchor
docs, or you find yourself reading the same files repeatedly without
making progress, run:

```bash
context-kit hotpath
```

It lists the largest files in the project and warns when any one file
or the top-N sum is likely to dominate your context window. The output
is advisory — when it warns, the right move is usually to narrow focus
to one file at a time, or stop and start a fresh session before
tackling the hot region.

## Optional — run refactor track when working a multi-PR extraction

If the user is in the middle of splitting a monolith file (e.g.
`core/tasks.py`) into sibling modules across many PRs, run:

```bash
context-kit refactor track core/tasks.py --detector celery-task
```

It prints total / migrated / remaining item counts, percentage
complete, the largest remaining domains (when a Phase-0-style plan
file is provided via `--plan` or auto-discovered under
`docs/refactors/`), and an estimated PRs-remaining number. Detectors
in v1: `function`, `class`, `celery-task`. Read-only.

## When the orient command does not exist

If `context-kit orient` and `python3 context_kit.py orient` both fail, the
project either predates the orient subcommand or was set up by hand. Fall
back to reading these files directly, in order:

1. `00-START-NEXT-SESSION.md` (repo root)
2. `docs/*_WHAT_IT_IS.md`
3. `docs/*_INVENTORY.md`
4. The most recent `docs/handoffs/SESSION_*.md`
5. `docs/docs-pattern/README.md` if it exists (the framework guide)

The order is what matters. Read all five before doing project work.

## When this skill does NOT apply

- Repos with no `00-START-NEXT-SESSION.md` and no `docs/docs-pattern/`
  folder — they don't use this pattern. Don't try to force it.
- One-off scripts, throwaway prototypes, or repos where the human is
  clearly driving and just wants a small change.
- Pure documentation edits to `docs/docs-pattern/` itself — that's the
  framework, not a project using the framework.

## If the project ISN'T context-kit yet

If a user asks you to help with a project that has no
context-kit markers but they want the same memory layer wrapped
around their existing code, **suggest `context-kit adopt`**.
It's the retrofit entry point — read-only against source by
default. Output leads with an **Adopt Summary** card naming
the project's Type, Structure (per-child workspace stacks),
Reality (assessment + confidence + why), and prioritized Next
actions. It generates the load-bearing docs
(`docs/BUILD_PLAN.md`, `docs/PROJECT_WHAT_IT_IS.md`,
`00-START-NEXT-SESSION.md`, augments any existing `CLAUDE.md`),
and surfaces "Diagnostic signals" — metadata from adopt's
internal failure taxonomy — when classification limits or
review priorities are worth flagging. (Diagnostic signals are
informational, not errors in the user's repo.)

Every adopt run also produces an **Agent Launch Prompt** — a
single copy-paste block that tells the next AI agent the
project's shape, the user's framing, a recommended read-only
first action, and explicit safety rules. Suggest the user
hand this prompt to their AI agent as the first message of
the next session. Two flags make adopt fully non-interactive:
``--project-summary "..."`` and ``--next-task "..."`` — useful
for scripted demos and CI.

The dry-run plus `--html` (`context-kit adopt . --html`) opens
a single self-contained static review report that's much easier
to scan than terminal output on large repos.

---

*This skill ships with [context-kit](https://github.com/clwest/context-kit).
It is the agent-facing entry point; `context-kit orient` is the human-facing
one. They read from the same source so they cannot disagree.*
