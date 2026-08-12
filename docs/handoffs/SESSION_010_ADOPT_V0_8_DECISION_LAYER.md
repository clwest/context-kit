---
title: "Session 010 — adopt v0.8.0 decision layer (Phases 1–4.6)"
date: 2026-04-27
status: built-locally + pushed to origin/main; not released to PyPI
---

# Session 010 — adopt v0.8.0 decision layer

This session built the v0.8.0 "decision layer" on top of the v0.7.0
adopt foundation — twelve incremental ships that turn `adopt`'s
output from raw signals into a single read-once "what is this
project, what's the reality, what should I do" report. All ships
are render/derivation only; v0.7's detection logic and failure
taxonomy are unchanged.

The full design lives in `docs/proposals/SESSION_009_ADOPT.md`
sections that flagged Phase-2 follow-ups (workspace walking,
framework detection inside manifests). This session executed the
workspace-walking item and added a derived "decision layer"
(Stack reality, Project type, Suggested next actions, Adopt
Summary, workspace-aware detection, diagnostic-signals copy
softening, context-aware actions) on top.

## What shipped (in commit order, oldest first)

### Phase 1 — depth-2 workspace child detection (data model only) — `47a91eb`

- New `WorkspaceChild` dataclass on `StackProfile`
  (`workspace_children: list[WorkspaceChild]`).
- New `scan_workspace_children(repo)` walker — depth-2 only, only
  enters known workspace containers (`apps/`, `packages/`,
  `services/`, `crates/`, `members/`, `workspaces/`), reuses
  `_scan_subdir_contents` for manifests + extension counts.
- Each child has `name = "<container>/<child>"`, `manifest_files`,
  `notable_extensions`, `hint` (prefers `_manifest_hint`, falls
  back to dominant DOMAIN_HINTS extension note).
- Wired into `detect_stack` at all three return sites; pure
  additive — no classification or rendering changes yet.
- Tests: 10 new in `TestWorkspaceChildren` (fns/turborepo/flutter
  fixtures + 7 guards).

### Phase 2a — render workspace children — `9182989`

- CLI dry-run `Workspace children (depth-2):` block.
- HTML report `<section>` with collapsible `<details class="unc">`
  per child (reuses unknown-but-present styling).
- BUILD_PLAN.md `### Workspace children (depth-2)` short list
  (names + hints only per "do not overwhelm" constraint).
- All three sections silent when no workspace children.

### Phase 2b — dedup the container double-render — `f6079b1`

- Workspace containers (`apps/`, `packages/`, ...) were rendering
  in both Unknown-but-present (capped, aggregated counts) AND
  Workspace children (per-child counts). Counts didn't always
  agree — eroded trust.
- New `_workspace_covered_containers(stack)` helper. Filters
  covered containers from both signal + data-only partition lists.
- Section header now carries the count: `Workspace children (N)`.
- HTML trivial children (only `package.json`, no extensions)
  render as a non-collapsible `<div class="unc unc-trivial">`.
- HTML body no longer repeats the hint already in the summary
  badge.
- `MONOREPO_DEPTH_LIMIT` description rewritten: "Child workspaces
  are surfaced (and labeled in the workspace stack summary) but
  not yet part of primary classification."

### Phase 2c — workspace child name visibility — `5568fa3`

- HTML restructure: each workspace child card now leads with the
  child name as a block-level `<span class="dir-name">` (bold,
  larger, accent color) on its own line, followed by manifests/
  extensions on a dim meta line beneath.
- New CSS `.dir-head` / `.dir-name` / `.dir-meta` (then renamed
  from `.wsc-*` in Phase 2d).
- `generate_claude_block` now includes a compact `### Workspace
  children (N)` block inside the adopt-managed markers (was only
  in BUILD_PLAN.md before).

### Phase 2d — show unknown directory titles in HTML — `63ad158`

