---
title: "Session 002 — Real Inventory Generator (Option D)"
date: 2026-04-25
status: shipped
---

# Session 002 — Real Inventory Generator (Option D)

Closes the dogfood loop opened in Session 1. The repo's inventory file
is no longer hand-maintained — `context-kit inventory --write`
generates the numbers from real repo state, and `--check` is a
CI-friendly gate that fails when the inventory drifts.

---

## What shipped

A single commit: `feat(inventory): add runtime inventory generator`.

### `context-kit inventory` — three modes

`cli/inventory.py`. Same in-process pattern as `orient` and `hotpath`.

| Mode | Behavior | Exit codes |
|---|---|---|
| `--write` | Update the managed block in `docs/CONTEXT_KIT_INVENTORY.md`. Creates the file with a default header if missing; appends the block safely if the file exists but has no markers. | `0` on success, `2` on bad project path |
| `--check` | Regenerate in memory and compare against the existing block. CI-friendly. | `0` if current, `1` if stale or no block, `2` on error |
| `--json` | Print machine-readable JSON to stdout. Read-only. | `0` on success |

The managed block lives between two HTML-comment markers:

```
<!-- context-kit:inventory:start -->
<!-- context-kit:inventory:end -->
```

Everything outside the markers is human-written and preserved on every
`--write`. The marker strings are exact and load-bearing.

### What gets collected

| Field | Source |
|---|---|
| `cli_subcommands` | In-process `context_kit.build_parser()` introspection |
| `cli_modules` | `cli/*.py` |
| `guide_docs` | `0[1-8]_*.md` at project root |
| `docs_files` | `docs/*.md` (excluding the inventory file itself) |
| `handoff_files` | `docs/handoffs/*.md` |
| `template_files` | `templates/*` (files only) |
| `starter_files` | `starter/**/*` files, excluding `starter/scaffold/` |
| `scaffold_files` | `starter/scaffold/**/*` files |
| `test_files` | `tests/test_*.py` |
| `test_count` | Static `def test_` parse — fast, no execution |
| `skill_files` | `skills/**/SKILL.md` |
| `tracked_file_count` | `git ls-files` (None if not a git repo) |
| `package` | Regex extraction of `name`, `version`, `description`, `requires-python` from `pyproject.toml` |
| `hotpath` | In-process reuse of `cli.hotpath._collect_files` / `_with_sizes` |

JSON output is sorted, indented, and stable — safe to diff in code
review or pipe to `jq`.

### Bootstrap / runtime copy

`cli/inventory.py` added to `RUNTIME_COPY` in `cli/bootstrap.py`. Every
generated project ships the inventory subcommand standalone.

### Tests

`tests/test_inventory.py` — 20 new tests covering:

- JSON output is valid and includes every documented key
- JSON does not modify the inventory file
- `--write` creates the file with markers + default header when missing
- `--write` replaces only the block when markers exist
- `--write` preserves all content outside markers (including before
  and after)
- `--write` keeps exactly one marker pair
- `--write` appends safely when the file exists but has no markers
- `--check` passes immediately after `--write` (timestamp normalization
  works)
- `--check` fails when file missing, when no block, when stale
- Direct API: `collect_inventory()` returns expected keys;
  `write_inventory()` returns correct action label
- `--write`/`--check`/`--json` mutually exclusive — no mode returns 2

Total suite: **89/89** passing.

### Dogfood inventory file

`docs/CONTEXT_KIT_INVENTORY.md` rewritten:

- Removed the hand-written "Core counts" table — superseded by the
  auto-block
- Removed the hand-written "Guide doc inventory" *count* table — kept
  the **topic** mapping (filename → what it teaches), since topics are
  the value and the generator can't know them
- Removed the "How to verify" shell-snippet section — replaced by
  pointers to `--write` / `--check` / `--json`
- Kept the narrative subcommand inventory (read-only? network?
  properties the agent needs) — generator can't know those either
- Kept Drift Notes — repurposed to document things the generator can't
  surface (PATTERN_EXCLUDES gap, narrative TL;DR scale-line
  duplication, why the inventory excludes itself from `docs_files` and
  `hotpath`)
- `status:` frontmatter changed from `manual` to `auto-with-narrative`

### README

Added `inventory` to the commands list and a per-mode options table.

---

## Verification

```
python3 context_kit.py inventory --write    # context-kit: updated docs/CONTEXT_KIT_INVENTORY.md
python3 context_kit.py inventory --check    # context-kit: inventory is current
python3 context_kit.py inventory --json     # valid JSON to stdout
python3 context_kit.py orient               # all 5 sections, latest handoff is this file
python3 context_kit.py hotpath              # OK, top 10 sum ~88 KB / total ~230 KB
python3 -m unittest discover -s tests -t .  # 89/89 passing
```

