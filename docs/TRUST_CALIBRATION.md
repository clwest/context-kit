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

