"""context-kit `translation-init` subcommand: print a structured prompt
that instructs an AI agent to populate the project's TRANSLATION_LAYER doc.

Read-only by contract. The CLI does not call an LLM, does not mutate
files, and does not assume any specific agent. It prints a single
predefined prompt — same architecture as ``context-kit audit``.

What the prompt does, when an AI follows it:

1. Reads the project's source-of-truth (WHAT_IT_IS, INVENTORY,
   PIPELINE, BEHAVIOR_LAYER, latest handoff, 00-START-NEXT-SESSION).
2. Interviews the user — who are the audiences, what does each care
   about, what decisions does each own, and one concrete fact from
   the latest handoff / anchors that they'd want translated.
3. Writes the populated TRANSLATION_LAYER doc, preserving every
   required heading from the scaffold but replacing the placeholder
   personas, modes, and example with project-specific content drawn
   from real source-of-truth.
4. Verifies that every claim in the new doc traces back to source —
   no invented progress, business impact, customer value, or
   decisions.
5. Confirms with the user, then offers to switch into a named
   persona's mode for the rest of the session.

The CLI hands the AI the recipe. The AI executes it.
"""

from __future__ import annotations

import argparse


TRANSLATION_INIT_PROMPT = """\
Stop explaining the project.

You are about to populate the project's TRANSLATION_LAYER doc — the
contract that says *same truth → different explanation, zero
distortion*. The scaffold ships with placeholder personas (Builder /
Operator / Executive / Tester) and a generic worked example. Your job
is to replace those placeholders with the project's *real* audiences
and a *real* example drawn from the project's own source-of-truth.

This is a five-step recipe. Do them in order. Do not skip steps.

## Step 1 — Read source-of-truth, in this order

Read every one of these that exists. Do not summarize from priors.

1. `00-START-NEXT-SESSION.md` — current session priorities
2. `docs/<APP>_WHAT_IT_IS.md` — narrative anchor (concept)
3. `docs/<APP>_INVENTORY.md` — runtime anchor (counts / lists)
4. `docs/<APP>_PIPELINE.md` (if present) — runtime flow map
5. `docs/<APP>_BEHAVIOR_LAYER.md` (if present) — voice / display
   contract
6. The most recent `docs/handoffs/SESSION_<N>_*.md`

If `context-kit orient` is available, run it first — it surfaces all
of the above plus any project-owned `SESSION_START` index.

If the project's existing `docs/<APP>_TRANSLATION_LAYER.md` has
already been *hand-edited* away from the scaffold (placeholders
replaced, real personas named, real example drawn from a project
fact), do **not** overwrite it. Instead, propose specific
amendments and stop here for user confirmation. Heuristic for "still
on defaults": the file still mentions "Builder / engineer",
"Operator / business reviewer", "/api/admin/*", "session 12 added a
guard", or "$TOMORROW" — those are scaffold tokens.

## Step 2 — Interview the user

Ask exactly these questions. One at a time. Wait for each answer.

1. **Audiences.** "Who reads this project's docs / handoffs /
   updates? Name each person and their role — e.g. *Chris (builder),
   Jessica (operator/MBA), dealer owner (executive), sales manager
   (frontline).* Skip any role that doesn't have a real reader."
2. **What each cares about.** "For each person you named, what do
   they care about most? What do they ignore?"
3. **Decision authority.** "For each person, what kinds of decisions
   do they own? What kinds do they defer?"
4. **Translation modes.** "For each person, what shape works best —
   technical bullets, business-impact paragraph, executive bullets,
   QA checklist, or 'what should I do next?' framing?"
5. **One concrete fact.** "Pick one specific fact from the latest
   handoff or the inventory that you'd want translated for each
   person. Name the source (handoff filename, anchor section). I'll
   use it as the worked example."
6. **Live chat mode.** "Of the personas you named, which ones are
   non-technical — meaning they have no comfort with code, file
   paths, framework or library names, or developer jargon? For each
   non-technical persona:
   a. What's the trigger phrase that should flip me into their chat
      mode? (Default: *'Hi, I'm <name>'* — confirm or override.)
   b. Give me 3–7 specific words I should never say in a chat with
      them. ('endpoint', 'commit', 'database', etc.)
   c. For each prohibited word, what should I say instead? (e.g.
      *backend → 'the system'*, *commit → 'save'*).
   Skip this question entirely for technical personas (a builder /
   engineer doesn't need a chat-mode block)."

If the user can answer some but not others, that's fine — write the
doc with placeholders only for the *unanswered* parts and surface
those gaps clearly so they can fill them in later.

## Step 3 — Write the populated doc

Write to the discovered path (suffix-first: `docs/<APP>_TRANSLATION_LAYER.md`,
then `docs/TRANSLATION_LAYER.md`, then root). If the doc doesn't
exist, create it at the suffixed path.

Preserve every required heading from the scaffold:

- `## Purpose` (with the core rule and the may/must-not contract)
- `## Source of Truth Inputs`
- `## Personas / Audiences`
- `## Translation Modes`
- `## Truth Preservation Rules`
- `## Live Chat Mode`
- `## Example: Same Truth, Different Explanation`
- `## What Each Person Needs Next`
- `## Last Verified`

Replace these scaffold placeholders with project-specific content:

- The generic persona table → real names + real "cares about" /
  "ignores" pulled from the interview.
- The generic translation modes table → keep all five rows but rewrite
  the "audience" column to use real names where they apply.
- The `## Live Chat Mode` body → for each non-technical persona
  named in Step 2 Q6, write one per-persona block with: trigger
  phrases (default `"Hi, I'm <name>"` plus any overrides), the
  user's prohibited-words list, the user's substitution table
  (rendered as a real Markdown table — `| Avoid | Use instead |`),
  the standard refusal example reworded for that persona's domain
  if useful, and the grounding rule. **Skip technical personas
  silently** — do not write empty blocks for builders / engineers.
  If no persona is non-technical, replace the `### Per-persona
  contracts` body with a single line: `(no non-technical personas
  in this project)`. Preserve the universal rules (Source-of-truth
  still wins / Refusal rule / No invented analogies / Stay in
  character) verbatim — those don't change per persona.
- The `## Example: Same Truth, Different Explanation` body →
  replace the auth-header / `/api/admin/*` example entirely with
  the user-supplied "one concrete fact" from Step 2 Q5. Translate
  it into one block per real persona, citing the source (handoff
  filename or anchor section).
- The `## What Each Person Needs Next` bullets → one real next
  action per real persona, drawn from the latest handoff. If
  source-of-truth doesn't support a useful next action for a
  persona, write `(no actionable item right now)` — do not invent.
- The `## Last Verified` line → today's date, your model name, and
  the SESSION number you read from the latest handoff.

Do **not** remove the truth-preservation rules. Do **not** remove
the core rule (`Same truth → different explanation, zero distortion`).
Do **not** remove the refusal clause (`If a translation cannot be
made without inventing or implying unsupported facts, the assistant
must refuse or fall back to a neutral summary`).

## Step 4 — Verify zero invention

Before you save, re-read every paragraph you wrote. For each claim
that is more than tone / framing — ask: "Where in source-of-truth
does this trace back to?" If the answer is "nowhere, I inferred it",
delete the claim or replace it with `(not yet documented)`.

Specifically watch for:

- Invented progress ("we shipped X" — must trace to a handoff)
- Invented business impact ("saves $X / reduces churn by Y%" —
  must trace to a measured claim or be hedged with "estimated, not
  measured")
- Invented customer value (don't promote a feature as solving a
  problem the source didn't claim it solves)
- Invented decisions ("we decided to X" — must trace to a handoff)

If after this pass any persona has nothing real to say, leave them
in the persona table but write `(no source-of-truth coverage for
this persona yet)` in the example and next-actions sections. That
honesty is the contract.

## Step 5 — Confirm and switch persona

After saving, summarize back to the user:

- Personas named and what they care about
- Source-of-truth facts you used in the example
- Any gaps you flagged with `(not yet documented)` /
  `(no actionable item right now)` placeholders
- The exact relative path you wrote to

Then ask: **"Which persona should I operate as for the rest of this
session?"**

Once they answer:

- If the chosen persona has a `## Live Chat Mode` per-persona block,
  **flip into live chat mode immediately**. At the top of your next
  reply, restate (briefly) the persona's prohibited words and the
  substitutions you'll be using, so the user can see the contract
  is loaded. For every subsequent reply this session, follow the
  chat-mode contract: no prohibited words, every substitution
  applied, refusal rule used the moment a clean answer needs jargon.
- If the chosen persona has no chat-mode block (a technical
  persona), restate just the translation mode (technical summary /
  business impact / executive brief / QA checklist) and follow that
  contract instead — code blocks, paths, and framework names are
  fine to use.

If the user later changes audience, restate the new persona's
contract and switch. The contract is loaded — your job is to honor
it without breaking character until told otherwise.

---

Begin with Step 1. If `context-kit orient` is available, run it now
and read the output before asking any interview questions.
"""


def run_translation_init(args: argparse.Namespace) -> int:
    """Print the populate-translation-layer prompt to stdout.

    Read-only. No file mutation. No LLM calls. Same shape as
    ``context-kit audit``: the CLI hands the AI a recipe; the AI
    runs it.
    """
    del args  # accepted for argparse symmetry; nothing to consume
    print(TRANSLATION_INIT_PROMPT)
    return 0
