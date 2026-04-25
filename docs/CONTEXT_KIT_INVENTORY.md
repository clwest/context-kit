---
title: "context-kit Repo Inventory"
status: manual
last_verified: 2026-04-25
companion_doc: CONTEXT_KIT_WHAT_IT_IS.md
---

# context-kit Repo Inventory

> **MANUAL UNTIL GENERATOR EXISTS.** Every count below was hand-counted
> on `last_verified`. This file is a *promise* of what runtime-derived
> data will look like once a real generator is wired up — see Option D
> in `00-START-NEXT-SESSION.md`. Until then, treat these numbers as
> accurate at the timestamp above and stale by default.
>
> The convention still holds: when this file disagrees with the
> narrative anchor, this file wins. The drift detection just happens
> in human heads instead of in code, for now.

---

## Core counts

| Item | Count | Source of truth |
|---|---|---|
| CLI subcommands | 4 | `init`, `start`, `orient`, `hotpath` (registered in `context_kit.py` `build_parser`) |
| Python source files in `cli/` | 6 | `__init__.py`, `bootstrap.py`, `placeholders.py`, `server.py`, `orient.py`, `hotpath.py` |
| Top-level guide docs | 8 | `01_two_doc_anchor.md` … `08_collaboration_roles.md` |
| Reference templates | 4 | files in `templates/` |
| Starter files | 9 | files under `starter/` (root, docs, scaffold combined) |
| Bundled Claude skills | 1 | `skills/context-kit/SKILL.md` |
| Unit tests | 69 | `python3 -m unittest discover -s tests -t .` |
| Test files | 5 | `test_bootstrap.py`, `test_placeholders.py`, `test_server.py`, `test_orient.py`, `test_hotpath.py` |
| Runtime files copied to generated projects | 5 | `RUNTIME_COPY` in `cli/bootstrap.py` |
| Skills copied to generated projects | 1 directory | `SKILLS_COPY` in `cli/bootstrap.py` |

---

## Subcommand inventory

| Command | Module | Read-only? | Network? |
|---|---|---|---|
| `init` | `cli/bootstrap.py` | No (writes to target) | No |
| `start` | `cli/server.py` | No (binds localhost) | No (loopback only) |
| `orient` | `cli/orient.py` | Yes | No |
| `hotpath` | `cli/hotpath.py` | Yes | No |

---

## Guide doc inventory

| File | Topic |
|---|---|
| `01_two_doc_anchor.md` | Narrative vs runtime split |
| `02_drift_verifier.md` | How runtime stays authoritative |
| `03_topic_docs.md` | Embeddable subsystem docs |
| `04_session_handoffs.md` | Append-only build history |
| `05_start_here.md` | Why `00-START-NEXT-SESSION.md` exists |
| `06_dos_and_donts.md` | Anti-patterns from real failures |
| `07_bootstrap_checklist.md` | First-session sequence |
| `08_collaboration_roles.md` | How AI and human share work |

---

## Drift notes (manual review)

Manual inventories are fragile by construction. Every count above had
to be re-verified by hand for this commit, and *will* drift again the
moment the next subcommand, guide doc, or test file lands. The
permanent fix is the inventory generator (Session 2 Option D). Until
then, these are the rough edges a real generator would catch
automatically without anyone having to remember:

- `tests/` is not in `PATTERN_EXCLUDES` (see `cli/bootstrap.py`), so
  generated projects ship our test files inside `docs/docs-pattern/`.
  Harmless, but a real verifier would flag it.
- The 9-file starter count includes `starter/root/`, `starter/docs/`,
  and `starter/scaffold/` — `--with-scaffold` is opt-in but the files
  always ship in the source tree.
- Several counts appear in two places (here and the narrative anchor's
  TL;DR scale line). The generator should drive both, not just this
  file, or the narrative will silently disagree again.

---

## Release history

See `CHANGELOG.md` for the canonical version log. Latest tagged
release: `0.3.0` (2026-04-21). `[Unreleased]` currently contains the
`orient`, skill, and `hotpath` features shipped 2026-04-25.

---

## How to verify (until a generator exists)

```bash
# Test count
python3 -m unittest discover -s tests -t . 2>&1 | tail -3

# Subcommand list
python3 context_kit.py --help | grep -E "^\s+(init|start|orient|hotpath)"

# File counts
find starter -type f | wc -l
find templates -type f | wc -l
ls 0[1-8]_*.md | wc -l

# Hot-file dashboard
python3 context_kit.py hotpath
```

Any drift between the table above and these commands = update the
table. That's the manual version of the verifier loop.
