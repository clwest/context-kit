# Changelog

All notable changes to context-kit are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
