---
title: "context-kit — What It Actually Is"
status: active
generated: 2026-04-25
last_revised: 2026-05-21 (SESSION 19)
companion_doc: CONTEXT_KIT_INVENTORY.md
---

# context-kit — What It Actually Is

> **Read-order note:** this is the conceptual anchor for the
> context-kit repo. Its companion, [`CONTEXT_KIT_INVENTORY.md`](CONTEXT_KIT_INVENTORY.md),
> is the runtime anchor — *what exists right now* in the repo. Until a
> real inventory generator is built, the inventory is hand-maintained;
> when narrative and inventory disagree on a number, the inventory still
> wins by convention so the discipline holds.

---

## Adapted, not literal

This repo's adoption of its own pattern is **adapted**, not a literal
copy of what `context-kit init` generates. The reason: context-kit is
both *the tool* (a Python CLI) and *the teaching material* (8 guide
docs that explain why the pattern works). A generated project ships
the guide docs at `docs/docs-pattern/` because that's the only place
they exist. In this repo they live at the root (`01_*.md` …
`08_*.md`) because they're the source files. Duplicating them under
`docs/docs-pattern/` would be silly.

So if you've seen a generated project, the layout here will look
*almost* the same — anchor docs, start-here, handoffs, calibration
log — but the framework guide is at the root, not nested.

---

## TL;DR — One Sentence

context-kit scaffolds the session-handoff, two-doc anchor, drift
verifier, and AI-collaboration conventions that keep AI-assisted
projects from losing context across sessions, distilled from ~1,100
AI-assisted build sessions.

**Scale (manual, see inventory):** ~7 Python source files, 5 CLI
subcommands, 8 guide docs, 1 Claude skill, 69 unit tests.

---

## Who it's for

- Developers using AI pair programmers (Claude Code, Cursor, etc.) on
  projects that span more than one session.
- People who have hit the failure mode where the AI "starts over"
  every session — re-derives layout, re-asks decided questions,
  hallucinates stats that drifted out of the docs.
- Teams that want the AI's behavior to be a function of the project's
  *structure*, not the human's prompt discipline.

It is **not** for one-off scripts, throwaway prototypes, or projects
where a single session ships everything.

---

## What it ships

Two things on purpose:

**The tool.** A zero-dependency Python CLI:

| Subcommand | Purpose |
|---|---|
| `init NAME` | Scaffold a new project with the full pattern in place. |
| `start` | Launch a localhost onboarding page for a generated project. |
| `orient` | Print the project's authoritative session-start context as one plain-text report. The Claude skill calls this. |
| `hotpath` | Read-only file-size dashboard. Warns when any file or the top-N sum is large enough to dominate an AI session's context. |
| `verify` | Read-only truth/status layer that checks whether key repo claims are verified, doc-only, conflicting, or unknown. |

**The teaching material.** 8 guide docs at the repo root explaining
each piece of the pattern:

| File | Topic |
|---|---|
| `01_two_doc_anchor.md` | Narrative vs runtime split |
| `02_drift_verifier.md` | How runtime stays authoritative |
| `03_topic_docs.md` | Embeddable subsystem docs |
| `04_session_handoffs.md` | Append-only build history |
| `05_start_here.md` | Why `00-START-NEXT-SESSION.md` exists |
| `06_dos_and_donts.md` | Anti-patterns from real failures |
| `07_bootstrap_checklist.md` | The first-session sequence |
| `08_collaboration_roles.md` | How AI and human share work |

Plus reference templates under `templates/`, an optional Python
scaffold for the drift verifier and docs index builder, and a
bundled Claude Code skill at `skills/context-kit/SKILL.md`.

---

## Layered architecture

```
                    ┌─────────────────────────────┐
                    │   Bundled Claude skill      │  agent-facing entry
                    │  skills/context-kit/        │
                    └──────────────┬──────────────┘
                                   │ calls
                                   ▼
        ┌──────────────────────────────────────────────┐
        │  context-kit CLI                              │
        │   init  •  start  •  orient  •  hotpath       │  human + agent
        │   (cli/bootstrap.py, server.py, orient.py,    │   share interface
        │    hotpath.py)                                │
        └──────────────┬────────────────┬──────────────┘
                       │                │
                       ▼                ▼
        ┌──────────────────────┐  ┌─────────────────────┐
        │  starter/ + templates │  │  Guide docs (01-08) │
        │  (project skeleton)   │  │  (teaching material) │
        └──────────────────────┘  └─────────────────────┘
```

The two outputs of `init` are kept separate on purpose: the *project
skeleton* is what the developer edits on day one; the *teaching
material* is reference content the developer reads to understand the
pattern.

---

## The single principle

**Runtime wins.** When the narrative anchor says "83 agents" and the
runtime anchor (or a verifier) says "101," the runtime side is right.
This is the discipline that keeps the whole pattern honest, and it's
why `INVENTORY.md` is a peer of `WHAT_IT_IS.md`, not a footnote inside it.

In this repo, the inventory is hand-maintained until a real generator
exists (see Session 2 punch list). The discipline holds anyway:
when the file count or test count drifts, fix the inventory; do not
quietly update the narrative.

---

## What it deliberately is *not*

- Not a docs website. The files are Markdown for a reason — they live
  next to the code and travel with the repo.
- Not a framework. There are no abstractions to learn beyond
  "narrative anchor, runtime anchor, handoff, start-here." If you can
  write Markdown and run a Python script, you have everything you need.
- Not a memory store, vector DB, or "AI memory layer." It is a
  filesystem layout plus a small CLI. The "memory" is whatever the
  agent reads when it runs `orient`.
- Not opinionated about your stack. Anything under `starter/root/` and
  `starter/docs/` is pure Markdown. The optional Python scaffold under
  `starter/scaffold/` is opt-in via `--with-scaffold`.

---

## Origin

Distilled from ~1,100 AI-assisted build sessions across ~18 months of
shipping production code (mostly Django + React + Celery, with a Python
agent-orchestration layer). Every rule in the guide docs cost a real
bug, a dead-end session, or a silent hallucination to learn.

The first public release (`0.3.0`) shipped 2026-04-21. The `orient`
command, Claude skill, and `hotpath` shipped on 2026-04-25 in
response to LinkedIn feedback from Damian Tedrow, Brian Turney, and
Austin (Ethereum Foundation).

See `CHANGELOG.md` for the live release history.
