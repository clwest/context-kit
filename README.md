---
title: "context-kit — build AI projects that don't lose context"
status: active
---

# context-kit

**Build AI projects that don't lose context.**

context-kit scaffolds the structure, memory layer, and drift detection that
keep your AI pair programmer from starting over every session. Designed
so even non-technical builders can go from a raw idea to a Claude-ready
project without choosing a stack alone.

Five commands, one loop:

```
init  →  recommend-stack  →  seed  →  doctor  →  orient
```

| Step | What it does |
|---|---|
| **`context-kit init`** | Creates the project memory structure |
| **`context-kit recommend-stack idea.md`** | Helps beginners pick a sane v0 stack from their idea |
| **`context-kit seed idea.md`** | Turns the raw idea into Claude-ready context |
| **`context-kit doctor`** | Catches environment / setup blockers before they bite |
| **`context-kit orient`** | Loads the current context for the next AI session *(the bundled Claude Code skill calls this automatically)* |

Plus `inventory --check` for CI drift detection and `hotpath` for
file-size budget warnings. All read-only by default. All exit cleanly
for an agent to parse.

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

## Install

```bash
pip install contextkit-ai
# or, isolated:
pipx install contextkit-ai
```

The PyPI distribution is **`contextkit-ai`** (the unsuffixed
`context-kit` name was rejected as too similar to another project).
The CLI command and the GitHub repo are still `context-kit` — only
the install command differs:

```bash
$ pip install contextkit-ai
$ context-kit init "My App"
```

Or from source (editable install):

```bash
git clone https://github.com/clwest/context-kit
cd context-kit
pip install -e .
```

## Quick start

**If you're new, just run this:**

```bash
context-kit start
```

It opens a guided onboarding page in your browser that walks you
through naming the project, writing your idea, running the right CLI
commands, and getting your environment ready. You don't have to know
what `init`, `seed`, `recommend-stack`, `doctor`, or `orient` mean
before you begin — the wizard surfaces each one at the right moment.

For experienced builders who want the CLI directly, the full beginner
loop, end-to-end:

```bash
# 1. Scaffold the project
context-kit init "My App"
cd my-app

# 2. Write a structured idea file (see docs/docs-pattern/IDEA_SCHEMA.md)
$EDITOR idea.md

# 3. Get an opinionated v0 stack pick (skip if you already know your stack)
context-kit recommend-stack idea.md

# 4. Bake the idea + recommendation into project context
context-kit seed idea.md

# 5. Verify your environment is ready (Python, git, Node, Expo, etc.)
context-kit doctor

# 6. Confirm the agent has what it needs at session start
context-kit orient

# 7. Build
claude  # or your AI tool of choice — the bundled skill auto-loads
```

Each command is read-only-by-default (`init` and `seed` write; the
others just report). Exit codes are CI-friendly. Run any of them
individually whenever you need them; nothing depends on a fixed order
after the first few.

For experienced builders: skip steps 3 and 5 unless you want them.
The minimum loop is `init → seed → orient`.

With the optional Python scaffold (drift verifier + index builder):

