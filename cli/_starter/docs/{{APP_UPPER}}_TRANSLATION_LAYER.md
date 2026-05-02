---
title: "{{APP_TITLE}} — Translation Layer"
status: project-owned
generated: {{DATE}}
companion_docs: ["{{APP_UPPER}}_WHAT_IT_IS.md", "{{APP_UPPER}}_INVENTORY.md", "{{APP_UPPER}}_PIPELINE.md", "{{APP_UPPER}}_BEHAVIOR_LAYER.md"]
---

# {{APP_TITLE}} — Translation Layer

> **Project-owned, handwritten.** This file is **not** auto-generated.
> `context-kit init` placed this template once; subsequent `context-kit
> adopt`, `seed`, or `inventory --write` runs **must not** overwrite it.
> Edit it freely. If you delete it, `orient` silently omits this
> section — older projects keep working unchanged.

---

## Purpose

> **Core rule:** *Same truth → different explanation layer → zero distortion.*

This doc tells future agents **how to explain the same source-of-truth
to different humans without changing facts**. It is *not* a marketing
doc, *not* a prompt template, *not* a personalization layer. It is a
contract that says:

- The assistant **may** reframe, simplify, reorder, change examples,
  and adjust vocabulary for the audience.
- The assistant **must not** invent progress, test results, business
  impact, features, customer value, or decisions not supported by
  source material.
- If a translation cannot be made without inventing or implying
  unsupported facts, the assistant must refuse or fall back to a
  neutral summary.

If a fact isn't in `{{APP_UPPER}}_WHAT_IT_IS.md`,
`{{APP_UPPER}}_INVENTORY.md`, `{{APP_UPPER}}_PIPELINE.md`,
`{{APP_UPPER}}_BEHAVIOR_LAYER.md`, the latest handoff, or this file —
**the assistant must not assert it**, regardless of which audience is
reading.

---

## Source of Truth Inputs

The translation layer reads from the project's existing anchors. It
does not introduce new facts. Order matches `orient`'s read order:

1. `docs/{{APP_UPPER}}_WHAT_IT_IS.md` — narrative anchor (what the
   system *is*)
2. `docs/{{APP_UPPER}}_INVENTORY.md` — runtime anchor (what currently
   *exists*)
3. `docs/{{APP_UPPER}}_PIPELINE.md` — runtime flow map (how requests
   *move*)
4. `docs/{{APP_UPPER}}_BEHAVIOR_LAYER.md` — voice / display contract
5. Latest `docs/handoffs/SESSION_<N>_*.md` — what last session shipped
6. `00-START-NEXT-SESSION.md` — next session's priority

If any of those say "X is shipped" or "Y is broken", the translation
layer can rephrase X or Y for any audience. If none of them say it,
the translation layer **invents nothing** to fill the gap.

---

## Personas / Audiences

Pick the personas that actually exist for this project. Below are
generic starting points — replace them with concrete real names /
roles when known.

| Persona | Cares about | Ignores |
|---|---|---|
| Builder / engineer | What was changed, why, what risks remain, what's safe to merge | Business framing, customer outcomes |
| Operator / business reviewer | What works for users today, what's broken in production, what's the impact | Implementation details, library choices |
| Executive / owner | Where we are vs the plan, what's the next milestone, what could derail it | Code internals, infra, day-to-day |
| Frontline user / tester | What to click, what to verify, what counts as broken | Architecture, why-this-was-built |

Keep this short and project-specific. A solo project might have
exactly one persona ("me, future-me, and the AI"); a multi-stakeholder
project might add 2–3 more. **Don't add a persona unless someone
actually reads the explanation in that mode.**

---

## Translation Modes

These are the *forms* the same source-of-truth can take. Each mode
serves one or more personas — but the underlying facts are identical.

| Mode | Audience | Output shape |
|---|---|---|
| Technical summary | Builder | bullet list of changes, file paths, follow-ups, known risks |
| Business impact summary | Operator | one paragraph: what users / customers experience, what's measurable |
| Executive brief | Owner | 3–5 bullets max: where we are, the next decision, the next risk |
| QA / testing checklist | Tester | numbered click-through with expected results and "what counts as broken" |
| "What should this person do next?" | Any persona | one sentence per persona: their single most useful next move |

Add or remove modes to match the project. The brief format
(executive) is intentionally compact: more than ~5 bullets means the
brief is too long for the persona it serves.

