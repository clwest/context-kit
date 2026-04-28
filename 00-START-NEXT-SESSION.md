# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated; wins on conflict)
> 3. `docs/handoffs/SESSION_013_V0_10_TO_V0_11_2_BACKFILL.md` — the four-release backfill + Phase 1 truth restore
> 4. `docs/handoffs/SESSION_012_V0_9_0_RELEASE_CLOSEOUT.md` — last release closeout before the gap
>
> When any other doc disagrees with the above, the above wins.

---

## Where state actually is right now

- **Version:** `0.11.2` (`pyproject.toml`). Published to PyPI; tagged
  `v0.11.2` on `origin`; GitHub release attached.
- **`cli/__init__.py.__version__`:** resolves via
  `importlib.metadata.version("contextkit-ai")` — single source of
  truth, no manual constant to drift.
- **Tests:** **494 / 494 passing**.
- **Inventory:** current (`python3 context_kit.py inventory --check`
  clean).
- **`[Unreleased]` in CHANGELOG.md:** empty. Next release will be
  `[0.12.0]` and will include the new `audit` command (commit `9b56acc`,
  not yet released).

The last four releases (0.10.0, 0.11.0, 0.11.1, 0.11.2) shipped without
session handoffs — backfilled in `SESSION_013` this session. Read that
file for what changed across the window.

---

## Next session priorities

Three threads, in roughly the order I'd tackle them. None are committed
yet — confirm scope with the user before starting.

### 1. Audit feature expansion

`context-kit audit` ships as a static-prompt printer (commit `9b56acc`).
It works, but is intentionally minimal. Possible next steps, in order
of payoff:

- **`audit --check` / `audit --json`** modes that *run* selected drift
  checks programmatically (inventory freshness, version-constant
  consistency, missing handoffs since last release tag) instead of
  delegating everything to the agent. The static prompt stays for the
  things only an LLM can do; the deterministic checks move into the
  command itself.
- **Pipe-friendly output.** The current prompt is plain text; consider
  whether `--copy` (pbcopy on macOS, xclip elsewhere) is worth adding
  given the existing one-liner workaround.

Decide scope before writing code. The command was added under "do not
over-engineer"; that constraint should still hold.

### 2. Adopt refactor

`cli/adopt.py` is **4,776 lines** and `tests/test_adopt.py` is **6,337
lines** — together ~59% of the Python in the repo. 16 of the last 25
commits touch adopt. The refactor is overdue but should be approached
carefully:

- **First step is measurement, not splitting.** Run `coverage run -m
  unittest tests.test_adopt` to find dead branches before deciding the
  module boundaries. Refactoring under bad coverage is risk for no
  payoff.
- **Proposed split** (from the SESSION_013 handoff): `cli/adopt/`
  package with `detect.py`, `classify.py`, `summarize.py`, `prompt.py`,
  `write.py`, `notes.py`. Keep `cli/adopt.py` as a thin orchestrator
  that re-exports `run_adopt` so the test split can land incrementally.

Multi-session work. Don't try to land it in one PR.

### 3. Doc drift cleanup (Phase 2 of the audit)

Phase 1 (this session) closed the P0 findings — inventory regen,
SESSION_013 backfill, version constant fixed, start-here doc rewrite.
Phase 2 closes the P1 references that are still wrong:

- **Stale skill paths in 4 docs.** `CLAUDE.md:90`, `README.md:283-284`,
  `docs/CONTEXT_KIT_WHAT_IT_IS.md:92,101`,
  `docs/DISTRIBUTION_NOTES.md:88-89,245-247` reference a root-level
  `skills/` that doesn't exist. Source is `cli/_skills/context-kit/`;
  mirror is `.claude/skills/context-kit/`.
- **Inventory narrative subcommand table** at
  `docs/CONTEXT_KIT_INVENTORY.md:46-54` lists 5 of 10 commands.
  Missing: `adopt`, `audit`, `doctor`, `recommend-stack`, `seed`.
  Either extend it to all 10 (with risk-relevance: `adopt` mutates
  with `--write`; `audit` is read-only) or delete the table and rely
  on the auto-block.
- **README version framing.** `README.md:265` still frames v0.8.0–v0.9.0
  as the current frontier. Either drop the version anchors or rewrite to
  current.
- **Inventory drift notes** (`docs/CONTEXT_KIT_INVENTORY.md` near line
  80) reference "queued investigations" that no longer exist.

### Phase 3 — the durable fix (do this before the next release)

Add `python3 context_kit.py inventory --check` as a step in
`.github/workflows/test.yml`. Without this, the drift this session
just fixed will recur on the next release. Same shape for a "handoff
exists for current version" check if we want to enforce that
structurally too.

---

## What is intentionally NOT in scope for this session's commit

- `scripts/track_engagement.py` (PyPI / GH telemetry snapshotter — the
  user's engagement-tracking thread).
- `metrics/engagement.csv`.
- `.gitignore` modifications adding `metrics/` to the ignored set.

These are a separate thread of work and stay untouched in the working
tree. See `git status` for current state.

---

## Where to look when you come back

| What | Where |
|---|---|
| This session's backfill handoff | `docs/handoffs/SESSION_013_V0_10_TO_V0_11_2_BACKFILL.md` |
| Last release closeout before the gap | `docs/handoffs/SESSION_012_V0_9_0_RELEASE_CLOSEOUT.md` |
| Audit prompt | `python3 context_kit.py audit` |
| Audit command source | `cli/audit.py` |
| Adopt code (refactor target) | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| Recent commits | `git log --oneline -16` |
| CI config (Phase 3 target) | `.github/workflows/test.yml` |

---

## Load-bearing reminder

`docs/CONTEXT_KIT_INVENTORY.md` is auto-generated from `context-kit
inventory --write`. Re-run it whenever code/test/doc counts change so
the runtime anchor stays accurate. CI does **not** currently enforce
this — that's Phase 3 of the audit. Until then, the discipline is
manual.