- Apply the `dir-head` / `dir-name` / `dir-meta` layout to
  Unknown-but-present cards too (was inheriting the small grey
  `<code class="dirname">` styling that blended with the meta
  text).
- Renamed CSS class set `.wsc-*` → `.dir-*` since both card types
  now share the treatment. Bumped name styling to 1.05rem / weight
  700 / monospace / accent color.

### Phase 3 — workspace stack summary — `84df9bc`

- New `_classify_workspace_child(c) -> Optional[str]` helper with
  four obvious signals (Expo / Solidity / Flutter / Next.js).
- New `_workspace_stack_pairs(stack)` returns `(child_name, label)`
  pairs for children with a label.
- Three render helpers (CLI block, markdown, HTML inline section)
  surface a `Workspace stack` block in CLI / HTML / BUILD_PLAN /
  CLAUDE.

### Phase 4.1 — Stack reality check + "Needs clarification" rename — `2f4b45c`

- New `StackReality` dataclass with `assessment` / `confidence` /
  `why` / `primary` / `workspace_signals` fields.
- `derive_stack_reality(stack, failures)` — five-rule cascade:
  Unknown / Mixed-workspace / Mixed-parts / Single-stack-medium
  (when ROOT_SIGNAL_OVERRIDE or MISLEADING_CLASSIFICATION fires)
  / Single-stack-high.
- "Unknown but present" renamed to "Needs clarification" across
  CLI / HTML / BUILD_PLAN / CLAUDE with softer description copy
  ("…Confirm what they are before making changes.").
- `run_adopt` now does a two-pass `analyze_failures` so reality
  can be derived BEFORE plan_files (IDEMPOTENCY_RISK is
  plan-dependent and re-derived after).

### Phase 4.2 — project type inference — `729cc05`

- New `ProjectType` dataclass + `derive_project_type(stack,
  reality)` with six deterministic rules (Web3 dApp / Full-stack
  web app / Mobile app suite / JavaScript app/tooling / Python
  app/tooling / Unclear catch-all).
- Surfaces in all four output paths via a new `Project type`
  section.

### Phase 4.3 — suggested next actions — `3e232e0`

- New `SuggestedAction` dataclass + `derive_suggested_actions(
  stack, reality, project_type, failures)` with seven rules.
- Output deduped by title, sorted by priority (high→medium→low),
  capped at 5.
- `run_adopt` now does a two-pass `plan_files` so IDEMPOTENCY_RISK
  (plan-dependent) can inform actions before the final plan is
  built.

### Phase 4.4 — Adopt Summary consolidation — `a78492d`

- New `AdoptSummary` dataclass + `derive_adopt_summary(stack,
  reality, project_type, actions)` pure aggregation.
- Single "Adopt Summary" card with four sub-sections (Type /
  Structure / Reality / Next actions) replaces the four
  standalone Phase 3 / 4.1 / 4.2 / 4.3 sections in CLI / HTML /
  BUILD_PLAN / CLAUDE. Visual flow improvement after dogfood
  showed the four cards stacking fragmented the page.
- Standalone section helpers kept in the module for a future
  debug toggle but no longer assembled into the output.

### Phase 4.5 — workspace-aware detection — `52e68d9`

- New `StackProfile.inferred_primary: Optional[str]` field.
- New `_infer_primary_from_workspace(children)` helper. Fires
  only when `stack.language == "unknown"` AND every non-trivial
  child shares the same Phase 3 label AND that label maps to one
  of three Phase 4.5 targets (Flutter / Solidity / Next.js).
- `_stack_summary` returns `"<label> (inferred from workspace
  children)"` when inferred.
- `derive_stack_reality` adds an explicit inferred-primary path
  returning `Single-stack project / Medium`.
- Resolves the "Detection: Unknown but Project type: Mobile app
  suite" contradiction on flutter-monorepo-example.

### Phase 4.5 follow-up — Detection card label fix — `5adb8b4`

