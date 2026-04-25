# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. Most recent `docs/handoffs/SESSION_NNN_*.md`
> 4. `docs/LAUNCH_FEEDBACK.md` — running feedback log (live)
>
> When any other doc disagrees with the above, the above wins.

---

## What just shipped

`contextkit-ai 0.4.2` is live on PyPI. The `init / seed / orient`
loop is the shippable shape of the tool now.

Recent commit history (latest first):

- `chore(release): bump to 0.4.2` — version bump; 0.4.1 was already
  published without `seed` and PyPI versions are immutable, so seed
  ships in 0.4.2.
- `docs: position seed in launch + log estimation calibration` —
  README + DISTRIBUTION_NOTES updated with the three-line positioning;
  TRUST_CALIBRATION gains an entry on AI-paced estimates being too
  high when design is locked.
- `feat(seed): generate project context from idea files` — the
  Session 5 feature. 5 target files, managed-block markers, schema
  documented at `cli/_pattern/IDEA_SCHEMA.md`. 34 new tests.
- `chore(packaging): rename PyPI distribution to contextkit-ai` —
  the unsuffixed `context-kit` name was rejected.
- `feat(packaging): make wheel installable` — Session 4 work; assets
  moved inside `cli/` as package data, bootstrap reads via
  `importlib.resources`.

127/127 tests passing. Clean-venv install of the live PyPI wheel
verified end-to-end (init → seed → orient).

See the SESSION_NNN_*.md handoffs in `docs/handoffs/` for full
context. The latest is Session 4 (`SESSION_004_PYPI_PREP.md`); a
Session 5 handoff is queued for the next session that does
non-launch work.

---

## MODE: launch watch (still)

PyPI publish was infrastructure for the launch, not new product
scope. We remain in launch-watch mode: **no new build work until
3-5 real feedback signals are in.** Decision gate is in
`docs/LAUNCH_FEEDBACK.md`.

---

## What the human is doing (off-keyboard, in order)

### Done

- ✅ `pip install contextkit-ai` is live on PyPI as **0.4.2**.
- ✅ Tags `v0.4.1` and `v0.4.2` pushed.
- ✅ GitHub release v0.4.2 published:
  https://github.com/clwest/context-kit/releases/tag/v0.4.2
- ✅ All launch copy in `docs/DISTRIBUTION_NOTES.md` reflects the
  shipped state.

### Now: the public launch

1. **Reply** to Damian, Brian, Austin under their original LinkedIn
   comments using the snippets in `DISTRIBUTION_NOTES.md`. Edit to
   your voice. Include the demo (asciinema cast or screen recording
   of `examples/demo.sh`) if you have one.
2. **Wait ~24h.** Read whatever comes back.
3. **Post** the long-form LinkedIn update (draft in
   `DISTRIBUTION_NOTES.md` — leads with the `init / seed / orient`
   loop and the live install).
4. **Wait ~24h.**
5. **Post** the X/Twitter thread (6 tweets, draft in
   `DISTRIBUTION_NOTES.md`).

---

## What I can do (on-keyboard) once feedback arrives

- Open a GitHub issue for any signal you paste me, with the right
  label (`drift` / `onboarding` / `confusion` / `missing-feature` /
  `dogfood` / `feedback`).
- Append to `LAUNCH_FEEDBACK.md` with source + paraphrase + my read.
- Reproduce reported bugs against a clean wheel install (now
  trivially possible: build wheel → install in venv → run failing
  command).
- Help draft replies (you send them).

---

## What we are NOT doing

- Not building new features. Not even small ones. Not even
  PyPI-related ones unless the publish itself fails.
- Not refactoring "while we're here."
- Not polishing the README again.
- Anything tempting goes to "Queued for after the recap" below.

---

## Queued for after the recap

- **CI install matrix.** Add a workflow step that builds the wheel
  and installs it in a clean venv on every PR. Catches packaging
  regressions before they hit users.
- **`tests` to `PATTERN_EXCLUDES`.** Now obsolete — the new
  bootstrap reads from `cli/_pattern/` only, so tests can't leak in.
  Removable as a queued item.
- **Wire `inventory --check` into CI.** Failing build = drift between
  code and inventory in the same commit.
- **Pre-commit hook for inventory currency.**
- **`_cli_subcommands` introspection of generated projects' own
  entry script.**

---

## AI / Assistant Context

- Sessions 1-4 followed the pattern. Session 4 broke the
  launch-watch rule on purpose (PyPI is universal onboarding
  friction, not feature scope) and that was the right call.
- `docs/TRUST_CALIBRATION.md` now has 2 entries. Re-read both
  before any future estimation, especially if you catch yourself
  unconsciously quoting human-paced timelines.
