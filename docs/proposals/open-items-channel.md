---
title: "Proposal — `OPEN_ITEMS.md`, the out-of-scope channel"
status: proposed
created: 2026-08-26
implemented: false
source: dogfooded in ~/Donkey_Betz/scout (Session 5 onward)
related:
  - docs/proposals/brief-review-loop.md
  - 05_start_here.md
  - 06_dos_and_donts.md
---

# Proposal — `OPEN_ITEMS.md`, the out-of-scope channel

A scoped session plan works by refusing work. `## NOT this session` is what
keeps a session to 5–20 minutes. But an agent that correctly declines to
build something has nowhere to put what it noticed, so the observation dies
in the terminal — the project pays the cost of the discipline without
banking its findings.

`OPEN_ITEMS.md` is the exhaust pipe: one append-only file both the builder
and the reviewer write to, holding things that are **real, observed, and
out of scope right now**.

Scout's convention-only version is live at
`~/Donkey_Betz/scout/docs/OPEN_ITEMS.md`. Three items were logged and all
three were promoted into `SESSION_006_BRIEF.md` within one session — the
cycle works. What Scout cannot do, and context-kit can, is *enforce* it.

---

## The failure mode this must be designed against

Every backlog dies the same way: things go in, nothing comes out, and the
file becomes a place where noticing something feels like doing something
about it. That is strictly worse than no file, because it converts a real
finding into a false sense of capture.

Four causes, each with a mechanical answer:

| Cause | Answer |
|---|---|
| Items are added but never read | A **triage moment** bound to an existing ritual, plus surfacing in `orient` |
| Items accumulate forever | **Aging that forces a decision** — see below |
| Items are too vague to triage cheaply | **Required fields**, enforced at add time |
| Nobody knows if an item is still true | **Staleness check** — does its cited path still exist? |

---

## On expiry: age items to a decision, never to a delete

The obvious rule is "delete after N days." It is the wrong default, and
worth stating plainly because it is tempting.

An item that silently disappears destroys the one thing the file is for:
the record that something was noticed and consciously not done. Six months
later the question is never "what was in the backlog" — it is "did we ever
think about X, and what did we decide?" A deleted item answers that
question with silence, which reads identically to never having noticed.

So aging should **escalate, not erase**:

- item open past N sessions (default 3) → `orient` flags it as
  **needs-decision**, listed by name
- past 2N → the drift sweep treats it the way it treats stale inventory:
  something load-bearing to resolve before claiming the next slice
- resolution is always one of **promote** or **close-with-reason**. Closed
  items stay in the file, with their reason and date.

The file grows. That is fine — it is a decision log, and decision logs are
supposed to grow. `context-kit items --open` is the working view.

**Structural alarm, not a grooming task:** if open items exceed a
threshold (say 12), the signal is that *the plan is wrong* — the sessions
are mis-scoped and work keeps falling outside them. The right response is
revisiting `SESSION_PLAN.md`, not tidying the backlog. `doctor` should say
that in those words rather than suggesting cleanup.

---

## What goes in, and what stays out

The in-rules matter less than the out-rules. Most backlogs rot because
everything is allowed in.

**In:**

- a real, observed thing that the current session's non-goals exclude
- a contract/spec obligation that no planned session owns
  (Scout: §5.5 and §5.6 were hard-failure rules with no check anywhere)
- a decision deliberately deferred, with the reason it was deferred
- a defect found outside the session that surfaced it

**Out:**

- **Ideas and wishlist items.** "It'd be nice if…" is a proposal
  (`docs/proposals/`), not an open item. Open items are observations, and
  an observation has a location.
- **Anything in scope for the current session.** Fix it; do not log it.
  Logging in-scope work to avoid doing it is the failure mode this file
  most invites.
- **Anything `SESSION_PLAN.md` already owns.** That is planned, not open.
- **Vague unease with no observation.** If there is no file, line, or
  contract section to point at, it is not yet an item.
- **Anything fixable in less time than the entry takes to write.** Just fix it.

