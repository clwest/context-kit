---
title: "Session 009 — context-kit adopt (v0 → v0.3) + 0.7.0 release prep"
date: 2026-04-26
status: built-locally — unpushed, unpublished, untagged
---

# Session 009 — `context-kit adopt` (v0 → v0.3) + 0.7.0 release prep

`context-kit adopt` is the new top-level command for retrofitting
context-kit's docs layer onto an existing project that already has
code. Designed and shipped in seven incremental releases driven by
real-world dogfood, plus the 0.7.0 release prep. Source code is
never modified — adopt is read-only against `src/` / `app/` /
`lib/` / etc. The strict invariant is that bytes outside the
generated/augmented docs never change.

The full design lives in `docs/proposals/SESSION_009_ADOPT.md`
(22 sections plus 3 appendices, ~2,000 lines). This handoff is
the readable summary. When the proposal disagrees with what's
actually in `cli/adopt.py`, the code wins — but most of the gaps
are sections explicitly marked "deferred" or "v0.3 backlog".

## What shipped (in commit order)

### v0 — minimal `context-kit adopt` (cea6327)

The smallest credible surface area:

- New `context-kit adopt [PATH]` command on the existing dispatcher.
- Three-language detection from manifest filename presence:
  - `package.json` → `javascript`
  - `manage.py` / `requirements.txt` / `pyproject.toml` →
    `python`
  - Anything else → `unknown`. Mixed JS+Python at root returns
    `javascript` with an honest "v0 doesn't multi-stack yet" note.
- Two interactive prompts collected before generation: "What is this
  project?" and "What are you trying to do next?"
- Four files generated: `docs/BUILD_PLAN.md`,
  `docs/PROJECT_WHAT_IT_IS.md`, `00-START-NEXT-SESSION.md`, plus
  either a fresh `CLAUDE.md` or an augment-only block on an
  existing one.
- Dry-run by default; `--write` to apply.
- Augment-mode on existing CLAUDE.md is byte-safe: content outside
  `<!-- context-kit:adopt:start --> / :end -->` markers is preserved
  verbatim. Idempotent across re-runs.
- 14 focused tests across 4 classes.

### v0.1 — split-monorepo detection (3f45087)

Real `/development/` projects almost never have manifests at root —
they have `backend/` + `frontend/` (and sometimes `mobile/`). v0.1
falls back to a depth-1 walk into seven recognized subdirs
(`backend`, `frontend`, `web`, `mobile`, `api`, `client`, `server`)
when the root scan returns empty.

- New `StackProfile.parts: dict[str, str]` carries per-subdir
  classifications (e.g. `{"backend": "python", "frontend": "javascript"}`).
- Backend wins as primary by convention (the AI session's default
  frame anchors where the domain logic lives).
- Generators render a per-subdir bullet table in BUILD_PLAN.md and
  the CLAUDE.md augment block when `parts` is non-empty.
- Verified against `focus-flow`, `dealflowtracker`,
  `contract-concierge`, `norman-handyman-mvp` (three-part split:
  backend + web + mobile), and `ai-content-studio` (single-stack
  root, regression-tested to confirm root still wins over a
  same-named subdir).
- +6 tests (20 total).

### v0.2 — visibility-first unclassified scan (7a5ddb8)

The load-bearing principle that emerged from the
clarity-timelock + flow-name-service dogfood:

> **Never allow real project structure to be invisible.**

After classification, adopt walks every non-hidden depth-1 child
directory and reports what classification missed:

- Manifest-shaped files found at depth 1 of each subdir
  (`Clarinet.toml`, `pubspec.yaml`, `foundry.toml`, `flow.json`,
  `Cargo.toml`, etc. — anything matching
  `_is_manifest_like` filtered against a deny list of lock files).
- Source-extension counts via a depth-2 walk capped at 200 files
  per subdir. Domain extensions (`.sol`, `.clar`, `.cdc`, `.move`,
  `.dart`, `.rs`, `.go`, `.swift`, `.kt`, `.scala`, `.ex`, `.elm`,
  `.cairo`, `.fc`, `.ipynb`) report at any count ≥1 because one
  `.sol` file is meaningful. Generic extensions (`.py`, `.ts`,
  `.tsx`, `.js`, `.jsx`) report only above
  `MIN_SOURCE_FILES_TO_REPORT = 3` to filter noise.