---

## Truth Preservation Rules

These are the load-bearing rules. Read them as a contract on every
translation:

1. **No invention.** If a fact isn't in source-of-truth inputs, do
   not assert it. Use placeholders ("not yet measured", "no data
   yet") rather than confident claims.
2. **No false precision.** Round numbers down to what the source
   actually supports. "47 tests pass" requires `tests/` to actually
   show 47 passes — not approximate guesses.
3. **No invented progress.** "We shipped X" must trace back to a
   handoff, a CHANGELOG entry, or a doc that names X as shipped.
4. **No invented business impact.** "This saves $X" or "This
   reduces churn by Y%" requires either an explicit claim in
   source-of-truth or an explicit "estimated, not measured" hedge.
5. **No invented customer value.** Don't promote a feature as
   solving a problem the source-of-truth didn't claim it solves.
6. **No invented decisions.** "We decided to X" must trace to a
   handoff or doc; "We are considering X" is allowed when the
   source supports it.
7. **Reorder freely.** Whatever order makes sense for the audience
   is fine, as long as the *facts* don't change.
8. **Change vocabulary freely.** Translate jargon to plain language
   for non-technical audiences and back again. Word choice is
   discretion; underlying claim is not.
9. **Change examples freely.** Pick examples that resonate with the
   audience as long as they're real (drawn from the codebase, the
   handoffs, or the current data).
10. **Hedge when source is thin.** Use "appears to", "based on the
    last handoff", "as of <date>" to make the source's age visible
    rather than implicit.

If you catch yourself adding a fact to make the explanation land
better — **stop**. The fact belongs in source-of-truth first, or
nowhere.

---

## Example: Same Truth, Different Explanation

The example below demonstrates a single fact rewritten for four
audiences without inventing claims.

**Source-of-truth fact** (suppose this is the only thing the
handoff actually said):

> Session 12 added a guard that rejects requests with no auth header
> on `/api/admin/*`. 14 existing routes were updated. Test suite is
> green. Production deploy is queued for tomorrow.

**Builder translation** (technical summary):

> Session 12: added auth-header guard at `/api/admin/*`. Touched 14
> route handlers. Tests green. Deploy queued for $TOMORROW. Risk:
> any consumer that didn't already send the header will start 401-ing
> after deploy — confirm the rollout list before merge.

**Operator translation** (business impact):

> Admin endpoints will reject anonymous traffic starting tomorrow's
> deploy. No external customer impact unless an internal tool was
> calling admin URLs without auth. Worth checking with whoever owns
> the internal admin tooling.

**Executive translation** (executive brief):

> Admin API hardening lands tomorrow.
> Risk: internal tools that quietly used unauth'd admin URLs may
> break.
> Decision needed: confirm rollout list or postpone.

**Tester translation** (QA checklist):

> 1. Hit any `/api/admin/*` endpoint without an auth header → expect
>    401.
> 2. Hit the same endpoint with a valid auth header → expect 200 (or
>    its previous response).
> 3. If a known internal tool stops working after deploy, that is a
>    rollout-list miss, not a regression — escalate.

**Notice what didn't change:** the underlying facts (session 12,
14 routes, deploy timing, test status) are identical in every mode.
Only the framing, vocabulary, and detail level change.

---

## What Each Person Needs Next

For each persona named above, write the single most useful next
action *given the current source-of-truth*. Update it when source
state changes — don't speculate.

- **Builder:** _e.g. confirm the rollout list with internal-tools
  owners before merging the auth-guard PR._
- **Operator:** _e.g. ping internal-tools team to verify they're not
  calling admin URLs anonymously._
- **Executive / owner:** _e.g. decide whether to postpone the deploy
  or accept the risk._
- **Tester:** _e.g. run the 3-step QA checklist above against the
  staging deploy._

If the source-of-truth doesn't currently support a useful next
action for a persona, write `(no actionable item right now)` — do
not invent one.

---

## Last Verified

When was this doc last reconciled with the actual source-of-truth?
Update this line when you've re-read the anchors and confirmed the
translations / examples / next-actions still hold.

- **Last verified:** _<DATE> — by <NAME> against handoff
  SESSION_<N>_<SLUG>.md._

If this line is more than a few sessions old, treat the translations
above as suggestive, not authoritative. Re-read the latest handoff
and update this doc before relying on it.
