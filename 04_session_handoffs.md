---
title: "Session Handoffs"
status: active
---

# Session Handoffs

Every session on this platform ends with a handoff doc. Over ~1100 sessions, these became the project's **oral history** — the only place you can reconstruct *why* a decision was made.

**They are not optional.** Git history tells you what changed. Handoffs tell you what *almost* changed, what was debated, what Rigby flagged, and what the next session should pick up.

---

## The Pattern

```
docs/handoffs/
    SESSION_001_BOOTSTRAP.md
    SESSION_002_FIRST_AGENT.md
    ...
    SESSION_1098_WRAP_CANARY_GREEN.md
    SESSION_1099_DOC_RECONCILIATION.md
```

Filename format: `SESSION_<N>_<KEBAB_SLUG>.md`. `<N>` is a monotonic counter starting at 1. The slug is 2–6 words describing the session's headline work.

---

## Per-Handoff Structure

```markdown
---
title: "Session <N> — <Headline>"
date: YYYY-MM-DD
status: complete
---

# Session <N> — <Headline>

## TL;DR
<3–5 bullets — what shipped, what didn't, what's queued>

## What Shipped
<PRs + commits + brief descriptions, organized by area>

## What Didn't (and why)
<blocked work, reversals, investigations that hit dead ends — this is often the most valuable section for future sessions>

## Known Issues / Test Artifacts
<anything intentionally left in a weird state — live canaries, disabled features, pending cleanups>

## Rollback Criteria
<only if the session shipped risky changes — what to watch for, how to revert>

## Next Session Picks Up With
<1–3 specific items — file paths, PR numbers, commands to run first>

## Rigby / PA Context
<conversation IDs, state of ongoing PA conversations, any cross-session PA context>
```

**Length target:** 150–400 lines. If shorter, you're skipping detail future-you will need. If longer, split into an addendum.

---

## Write at the End, Not the Start

Do the handoff at the **end of the session that shipped the work**. Not the start of the next session. Reason: the knowledge decays fast. By tomorrow morning you won't remember why you chose approach A over approach B. The handoff is the only place to capture it.

**Exception:** quick hotfix sessions (<30 min) can roll into the next full handoff.

---

## The Headline-Trio Rule

Every handoff's TL;DR has exactly three parts:
1. **What shipped** (bullet: PR # + one-line outcome)
2. **What's blocking next** (bullet: the one thing that matters tomorrow)
3. **What's in a weird state** (bullet: test artifacts, live canaries, half-disabled features)

If you can't fill all three, you're not done with the handoff.

---

## Cross-linking

Every handoff links to:
- The PRs it shipped (GitHub URLs)
- The previous handoff (`../SESSION_<N-1>_*.md`)
- Any topic doc it touched (`../topics/<subsystem>.md`)
- Rigby's PA conversation if the session had one

The handoff corpus becomes a graph. You can walk backward from "why did we change X" to the originating session in 2–3 hops.

---

## The Start-Here Doc Consumes the Latest Handoff

`00-START-NEXT-SESSION.md` at the repo root is rewritten at the end of each session to preview the **next** one. It pulls from the handoff's "Next Session Picks Up With" section. This is the hand-off of the hand-off — see [`05_start_here.md`](05_start_here.md).

---

## What Works About This (that was surprising)

1. **Handoffs make AI sessions resumable across weeks.** Come back after a break, read the last handoff + `00-START-NEXT-SESSION.md`, you're oriented in 10 minutes.
2. **Handoffs reveal patterns the code doesn't.** Grepping handoffs for "revert" or "rollback" surfaces which changes kept breaking. That informs future design.
3. **Handoffs preserve debate.** "We considered X but went with Y because Z" is worth more than any commit message.
4. **AI pair programming needs them most.** The AI has no memory across sessions. The handoff IS its memory.

---

## What Didn't Work (lessons)

- **Skipping handoffs "just this once"** — always resulted in a confused next session. 1098 sessions in, zero exceptions.
- **Handoffs that only list PRs** — too thin. Include the *why* and the *what's weird*.
- **Long handoffs that try to summarize the whole state** — that's what `PLATFORM_WHAT_IT_IS.md` is for. Handoffs are about *this session*, not the platform.
- **Multiple sub-handoffs per session** — hard to find later. Use addendums: `SESSION_1098_ADDENDUM_CANCEL_AND_LINT.md`.

---

## Directory growth

After ~1100 sessions, `docs/handoffs/` has 676 files. That's fine — it's append-only and nobody reads the oldest ones. Don't prune. The occasional "what did we decide in session 300" moment pays back every month of storage.

If the directory feels cluttered, add subdirectories by quarter: `docs/handoffs/2026-Q2/`. But don't do it preemptively.

---

## Template

See [`templates/SESSION_HANDOFF.template.md`](templates/SESSION_HANDOFF.template.md) for a copy-paste starter.

---

*A session without a handoff is a session that happened in a dream.*
