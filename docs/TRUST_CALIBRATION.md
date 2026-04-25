---
title: "context-kit — AI ↔ Human Trust Calibration Log"
status: active
---

# Trust Calibration Log

Append-only record of moments where the AI was confidently wrong,
right despite human pushback, or had a near-miss. The goal is not
blame — it's calibration. Over time, the patterns here become the
strongest signal for *when* to trust the AI and *what* to verify by hand.

See `08_collaboration_roles.md` for the full collaboration framing.

---

## Format

Each entry:

```markdown
## YYYY-MM-DD — short label

**Type:** confidently-wrong | right-despite-pushback | near-miss
**Session:** SESSION_NNN_<slug>
**Context:** what was happening
**What the AI claimed:** ...
**What was actually true:** ...
**How it was caught:** test / human review / runtime check / customer
**Lesson / pattern:** ...
```

---

## Entries

## 2026-04-25 — even AI-paced estimates can be too high when design is locked

**Type:** estimation-too-high (in the safer direction)
**Session:** SESSION_005_SEED (`feat(seed): generate project context from idea files`)
**Context:** estimating implementation + tests + smoke time for the
`context-kit seed` feature, after the three-way design discussion
(Claude / human / ChatGPT) had reached agreement on every load-bearing
question.
**What the AI claimed:** "~30-45 min at AI pace" to land the feature.
**What was actually true:** **10m 34s** end-to-end — tests written,
implementation written, two smoke-test bugs caught and fixed, full
verification battery green, wheel built and re-tested.
**How it was caught:** the human noticed the gap and asked for a
calibration entry.
**Lesson / pattern:** AI-paced estimates can still be too conservative
when the design uncertainty has already been resolved. The earlier
calibration (below, "estimating work in human time") corrected the
*human-pace-vs-AI-pace* axis. This one corrects a different axis:
**design-uncertainty time** vs **coding-execution time**. Both got
collapsed into "implementation time" in my estimate, even though the
design discussion had already paid down the uncertainty.

Practical rule going forward:

- When the design is locked (file ownership clear, edge cases
  enumerated, contracts agreed), estimate based on **coding
  execution + test loop time only**. For a moderately-sized feature
  with tests: 5-15 min, not 30-45.
- When the design is genuinely open (architecture ambiguous, edge
  cases unclear, contracts unsettled), surface **uncertainty as
  risk, not as time**. Say "design uncertainty: high" instead of
  inflating the time estimate to absorb it.
- Default to the lower honest number. If I'm wrong on the low side
  ("I said 10 min, took 25"), the human re-plans cheaply. If I'm
  wrong on the high side ("I said 45 min, took 10"), useful work
  gets postponed indefinitely. The asymmetry favors the lower
  estimate.

The compounded version of both calibration entries: **estimate
based on the actual cycle that will happen, not on a generic
"implementation" abstraction.**

---

## 2026-04-25 — estimating work in human time, not Claude Code time

**Type:** judgment-needs-pushback
**Session:** SESSION_004_PYPI_PREP (planning conversation)
**Context:** scoping the PyPI-prep work. The user asked how to make
context-kit pip-installable.
**What the AI claimed:** "~half a day of careful work + tests" to
land the wheel-install feature.
**What was actually true:** at AI execution speed, the actual work
was ~30-45 minutes of focused code + test loops. The "half day"
estimate was unconsciously imagining a human writing the code at
human speed (read the file, think, type, test, debug, repeat).
**How it was caught:** the human pushed back directly: "remember
that when you start thinking in coding times you need to think in
how long it will take you to do something not me. You are writing
the code, I am just guiding."
**Lesson / pattern:** when Claude Code is doing the implementation,
estimate based on Claude execution + test-loop time, not on a
human's read/think/type/debug cycle. Practical rule for future
estimates:

  - If the user is reviewing and guiding (not typing): use AI
    execution time. Roughly: read + plan + write + test = 5-10
    minutes per moderate change; 30-60 minutes for a
    multi-file feature with tests; hours only for genuinely
    open-ended exploration.
  - If the user is coding alongside or doing the typing: revert to
    human-paced estimates.
  - When uncertain, say which mode the estimate assumes ("at AI
    pace, ~30 min; if you're typing, half a day"), don't quietly
    pick the longer one to seem cautious.

This calibration matters because over-estimating in AI mode
generates false friction: the human postpones useful work because
"that's a half-day project" when the real cost is 30 minutes. The
larger the gap between estimated and actual, the more good work
gets deferred indefinitely.

---

## 2026-04-25 — "deliberate worked example" was the wrong call

**Type:** judgment-needs-pushback
**Session:** SESSION_001_INITIAL
**Context:** drafting the first hand-written `CONTEXT_KIT_INVENTORY.md`
during the dogfood commit.
**What the AI claimed:** that shipping the test-file count as "4" when
the real count was "5" was a useful worked example of why hand-counts
drift, worth keeping in the published commit.
**What was actually true:** publishing an intentional mismatch in the
first dogfood commit would undercut the entire "runtime wins" message
the inventory exists to enforce. The lesson is real; the
demonstration vehicle was wrong.
**How it was caught:** human review before push.
**Lesson / pattern:** "this teaches a good lesson" is not sufficient
justification for shipping something wrong on a published page,
especially in the artifact whose whole purpose is to be the
authoritative source. Future analogue: if the AI proposes leaving a
known-incorrect value in place because it illustrates a principle,
push back — find a different way to illustrate the principle.

