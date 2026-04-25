# CLAUDE / AGENTS — AI Session Entry Point

> **Source of truth for numbers:** `docs/{{APP_UPPER}}_WHAT_IT_IS.md` (narrative)
> + `docs/{{APP_UPPER}}_INVENTORY.md` (runtime-derived, regenerable).
> When this doc disagrees with either, INVENTORY wins.

---

## Quick Start

1. Read `00-START-NEXT-SESSION.md` first — it describes the current priority.
2. Project-wide conventions live in `docs/docs-pattern/` (the meta-framework).
3. Subsystem deep-dives live in `docs/topics/`.
4. Build history lives in `docs/handoffs/`.

---

## The Pattern

{{APP_TITLE}} was scaffolded with **context-kit** and follows the docs-pattern
conventions it ships. Load-bearing rules:

- **Every session ends with a handoff** in `docs/handoffs/SESSION_NNN_*.md`.
- **`00-START-NEXT-SESSION.md`** at the repo root is overwritten at session end
  to preview the next session.
- **The two-doc anchor** (`docs/{{APP_UPPER}}_WHAT_IT_IS.md` +
  `docs/{{APP_UPPER}}_INVENTORY.md`) is the source of truth for counts and claims.
- **Runtime wins.** When asked about current platform state, prefer the
  INVENTORY doc or the verifier over anything narrative.

---

## Collaboration Conventions

See `docs/docs-pattern/08_collaboration_roles.md`. Summary:

- **AI drafts, human edits** — not the reverse.
- **AI is expected to push back** when a request contradicts memory, the
  framing looks wrong, or the action is risky with thin context.
- **AI Notes** section in every handoff is where the AI writes as itself.
- **`docs/TRUST_CALIBRATION.md`** is the append-only log of calibration events.

---

## Key Commands (once wired up)

```bash
# Regenerate the runtime inventory
python manage.py generate_platform_inventory          # or your stack's equivalent

# Check which docs disagree with reality
python manage.py verify_doc_claims --only-drift

# Rebuild the docs search/embedding index
python manage.py build_docs_index
```

---

## Where to find things

| What | Where |
|---|---|
| This session's priorities | `00-START-NEXT-SESSION.md` |
| Conceptual narrative | `docs/{{APP_UPPER}}_WHAT_IT_IS.md` |
| Runtime truth | `docs/{{APP_UPPER}}_INVENTORY.md` |
| Subsystem docs | `docs/topics/` |
| Session history | `docs/handoffs/` |
| The meta-framework | `docs/docs-pattern/` |
| AI calibration log | `docs/TRUST_CALIBRATION.md` |
