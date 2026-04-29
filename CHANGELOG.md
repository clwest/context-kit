# Changelog

All notable changes to context-kit are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.15.0] — 2026-04-30

**Refactor progress tracking.** A new `refactor` command group ships
with its first subcommand, `track`: a read-only, deterministic
progress reporter for multi-PR module-extraction refactors. Designed
for the workflow of splitting a monolith file into sibling modules
across many PRs and watching the percentage tick up over weeks of
work — without inventing numbers, hand-maintaining counts, or
re-deriving a baseline from memory each session.

### Added — `context-kit refactor track`

- **New command group `refactor`** registered under the top-level
  CLI. Anticipates two future subcommands (`extract`, `verify`) but
  v1 ships only `track`.
- **`refactor track SOURCE`** — read a monolith Python file plus its
  sibling destination files, and print a deterministic progress
  report: total / migrated / remaining item counts, percentage
  complete, items by destination (current state), top remaining
  domains (when a Phase-0-style plan is provided), and an estimated
  PR count from a configurable avg-per-PR.
- **Three v1 detectors** for "what counts as a migratable item":
  `function` (every module-level FunctionDef / AsyncFunctionDef),
  `class` (ClassDef), `celery-task` (FunctionDef decorated with
  `@shared_task` or `@app.task`, all decorator forms — bare,
  parens, kwargs, attribute access).
- **Two output formats:** `text` (human-readable, default) and
  `json` (sorted keys, byte-identical across runs — verified by
  determinism test).
- **Plan auto-discovery** — when `--plan` is omitted, looks for a
  Phase-0-style markdown file under `docs/refactors/`,
  `<source>/../docs/refactors/`, or `<source>/.`. Pass `--plan ""`
  to disable autodiscovery explicitly.
- **Plan parser is lenient** — accepts any markdown file with a
  `Total tasks:` / `Total items:` line and a destination-count
  table. Handles list-bullet prefixes, bold/italic emphasis,
  backtick-wrapped destination names. Underscores inside
  identifiers (`tasks_ops.py`) are preserved correctly.
- **Baseline resolution priority:** `--baseline-count` flag >
  plan total > computed (current source + current siblings).
  When the fallback to "computed" fires, the command emits a
  clear warning in both text and JSON output:
  > Warning: baseline inferred from current files; progress
  > may be underreported. Use --baseline-count for accurate
  > historical progress.
- **Read-only by contract.** AST + filesystem only. No git, no
  network, no subprocess. Exits 0 in all normal cases; exits 2
  only when the source path doesn't exist.

### Added — README + skill integration

- **README** entry alongside `inventory --check` / `hotpath` /
  `adopt` calling out `refactor track` as the entry point for
  multi-PR module-extraction work.
- **Bundled Claude skill** (`.claude/skills/context-kit/SKILL.md`,
  mirrored to `cli/_skills/context-kit/SKILL.md`) gains an
  "Optional — run refactor track" section so AI agents working in
  a context-kit project know to invoke the command when the user
  is in the middle of a long-running modularization effort.

### Real-world calibration

