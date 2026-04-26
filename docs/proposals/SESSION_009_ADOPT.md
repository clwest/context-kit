---
title: "Session 009 — adopt (retrofit context-kit onto an existing project)"
date: 2026-04-26
status: partially-shipped
shipped:
  - v0  (cea6327): minimal adopt command
  - v0.1 (3f45087): split-layout detection (depth-1 subdir scan)
deferred:
  - v0.2: deeper-than-1 layouts (apps/<name>/, microservices), confidence scoring, [adopt: please describe] doctor checks, recommend-stack integration, wizard branch
authors: chris@donkeybetz.com, claude (claude-opus-4-7)
---

# Session 009 — `context-kit adopt`

**Status:** v0 + v0.1 shipped; v0.2 designed but not yet
implemented. The full release was deliberately broken into a series
of small validating ships rather than one big "feature complete"
landing — the v0 dogfood exposed split-monorepo as the highest-
value next move (now shipped as v0.1), and the same pattern
will let v0.2 be designed against real evidence rather than guess.

**What's live today:** `context-kit adopt [PATH] [--write]` works
against single-stack root-managed projects (e.g. `ai-content-studio`)
and against `backend/` + `frontend/` style split monorepos with up
to one level of subdirectory depth. See §15 for the v0.2 backlog
and §16 for what each shipped session actually delivered vs. the
original design.

> **Reviewers (now):** §15 (v0.2 backlog) is the live design
> question. §3, §5, and §10 are largely shipped — see the
> "shipped vs. deferred" annotations inline.

---

## 1. Origin

The `init` / `seed` / `recommend-stack` / `doctor` loop assumes an
empty cwd and a human-written `idea.md`. That covers the
"non-technical builder starts something new" case beautifully, but
it's the minority of real users. Most builders coming to context-kit
already have a partly-built project and want the memory layer
wrapped around what they have, not a from-scratch scaffold.

Today the workaround is:

```bash
context-kit init . --force        # works, scaffolds docs
# now you write CLAUDE.md, BUILD_PLAN.md, WHAT_IT_IS.md by hand…
```

Step 2 is where most users bounce. They came to context-kit because
they didn't want to hand-write boilerplate; asking them to fill in
five docs by hand defeats the purpose.

`adopt` closes the loop: point it at an existing repo, it inspects
the manifests + entry-point files, and generates the same docs
`init + seed` would have generated for a from-scratch project — but
populated from observed signals instead of from `idea.md`.

The user gets:

- A working memory layer in 30 seconds, not 30 minutes.
- A `BUILD_PLAN.md` that reflects their *actual* stack, not a
  recommendation that may not match what they already wrote.
- A clear list of `[adopt: please describe]` gaps where the CLI
  couldn't infer something (the "why" of the project, the domain
  glossary, non-obvious decisions). These are honest about the
  limit instead of hallucinating.

## 2. Architecture

`cli/adopt.py` — one module, three layers.

```
┌─────────────────────────────────────────────┐
│  Layer 1: Detectors (read-only)             │
│  Pure functions, no side effects.           │
│  detect_stack(repo_path) -> StackProfile    │
│  detect_topics(repo_path) -> list[Topic]    │
│  detect_existing_ai_docs(repo_path) -> dict │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Layer 2: Generators (pure transforms)      │
│  Take detector output, return file content. │
│  generate_idea_md(stack, readme) -> str     │
│  generate_build_plan(stack) -> str          │
│  generate_what_it_is(stack, readme) -> str  │
│  generate_topics_index(topics) -> list[str] │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Layer 3: Materializer (the only writer)    │
│  Writes inside managed blocks; preserves    │
│  human content; honors --dry-run / --force. │
│  apply(plan, target, dry_run, force) -> int │
└─────────────────────────────────────────────┘
```

This mirrors the `seed` / `inventory` shape. The key invariant:
**only Layer 3 touches disk**, and it always writes through managed
markers so re-running `adopt` is safe.

**Dataclasses:**

- `StackProfile`: `language`, `frameworks: list[str]`, `runtime`,
  `manifest_files: list[Path]`, `confidence: float`,
  `signals: list[str]`, `notes: list[str]`