```bash
context-kit init "My App" --with-scaffold
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
  seed PATH            Turn a structured idea file into project context (5 files)
  recommend-stack PATH Suggest a beginner-friendly v0 stack from an idea file
  start                Launch the onboarding server for the current project
  orient               Print the assembled session-start orientation report
  hotpath              Show the largest files most likely to dominate AI context
  inventory            Generate a runtime-derived inventory of the project
  doctor               Read-only environment + setup diagnostics

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

**`orient` options**

| Flag | Default | Purpose |
|---|---|---|
| `--project DIR` | `cwd` | Project root to orient against |

`orient` is also the command the bundled Claude Code skill calls — see
`skills/context-kit/SKILL.md`. Every generated project gets a copy at
`.claude/skills/context-kit/SKILL.md`, so any agent run inside the
project picks it up automatically.

**`hotpath` options**

| Flag | Default | Purpose |
|---|---|---|
| `--project DIR` | `cwd` | Project root to scan |
| `--single-threshold-kb N` | `50` | Warn on any single file larger than this |
| `--top-count N` | `10` | How many of the largest files to list |
| `--top-threshold-kb N` | `200` | Warn when the top-N sum exceeds this |

`hotpath` is read-only and always exits 0. It prefers `git ls-files`
when run inside a git repo, and falls back to a recursive walk
(skipping `.git`, `node_modules`, `__pycache__`, `.venv`, `dist`,
`build`, `.next`, `coverage`, `.pytest_cache`, `*.egg-info`, etc).
Use it when an AI session feels like it's looping or losing focus —
file size is a surprisingly good proxy for "this won't fit comfortably
in the agent's context."

**`seed` options**

| Flag | Default | Purpose |
|---|---|---|
| *positional* `PATH` | required | Path to the markdown idea file |
| `--project DIR` | `cwd` | Project root (must already be `init`'d) |
| `--force` | off | Overwrite seed-owned content even when normally skipped |
| `--dry-run` | off | Print what would change; don't write files |

`seed` reads a structured markdown idea file (see
`docs/docs-pattern/IDEA_SCHEMA.md` inside any generated project for the
full format) and populates five files in your project: the narrative
anchor's TL;DR, the start-here doc's first milestone, the bootstrap
handoff, a product-framing topic, and a structured `BUILD_PLAN.md`.
Deterministic, no LLM. Re-runnable: managed-block markers
(`<!-- context-kit:seed:start --> / :end -->`) keep human content
outside them safe across re-runs.

The recommended greenfield workflow:

```bash
context-kit init "My App"
cd my-app && $EDITOR idea.md
context-kit seed idea.md
context-kit inventory --write
context-kit orient
claude  # or your AI tool of choice
```

**`inventory` options** (mutually exclusive modes)

| Flag | Default | Purpose |
|---|---|---|
| `--project DIR` | `cwd` | Project root to scan |
| `--write` | off | Update the managed block in `docs/CONTEXT_KIT_INVENTORY.md` |
| `--check` | off | Exit 0 only if the managed block is current; 1 if stale |
| `--json` | off | Print machine-readable JSON to stdout (read-only) |

**`recommend-stack` options**

| Flag | Default | Purpose |
|---|---|---|
| *positional* `PATH` | required | Path to the markdown idea file |
| `--json` | off | Print machine-readable JSON to stdout |

`recommend-stack` reads a structured markdown idea file (same format
as `seed`) and prints an opinionated v0 stack pick: what to use, why,
what NOT to add yet, risks, when to upgrade later. Deterministic, no
LLM, always exits 0. Designed for non-technical builders who know
their problem but not whether they need React, Flutter, Django, etc.

**Seed integration:** when `## Tech stack` is **missing** from the
idea file, `seed` calls into the same engine and bakes the
recommendation into `docs/BUILD_PLAN.md` automatically (with an
attribution note). When `## Tech stack` is **present**, `seed` trusts
your pick and leaves it alone.

**`doctor` options**

| Flag | Default | Purpose |
|---|---|---|
| `--project DIR` | `cwd` | Project root to diagnose |
| `--json` | off | Print machine-readable JSON to stdout |

`doctor` runs a fixed set of read-only checks: Python version, git,
context-kit project structure, Node.js, Expo SDK + config,
file-watcher / `ulimit` pressure, and inventory freshness. Exits `1`
only if a **blocking** issue is found; warnings never affect the exit
code. Specifically tuned for the EMFILE / Expo Go SDK mismatch /
deprecated `expo-cli` friction we hit when dogfooding on Munchkin App.

`inventory` generates runtime-derived counts (CLI subcommands, guide
docs, templates, tests, package metadata, hot-path summary, etc.)
and writes them between two markers:

```
<!-- context-kit:inventory:start -->
<!-- context-kit:inventory:end -->
```

Everything outside the markers is human-written commentary and is
preserved on every `--write`. Use `--check` in CI to fail the build
when the inventory drifts from the code that ships in the same commit.

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

## Installable CLI

`pip install contextkit-ai` is the supported install. The wheel ships
`starter/`, the 8 guide docs, the reference templates, and the
bundled Claude Code skill as package data inside the `cli` package,
so `context-kit init` works end-to-end after a wheel install:

```bash
pip install contextkit-ai
context-kit init "My App"
context-kit start
```

Editable installs (`pip install -e .`) work the same way — both modes
load packaged assets via `importlib.resources`, so there's no separate
"developer" code path.

---

## Status

- **Phase 1** (minimal working bootstrap) — ✅ shipped
- **Phase 2** (rename to context-kit + onboarding server) — ✅ shipped
- **Phase 3** (tests + pyproject + git init + README polish) — ✅ shipped
- **Phase 4** (wheel packaging — `pip install contextkit-ai` works end-to-end) — ✅ shipped in 0.4.1
- **Phase 5** (idea-to-context: `seed` command) — ✅ shipped in 0.4.2
- Phase 6 (release workflow, CI install matrix) — in progress

---

*The pattern is "human and AI working together," not "human using AI to do
something for them." The 8 guide docs explain why. context-kit makes the
first project cheap.*
