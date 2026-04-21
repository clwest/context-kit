---
title: "The Start-Here Doc"
status: active
---

# The Start-Here Doc

`00-START-NEXT-SESSION.md` at the **repo root** (not inside `/docs/`) is the first thing every AI session reads. It's the cold-start handshake between yesterday's work and tomorrow's.

The leading `00-` keeps it sorted at the top of any directory listing. The name is explicit because it's the *only* filename every collaborator (human + AI) needs to remember.

---

## Why at the Repo Root

Not in `/docs/` because:
1. AI tools (Claude Code, Cursor) default to scanning root
2. Humans see it immediately on `git clone`
3. It's a dynamic, session-specific doc — not a reference

The two-doc anchor (`PLATFORM_WHAT_IT_IS.md` + `PLATFORM_INVENTORY.md`) lives in `/docs/` because they're **reference** docs. `00-START-NEXT-SESSION.md` is a **working** doc.

---

## What Goes In It

```markdown
# Next Session — Start Here

## SOURCE OF TRUTH (read first)
- docs/PLATFORM_WHAT_IT_IS.md — what the platform is
- docs/PLATFORM_INVENTORY.md — what exists right now (regenerable)
- python manage.py verify_doc_claims --only-drift — live drift report

## READ THIS FIRST — <critical trap>
<environment trap, auth trap, platform quirk — anything that has burned a
session. On this repo: the LOCAL vs PROD Rigby trap.>

## SESSION <N> — START HERE
<what the previous session wrapped with, what to pick up>

### FIRST THING — <headline priority>
<single bullet — the thing you do before anything else>

### Step 1 — <immediate task>
<commands to run, files to check>

### Step 2 — <next task>

### Step 3 — <next task if applicable>

### Rollback Criteria
<if this session shipped risky changes>

## What Session <N-1> Shipped
<context only — not a handoff. Point at the handoff file for detail>

## Queued Investigations
<1–3 items that can wait but shouldn't be forgotten>

## Rigby / PA Context
<conversation IDs, how to invoke the AI assistant, any cross-session state>
```

---

## The Four Required Sections

Cut anything else, keep these:
1. **Source of Truth** — pointer to the two-doc anchor + verifier
2. **Critical Trap** — the one environment/setup thing that will break your day
3. **First Thing + Next Steps** — ordered, executable
4. **Rigby / PA Context** — how to resume the AI conversation

Everything else is optional. If the doc gets longer than ~300 lines, split detail into the previous session's handoff.

---

## Rewrite at Session End

The doc is **overwritten** at the end of each session. It's not append-only. It describes *only* the next session.

Workflow:
1. End of session N → write `docs/handoffs/SESSION_<N>_*.md` (append-only history)
2. Same commit → overwrite `00-START-NEXT-SESSION.md` with next session's instructions
3. Include: pointer to handoff just written, next session's priorities, any new traps discovered

Your commit message should say `docs: Session <N> wrap + Session <N+1> start-here` (pattern used throughout this repo's history).

---

## The Source-of-Truth Block (required, always at top)

After Session 1099, every `00-START-NEXT-SESSION.md` starts with this block (or equivalent):

```markdown
## SOURCE OF TRUTH

When stats in any doc disagree:
1. **`docs/PLATFORM_WHAT_IT_IS.md`** — narrative, conceptual ground truth
2. **`docs/PLATFORM_INVENTORY.md`** — runtime-derived, regenerable via
   `python manage.py generate_platform_inventory`

Live drift report: `python manage.py verify_doc_claims --only-drift`

If you're unsure which doc to trust, read these two first.
```

Without this block, new sessions start by trusting whatever doc they happened to open. With it, they anchor on the canonical pair immediately.

---

## Anti-patterns

- **`00-START-NEXT-SESSION.md` as a dumping ground.** It's not a scratchpad. Keep it short, executable, and about the *next* session.
- **Leaving it stale.** If you open a session and the doc refers to work from three sessions ago, someone skipped the handoff. Fix it before proceeding.
- **Two "start here" docs.** One canonical file at the root. No `START_HERE.md` + `README_FIRST.md` + `00_NEXT_SESSION.md`. Pick one name, stick with it.

---

## On a New App

Bootstrap file sequence (see [`07_bootstrap_checklist.md`](07_bootstrap_checklist.md)):
1. `00-START-NEXT-SESSION.md` at root — even if empty, creates the habit
2. `CLAUDE.md` or `AGENTS.md` at root — AI entry instructions
3. `docs/PLATFORM_WHAT_IT_IS.md` + `docs/PLATFORM_INVENTORY.md`
4. `docs/topics/` + first 2–3 subsystem docs

By file #4, the pattern is load-bearing. After ~20 sessions, it's the habit.

---

*The Start-Here doc is what lets a new session (or a returning one after a break) start producing work in 10 minutes instead of 2 hours.*