- An example path per extension so the user / AI can one-keystroke
  navigate to a real file.
- A "this looks like X; verify with user" hint when the dominant
  extension is in `DOMAIN_HINTS`.

The fallback fires *unconditionally* — even on classified projects —
because its purpose is to surface anything classification missed,
never to replace classification. Per-ecosystem detectors are
deliberately deferred: visibility-first sidesteps the per-ecosystem
treadmill that would otherwise be required to keep up with new
languages and frameworks.

- +13 tests (33 total).
- Three new dogfood fixtures logged in the proposal: dbao-studio
  (§17), donkey_betz_world (§18), tornado-core (§20).

### v0.2.x — safety + clarity polish (8abde7d)

The unified-donkey-betz dogfood (90+ subdir Django monorepo)
exposed four concrete issues that needed fixing before adopt was
safe to use on real projects:

1. **Idempotency** (the load-bearing fix). v0.2 had `BUILD_PLAN.md`,
   `PROJECT_WHAT_IT_IS.md`, and `00-START-NEXT-SESSION.md` as
   create-only — re-running `--write` would silently overwrite
   user edits. unified-donkey-betz already had a hand-written
   `00-START-NEXT-SESSION.md` that v0.2 would have clobbered.
   v0.2.x wraps all three in adopt markers (same pattern as
   CLAUDE.md augment block) and adds a `skip` plan kind that
   refuses to touch existing files without our markers. The
   `_apply_managed_block` helper now strips any prelude (like the
   START doc's YAML frontmatter) from the new content before
   splicing, so frontmatter doesn't double on re-runs.
2. **Pattern-based noise filter.** Replaces exact-name `NOISE_DIRS`
   with `_is_noise_dir(name)` that catches `venv_ml/`, `venv-prod/`,
   `.venv-old/`, etc. while preserving lookalike names like
   `envelope/` and `envoy/`.
3. **Lightweight subsystem hints.** Three pattern hints from
   manifest filename combinations: `package.json + vite.config.* +
   tailwind.config.*` → "Vite + Tailwind web app", `package.json
   + app.config.*` → "Expo / React Native mobile app",
   `requirements.txt` in a subdir → "Python subsystem with
   isolated dependencies". Restored visual contrast on Python+JS-
   only monorepos.
4. **Data-only directory grouping.** Subdirs with files but no
   recognized source extensions collapse into a single "Data /
   content / non-code directories" footer. unified-donkey-betz
   went from 35 identical "no recognized extensions" cards to
   one collapsible block.

- +20 tests (53 total).
- Confirmed safe on unified-donkey-betz: `would skip
  00-START-NEXT-SESSION.md (exists without adopt markers)`.

### `--html` static review report (2d350df) — proposal §21

Long terminal output became painful on real projects. New
`--html` flag writes a single self-contained HTML report to a
temp file and auto-opens it in the browser:

- Single self-contained file: inline CSS, vanilla JS only
  (collapse via `<details>`, copy buttons via tiny handler).
  Same constraint as `cli/_static/wizard.html`. Zero external
  assets, zero dependencies, zero server.
- Default destination
  `<tempdir>/contextkit-adopt-report-<short-hash-of-cwd>.html`.
  Same project re-run overwrites in place; different projects
  don't collide. Source tree untouched.
- `--html-out PATH` for explicit destination (also implies
  `--html`).
- `--no-browser` for tests / headless / CI.
- Six sections: header, detection summary card, classified parts
  card, unknown-but-present (the main visual focus, with
  collapsible per-subdir items), plan with expand-to-preview per
  file, suggested next-action CTA.
- CLI dry-run stdout is byte-equal with or without `--html` modulo
  a single trailing "HTML report: <path>" line.
- +14 tests (67 total).

### Failure taxonomy (046dcfc)

Turns recurring patterns observed across dogfood reports into
reusable, structured signals:

- New `FailureRecord` dataclass: `failure_type`, `severity`
  (low/medium/high), `surface_area`
  (classification/visibility/safety/UX), `description`,
  `detected_in` (subdir or root), `example`.
- `FAILURE_TYPES` frozenset of 9 fixed labels:
  `ROOT_SIGNAL_OVERRIDE`, `UNRECOGNIZED_ECOSYSTEM`,
  `SILENT_SUBDIR_DROP`, `WRAPPER_DIRECTORY_INVISIBILITY`,
  `NOISE_DIRECTORY_POLLUTION`, `IDEMPOTENCY_RISK`,
  `MISLEADING_CLASSIFICATION`, `MISSING_FRAMEWORK_DETECTION`,
  `STRUCTURE_UNDERREPRESENTED`.
- New `analyze_failures(repo, stack, plan)` pure function over
  `StackProfile + plan`. Deterministic rules — no I/O, no AI
  calls, no dynamic taxonomy. Multiple failures per project
  allowed; same failure_type fires at most once per `detected_in`
  target.
- HTML report gains a "Detected issues" section between unknown-
  but-present and the plan, with severity color badges
  (`sev-high` red, `sev-medium` amber, `sev-low` grey).
- CLI dry-run gets a compact "Detected issues (N): ..." summary
  at the end (silent on clean projects).
- +13 tests (80 total).

### v0.3 — `MONOREPO_DEPTH_LIMIT` (199e095) — proposal §22

The first batch of `context-kit-dogfood-repos` clones (5
open-source projects: expo-monorepo-example,
flutter-monorepo-example, fns-monorepo, solidity-template,
turborepo-next-django-starter) exposed that 3 of 5 monorepo
shapes emitted ZERO failure records under v0.2.x. Most damning:
fns-monorepo with 29 `.sol` files plus `apps/forge/foundry.toml`
fired no labels because the depth-1 scan can't enter `apps/`.

Two additions:

1. **New `MONOREPO_DEPTH_LIMIT` failure label** (taxonomy goes
   from 9 to 10). Fires when a workspace-container subdir
   (`apps`, `packages`, `services`, `crates`, `members`,
   `workspaces`) holds substantial content but adopt's depth-1
   scan can't enter the child projects. Detection: ≥10 source
   files via the depth-2 walk OR an example path containing
   ≥2 separators (proxy for "content lives in a child subdir").
   Fires at most once per workspace container — no per-card
   explosion on a 20-app Turborepo.
2. **Root-level `UNRECOGNIZED_ECOSYSTEM` extension.** The
   existing detector loop only checked subdir manifests; v0.3
   also scans `repo.iterdir()` for filenames in
   `_ECOSYSTEM_MANIFESTS` (now including `melos.yaml` for the
   Dart Flutter monorepo case). Both detectors are independent
   — root-level and subdir hits can fire on the same project.

- +8 tests (88 total for adopt).
- All five cloned dogfood repos now produce meaningful labels.
  Headline: fns-monorepo went from 0 failures to 1
  (MONOREPO_DEPTH_LIMIT for `apps/`).

### 0.7.0 release prep (a0ae625)

Closes the audit's release blockers:

- `cli/bootstrap.py` `RUNTIME_COPY` now includes `cli/adopt.py`
  so generated projects can run `python3 ./context_kit.py adopt .`
  from their own copy without `ImportError`.
- New regression test
  `test_generated_project_includes_cli_adopt` asserts both file
  presence and tuple membership (named-by-string so silent
  removal is hard).
- `CHANGELOG.md` `[Unreleased]` block replaced with a
  comprehensive `[0.7.0]` entry covering all seven adopt ships
  plus this prep work and the dogfood validation matrix.
- `README.md` adopt options table gains rows for `--html`,
  `--html-out PATH`, `--no-browser` (only `--write` was
  documented before).
- `cli/_skills/context-kit/SKILL.md` gains a brief "If the
  project ISN'T context-kit yet" footer pointing at
  `context-kit adopt`.
- `pyproject.toml` version `0.6.1 → 0.7.0`.

## Where state actually is right now

- **Local commit:** `a0ae625 chore(release): prepare 0.7.0`
- **Pushed to `origin/main`:** **No.** Local is one commit ahead.
- **Tests:** **328/328 passing.**
- **Inventory:** **current** (regenerated as part of this handoff
  + the prep commit).
- **Build:** clean. `dist/contextkit_ai-0.7.0-py3-none-any.whl`
  + `.tar.gz` exist locally.
- **`twine check`:** PASSED for both artifacts.
- **Fresh-venv install smoke:** passed end-to-end. `pip install`
  the local wheel, `context-kit adopt --help` shows all four
  flags, `context-kit adopt <fixture> --html --no-browser` runs
  to exit 0 against a small JS+Solidity test fixture.
- **PyPI:** **NOT published.** Live PyPI version is still 0.6.1.
- **Git tag:** **NOT created.** No `v0.7.0` tag yet.
- **GitHub release:** **NOT created.**

## Next steps (in order)

1. **`git push origin main`** — single commit (`a0ae625`).
2. **`python3 -m twine upload dist/*`** — uploads
   `contextkit_ai-0.7.0` to PyPI. (Or upload to TestPyPI first
   if you want a dry run.)
3. **Verify fresh install** from PyPI (not the local wheel):
   `pip install contextkit-ai==0.7.0` in a new venv, run
   `context-kit adopt --help` to confirm the install works
   end-to-end against the published artifact.
4. **`git tag -a v0.7.0 -m "..."`** then `git push origin v0.7.0`.
5. **GitHub release** for `v0.7.0` — body can come from the
   CHANGELOG `[0.7.0]` section verbatim, or be summarized.

## Open design questions (deferred to v0.8.0+)

- **`apps/<name>/` workspace walking** (proposal §15 #3). The
  primary unfinished item from the v0.2 backlog and the natural
  follow-on to v0.3's MONOREPO_DEPTH_LIMIT. v0.3 *labels* the gap;
  v0.8 should *fix* it by walking depth-2 inside the seven
  workspace containers and populating per-child entries into
  `StackProfile.parts`. After that ships, MONOREPO_DEPTH_LIMIT
  keeps firing only when a workspace contains content the
  deeper walk itself didn't reach (genuinely deeper-than-2
  layouts).
- **Framework detection inside manifests** (proposal §15 #5).
  Currently adopt classifies as plain "JavaScript" / "Python"
  without naming the framework — even when `manage.py` is
  present (Django) or `next.config.*` is at root (Next.js). One
  small dependency-name lookup per manifest type closes most of
  the visible gap. Pairs naturally with the workspace-walking
  work since each child project would also benefit.
- **`[adopt: please describe]` doctor check** (proposal §15 #6).
  The placeholders adopt leaves in generated docs are the
  contract for "the AI session reading these should ask the
  user." `doctor` learning to grep for them and warning would
  close the loop.
- **Wizard branch for adopt** (proposal §15 #7). The current
  wizard assumes empty cwd. Could add a "fresh tab discovery"
  entry point: when `/api/state` reports the cwd has no init
  markers but `adopt` would detect a usable stack, the wizard
  offers "We found an existing project. Want to adopt it instead
  of starting from scratch?".

## Where to look when you come back

- **Code:** `cli/adopt.py` (single file, ~1,800 lines including
  detector + renderer + failure taxonomy + HTML report).
- **Tests:** `tests/test_adopt.py` (~1,300 lines, 88 tests across
  13 test classes).
- **Design:** `docs/proposals/SESSION_009_ADOPT.md` — sections
  §17, §18, §20 are full per-project fixture write-ups; §19 is
  the visibility-first principle; §21 is the `--html` design;
  §22 is the v0.3 MONOREPO_DEPTH_LIMIT proposal. Appendix C is
  the broader dogfood-fixture inventory.
- **Dogfood projects:** `/development/` for the original five
  (focus-flow, dealflowtracker, contract-concierge,
  norman-handyman-mvp, ai-content-studio) plus the four full
  fixtures (dbao-studio, donkey_betz_world, clarity-timelock,
  unified-donkey-betz, tornado-core under apps/). Five cloned
  open-source projects under
  `/development/context-kit-dogfood-repos/`.

## AI Notes

The seven-ship cadence (each one a single focused commit, scoped
tight, with its own dogfood-driven motivation) worked well for
adopt and is worth keeping for v0.8. Each ship was small enough
to land same-session; the failure taxonomy emerged retroactively
once the patterns were obvious from the dogfood — that's
probably the right order (don't taxonomize before you've seen
the failure modes in real repos).

The visibility-first principle (§19) is the single most important
design decision in adopt. Per-ecosystem detection is a treadmill
the team would lose; "describe what's there, classify what you
can, never silently drop anything" scales to ecosystems we
haven't seen yet.

`MONOREPO_DEPTH_LIMIT` is currently the only label in the taxonomy
that the *fix* (depth-2 walking inside workspace containers) is
known but unshipped. Worth keeping that label even after the fix
ships because not all monorepo shapes follow Turborepo
conventions — a label that explicitly says "we tried but
couldn't reach" stays honest.