- `Topic`: `name`, `paths: list[Path]`, `kind`
  (`"backend" | "frontend" | "mobile" | "infra" | "docs"`),
  `description: str | None` (None when CLI can't infer)
- `AdoptionPlan`: list of `(target_path, content, kind)` tuples
  where `kind` is `"create" | "augment" | "skip" | "warn"`

**CLI surface:**

```
context-kit adopt PATH [--write] [--force] [--json] [--quiet]
```

- Default: dry-run report to stdout. No file writes.
- `--write`: actually create the files.
- `--force`: overwrite existing context-kit-generated content
  (still preserves content outside managed markers).
- `--json`: machine-readable output for tooling.
- `--quiet`: only errors.

Exits 0 on successful adoption (or successful dry-run). Exits 1
when the repo is fundamentally un-adoptable (no detectable manifest
of any kind — no package.json, pyproject.toml, etc.). Exits 2 on a
detected ambiguity that needs human resolution (e.g., manifest says
Django *and* Next.js but neither is in a `backend/` or `frontend/`
subdir — likely two projects in one repo, refuse to guess).

## 3. The detection ladder

> **Shipped (v0 + v0.1):** root-first scan with depth-1 fallback
> into seven recognized subdirs (`backend`, `frontend`, `web`,
> `mobile`, `api`, `client`, `server`). No confidence scoring yet
> (binary detection only). Backend wins when picking the primary
> for split repos. Mixed JS+Python at root returns javascript with
> an honest "v0 doesn't multi-stack yet" note. See `cli/adopt.py`
> `detect_stack()` for the live behavior.
>
> **Deferred to v0.2:** the confidence-score table below, deeper-
> than-1 layouts (`apps/<name>/...`, microservice monorepos),
> framework-level detection beyond the four manifest filenames
> (Next.js vs. Vite vs. CRA, Django vs. Flask vs. FastAPI).

Every detector is a pure function returning a `StackProfile` with a
confidence score. We run them all and pick the highest-confidence
non-conflicting set. **This is the section that will get the most
review pushback** — biases here decide whether `adopt` is useful or
embarrassing.

| Signal | Confidence | Yields |
|---|---|---|
| `manage.py` at root | 0.95 | Django |
| `manage.py` + `<name>/settings.py` | 0.99 | Django (named) |
| `pyproject.toml` with `tool.poetry` | 0.85 | Python (Poetry) |
| `pyproject.toml` with `[project]` only | 0.80 | Python (PEP 621) |
| `requirements.txt` only | 0.70 | Python (pip) |
| `Pipfile` | 0.80 | Python (Pipenv) |
| `package.json` with `"next"` dep | 0.95 | Next.js |
| `package.json` with `"react"` + `vite.config.*` | 0.90 | Vite + React |
| `package.json` with `"react-native"` | 0.95 | React Native |
| `package.json` with `"expo"` | 0.95 | Expo |
| `package.json` (no framework signal) | 0.50 | Node.js (generic) |
| `pubspec.yaml` | 0.95 | Flutter |
| `Cargo.toml` | 0.95 | Rust |
| `go.mod` | 0.95 | Go |
| `Gemfile` with Rails gem | 0.95 | Rails |
| `*.xcodeproj` or `Podfile` | 0.85 | iOS native |
| `app/build.gradle` | 0.85 | Android native |
| `docker-compose.yml` | 0.40 (modifier) | Containerized — adds note |
| `Makefile` | 0.20 (modifier) | Has build conventions — read targets |

**Multi-stack handling.** Real-world repos almost always have
multiple manifests. The convention:

- If `backend/` and `frontend/` both exist as siblings → split
  monorepo; report each detected separately and label them by
  subdir. The seed `idea.md` Tech stack section reads
  `Backend: Django · Frontend: React/Vite`.
- If detected stacks are siblings at root with no clear partition
  (e.g., `package.json` AND `manage.py` at root level) → exit 2
  with a "this looks like two projects in one folder, please point
  `adopt` at one of them" message. Better to refuse than guess wrong.

**Lessons baked in from the existing `recommend_stack`:**

- Substring matching is too loose for adoption — manifest parsing
  is exact; we're not guessing from a free-text idea anymore.
- Highest-priority-wins is wrong when multiple stacks coexist;
  multi-stack support is a first-class output, not an edge case.

## 4. Topic detection

Topics map onto `docs/topics/` deep-dive files. We detect them from
directory shape + manifest contents:

| Detection | Topic name | Description (stub) |
|---|---|---|
| `backend/` directory | `backend` | (CLI cannot infer — `[adopt: please describe]`) |
| `frontend/` directory | `frontend` | (CLI cannot infer) |
| `mobile/` directory | `mobile` | (CLI cannot infer) |
| `apps/<name>/` (Django app) | `apps_<name>` | "Django app: $name. Models: $model_count" — model count is mechanical |
| `docker-compose.yml` services | `infrastructure` | "Containerized: services = [list]" |
| `.github/workflows/*.yml` | `ci_cd` | "CI: GitHub Actions. Workflows: [list]" |
| `Makefile` targets | `commands` | Detected target names + first-line comment |

Topics that the CLI cannot describe get a `[adopt: please describe]`
placeholder. The CLAUDE.md "Read This Before Writing Any Code"
section gets a corresponding rule that an agent must surface these
gaps to the user before writing code that touches the topic.

## 5. Managed-block strategy for non-empty repos

> **Shipped (v0):** `CLAUDE.md` augment-only with markers
> `<!-- context-kit:adopt:start --> / :end -->`, idempotent re-run
> (block replaces in place, doesn't stack), source bytes never
> change outside markers. `BUILD_PLAN.md` / `PROJECT_WHAT_IT_IS.md` /
> `00-START-NEXT-SESSION.md` are create-only in v0 — re-running
> over an existing one would currently overwrite. Idempotent
> create-or-augment for those three is on the v0.2 list.
>
> **Deferred to v0.2:** managed-block markers inside the three
> create-only files so re-runs preserve human edits there too.
> Currently a user who edits `BUILD_PLAN.md` and then re-runs
> `adopt --write` would lose their edits.

This is the section most likely to bite us if we get it wrong, so
nailing the contract before code is written is worth the time.

**Files `adopt` may write to** (with strategy per file):

| File | If absent | If exists |
|---|---|---|
| `CLAUDE.md` | Create from template, fill `{{APP}}` etc. | **Augment-only.** Append `<!-- context-kit:adopt:start -->` block under a new `## Project facts (auto-detected)` H2. Never overwrite the human's existing CLAUDE.md prose. |
| `00-START-NEXT-SESSION.md` | Create with `state: scaffold` frontmatter and a "Project adopted into context-kit on $DATE — first task: review the [adopt: please describe] placeholders." | **Skip + warn.** Do not touch the user's session priorities. |
| `idea.md` | Create populated draft. | **Skip + warn.** User's idea — don't touch it. |
| `docs/<APP>_WHAT_IT_IS.md` | Create with detected stack + README first paragraph + placeholders for the "why". | **Augment-only**, same managed-block pattern. |
| `docs/<APP>_INVENTORY.md` | Create empty managed block; user runs `inventory --write` separately. | Skip — `inventory` owns this file. |
| `docs/BUILD_PLAN.md` | Create populated from detected stack. | **Augment-only** under managed block; warn if existing content disagrees with detected stack. |
| `docs/topics/*.md` | Create stub per detected topic. | Skip + warn per file. |
| `docs/handoffs/SESSION_001_ADOPTION.md` | Create handoff describing what `adopt` did. | Skip — handoffs are append-only. |
| `docs/docs-pattern/` | Copy the framework files (same as `init`). | Skip if present and same version. |

**Marker convention:** `<!-- context-kit:adopt:start -->` and
`:end -->`, mirroring the existing `seed` and `inventory` patterns.

**Non-AI-doc files we don't touch:** Everything in `src/`, `app/`,
`lib/`, `backend/`, `frontend/`, `mobile/`, `apps/`, `tests/`,
`migrations/`, `node_modules/`, `venv/`, `__pycache__/`, etc.
`adopt` is read-only against source code — the strict invariant is
**source bytes never change**.

## 6. Sample dry-run report (against `focus-flow`)

To make this concrete — what would `context-kit adopt
/Users/donkeyking/development/focus-flow` print today?

```
context-kit adopt — DRY RUN
===========================
target: /Users/donkeyking/development/focus-flow

Detected:
  • Split monorepo (backend/ + frontend/)
  • backend/  : Python (no top-level manifest visible — needs deeper scan)
  • frontend/ : (manifest scan needed)
  • README.md : present (will pull first paragraph for narrative)
  • CLAUDE.md : absent
  • idea.md   : absent

Plan:
  CREATE   CLAUDE.md                           (from template)
  CREATE   00-START-NEXT-SESSION.md            (state: scaffold + adoption note)
  CREATE   idea.md                             (draft from README + detected stack)
  CREATE   docs/FOCUS_FLOW_WHAT_IT_IS.md       (3 [adopt: please describe] gaps)
  CREATE   docs/FOCUS_FLOW_INVENTORY.md        (empty managed block)
  CREATE   docs/BUILD_PLAN.md                  (split-stack template, partial)
  CREATE   docs/topics/backend.md              ([adopt: please describe])
  CREATE   docs/topics/frontend.md             ([adopt: please describe])
  CREATE   docs/handoffs/SESSION_001_ADOPTION.md
  CREATE   docs/docs-pattern/                  (10 framework files)

Gaps you'll need to fill (4):
  1. docs/FOCUS_FLOW_WHAT_IT_IS.md — "Why does this exist?"
  2. docs/FOCUS_FLOW_WHAT_IT_IS.md — "Who is it for?"
  3. docs/topics/backend.md        — what the backend does
  4. docs/topics/frontend.md       — what the frontend does

Re-run with --write to apply this plan.
```

The dry-run is the user's commit point. Nothing on disk changes
until they re-run with `--write`.

## 7. The `[adopt: please describe]` placeholder contract

Anywhere `adopt` couldn't infer something, it writes a literal
`[adopt: please describe: <what's missing>]` placeholder. Two things
make these load-bearing instead of decorative:

1. **`context-kit doctor` learns a new check.** If any
   `[adopt: please describe...]` markers exist in the project's
   docs, doctor flags them as warnings (not blocking, but visible
   on every run). This nudges the user back to the gaps without
   nagging.
2. **`CLAUDE.md`'s "Read This Before Writing Any Code" section
   gets a new line:** "If you see `[adopt: please describe]` in a
   doc, ask the user to fill it in before writing code that
   depends on the missing context."

These two together make the placeholders honest: the CLI doesn't
pretend to know what it doesn't, and the agent loaded into the
project knows to ask.

## 8. The seeded `idea.md` shape

```markdown
# {{APP_TITLE}}

> Generated by `context-kit adopt` on {{DATE}}.
> Review and refine — especially the [adopt: please describe] sections.

## What are we building?

[adopt: please describe — first paragraph of README was:]
> {{README_FIRST_PARAGRAPH or "(no README found)"}}

## Who is it for?

[adopt: please describe — adopt cannot infer audience from code.]

## Problem

[adopt: please describe — adopt cannot infer the original motivation.]

## First milestone

[adopt: please describe — for an existing project, "first milestone"
may already be shipped. Either describe the next milestone or delete
this section.]

## Tech stack

{{DETECTED_STACK_BLOCK}}

<!-- detected by context-kit adopt — high confidence
     (parsed from {{MANIFEST_FILES}}). If wrong, edit
     this block; seed will respect what you write here. -->

## Open questions

- [adopt] What problem does this project solve that wasn't solved
  before?
- [adopt] What was the most recent thing you were working on?
- [adopt] Are there any architectural decisions you'd reconsider
  with hindsight?
```

Critically: **the Tech stack section is populated by `adopt`, not
left for `recommend-stack`**. Recommending a stack to someone who's
already chosen one is the most common way to disrespect a user's
prior work. If the user disagrees with adopt's detection, they edit
the section, and seed/recommend-stack honors what's written.

## 9. Workflow

The user-facing workflow `adopt` enables:

```bash
# In your existing project root:
context-kit adopt .                    # see the dry-run report
context-kit adopt . --write            # apply it

# Open the generated idea.md, fill in the [adopt: please describe]
# gaps. Maybe 5 minutes for a small project.

context-kit seed idea.md --force       # re-seed against the now-complete idea
                                       # (--force because adopt's drafts already
                                       # exist; seed augments under markers)
context-kit doctor                     # surface remaining placeholders + env checks
context-kit inventory --write          # generate runtime anchor
context-kit start                      # opens the project view (since 00-START exists)
```

Or if the user wants a guided experience:

```bash
context-kit adopt . --write && context-kit start
# wizard detects state: scaffold, opens at the "tell me about your project" step
```

**Wizard integration (deferred to a follow-up).** The current wizard
flow is from-scratch; an adoption flow needs different copy ("Let's
fill in what context-kit couldn't detect"). I'd ship `adopt` as
CLI-only first and add a wizard branch in a follow-up release once
we have real-user feedback on the bare command.

## 10. Test strategy

> **Shipped (v0 + v0.1):** 20 focused tests in `tests/test_adopt.py`
> across 5 classes — `TestDetectStack` (5), `TestSubdirDetection`
> (6, v0.1), `TestPlanAndApply` (3), `TestClaudeMdAugmentation` (3),
> `TestRunAdoptCli` (3). The suite is a small, fast, focused subset
> of the ~50 tests this section originally proposed; the larger
> set lands as fixtures and assertions are added in v0.2 work.
>
> Real-world dogfood (manual, dry-run only) covered all 6 listed
> projects: focus-flow, dealflowtracker, contract-concierge,
> norman-handyman-mvp, ai-content-studio, and (held in reserve) the
> Flutter project. All five tested projects produce usable plans on
> first try.

This is harder than `recommend_stack` because real projects are
large and varied. The pattern:

**Per-detector tests** (~30 expected, mirrors `test_recommend_stack`):
- Each manifest signal → tiny fixture project under
  `tests/fixtures/adopt/django_minimal/`,
  `tests/fixtures/adopt/nextjs_minimal/`, etc. Fixtures are 3-5
  files each, enough to trigger the detector.
- Negative tests: fixture has `package.json` but no `react` dep →
  doesn't trigger React detector.

**Multi-stack integration tests** (~6):
- `split_monorepo`: backend/ Django + frontend/ Next.js → both
  detected, BUILD_PLAN renders both.
- `monorepo_ambiguous`: package.json + manage.py at root → exit 2
  with the "two projects" message.
- `expo_only`: package.json with expo dep → React Native + Expo
  detected.
- `python_only`: pyproject.toml only → Python detected, no
  framework specifics.
- `unknown`: README + nothing else → exit 1, helpful message.
- `partially_adopted`: pre-existing CLAUDE.md → augment-only path
  exercised, original CLAUDE.md preserved verbatim outside markers.

**Generator tests** (~10):
- Stack section renders correctly per detected profile.
- `[adopt: please describe]` placeholders count matches expected.
- Managed-block markers present and well-formed.
- README first paragraph extraction works for the README shapes
  we have in /development/.

**Materializer tests** (~6):
- Dry-run never writes.
- `--write` writes only inside markers when target exists.
- `--force` overwrites the marker contents but preserves prose
  outside.
- Skip-and-warn fires on non-augmentable existing files
  (`idea.md`, session priorities).

**Real-world dogfood tests** — *not in CI*. We run these manually
against `/development/` projects before each release of `adopt`:

| Project | Expected detection | Notes |
|---|---|---|
| `focus-flow` | Split monorepo (backend + frontend) | The medium case. |
| `dealflowtracker` | Split monorepo + render.yaml + start.sh | Tests deployment-script signal handling. |
| `norman-handyman-mvp` | Multi-platform (backend + mobile + web) + existing CLAUDE.md | Tests augment-only path on a real CLAUDE.md. |
| `contract-concierge` | Split monorepo + render.yaml | Smaller version of dealflowtracker. |
| `ai-content-studio` | Django (largest test) | Stress test — many subdirs, many manifests. |
| `flutter` | Flutter / Dart | Tests pubspec detection. |

The user explicitly excluded `unified-donkey-betz` from dogfooding;
that's the integration-mega-project and would be a poor first test.

Total expected tests: **~50**, raising the suite from 239 → ~289.

## 11. Files this session would change

```
A  cli/adopt.py                                     ~600 lines
A  cli/_pattern/ADOPT_PLAYBOOK.md                   user-facing how-to
A  tests/test_adopt.py                              ~700 lines, ~50 tests
A  tests/fixtures/adopt/django_minimal/             3 files
A  tests/fixtures/adopt/nextjs_minimal/             3 files
A  tests/fixtures/adopt/split_monorepo/             ~10 files
A  tests/fixtures/adopt/partially_adopted/          5 files
A  ... (~6 more fixture dirs)
A  docs/handoffs/SESSION_009_ADOPT.md               this file (status: shipped)
M  cli/doctor.py                                    new check: warn on
                                                    [adopt: please describe]
                                                    placeholders in docs
M  cli/_starter/root/CLAUDE.md                      new rule: surface adopt
                                                    placeholders before
                                                    writing code
M  cli/bootstrap.py                                 cli/adopt.py in RUNTIME_COPY
M  context_kit.py                                   adopt subparser + dispatcher
M  README.md                                        commands list + adopt
                                                    section ("for existing
                                                    projects")
M  CHANGELOG.md                                     0.7.0 entry
M  cli/_skills/context-kit/SKILL.md                 mention adopt in the skill
M  docs/CONTEXT_KIT_INVENTORY.md                    regen
```

Versioning: this is a real new feature. **0.7.0** is right.

## 12. Open questions (for review)

These need decisions before implementation. Flagged so reviewers
can push back without us building the wrong thing:

1. **Should `adopt` be one command or two?** Alternatives:
   - **(A) one command**: `context-kit adopt .` does detection +
     scaffolding + idea.md draft in one shot. Recommended.
   - **(B) two commands**: `adopt-detect` (read-only report) +
     `adopt-apply` (writes). More composable, more typing.

   I'm proposing (A) with `--write` as the gate. Same pattern as
   `inventory --write`. Rejecting (B) on UX grounds: a beginner
   shouldn't have to learn two verbs.

2. **What's the right confidence threshold for "I refuse to
   guess"?** Currently I'm proposing exit 2 when multiple top-level
   manifests conflict. Alternatives:
   - Always pick highest-confidence and warn (risk: silent wrong
     pick).
   - Always exit 2 and require `--target backend` style narrowing
     (more honest but more typing).

   Recommended: exit 2. Better to ask than guess on something this
   load-bearing.

3. **Does `recommend-stack` get involved at all?** For an adopted
   project, the stack is decided. I'm proposing
   `recommend-stack` is **not** invoked — the `## Tech stack`
   section is populated from detected manifests, full stop. This
   means a user adopting a Flask project won't be subtly nudged
   toward FastAPI. Is that the right call? I think yes; happy to be
   overruled.

4. **CLAUDE.md augmentation: how aggressive?** When an existing
   CLAUDE.md is present, what do we add inside the managed block?
   - Stack facts (high confidence, mechanical)
   - Detected topics (medium confidence)
   - The "Read BUILD_PLAN.md before coding" rule? — probably yes,
     since it's the reason we're here.
   - The "Where to find things" table? — probably no; that's the
     human's home turf.

5. **Should `adopt` invoke `inventory --write` automatically?**
   Pro: completes the loop in one command. Con: `inventory --write`
   has its own opinions and a user might not want it written without
   an explicit step. Recommended: don't auto-invoke; instead print
   it as the next suggested command in the dry-run report.

6. **Wizard integration.** Should this ship with a wizard mode in
   0.7.0 or wait for 0.7.1 once we've seen real-user feedback on
   the CLI? Recommended: CLI-only in 0.7.0.

7. **What about projects that already have `.cursorrules`,
   `.windsurfrules`, `AGENTS.md`, or other AI-tool configs?** Do
   we read them as additional signal (the user has thought about
   this before), or treat them as orthogonal? Recommended: read
   them as signal, surface in the dry-run report as
   "Found existing AI config: .cursorrules — consider porting
   notable rules to your CLAUDE.md", but don't try to auto-merge.

## 13. What this is NOT

To keep scope honest:

- ❌ Not a code analyzer. We don't try to summarize what
  functions do, what classes mean, or what business logic exists.
  That's the agent's job once it has the docs.
- ❌ Not a migration tool. We don't move source files, restructure
  directories, or "convert" the project to anything.
- ❌ Not opinionated about the project. We report what we observe;
  we don't suggest "you should be using X instead of Y."
- ❌ Not a substitute for the human's understanding. Every
  `[adopt: please describe]` is the CLI saying "I cannot do this
  for you." That's a feature.

## 14. Definition of done

For 0.7.0 to ship:

- [ ] `context-kit adopt .` works against all 6 dogfood projects
      in §10 without manual intervention.
- [ ] Each dogfood project's generated docs make an AI session
      productive on first try (subjective; user-validated).
- [ ] `--dry-run` and `--write` produce identical outputs except
      for the disk side effects.
- [ ] Re-running `adopt . --write` on a project that's already
      been adopted is a no-op (idempotent).
- [ ] An existing CLAUDE.md is preserved byte-for-byte outside
      managed markers after `--write`.
- [ ] `doctor` warns on remaining placeholders.
- [ ] All 50 new tests pass; the existing 239 still pass.
- [ ] `inventory --check` is current.
- [ ] CHANGELOG and README updated with the new command and the
      "for existing projects" framing.

---

## Appendix A: signals we considered but rejected for v1

- **Reading `.git/config` for the upstream URL** to populate the
  GitHub repo link in CLAUDE.md. Plausible but adds a network/
  filesystem assumption. Defer to 0.7.1.
- **Parsing TypeScript `tsconfig.json` for project shape**. Useful
  but expensive; we get most of the value from `package.json` deps.
- **Reading actual code files for class/function inventories**.
  That's what `inventory` is for already; don't duplicate.
- **Inferring "what the project does" from README + commit
  history**. Tempting but high-risk for confident wrong claims. The
  `[adopt: please describe]` placeholder is the safer move.

## Appendix B: comparison with similar tools

For reviewer context — how this differs from neighbors in the space:

- **`npm init` / `cargo new`** — scaffold only, single-language,
  no docs layer.
- **`cookiecutter`** — template-driven scaffolding, no detection.
- **`README.md` generators** (`readme-md-generator` etc.) —
  produce a README from a manifest, but no AI-session memory layer.
- **GitHub Copilot / Cursor `.rules` generators** — closer in
  spirit, but tied to one editor and don't produce the
  load-bearing docs the AI session itself needs to read.

`adopt` occupies a gap none of these fill: a portable, editor-
agnostic memory layer generated from observed signals, with honest
gaps where the CLI can't infer.

---

*End of original design proposal. Sections 15–16 below were added
after v0 + v0.1 shipped to track what landed and what's next.*

---

## 15. v0.2 backlog (post-v0.1)

> **Update (2026-04-26, after the clarity-timelock + flow-name-service
> dogfood):** items #1 and #2 below are **superseded by §19**, which
> consolidates them under a single core principle — *visibility
> first, classification second*. The original items captured the
> right symptoms (dbao-studio's misclassification, donkey_betz_world's
> silent drop) but proposed ecosystem-by-ecosystem fixes that don't
> generalize. §19's fallback-scan approach handles every fixture we've
> logged so far, plus future Web3 / Solidity / Rust / Go projects we
> haven't tested yet, with no per-ecosystem code. Items #3–#9 below
> are unaffected and remain real backlog work.

Ordered by "expected payoff per unit of work", informed by the
five-project dogfood at the close of v0.1:

1. **[SUPERSEDED BY §19]** Root manifest should not automatically
   win when subdirs contain stronger framework signals. v0.1's
   "root wins"
   shortcut is correct for clean single-stack repos but wrong for
   "abandoned-shape" repos where the root carries weak/leftover
   manifests (e.g. a root `package.json` for tooling) and the
   real application lives in `backend/` + `frontend/`. The
   dbao-studio fixture (see §17) is the canonical example: root
   has both `package.json` and `requirements.txt`, but `backend/`
   contains `manage.py` (a much stronger Django signal) and the
   existing CLAUDE.md confirms "Django backend". v0.2 should: (a)
   when root has only weak/mixed signals, also scan recognized
   subdirs and merge results; (b) treat `manage.py` /
   `pubspec.yaml` / `Cargo.toml` / `go.mod` as *strong* framework
   signals that outrank a generic root `package.json` /
   `requirements.txt` even when both are present. Pairs naturally
   with item #3 below (framework detection inside manifests).
2. **[SUPERSEDED BY §19]** Expand manifest recognition beyond
   JS/Python and report scanned-but-unrecognized subdirs. v0.1
   only knows four manifest filenames (`package.json`, `manage.py`,
   `requirements.txt`, `pyproject.toml`). A subdir whose only
   manifest is something else (`pubspec.yaml`, `Cargo.toml`,
   `go.mod`, `Gemfile`, `*.xcodeproj`, `app/build.gradle`) is
   silently dropped — `_detect_in_dir()` returns `unknown` with
   empty signals and the scanner skips the subdir entirely so it
   never appears in the dry-run report. The donkey_betz_world
   fixture (see §18) is the canonical example: the repo has a
   real Flutter app under `mobile/` but v0.1's report mentions
   only backend + frontend. v0.2 should: (a) extend the manifest
   set to at minimum Flutter (`pubspec.yaml`), Rust
   (`Cargo.toml`), Go (`go.mod`), Ruby (`Gemfile`), iOS
   (`*.xcodeproj` / `Podfile`), and Android (`app/build.gradle`);
   (b) when a recognized subdir name (`backend`/`frontend`/
   `mobile`/etc.) exists but contains no recognized manifest,
   surface it in the dry-run as `scanned mobile/, found
   pubspec.yaml — adopt v0.2 doesn't recognize that format yet`
   instead of silently omitting it. Honest-by-omission is worse
   than misclassification: at least misclassification is visible.
3. **`apps/<name>/` Turborepo / monorepo shapes.** The current
   depth-1 limit returns "unknown" for Nx, Turborepo, and
   microservice monorepos that put each component under
   `apps/api`, `apps/web`, etc. v0.1's `_detect_in_dir()` is
   already the right primitive — v0.2 adds a second fallback that
   walks `apps/*/` (and maybe `packages/*/` and `services/*/`)
   when the depth-1 scan returns empty.
4. **Idempotent BUILD_PLAN / WHAT_IT_IS / START rewriting via
   managed-block markers.** Currently these three files are
   create-only — re-running `adopt --write` against a project
   where they exist would either skip them or overwrite them
   (depending on framework state). Wrap each in
   `<!-- context-kit:adopt:start --> / :end -->` blocks so re-runs
   refresh the auto-generated portions and preserve human edits.
   Same pattern the CLAUDE.md augment block already uses.
5. **Framework detection inside the four manifests.** Today we
   know "JavaScript" but not "Next.js"; "Python" but not "Django"
   (despite already detecting `manage.py` separately).
   `package.json` parsing with a small dependency-name lookup
   table (next, react, vue, svelte, vite, expo, react-native,
   express, fastify) and `requirements.txt` / `pyproject.toml`
   keyword grep (django, fastapi, flask) gets us most of the way.
   Output line goes from "JavaScript / Node.js" to "Next.js
   (React, App Router)".
6. **`[adopt: please describe]` doctor check.** §7 of the original
   design. `doctor` learns to grep the project's docs for the
   marker and warn (not block) on each occurrence. Closes the
   loop — adopt is honest about what it didn't infer, doctor
   surfaces those gaps every run until they're filled in.
7. **Wizard branch.** The current wizard assumes empty cwd. Add
   a "fresh tab discovery" entry point: when `/api/state` reports
   the cwd has no init markers but `adopt` would detect a usable
   stack, the wizard offers "We found an existing project. Want
   to adopt it instead of starting from scratch?". Lifts adopt
   into the beginner flow without forcing it on existing CLI
   users.
8. **`recommend-stack` integration (read-only).** The current
   adopt block hard-codes the "do not switch frameworks without
   asking" rule. v0.2 could optionally invoke `recommend-stack`
   on the *adopted* project's idea-equivalent (the user-supplied
   description) and surface the diff: "You're using Flask;
   recommend-stack would have suggested FastAPI for this idea —
   here's why, but you've already shipped, so we're not changing
   anything." Honest, advisory, never modifies the stack.
9. **Confidence scoring.** §3's full table. Useful when v0.2
   starts seeing genuinely ambiguous projects; not useful while
   we're still operating on binary detection of four manifest
   filenames.

Items 1 and 2 (now superseded by §19) covered the "see what's
actually there" gap. Items 3 and 4 unblock the next class of
layouts (Turborepo) and make adopt safely re-runnable. Item 5
closes the "honest about what we don't know" loop alongside
item 6. Items 7–9 are nice-to-haves once the core is solid.

Specific fixture-to-item mapping (post-§19):
- **All four logged fixtures** (dbao-studio §17, donkey_betz_world
  §18, plus the clarity-timelock and flow-name-service cases that
  motivated §19) are addressed by §19's visibility-first design.
- **dbao-studio** additionally benefits from item #5 (framework
  detection inside manifests) — §19 makes mobile/ visible but
  doesn't upgrade "Python" to "Django"; item #5 does.
- **donkey_betz_world** likewise benefits from item #5.
- All four fixtures benefit from item #4 (idempotent rewrites)
  if the user hand-edits the generated docs and re-runs adopt.

## 16. What shipped vs. what was designed

Quick reference for cross-checking the original §1–§14 against the
live code:

| Section | Original design | v0 (cea6327) | v0.1 (3f45087) |
|---|---|---|---|
| §2 architecture | 3-layer (detect/generate/materialize) | ✓ shipped | ✓ preserved |
| §3 detection ladder | Confidence scores, ~17 signals | Binary, 4 signals (root only) | Binary, 4 signals (root + 7 subdirs) |
| §4 topic detection | `docs/topics/*.md` per detected topic | not shipped | not shipped |
| §5 managed blocks | Augment-only on existing files | CLAUDE.md only | unchanged |
| §6 sample dry-run | Detailed multi-section report | Compact 4-line plan | Adds split-stack summary |
| §7 `[adopt: please describe]` | Placeholder + doctor integration | Placeholder text only | unchanged |
| §8 `idea.md` shape | Generated draft | Replaced with two simple prompts | unchanged |
| §9 workflow | adopt → seed → doctor → inventory | adopt only (others manual) | unchanged |
| §10 test strategy | ~50 tests + fixtures | 14 tests | 20 tests (+6) |
| §11 files this session | ~10 file changes + RUNTIME_COPY entry | 5 files, no RUNTIME_COPY | 3 files |
| §12 open questions | 7 questions | (A) one command, (3) recommend-stack opt-out, (5) inventory not auto-invoked | unchanged |

The pattern across v0 and v0.1: ship the smallest credible thing,
let real projects expose the next limit, then design v0.2 against
evidence. This is the same pattern that worked for `recommend-
stack` (Session 7) and `doctor` (Session 6).

## 17. v0.2 fixture: dbao-studio

A real project at `/Users/donkeyking/development/dbao-studio` that
v0.1 misclassifies. Logged here as a concrete acceptance target
for the v0.2 work — when v0.2 ships, the dry-run against this
project should produce a correct BUILD_PLAN without hand-editing.

### What's actually there

- **Root manifests:** both `package.json` AND `requirements.txt`.
  Both are weak signals individually — the `package.json` may be
  tooling-only (lint, build helpers, frontend bundler config), and
  `requirements.txt` is a generic Python pin file with no
  framework name in it.
- **Subdirectory shape:** `backend/`, `frontend/`, plus
  `agents/`, `config/`, `docker/`, `docs/`, `documentation/`,
  `documentations/` (yes, two doc dirs), and `sdk/`.
- **Strong subdir signal:** `backend/` contains `manage.py`. This
  is a Django marker — much stronger than the root manifests
  combined.
- **Existing rich CLAUDE.md** at root, with the project's actual
  architecture documented inline:
    > "backend/ # Django backend, with subsystems for agents/,
    > api/, core/ Django settings, integrations/, content/,
    > embeddings/, memory/, prompts/, learning/, manage.py."
  The existing CLAUDE.md is already authoritative — augment-mode
  must preserve every byte of it.
- **README.md** present at root.
- **Multiple `docker-compose*.yml` files** (production, unified,
  default) suggesting a containerized multi-service deployment.

### Current v0.1 behavior (misclassification)

Run on 2026-04-26 with v0.1 at commit `3f45087`:

```
Detected stack: JavaScript / Node.js (detected from package.json)
  note: Detected both JavaScript and Python manifests at root.
        v0 reports JavaScript and notes Python presence;
        multi-stack handling is planned for a later release.

Plan:
  would create   docs/BUILD_PLAN.md
  would create   docs/PROJECT_WHAT_IT_IS.md
  would create   00-START-NEXT-SESSION.md
  would augment  CLAUDE.md
```

The `would augment` line is correct — augment-mode would preserve
the existing CLAUDE.md verbatim. But the generated BUILD_PLAN's
`## Tech stack` heading would read:

```
## Tech stack

JavaScript / Node.js (detected from package.json)
```

This is misleading. The existing CLAUDE.md says the backend is
Django (Python). An AI session reading the v0.1-generated
BUILD_PLAN would treat JavaScript as the source-of-truth stack
and propose Node-first solutions, contradicting reality.

### Desired v0.2 behavior

When v0.2 ships, this same dry-run should produce:

```
Detected stack: Split monorepo —
  backend = Django (detected from backend/manage.py)
  frontend = JavaScript / Node.js (detected from frontend/package.json)
  note: Root manifests (package.json, requirements.txt) appear to
        be tooling/infra only; backend/manage.py is a stronger
        framework signal and was preferred. To override, edit
        docs/BUILD_PLAN.md after --write.

Plan:
  would create   docs/BUILD_PLAN.md      (managed-block, re-runnable)
  would create   docs/PROJECT_WHAT_IT_IS.md  (managed-block, re-runnable)
  would create   00-START-NEXT-SESSION.md
  would augment  CLAUDE.md
```

And the generated BUILD_PLAN's `## Tech stack` heading should read:

```
## Tech stack

- **Backend:** Django (detected from `backend/manage.py`)
- **Frontend:** JavaScript / Node.js (detected from `frontend/package.json`)
```

### Acceptance criteria for "v0.2 handles dbao-studio"

- [ ] `detect_stack(dbao_studio_path).parts` is non-empty and
      contains `{"backend": "django", "frontend": "javascript"}`
      (or `"python"` if framework detection from item #4 doesn't
      land in the same v0.2 ship).
- [ ] `detect_stack(...).language` is `"python"` (backend wins).
- [ ] BUILD_PLAN.md renders the per-subdir bullet table, not the
      single-line "JavaScript / Node.js" summary.
- [ ] CLAUDE.md augment block carries the split table too.
- [ ] Existing CLAUDE.md prose (project structure tree, agent
      list, integrations) is preserved byte-for-byte outside the
      managed markers — re-verify this stays true through the
      detection-priority rewrite.
- [ ] A re-run of `adopt --write` after a hand-edit to BUILD_PLAN
      preserves the human edit (depends on item #3 — managed
      markers in BUILD_PLAN).

### Which v0.2 backlog items this fixture exercises

- **§19 (visibility-first fallback scan)** — primary driver.
  §19 supersedes the original items #1 and #2; it surfaces the
  Django backend by reporting that `backend/` exists and contains
  a recognized `manage.py` even when the root has its own
  manifests, so the user no longer sees a misleading "JavaScript"
  classification with the real backend invisible.
- **#4 (idempotent BUILD_PLAN via managed markers)** — required
  for the "re-runnable after hand-edit" acceptance criterion.
- **#5 (framework detection inside manifests)** — upgrades
  "Python" to "Django" so the BUILD_PLAN reads the way the
  existing CLAUDE.md does. §19 alone makes the project visible;
  #5 makes the labels accurate.

A v0.2 release that ships §19 + items #4 + #5 would handle this
fixture cleanly. The other backlog items (#3 Turborepo walking,
#6 doctor placeholders, #7–9) are orthogonal — important on their
own merits but not required to fix dbao-studio.

### How to use this fixture during v0.2 implementation

Manual (dry-run, safe — never touches source):

```bash
python3 context_kit.py adopt /Users/donkeyking/development/dbao-studio
```

The expected output above (or close to it) is the eyeball test.
For automated coverage, lift a stripped-down fixture under
`tests/fixtures/adopt/dbao_studio_shape/` containing just the
manifest files and an existing CLAUDE.md — that lets the test
suite assert the new detection priority without depending on the
real `/development/` path.

## 18. v0.2 fixture: donkey_betz_world (Flutter mobile)

A real project at `/Users/donkeyking/development/donkey_betz_world`
that v0.1 partially handles correctly but silently drops one
component. Logged as a second concrete acceptance target for v0.2,
complementary to dbao-studio (§17). Where dbao-studio exposes the
"misclassification" failure mode, donkey_betz_world exposes the
worse "honest-by-omission" failure mode — the dry-run report
mentions only the two stacks v0.1 understands and gives no signal
that anything was missed.

### What's actually there

- **Empty repo root** (just a `Makefile`, `media/`, and the three
  recognized subdirs). No CLAUDE.md, no README, no root manifests.
  This is the clean case for v0.1's depth-1 fallback.
- **`backend/`** contains both `manage.py` AND `requirements.txt`.
  Django (Python). v0.1 detects this correctly.
- **`frontend/`** contains `package.json`, `next.config.mjs`,
  `eslint.config.mjs`, `jsconfig.json`, an `app/` dir. Next.js.
  v0.1 detects the `package.json` and labels it "JavaScript /
  Node.js" (correct as far as v0.1 can see; framework name will
  arrive with backlog item #5).
- **`mobile/`** is a real Flutter / Dart project: `pubspec.yaml`
  at root, `lib/` for Dart source, plus `android/`, `ios/`,
  `macos/`, `linux/` build targets and `analysis_options.yaml`
  for Dart analyzer config. **v0.1 cannot see this at all.**
  `_detect_in_dir(mobile/)` returns `("unknown", [])` because
  none of the four recognized manifest filenames are present, and
  the scanner skips the subdir entirely so it never appears in
  the `parts` dict, the signals list, or the dry-run report.

### Current v0.1 behavior (silent omission)

Run on 2026-04-26 with v0.1 at commit `3f45087`:

```
Detected stack: Split monorepo — backend=Python, frontend=JavaScript / Node.js
  note: Split monorepo detected. Per-subdir stack listed below;
        deeper layouts (apps/<name>/...) are not yet handled.

Plan:
  would create   docs/BUILD_PLAN.md
  would create   docs/PROJECT_WHAT_IT_IS.md
  would create   00-START-NEXT-SESSION.md
  would create   CLAUDE.md
```

The detection line names two stacks. The note mentions a single
caveat (deeper layouts). **Nothing in this output indicates that
`mobile/` exists, was scanned, or contains a real Flutter app.**
The generated BUILD_PLAN's `## Tech stack` section reads:

```
## Tech stack

- **Backend:** Python (detected from `backend/manage.py`)
- **Frontend:** JavaScript / Node.js (detected from `frontend/package.json`)
```

An AI session loaded into this project from these docs would build
two-thirds of the application — backend and web frontend — and
have no awareness that there's a Flutter mobile app to keep in
sync. That's a more dangerous failure than dbao-studio's
misclassification: a wrong fact can be challenged; a missing fact
cannot.

### Desired v0.2 behavior

When v0.2 ships item #2 from §15, this same dry-run should
produce:

```
Detected stack: Split monorepo —
  backend = Python (detected from backend/manage.py)
  frontend = JavaScript / Node.js (detected from frontend/package.json)
  mobile = Flutter / Dart (detected from mobile/pubspec.yaml)

Plan:
  would create   docs/BUILD_PLAN.md
  would create   docs/PROJECT_WHAT_IT_IS.md
  would create   00-START-NEXT-SESSION.md
  would create   CLAUDE.md
```

And the BUILD_PLAN's `## Tech stack` section should read:

```
## Tech stack

- **Backend:** Python (detected from `backend/manage.py`)
- **Frontend:** JavaScript / Node.js (detected from `frontend/package.json`)
- **Mobile:** Flutter / Dart (detected from `mobile/pubspec.yaml`)
```

Even if v0.2 doesn't add full Flutter support in the same ship,
the half-fix is acceptable as long as it's *visible*:

```
Detected stack: Split monorepo — backend=Python, frontend=JavaScript / Node.js

Subdirs scanned but not classified:
  mobile/ — found pubspec.yaml; adopt v0.2 doesn't recognize this format yet.
```

The honest-omission scan-but-report behavior is item #2's "(b)"
sub-bullet and is the load-bearing part of the fix; the manifest
recognition list extension is item #2's "(a)" and is mostly
mechanical.

### Acceptance criteria for "v0.2 handles donkey_betz_world"

Either path satisfies the fixture:

**Full fix** (item #2 ships both (a) and (b)):
- [ ] `detect_stack(donkey_betz_world).parts` contains
      `{"backend": "python", "frontend": "javascript", "mobile": "flutter"}`
      (or whatever `_lang_label` ends up calling Dart).
- [ ] BUILD_PLAN.md renders all three subdirs in its bullet table.
- [ ] CLAUDE.md augment block (or fresh-create) carries all three.
- [ ] `language` is still `"python"` (backend wins, primary
      unchanged).

**Half fix** (item #2 ships only (b) — the visibility fix —
without the recognition list extension):
- [ ] Dry-run output contains a "Subdirs scanned but not
      classified" section listing `mobile/` with the actual
      filename found (`pubspec.yaml`).
- [ ] The BUILD_PLAN.md likewise notes the unclassified subdir so
      an AI session reading the doc knows mobile exists, even if
      adopt couldn't say what kind of app it is.

The half fix is the honest minimum. Without it, v0.2 still has
the silent-drop bug for any future-not-yet-recognized manifest.

### Which v0.2 backlog items this fixture exercises

- **§19 (visibility-first fallback scan)** — primary and
  sufficient driver. §19 supersedes the original item #2; its
  fallback-scan approach surfaces `mobile/` because the subdir
  exists and contains files (notably `pubspec.yaml` and a `lib/`
  with `.dart` source) regardless of whether `pubspec.yaml` is
  in any "recognized manifest" list. The "Unknown but present"
  framing makes the omission impossible.
- **#5 (framework detection inside manifests)** — would upgrade
  "Python" to "Django" and "JavaScript / Node.js" to "Next.js"
  in the BUILD_PLAN, matching the depth of detail §19 adds for
  the mobile subdir.

A v0.2 release that ships §19 alone handles this fixture's
load-bearing requirement (mobile is no longer invisible);
pairing with #5 makes the output read consistently across all
three subdirs.

### How to use this fixture during v0.2 implementation

Manual (dry-run, safe — never touches source):

```bash
python3 context_kit.py adopt /Users/donkeyking/development/donkey_betz_world
```

Compare the output against the "desired v0.2 behavior" block
above. The "Subdirs scanned but not classified" section is the
load-bearing change to look for; it's what closes the
silent-omission gap regardless of whether full Flutter support
lands at the same time.

For automated coverage, lift a stripped-down fixture under
`tests/fixtures/adopt/donkey_betz_world_shape/` containing the
three subdir manifests (a one-line `manage.py`, a `{}`
`package.json`, and a minimal `pubspec.yaml`). The test asserts
that `mobile/` appears in the report — either as a detected part
or as a "scanned but not classified" entry — and never as a
silent omission.

## 19. Core principle for v0.2: visibility first, classification second

> **Status:** authoritative for v0.2 design. Supersedes §15 items
> #1 and #2. Added 2026-04-26 after the clarity-timelock and
> flow-name-service dogfood made it clear that ecosystem-by-
> ecosystem manifest recognition is a losing strategy — every new
> ecosystem (Web3, Flutter, Rust, Go, Solidity, Move, Cadence, …)
> would require its own carve-out and would silently miss anything
> we hadn't pre-listed. The new principle inverts the design: the
> CLI describes what's there, and the human or AI fills in what
> it means.

### The principle

**Never allow real project structure to be invisible.**

Classification is a nice-to-have. *Visibility* is load-bearing.
A user (or an AI session reading the generated docs) must always
be able to tell what subdirectories exist, what manifest-shaped
files live in them, and what kinds of source files are present —
even when adopt has no idea what any of it means.

This rotates v0.2's center of gravity. v0 and v0.1 asked "what
language is this?" and silently dropped what they couldn't answer.
v0.2 asks "what's *here*?" and reports everything, classifying
only what it can.

**Per-ecosystem detection is deferred.** Visibility-first must make
unknown-but-important structure visible *before* classification
gets smarter. Adding Solidity / Move / Anchor / Cadence / Foundry /
Hardhat / Brownie / Truffle / Reflex / Flutter manifest detectors
is correct work, but it's a refinement on top of §19 — not a
substitute. The dogfood inventory (Appendix C) shows what
ecosystem variety we'd otherwise need to support indefinitely.
Visibility-first sidesteps that treadmill: every new ecosystem
shows up in the "Unknown but present" section automatically, with
the user (or the AI session) filling in what it means until and
unless we choose to classify it.

### What v0.2 must add

A **fallback scan** that runs after the existing root + recognized-
subdir detection. The fallback is unconditional — it always runs,
even when the recognized scan classifies everything — because its
purpose is to surface *anything that wasn't classified*, not to
replace classification.

For each non-hidden depth-1 subdir of the repo:

1. **Always list the subdir by name**, regardless of what's in it.
2. **Report any "manifest-shaped" files** present, *whether or not*
   adopt recognizes them. The presence list is generated from a
   pattern set, not a name whitelist:
   - filenames containing `config` (`hardhat.config.ts`,
     `vite.config.js`, `next.config.mjs`)
   - top-level `*.toml` files (`Clarinet.toml`, `Cargo.toml`,
     `foundry.toml`, `Anchor.toml`, `Move.toml`, `pyproject.toml`)
   - top-level `*.json` files matching common patterns (`package.json`,
     `tsconfig.json`, `composer.json`, `flow.json`)
   - top-level `*.yaml` / `*.yml` (`pubspec.yaml`, `docker-compose.yml`)
   - Other well-known manifests by exact name (`manage.py`,
     `Gemfile`, `Pipfile`, `Makefile`, `Dockerfile`)
3. **Report representative source-file extensions** found in the
   subdir's tree (depth-2 walk to keep cost bounded). For each
   extension that appears more than N times (suggest N=3 to filter
   noise), report a count and one example path:
   - `.sol` → "Solidity" likely
   - `.clar` → "Clarity / Stacks" likely
   - `.cadence` → "Cadence / Flow" likely
   - `.rs`, `.go`, `.rb`, `.swift`, `.kt`, `.dart`, etc.
   - **Do not classify** based on these — just surface them.
4. **Skip hidden dirs** (`.git`, `.venv`, `.cache`, etc.) and the
   existing `RECOGNIZED_SUBDIRS_TO_SKIP` set (`node_modules`,
   `__pycache__`, `dist`, `build`, `.idea`, `.vscode`).

The result is a new `unclassified_subdirs` field on `StackProfile`:

```python
@dataclass
class UnclassifiedSubdir:
    name: str                        # "timelocked-wallet"
    manifest_files: list[str]        # ["Clarinet.toml"]
    notable_extensions: dict[str, int]  # {".clar": 2}
    one_example_path: dict[str, str] # {".clar": "contracts/timelocked-wallet.clar"}
```

### How it surfaces in output

**Dry-run report** gains an "Unknown but present" section:

```
Detected stack: Unknown stack — no manifest detected at root or in
                recognized subdirs.

Unknown but present (depth 1, not classified):
  timelocked-wallet/  manifests: Clarinet.toml
                      source:    2 .clar files
                                 (e.g. contracts/timelocked-wallet.clar)
```

**BUILD_PLAN.md** gains an "Unknown but present" subsection under
`## Tech stack` whenever `unclassified_subdirs` is non-empty:

```markdown
## Tech stack

Unknown stack — adopt could not classify the project.

### Unknown but present

The following directories exist and contain notable files but
adopt does not yet recognize their type. An AI session reading
this should ask the user what these are before writing code that
touches them.

- **timelocked-wallet/** — contains `Clarinet.toml` and 2 `.clar`
  files (example: `contracts/timelocked-wallet.clar`). The `.clar`
  extension typically indicates Clarity (Stacks blockchain) smart
  contracts; verify with the user.
```

**CLAUDE.md augment block** likewise gains a "Subdirs of unknown
type" subsection so an AI session loaded into the project can't
miss them.

The "(e.g. contracts/...)" example paths are essential — they let
the user one-keystroke navigate to the actual file and let an AI
session glance at it to figure out the language.

### How the existing fixtures look under §19

Showing the same five projects we've dogfooded, with §19's expected
behavior. None of the dry-run outputs below requires any per-
ecosystem code — they all fall out of the visibility-first
fallback scan.

**focus-flow** (no change — already classified by v0.1):

```
Detected stack: Split monorepo — backend=Python, frontend=JavaScript / Node.js
```

**dbao-studio** (root wins for classification, but `backend/` is
now also surfaced as a separate signal):

```
Detected stack: JavaScript / Node.js (detected from package.json)
  note: Detected both JavaScript and Python manifests at root.

Unknown but present (depth 1, also scanned):
  backend/    manifests: manage.py, requirements.txt
              source:    many .py files (e.g. backend/api/views.py)
              note:      manage.py + .py files suggest Django; verify with user.
```

The misclassification at root remains, but the user (and AI
session) now sees there's a Django backend that adopt's primary
classification missed. Item #5 (framework detection inside
manifests) would later upgrade root from "JavaScript" to
"JavaScript (no detected framework)" or similar.

**donkey_betz_world** (mobile/ now surfaces):

```
Detected stack: Split monorepo — backend=Python, frontend=JavaScript / Node.js

Unknown but present (depth 1):
  mobile/   manifests: pubspec.yaml
            source:    many .dart files (e.g. mobile/lib/main.dart)
            note:      pubspec.yaml + .dart files suggest Flutter / Dart;
                       verify with user.
```

**clarity-timelock** (whole project surfaces from invisibility):

```
Detected stack: Unknown stack — no manifest detected at root or in
                recognized subdirs.

Unknown but present (depth 1):
  timelocked-wallet/  manifests: Clarinet.toml
                      source:    2 .clar files (e.g. contracts/timelocked-wallet.clar)
                      note:      .clar files suggest Clarity / Stacks
                                 smart contracts; verify with user.
```

**flow-name-service** (cadence/ surfaces; api/ surfaces as empty):

```
Detected stack: Split monorepo — web=JavaScript / Node.js

Unknown but present (depth 1):
  api/      empty
  cadence/  source: 4 .cdc files (e.g. cadence/contracts/Domains.cdc)
            note:   .cdc files suggest Cadence / Flow blockchain;
                    verify with user.
```

### What §19 does NOT do

- **Does not classify.** The `note:` lines say "suggest X; verify
  with user" — they're hints for the human reader and the AI
  session, not declarations adopt is staking a claim on. The
  classification surface (`StackProfile.language`, `parts`) is
  unchanged from v0.1.
- **Does not parse manifests.** Just file presence. We don't
  open `Clarinet.toml` to confirm it's well-formed; we just
  report that a file by that name exists.
- **Does not walk deep.** Manifest files: depth 1 (immediate
  contents of each subdir). Source-extension counts: depth 2
  (one level into typical contracts/ / src/ / lib/ patterns).
  Going deeper would explode cost on large repos.
- **Does not replace v0.1's existing detection.** Recognized
  manifests at root or in recognized subdirs still produce the
  primary classification. §19 is additive — it surfaces what
  classification missed, never overrides what classification
  found.

### Acceptance criteria for §19

- [ ] All four logged fixtures (dbao-studio, donkey_betz_world,
      clarity-timelock, flow-name-service) produce dry-run output
      where every non-hidden depth-1 subdir is named explicitly.
- [ ] No regression for already-classified projects (focus-flow,
      ai-content-studio, the test fixtures): existing classification
      output is unchanged; the "Unknown but present" section
      appears only when `unclassified_subdirs` is non-empty.
- [ ] BUILD_PLAN.md and the CLAUDE.md augment block both carry
      the "Unknown but present" content when applicable, so an AI
      session reading from disk sees the same information the
      dry-run shows the user.
- [ ] No per-ecosystem code added: the manifest-shaped pattern
      list and the source-extension report are both data, not
      ecosystem-specific code paths. Adding Solidity / Move /
      Anchor support later means adding rows to the data, not
      writing detector functions.
- [ ] Hidden dirs and noise dirs (`.git`, `.venv`, `node_modules`,
      `__pycache__`, `dist`, `build`, `.idea`, `.vscode`) are
      filtered out of the unknown-but-present scan.
- [ ] Cost is bounded: the source-extension walk caps at depth 2
      and at N files per subdir (suggest N=200 to bound on huge
      monorepos).

### Why this beats per-ecosystem detection

Three reasons, in order of importance:

1. **It scales to ecosystems we haven't seen.** Anything new
   shows up in the "Unknown but present" section automatically.
   The user (or the AI session) sees the manifest filename and
   the representative file extensions and can fill in the gap
   without an adopt update. Solidity, Move, Cadence, future
   ecosystems we can't name yet — all visible without code
   changes.
2. **It's honest about uncertainty.** Per-ecosystem detection
   risks confidently-wrong classifications when a project mixes
   ecosystems or uses a non-canonical layout. "Suggest X; verify
   with user" is a stronger contract than a flat label.
3. **It's much smaller code.** §19 is roughly one new function
   (`scan_unclassified_subdirs(repo)`), one dataclass
   (`UnclassifiedSubdir`), and rendering changes in two
   generators. The per-ecosystem alternative would be a function
   per ecosystem indefinitely.

Item #5 (framework detection inside the four manifests we already
recognize) is still worth doing — it's how "JavaScript / Node.js"
becomes "Next.js" — but it's a refinement on top of §19, not a
replacement for it. Even with item #5 fully shipped, an
unrecognized manifest still goes through §19's fallback path.

### Why the manifest-shaped pattern list is not a slippery slope

The original item #2 design was a manifest *whitelist* — adding
each new format meant updating both the recognition list AND the
classification logic. The §19 pattern list is just a **detector
for "this file is probably a manifest of some kind"**: presence
gets reported, classification doesn't. A new ecosystem requires
zero adopt changes for visibility (the source-extension report
catches it via `.sol` / `.move` / `.cdc` etc.) and exactly one
data row per ecosystem when we later want to upgrade visibility
to classification.

This is the same shape as `inventory`'s "list everything; classify
what you can" approach — the principle that worked in 2024 still
works in 2026.

### Implementation sketch

A complete v0.2 implementation of §19 should be ~200 lines added
to `cli/adopt.py`:

```python
# New constants
NOISE_DIRS = {"node_modules", "__pycache__", ".git", ".venv",
              "venv", "dist", "build", ".idea", ".vscode", ".cache"}
NOTABLE_EXTENSIONS = {  # extension -> human label (purely descriptive)
    ".sol": "Solidity",
    ".clar": "Clarity / Stacks",
    ".cdc": "Cadence / Flow",
    ".cadence": "Cadence / Flow",
    ".move": "Move (Sui/Aptos)",
    ".dart": "Dart / Flutter",
    ".rs": "Rust",
    ".go": "Go",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".ex": "Elixir",
    ".elm": "Elm",
    # ... add freely; this is data, not code
}
MIN_SOURCE_FILES_TO_REPORT = 3
MAX_FILES_PER_SUBDIR = 200  # cost bound

@dataclass
class UnclassifiedSubdir:
    name: str
    manifest_files: list[str]
    notable_extensions: dict[str, int]
    example_paths: dict[str, str]
    note: str | None  # "suggest X; verify with user" or None

def _looks_like_manifest(filename: str) -> bool:
    """File-shape heuristic: anything that *could* be a manifest."""
    # exact-match well-knowns + suffix patterns
    ...

def scan_unclassified_subdirs(repo: Path,
                              already_classified: set[str]) -> list[UnclassifiedSubdir]:
    """Walk depth 1; report what wasn't classified.
    
    ``already_classified`` is the set of subdir names that
    detect_stack() populated into StackProfile.parts. Those are
    excluded from the unknown-but-present report (they're already
    classified). Everything else at depth 1 that isn't noise gets
    described.
    """
    ...
```

`StackProfile` gains a single field:

```python
@dataclass
class StackProfile:
    ...
    unclassified_subdirs: list[UnclassifiedSubdir] = field(default_factory=list)
```

Generators check `if stack.unclassified_subdirs` and render the
new section.

### Test strategy for §19

~10 new tests in `tests/test_adopt.py`, fixture-driven:

| Fixture | Asserts |
|---|---|
| `unknown_only/timelocked-wallet/Clarinet.toml + .clar files` | dir surfaces with manifest + extension |
| `mixed_classified_and_unclassified/backend/manage.py + mobile/pubspec.yaml + .dart files` | mobile/ in unknown-but-present, backend/ not duplicated |
| `empty_subdir/api/` (dir exists, no files) | `api/   empty` |
| `noise_dirs_skipped/node_modules/* + .git/*` | not surfaced |
| `extension_threshold/contracts/foo.sol + bar.sol` | 2 files < threshold of 3, not reported as notable |
| `large_subdir/contracts/*.sol × 500` | capped at MAX_FILES_PER_SUBDIR |
| Generator: BUILD_PLAN renders the new section when `unclassified_subdirs` is non-empty | string assert |
| Generator: CLAUDE.md augment block renders likewise | string assert |
| Generator: section is omitted when `unclassified_subdirs` is empty (no extra noise on clean projects) | negative assert |
| Regression: ai-content-studio (single-stack root) still works | classification unchanged, no new section |

## 20. v0.2 fixture: tornado-core (legacy Solidity / Truffle)

A real project at `/Users/donkeyking/development/apps/tornado-core`
that v0.1 confidently misclassifies — possibly the most consequential
mistake in the dogfood inventory. The repo is the original Tornado
Cash core: zk-SNARK Ethereum mixer contracts plus the Truffle
deployment tooling around them. v0.1 sees only the Truffle tooling
and reports "JavaScript / Node.js", giving an AI session reading
the docs no signal that it's looking at Solidity smart contracts
or zk-SNARK circuits.

This is the canonical EVM smart-contract fixture — every Hardhat,
Truffle, and Foundry project shares the same shape (tooling
manifest at root, contracts hidden in a non-recognized subdir).
A v0.2 ship that handles this fixture handles the whole EVM
ecosystem the same day.

### What's actually there

- **Root manifests:** `package.json`, `truffle-config.js`, `yarn.lock`.
  Both `package.json` and `truffle-config.js` are real signals;
  `truffle-config.js` is the actual project-defining file but v0.1
  has never heard of it.
- **`contracts/`** contains 11 `.sol` files — `Tornado.sol`,
  `cTornado.sol`, `ETHTornado.sol`, `ERC20Tornado.sol`,
  `MerkleTreeWithHistory.sol`, `Verifier.sol`, plus a `Mocks/`
  subdir. This is the heart of the project.
- **`circuits/`** contains 2 `.circom` files (`merkleTree.circom`,
  `withdraw.circom`). zk-SNARK circuits compiled by Circom into
  the Solidity Verifier above. First `.circom` files we've seen
  in the dogfood inventory.
- **`migrations/`** contains 4 numbered Truffle deploy scripts
  (`2_deploy_hasher.js` through `5_deploy_erc20_tornado.js`).
- Other directories: `src/`, `test/`, `scripts/`, `docs/`.
  No `CLAUDE.md`, no `README.md` at root.

### Current v0.1 behavior (silent misclassification)

Run on 2026-04-26 with v0.1 at commit `62ce043`:

```
Detected stack: JavaScript / Node.js (detected from package.json)

Plan:
  would create   docs/BUILD_PLAN.md
  would create   docs/PROJECT_WHAT_IT_IS.md
  would create   00-START-NEXT-SESSION.md
  would create   CLAUDE.md
```

The detection line names a stack with no qualification. The
generated BUILD_PLAN's `## Tech stack` section would read
"JavaScript / Node.js (detected from package.json)" with zero
mention of Solidity, smart contracts, or zk-SNARKs. An AI session
loaded into these docs would propose Node.js solutions for what
is fundamentally a Solidity DeFi protocol with cryptographic
circuits. **This failure mode is worse than dbao-studio's:** there
isn't even an existing CLAUDE.md to compensate for the wrong
classification.

### Desired §19 behavior

When §19 ships, this same dry-run should produce:

```
Detected stack: JavaScript / Node.js (detected from package.json)

Unknown but present (depth 1):
  contracts/  source: 11 .sol files (e.g. contracts/Tornado.sol)
              note:   .sol files suggest Solidity / EVM smart contracts;
                      verify with user
  circuits/   source: 2 .circom files (e.g. circuits/withdraw.circom)
              note:   .circom files suggest zk-SNARK circuits (Circom);
                      verify with user
  migrations/ source: 4 .js files (numbered deploy scripts —
                                   typical of Truffle)
```

The classification line stays unchanged (no per-ecosystem detection;
JavaScript is what `package.json` actually says). What changes is
that the user — and any AI session reading the generated docs —
can no longer miss that Solidity contracts and Circom circuits
are present. The "(e.g. contracts/Tornado.sol)" example path lets
both the human and the agent open the actual file with one click.

### Why this matters

Smart-contract projects can look like JavaScript tooling projects
unless the source structure is visible. The classification surface
of EVM tooling (Truffle, Hardhat, even Foundry's Solidity testing
harness) is JavaScript / TypeScript by file count and manifest
shape; the *meaningful* surface is Solidity. v0.1 reports the
former and silently drops the latter. §19's visibility-first
fallback fixes this **without adding a single line of EVM-specific
detection code** — `.sol` is in the `NOTABLE_EXTENSIONS` data
table and reports itself. The same mechanism handles `.move`,
`.cairo`, `.fc` (Tact / TON), and any other smart-contract
language we eventually want to surface.

### Acceptance criteria for "v0.2 handles tornado-core"

- [ ] `detect_stack(tornado_core_path).language` is still
      `"javascript"` (root classification unchanged — v0.2 is not
      claiming to know what Truffle is).
- [ ] `detect_stack(...).unclassified_subdirs` contains
      `contracts/` (with `.sol` listed in `notable_extensions`)
      and `circuits/` (with `.circom` listed).
- [ ] BUILD_PLAN.md's `## Tech stack` section gains an "Unknown
      but present" subsection naming both directories, the file
      counts, and one example path each.
- [ ] CLAUDE.md (created fresh, since none exists at root) carries
      the same "Unknown but present" content, so an AI session
      reading the entry-point doc sees the contracts immediately.
- [ ] The "(suggest X; verify with user)" hint lines appear for
      `.sol` (Solidity) and `.circom` (zk-SNARK / Circom) — these
      are data table entries, not code paths.

### Which v0.2 backlog items this fixture exercises

- **§19 (visibility-first fallback scan)** — primary and
  sufficient driver. Item #19 alone closes this fixture.
- **#5 (framework detection inside manifests)** — would add
  "Truffle" to the JavaScript label by reading the root
  `truffle-config.js` filename, e.g. `JavaScript / Node.js
  (Truffle)`. Nice-to-have; not required.

A v0.2 release that ships §19 would handle this fixture cleanly.
Item #5 would tighten the root classification but is independent
of the load-bearing fix.

### How to use this fixture during v0.2 implementation

Manual (dry-run, safe — never touches source):

```bash
python3 context_kit.py adopt /Users/donkeyking/development/apps/tornado-core
```

Compare against the "Desired §19 behavior" block above. The two
load-bearing changes to look for: (1) the `Unknown but present`
section names both `contracts/` and `circuits/`, and (2) the
classification line for the root remains "JavaScript / Node.js" —
§19 is *additive*, not corrective.

For automated coverage, lift a stripped-down fixture under
`tests/fixtures/adopt/tornado_shape/` containing a one-line
`package.json`, a one-line `truffle-config.js`, an empty
`contracts/Tornado.sol`, and an empty `circuits/withdraw.circom`.
The test asserts the dry-run output contains both directory
names, both extensions, and the suggest/verify hint lines for
each — closing the silent-EVM-misclassification gap with no
EVM-specific code.

## Appendix C: Dogfood fixture inventory

Snapshot of candidate projects scanned across `/development/` and
`/development/apps/` on 2026-04-26 (134 entries surveyed, 47 of
them nested wrappers). Only the top-10 most useful for `adopt`
testing are listed here. Already-tested fixtures (focus-flow,
dealflowtracker, contract-concierge, norman-handyman-mvp,
ai-content-studio) and the four that earned full sections (§17
dbao-studio, §18 donkey_betz_world, §20 tornado-core, plus the
clarity-timelock and flow-name-service cases that motivated §19)
are excluded from this table to keep it curated.

| # | Path | Interesting shape | Failure mode | Why useful |
|---|---|---|---|---|
| 1 | `apps/reflex-project` | Python full-stack: `requirements.txt` + `rxconfig.py`, no JS at all | v0.1 says "Python" but misses that this is Reflex (compiles to React) | Tests narrowness of recognized manifests; `rxconfig.py` is the real defining file |
| 2 | `donkey_betz_visualizer` | True 3-part split: `backend/` + `frontend/` + `mobile/` (Flutter), no existing CLAUDE.md | mobile/ silently dropped (donkey_betz_world repeat, no CLAUDE.md) | Cleaner 3-part split fixture than donkey_betz_world; tests fresh-create on three-stack repos |
| 3 | `apps/stacks-course/stacks-token-streaming` | Wrapper layout (single child) + Clarinet + `package.json` | Wrapper hides project AND `Clarinet.toml` unrecognized | Two failure modes in one fixture; Stacks ecosystem |
| 4 | `donkey-betz-agent-orchestra` | 5 root manifests (JS+Py+Docker+Make), 282 .py vs 4 .js, existing CLAUDE.md | dbao-studio shape "turned up to 11" — most extreme misclassification we've seen | Stress test for §19 + #5 framework detection; augment-mode on real CLAUDE.md |
| 5 | `apps/LangChain-Udemy-Course` | No manifests; numbered course dirs (`01_*/` … `19_*/`) full of notebooks | v0.1 returns "Unknown" with zero useful info | Tests §19's per-subdir reporting on notebook-only projects |
| 6 | `apps/3d-course` | Multiple unrecognized peer demo subdirs (`three-js-animation/`, `three-js-sample/`, `three-js-webpack/`) | All four sibling demos invisible | Tests "wrapper without the wrapper" — sibling mini-apps |
| 7 | `mentorforge` | Recognized split (`backend/` + `frontend/`) PLUS 4 unrecognized peer dirs (`analysis/`, `financial/`, `reports/`, `research/`) | v0.1 reports only backend+frontend; the four domain dirs silently dropped | Tests §19's "merge classified + unclassified in one report" requirement |
| 8 | `compliancesentinel` / `ironwood-protocol` / `pitchdeckforge` (cluster) | Identical empty-root + `render.yaml` + `start.sh` + `backend/` + `frontend/` shape | Detection works (focus-flow shape), but `render.yaml` invisible at root | Tests whether §19 reports notable root-level non-manifest files |
| 9 | `flutter` (the SDK) | ~5 GB Flutter SDK source tree, ~50 subdirs, no recognized manifests, thousands of `.dart` files | Stress test — does the depth-2 walk + file caps hold? | Performance/cost fixture distinct from classification fixtures |
| 10 | `apps/Donkey Betz` *(literal space in name)* | Mixed root + 387 .py vs 6 .js + space in directory name | Same dbao-studio shape; whitespace-in-path edge case | Whitespace-safety smoke test on adopt's path handling |

Honorable mentions worth knowing about (not in the top 10):

- **`apps/totk_companion`** — `pubspec.yaml` at root + `backend/` subdir. Inverted shape: root has *some* manifest-shaped file so §19's recognized-subdir scan doesn't fire on `backend/`.
- **`apps/working_reflex/reflex-project`** — nested wrapper containing a real Reflex app. Tests wrapper detection AND Reflex recognition in one go.
- **`court_evidence_apps`** — meta-project: `01_deliverables_from_database/`, `02_app_source_evidence/`, `00_OVERVIEW_START_HERE.md`. Different conceptual shape from anything else here.
- **`apps/tornado-core/circuits/`** — first `.circom` (zk-SNARK / cryptography) ecosystem we've seen; baked into the `NOTABLE_EXTENSIONS` table by §20's acceptance criteria.

Empty/dead candidates (skip): `SuperClaude`, `founder-toolkit`,
`apps/buffet_project`, `apps/crewai_test`, `apps/eleven-labs-tutorial`,
`nicolas`, `apps/Donkey_Betz_Server`, `apps/api_playground`,
`apps/chatterbot`, `apps/donkey_workspace`, `apps/aidentifier`,
`apps/ner_labels`, `apps/3js-app`, `apps/realtime_api`,
`apps/twillo_text`, `apps/tailwind_udemy`, `apps/reddit-testing`,
`apps/three-js-next-app`, `apps/r3f-animated-book-slider-starter`,
`apps/Nextjs-Creative-Portfolio-Starter-Code-Files`,
`apps/testing-front-end`,
`apps/Car-rental-app-with-AB-testing-and-personalisation`. Some are
just `app.py` + nothing; others are starter-repo clones with
`package.json` only.

This appendix is a snapshot. Re-running the survey scanner over
`/development/` will surface different projects as the directory
evolves; the value here is the *failure-mode coverage* — together
the top 10 above plus the five fixtures with full sections (§17,
§18, §20, plus clarity-timelock and flow-name-service in §19's
worked examples) cover every distinct way v0.1 fails that we've
documented to date.

## 21. adopt --html static review report

> **Status:** design only. Added 2026-04-26 after the v0.2
> visibility-first ship (commit 7a5ddb8) made the dry-run output
> long enough on real projects (tornado-core surfaces 7 unclassified
> subdirs) that reading it in a terminal became painful. This section
> proposes the smallest UX layer that makes adopt's output reviewable.
> No code in this commit.

### Recommendation in one sentence

Add a `--html` flag to `context-kit adopt` that writes a single
self-contained HTML report to a temp file and auto-opens it in the
browser. Nothing else. CLI behavior is unchanged.

### Hard contracts

These are non-negotiable for the MVP. Future scope creep should
re-read this list before adding anything.

- **Static HTML report.** A single self-contained file. Inline CSS,
  vanilla JS only (collapse / copy-to-clipboard). Same constraint
  as `cli/_static/wizard.html`. No JS framework, no npm
  dependencies, no build step. context-kit stays zero-dep Python.
- **No server.** No new HTTP endpoints anywhere. The report is a
  file on disk; the browser opens it via `file://`. Sidesteps the
  Oreo lifecycle problems the wizard work surfaced.
- **No wizard integration.** Backlog item §15 #6 is still deferred.
  Don't sneak it in via the report. `context-kit start` and
  `context-kit adopt` stay independent commands.
- **Source tree untouched by default.** Default output destination
  is `/tmp/contextkit-adopt-report-<short-hash-of-cwd>.html`. The
  short hash is `cwd.resolve()` digest-truncated so re-runs in
  different projects don't collide on the same file. Same project
  re-run overwrites in place. No `.gitignore` entry needed because
  nothing lands in the project.
- **`--html-out PATH` for explicit destination.** A user who
  wants the report inside their project (e.g.
  `./adopt-report.html`) can pass it explicitly. Default keeps
  source untouched.
- **`--no-browser` for tests / headless / CI.** Without it, the
  default behavior calls `webbrowser.open()` (same stdlib trick
  `context-kit start` already uses). Tests must pass `--no-browser`.
- **No edit / apply actions in the browser.** The report is
  read-only. No "click to apply just this part of the plan" or
  "edit description and save back" controls. Both would require
  HTTP endpoints, both would re-introduce server lifecycle pain,
  both would break the dry-run-is-safe contract. The user's only
  control surface remains the CLI: re-run with `--write` (or with
  different flags) when the report looks right.
- **Unknown-but-present structure is the main visual focus.** §19's
  visibility output is the load-bearing reason this UX exists. The
  report's center-of-page real estate goes to the "Unknown but
  present" section, with collapsible per-subdir items so 7
  unclassified subdirs (tornado-core's case) don't render as a wall
  of text by default. Classified parts get a card too, but tighter.
- **CLI dry-run text output unchanged.** `--html` is purely
  *additive*. Removing the flag leaves adopt v0.2 behaving exactly
  as it does today. Tests assert the dry-run stdout is byte-equal
  with and without `--html`.

### Why HTML and not the alternatives

Four options were weighed:

| Option | Cost | Why rejected (or chosen) |
|---|---|---|
| **`adopt --html` static report** | ~300 LOC + 10 tests | **Chosen.** No server lifecycle. Aligns with `inventory --json` pattern. Source-tree untouched. Works offline. |
| Wizard branch in `context-kit start` | ~700 LOC + new HTTP routes | Rejected. Couples adopt to the wizard, reintroduces server lifecycle, wizard is already feature-rich. |
| TUI / pager output | Medium | Rejected. The user's complaint is "long terminal output is painful" — a pager just paginates the pain. |
| `--report report.md` markdown | Tiny | Considered as a follow-up. HTML costs barely more and gives real visual hierarchy with collapsibles. |

The wizard option is the most tempting and the most dangerous. We
already saw what server-lifecycle complexity costs (the Oreo
recovery work). Adopt is a one-shot operation; it doesn't earn the
server.

### What the report shows (six sections, top-to-bottom)

1. **Header band** — project name (cwd basename), full cwd path,
   generated timestamp, adopt version (read from
   `cli/__init__` or pyproject).
2. **Detection summary card** — primary classification line, the
   signals that produced it, classifier notes ("Split monorepo
   detected", "Detected both JavaScript and Python at root").
   Color-coded: green when classified, amber when "Unknown stack",
   red when no signal at all.
3. **Classified parts card** — only when `parts` is non-empty.
   Per-subdir bullet list mirroring the BUILD_PLAN markdown table.
4. **Unknown but present** — the §19 visibility output as a
   collapsible list. Each subdir item shows manifest files,
   notable extensions with counts and example paths (clickable
   `file://` links), and the suggest-hint note when present. **This
   is the main visual focus** — the section gets the most page real
   estate and the clearest typography.
5. **What adopt would write** — the four-file plan with
   `create` / `augment` badges. Each file row has an "expand to
   preview" toggle that reveals the actual content adopt would
   produce. The CLAUDE.md augment block is shown side-by-side with
   what currently exists in the file (when augment-mode applies)
   so the user can see what's preserved vs. what's added.
6. **Suggested next action** — one prominent CTA. Either:
   - **"Looks good — run with `--write`"** with the literal command
     pre-formatted in a copy box, OR
   - **"Fill in `[adopt: please describe]` placeholders before
     writing"** with file links to where the placeholders appear in
     the planned content.

### Visual separation

Match `cli/_static/wizard.html`'s aesthetic. Card-based vertical
layout, single-column 720-px max width, dark/light auto-theme via
`prefers-color-scheme`. Color hierarchy:

| Region | Color accent | Tone |
|---|---|---|
| Detection card (classified) | Green | "Confident result" |
| Detection card (unknown) | Amber | "We tried and found nothing definitive" |
| Unknown but present | Amber | "Worth your attention but not a problem" |
| Plan / file previews | Neutral grey | "Mechanical output" |
| Warnings / inline notes | Yellow callout boxes | "Read this before acting" |
| Suggested next action | Single bold green button | "Do this next" |

Typography: monospace for paths and commands, system sans-serif
for prose. Inline copy buttons reuse the wizard's `data-copy-text`
delegation pattern.

### Default output destination

```
/tmp/contextkit-adopt-report-<short-hash-of-cwd>.html
```

`<short-hash-of-cwd>` is the first 8 chars of a SHA1 of
`cwd.resolve()`. Same project re-run produces the same filename
and overwrites in place. Different projects on the same machine
don't collide.

Why `/tmp/`:
- Untouched at next reboot — no accumulation risk.
- Standard scratch location every Unix has.
- macOS reflects to `/private/var/folders/...` which `webbrowser.open`
  handles fine.
- Doesn't pollute the project, doesn't pollute `~/.context-kit/`,
  doesn't require a settings file.

`--html-out PATH` is the explicit override. A user who wants the
report version-controlled inside their project (e.g.
`./docs/adopt-report.html`) can pass it. Default keeps the source
tree untouched.

### Test strategy

~10 focused tests, mirroring the wizard's HTML-load + grep-the-body
pattern (already in tests/test_wizard.py). Each runs against a tiny
fixture project under `tests/fixtures/adopt_html/...`.

| Test | Asserts |
|---|---|
| `--html` triggers a write to default path | file exists at expected location after dry-run |
| `--html-out PATH` writes to that path | exact path control |
| Re-run overwrites (doesn't accumulate) | file size / mtime changes, no second file appears |
| HTML contains project name, classification line, all unclassified subdir names | visibility coverage |
| HTML escapes user-supplied content (description, next_step) | XSS safety on user input |
| `--html` co-exists with `--write` | both behaviors fire, exit 0 |
| CLI dry-run stdout unchanged when `--html` also passed | additivity contract |
| Clean classified project's HTML omits "Unknown but present" section | no noise on tidy projects |
| HTML's CTA reads "Run with --write" when no placeholders in the plan | happy path |
| HTML's CTA reads "Fill in placeholders first" when placeholders exist | guard rail |
| `--no-browser` suppresses the `webbrowser.open()` call | tests + CI safety |

### Risks of overbuilding (the "do not build" list)

These are seven concrete risks observed during design. Future
implementation should re-read before adding anything.

1. **JS framework / build pipeline.** Hard rule: vanilla JS only,
   inline. Same as the wizard.
2. **Server-backed interactivity.** "Click to apply only part of
   the plan", "edit and save back" — both require HTTP endpoints
   and break the dry-run contract.
3. **Auto-refresh / websockets.** Adopt is one-shot. Real-time is
   the wrong frame.
4. **Wizard integration via the back door.** §15 backlog item #6
   says wizard branch is deferred. Don't sneak it in via the
   report.
5. **"Looks professional" trap.** The wizard's HTML is intentionally
   not a designer's portfolio. Match that aesthetic, don't
   over-style.
6. **PDF / screenshot / "share report" features.** Each adds
   dependencies, hosting concerns, or scope. None help the user
   answer "what does adopt see in my project?"
7. **Visualization for visualization's sake.** Dependency graphs,
   file-count pie charts, etc. — tempting but distract from the
   core question. Tables and lists are enough.

### MVP scope (write this down before coding)

**Build:**
- `--html` flag on `context-kit adopt`
- Default output `/tmp/contextkit-adopt-report-<short-hash-of-cwd>.html`
- `--html-out PATH` for explicit destination
- `--no-browser` flag
- Single self-contained HTML file; inline CSS + vanilla JS for
  collapse / copy only
- The six sections above, with **unknown-but-present as the
  primary visual focus**
- Auto-open via `webbrowser.open()` unless `--no-browser`
- ~10 focused tests

**Explicitly do NOT build:**

- ❌ Wizard branch / `context-kit start` adopt mode
- ❌ Any HTTP endpoints
- ❌ Real-time / websockets / auto-refresh
- ❌ Edit-in-browser / save-back
- ❌ "Apply partial plan" controls
- ❌ JS framework / npm dependencies / build step
- ❌ PDF / screenshot / share features
- ❌ Visualization beyond tables / lists / badges
- ❌ Cache / metadata files inside the project
- ❌ Authentication or hosting concerns

### Cost estimate

~300 LOC for the renderer + ~100 LOC of inline CSS + 10 tests.
One focused session. The renderer is a pure function from
`StackProfile` + `AdoptionInputs` → `str` (mirrors the existing
markdown generators), so testability is straightforward.

### Implementation note (when v0.3 starts)

The renderer should consume `StackProfile` through its public
attributes only — no reaching into private fields, no shape
assumptions beyond what `cli/adopt.py` declares in its dataclasses.
If `UnclassifiedSubdir` gains or loses a field, the renderer
should fail loudly (raise on unknown shape) rather than silently
render the wrong thing. This is the same contract the wizard's
renderer respects against `_render_html`'s callers.

### What this is NOT

- Not a wizard step. The wizard remains from-scratch oriented.
- Not a server feature. No `context-kit start` involvement.
- Not a project-state UI. It only shows what *one adopt run* sees.
  History / diff between adopt runs is out of scope.
- Not a substitute for the CLI dry-run. The plain text output
  stays intact and is the primary scripting / CI path.

### Where this slots into the v0.3 plan

This is design for v0.3 (or v0.2.1 if shipped on its own without
other changes). The visibility-first scan (§19) in v0.2 produced
the data; this section proposes how to make that data scannable.
It's orthogonal to the rest of the v0.2 backlog (§15 items #3 –
#9): independent ship, doesn't block any of them.

## 22. Proposed v0.3 failure label: MONOREPO_DEPTH_LIMIT

> **Status:** design proposal, not yet implemented. Added 2026-04-26
> after the first batch of `context-kit-dogfood-repos` (5 cloned
> open-source projects: expo-monorepo-example, flutter-monorepo-example,
> fns-monorepo, solidity-template, turborepo-next-django-starter)
> exposed a category the v0.2.x failure taxonomy doesn't cover.
> No code in this commit.

### Origin

Three of the five clones (expo, fns, turborepo-next-django) are
Turborepo / pnpm-workspace shapes where the actual project boundaries
live at depth 2 under `apps/<name>/` or `packages/<name>/`. Adopt's
depth-1 scan can see the parent `apps/` directory and (via the
depth-2 source-extension walk) can count files inside, but it
cannot see that `apps/forge/` is a Foundry Solidity project and
`apps/next/` is a Next.js app — those project boundaries collapse
into a single `apps/` aggregate.

The most damning case: **fns-monorepo emits 0 failure records**
even though it contains 29 Solidity files plus a Foundry config
buried at `apps/forge/foundry.toml`. None of the existing v0.2.x
labels (ROOT_SIGNAL_OVERRIDE, MISLEADING_CLASSIFICATION,
MISSING_FRAMEWORK_DETECTION, etc.) fire because every detector
operates on data populated by the depth-1 scan, and `apps/forge/`
is depth 2.

This is the failure-taxonomy equivalent of §15 backlog item #3
(apps/<name>/ Turborepo walking). The two need to ship together:
backlog #3 surfaces the child workspaces in StackProfile;
MONOREPO_DEPTH_LIMIT labels the gap until they're surfaced, and
also stays useful afterward for monorepo shapes that exceed
whatever depth limit v0.3 picks.

### Proposed label spec

| Field | Value |
|---|---|
| `failure_type` | `MONOREPO_DEPTH_LIMIT` |
| `severity` | `high` |
| `surface_area` | `visibility` |
| Trigger | A non-noise depth-1 subdir whose name is in the workspace-container set (`apps`, `packages`, `services`, `crates`, `members`, `workspaces`) AND has substantial content (≥10 source files via the existing depth-2 walk OR ≥1 manifest visible at depth 2) AND adopt has not classified anything inside it. |
| Description template | `<name>/` is a workspace container with N child projects adopt's depth-1 scan can't enter. Real classification is hidden behind one or more `<name>/<sub>/` manifest files. |
| `detected_in` | the workspace container's name (`apps`, `packages`, etc.) |
| `example` | one example child path adopt found (e.g. `apps/forge/foundry.toml`) |

The detector should fire **once per workspace-container subdir**, not
once per child project, to avoid the 70-card explosion problem.

### Primary fixture: fns-monorepo

A real project at `/Users/donkeyking/development/context-kit-dogfood-repos/fns-monorepo`.
The Filecoin Name Service Turborepo: a Solidity Foundry contracts
project and a Next.js dApp frontend coexisting in one workspace.

**What's actually there:**

```
fns-monorepo/
├── package.json          ← root (Turborepo orchestration)
├── pnpm-workspace.yaml
├── turbo.json
├── apps/
│   ├── forge/
│   │   ├── package.json     ← Node tooling for Foundry
│   │   └── foundry.toml     ← THE Solidity project manifest
│   └── next/
│       └── package.json     ← Next.js / React dApp
└── ens-contracts/        ← uninitialized git submodule (empty)
```

29 `.sol` files live under `apps/forge/` and 7+ `.tsx`/`.ts` files
live under `apps/next/`. Everything load-bearing is at depth 2.

**Current adopt v0.2.x behavior (zero failure labels):**

```
Detected stack: JavaScript / Node.js (detected from package.json)

Unknown but present (depth 1):
  apps/  source: 29 .sol files (e.g. apps/forge/flattened/...Flattened.sol)
                 7 .tsx files (e.g. apps/next/components/DomainSelect.tsx)
                 3 .js files (e.g. apps/next/tailwind.config.js)
                 3 .ts files (e.g. apps/next/lib/testkeys.ts)
         note:   .sol files suggest Solidity / EVM smart contracts; verify with user
  ens-contracts/  empty
```

The `.sol` hint fires (visibility-first works), but no FailureRecord
labels the depth-2 invisibility. An AI session reading this would
have no structured signal that there's a complete Foundry project
and a complete Next.js app inside `apps/`.

**Desired v0.3 behavior with MONOREPO_DEPTH_LIMIT:**

```
Detected stack: JavaScript / Node.js (detected from package.json)

Unknown but present (depth 1):
  apps/  ... [same as today] ...

Detected issues (1):
  high   MONOREPO_DEPTH_LIMIT   apps  (apps/forge/foundry.toml)
```

Description text in the report:
> `apps/` is a workspace container with at least 2 child projects
> adopt's depth-1 scan can't enter. Real classification is hidden
> behind `apps/forge/foundry.toml` and `apps/next/package.json`.
> Plan to ship §15 backlog item #3 (apps/<name>/ walking) to
> classify each child project individually.

### Other v0.3 fixture targets from the same dogfood batch

**`expo-monorepo-example`** — Turborepo + Expo. `apps/example/` is a
real Expo app with `package.json` + `app.config.*`. Same depth-2
invisibility as fns-monorepo but with only one child workspace.
v0.2.x emits **0 failure labels**. v0.3 should emit
MONOREPO_DEPTH_LIMIT for `apps/`.

**`turborepo-next-django-starter`** — Turborepo + Django + Next.js.
v0.2.x correctly emits SILENT_SUBDIR_DROP for `server/` (Django
backend at `server/backend/manage.py` — recognized subdir name
catches it). But `apps/web/` and `apps/docs/` are both real Next.js
apps invisible behind the `apps/` aggregate. v0.3 should emit
MONOREPO_DEPTH_LIMIT for `apps/` AND keep the existing
SILENT_SUBDIR_DROP for `server/`.

**`flutter-monorepo-example`** — Melos-based Flutter monorepo.
`apps/buyer_app/` and `apps/seller_app/` are two complete Flutter
apps with their own `pubspec.yaml` files, invisible behind `apps/`.
v0.3 should emit MONOREPO_DEPTH_LIMIT here too. Currently emits
only one label: `UNRECOGNIZED_ECOSYSTEM` for `shared/pubspec.yaml`.

### Related backlog note: root-level UNRECOGNIZED_ECOSYSTEM gap

The flutter-monorepo case also exposed a smaller, distinct gap in
the existing `UNRECOGNIZED_ECOSYSTEM` detector: it only fires for
**subdir** manifests (entries in `unclassified_subdirs[*].manifest_files`),
never for **root-level** ecosystem manifests like `melos.yaml`.

Concrete: `flutter-monorepo-example/melos.yaml` at root is a
Dart-ecosystem monorepo manifest. Adopt sees it (it matches the
manifest-shaped pattern), but classification doesn't recognize it
and the failure detector doesn't label it because the detector
loop is `for u in stack.unclassified_subdirs: for m in
u.manifest_files: ...` — root-level manifest_files aren't checked.

**Proposed minor extension to the existing detector** (not a new
label): also scan root for filenames in `_ECOSYSTEM_MANIFESTS` and
emit `UNRECOGNIZED_ECOSYSTEM` with `detected_in="root"` when found.
Same severity/surface as the existing rule. Would catch:
- `melos.yaml` (Dart/Flutter)
- A future root-level `pubspec.yaml` for a single-package Dart project
- Root `Cargo.toml` in a single-crate Rust project that adopt also doesn't classify

This is a one-liner change plus a small data-table consideration
(`melos.yaml` would need to enter `_ECOSYSTEM_MANIFESTS`). Tracked
here so it ships alongside or before the MONOREPO_DEPTH_LIMIT work.

### Acceptance criteria for v0.3 MONOREPO_DEPTH_LIMIT

- [ ] `analyze_failures` emits at least one MONOREPO_DEPTH_LIMIT
      record for fns-monorepo, with `detected_in="apps"` and
      `example` naming a real depth-2 file (foundry.toml,
      package.json, or a .sol path).
- [ ] Same label fires for expo-monorepo-example,
      turborepo-next-django-starter, and flutter-monorepo-example.
- [ ] Label does NOT fire when a workspace-container subdir
      (`apps/`, `packages/`) is present but EMPTY (e.g. an
      uninitialized `apps/` placeholder dir). Threshold prevents
      false positives.
- [ ] Label fires AT MOST ONCE per workspace-container subdir
      (no per-child explosion on a 20-app Turborepo).
- [ ] Existing labels keep firing as before — MONOREPO_DEPTH_LIMIT
      is additive, not a replacement.
- [ ] HTML "Detected issues" section renders the new label with
      severity badge `sev-high` (red).
- [ ] CLI compact summary shows it with severity `high`.
- [ ] When v0.3 ALSO ships §15 #3 (apps/<name>/ walking), the
      classifier should populate child workspaces into
      `StackProfile.parts`; MONOREPO_DEPTH_LIMIT then keeps firing
      only when the workspace contains content the deeper walk
      itself didn't reach (genuinely deeper-than-2 layouts).

### Implementation sketch

Detector fits the same shape as the other rules in
`analyze_failures`:

```python
_WORKSPACE_CONTAINERS = frozenset({
    "apps", "packages", "services", "crates", "members", "workspaces",
})
_MONOREPO_DEPTH_FILE_THRESHOLD = 10  # same shape as STRUCTURE_UNDERREPRESENTED

for u in stack.unclassified_subdirs:
    if u.name not in _WORKSPACE_CONTAINERS:
        continue
    # Substantial content threshold: either the depth-2 walk found
    # ≥10 source files (collapsed across children), or it found at
    # least one example_path that looks like a child manifest.
    has_files = sum(u.notable_extensions.values()) >= _MONOREPO_DEPTH_FILE_THRESHOLD
    has_child_manifest = any(
        "/" in path  # depth-2 path implies a child subdir
        for path in u.example_paths.values()
    )
    if not (has_files or has_child_manifest):
        continue
    example = next(iter(u.example_paths.values()), u.name + "/")
    out.append(FailureRecord(
        failure_type=FAILURE_MONOREPO_DEPTH_LIMIT,
        severity="high",
        surface_area="visibility",
        description=(
            f"{u.name}/ is a workspace container — adopt's depth-1 "
            f"scan saw the directory and (via the depth-2 source walk) "
            f"counted files inside, but the individual child projects "
            f"under {u.name}/<name>/ are invisible to classification. "
            f"Likely to contain real package.json / foundry.toml / "
            f"pubspec.yaml manifests adopt cannot reach yet."
        ),
        detected_in=u.name,
        example=example,
    ))
```

Code cost: ~30 LOC + the constant. Tests: ~5 (one per fixture
shape, plus a negative test for empty `apps/`).

### Why a new label vs. extending an existing one

Considered extending `STRUCTURE_UNDERREPRESENTED` to also fire on
this case. Rejected because the two failure modes are
qualitatively different:

- `STRUCTURE_UNDERREPRESENTED` — many subdirs at depth 1 with real
  signal, but few classified into `parts`. The fix is "classify
  more of them at depth 1."
- `MONOREPO_DEPTH_LIMIT` — one or two depth-1 subdirs whose REAL
  content lives at depth 2 inside a known workspace shape. The fix
  is "walk one level deeper inside known workspace containers."

Different causes, different remedies, different scopes. Worth a
distinct label so the user / AI session reading the report knows
which gap the project hits.

### Current taxonomy after this addition

If MONOREPO_DEPTH_LIMIT ships, the v0.3 taxonomy goes from 9 types
to 10. Same closed-set pattern; ``FAILURE_TYPES`` frozenset gains
one entry; no other changes to the core data structures.

The other v0.2.x labels stay at their current severity / surface
assignments. No reorganization needed.
