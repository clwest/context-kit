---
title: "context-kit — build AI projects that don't lose context"
status: active
---

# context-kit

**Build AI projects that don't lose context.**

context-kit scaffolds the structure, memory layer, and drift detection that
keep your AI pair programmer from starting over every session.

Think `create-next-app`, but for the memory layer around your code.

> Distilled from ~1,100 AI-assisted build sessions across ~18 months of
> shipping production code with an AI pair. Every rule here cost a real
> bug, a dead-end session, or a silent hallucination to learn.

---

## The problem

AI-assisted projects decay in predictable ways:

- **Context is lost across sessions.** The model has no memory of what was
  decided yesterday or why. Every session starts cold.
- **Docs drift from reality.** Hand-maintained claims rot within days. The
  doc says "83 agents," the code has 101, and nobody notices until the AI
  confidently cites the wrong one.
- **The AI becomes unreliable.** Stale context plus drifted docs equals
  confident hallucinations. Trust erodes in both directions.

context-kit gives every new project the same proven structure from day one:
a narrative anchor, a runtime-derived inventory, a drift verifier, session
handoffs, and explicit AI/human collaboration conventions.

---

## Quick start

```bash
# 1. Scaffold a new project
python3 context_kit.py init "My App"

# 2. Enter it
cd my-app

# 3. Open the onboarding page (opens your browser — no install required)
python3 context_kit.py start
```

That's it. The onboarding page walks you through the first-session checklist
and shows you which files matter most.

With the optional Python scaffold (drift verifier + index builder):

```bash
python3 context_kit.py init "My App" --with-scaffold
```

Custom target directory:

```bash
python3 context_kit.py init "My App" --target ~/projects/my-app
```

---

## What's in the box

Two things ship together on purpose:

**The tool** — `context_kit.py` plus `cli/`, `starter/`, and `examples/`.
A zero-dependency Python CLI that scaffolds a new project and runs a
localhost onboarding page. Start here if you just want to begin.

**The teaching material** — 8 short guide docs (`01_*.md` through `08_*.md`)
plus reference templates under `templates/`. Every new project gets its own
copy at `docs/docs-pattern/`. Read these to understand *why* the pattern
works.

The value isn't the files — it's the habits this structure enforces.

See `examples/EXAMPLE_OUTPUT.md` for the full generated tree.

---

## CLI reference

```
context-kit COMMAND [options]

Commands:
  init NAME            Scaffold a new project with the context-kit pattern
  start                Launch the onboarding server for the current project

Run `python3 context_kit.py <command> --help` for per-command options.
```

**`init` options**

| Flag | Default | Purpose |
|---|---|---|
| *positional* `NAME` | required | App name, e.g. `"My App"` or `my-app` |
| `--target DIR` | `./<slug>` | Where to write the project |
| `--with-scaffold` | off | Include optional Python scaffold |
| `--force` | off | Overwrite existing files at the target |
| `--quiet` | off | Suppress per-file output |

**`start` options**

| Flag | Default | Purpose |
|---|---|---|
| `--host HOST` | `127.0.0.1` | Host to bind |
| `--port PORT` | `0` (auto) | Port; `0` lets the OS pick a free one |
| `--no-browser` | off | Don't auto-open the browser |

---

## What gets generated

```
my-app/
├── context_kit.py                   # runtime entry point (for `start`)
├── cli/
│   ├── __init__.py
│   └── server.py                     # onboarding server
├── 00-START-NEXT-SESSION.md         # first-session entry point
├── CLAUDE.md                         # AI session entry rules
└── docs/
    ├── MY_APP_WHAT_IT_IS.md          # narrative anchor (stub)
    ├── MY_APP_INVENTORY.md           # runtime anchor (stub)
    ├── TRUST_CALIBRATION.md          # AI ↔ human calibration log
    ├── docs-pattern/                 # the teaching framework (copied in full)
    ├── handoffs/
    │   └── SESSION_001_BOOTSTRAP.md
    └── topics/
        └── infrastructure.md         # first subsystem stub
```

With `--with-scaffold` you also get `scaffold/python/doc_claim_verification.py`
and `scaffold/python/build_docs_index.py`.

The generated project runs `start` standalone — no need to keep the
context-kit source repo around after bootstrapping.

---

## Why `docs/docs-pattern/` inside generated projects

context-kit is the **tool**. "docs-pattern" is the **teaching material**
the tool ships. Same relationship as `create-next-app` (tool) → `next.js`
(framework content it scaffolds).

The directory name `docs/docs-pattern/` inside your generated project
preserves a stable reference: the 8 guide docs cross-link to each other
and to the templates by that path, and everyone who has seen the pattern
knows to look for it there. Keeping the directory name stable means the
guide docs don't need rewriting for every new project.

---

## What's framework-agnostic, what's not

| Piece | Portable? | Notes |
|---|---|---|
| The 8 guide docs | ✅ Any stack | Principles, not code |
| Reference templates in `templates/` | ✅ Any stack | Markdown + a Python skeleton |
| Starter tree under `starter/root/` + `starter/docs/` | ✅ Any stack | Pure Markdown |
| Bootstrap CLI + onboarding server | ✅ Python 3.9+ | stdlib only, no deps |
| `starter/scaffold/python/doc_claim_verification.py` | 🟡 Python projects | Framework-neutral; wire into Django / Typer / etc. |
| `starter/scaffold/python/build_docs_index.py` | 🟡 Python projects | Runnable standalone; trivially portable to Node |

