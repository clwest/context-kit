---
title: "{{APP_TITLE}} — Session Start Index"
status: project-owned
generated: {{DATE}}
companion_docs: ["{{APP_UPPER}}_WHAT_IT_IS.md", "{{APP_UPPER}}_INVENTORY.md", "00-START-NEXT-SESSION.md"]
---

# {{APP_TITLE}} — Session Start

> **Project-owned, handwritten.** This file is **not** auto-generated.
> `context-kit init` placed this template once; subsequent `context-kit
> adopt`, `seed`, or `inventory --write` runs **must not** overwrite it.
> Edit it freely. If you delete it, `orient` silently omits this
> section — older projects keep working unchanged.
>
> This is a short, project-specific index a returning agent (or human)
> reads **before** the long anchor docs. Mature repos accumulate 250+
> lines across the two-doc anchor + handoff + start-here doc; this
> file is the 30-second answer to "what's the actual entry point right
> now?"

---

## Read first

Replace this list with the 2–4 docs an agent absolutely must skim
before touching code. Order matters — most load-bearing first.

1. `00-START-NEXT-SESSION.md` — this session's priorities
2. `docs/{{APP_UPPER}}_WHAT_IT_IS.md` — narrative anchor
3. `docs/{{APP_UPPER}}_INVENTORY.md` — runtime anchor (regenerable)
4. Latest `docs/handoffs/SESSION_<N>_*.md` — what last session shipped

Replace any of these with project-specific docs as needed (a deploy
runbook, a vendor-onboarding doc, etc.).

---

## Canonical next-task location

Where in this repo does an agent find the **single** authoritative
"next task" pointer? Pick one and say it explicitly. Common choices:

- The handwritten `## Next session priorities` in `00-START-NEXT-SESSION.md`
- The adopt-managed `## What's next` block inside `00-START-NEXT-SESSION.md`
- A linked task tracker (Linear, Jira, GitHub issue)

Pick **one** and document the choice here. Mature repos that have both
an adopt-managed `What's next` and a handwritten `Next session
priorities` confuse agents — `context-kit doctor` will warn when those
two disagree.

---

## Current baseline

Reproducible numbers an agent can verify before assuming anything:

| What | Current value | How to recompute |
|---|---|---|
| Test suite | _e.g. 494 / 494 passing_ | `pytest` / `python -m unittest discover` |
| Lint / typecheck | _e.g. clean_ | `ruff check . && mypy .` |
| Build | _e.g. green_ | `npm run build` / `cargo build --release` |
| Inventory | _e.g. current_ | `python3 context_kit.py inventory --check` |

Numbers drift. Update this table when you ship the next session and
the number actually changes — don't update it speculatively.

---

## Smoke checks

What the agent should run **before** declaring a fix shipped. Keep
this short and specific to *this* project.

```bash
# Replace with the project's actual smoke commands.
# e.g.:
#   pnpm dev                    # local dev server boots
#   curl localhost:3000/healthz # health endpoint returns 200
#   pytest tests/test_smoke.py  # smoke test passes
```

---

## What to skip / low-signal docs

Files in this repo that look authoritative but aren't load-bearing
for the current work. Naming them here saves the next agent from
reading 600 lines of stale prose.

- _example: `docs/architecture/2024_PROPOSAL.md` — superseded by
  `docs/{{APP_UPPER}}_PIPELINE.md`; kept for archeology only._
- _example: `README.md` versions section — out of date, see
  `CHANGELOG.md` instead._

---

## Task-specific docs

Quick-reference entries for the tasks this project actually does
often. One-line pointer per task; deep content lives in the linked
doc.

- _Onboarding a new contributor:_ `docs/topics/ONBOARDING.md`
- _Adding a new endpoint:_ `docs/{{APP_UPPER}}_PIPELINE.md` §"Entry points"
- _Releasing:_ `docs/handoffs/SESSION_*RELEASE*.md` for the most
  recent release runbook
