---
title: "Session 009 — adopt (retrofit context-kit onto an existing project)"
date: 2026-04-26
status: design
authors: chris@donkeybetz.com, claude (claude-opus-4-7)
---

# Session 009 — `context-kit adopt`

**Status:** design proposal, not yet implemented. Written for joint
review with ChatGPT and dogfood against existing projects under
`/development/` before implementation.

> **Reviewers:** focus pushback on §3 (the detection ladder), §5
> (managed-block strategy for non-empty repos), §7 (the
> `[adopt: please describe]` placeholder contract), and §10 (test
> strategy). The other sections are mostly mechanical.

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

*End of design proposal. Ready for ChatGPT review and joint
sign-off before implementation.*