Enforce the shape at add time — an item without `observed:` and
`why not now:` is rejected by the CLI rather than accepted and left to rot.

---

## The rule that makes it safe

**Logging an item never authorizes the work.**

An entry is not a task, not a permission, and not a plan. `## NOT this
session` is completely unaffected by anything in the file. Only the
operator promotes. A session that builds something because it appeared here
has done precisely what the file exists to prevent.

This belongs in the generated `CLAUDE.md` conventions verbatim, because it
is the rule an agent is most likely to rationalize around — the item is
right there, it is real, and it looks like a to-do list.

---

## Recommendation, not self-promotion

Chris's ask: have the agent recommend when to implement something. Worth
doing, with one boundary — the agent proposes candidates **with reasons**;
the operator promotes. An agent that both files items and promotes them
into its own work queue has routed around the scope discipline entirely.

Concretely, at brief-writing time (or `context-kit items --suggest`):
match open items against the next unstarted session's scope and print
candidates with a one-line rationale each. Output is a suggestion list a
human acts on, never an edit to the plan.

Scout's manual version of this is exactly what happened: writing
`SESSION_006_BRIEF.md` began by reading `OPEN_ITEMS.md`, and OI-001,
OI-002 and OI-005 became brief items 1–3 because Session 6 is the last
session touching generated prose. That reasoning — *this session is the
last cheap moment for this item* — is the kind a tool can surface and
should not decide.

---

## Silent resolution — the cleanup problem

Aging handles items nobody decided about. There is a second, quieter
failure: **an item stops being true and nobody notices.** Session 7
refactors a module and OI-003 becomes moot; the code moved, the item did
not. It now sits in the file looking live, and every future triage pass
pays to re-read something already dead.

This is the cleanup Chris named, and the answer is the same as the answer
to expiry: **detect, do not delete.** The file should be able to tell that
reality moved out from under an item, and say so.

The mechanism, borrowed from the thing Scout itself enforces — a claim
with a source you can re-check:

- an item may carry an optional **`reproduce:`** field — a command, a test
  name, or a path plus a pattern that demonstrates the observation
- `context-kit items --check` runs what it can and reports each item as
  **reproduces**, **no longer reproduces**, or **uncheckable**
- "no longer reproduces" is a **candidate for closure with evidence**,
  surfaced for the operator — never an auto-close. Code changing is
  suggestive, not conclusive; the item may have moved rather than resolved.
- closing it stamps the evidence: *closed — no longer reproduces as of
  `<commit>`*, and the entry stays in place

Keep `reproduce:` **optional**. Requiring it would make logging expensive,
and an item that is expensive to log does not get logged mid-session —
which is the whole reason the channel exists. Encourage it where one
exists; accept prose where it does not.

Cheap version of the same idea, available before any of this ships: the
`observed:` path check already proposed under `verify`. A cited file that
no longer exists is the weakest possible reproducer, and still catches the
most common case.

---

## Proposed surface

- `docs/OPEN_ITEMS.md` scaffolded by `init` and `adopt`, with the format
  and both rules in the header
- `context-kit items add|list|promote|close` — `add` enforces required
  fields; `promote`/`close` stamp date and destination, never delete
- `orient` gains an **OPEN ITEMS** line in `## CURRENT RUNTIME STATE`:
  open count, needs-decision count, over-threshold warning
- `context-kit items --check` runs each item's optional `reproduce:` and
  reports reproduces / no-longer-reproduces / uncheckable; the middle
  case is surfaced as a closure candidate with evidence, never auto-closed
- `verify` treats an item whose `observed:` path no longer exists as
  `UNKNOWN` and asks whether it was silently resolved
- `doctor` reports the over-threshold condition as a plan problem

---

## Open questions

- Does an item need a severity, or does that invite arguing about severity
  instead of deciding? Scout has run without one.
- Should `close` require the operator, or may an agent close an item it can
  demonstrate is no longer reachable (with evidence)?
- Threshold defaults (3 sessions / 12 items) are guesses from one project.
  They need a second before they are defaults rather than placeholders.
