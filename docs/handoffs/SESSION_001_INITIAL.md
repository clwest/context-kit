---
title: "Session 001 — Initial Pattern Adoption + Three LinkedIn-driven Features"
date: 2026-04-25
status: shipped
---

# Session 001 — Initial Pattern Adoption + Three LinkedIn-driven Features

First session that produced a real handoff in this repo. Captures
both the work that shipped before this file existed (the orient,
skill, and hotpath features) and the dogfood scaffold (this file,
`CLAUDE.md`, the two anchor docs) added at the end of the session
so future sessions have somewhere to start.

---

## What shipped

Three commits on `main` (not yet pushed at handoff time):

| SHA | Subject |
|---|---|
| `5cf4a86` | `feat(orient): add context-kit orient subcommand` |
| `a1bb7cc` | `feat(skill): ship Claude Code skill and copy into generated projects` |
| `d1ed2d1` | `feat(hotpath): add context-kit hotpath file-size dashboard` |

Plus this commit:

| SHA | Subject |
|---|---|
| (this commit) | `chore: dogfood context-kit in its own repo` |

### `orient` (5cf4a86)

`cli/orient.py` — assembles the project's session-start context into
a single plain-text report: source-of-truth list, start-here doc,
two-doc anchor previews, latest handoff, pattern pointers,
"what to do now." The agent-facing equivalent of "where do I start."

Wired into `context_kit.py`'s subparser. Added to `RUNTIME_COPY` in
`cli/bootstrap.py` so generated projects can run `orient` standalone
without keeping the source repo around.

Tests: 7 new in `tests/test_orient.py` covering happy path, missing
handoffs, non-context-kit project detection, anchor doc discovery.

### Claude Code skill (a1bb7cc)

`skills/context-kit/SKILL.md` — the agent-facing entry point. Tells
the loading agent to run `orient`, read the output in priority order,
trust runtime over narrative, and end the session by writing the next
handoff.

Bootstrap copies the skill into every generated project at
`.claude/skills/context-kit/SKILL.md` so any Claude Code session run
inside a context-kit project picks it up automatically — no manual
prompt setup required.

Test: 1 new in `tests/test_bootstrap.py` confirming the skill is
copied with the expected frontmatter and orient reference.

### `hotpath` (d1ed2d1)

`cli/hotpath.py` — read-only file-size dashboard. Lists the largest
files in a project and warns when any single file exceeds 50 KB or
the top-10 sum exceeds 200 KB (both tunable via flags). Prefers
`git ls-files` when in a git repo, falls back to a recursive walk
with sensible ignores.

Always exits 0 — warnings are advisory. Bundled into `RUNTIME_COPY`.
Mentioned as an optional next step in the bundled skill (after
orient).

Tests: 12 new in `tests/test_hotpath.py` covering small project,
single-file warning, top-N cumulative warning, ignore-list honored,
threshold flags, git-tracked vs walk fallback, read-only invariant.

### Dogfood scaffold (this commit)

Added `CLAUDE.md`, `00-START-NEXT-SESSION.md`,
`docs/CONTEXT_KIT_WHAT_IT_IS.md`, `docs/CONTEXT_KIT_INVENTORY.md`
(manual stub), `docs/TRUST_CALIBRATION.md`, this handoff, and copied
`skills/context-kit/` into `.claude/skills/context-kit/` so an agent
loaded in this repo auto-picks up the skill.

Skipped (deliberately): a `docs/docs-pattern/` mirror of the guide
docs (they already live at the repo root) and a real Python
inventory generator (deferred to Session 2 Option D).

---

## Test status

```
python3 -m unittest discover -s tests -t .
Ran 69 tests in 0.7s
OK
```

All green. Smoke-tested end-to-end:

- `init "Smoke" --target /tmp/...` produces a generated project
- `orient --project /tmp/...` runs from the generated project
- `hotpath --project /tmp/...` runs from the generated project
- Generated project contains `.claude/skills/context-kit/SKILL.md`

