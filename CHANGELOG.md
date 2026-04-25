# Changelog

All notable changes to context-kit are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
