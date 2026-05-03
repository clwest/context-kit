# CLAUDE / AGENTS — AI Session Entry Point (context-kit repo)

> **Source of truth (read in this order):**
> 1. `00-START-NEXT-SESSION.md` — this session's priorities
> 2. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 3. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (currently manual; see file)
> 4. Latest `docs/handoffs/SESSION_NNN_*.md` — what last session shipped
>
> When this doc disagrees with any of the above, the above wins.

---

## How to start

If you have the `context-kit` CLI on PATH, just run:

```bash
context-kit orient
```

Or from this repo:

```bash
python3 context_kit.py orient
```

The Claude Code skill at `.claude/skills/context-kit/SKILL.md` will tell
any agent loaded in this repo to do exactly that.

---

## What this repo is

context-kit is both:

- **The tool** — a zero-dependency Python CLI (`init`, `start`, `orient`,
  `hotpath`, `verify`) that scaffolds AI-friendly project context
- **The teaching material** — 8 guide docs (`01_*.md` … `08_*.md`) that
  explain *why* the pattern works

So this repo's adoption of its own pattern is *adapted*, not literal —
the guide docs already live at the repo root rather than under
`docs/docs-pattern/`. See the narrative anchor for details.

---

## Load-bearing conventions

- **Every session ends with a handoff** in `docs/handoffs/SESSION_NNN_*.md`
  and overwrites `00-START-NEXT-SESSION.md` with next session's priorities.
- **Runtime wins.** The inventory is currently hand-maintained — when it
  drifts from the code, fix the inventory rather than the other way round.
- **AI Notes** section in every handoff is where the AI writes as itself
  (per `08_collaboration_roles.md`).
- **`docs/TRUST_CALIBRATION.md`** is the append-only log of calibration
  events (AI confidently wrong, right despite pushback, near-misses).

---

## Key commands

```bash
# Run the test suite
python3 -m unittest discover -s tests -t .

# Read the assembled session-start orientation
python3 context_kit.py orient

# Check which files are large enough to dominate context
python3 context_kit.py hotpath

# Verify important repo claims against docs + code/config
python3 context_kit.py verify

# Smoke-test the bootstrap into a temp dir
python3 context_kit.py init "Smoke" --target /tmp/ctx-smoke --force
```

---

## Where to find things

| What | Where |
|---|---|
| This session's priorities | `00-START-NEXT-SESSION.md` |
| Narrative anchor | `docs/CONTEXT_KIT_WHAT_IT_IS.md` |
| Runtime anchor (manual stub) | `docs/CONTEXT_KIT_INVENTORY.md` |
| Session history | `docs/handoffs/` |
| AI calibration log | `docs/TRUST_CALIBRATION.md` |
| Guide docs (the teaching material) | `01_*.md` … `08_*.md` at repo root |
| Reference templates | `templates/` |
| CLI source | `context_kit.py` + `cli/` |
| Bundled Claude skill | `skills/context-kit/SKILL.md` (mirrored at `.claude/skills/context-kit/SKILL.md`) |