- The HTML `<h2>Detection</h2>` card had a separate hardcoded
  label-builder branch that read `stack.language` directly,
  silently disagreeing with the rest of the report on
  flutter-monorepo. Updated to use `inferred_primary` in the
  unknown branch and flip the card border `card-warn` →
  `card-ok`.

### Phase 4.5.1 — soften diagnostic-signals wording — `3c51dbf`

- Section title `Detected issues` → `Diagnostic signals` in CLI +
  HTML.
- Description copy replaced with: "Signals from adopt's internal
  failure taxonomy. These help explain classification limits and
  review priorities; they do not mean the project is broken."
- Failure type names (MONOREPO_DEPTH_LIMIT, etc.) unchanged.

### Phase 4.6 — context-aware suggested actions — `efaef43`

- Rewrote `derive_suggested_actions` to emit context-specific
  titles + reasons that name concrete workspace children and
  unclassified dir paths instead of generic prose.
- Three titles renamed:
  - `Confirm contract workspace` → `Confirm smart-contract +
    frontend boundary`
  - `Inspect child workspaces` → `Review workspace children`
  - `Review unclassified directories` → `Classify unrecognized
    directories`
- One new rule: Mobile app suite → `Confirm mobile app structure`
  (high) with Flutter children named.
- Two refined-reason rules with unchanged titles: Full-stack web
  app (now mentions API ownership / dev startup / deployment),
  needs-clarification scaling (1–3 names verbatim, >3 uses count
  + first 3).
- Phase 4.3 invariants preserved (max 5, dedupe by title, sort
  high-first).

## Where state actually is right now

- **Latest commits on `origin/main`** (all v0.8.0 ships pushed):
  ```
  efaef43 feat(adopt): make suggested actions context aware
  3c51dbf fix(adopt): soften diagnostic signals wording
  5adb8b4 fix(adopt): inferred primary surfaces in HTML detection card
  52e68d9 feat(adopt): infer detection from workspace children
  a78492d feat(adopt): consolidate top-level summary into one card
  3e232e0 feat(adopt): suggest next actions
  729cc05 feat(adopt): infer project type summary
  2f4b45c feat(adopt): add stack reality check
  84df9bc feat(adopt): summarize workspace child stacks
  63ad158 fix(adopt): show unknown directory titles in html report
  5568fa3 fix(adopt): clarify workspace child names in report
  f6079b1 fix(adopt): deduplicate workspace child rendering
  9182989 feat(adopt): render depth-2 workspace children
  47a91eb feat(adopt): add depth-2 workspace child detection (data model only)
  ```
  Note: spec for this handoff said "branch state: 2 commits ahead
  before push if still true" — the two commits in question
  (`3c51dbf` + `efaef43`) were already pushed before this
  handoff was written, so the branch is now at parity with
  `origin/main` modulo this handoff commit itself.
- **Tests:** **407/407 passing.**
- **Inventory:** regenerated as part of this handoff.
- **PyPI:** still on **0.7.0**. v0.8.0 is **not released yet** —
  no version bump in `pyproject.toml`, no `dist/` artifacts, no
  tag, no GitHub release.
- **CHANGELOG.md:** `[0.7.0]` is the latest entry. v0.8.0
  changelog block is **not written yet**.

## What v0.8.0 ships (one-line)

`context-kit adopt` gains a depth-2 workspace walk plus a derived
decision layer (Adopt Summary card with Type / Structure / Reality
/ Next actions, all named to the concrete project's content).
Detection logic and failure taxonomy are unchanged; classification
gains exactly one new behavior — workspace-aware primary
inference for the Flutter / Solidity / Next.js cases when root
detection is unknown.

## Live dogfood snapshot (per `~/dev/context-kit-dogfood-repos/`)

| repo | project type | next-action count |
|---|---|---|
| example-web3-monorepo | Web3 dApp | 3 |
| turborepo-next-django-starter | Full-stack web app | 3 |
| flutter-monorepo-example | Mobile app suite | 3 |
| expo-monorepo-example | Unclear project type | 1 |
| solidity-template | JavaScript app/tooling project | 1 |
| aave-v3-core | JavaScript app/tooling project | 1 |
| openzeppelin-contracts | JavaScript app/tooling project | 1 |
| v3-core | JavaScript app/tooling project | 1 |

Known acknowledged limitation: Hardhat-style Solidity repos
without an `apps/` workspace still classify as "JavaScript
app/tooling project" because Phase 4.2 Rule 4 fires (single root
JS, no parts, no workspace children). Spec-faithful but a
candidate for a future Phase 4.x refinement.

