# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (manual stub for now)
> 3. Most recent `docs/handoffs/SESSION_NNN_*.md`
>
> When any other doc disagrees with the above, the above wins.

---

## What just shipped (Session 1)

Three commits on `main` (not yet pushed):

- `5cf4a86 feat(orient)` — `context-kit orient` assembles session-start
  context (start-here, anchors, latest handoff, pattern pointers) into a
  single plain-text report. The "single authoritative path."
- `a1bb7cc feat(skill)` — Claude Code skill at
  `skills/context-kit/SKILL.md`, copied into every generated project at
  `.claude/skills/context-kit/SKILL.md`.
- `d1ed2d1 feat(hotpath)` — read-only file-size dashboard. Warns when
  any file exceeds 50 KB or top-10 sum exceeds 200 KB (both tunable).

69/69 tests passing. See `docs/handoffs/SESSION_001_INITIAL.md` for
detail and AI notes.

This session also added the dogfood scaffold (this file plus the docs
under `docs/`) so context-kit follows its own pattern.

---

## SESSION 2 — START HERE

### FIRST THING — Pick one

Three remaining items from the LinkedIn-feedback punch list, plus a
dogfood follow-up. They're independent — pick whichever fits your
appetite for the session.

### Option A — Distribution (Austin's #2)

1. Decide on package name on PyPI (`context-kit` is preferred; check
   availability with `pip index versions context-kit`).
2. Move `starter/` and the guide docs (`01_*.md` … `08_*.md`) inside the
   `cli/` package as `package_data` so wheel installs work end-to-end
   (currently editable installs only — see `pyproject.toml` notes).
3. Test wheel build locally: `python3 -m build && pipx install ./dist/context-kit-*.whl`.
4. Publish to TestPyPI, then PyPI.

### Option B — Tweet-able demo + GitHub feedback loop

1. Record a 30-second screen capture: `init` → `orient` → agent loads
   skill → behaves correctly.
2. Add `.github/ISSUE_TEMPLATE/` with two templates: "Where it broke"
   and "Pattern question."
3. Draft the tweet text (probably one tight thread, not a one-shot).

### Option C — Reply to Damian and Brian on LinkedIn

Both deserve a real follow-up that what they said is now in code. Damian
especially — `hotpath` is essentially his idea.

### Option D — Real inventory generator (close the dogfood loop)

`docs/CONTEXT_KIT_INVENTORY.md` is currently hand-maintained and
labeled as such. Build a small Python script (`scaffold/python/...` or
under a new `tools/` dir) that counts CLI subcommands, guide docs,
templates, starter files, tests, and skills, then regenerates
INVENTORY.md. This is the proof-of-concept for the drift verifier
pattern in our own repo.

### Rollback Criteria

None. All four options are additive.

---

## Queued Investigations

- `tests/` is not in `PATTERN_EXCLUDES` in `cli/bootstrap.py`, which
  means generated projects' `docs/docs-pattern/` includes our test
  files. Harmless but noisy. Worth fixing in a small follow-up.
- The Pyright "Import could not be resolved" warnings on new modules
  appear to be stale-cache; runtime imports work. If they persist,
  worth investigating editor config.

---

## AI / Assistant Context

- Session 1 was the first time this repo used its own pattern. Treat
  the dogfood scaffold (this file, `docs/CONTEXT_KIT_*.md`, the
  handoff) as load-bearing now — don't bypass.
- Collaboration conventions: `08_collaboration_roles.md`.
- Handoff `## AI Notes` section is required from every session forward.
- `docs/TRUST_CALIBRATION.md` is empty; first real calibration event
  (AI confidently wrong, right despite pushback, near-miss) gets
  logged there.