Everything under `starter/root/` + `starter/docs/` works for any stack.
Everything under `starter/scaffold/` is language-specific and opt-in.

---

## Placeholders

The bootstrap derives every form from a single `NAME`:

| Placeholder | Input `"My App"` | Input `"donkey-betz"` |
|---|---|---|
| `{{APP}}` | `My App` | `donkey-betz` |
| `{{APP_SLUG}}` | `my-app` | `donkey-betz` |
| `{{APP_UPPER}}` | `MY_APP` | `DONKEY_BETZ` |
| `{{APP_TITLE}}` | `My App` | `Donkey Betz` |
| `{{DATE}}` | today, YYYY-MM-DD | today, YYYY-MM-DD |
| `{{YEAR}}` | today's year | today's year |

Placeholders appear in both filenames (`{{APP_UPPER}}_WHAT_IT_IS.md` →
`MY_APP_WHAT_IT_IS.md`) and file contents.

---

## Repo layout

```
context-kit/
├── README.md                         # this file
├── 01_two_doc_anchor.md              # ┐
├── 02_drift_verifier.md              # │
├── 03_topic_docs.md                  # │ teaching content
├── 04_session_handoffs.md            # │ (8 guide docs)
├── 05_start_here.md                  # │
├── 06_dos_and_donts.md               # │
├── 07_bootstrap_checklist.md         # │
├── 08_collaboration_roles.md         # ┘
├── templates/                        # reference templates (generic)
├── context_kit.py                    # CLI entry point
├── cli/
│   ├── __init__.py
│   ├── bootstrap.py                  # `init` implementation
│   ├── placeholders.py               # shared placeholder logic
│   └── server.py                     # `start` implementation
├── starter/                          # files rendered into new projects
│   ├── root/                         # → new project's root
│   ├── docs/                         # → new project's docs/
│   └── scaffold/                     # → optional, behind --with-scaffold
└── examples/
    └── EXAMPLE_OUTPUT.md             # annotated generated tree
```

When `init` runs, `cli/`, `starter/`, `examples/` (and the source
`context_kit.py`) are **excluded** from the copy into
`<project>/docs/docs-pattern/` — those are tooling, not teaching material.
The guide docs + `templates/` + this README are copied in.

Separately, the runtime files needed to run `start` inside the generated
project (`context_kit.py`, `cli/__init__.py`, `cli/server.py`) are copied
to the generated project's root so it works standalone.

---

## Core principles (the short version)

| Piece | File in generated project | Purpose |
|---|---|---|
| Narrative anchor | `docs/<APP>_WHAT_IT_IS.md` | *What is this system?* — conceptual doc |
| Runtime anchor | `docs/<APP>_INVENTORY.md` | *What exists right now?* — regenerable |
| Drift verifier | `scaffold/python/doc_claim_verification.py` | Finds stale claims automatically |
| Topic docs | `docs/topics/<subsystem>.md` | Embeddable deep-dives |
| Handoffs | `docs/handoffs/SESSION_####_*.md` | Build history, one per session |
| Entry point | `00-START-NEXT-SESSION.md` | Where every session begins |
| Calibration log | `docs/TRUST_CALIBRATION.md` | AI ↔ human calibration events |

**Single principle: runtime wins.** If a number is in a hand-written doc
and the verifier says it's wrong, the verifier is right. Fix the doc, or
tag it with a pointer header, and move on.

---

## Development

Zero runtime dependencies (Python 3.9+ stdlib only). Quick local test:

```bash
# Scaffold into a temp directory
python3 context_kit.py init "Test App" --target /tmp/test-app --force

# Run onboarding from inside the generated project
cd /tmp/test-app && python3 context_kit.py start --no-browser
```

To iterate on starter templates, edit files under `starter/` — placeholders
use `{{NAME}}` syntax. To iterate on the guide, edit `01_*.md` through
`08_*.md` (these are copied as-is into every generated project).

---

## Testing

Tests use only the standard library (`unittest`). From the repo root:

```bash
python3 -m unittest discover -s tests -t .
```

Three suites cover the surface area: placeholder derivation, end-to-end
bootstrap into a temp directory, and a live onboarding server on an
OS-picked port.

---

## Installable CLI (experimental)

A minimal `pyproject.toml` is shipped so the CLI can be installed editable:

```bash
pip install -e .
context-kit init "My App"
context-kit start
```

Editable installs work end-to-end today. Wheel distribution is Phase 4 work
(the starter tree and guide docs need packaging as data files, not just
Python modules).

---

## Status

- **Phase 1** (minimal working bootstrap) — ✅ shipped
- **Phase 2** (rename to context-kit + onboarding server) — ✅ shipped
- **Phase 3** (tests + pyproject + git init + README polish) — ✅ shipped
- Phase 4 (wheel packaging, LICENSE, release workflow) — planned

---

*The pattern is "human and AI working together," not "human using AI to do
something for them." The 8 guide docs explain why. context-kit makes the
first project cheap.*