## Next steps (in order)

1. **Push this handoff commit.** The feature commits
   (`3c51dbf` + `efaef43`) are already on `origin/main`; this
   handoff is the only outstanding push.
2. **Final dogfood / visual review** of the 8 HTML reports to
   spot any regression or copy issue introduced by the Phase 4.x
   chain. Reports live in `/var/folders/.../T/contextkit-adopt-
   report-*.html` after `python3 context_kit.py adopt
   <repo> --html --no-browser`.
3. **Decide whether v0.8.0 is release-ready.** Rough checklist:
   - Tests green (already true).
   - Dogfood reports look right end-to-end.
   - No regression on plain (non-monorepo) repos.
   - CHANGELOG block written (see step 4).
4. **Release prep if yes:**
   - Bump `pyproject.toml` version `0.7.0 → 0.8.0`.
   - Write `[0.8.0]` block in `CHANGELOG.md` mirroring this
     handoff's "What shipped" list.
   - Build wheel + sdist; `twine check`.
   - Publish to PyPI; tag `v0.8.0`; push tag; create GitHub
     release attached to the tag (mirror the v0.7.0 process from
     SESSION_009).

## Open design questions (deferred to v0.9+)

- **Single-Solidity-repo classification.** Hardhat / Foundry repos
  without an `apps/` workspace fall into the JS app/tooling
  bucket. A Phase 4.x rule could check root for `hardhat.config.*`
  / `foundry.toml` and override the project type.
- **Expo workspace inference.** Phase 4.5 deliberately leaves
  Expo out of the inferred-primary set (only Flutter / Solidity
  / Next.js). expo-monorepo-example currently shows "Unclear
  project type" as a result. Worth revisiting once Phase 3 has
  a stronger Expo signal than just `app.config.*`.
- **Framework detection inside manifests** (proposal §15 #5).
  Still deferred. Pairs naturally with the workspace-walking
  work now that depth-2 is in place.
- **`[adopt: please describe]` doctor check** (proposal §15 #6).
  Still deferred.
- **Wizard branch for adopt** (proposal §15 #7). Still deferred.

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | this file (`docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md`) |
| Adopt code | `cli/adopt.py` |
| Adopt tests | `tests/test_adopt.py` |
| v0.7.0 design (still authoritative for the foundation) | `docs/proposals/SESSION_009_ADOPT.md` |
| Recent commits | `git log --oneline efaef43~14..HEAD` |
| Dogfood repos | `~/dev/context-kit-dogfood-repos/` |

## AI Notes

The "consolidate then refine" pattern worked well across Phase 4:
each Phase 4.x ship added one named derivation (reality, project
type, actions, summary), the dogfood revealed each new card
fragmenting the visual flow, and Phase 4.4 collapsed them into a
single card. Doing it in that order gave each derivation its own
testable surface area before the consolidation rewrote the
renderers.

The two-pass plan / failures dance in `run_adopt` is now load-
bearing for IDEMPOTENCY_RISK to surface in actions. Worth
preserving the comment that explains why; otherwise a future
refactor could try to fold it back into one pass and lose the
dependency.

Hardhat-style single-Solidity-repo misclassification is the
biggest remaining pebble in the v0.8 shoe. The user explicitly
acknowledged it as spec-faithful per the Phase 4.2 rules, so
not a blocker, but worth fixing before v0.9.
