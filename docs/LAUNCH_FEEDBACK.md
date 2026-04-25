---
title: "Launch Feedback Log"
status: live
started: 2026-04-25
target_signals: 5
---

# Launch Feedback Log

Append-only running log of feedback received during and after the
launch push. The point isn't reach — it's *real signal*. When 3-5
honest signals are in across the categories below, we reconvene and
decide: double down, reposition, or expand features.

**Until then: no new build work unless multiple people hit the same
friction, or the friction blocks onboarding.**

---

## Where signals come from

In rough order of expected volume:

1. LinkedIn comment thread on the original announce post (already
   has 12 comments; the launch follow-up post will draw more).
2. LinkedIn comments on the long-form follow-up post.
3. X/Twitter thread replies and quote-tweets.
4. GitHub issues — the four templates (`bug_report`,
   `feature_request`, `drift_report`, `dogfood_report`) all route here.
5. DMs and side conversations (often the most candid; log them too,
   summarize without quoting verbatim unless the person OK'd it).

---

## Categories

| Category | GitHub label | Meaning |
|---|---|---|
| **drift** | `drift` | A real disagreement between docs and runtime; the kind of bug `inventory --check` exists to surface |
| **onboarding** | `onboarding` | Friction getting started: install, `init`, `orient`, the skill, first session |
| **confusion** | `confusion` | Mental-model mismatch — they don't get *what* context-kit is or *why* it exists |
| **missing feature** | `missing-feature` | Wanted to do X, couldn't |
| **resonance** | `feedback` | "Yes, I have this exact problem" — log here even if no action needed |
| **rejection** | `feedback` | "Not for me, because…" — log here; the *because* is the signal |

`drift / onboarding / confusion / missing-feature` are also the four
explicit issue tags we set up. `resonance` and `rejection` are
log-only — they don't typically warrant a GitHub issue.

---

## How to log

Append a new entry under **Entries** below for each signal. Use this
shape; under-filled entries are fine — partial signal beats no
signal:

```
## YYYY-MM-DD — short label

**Source:** LinkedIn comment / LinkedIn DM / X reply / GitHub issue #N / DM / call
**Person:** name (handle if public)
**Category:** drift | onboarding | confusion | missing | resonance | rejection
**What they said:** quote (with permission) or paraphrase
**Action taken:** issue #N opened / reply sent / none yet
**My read:** one sentence on what this signal means
```

When you open a GitHub issue from a signal, label it with the
matching category tag. For dogfood reports, use `dogfood` *plus* the
specific category that best describes the signal.

---

## Decision gate (3-5 signals)

When the log reaches 3-5 distinct signals, stop adding new entries
silently and call a recap session. The recap should answer:

1. **Did the "context drift" framing land?** If most of the
   resonance signals quoted the *drift* framing back at us, yes. If
   they quoted something else (e.g., "the orient command itself,"
   "the skill"), the drift framing isn't the lede — reposition
   around what *did* land.
2. **Where do people get stuck?** If 2+ people hit the same
   onboarding friction, fix that next, before any new feature work.
3. **What's the most-asked missing feature?** If anything appears 2+
   times, it goes on the build list. Anything appearing once stays
   filed; one signal doesn't outweigh the cost of building.
4. **Anyone running it on a real project?** Even one honest dogfood
   report is more valuable than ten "looks cool"s. If we have one,
   we have a beachhead.

Output of the recap: an updated `00-START-NEXT-SESSION.md` with the
chosen direction (double down / reposition / expand) and a
prioritized punch list. Keep this discipline tight — easy to
post-rationalize five "looks cool" comments as validation.

---

## Anti-patterns to avoid while watching

- **Reading every reply as a feature request.** Many comments are
  conversation, not asks. Log resonance, don't ship.
- **Building before the recap.** "Just one quick fix" turns into a
  weekend. Hold.
- **Cherry-picking signals.** If the negative ones outnumber the
  positive ones, that's the signal — log it honestly even if it
  stings.
- **Treating volume as validation.** 5 thoughtful "I tried it and
  here's what broke" reports beat 200 likes.

---

## Entries

*(none yet — first entry lands when you reply to Damian / Brian /
Austin and they respond, or when the long-form post draws comments.)*