The feature was extracted from the unified-donkey-betz `core/tasks.py`
modularization that ran across this session: 5 stacked PRs (#2040
through #2044) moved 51 of 356 Celery tasks out of a 12,474-line
monolith into 5 new sibling modules (diagnostics, boardroom,
experiments, backfill, learning). The hand-maintained progress
snapshot produced mid-stream became the algorithm; the lessons
about baseline drift and plan/reality mismatch became the warning
surface. The v1 design explicitly defers `refactor extract` (the
AST-based move primitive) and `refactor verify` (the post-extract
verification battery) so the tracking surface lands first and proves
its shape on real workloads.

### Tests

- 29 new tests in `tests/test_refactor_track.py` covering: detector
  unit behavior (5), scan unit behavior (5), plan parser (5),
  fresh-state fixture (3), mid-refactor fixture (4), plan/reality
  mismatch (1), edge cases (4) including baseline-flag override and
  unknown-detector rejection.
- **Total suite: 620 tests, all passing** (was 591 in v0.14.0).
- JSON-output determinism tested by running twice and asserting
  byte-equality.

### Deferred to v0.16+ (per design)

- `markdown` output format
- `decorated:<NAME>`, `django-view`, `django-url` detectors
- `--baseline-ref GIT_REF` (compute baseline from git history)
- `orient` integration ("refactor in progress: X% complete")
- `refactor extract` (AST-based move primitive)
- `refactor verify` (post-extract verification battery)

## [0.14.0] — 2026-04-29

**Audit ↔ inspect bridge + Documentation Intelligence.** Two
complementary features that make `audit` start smarter and let
`inspect` recognize when a repo treats `docs/` as active AI
memory infrastructure rather than passive reference material.

### Added — `audit` encourages inspect-grounded findings

- **New paragraph at the top of `AUDIT_PROMPT`:**
  *"Before beginning, consider running `context-kit inspect` to
  build a system map. If inspect output is available, use it to
  ground your audit in real system structure instead of
  assumptions."* Lands ahead of the senior-engineer role frame
  so the agent's first move is to read deterministic system
  facts when they exist.
- **New audit dimension** in the existing five-bullet list:
  *"system topology and subsystem boundaries (if available)"*.
  The `(if available)` qualifier tells the agent not to
  fabricate a topology when `inspect` wasn't run.
- **Backward compatible by design.** No flags, no shape change,
  no dependency on `inspect` actually being run. Projects that
  don't have `inspect` available get a slightly longer prompt
  with one extra `(if available)` bullet — nothing breaks. The
  same updated prompt rides along inside `audit --write`'s
  embedded prompt block.
- 3 new audit-prompt tests + augmented `--write` embed test for
  end-to-end coverage of the new content.

### Added — `inspect` Documentation Intelligence section

- **Detects whether `docs/` is being used as active AI memory
  infrastructure** (embedded, retrieved, or injected at runtime)
  rather than passive reference material. Filename /
  directory-existence probes only — no parsing.
- **Signal types probed:**
  - Markdown files under `docs/` (recursive, ignored-dir-aware)
  - `SESSION_*.md` session handoffs in `docs/handoffs/`
  - Anchor docs at `docs/*_WHAT_IT_IS.md` +
    `docs/*_INVENTORY.md`
  - Audit / cleanup folders directly under `docs/` (any name
    containing `audit` or `cleanup`)
  - Process docs at `docs/docs-pattern/` (plus `process/`,
    `patterns/` variants)
  - RAG corpus at `.rag/*.{jsonl,json}` at the project root
- **Strength classifier (deterministic):** `none` if no markdown
  found; `low` if docs exist but no active-context signals;
  `medium` if ≥ 2 distinct active-signal types are present;
  `high` if ≥ 2 signals AND scale (≥ 200 markdown files OR
  ≥ 50 session handoffs).
- **Report section renders at `medium` and `high` strength**
  with the standard interpretation + caution lines:
  > This repository appears to use documentation as an active
  > context/memory layer.
  > ! Caution: do not treat docs/ as disposable clutter without
  >   checking whether docs are embedded, retrieved, or injected
  >   at runtime.

### Added — `review-docs-context-first` recommendation

- **New recommendation rule** that fires only at
  `documentation_intelligence.strength == "high"`. Confidence:
  `high`. Suggestion: *"Review the docs context layer before
  deleting, archiving, or refactoring documentation."* `why`
  line cites the actual signal counts.
- **Wired ahead of risk-driven recommendations** so the
  "don't delete docs" warning lands early enough to influence
  what other cleanup PRs touch.

### Changed — JSON schema gains `documentation_intelligence`

- **`documentation_intelligence` joins the locked top-level
  keys** (13 total now). The field is always present
  regardless of strength.
- **Inner schema (8 keys, locked):** `markdown_file_count`,
  `session_handoff_count`, `anchor_docs`, `audit_folders`,
  `process_docs_present`, `rag_corpus_present`,
  `rag_corpus_paths`, `strength`.
- 7 new tests in `TestDocumentationIntelligence` cover no-docs
  → `none`, small-docs → `low`, medium signal renders section
  without rec, high signal fires recommendation, anchor doc
  paths are project-relative, RAG `.jsonl` detection, and the
  inner-schema lock.

### Real-world calibration

- **unified-donkey-betz** (the dogfood target):
  `strength=high` (1,901 markdown files, 661 handoffs, 4
  anchor docs, 4 audit folders, process docs, RAG corpus).
  `review-docs-context-first` fires as the first
  recommendation, ahead of `cleanup-tracked-venv`.
- **context-kit (this repo):** `strength=medium` (21
  markdown, 12 handoffs, 2 anchors, 1 audit folder, no RAG).
  Section renders with interpretation + caution; the
  high-confidence recommendation is correctly skipped because
  this repo doesn't approach the active-context-layer scale.

### Tests

- 591 passing (was 581 at v0.13.0 release).
- +3 in `tests/test_audit.py` for the audit-prompt bridge
  (inspect pre-run guidance, grounding instruction, topology
  dimension), plus 1 augmented `--write` embed assertion.
- +7 in `tests/test_inspect.py` for documentation
  intelligence (the seven scenarios above), plus the locked
  top-level keys test now includes `documentation_intelligence`.

## [0.13.0] — 2026-04-29

**System-mapping milestone.** New `context-kit inspect` command turns
context-kit from "audit prompt + cleanup loop" into a tool that also
produces a deterministic, code-side map of *what's actually in the
repo* — primary stack, depth-1 workspaces with per-child framework
probes, hot files, risk patterns, and a recommendations engine.
Where `audit` outsources inspection to an LLM (the prompt is the
output), `inspect` reads the code and prints what it found.

### Added — `context-kit inspect`

- **New top-level command.** `context-kit inspect [PATH]` reads an
  arbitrary repo and prints a structured system map: primary stack
  (manifest-driven), depth-1 workspace children with per-child
  framework probes, framework signals, entry points, hot files,
  risk patterns, likely-stale docs, and a deterministic
  "Recommended next moves" list.
- **Read-only by contract.** Never modifies files, never invokes an
  AI, never parses code as an AST. Filename / regex probes only.
- **Designed to seed an audit, not replace one.** The output is
  "what's here," not "what does it do" — hand the result to an
  agent, or use it directly to scope a cleanup PR.

### Added — Framework probes (v1: Django + Next.js)

- **Django** fires when `manage.py` is at scope root. Counts
  management commands (files in `*/management/commands/`),
  regex-matches `path(` / `re_path(` calls in `**/urls*.py`,
  `@shared_task`-family decorators in `**/tasks*.py`, view / model
  files, and sniffs `INSTALLED_APPS` length from `**/settings*.py`.
- **Next.js** fires when `next.config.{js,ts,mjs,cjs}` exists.
  Counts `page.{tsx,ts,jsx,js}` files under `app/` / `pages/` and
  `route.{ts,tsx,js}` for App Router API routes.
- Other frameworks (Rust, Go, smart contracts, mobile) are detected
  only as their primary language; specific signal counts are
  deferred to a future release.

### Added — Monorepo / workspace handling (depth-1 only)

- **Child directories with their own manifest get one framework
  probe each.** The recognized manifests are the same set the
  primary-stack classifier uses (`pyproject.toml`, `setup.py`,
  `package.json`, `next.config.*`, `Cargo.toml`, `go.mod`, etc.).
- **Each workspace renders as its own subsystem** in the report
  with framework-specific signals attached. Non-workspace
  top-level dirs render as bare file-count summaries (top 8 by
  size).
- **No deeper recursion in v1.** Workspaces inside workspaces are
  not probed individually.

### Added — Risk patterns (5 stable IDs in v1)

- `tracked-venv` — virtualenv directories tracked in git
  (`venv/`, `.venv/`, `venv_ml/`, `env/`, `ENV/`).
- `tracked-env-file` — `.env` (no template suffix) tracked at
  root; high severity, treat secrets as compromised.
- `multiple-env-templates` — three or more `.env.*` template
  variants at root; medium severity (likely duplication).
- `oversized-static-asset` — `*.png` / `*.jpg` / `*.svg` /
  `*.gif` / `*.webp` ≥ 5 MB inside any `*/static/` / `public/` /
  `assets/` segment.
- `tracked-build-artifacts` — `__pycache__/` / `node_modules/` /
  `dist/` / `build/` / `.pytest_cache/` / `.mypy_cache/`
  directories with tracked files. Probe runs an independent
  `git ls-files` (or unfiltered `os.walk` fallback) because
  `cli.hotpath._collect_files` filters those names by design.

### Added — Recommendations engine

- **Six rules in priority order, capped at 5 emitted suggestions.**
  Each fires only when its triggering signal is present; each
  emits a `Recommendation` dataclass with `id`, `suggestion`,
  `why`, and `confidence` (`low` / `medium` / `high`).
- **Rule IDs (stable for future override storage):**
  `cleanup-tracked-venv` (high), `rotate-and-untrack-env` (high),
  `triage-{risk-id}` (high fallback), `scaffold-audit-workspace`
  (medium, gated on "worth auditing": ≥1 risk OR framework
  signals OR >100 files), `consolidate-env-templates` (medium),
  `run-hotpath-leaderboard` (medium, gated on largest file
  ≥ 1 MB), `review-stale-docs` (low),
  `consider-per-subsystem-audit` (low, ≥2 framework workspaces).
- **Override-friendly framing.** Recommendations are phrased as
  suggestions ("Consider running...", "Review..."), not bare
  commands. Each rendered line carries a stable `id:` so a
  future override store can suppress specific recommendations
  per-repo. v1 has no override store; the schema is the
  contract for v2.

### Added — Stale-doc heuristic

- **Header-date grep on top-level + `docs/*.md`.** Flags files
  whose self-reported date (frontmatter `date:` line, or one of
  `Last Updated:` / `Generated:` / `Updated:` markers) is
  parseable as ISO `YYYY-MM-DD` and older than 30 days. Threshold
  is hardcoded in v1; deliberately conservative on what counts
  as stale.

### Added — JSON output

- **`--json` switches to machine-readable output** with locked
  top-level keys: `repo`, `path`, `head`, `counts`,
  `primary_stack`, `subsystems`, `entry_points`,
  `framework_signals`, `hot_files`, `risks`, `stale_docs`,
  `recommendations`. Risk and recommendation `id` fields are
  the load-bearing surface for downstream tools.
- **`--depth N`** controls workspace-detection depth (default
  `2`; v1 only uses depth-1 in practice but the flag is wired
  for future use).

### Fixed — `cli/__init__.py.__version__` survives source-only checkouts

- **CI regression on every push since v0.12.0's release-prep
  commit.** `cli/__init__.py` called
  `importlib.metadata.version("contextkit-ai")` at import time;
  GitHub Actions runs the test suite without `pip install`, so
  the package metadata isn't present and the lookup raises
  `PackageNotFoundError`. The exception propagated out of
  `__init__.py` and every test module's `from cli.X import ...`
  failed at module-import time.
- **Wrap the lookup in try/except**, fall back to a sentinel
  string `"0.0.0+source"` (PEP 440-valid local-version segment).
  Installed wheels keep returning the real version because the
  success path runs first. v0.12.0 PyPI wheel is unaffected —
  the bug only bit source-only invocations (CI, fresh clones
  running `python3 context_kit.py` without installing).
- **`tests/test_cli_version.py`** locks the fallback so future
  refactors can't quietly re-break CI.

### Tests

- 581 passing (was 546 at v0.12.0 release, was 549 after the CI
  fix landed).
- +32 in `tests/test_inspect.py` across 8 classes:
  empty / non-git directories, Django + Next.js probes counting
  expected signals, monorepo split with per-workspace framework
  attribution, all five risk-pattern IDs firing on synthetic
  fixtures, JSON schema lock, stale-doc heuristic (old date
  flags / recent date doesn't), and 11 recommendation-rule cases
  (schema, cap, conditional firing, confidence labels, priority
  ordering, text rendering with `[confidence]` + `id:` +
  override-friendly framing).
- +3 in `tests/test_cli_version.py` for the fallback contract.

### Real-world dogfood

- **unified-donkey-betz** (7,904 tracked files, 166 MB tree):
  runs in ~0.27s; correctly identifies `python + django` at
  high confidence with 45 apps / 115 models / 2,021 url
  patterns / 430 task decorators / 186 management commands;
  surfaces `tracked-venv` / `multiple-env-templates` /
  `oversized-static-asset` / `tracked-build-artifacts` risks;
  emits 3 recommendations (1 high, 2 medium).
- **context-kit (this repo):** emits 1 recommendation
  (`run-hotpath-leaderboard`, medium); `scaffold-audit-workspace`
  correctly skipped because `docs/audit/AUDIT_V1.md` already
  exists.

## [0.12.0] — 2026-04-28

**Audit-execution loop milestone.** Three new commands —
`audit`, `fix`, and `exec` — turn `context-kit` from a
project-bootstrap tool into a full audit → plan → execute
loop usable on any repo, not just ones it scaffolded. Plus
an upstream fix to `orient`'s latest-handoff selection
(discovered while dogfooding the new loop on a real
external project), team-reporting tone added to all
AI-facing prompts, and a real-world workflow writeup that
records an actual end-to-end run.

### Added — `context-kit audit`

- **New top-level command.** Prints a structured
  senior-engineer audit prompt to stdout: stale or
  misleading documentation, duplicated logic, dead code,
  risky / fragile patterns, and inconsistencies between
  declared state and actual runtime. Findings are
  P0 / P1 / P2 prioritized; the agent then proposes a
  concrete cleanup plan with phases.
- **`audit --write` scaffolds an audit workspace.** Creates
  `docs/audit/AUDIT_V1.md` (paste-target with a Metadata
  block) and `docs/audit/CLEANUP_PLAN.md` (Phase 1/2/3
  template) under the project root. **Existing files are
  never overwritten.** A re-run prints `skipped` for files
  that already exist; if either still carries its scaffold
  marker substring, the output also prints
  `Audit files exist but appear unfilled.` so a stale
  workspace is visible at a glance.
- **`audit --write` embeds the audit prompt.** After the
  scaffold output, the same prompt the no-flag invocation
  prints is included under `Audit prompt:` plus a numbered
  `Next steps:` block — so the user can scaffold + copy
  the prompt in one invocation instead of two.

### Added — `context-kit fix`

- **Reads `docs/audit/AUDIT_V1.md` + `docs/audit/CLEANUP_PLAN.md`
  and prints the phased cleanup plan as a human-readable
  outline.** Validates the workspace first (both files must
  exist and neither can still carry a scaffold-marker
  substring); exits `1` with a one-line pointer at
  `context-kit audit --write` when the workspace isn't
  ready.
- **Two markdown shapes for the plan are supported equally:**
  H1–H6 `### Phase N — Title` headings with top-level
  bullets, and top-level `- Phase N — Title` bullets with
  indented sub-bullets. Bullets between two phase boundaries
  belong to the preceding phase.
- **Modes:** default prints all phases under
  `=== CONTEXT-KIT FIX PLAN ===`; `--phase N` scopes to one
  phase only (errors if `N` isn't present, names the
  available phases); `--next` returns the first step of the
  first phase that has steps (skips empty phases). `--phase`
  and `--next` are mutually exclusive. Read-only by
  contract: never modifies files, never invokes an AI,
  never executes any printed step.

### Added — `context-kit exec`

- **Renders the same cleanup plan as a structured AI
  execution prompt** instead of a human-readable outline.
  Six fixed sections: **Goal / Context / Instructions /
  Phase tasks / Constraints / Output expectations**.
  Designed to be pasted into an AI coding agent as a
  kickoff message.
- **Anti-scope-creep constraints baked into the prompt.**
  *"Do not modify source files outside the scope of the
  listed tasks. Do not invent new tasks. Do not commit on
  a broken test suite. Read-only operations first."* So
  the constraint language doesn't have to be re-typed
  every session.
- **Same modes as `fix`:** default prints all phases;
  `--phase N` scopes to one phase with explicit
  *"Do not start other phases in the same invocation"*
  language in the Goal; `--next` returns a single-step
  prompt with single-step variants of the Goal and Output
  expectations sections. `--phase` and `--next` are
  mutually exclusive.
- **Validation, marker detection, and phase parsing
  reuse `cli.fix`** so both commands speak the same
  markdown grammar. Adding a new phase shape only needs
  to land in fix.py.

### Added — Team-reporting tone in all AI-facing prompts

- **AUDIT_PROMPT** gains a final paragraph asking the
  agent to *"report back as if you're updating a small
  project team. Keep it concise, specific, and
  action-oriented: what you checked, what you'd change or
  recommend, what remains open, and what you need from the
  team next."* Surfaces in `audit` (default) and inside
  the embedded prompt printed by `audit --write`.
- **`exec`'s Output expectations block** in both the
  full-prompt and `--next` variants leads with the same
  team-reporting framing, and the wrap-up sentence asks
  for the four-beat summary explicitly: what landed,
  what's still open, what's needed from the team next.
- **Senior-engineer / execution framing is preserved.**
  Team-reporting is a communication style, not a tone
  change — the prompts still ask for prioritized findings,
  specific file references, and a phased plan.

### Fixed — `orient` latest-handoff selection

- **Discovered while dogfooding `audit` on a real external
  project.** `context-kit orient` was selecting the wrong
  "latest handoff" because `cli/orient.py:121` used
  `sorted()` over a `glob("SESSION_*.md")` — a
  lexicographic sort. Two trap layers surfaced:
  - `SESSION_ROADMAP_*.md` lex-sorted after `SESSION_999_*`
    because `'R' > '9'`. Renaming the ROADMAP file in the
    target repo closed only the outermost layer.
  - 3-digit `SESSION_999_*` lex-sorts AFTER 4-digit
    `SESSION_1098_*` because ASCII `'9' > '1'`. So even
    after the rename, sessions kept regressing as repos
    crossed 999 → 1000.
- **New rule in `_latest_numbered_handoff`:**
  1. Only files matching `SESSION_<digits>_*.md` are
     considered. Non-numbered names (`SESSION_ROADMAP_*`,
     `SESSION_NOTES_*`, etc.) are ignored.
  2. Sort by **integer session number** (1098 > 999).
  3. Tiebreak on `mtime` ascending — when two files share
     a session number (wrap + addendum pattern), the most
     recently modified file wins.
- 7 new tests cover empty dir, ROADMAP ignored,
  only-non-numbered returns `None`, 4-digit beats 3-digit,
  mtime tiebreak among same session number, higher session
  beats newer mtime, and end-to-end orient output names
  the right file when ROADMAP and a 1100 session live
  alongside the auto-scaffolded 001.

### Added — `scripts/track_engagement.py`

- **Daily-snapshot tracker for PyPI download stats and
  GitHub traffic / repo metrics.** stdlib-only; appends
  one row per run to `metrics/engagement.csv` (PyPI
  day/week/month, GH views/uniques/clones/cloners 14d,
  stars, forks, watchers, open issues, top referrer).
  GitHub's traffic API only retains 14 days, so we have
  to roll our own history.
- **Flags:** `--no-write` fetches and prints without
  persisting; `--diff` prints the delta against the prior
  row.
- Requires `gh` CLI authenticated for traffic endpoints;
  otherwise read-only and zero new dependencies. Intended
  for ad-hoc runs or a launchd / cron / GitHub Actions
  schedule. `metrics/` is gitignored — engagement data is
  private.

### Added — `docs/WORKFLOWS_REAL_WORLD.md`

- **End-to-end record of a real `audit → fix → exec →
  execute` run** against an external Django + Celery
  project (7,928 tracked files, ~919K LOC). Engineer-
  audience writeup: concrete numbers (`hotpath` top-15
  74.01 MB → 63.57 MB delta, 16 PNGs untracked, two
  stacked PRs), the dry-run-first execution discipline,
  the stacked-PR pattern, and the audit calibration miss
  (`"docs` false positive from misreading `git ls-files`'s
  default quoting behavior).
- **"When not to use this workflow" section** so the doc
  doesn't read as a universal recommendation. Small repos,
  one-off scripts, and obvious fixes are explicitly out
  of scope.

### Changed — `cli/__init__.py.__version__`

- **Constant replaced with `importlib.metadata.version()`
  lookup.** The hand-maintained `__version__ = "0.3.0"`
  was 8 minor versions stale. New behavior sources the
  version from the same place setuptools does — single
  source of truth, no manual constant to drift.

### Tests

- 546 passing (was 489 before this release window).
- +5 in `tests/test_audit.py` for the audit prompt + UX
  improvements (`--write` scaffold idempotency, "appear
  unfilled" notice, embedded prompt, team-reporting
  framing).
- +15 in `tests/test_fix.py` covering validation,
  full-plan rendering, alternate bullet shape, phase
  filtering, `--next` empty-phase skipping.
- +16 in `tests/test_exec.py` covering validation,
  full-prompt all-six-sections, phase filtering with
  scaffolding-preserved, `--next` single-step framing,
  team-reporting in both full and single-step variants.
- +7 in `tests/test_orient.py` covering the
  numbered-handoff selection rule (empty, ROADMAP
  ignored, 4-digit beats 3-digit, mtime tiebreak, higher
  session beats newer mtime, end-to-end via `run_orient`).
- Audit + exec test loosening: short-substring assertions
  instead of long contiguous strings, so reasonable line
  reflows in the prompt templates don't break tests.

### Process

- **Phase 1 audit cleanup landed first.** Backfill
  `SESSION_013` covers the v0.10.0 → v0.11.2 release
  window that shipped without inline session handoffs.
  `00-START-NEXT-SESSION.md` is now anchored on Session
  013 instead of the stale Session 012 framing.
- **Audit calibration log lives in
  `docs/cleanup/FOLLOWUPS.md`** in the target repo. A
  `"docs` shell-artifact finding turned out to be a misread
  of `git ls-files`'s default quoting; lessons captured
  under `AUDIT-CAL-2026-04-28` so future audits don't
  repeat it.

## [0.11.2] — 2026-04-27

**Preserve-context loop closed.** The Agent Launch Prompt now
asks the agent to end its initial inspection response with a
copy-paste command that captures findings via `--notes`. One
copy → one paste → findings persist into BUILD_PLAN.md,
00-START-NEXT-SESSION.md, and the CLAUDE.md managed block
automatically. No more hand-copying inspection output into a
follow-up `--write` run.

### Added — `TO PRESERVE THIS CONTEXT` section

- **New section** sits between SAFETY INSTRUCTIONS and the
  closing wrap-up line of the Agent Launch Prompt. Embeds the
  exact `context-kit adopt . --write` command pre-wired with
  three placeholders the agent fills in:
  - `<refined one-sentence project summary>` → `--project-summary`
  - `<recommended next task>` → `--next-task`
  - `<key findings from this inspection>` → `--notes`
- **Five guardrails** for what the agent emits:
  1. Notes must be concise but specific (real risks, missing
     wiring, stale docs, dirty git state, incomplete features)
  2. Do not include secrets, tokens, or credentials in any value
  3. Escape quotes (`\"`) inside values, or rephrase to avoid
     quotes
  4. If no meaningful findings exist, omit `--notes`
  5. Do not run the command yourself — emit it for the user to
     copy

### Why this exists

The v0.11.0 / v0.11.1 work made agents do good initial
inspection (deep findings instead of "let me update the
README"). But the user then had to hand-summarize those
findings into a `--notes` flag manually for the follow-up
`--write` run — a clunky context-loss step. This release
makes the agent emit the whole `--write` line itself, so the
preservation loop closes in one paste.

### Validated against

Local testing on mentorforge (FastAPI + React/Vite split with
real production findings: Stripe/CORS/auth issues). The agent
correctly:
- Performed the same depth of inspection as prior tests
- Ended its response with a complete `context-kit adopt . --write`
  command
- Filled `--notes` with real findings (no placeholders, no
  secrets)
- Did not execute the command — emitted it for the user

### Tests

8 new tests in `TestAgentPromptBehaviorRules` lock the section
header, the embedded command + all three flags + all three
placeholders, the anti-secrets warning, the emit-don't-run
guard, the omit-notes-when-empty guidance, the placement
contract (SAFETY → PRESERVATION → WRAP-UP), and rendering
across unclear / single-stack / full-stack repos. 489/489
tests green.

### Scope

Patch level (not minor). No new flags, no new dataclasses,
no detection logic changes — only additive text in the
Agent Launch Prompt body.

## [0.11.1] — 2026-04-27

**Agent-behavior shaping in the launch prompt.** Two scoped
prompt-body improvements driven by real-repo testing
(mentorforge, flow-name-service, norman-handyman-mvp). No new
flags, no API changes, no detection logic changes — just the
text agents read.

### Added — three-tier inspection rule

- **New `HOW TO APPROACH THIS REPO` section** sits between the
  recommended first action and the safety instructions. Scales
  inspection depth to confidence:
  - **Low / unclear** — full structured read-through (entry
    points → system map → inconsistencies)
  - **Medium** — quick inspection (README + top-level + 1–2
    main files), then decide whether deeper analysis is
    needed
  - **High** — skip the read-through and go directly to the
    highest-value next task
- **Why this exists.** Most repos adopt sees land in "medium"
  confidence. The single-tier rule shipped in v0.11.0 made
  agents over-prepare on simple cases and under-prepare on
  hard ones. The three-tier rule lets the agent right-size
  its own ramp.

### Added — anti-doc-fallback priority rule

- **New `WHAT TO PRIORITIZE` section** in the same
  between-first-action-and-safety block:
  > Prefer identifying real risks, inconsistencies, missing
  > wiring, or unused / incomplete features over surface-level
  > tasks. Do not default to documentation updates unless the
  > user explicitly asked for them.
- **Why this exists.** Real-repo testing showed agents
  defaulting to "let me update the README" when handed a
  clear, healthy project — burning the chance to surface
  actual production bugs (Stripe redirect issues, CORS
  problems, customer-merge bugs, etc.).

### Fixed — contradictory unclear-project first action

- The unclear-project `RECOMMENDED FIRST ACTION` used to say
  "Do NOT write code yet. Clarify the project shape first" +
  "Wait for their answer before proposing any concrete next
  step" — which directly contradicted the new HOW TO APPROACH
  rule that tells the agent to do a structured read-through
  on low confidence. Agents were ignoring the "wait for the
  user" instruction and inspecting anyway (the right
  behavior). New wording codifies that:
  > Do not write code yet. Infer the project shape first.
  > - Perform a structured read-through of the repository
  >   (README, main files, routing, configs) to infer the
  >   system on your own.
  > - Read any generated docs and the user's project
  >   description for additional signal.
  > - Only ask the user for clarification after this
  >   inspection, and only for specific gaps that cannot be
  >   determined from the codebase.
- Other six first-action branches (Full-stack, Smart contract,
  Mobile, Web3 dApp, Rust, Go) and the generic catch-all are
  unchanged.

### Validated against

Three real local repos where the prior prompt was producing
shallow or generic responses:

- **mentorforge** — agent now identifies real risks (Stripe
  DB mismatch, CORS, auth issues) and pushes back on an
  inaccurate project summary instead of accepting it
- **flow-name-service** — agent does deep Cadence + Next.js
  inspection and finds runtime + logic bugs, not just
  documentation gaps
- **norman-handyman-mvp** — agent surfaces production-bug-
  level issues (Stripe redirect, customer merge logic) in
  a 3-way Django/Next.js/Expo split

### Tests

10 new tests in `TestAgentPromptBehaviorRules` plus the
updated unclear-first-action test in `TestAgentLaunchPrompt`
lock the new wording, the three-tier ordering, the priority
rule, the anti-doc language, the placement contract
(FIRST ACTION → HOW TO APPROACH → WHAT TO PRIORITIZE →
SAFETY), determinism, and the absence of the old
contradictory phrases. 481/481 tests green.

## [0.11.0] — 2026-04-27

**Discovered-notes preservation.** `context-kit adopt` gains a
`--notes TEXT` flag so findings from a prior dry-run / inspection
pass survive the user's later `--write` run with a refined
`--project-summary` or `--next-task`. Closes the trust-loss case
where probe findings vanish when the user iterates on the inputs.

### Added — `--notes TEXT`

- **Flag-only** — never prompted. When omitted, no notes section
  appears anywhere in adopt's output (no empty headings).
- **Surfaces in four places when provided:**
  - **Agent Launch Prompt** — new `DISCOVERED NOTES / CONTEXT`
    section between `USER CONTEXT` and `PRIMARY DETECTION`.
  - **`docs/BUILD_PLAN.md`** — new `## Discovered notes` section
    between the project summary and the tech-stack block.
  - **`00-START-NEXT-SESSION.md`** — new `## Discovered notes`
    section between "What's next" and "How to start the session".
  - **`CLAUDE.md`** — new `### Discovered notes` heading inside
    the adopt-managed block (between "What the user told adopt"
    and "Rule for this session"). Re-running `--write` refreshes
    the notes in place; no stacking.
- **Multi-line notes preserve line breaks.** First line carries
  the bullet prefix; subsequent lines indent two spaces so the
  result reads naturally in plain text and renders as a markdown
  list continuation. Whitespace-only notes collapse to "no notes".

### Why this exists

The v0.10.0 release flow exposed a trust-loss case: a user runs
`adopt --html` in probe mode, discovers something useful (port
collision, deployment quirk, demo credentials, etc.), then later
runs `--write` with a sharper `--project-summary` — and their
findings vanish from the generated docs. `--notes` is the
escape hatch: hand adopt the discoveries explicitly and they
ride along into every doc the agent will read.

### Internals

- **`AdoptionInputs`** gains `notes: str = ""` (default-safe
  for every existing test that constructs it positionally).
- **`collect_inputs`** gains a `notes=None` kwarg; never prompts
  for it. Empty / whitespace-only notes collapse to `""`.
- **`_format_notes_block`** centralizes the bullet + indent
  rendering; reused by all four surfaces so the format stays
  identical across the prompt and the three docs.
- **`derive_agent_launch_prompt`** threads notes through; when
  empty, the entire DISCOVERED NOTES section is omitted (no
  empty heading, no prelude line).
- **`run_adopt`** reads `getattr(args, "notes", None)` so legacy
  test namespaces without the attribute still work.

### Tests

13 new tests in `TestDiscoveredNotes` cover the argparse layer,
the dry-run Agent Launch Prompt path, all three written docs,
the omission case (no `--notes` => no section anywhere), the
multi-line preservation contract, and the re-run refresh-in-place
guarantee for the CLAUDE.md managed block. 471/471 tests green.

## [0.10.0] — 2026-04-27

**Agent Launch Prompt milestone.** Adopt now produces a single
copy-paste block the user can hand to any AI coding agent
(Claude Code, Cursor, Aider, etc.) as the first message of a
session. The prompt is self-contained — project shape, primary
detection, recommended first action, safety rules, and the
user's own framing — so the agent starts safely without a
question loop. Two new flags (`--project-summary`, `--next-task`)
make the whole adopt run non-interactive when paired.

### Added — Agent Launch Prompt (Phase 6.1)

- **`derive_agent_launch_prompt`** assembles a
  ``AgentLaunchPrompt`` from the same data the Adopt Summary
  already uses. Output is a single text block with five fixed
  sections: WHAT THIS PROJECT APPEARS TO BE, USER CONTEXT,
  PRIMARY DETECTION, WORKSPACE / PROJECT STRUCTURE, RECOMMENDED
  FIRST ACTION, and SAFETY INSTRUCTIONS. Confidence mirrors
  ``StackReality.confidence``.
- **`_agent_first_action_for`** picks a project-type-aware first
  action from 7 branches: Full-stack, Smart contract, Mobile app
  suite, Web3 dApp, Rust workspace, Go project, plus a generic
  catch-all. Each branch is 3–4 read-only inspection steps.
- **Surfaces in three places after `--write`:**
  ``00-START-NEXT-SESSION.md`` under "Agent Launch Prompt",
  ``CLAUDE.md`` under "Agent launch prompt", and
  ``docs/BUILD_PLAN.md`` under "Agent launch prompt". Same prompt
  block in each, embedded in the adopt-managed marker so re-runs
  refresh in place.
- **Surfaces before `--write`:** the dry-run preview prints the
  prompt above the plan so the user can copy it without
  generating any files.

### Added — Non-interactive flags

- **`--project-summary TEXT`** answers "In one sentence, what
  is this project?" up-front; skips the matching prompt.
- **`--next-task TEXT`** answers "What should the next AI
  session help with?" up-front; skips the matching prompt.
- **Both flags can be combined** for a fully non-interactive
  adopt run — useful for CI, scripted dogfood, and recorded
  demos. Without them, adopt prompts each question exactly once.
- **Answers are reused verbatim everywhere**: the Agent Launch
  Prompt USER CONTEXT block, BUILD_PLAN.md "What this project
  is" + "Next milestone", PROJECT_WHAT_IT_IS.md "In one
  paragraph", 00-START-NEXT-SESSION.md "What's next", and
  CLAUDE.md "What the user told adopt". The user types each
  answer once, regardless of where it surfaces.

### Fixed — Split-monorepo Full-stack project type

- **Repos with `backend/` + `frontend/` (or `server/` + `web/`,
  `api/` + `client/`) at root now classify as "Full-stack web
  app".** Closes the contract-concierge gap where adopt fell back
  to "Unclear project type" despite a clean split. Rule names
  the parts in the reason text and stays Medium confidence.
- **Recognized roles:** ``_BACKEND_ROLES = ("backend", "server",
  "api")`` and ``_FRONTEND_ROLES = ("frontend", "web",
  "client")``. Matching is case-sensitive and depth-1.

### Fixed — Pre-`--write` and missing-doc behavior

- **Agent Launch Prompt now works before `--write`.** Earlier
  versions assumed the generated docs existed when rendering
  the recommended first action. The prompt now self-fences
  with explicit safety language: "If they do not exist yet,
  read README, package/manifests, and inspect the detected
  project structure first."
- **Placeholder soft-framing in three doc generators.** When
  adopt cannot infer a value (``Why it exists``, ``Who it's
  for``, etc.), it writes ``[adopt: please describe]`` and
  every doc that mentions the placeholder now adds: "Do not
  block read-only inspection on these placeholders. Proceed
  with the recommended first action if it's safe and read-only."
  Prevents agents from stalling on unfilled context.

### Changed — Post-write CLI footer

- **Replaces the prior generic next-steps line** with an
  Agent-Launch-Prompt-centric next step: "Next step: paste the
  Agent Launch Prompt above into your AI coding agent (Claude
  Code, Cursor, Aider, etc.). The same prompt is saved in
  00-START-NEXT-SESSION.md under 'Agent Launch Prompt' for
  later reference."
- **`generate_claude_md_fresh` "Read this first"** now leads
  with the Agent Launch Prompt as the canonical session opener,
  followed by pointers to BUILD_PLAN / PROJECT_WHAT_IT_IS / the
  start-here doc as deeper context.

### UX wording

- **USER CONTEXT header** in the Agent Launch Prompt is now
  "(provided during adopt)" — accurate whether the answers
  came from the interactive prompts or the new flags.
- **Adopt's two prompts** sharpened to "In one sentence, what
  is this project?" and "What should the next AI session help
  with?" Each fires exactly once per run.

## [0.9.0] — 2026-04-27

**Ecosystem coverage milestone.** Five fixes driven by the
SESSION_011 dogfood batch on real public repos: Rust support,
Go support, a Smart contract project type, mixed-root JS/Python
correction, and a React Native vs Next.js disambiguation. The
v0.8.0 decision-layer machinery (Adopt Summary, Stack reality,
Project type, Suggested next actions) carries the new behavior
without UI changes; the failure taxonomy is unchanged.

### Added — Rust ecosystem (Phase 5.2)

- **Root `Cargo.toml` is now a recognized primary signal.**
  ``_detect_in_dir`` returns ``"rust"`` when Cargo.toml is the
  only manifest at root. JS / Python take precedence when
  multiple manifests coexist, so existing mixed cases keep
  going through Phase 5.1's source-dominance check.
- **Workspace child label "Rust crate"** fires on Cargo.toml
  or `.rs` files in a depth-2 workspace child. Surfaces
  cleanly in the Adopt Summary's Structure block.
- **Phase 4.5 inferred-primary** maps "Rust crate" workspace
  signals to a "Rust workspace" primary when root has no
  manifest — handles the rare Cargo workspace without a
  root Cargo.toml.
- **Project type "Rust workspace / library"** in Phase 4.2.
  Fires only when Rust is the actual primary identity (root
  Cargo.toml or unknown-root + Rust workspace inference);
  JS / Python primary repos that happen to have auxiliary
  Rust tooling (e.g. next.js's `crates/turbopack-*`) fall
  through to the JS / Python rules.

### Added — Go ecosystem (Phase 5.3)

- **Root `go.mod` is now a recognized primary signal.**
  ``_detect_in_dir`` returns ``"go"`` when go.mod is at root.
- **Project type "Go project"** in Phase 4.2 when
  `stack.language == "go"`. Reason text names the manifest
  evidence. (No workspace-child Go rule — Go workspaces are
  uncommon enough to defer.)

### Added — Smart contract project type (Phase 5.4)

- **New Phase 4.2 rule between Web3 dApp and Full-stack web
  app.** Fires when any of:
  - workspace child is labeled Solidity, OR
  - any depth-1 directory has ≥ 10 `.sol` files, OR
  - root contains a smart-contract framework config
    (`hardhat.config.{js,ts,mjs,cjs}`, `foundry.toml`,
    `truffle-config.js`, `brownie-config.yaml`).
  Result: project type = "Smart contract project". Closes the
  openzeppelin-contracts mislabel (was "JavaScript app/tooling
  project" through v0.8.0).
- **`derive_project_type` signature** now takes optional
  ``failures=None``. The smart-contract rule reads failure
  examples to detect root configs that aren't tracked in
  ``stack.signals``. ``run_adopt`` passes ``prelim_failures``;
  callers without failures still work with the default.

### Added — Mixed-root source dominance (Phase 5.1)

- **When both root JavaScript and root Python manifests are
  present, walk depth-2 source evidence and pick the dominant
  side.** v0 always picked JavaScript, which produced the
  django/django dogfood failure where 198 .py files in
  `django/` + 163 in `tests/` silently lost to a tooling-only
  root `package.json`.
- **Resolution rules:** Python wins when py-count ≥ 5 AND ≥ 3×
  js-count; symmetric for JavaScript; otherwise inconclusive
  (falls back to JS, preserves v0 default for non-audited
  callers).
- **Stack reality confidence is capped at Medium** for any
  mixed-root case regardless of which side won. Mixed-root
  setups rarely behave as a single stack in practice, and a
  "High confidence" label there would be confidently wrong.
- Notes explicitly say: "Mixed root manifests (package.json +
  pyproject.toml); Python primary based on source dominance
  (1229 .py files vs 12 .js/.ts/.tsx/.jsx files at depth ≤ 2)."

### Changed — React Native vs Next.js disambiguation (Phase 5.5)

- **Phase 3 `_classify_workspace_child` adds a "React Native /
  mobile framework" label** that fires BEFORE the Next.js rule
  when mobile signals are present:
  - `metro.config.{js,ts,mjs,cjs}`
  - `react-native.config.{js,ts,mjs,cjs}`
  - `Podfile` (CocoaPods, iOS)
  - `Gemfile` (Ruby, common in RN iOS)
  - `.swift` or `.kt` source files
  Closes the react-native dogfood failure where
  `packages/react-native` (a mobile framework with
  `metro.config.js + .tsx`) was labeled "Next.js / React web
  app", which then cascaded into a "Full-stack web app"
  project-type misfire via Phase 4.2 Rule 2.
- **Project type "Mobile app suite" generalized** to fire on
  Flutter OR React Native workspace signals. Reason text
  adapts to name which kind ("Flutter / Dart" / "React Native"
  / "Flutter and React Native") and lists up to 3 mobile
  children.

### Tests

- 424 passing (was 327 in 0.7.0, 407 in 0.8.0). +17 in
  TestMixedRootDominance + TestEcosystemCoverage covering all
  five spec'd fixture shapes (django-shape,
  ripgrep-shape, kubernetes-shape, openzeppelin-shape,
  react-native-shape) plus regression sanity checks
  (transformers, fns-monorepo) and the JS+Rust-aux guard
  fixture (next.js-shape).

### Dogfood validation

Real-world before/after on the seven repos in
`/Users/donkeyking/development/context-kit-dogfood-repos/`:

  django:                JS app/tooling High  -> Python app/tooling Medium
  react-native:          Full-stack web app   -> Mobile app suite
  openzeppelin-contracts: JavaScript app/tooling -> Smart contract project
  ripgrep:               Unclear / Low        -> Rust workspace / library
  kubernetes:            Unclear / Low        -> Go project (High)
  transformers:          unchanged (Python / High)
  fns-monorepo:          unchanged (Web3 dApp)

Beneficial side effects on existing dogfood repos:
aave-v3-core, solidity-template, and v3-core all flipped from
"JavaScript app/tooling project" to "Smart contract project"
since they have hardhat config or heavy `contracts/` dirs.

next.js correctly stays "Unclear project type" — it's a real
JS+Rust hybrid that doesn't fit any clean category, and the
Rust-rule guard prevents misclassifying it as a Rust project.

## [0.8.0] — 2026-04-27

**`context-kit adopt` gains a depth-2 workspace walk plus a
derived decision layer.** The output now leads with a single
"Adopt Summary" card (Type / Structure / Reality / Next actions)
that names the concrete project's content instead of emitting
raw signals. Built across twelve incremental ships in Phases
1–4.6; see `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md`
for the per-ship breakdown.

Detection logic and the failure taxonomy from 0.7.0 are
unchanged. Classification gains exactly one new behavior:
workspace-aware primary inference for Flutter / Solidity /
Next.js when the root scan returns "unknown".

### Added — Workspace awareness

- **Depth-2 workspace child detection.** New
  `StackProfile.workspace_children` field populated by
  `scan_workspace_children`, which walks one level deeper into
  known workspace containers (`apps/`, `packages/`,
  `services/`, `crates/`, `members/`, `workspaces/`). Each
  child carries its name (e.g. `apps/forge`), manifest files,
  notable extensions, and a hint string. Pure data — no
  classification change.
- **Workspace-aware deduplication.** When `workspace_children`
  covers a container, the same container no longer renders
  again in "Needs clarification" — eliminates the
  contradictory dual-counts the v0.7 dogfood revealed
  (`apps/` showing 29 .sol in the depth-1 summary while
  individual children showed different per-child counts).
- **Visible directory titles in the HTML report.** Both
  Workspace children cards and the renamed "Needs
  clarification" cards now lead with a block-level
  `<span class="dir-name">` (bold monospace, accent color)
  followed by manifests / extensions on a dim meta line
  beneath. Trivial children (only `package.json`, no notable
  extensions) render as a non-collapsible row instead of an
  empty-body `<details>` element.

### Added — Decision layer

- **Adopt Summary** (`AdoptSummary` dataclass +
  `derive_adopt_summary`). Single consolidated card at the top
  of every output — CLI dry-run, HTML report, BUILD_PLAN.md,
  and the CLAUDE managed block — with four sub-sections:
  - **Type** — derived project-type label (see below).
  - **Structure** — per-child stack labels.
  - **Reality** — `assessment` (Single-stack / Mixed
    workspace / Unclear), `confidence` (High / Medium / Low),
    and a one-sentence `why`.
  - **Next actions** — up to 5 prioritized actions (see
    below).
- **Stack reality assessment** (`StackReality` dataclass +
  `derive_stack_reality`). Five-rule cascade over the existing
  primary classification, parts table, workspace stack
  summary, and failure labels. Confidence drops from High to
  Medium for single-stack projects when MISLEADING_CLASSIFICATION
  or ROOT_SIGNAL_OVERRIDE fires (e.g. Hardhat repos with root
  `package.json` plus `hardhat.config.ts`).
- **Project type inference** (`ProjectType` dataclass +
  `derive_project_type`). Six deterministic rules over Phase 3
  workspace signals: Web3 dApp, Full-stack web app, Mobile
  app suite, JavaScript app/tooling project, Python app/tooling
  project, Unclear project type. Each carries a confidence
  band and a one-line reason.
- **Workspace stack summary** (Phase 3 — pre-consolidation).
  Per-child stack labels derived from a small fixed signal set:
  `app.config.*` → Expo, `foundry.toml`/`.sol` → Solidity,
  `pubspec.yaml`/`.dart` → Flutter, `next.config.*` or
  `package.json + .tsx`/`.jsx` → Next.js. The standalone
  section was folded into Adopt Summary's Structure block in
  Phase 4.4.

### Added — Suggested next actions

- **Context-aware suggested actions** (`SuggestedAction`
  dataclass + `derive_suggested_actions`). Up to 5 actions
  per run, each with a title, reason, and priority
  (high / medium / low). Deduped by title; sorted high-first.
  Reasons name the concrete things the user should inspect:
  - **Web3 dApp** → "Confirm smart-contract + frontend
    boundary" (high). Reason names the Solidity child(ren)
    and the Next.js child(ren) by path.
  - **Mobile app suite** → "Confirm mobile app structure"
    (high). Reason names up to two Flutter children.
  - **Full-stack web app** → "Confirm backend/frontend
    boundaries" (medium). Reason calls out API ownership,
    local dev startup order, and deployment boundaries.
  - **Needs-clarification dirs** → "Classify unrecognized
    directories" (medium). Reason lists up to 3 dir names
    verbatim; with more than 3, uses count + first 3.
  - **MONOREPO_DEPTH_LIMIT** → "Review workspace children"
    (high). Reason names up to two child workspaces.
  - **Stack reality Low confidence** → "Clarify project shape
    before coding" (high).
  - **IDEMPOTENCY_RISK** → "Preserve existing context docs
    before writing" (high).
  - **Catch-all (clean project)** → "Run adopt with --write
    when ready" (low).

### Added — Detection improvements

- **Workspace-aware primary inference**
  (`StackProfile.inferred_primary` +
  `_infer_primary_from_workspace`). When the root scan returns
  "unknown" but every non-trivial workspace child shares the
  same Phase 3 stack label, adopt promotes that into the
  primary detection. Three target labels (Flutter / Dart,
  Solidity / EVM smart contracts, Next.js / React); JS / Python
  root detections are never overridden. The detection line
  reads `<label> (inferred from workspace children)` so the
  source of evidence is visible.

### Changed — UX polish

- **"Unknown but present" → "Needs clarification".** New
  description copy: "These directories contain files adopt
  can see, but it cannot confidently identify their role yet.
  Confirm what they are before making changes." Applied
  consistently to CLI / HTML / BUILD_PLAN / CLAUDE.
- **"Detected issues" → "Diagnostic signals".** New
  description copy: "Signals from adopt's internal failure
  taxonomy. These help explain classification limits and
  review priorities; they do not mean the project is broken."
  Failure type names (MONOREPO_DEPTH_LIMIT,
  UNRECOGNIZED_ECOSYSTEM, etc.) unchanged.
- **Top-level section consolidation.** The four standalone
  Phase 3 / 4.x sections (Workspace stack, Stack reality,
  Project type, Suggested next actions) are folded into a
  single Adopt Summary card. Standalone helper builders are
  retained in the module for a future debug toggle but no
  longer assembled into the rendered output.
- **MONOREPO_DEPTH_LIMIT description** updated to reflect that
  child workspaces are surfaced (and labeled in the workspace
  stack summary) but not yet part of primary classification.
  Label, severity, and surface_area unchanged.

### Tests

- 407 passing (was 327 in 0.7.0). +80 across new test classes
  for workspace child data model, rendering, dedup, name
  visibility, workspace stack summary, stack reality, project
  type, suggested actions, Adopt Summary consolidation,
  workspace-aware detection, diagnostic signals wording, and
  context-aware actions.

### Dogfood validation

Verified end-to-end against the eight repos in
`/Users/donkeyking/development/context-kit-dogfood-repos/`:

  fns-monorepo                      → Web3 dApp           (3 actions)
  turborepo-next-django-starter     → Full-stack web app  (3 actions)
  flutter-monorepo-example          → Mobile app suite    (3 actions)
  expo-monorepo-example             → Unclear project type (1 action)
  solidity-template                 → JavaScript app/tooling project
  aave-v3-core                      → JavaScript app/tooling project
  openzeppelin-contracts            → JavaScript app/tooling project
  v3-core                           → JavaScript app/tooling project

Known acknowledged limitation: Hardhat-style Solidity repos
without an `apps/` workspace currently classify as JavaScript
app/tooling project (Phase 4.2 Rule 4 fires, spec-faithful).
Tracked for a future Phase 4.x refinement.

## [0.7.0] — 2026-04-26

**`context-kit adopt` — the existing-project entry point.** A new
top-level command that retrofits context-kit's docs layer onto
projects that already have code, without ever touching source files.
Designed and shipped in seven incremental releases (v0 through v0.3
plus several cross-cutting passes), each driven by real-world
dogfood against `/development/` projects and a curated set of
cloned open-source repos.

The full design lives in `docs/proposals/SESSION_009_ADOPT.md`.
What's in this release:

### Added — `context-kit adopt`

- **Minimal `context-kit adopt [PATH]` command (v0).** Detects basic
  stack from manifest files (JavaScript via `package.json`, Python
  via `manage.py` / `requirements.txt` / `pyproject.toml`, unknown
  otherwise). Prompts the user for two beginner-friendly things —
  what the project is and what they're trying to do next — then
  generates the load-bearing docs (`docs/BUILD_PLAN.md`,
  `docs/PROJECT_WHAT_IT_IS.md`, `00-START-NEXT-SESSION.md`) and
  either creates a fresh `CLAUDE.md` or augments an existing one.
  Dry-run by default; `--write` to apply. Source code is never
  modified — the strict invariant is that bytes outside the
  generated/augmented docs never change.
- **Split-monorepo detection (v0.1).** When the repo root has no
  manifest, adopt walks one level deep into seven recognized
  subdirs (`backend`, `frontend`, `web`, `mobile`, `api`, `client`,
  `server`) and reports a per-subdir stack. Backend wins as primary
  (the AI session's default frame anchors where the domain logic
  lives). Generators render a per-subdir bullet table in
  BUILD_PLAN.md and the CLAUDE.md augment block. Verified against
  `focus-flow`, `dealflowtracker`, `contract-concierge`,
  `norman-handyman-mvp` (three-part split: backend + web + mobile),
  and `ai-content-studio` (single-stack root, regression-tested to
  confirm root still wins over a same-named subdir).
- **Visibility-first fallback scan (v0.2 — the load-bearing
  principle).** "Never allow real project structure to be
  invisible." After classification, adopt walks every non-hidden
  depth-1 child directory and reports what classification missed:
  manifest-shaped files found, source-extension counts, one example
  path per extension, and a "this looks like X" hint when a domain
  extension (`.sol`, `.clar`, `.cdc`, `.move`, `.dart`, `.rs`,
  `.go`, `.swift`, `.kt`, `.ipynb`, etc.) is dominant. The
  fallback fires *unconditionally* — even on classified projects —
  so an AI session reading the generated docs can't be unaware of
  (say) a `contracts/` directory full of `.sol` files in a project
  the classifier called "JavaScript". Per-ecosystem detectors are
  deliberately deferred — visibility-first sidesteps the
  per-ecosystem-treadmill that would otherwise be required to keep
  up with new languages and frameworks.
- **Idempotency safety on every generated file (v0.2.x).** All four
  target docs (`BUILD_PLAN.md`, `PROJECT_WHAT_IT_IS.md`,
  `00-START-NEXT-SESSION.md`, `CLAUDE.md`) wrap their content in
  `<!-- context-kit:adopt:start --> / :end -->` markers. Re-running
  `--write` refreshes content inside the markers and preserves
  user edits outside them. If an existing file has *no* markers
  (i.e. user wrote it by hand), adopt now reports `would skip`
  instead of clobbering — the load-bearing fix from the
  unified-donkey-betz dogfood, where v0.2 would have silently
  overwritten a hand-written `00-START-NEXT-SESSION.md`.
- **Pattern-based noise filter (v0.2.x).** Replaces exact-name
  filtering with a pattern check that catches `venv_ml/`,
  `venv-prod/`, `.venv-old/`, etc. while preserving lookalike
  names like `envelope/` and `envoy/`.
- **Lightweight subsystem hints (v0.2.x — not full framework
  detection).** Three pattern hints derived from manifest filename
  combinations: `package.json + vite.config.* + tailwind.config.*`
  → "Vite + Tailwind web app", `package.json + app.config.*` →
  "Expo / React Native mobile app", `requirements.txt` in a subdir
  → "Python subsystem with isolated dependencies". Surface in the
  CLI dryrun, BUILD_PLAN markdown, and as a yellow `hint-badge` in
  the always-visible HTML summary line. Restored visual contrast
  on Python+JS-only monorepos that previously had zero `verify
  with user` notes firing.
- **Data-only directory grouping (v0.2.x).** Subdirs with files
  but no recognized source extensions (configs, JSON dumps,
  documentation, etc.) collapse into a single "Data / content /
  non-code directories" footer in the markdown docs and a single
  collapsible block in the HTML report. Unified-donkey-betz had
  35 of these — v0.2 rendered them as a wall of identical cards;
  v0.2.x renders them as one entry.
- **`--html` static review report (§21).** A new opt-in flag that
  writes a single self-contained HTML report (inline CSS, vanilla
  JS only, no external assets, no server, no HTTP endpoints).
  Default destination is `<tempdir>/contextkit-adopt-report-<short-hash-of-cwd>.html`
  so re-runs in the same project overwrite in place and the
  source tree stays untouched. `--html-out PATH` overrides the
  default; `--no-browser` suppresses `webbrowser.open()` for tests
  and CI. The report has six sections — header, detection summary,
  classified parts (when applicable), unknown-but-present (the
  main visual focus, with collapsible per-subdir items), the plan
  with expand-to-preview per file, and a suggested next-action
  CTA. CLI dry-run output is byte-equal with or without `--html`
  modulo a single trailing "HTML report: <path>" line.
- **Failure taxonomy (v0.2.x → v0.3 — 10 fixed labels).** Every
  detected issue during an adopt run is classified into one of a
  closed set of `FailureRecord` types with severity (low/medium/
  high), surface_area (classification/visibility/safety/UX),
  description, detected_in (subdir or root), and example. Pure
  additive metadata — does NOT change classification, plan, or
  any written output. Surfaces in both the CLI compact summary
  and a "Detected issues" section in the HTML report. The 10
  types: `ROOT_SIGNAL_OVERRIDE`, `UNRECOGNIZED_ECOSYSTEM`,
  `SILENT_SUBDIR_DROP`, `WRAPPER_DIRECTORY_INVISIBILITY`,
  `NOISE_DIRECTORY_POLLUTION`, `IDEMPOTENCY_RISK`,
  `MISLEADING_CLASSIFICATION`, `MISSING_FRAMEWORK_DETECTION`,
  `STRUCTURE_UNDERREPRESENTED`, `MONOREPO_DEPTH_LIMIT`. Detectors
  are deterministic rules over `StackProfile + plan`. No dynamic
  taxonomy generation, no AI-generated labels.
- **`MONOREPO_DEPTH_LIMIT` failure label (v0.3).** Fires when a
  workspace-container subdir (`apps`, `packages`, `services`,
  `crates`, `members`, `workspaces`) holds substantial content but
  adopt's depth-1 scan can't enter the child projects. Closes the
  v0.2.x gap exposed by the cloned dogfood batch, where 3 of 5
  Turborepo-style projects (`expo-monorepo-example`, `fns-monorepo`,
  `turborepo-next-django-starter`) emitted zero failure records
  despite obvious depth-2 invisibility. Designed in §22 of the
  proposal.
- **Root-level `UNRECOGNIZED_ECOSYSTEM` extension (v0.3).** The
  existing detector now also fires for ecosystem manifests at the
  project root (e.g. `melos.yaml` in a Dart Flutter monorepo,
  `foundry.toml` in a Solidity template). Previously the loop
  only checked subdir manifests.

### Added — bundled context-kit skill

- The bundled `cli/_skills/context-kit/SKILL.md` ships into every
  generated project at `.claude/skills/context-kit/SKILL.md` and
  was extended to mention `context-kit adopt` for projects that
  aren't context-kit yet — so an agent loaded into a non-adopted
  project knows the retrofit entry point exists.

### Changed

- README's CLI reference adds the `adopt` row, a full options
  table for adopt (positional `PATH`, `--write`, `--html`,
  `--html-out PATH`, `--no-browser`), and a paragraph framing
  adopt as the entry point for *existing* projects.
- `cli/bootstrap.py`'s `RUNTIME_COPY` now includes `cli/adopt.py`
  so generated projects can run `python3 ./context_kit.py adopt .`
  from their own copy without `ImportError`.
- `cli/server.py` and the bootstrap pipeline are unchanged. No
  existing CLI command's behavior changes.

### Tests

- 327 passing (was 239 in 0.6.1). +88 for `adopt` across 13 test
  classes covering: per-bucket classification (5), split-layout
  subdir scanning (6), plan/dry-run/write (3), CLAUDE.md augment +
  idempotency + BUILD_PLAN rule (3), CLI entry-point (3),
  visibility-first scan + extension reporting + cap (13), pattern-
  based noise filtering (4), manifest-hint detection (5),
  idempotency safety + skip-when-no-markers (5), data-only
  grouping + render hygiene (3), manifest-hint surfacing in CLI/
  Markdown/HTML (3), `--html` static report including XSS-safety
  on user input + the `--no-browser` contract (12 + 1 pure-render),
  failure taxonomy required cases + edge cases + record-shape
  invariants + render coverage (13), and the v0.3 monorepo-depth
  + root-ecosystem detectors (8).

### Dogfood validation (read-only, --html --no-browser)

Run during 0.7.0 prep. All five `/development/`-resident
fixtures plus five cloned `context-kit-dogfood-repos/` clones
correctly classified or honestly labeled:

  /development/dbao-studio              → ROOT_SIGNAL_OVERRIDE etc.
  /development/donkey_betz_world        → SILENT_SUBDIR_DROP for mobile/
  /development/clarity-timelock         → WRAPPER_DIRECTORY_INVISIBILITY
  /development/unified-donkey-betz      → IDEMPOTENCY_RISK + NOISE_POLLUTION
  /development/apps/tornado-core        → MISLEADING_CLASSIFICATION + UNRECOGNIZED_ECOSYSTEM (root foundry.toml)

  context-kit-dogfood-repos/expo-monorepo-example       → MONOREPO_DEPTH_LIMIT × 2
  context-kit-dogfood-repos/flutter-monorepo-example    → MONOREPO_DEPTH_LIMIT + UNRECOGNIZED_ECOSYSTEM × 2
  context-kit-dogfood-repos/fns-monorepo                → MONOREPO_DEPTH_LIMIT (the headline win — was 0 in v0.2.x)
  context-kit-dogfood-repos/solidity-template           → MISLEADING_CLASSIFICATION + UNRECOGNIZED_ECOSYSTEM
  context-kit-dogfood-repos/turborepo-next-django-starter → SILENT_SUBDIR_DROP + MONOREPO_DEPTH_LIMIT

## [0.6.1] — 2026-04-26

**Wizard polish, recovery, and a critical onboarding fix.** Driven
entirely by dogfood testing — most fixes have a real "the user (or
their dog) hit this" story attached. No CLI behavior changes;
existing 0.6.0 projects work unchanged.

### Changed
- **Wizard Step 2 is clearer about what a project name is for.**
  New title ("Where should we create your project?"), new helper text,
  re-framed labels (Project name / Folder name with examples), and a
  gentle inline warning when the user types a generic name like
  "new" / "app" / "test" / "project". The folder field now reads
  "Auto-created from the project name. You usually don't need to
  change this."
- **Wizard Step 3 talks like a friend, not a tech form.** New intro
  ("Just describe your idea like you would to a friend"), reassurance
  that most fields are optional, conversational labels ("What do you
  want to build?", "Who is this for?", "Why do you want this?", "Not
  sure about tech? Skip this."), and the medication-reminder
  dogfood case as the example.
- **Wizard Step 5 (init) now tells the user to open a *new* terminal
  and offers a fallback command.** A beginner reading "run
  context-kit init" in the same terminal that's serving the wizard
  would type into a busy server and see nothing happen. Step 5 now
  reads "Keep this page open. In a new terminal window, run: …" with
  a VS Code menu hint. If the new terminal lost the venv that
  `pip install contextkit-ai` populated, a second copy-able command
  shows `python3 -m context_kit init "<name>"` as the recovery path.
- **Final wizard step (Step 8) now hands the user a strengthened
  first prompt for their AI tool.** "Read CLAUDE.md,
  docs/BUILD_PLAN.md, and docs/*_WHAT_IT_IS.md. Summarize the
  project, confirm the stack, then begin implementing version 1. Do
  not change the stack without asking." Plus a beginner-friendly
  explanation of *why* it matters (without this, the AI may pick a
  different stack and produce code that doesn't fit the plan).
- **`/api/check` reasons now include the resolved folder path.** A
  user whose poll-check fails can see exactly which folder was
  inspected, instead of staring at a generic "not found" message.

### Added
- **Step 3 "Copy AI help prompt" button.** Generates a beginner-
  friendly prompt from the current idea fields ("Not sure yet" for
  empty ones) so a user who's stuck can paste it into ChatGPT,
  Claude, or any AI assistant and get planning help without leaving
  the wizard. Closes with "Do not overwhelm me." to keep the
  response right-sized.
- **`detected_projects` field on `GET /api/state`.** Lists immediate
  child directories of cwd that look like context-kit projects
  (have `00-START-NEXT-SESSION.md`), with which milestone files
  exist (idea.md, start doc, BUILD_PLAN.md) and a suggested wizard
  step. Drives the new fresh-tab recovery card.

### Fixed
- **Wizard polled the wrong project_dir when a user's project name
  changed across sessions.** The folder slug auto-derived from
  appName only fired when the field was empty, so stale localStorage
  from a prior wizard run would stick its old folder slug into the
  init/seed checks. Symptom: `context-kit init "stress test"`
  succeeded, created `./stress-test/`, but the wizard said
  "00-START-NEXT-SESSION.md not found in project_dir" because it was
  polling the old folder. Wizard slugify also now mirrors
  `cli/placeholders._slugify` exactly, including camelCase splits.
- **Wizard lost progress after the local server stopped.** A user
  whose `context-kit start` terminal got closed (or stepped on by a
  dog) would see "Network error: Failed to fetch" with no
  actionable guidance. Now a network failure surfaces a beginner-
  friendly recovery message ("The local context-kit server may have
  stopped. Go back to the terminal running context-kit start. If it
  stopped, run context-kit start again, then refresh this page.").
  On reload, the wizard reconciles localStorage with on-disk state
  via `/api/check`, so a user who already ran `seed` lands on
  Step 8 with a "picking up where you left off" banner instead of
  being asked to re-run a CLI command they've already run.
- **Wizard dropped fresh browser tabs at Step 1.** When the local
  server died and the user restarted it, the CLI helpfully reopened
  the wizard URL — often in a new browser window with empty
  localStorage. The reconciler couldn't help because it depends on
  `state.projectDir`. Bootstrap now calls `/api/state`, sees
  `detected_projects`, and offers a "We found an existing project:
  <name>. Continue from there?" card that jumps straight to the
  right step (8 if seeded, 6 if only scaffolded). Multiple
  candidates show a chooser; none shows the normal Step 1.
- **`CLAUDE.md` template did not enforce `BUILD_PLAN.md`.** Real
  failure observed in dogfood: an agent loaded into a freshly
  seeded project did not read `docs/BUILD_PLAN.md`, picked a
  different tech stack from the one `recommend-stack` had baked
  into the plan, and produced code that didn't fit. Framework-level
  gap. Generated `CLAUDE.md` now opens with a "Read This Before
  Writing Any Code" section carrying the rule "Always read
  `docs/BUILD_PLAN.md` before choosing a stack or writing code. Do
  not deviate unless you explain why and ask." Quick Start lists
  BUILD_PLAN.md as item #1 and the "Where to find things" table
  gains a top row labeled "Source of truth for tech stack and build
  approach". Closes the divergence loophole at the framework level
  so every new project ships with it.

### Tests
- 239 unit tests passing (was 223 in 0.6.0). +16 covering wizard
  Step 2/3/5/8 copy, ai-help prompt template, slug parity with the
  CLI, slugged-subdir polling, failure-reason path inclusion, fresh-
  tab discovery, the recovery message + helper functions, and the
  CLAUDE.md template enforcement.

## [0.6.0] — 2026-04-25

**Beginner-first onboarding.** `context-kit start` is now a guided
wizard that opens in the browser and walks a first-time user from
`pip install` to a Claude-ready project — no prior knowledge of the
CLI required.

Versioning rationale:
- `0.5.0` = non-technical builder *capabilities*
  (`recommend-stack` + `doctor`)
- `0.6.0` = beginner-first *onboarding* (`context-kit start` opens
  a wizard that surfaces those capabilities at the right moments)

The CLI is unchanged for experienced users; the wizard is a guided
wrapper, not a replacement. Already-seeded projects still get the
existing project-view page at `/`.

### Added
- **`context-kit start` is now a beginner wizard.** Open a guided
  onboarding page in the browser that walks a first-time user through:
  naming the project, writing the idea, saving `idea.md`, then running
  `init` / `recommend-stack` (optional) / `seed` / `doctor` / opening
  their AI tool. Each CLI step is shown as a copy-paste command; the
  wizard polls the filesystem to verify it ran before advancing.
  Detection is conservative: in a fresh directory the wizard opens; in
  an already-seeded project the existing project view opens unchanged.
  Wizard state persists in browser localStorage so closing the tab
  doesn't lose progress.
- New JSON endpoints on the local server (used by the wizard, useful
  for tooling): `GET /api/state` (classify cwd as none/scaffold/seeded),
  `POST /api/idea` (write idea.md to a project subdirectory; rejects
  path traversal), `GET /api/check?step=init|seed&project_dir=…`
  (verify CLI step ran).
- Wizard HTML ships as package data at `cli/_static/wizard.html`.
- README leads with `context-kit start` as the beginner entry point;
  CLI quickstart kept below for experienced builders.

### Changed
- `run_start` no longer warns "does not look like a context-kit
  project" when the landing page is the wizard — that warning fired
  on the very first run by a beginner, contradicting the wizard's
  whole purpose. Warning is preserved when the landing page is `/`
  but the directory truly has no project markers.

### Tests
- 223 unit tests passing (was 202 in 0.5.0). +21 for the wizard
  (project-state detection, path safety against 5 attack patterns,
  live-server integration covering every route).

## [0.5.0] — 2026-04-25

**context-kit for non-technical builders.** The full loop from a raw
idea to a Claude-ready project, with environment guardrails:

```
init  →  recommend-stack  →  seed  →  doctor  →  orient
```

| Step | What it does |
|---|---|
| `init` | Creates the project memory structure |
| `recommend-stack` | Helps beginners choose a sane v0 stack from their idea |
| `seed` | Turns the raw idea into Claude-ready context |
| `doctor` | Catches environment/setup blockers before they bite |
| `orient` | Loads the current project context for the AI session |

Two real features ship in this release: `recommend-stack` (Session 7,
beginner stack guidance driven by the medication-reminder use case)
and `doctor` (Session 6, environment diagnostics driven by real
Munchkin App / Expo / Metro friction).

### Added
- `context-kit recommend-stack PATH` — opinionated, deterministic v0
  stack guidance for non-technical builders. Reads the same structured
  idea file as `seed`. 8 MVP rules covering medication-reminders,
  mobile-personal-tracking, business-dashboard, content-website,
  local-automation, web-api, plus two modifier rules
  (privacy-sensitive, simple-mvp). Substring matching, case-insensitive.
  Highest-priority primary + capped "also detected" annotations.
  Default fallback when no rules match. Always exits 0; this is
  advisory. Output: human-readable by default, `--json` for tooling.
  **Seed integration:** when `## Tech stack` is missing from the idea
  file, `seed` calls into this engine and bakes the recommendation
  into `docs/BUILD_PLAN.md` with an attribution note. When
  `## Tech stack` is present, `seed` trusts the user's pick. The
  medication-reminders rule emphasizes accessibility (large tap
  targets, simple language, high contrast, minimal screens) and uses
  practical-not-scary privacy framing. Schema documented at
  `cli/_pattern/IDEA_SCHEMA.md`.
- `context-kit doctor` — read-only environment + setup diagnostics
  with 7 checks: Python version, git availability, context-kit
  project structure, Node.js version (against a `KNOWN_STABLE_NODE_MAJORS`
  range), Expo SDK detection + config check, file-watcher /
  `ulimit -n` pressure (with the EMFILE-from-Metro pattern called out
  as blocking), and inventory freshness. Exits `1` only on blocking
  issues; warnings never affect the exit code. Human + JSON output.
  No file mutations. Bundled into `RUNTIME_COPY` so generated projects
  ship the command standalone. Specific checks driven directly by
  real Munchkin App dogfood friction (EMFILE under Metro, Expo Go
  SDK mismatches, `expo-cli` deprecation drift) — see
  `docs/handoffs/SESSION_006_DOCTOR.md`.

### Changed
- README leads with the 5-command loop and "for non-technical
  builders" framing, replacing the prior 3-command shape (which
  predates `recommend-stack` and `doctor`).
- IDEA_SCHEMA explicitly notes `## Tech stack` is optional;
  `recommend-stack` will fill it in via `seed` if omitted.
- Bundled Claude Code skill points at the new commands at the right
  moments (suggest `recommend-stack` when stack is unclear; suggest
  `doctor` when environment friction is suspected).

### Tests
- 202 unit tests passing (was 127 in 0.4.2). +35 for `recommend-stack`,
  +40 for `doctor`.

## [0.4.2] — 2026-04-25

First public release with the full `init` / `seed` / `orient` loop.
0.4.1 (which shipped to PyPI without `seed`) is immutable, so this
release adds `seed` plus the supporting init-template change as a
minor version bump.

### Added
- `context-kit seed PATH` — turn a structured markdown idea file into
  project context. Populates 5 files (`*_WHAT_IT_IS.md` TL;DR,
  `00-START-NEXT-SESSION.md` first milestone, the bootstrap handoff,
  `docs/topics/product.md`, and a structured `docs/BUILD_PLAN.md`)
  using managed-block markers (`<!-- context-kit:seed:start -->` /
  `:end -->`) so human content outside the markers is preserved
  forever. Deterministic, no LLM. Tolerant of natural heading
  variations; unrecognized headings preserved under "Other notes" in
  BUILD_PLAN.md. Supports `--force`, `--dry-run`. Idempotent re-runs.
  Schema documented at `cli/_pattern/IDEA_SCHEMA.md` (ships into
  every generated project's `docs/docs-pattern/`).

### Changed
- Init template now writes `state: scaffold` frontmatter at the top of
  `00-START-NEXT-SESSION.md`. Seed reads this to know whether the
  start-here is safe to populate (and updates it to `state: seeded`
  on success). Replaces fragile string matching with an explicit
  contract.

## [0.4.1] — 2026-04-25

First version actually published to PyPI (as `contextkit-ai`).
Shipped wheel-installability + the orient/skill/hotpath/inventory
features. Did **not** include `seed` — that arrived in 0.4.2.

### Changed
- **PyPI distribution name is `contextkit-ai`** (not `context-kit`).
  PyPI rejected the unsuffixed `context-kit` name as too similar to
  an existing project, so the distribution was renamed before first
  publish. The CLI command (`context-kit`), the GitHub repo
  (`clwest/context-kit`), and the importable Python module
  (`context_kit`) are unchanged. Only the install command differs:
  `pip install contextkit-ai` then `context-kit init "My App"`.

### Added (originally targeted for 0.4.0; first publish ships in 0.4.1)
- **Wheel-installable.** `pip install contextkit-ai` now works end-to-end
  for non-editable installs. Starter assets, the 8 guide docs, the
  reference templates, and the bundled Claude Code skill have been
  moved inside the `cli` package as `cli/_starter/`, `cli/_pattern/`,
  and `cli/_skills/`, and they ship as `package_data`. Bootstrap
  reads them via `importlib.resources` — same code path for editable
  installs and wheel installs.
- `context-kit orient` — prints the project's assembled session-start
  context (start-here doc, two-doc anchor preview, latest handoff,
  pattern pointers) so an agent or returning human reads from a single
  authoritative path instead of guessing which file to open first.
- Claude Code skill at `skills/context-kit/SKILL.md`, copied into every
  generated project at `.claude/skills/context-kit/SKILL.md`. An agent
  loads the skill, runs `orient`, and follows the priority order — no
  human prompt required to bootstrap a new session.
- `context-kit hotpath` — read-only file-size dashboard. Lists the
  largest files in a project and warns when any single file exceeds
  50 KB or the top 10 sum exceeds 200 KB (both tunable). Prefers
  `git ls-files` when inside a git repo, falls back to a recursive
  walk (with sensible ignores). Inspired by Damian Tedrow's "hot
  path" observation that file size is a strong proxy for whether a
  region of code will fit comfortably in an AI session's context.
- `context-kit inventory` — runtime inventory generator with
  `--write` / `--check` / `--json` modes. Writes only inside HTML
  comment markers (`<!-- context-kit:inventory:start -->` /
  `:end -->`) and preserves all human content outside them. Counts
  CLI subcommands, cli/ modules, top-level guide docs, docs files,
  handoffs, templates, starter and scaffold files, test files,
  test-method count, skill files, git-tracked file count, and a
  hot-path summary, plus extracts package metadata from
  `pyproject.toml`. `--check` is CI-friendly (exits 1 on drift).
  Closes the dogfood loop opened in the initial release: the repo's
  own inventory is now half auto-generated.

## [0.3.0] — 2026-04-21

First public release.

### Added
- `context-kit init <NAME>` — scaffold an AI-friendly project with the
  docs-pattern framework: narrative + runtime anchors, drift verifier,
  session handoffs, and AI/human collaboration conventions.
- `context-kit start` — localhost onboarding server that shows the
  first-session checklist and auto-discovers key files in the project.
- 8 guide docs distilled from ~1,100 AI-assisted build sessions over
  ~18 months (`01_two_doc_anchor.md` through `08_collaboration_roles.md`).
- Reference templates for the two-doc anchor, session handoffs, and
  drift verifier (under `templates/`).
- Starter tree with placeholder substitution: `{{APP}}`, `{{APP_SLUG}}`,
  `{{APP_UPPER}}`, `{{APP_TITLE}}`, `{{DATE}}`, `{{YEAR}}`.
- Optional Python scaffold via `--with-scaffold`: drift verifier
  (`doc_claim_verification.py`) and docs index builder
  (`build_docs_index.py`).
- `pyproject.toml` with the `context-kit` console script.
- MIT `LICENSE`.
- GitHub Actions CI across Python 3.9, 3.10, 3.11, and 3.12.
- `unittest` test suite (49 tests) covering placeholder derivation,
  end-to-end bootstrap, and the live onboarding server.
- `CONTRIBUTING.md` with development setup and PR expectations.

### Known limitations
- Wheel distribution (`pip install context-kit` from a built wheel)
  currently ships without the starter tree and guide docs. Use editable
  installs (`pip install -e .`) for now. Proper package-data packaging
  is planned for a future release.