---

## Design choices and tradeoffs

### Self-reference: how the inventory excludes itself

The inventory's data includes `docs/` file count and a hot-path
summary (file sizes). The inventory file itself lives in `docs/` and
appears in the file list. Without exclusion, writing the inventory
*changes the inventory*: the file's existence and size change between
`--write` (which renders before writing) and the next `--check`
(which sees the just-written file). `--check` would fail
immediately.

Fix: exclude the inventory file from both `_docs_files` and
`_hotpath_summary`. Documented in the Drift Notes section of the
inventory file itself, and in inline comments in `cli/inventory.py`.

### Timestamp normalization

The auto-block contains a `<!-- Last generated: <ISO time> -->` line.
A naive byte-for-byte `--check` would fail every time because the
timestamp moves. The check normalizes that line on both sides
(replaces with a placeholder) before comparing. Means the check is
honest about content drift while ignoring time-of-rendering drift.

### Test count via static parse, not unittest discovery

I count `def test_*(` definitions with regex rather than running
unittest in collect mode. Pros: fast (~ms), deterministic, no test
side-effects. Cons: misses parametrized multipliers (subTest, etc.).
For the unittest-conventional tests this repo uses, the static count
matches discovery exactly. If a future test file leans on
parametrization, the count under-reports — at which point we
either (a) accept the under-report or (b) switch to a real discovery
call.

### `--write` is the only mutating mode

`--check` and `--json` are strictly read-only. Even when `--check`
finds the inventory stale, it does not auto-fix — that would mask
drift in CI and surprise users. CI policy: run `--check`, fail the
build on nonzero, let the developer run `--write` and commit the
update.

### Subcommand introspection trusts the in-process parser

`_cli_subcommands()` calls `context_kit.build_parser()` from this
process rather than parsing `--help` output of a subprocess. Cleaner
and more precise, but assumes the project's `context_kit.py` matches
ours. That assumption holds because every generated project gets a
byte-identical copy via `RUNTIME_COPY`. If a user customizes their
entry script, this assumption breaks — at which point the right fix
is a re-introspection pass that loads the project's own
`context_kit.py` via `importlib.util`. Not worth the complexity yet.

---

## Files changed

```
M  cli/bootstrap.py                          (+1 RUNTIME_COPY entry)
A  cli/inventory.py                          (~340 lines)
A  tests/test_inventory.py                   (~330 lines, 20 tests)
M  context_kit.py                            (+ inventory subparser, dispatcher entry)
M  README.md                                 (+ inventory command + options table)
M  CHANGELOG.md                              (+ Unreleased bullet)
M  docs/CONTEXT_KIT_INVENTORY.md             (rewrite, narrative + auto-block)
A  docs/handoffs/SESSION_002_INVENTORY_GENERATOR.md   (this file)
M  00-START-NEXT-SESSION.md                  (advance to Session 3)
```

---

## AI Notes

- Caught two real self-reference bugs while writing tests, not after.
  First: hotpath summary shifted between `--write` and `--check`
  because writing the inventory file changed the file's size. Second:
  `docs_files` count shifted between the same two calls because the
  inventory file *appeared* in the docs directory after `--write`.
  Both surfaced as test failures; both fixed by excluding the
  inventory file from its own data.
- The fix to the Pyright "could not be resolved" warnings on
  `cli.hotpath` and `cli.inventory` is editor-cache lag; runtime
  imports work and tests pass. Not chasing.
- The `_cli_subcommands` parameter was originally `(project: Path)`
  for API symmetry with the other collectors, but never used the
  argument. Removed the parameter rather than naming it `_project`
  or adding a fake use — honest signature beats consistent signature.
- One judgment call worth flagging: I rewrote
  `docs/CONTEXT_KIT_INVENTORY.md` to delete the hand-written count
  tables that the generator now owns, but I *kept* the narrative
  subcommand table (with read-only / network properties) and the
  guide-doc topic mapping. The generator can list filenames; only a
  human can label what each file *means*. This is the right
  separation, but the file's `status:` frontmatter is now
  `auto-with-narrative` rather than purely `auto` — a future cleanup
  could split into two files (`docs/CONTEXT_KIT_INVENTORY.md` for the
  auto-block, `docs/CONTEXT_KIT_INVENTORY_NOTES.md` for the
  narrative). I think the single-file version is fine for now;
  flagging it as an option.
- The `tests/` not in `PATTERN_EXCLUDES` issue surfaces clearly in the
  generated project's hot-path output. Now that the inventory
  generator exists, this gap is much more visible — running
  `inventory --json` on a generated project would reveal what's
  there. Worth fixing in Session 3 alongside the other punch-list items.
