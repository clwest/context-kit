---
title: "Example Bootstrap Output"
status: reference
---

# Example Bootstrap Output

Running:

```bash
python3 context_kit.py init "Acme Insights" --target ./acme-insights --with-scaffold
```

Produces:

```
acme-insights/
├── context_kit.py                         # runtime entry point for `start`
├── cli/
│   ├── __init__.py
│   └── server.py                           # onboarding server (stdlib only)
├── 00-START-NEXT-SESSION.md
├── CLAUDE.md
├── docs/
│   ├── ACME_INSIGHTS_WHAT_IT_IS.md         # narrative anchor (stub)
│   ├── ACME_INSIGHTS_INVENTORY.md          # runtime anchor (stub)
│   ├── TRUST_CALIBRATION.md                # empty calibration log
│   ├── docs-pattern/                       # the teaching material (copied)
│   │   ├── README.md
│   │   ├── 01_two_doc_anchor.md
│   │   ├── 02_drift_verifier.md
│   │   ├── 03_topic_docs.md
│   │   ├── 04_session_handoffs.md
│   │   ├── 05_start_here.md
│   │   ├── 06_dos_and_donts.md
│   │   ├── 07_bootstrap_checklist.md
│   │   ├── 08_collaboration_roles.md
│   │   └── templates/
│   │       ├── PLATFORM_WHAT_IT_IS.template.md
│   │       ├── PLATFORM_INVENTORY.template.md
│   │       ├── SESSION_HANDOFF.template.md
│   │       └── verify_doc_claims.skeleton.py
│   ├── handoffs/
│   │   └── SESSION_001_BOOTSTRAP.md
│   └── topics/
│       └── infrastructure.md
└── scaffold/                               # only with --with-scaffold
    └── python/
        ├── doc_claim_verification.py
        └── build_docs_index.py
```

---

## Placeholder substitutions that ran

For `init "Acme Insights"`:

| Placeholder | Rendered value |
|---|---|
| `{{APP}}` | `Acme Insights` |
| `{{APP_SLUG}}` | `acme-insights` |
| `{{APP_UPPER}}` | `ACME_INSIGHTS` |
| `{{APP_TITLE}}` | `Acme Insights` |
| `{{DATE}}` | today's date (YYYY-MM-DD) |
| `{{YEAR}}` | today's year |

Filenames containing `{{APP_UPPER}}` are renamed on the way out:

- `starter/docs/{{APP_UPPER}}_WHAT_IT_IS.md` → `docs/ACME_INSIGHTS_WHAT_IT_IS.md`
- `starter/docs/{{APP_UPPER}}_INVENTORY.md` → `docs/ACME_INSIGHTS_INVENTORY.md`

---

## First-session checklist

Open the onboarding page (fastest):

```bash
cd acme-insights
python3 context_kit.py start
# → http://127.0.0.1:<free-port>/  (auto-opens)
```

Or the manual path (from the generated `00-START-NEXT-SESSION.md`):

1. Read `docs/docs-pattern/README.md` + `07_bootstrap_checklist.md`.
2. Flesh out `docs/ACME_INSIGHTS_WHAT_IT_IS.md`.
3. Pick stack; record in `docs/topics/infrastructure.md`.
4. Wire the verifier (`scaffold/python/doc_claim_verification.py`) into
   a CLI entry point.
5. Run `python3 scaffold/python/build_docs_index.py` to produce the first
   `docs/INDEX.md` + `docs/_index.json`.
6. End Session 1 by overwriting `00-START-NEXT-SESSION.md` and writing
   `docs/handoffs/SESSION_002_*.md`.

---

## `start` — the onboarding server

```bash
cd acme-insights
python3 context_kit.py start
```

- Serves a single page at `http://127.0.0.1:<auto-port>/` (OS-picked).
- Auto-opens the browser. Use `--no-browser` to skip.
- Use `--port 8080` to pin a port.
- Press `Ctrl+C` in the terminal to stop.

The page shows: first-session checklist, why this pattern exists, Do/Don't
rules, and a live-discovered list of your key files.

---

## Re-running `init`

Default behavior is idempotent — existing files are preserved:

```bash
python3 context_kit.py init "Acme Insights" --target ./acme-insights
# context-kit: wrote 0 files.
# No files written (already scaffolded). Re-run with --force to overwrite.
```

Use `--force` to overwrite:

```bash
python3 context_kit.py init "Acme Insights" --target ./acme-insights --force
```

---

## Without the scaffold

Dropping `--with-scaffold` skips the Python helpers — useful when the new
project isn't Python or when you want to hand-write the verifier.

```bash
python3 context_kit.py init "Acme Insights"
# (no scaffold/ directory created)
```
