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
context-kit codex --mode=execute --short
```

That opens Codex interactively and copies the startup prompt. Paste
that prompt as the first Codex message. For one-shot automation, use:

```bash
context-kit codex --exec --mode=execute --short
```

If you want the lower-level prompt only:

```bash
context-kit start-codex --mode=execute --short
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

- **The tool** — a zero-dependency Python CLI (`init`, `start`, `codex`,
  `start-codex`, `orient`, `hotpath`, `verify`) that scaffolds AI-friendly project context
- **The teaching material** — 8 guide docs (`01_*.md` … `08_*.md`) that
  explain *why* the pattern works

So this repo's adoption of its own pattern is *adapted*, not literal —
the guide docs already live at the repo root rather than under
`docs/docs-pattern/`. See the narrative anchor for details.

---

## Load-bearing conventions

- **Every session starts with a drift sweep.** Run `python3 context_kit.py orient`
  and read the `## CURRENT RUNTIME STATE` block at the bottom. It surfaces
  stale inventory, test-count drift, narrative-anchor date drift, handoff
  numbering gaps, and start-vs-handoff text mismatches before you touch
  code. Fix anything load-bearing before claiming the next slice.
- **Every session ends with a handoff** in `docs/handoffs/SESSION_NNN_*.md`
  and overwrites `00-START-NEXT-SESSION.md` with next session's priorities.
  Pair the handoff with `python3 context_kit.py handoff write <N>` to
  re-stamp every anchor doc's `last_revised:` frontmatter and audit
  whether the handoff's `## Calibration moments` subsections are
  present in `docs/TRUST_CALIBRATION.md`. Removes the per-slice
  doc-staleness surface the SESSION_016 narrative-anchor freshness
  check was a *detector* for.
- **Runtime wins.** The inventory is currently hand-maintained — when it
  drifts from the code, fix the inventory rather than the other way round.
- **Verification config wins for doc claims.** Use `.context-kit/verify.yaml`
  as the source map for canonical docs, and treat historical docs as memory
  unless the task explicitly says to include archive evidence.
- **Close the loop before you leave.** If behavior changes, update the
  relevant docs. If commands, routes, or features change, refresh or verify
  the inventory. If generated artifacts appear, remove them, ignore them, or
  mark them intentionally tracked. Before handoff, run `context-kit verify`
  and `context-kit doctor` where applicable. After major work, write or update
  a handoff note.
- **Correct stale docs before closing the task.** Runtime truth wins over
  stale docs, but stale docs are not acceptable as the final state.
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

# Prepare and launch a Codex session
python3 context_kit.py codex --mode=execute --short

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
