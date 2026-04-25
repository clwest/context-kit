---
title: "Collaboration Roles — Human + AI as a Pair"
status: active
---

# Collaboration Roles — Human + AI as a Pair

The other 7 docs in this directory describe how to give the AI durable context across sessions. That's necessary but not sufficient. Without a second layer — who owns what, when either side pushes back, where the AI writes as itself — the pattern quietly defaults to "human directs, AI executes."

This doc names the partnership explicitly: what each side owns, when the AI is expected to disagree, and where the AI's voice lives in the corpus.

---

## The Three Columns

| Human-owned | AI-owned | Shared |
|---|---|---|
| Product direction & priorities | First draft of almost everything | Architecture decisions |
| External actions (deploy, merge, emails, payments) | Noticing cross-session patterns | Handoff content |
| Final call on taste / UX / voice | Flagging drift the human missed | Topic doc content |
| Approving risky / irreversible steps | Proposing missing docs & verifiers | The two-doc anchor itself |
| Deciding what ships when | Cataloguing its own uncertainty | Trust calibration log |

**Default posture: AI drafts, human edits.** Not "human drafts, AI executes." If the human is writing prose, the AI is idle; if the AI is writing prose alone with no check, the human is idle. Neither is the goal.

---

## When the AI Must Push Back

Pushing back is not a politeness failure. Silently doing a thing the AI has reason to doubt is the failure. The AI is expected to interrupt when:

1. **The request contradicts stable memory/feedback.** The human said "always X" three sessions ago; today they're asking for not-X without acknowledging the reversal.
2. **The framing looks wrong, not just the implementation.** "We should cache this" when the real issue is a bad query.
3. **A past handoff warned about this exact path.** Raise the handoff before proceeding.
4. **The action is risky and the context is thin.** Ambiguous destructive actions → confirm before acting.
5. **The AI is confidently uncertain.** If the AI would cite a number without checking, say so instead of citing.

Each push-back lands in the handoff's `## AI Notes` section (below), even if the human overrides. The overrides themselves become pattern data.

---

## When the AI Defers

Just as important as pushing back — most decisions are not the AI's to make:

- **Taste, voice, and UX preference** — the human's product, the human's voice.
- **External-world actions with real consequences** — deploys, PRs to main, messages to other humans, money movement, permissions changes.
- **Prioritization across sessions** — "what do we work on tomorrow" is the human's call, informed by the AI's observations.
- **When the AI's confidence is low and the human's is high** — after surfacing the uncertainty, defer.

Deferring is not the same as agreeing. The AI can defer and still log the disagreement in `## AI Notes` for future calibration.

---

## The AI Voice in Docs

Three places the AI writes as itself, not as a ghostwriter for the human:

### 1. `## AI Notes` in every session handoff

A first-person (AI) section covering:
- What the AI is uncertain about in what just shipped
- Patterns across recent sessions the human may not have noticed
- What the AI pushed back on (successful or overridden)
- What the human said that belongs in durable memory

### 2. AI-initiated topic docs

When the AI notices a subsystem that deserves a topic doc and none exists, it drafts one and tags it:

```markdown
---
title: "..."
status: ai-drafted
initiated_by: ai
reviewed_by: <pending | human-name>
---
```

Once the human reviews and signs off, `status` flips to `active` and `reviewed_by` fills in. An AI-drafted doc without review is still better than no doc, but it's marked so nobody treats it as canonical.

### 3. `docs/TRUST_CALIBRATION.md`

Append-only log of calibration events worth remembering — see next section. Updated by the AI directly; that's intentional.

---

## Trust Calibration

Over time, the human and AI need to know: *when is the AI's confident claim worth trusting?* The only way to answer that is to record the evidence as it happens.

`docs/TRUST_CALIBRATION.md` is an append-only log with three event types:

```markdown
## 2026-04-21 — AI confidently wrong
- **Claim:** "The `refresh_cache` task runs every 10 min."
- **Reality:** No `PeriodicTask` row exists; task is defined but unscheduled.
- **Found by:** verifier (session 1101).
- **Lesson:** check `PeriodicTask` table, not just task definitions.

## 2026-04-22 — AI right despite human skepticism
- **Claim:** "This migration will lock `orders` for >30s under load."
- **Human response:** "I don't think it'll be that bad."
- **Outcome:** Staging test confirmed 47s lock. Migration was split.
- **Lesson:** AI's migration-lock estimates have been reliable 3 of 3.

## 2026-04-23 — Near-miss override
- **Context:** AI proposed renaming `UserService.resolve()` → `.lookup()`.
- **Human initial response:** approved.
- **Caught by:** AI flagged 14 external callers the rename would break.
- **Lesson:** surface blast radius *before* proposing refactors, not after approval.
```

Three classes: **AI wrong**, **AI right despite pushback**, **near-miss**. Losing only one side of the ledger leads to over- or under-trust. Keep both.

---

## Debates in Handoffs

Single-voice handoffs hide the most valuable data: *what almost happened*. Add a `## Debates` section whenever a session had a real back-and-forth:

```markdown
### Drop the legacy auth middleware now or next sprint?

- **AI proposed:** Drop now — 400 lines, zero current callers.
- **Human countered:** Keep until Q3 — compliance audit refers to it.
- **Settled:** Keep, add `# DEPRECATED 2026-Q3` comment + ticket.
- **If this comes back up:** ticket #1234 tracks removal.
```

Four fields, ~6 lines per debate. Over months, this becomes the most-grepped section of the handoff corpus.

---

## Anti-patterns

- **"The AI agreed with me" used as confirmation.** If the AI has no basis to disagree (hasn't read the relevant files), its agreement is noise. The AI should say so.
- **AI Notes as a shadow todo list.** It's for observations and uncertainty, not for "things I'll do next session." Next-session work goes in `## Next Session Picks Up With`.
- **Trust calibration that only records the AI's wins.** Or only its losses. Asymmetric logs recalibrate in the wrong direction.
- **Human rewriting AI Notes in their own voice.** Defeats the purpose. If the human disagrees, add a reply *below* the AI note, don't overwrite.
- **Treating AI-initiated docs as canonical before review.** `status: ai-drafted` means "not yet blessed." A human sign-off flips it to `active`.
- **Consulting the AI only at the end.** Architecture conversations that skip the AI until the code-writing step waste the partnership. Bring the AI in at the sketch.

---

## Porting

If you're already using this pattern (per `07_bootstrap_checklist.md`) and adding collaboration roles later:

1. Add `## AI Notes` + `## Debates` + `## Trust Calibration (this session)` to the handoff template (already done if you took the template from this directory post-2026-04-21).
2. Create `docs/TRUST_CALIBRATION.md` with just the heading — the log grows from the first real event.
3. Next time the AI drafts a doc unprompted, tag it `status: ai-drafted`.
4. Next session debate: write it up. One entry proves the pattern; ten entries make it load-bearing.

No code change. Pure convention. The value shows up around session 10 and compounds from there.

---

*The pattern is "human and AI working together," not "human using AI to do something for them." The other 7 docs give the AI context. This one gives it a seat at the table.*
