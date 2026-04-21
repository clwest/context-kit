---
title: "Session <N> — <Headline>"
date: YYYY-MM-DD
status: complete
session: <N>
previous_handoff: ../SESSION_<N-1>_*.md
---

# Session <N> — <Headline>

## TL;DR

- **What shipped:** <PR # + one-line outcome>
- **What's blocking next:** <the one thing that matters tomorrow>
- **What's in a weird state:** <test artifacts, live canaries, half-disabled features>

---

## What Shipped

### <Area 1 — e.g. Backend>

- **PR #<N>:** <title>
  - <1–3 bullets — what changed, blast radius, test coverage>
  - <any relevant context — why this approach, what was rejected>

- **PR #<N+1>:** <title>
  - ...

### <Area 2 — e.g. Docs>

- <Files changed, why>

### <Area 3 — e.g. Infrastructure>

- <Config changes, env var flips, deploys>

---

## What Didn't (and Why)

<Blocked work, reversals, investigations that hit dead ends. This is often
the most valuable section for future sessions — it prevents repeating the
same dead-end.>

### <Dead-end / blocker 1>

- **Attempted:** <what you tried>
- **Why it didn't work:** <the specific reason>
- **Next attempt:** <what would be worth trying, if relevant>

### <Dead-end / blocker 2>

...

---

## AI Notes

<Written by the AI at session end, first-person (AI). See
`docs-pattern/08_collaboration_roles.md`. Keep this section even when short —
the absence of AI Notes is itself a signal that the AI was on autopilot.>

- **Uncertain about:** <what in what shipped the AI isn't confident in>
- **Patterns noticed (this session or across recent sessions):** <things the human may not have flagged>
- **Pushed back on:** <what, how it resolved — successful or overridden>
- **Belongs in durable memory:** <anything said this session that future sessions should keep>

<Human reply, optional, inline below any bullet. Do not overwrite the AI note —
reply underneath.>

> <Human response if worth preserving.>

---

## Debates

<Only if the session had real back-and-forth worth preserving. Skip if none.
Four fields per topic; keep each to ~6 lines.>

### <Topic 1 — phrased as the question that was debated>

- **AI proposed:** <position>
- **Human countered:** <position>
- **Settled:** <outcome + reason>
- **If this comes back up:** <trigger, open question, or ticket link>

### <Topic 2>

...

---

## Known Issues / Test Artifacts

<Anything intentionally left in a weird state — live canaries, disabled
features, pending cleanups, artifacts that should NOT be deleted yet.>

- **<Artifact ID>** — <why it exists, when it can be cleaned up>
- **<Feature flag>** — `FLAG=value` set until <condition>

---

## Rollback Criteria

<Only if the session shipped risky changes. What to watch for, how to revert.>

- **Trigger:** <error pattern, metric threshold, etc.>
- **Rollback steps:**
  1. <command or commit SHA to revert>
  2. <follow-up cleanup>

---

## Trust Calibration (this session)

<New entries appended to `docs/TRUST_CALIBRATION.md` — link, don't duplicate.
Three event types: AI confidently wrong, AI right despite pushback, near-miss.
See `docs-pattern/08_collaboration_roles.md`.>

- <YYYY-MM-DD — short title> — see `docs/TRUST_CALIBRATION.md`
- None this session.

---

## Next Session Picks Up With

<1–3 specific items — file paths, PR numbers, commands to run first.>

1. **<Priority 1>** — <what, where, any gotchas>
2. **<Priority 2>** — <what, where>
3. **<Priority 3>** — <what, where>

---

## Rigby / PA / AI Context

- **Conversation ID:** `<conversation-id>` (if applicable)
- **State at end of session:** <what the AI knows, any cross-session threads>
- **How to resume:** `<command to resume conversation>`

---

## Cross-References

- Previous handoff: [`SESSION_<N-1>_*.md`](SESSION_<N-1>_*.md)
- Related topic docs:
  - [`docs/topics/<subsystem>.md`](../topics/<subsystem>.md)
- PRs: #<N>, #<N+1>, #<N+2>
- Relevant commits: `<sha>`, `<sha>`

---

*Written at end of session <date>. Do not edit after the next session begins.
If the next session finds a bug in this handoff's reasoning, add a note at
the bottom rather than rewriting — the original reasoning is history.*
