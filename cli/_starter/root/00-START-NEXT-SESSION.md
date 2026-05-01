---
state: scaffold
---

# Next Session — Start Here

> **Source of truth for numbers:** `docs/{{APP_UPPER}}_WHAT_IT_IS.md` (narrative)
> + `docs/{{APP_UPPER}}_INVENTORY.md` (runtime-derived, regenerable).
> **Source of truth for runtime flow:** `docs/{{APP_UPPER}}_PIPELINE.md`
> (entry points, guard coverage, retrieval paths, post-processing order).
> When any doc disagrees with INVENTORY (counts) or PIPELINE (flow), those win.
> Live drift report: `python manage.py verify_doc_claims --only-drift` (once wired up).
>
> **Frontmatter `state:`** above is consumed by `context-kit seed`.
> `scaffold` = freshly init'd, safe for seed to populate.
> `seeded` = seed ran. `active` = a real session-end handoff has been written.
> Don't edit by hand unless you know what you're doing.

---

## READ THIS FIRST — Bootstrap trap

This project was scaffolded with **context-kit** on {{DATE}}.
Nothing runs yet. Before shipping real work:

1. (Optional) `python3 context_kit.py start` opens a local onboarding page
   that walks through the first-session checklist in a browser.
2. Read `docs/docs-pattern/README.md` then `docs/docs-pattern/07_bootstrap_checklist.md`.
3. Flesh out `docs/{{APP_UPPER}}_WHAT_IT_IS.md` with the actual concept for {{APP_TITLE}}.
4. Pick your stack (language + framework) and wire the inventory generator + verifier.
5. End Session 1 by writing `docs/handoffs/SESSION_002_*.md` and overwriting this file.

---

## SESSION 1 — START HERE

### FIRST THING — Finish adopting the pattern

Walk through `docs/docs-pattern/07_bootstrap_checklist.md`. The bootstrap tool
placed files #1, #3, #4, #5, #6, #7 for you. You still need to decide on:
- #2 — which variant of `CLAUDE.md` / `AGENTS.md` to keep (both were created)
- #8 — verifier (skeleton in `scaffold/python/` if you bootstrapped with `--with-scaffold`)
- #9 — inventory generator (stack-specific; see 02_drift_verifier.md)
- #10 — index builder (skeleton in `scaffold/python/build_docs_index.py`)

### Step 1 — Fill in `docs/{{APP_UPPER}}_WHAT_IT_IS.md`

Even a rough first pass. TL;DR + one layered-architecture sketch is enough
for Session 1. Use `docs/docs-pattern/templates/PLATFORM_WHAT_IT_IS.template.md`
as the full reference structure.

### Step 2 — Commit the skeleton

One commit: `chore: scaffold {{APP_TITLE}} with context-kit`.

### Step 3 — Write your first real handoff

End of Session 1: write `docs/handoffs/SESSION_002_<SLUG>.md` describing what
shipped today, then overwrite **this file** with the next session's priorities.
The template is at `docs/docs-pattern/templates/SESSION_HANDOFF.template.md`.

---

## Queued Investigations

- None yet — this is session 1.

---

## AI / Assistant Context

- No prior sessions.
- Collaboration conventions: `docs/docs-pattern/08_collaboration_roles.md`.
- Handoff `## AI Notes` section is required from Session 2 onward.
- `docs/TRUST_CALIBRATION.md` starts empty; first real calibration event
  (AI confidently wrong / right despite pushback / near-miss) gets logged there.
