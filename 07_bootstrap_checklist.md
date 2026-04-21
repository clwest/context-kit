---
title: "Bootstrap Checklist — First 10 Files for a New App"
status: active
---

# Bootstrap Checklist

Starting a new project and want the same docs pattern? These are the first 10 files to create, in order. Do them before writing app code — by file #10, the pattern is load-bearing and every session after benefits.

Estimated total time: **2–3 hours** for the first pass, including stub content.

---

## The 10 Files

### 1. `00-START-NEXT-SESSION.md` (repo root)
Even if empty. Creates the habit. Starter content:

```markdown
# Next Session — Start Here

## SOURCE OF TRUTH
- `docs/<APPNAME>_WHAT_IT_IS.md` — what the platform is
- `docs/<APPNAME>_INVENTORY.md` — what exists right now (regenerable)
- `python manage.py verify_doc_claims --only-drift` (after verifier is built)

## READ THIS FIRST — <critical trap TBD>

## SESSION 1 — START HERE
First thing: bootstrap the repo following docs/docs-pattern/.

## Next Session Picks Up With
- Finish docs/docs-pattern/ adoption
- Stand up docs/PLATFORM_INVENTORY.md generator
```

### 2. `CLAUDE.md` (or `AGENTS.md`) at repo root
AI session entry point. At the TOP:

```markdown
# CLAUDE / AGENTS — AI Session Entry Point

> **Source of truth for numbers:** `docs/<APPNAME>_WHAT_IT_IS.md` (narrative)
> + `docs/<APPNAME>_INVENTORY.md` (runtime-derived, regenerable). When this
> doc disagrees with either, INVENTORY wins.

## Quick Start
- Read `00-START-NEXT-SESSION.md` first
- Project structure in `docs/topics/`
- See `docs/docs-pattern/` for the docs framework itself
```

### 3. `docs/<APPNAME>_WHAT_IT_IS.md`
The narrative anchor. Copy [`templates/PLATFORM_WHAT_IT_IS.template.md`](templates/PLATFORM_WHAT_IT_IS.template.md). Fill in the TL;DR and layered architecture as stubs. Keep it short at first — grow with the app.

### 4. `docs/<APPNAME>_INVENTORY.md`
The runtime anchor. Copy [`templates/PLATFORM_INVENTORY.template.md`](templates/PLATFORM_INVENTORY.template.md). Even a stub inventory is useful — just write the section headings with "TBD — populated by generate_platform_inventory."

### 5. `docs/docs-pattern/` (copy this directory over)
The meta-framework. Keep it in the repo so future sessions know the rules. The templates sub-directory is what you'll use in file #3/#4/#6/#10.

### 6. `docs/handoffs/SESSION_001_BOOTSTRAP.md`
The first handoff. Even if the session only bootstrapped docs, write the handoff. Copy [`templates/SESSION_HANDOFF.template.md`](templates/SESSION_HANDOFF.template.md).

### 7. `docs/topics/` directory + 2–3 starter subsystem docs
Create `docs/topics/infrastructure.md` at minimum. Add one topic doc per subsystem as you build. Short template:

```markdown
---
title: "<Subsystem>"
status: stub
---

# <Subsystem>

<one-paragraph summary>

## Current Stats
| Metric | Value |
|---|---|

## Architecture
TBD

## Key Files
| File | Purpose |
|---|---|

## Known Issues / Drift
- None yet — subsystem is stub

## Related
- `docs/<APPNAME>_INVENTORY.md`
```

### 8. Verifier: `<backend>/services/doc_claim_verification.py` + CLI
Copy [`templates/verify_doc_claims.skeleton.py`](templates/verify_doc_claims.skeleton.py). Wire it into your framework's management-command equivalent (Django: `manage.py`, FastAPI: a Typer CLI, Next.js: a tsx script). Seed with 3–5 claims to prove the loop works.

### 9. Inventory generator: `<backend>/services/platform_inventory.py` + CLI
The regenerator for file #4. Start with 3–5 sections (Agents, Models, Routes, Tasks — whatever your stack has). Expand over time. The rule: **every section is read from runtime, never hand-written.**

### 10. Index builder: `build_docs_index` CLI
Walks `docs/` recursively, produces `docs/INDEX.md` (human-readable) + `docs/_index.json` (embeddable). Without this, the AI can't see your topic docs.

Minimal Python stub (adapt to your framework):

```python
# backend/commands/build_docs_index.py
import os, json, re
from pathlib import Path

def build():
    docs = Path("docs")
    index = {"docs": []}
    for md in docs.rglob("*.md"):
        content = md.read_text()
        headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        index["docs"].append({
            "path": str(md),
            "headings": [(len(h[0]), h[1]) for h in headings],
            "lines": len(content.splitlines()),
        })
    Path("docs/_index.json").write_text(json.dumps(index, indent=2))
    # also write INDEX.md as a human-readable TOC
    ...

if __name__ == "__main__":
    build()
```

---

## After the 10 Files

1. **Commit all 10 files** in one go with message `chore: bootstrap docs pattern (docs-pattern/ adopted)`.
2. **Add the hook:** pre-commit that runs `build_docs_index` on any `.md` change in `docs/`.
3. **Add the CI check:** `verify_doc_claims --fail-on-drift` on every PR.
4. **Start the handoff habit:** end every session with a `SESSION_N_*.md` + updated `00-START-NEXT-SESSION.md`.

By Session 5, the habit is automatic. By Session 20, you can't imagine working without it.

---

## Port Helper — Copy From This Repo

Once this repo is accessible, the fastest bootstrap:

```bash
# From the new app's repo root:
cp -r /path/to/unified-donkey-betz/docs/docs-pattern docs/docs-pattern

# Copy the verifier + inventory templates (language-adapt if needed):
cp /path/to/unified-donkey-betz/core/services/doc_claim_verification.py <backend>/
cp /path/to/unified-donkey-betz/core/services/platform_inventory.py <backend>/
cp /path/to/unified-donkey-betz/core/management/commands/verify_doc_claims.py <backend>/commands/
cp /path/to/unified-donkey-betz/core/management/commands/generate_platform_inventory.py <backend>/commands/
cp /path/to/unified-donkey-betz/core/management/commands/build_docs_index.py <backend>/commands/
```

Then adapt to your stack (Django → FastAPI → Next.js):
- Django commands become Typer subcommands or npm scripts
- `apps.get_models()` becomes a SQLAlchemy/Prisma scan
- `AGENT_MAP` dict becomes whatever your agent registry is

The **pattern** ports; the implementation adapts.

---

## What NOT to Port

- Don't copy content from `PLATFORM_WHAT_IT_IS.md` — it's about *this* platform. Rewrite for yours.
- Don't copy `docs/topics/<file>.md` content — yours will be different subsystems.
- Don't copy session handoffs — those are history for *this* project.

You're porting the **structure and tooling**, not the content.

---

## Minimum Viable Version

If 10 files is too much for day 1, the MVP is:

1. `00-START-NEXT-SESSION.md`
2. `docs/<APPNAME>_WHAT_IT_IS.md`
3. `docs/handoffs/SESSION_001_BOOTSTRAP.md`

Three files. The rest can come within the first 10 sessions.

---

*Bootstrapping the pattern is the best ~3 hours you can spend on a new project. Everything after compounds.*
