# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` — what last session shipped
> 4. `docs/proposals/SESSION_009_ADOPT.md` — full adopt design (deep reference)
>
> When any other doc disagrees with the above, the above wins.

---

## Where state actually is right now

**Version 0.7.0 is published.** Code is on `origin/main`, the
package is live on PyPI, and the `v0.7.0` tag is created and pushed.
Only the GitHub release remains.

- **Local commit:** `ff5b87c docs(handoff): session 009 adopt and
  0.7.0 release state` — matches `origin/main`.
- **Tests:** **328/328 passing**.
- **Inventory:** current.
- **Build:** clean. `dist/contextkit_ai-0.7.0-py3-none-any.whl` +
  `.tar.gz` exist locally.
- **`twine check`:** PASSED for both artifacts.
- **Fresh-venv install smoke (local wheel):** passed end-to-end.
- **PyPI:** **0.7.0 PUBLISHED.** `pip install
  contextkit-ai==0.7.0` in a fresh venv works; `context-kit adopt
  --help` runs from the PyPI install.
- **Git tag:** **`v0.7.0` created and pushed to `origin`**
  (annotated, message "v0.7.0 — adopt existing projects",
  points at `ff5b87c`).
- **GitHub release:** still **NOT created** — the only remaining
  step.

## What 0.7.0 ships

Top-line: `context-kit adopt` is the new public command for
retrofitting context-kit's docs layer onto existing projects
without touching source code. Built across seven incremental
ships (v0 through v0.3) plus this release prep.

Headline features in the 0.7.0 release notes:

- **`context-kit adopt [PATH]`** — minimal three-language
  detection, two-prompt user input, four-file generation
  (BUILD_PLAN.md, PROJECT_WHAT_IT_IS.md, 00-START-NEXT-SESSION.md,
  fresh-or-augment CLAUDE.md). Dry-run by default; `--write` to
  apply.
- **Split-monorepo detection** — when root has no manifest, walks
  one level into seven recognized subdir names; backend wins as
  primary.
- **Visibility-first unclassified scan** — the load-bearing
  principle. Never silently drops a depth-1 child directory;
  always reports manifests + source extensions + example paths +
  domain-extension hints.
- **Idempotency safety** — all four generated files use adopt
  markers. Re-runs preserve user edits; existing files without
  markers are skipped (not clobbered).
- **Pattern-based noise filter** — catches `venv_ml/`,
  `venv-prod/`, etc. while preserving `envelope/`.
- **Lightweight subsystem hints** — Vite + Tailwind, Expo +
  React Native, Python isolated subsystem.
- **Data-only directory grouping** — collapses N "no recognized
  source extensions" cards into one block.
- **`--html` static review report** — single self-contained file,
  inline CSS + vanilla JS, no server. Default writes to system
  temp dir.
- **Failure taxonomy** — 10 fixed labels (ROOT_SIGNAL_OVERRIDE,
  UNRECOGNIZED_ECOSYSTEM, SILENT_SUBDIR_DROP,
  WRAPPER_DIRECTORY_INVISIBILITY, NOISE_DIRECTORY_POLLUTION,
  IDEMPOTENCY_RISK, MISLEADING_CLASSIFICATION,
  MISSING_FRAMEWORK_DETECTION, STRUCTURE_UNDERREPRESENTED,
  MONOREPO_DEPTH_LIMIT). Pure additive metadata. CLI compact
  summary + HTML "Detected issues" section.
- **MONOREPO_DEPTH_LIMIT (v0.3)** — labels Turborepo / pnpm-
  workspace shapes where child projects live below adopt's
  current scan depth. Closes the v0.2.x gap exposed by the
  cloned dogfood batch.

Full per-ship breakdown lives in
`docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md`. Full design lives
in `docs/proposals/SESSION_009_ADOPT.md`.

## Next steps (in order)

1. **GitHub release** for `v0.7.0` — the only remaining release
   step. Body can come from the `[0.7.0]` section of
   `CHANGELOG.md` verbatim, or be summarized. Tag already
   exists on `origin`, so the release just needs to attach to it.

After the release lands, the next session is free to pick up
v0.8.0 work (see "Open design questions" below).

## Open design questions (deferred, NOT for this release)

- **`apps/<name>/` workspace walking** (proposal §15 #3) — the
  natural follow-on to v0.3's MONOREPO_DEPTH_LIMIT. v0.3
  *labels* the gap; v0.8.0 should *fix* it by walking depth-2
  inside the seven workspace containers.
- **Framework detection inside manifests** (proposal §15 #5) —
  classify `manage.py` as Django, `next.config.*` as Next.js,
  etc. Pairs naturally with the workspace-walking work.
- **`[adopt: please describe]` doctor check** (proposal §15 #6).
- **Wizard branch for adopt** (proposal §15 #7).

These are post-0.7.0 work. Don't sneak them into the release.

## Where to look when you come back

| What | Where |
|---|---|
| Latest handoff | `docs/handoffs/SESSION_009_ADOPT_AND_0_7_0.md` |
| Adopt code | `cli/adopt.py` (~1,800 lines) |
| Adopt tests | `tests/test_adopt.py` (~1,300 lines, 88 tests) |
| Full adopt design | `docs/proposals/SESSION_009_ADOPT.md` |
| Release notes | `CHANGELOG.md` `[0.7.0]` section |
| Recent commits | `git log --oneline -10` |
| Wheel + sdist | `dist/contextkit_ai-0.7.0.{whl,tar.gz}` |

## Load-bearing reminder

`docs/CONTEXT_KIT_INVENTORY.md` is auto-generated from
`context-kit inventory --write`. Re-run it whenever code/test/doc
counts change so the runtime anchor stays accurate. CI (and the
project's own discipline) treats it as the source of truth — when
narrative docs disagree with the inventory, the inventory wins.