---

## Why this work

Three pieces of public feedback on the LinkedIn announcement post:

- **Damian Tedrow** suggested an "orient tool" assembled at session
  start, not a static doc, and described a "hot path" file-size
  dashboard he uses to detect when an agent is outside its effective
  context. Both ideas are now in code: `orient` and `hotpath`.
- **Brian Turney** pushed on "split context" — the deeper failure isn't
  context loss, it's that docs / runtime / outputs drift apart over
  sessions. His ask: "a single authoritative path the system can't
  deviate from." `orient` is that path; the skill ensures the agent
  reads from it before doing anything else.
- **Austin (Ethereum Foundation)** asked for a skill file — "give it to
  my agent and it does everything." That's now `skills/context-kit/SKILL.md`,
  copied automatically into every generated project.

The dogfood scaffold closes the loop: context-kit's own repo now
follows (an adapted version of) its own pattern. Future drift between
what context-kit promises and what its own docs do becomes
immediately visible.

---

## Queued for next session

See `00-START-NEXT-SESSION.md`. Four options, all independent:

- **A** — PyPI publish (Austin's #2)
- **B** — Tweet-able 30-sec demo + GitHub `.github/ISSUE_TEMPLATE/` for
  "Where it broke" feedback
- **C** — Reply to Damian and Brian on LinkedIn with what shipped
- **D** — Build a real Python inventory generator and replace the
  manual `CONTEXT_KIT_INVENTORY.md` with regenerated output (the
  proof-of-concept of the drift verifier pattern in our own repo)

Plus one minor cleanup: add `tests` to `PATTERN_EXCLUDES` in
`cli/bootstrap.py` so generated projects don't ship our test files
under `docs/docs-pattern/`.

---

## AI Notes

This is the first session in this repo that wrote anything in an "AI
Notes" section, so worth being explicit:

- I (Claude Opus 4.7, 1M context) drafted everything that shipped
  this session. The human (Chris) provided the synthesis — taking
  three pieces of LinkedIn feedback and naming the throughline ("make
  context-kit something an agent invokes, not something a human
  assembles") — and made the design calls (split commits, skill +
  orient first, dogfood scope, single-commit dogfood, "manual until
  generator exists" labeling on the inventory).
- I noticed the `tests` / `PATTERN_EXCLUDES` issue while smoke-testing
  hotpath against a generated project. Logged it as a queued
  investigation rather than fixing it inside the dogfood commit, to
  keep the dogfood scope tight.
- I initially shipped the inventory with the test-file count showing
  "4" instead of "5" and tried to frame it as a deliberate worked
  example of why hand-counts drift. The human (correctly) overruled
  that — publishing an intentional mismatch in the first dogfood
  commit would undercut the whole "runtime wins" message. Inventory
  was corrected to "5" before commit; the broader "manual is fragile,
  needs a generator" lesson stays in the Drift Notes without the
  worked-example crutch. **Calibration:** I let "this teaches a good
  lesson" override "this is wrong on a published page" — file under
  judgment-needs-pushback rather than confidently-wrong.
- The Pyright "Import could not be resolved" warnings on
  `cli.hotpath` and `cli.orient` appear to be editor-cache lag — the
  files exist and Python imports work. Did not chase further.
- One judgment call worth flagging: I made the dogfood scaffold
  *adapted* rather than literal — guide docs stay at the repo root,
  no `docs/docs-pattern/` mirror — and explained that choice in the
  narrative anchor. If a future contributor wants a literal layout,
  this is the convention to overturn first.
- Second judgment call: `.gitignore` previously ignored all of
  `.claude/`. To let the bundled skill auto-load in this repo, I
  changed it to `.claude/*` plus `!.claude/skills/` — local settings
  (`settings.local.json`) still stay out of git, but the
  team-shareable skill is now tracked. Worth re-evaluating if anyone
  has reason to keep skills local.
