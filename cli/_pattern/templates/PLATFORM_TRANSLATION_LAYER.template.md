---
title: "<App> — Translation Layer"
status: project-owned
companion_docs: ["<APP>_WHAT_IT_IS.md", "<APP>_INVENTORY.md", "<APP>_PIPELINE.md", "<APP>_BEHAVIOR_LAYER.md"]
---

# <App> — Translation Layer

> **Project-owned, handwritten.** Generators must not overwrite this.
> When `orient` finds it, the orient report includes a
> `## TRANSLATION LAYER` section above DO_NOTS — so a returning
> agent reads the audience contract before writing prose for any
> stakeholder. Delete the file and `orient` silently omits the
> section.

---

## Purpose

> **Core rule:** *Same truth → different explanation layer → zero distortion.*

The assistant **may** reframe, simplify, reorder, change examples,
and adjust vocabulary for the audience.
The assistant **must not** invent progress, test results, business
impact, features, customer value, or decisions not supported by
source material.
If a translation cannot be made without inventing or implying
unsupported facts, the assistant must refuse or fall back to a
neutral summary.

If a fact isn't in `<APP>_WHAT_IT_IS.md`, `<APP>_INVENTORY.md`,
`<APP>_PIPELINE.md`, `<APP>_BEHAVIOR_LAYER.md`, the latest
handoff, or this file — the assistant must not assert it,
regardless of audience.

---

## Source of Truth Inputs

The translation layer reads from existing anchors. It introduces
no new facts.

1. `<APP>_WHAT_IT_IS.md` — narrative anchor
2. `<APP>_INVENTORY.md` — runtime anchor
3. `<APP>_PIPELINE.md` — runtime flow map (if present)
4. `<APP>_BEHAVIOR_LAYER.md` — voice / display contract (if present)
5. Latest `docs/handoffs/SESSION_<N>_*.md`
6. `00-START-NEXT-SESSION.md`

---

## Personas / Audiences

Replace with concrete real names / roles. Generic starting points:

| Persona | Cares about | Ignores |
|---|---|---|
| Builder / engineer | Changes, risk, what's safe to merge | Business framing |
| Operator / business reviewer | What works for users, what's broken, impact | Implementation detail |
| Executive / owner | Plan vs reality, next milestone, derailers | Code internals |
| Frontline user / tester | What to click, what to verify, what counts as broken | Architecture |

**Don't add a persona unless someone actually reads in that mode.**

---

## Translation Modes

| Mode | Audience | Output shape |
|---|---|---|
| Technical summary | Builder | bullets: changes, files, follow-ups, risks |
| Business impact summary | Operator | one paragraph: user / customer experience |
| Executive brief | Owner | 3–5 bullets max |
| QA / testing checklist | Tester | numbered click-through with expected results |
| "What should this person do next?" | Any | one sentence per persona |

---

## Truth Preservation Rules

1. **No invention.** Fact not in source-of-truth → do not assert.
2. **No false precision.** Don't round up to look good.
3. **No invented progress.** Trace every "shipped X" to a handoff.
4. **No invented business impact.** Hedge with "estimated, not
   measured" when no source data exists.
5. **No invented customer value.** Don't promote a feature as
   solving a problem source-of-truth didn't claim.
6. **No invented decisions.** Trace every "we decided" claim.
7. **Reorder freely.**
8. **Change vocabulary freely.**
9. **Change examples freely** — but only with examples drawn from
   the actual codebase / handoffs / current data.
10. **Hedge when source is thin** ("appears to", "as of <date>").

---

## Live Chat Mode

> **Stricter contract than doc translation.** Sections above govern
> *written* translations (handoffs, briefs, checklists). This section
> governs *live chat* with a non-technical persona where re-reads
> and revisions don't exist.

**Trigger**: activates when the user identifies as a named persona
below (*"Hi, I'm <name>"*) or asks to *"operate as <persona>"*.
Stays on for the session. Restate the active persona at the top of
every reply.

**Universal rules**:

1. Source-of-truth still wins. Chat mode changes vocabulary, never
   facts.
2. **Refusal rule.** If a truthful answer needs prohibited words,
   say: *"I can't answer that cleanly without using technical words
   — want a higher-level version, or the technical version just
   this once?"* Don't invent analogies.
3. Stay in character until told otherwise.

**Per-persona contracts** — one block per non-technical persona.
Skip technical personas. If none need this, write
`(no non-technical personas in this project)`.

#### Example persona — Operator (replace with real name + role)

- **Trigger phrases**: *"Hi, I'm <name>"*, *"This is <name>"*.
- **Prohibitions**: code blocks, file paths, framework / library
  names, acronyms unless persona used them first, jargon
  (`endpoint`, `API`, `database`, `commit`, `deploy`, `migration`,
  `variable`, `function`, etc.).
- **Substitutions**:

| Avoid | Use instead |
|---|---|
| backend | the system |
| frontend | the page they see |
| API call | the saved settings / the action |
| test | scenario / thing to try |
| commit / push | save / publish |
| migration | upgrade |
| deploy | release |

- **Grounding**: every claim still traces to source-of-truth.
  Hedge with *"I don't see that recorded yet"* rather than
  inventing.

---

## Example: Same Truth, Different Explanation

Pick one fact from the latest handoff. Restate it for each persona.
Verify nothing changed except framing / vocabulary / detail level.

> _Example template:_
>
> **Source-of-truth fact:** _<one sentence from a handoff>_
>
> - **Builder:** _<technical summary, 1–3 bullets>_
> - **Operator:** _<business impact, one paragraph>_
> - **Executive:** _<3–5 bullets, decision-shaped>_
> - **Tester:** _<numbered QA steps>_

---

## What Each Person Needs Next

One sentence per persona — the single most useful next action given
current source-of-truth. Write `(no actionable item right now)`
when source doesn't support one. **Do not invent.**

---

## Last Verified

- **Last verified:** _<DATE> — by <NAME> against handoff
  SESSION_<N>_<SLUG>.md._

If stale by more than a few sessions, treat translations above as
suggestive, not authoritative.
