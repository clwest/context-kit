# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. Most recent `docs/handoffs/SESSION_NNN_*.md`
> 4. `docs/LAUNCH_FEEDBACK.md` — running feedback log (live)
>
> When any other doc disagrees with the above, the above wins.

---

## What just shipped (Session 4 — on branch `pypi-prep`)

- `feat(packaging): make wheel installable` — bump 0.3.0 → 0.4.0.
  All starter, pattern, and skill assets moved into `cli/_starter/`,
  `cli/_pattern/`, `cli/_skills/` as package data. Bootstrap reads
  via `importlib.resources` — same code path for editable and wheel
  installs.
- `pip install context-kit` works end-to-end after the human
  publishes to PyPI (see manual steps below).
- TRUST_CALIBRATION entry added: AI was estimating implementation
  work in human time instead of AI execution time. Future estimates
  distinguish the two.
- 92/92 tests passing. Clean-venv wheel smoke test green: install
  → `init` → 29-file generated project with no `__pycache__`
  leakage → `orient`/`hotpath`/`inventory` all run inside the
  generated project.

See `docs/handoffs/SESSION_004_PYPI_PREP.md` for full detail.

---

## MODE: launch watch (still)

PyPI prep was plumbing for the launch, not new product scope. We
remain in launch-watch mode: **no new build work until 3-5 real
feedback signals are in.** Decision gate is in
`docs/LAUNCH_FEEDBACK.md`.

---

## What the human is doing (off-keyboard, in order)

### Now: merge `pypi-prep` and publish

1. Push `pypi-prep`, optionally open a PR for self-review, then
   merge to `main`.
2. **Verify the package name is available:**
   ```bash
   pip index versions context-kit
   ```
3. **Build a fresh wheel from main:**
   ```bash
   git checkout main && git pull
   rm -rf dist build
   python3 -m build
   ```
4. **TestPyPI dry-run** (recommended before real PyPI):
   ```bash
   pip install --upgrade twine
   python3 -m twine upload --repository testpypi dist/*
   ```
   You'll need a TestPyPI account + API token in `~/.pypirc`.
5. **Verify TestPyPI install** in a fresh venv:
   ```bash
   python3 -m venv /tmp/test-pypi
   /tmp/test-pypi/bin/pip install \
       --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ \
       context-kit
   /tmp/test-pypi/bin/context-kit init "Test PyPI" --target /tmp/tp
   ```
6. **Real PyPI publish:**
   ```bash
   python3 -m twine upload dist/*
   ```
7. **Tag and push:**
   ```bash
   git tag v0.4.0 && git push --tags
   ```
8. **Update `docs/DISTRIBUTION_NOTES.md`** — change "coming soon to
   PyPI" to "now on PyPI." Then push.

### Then: the launch (unchanged from Session 3)

9. Reply to Damian, Brian, Austin under their original LinkedIn
   comments using the snippets in `DISTRIBUTION_NOTES.md`.
10. Wait ~24h.
11. Post the long-form LinkedIn update (now with `pip install
    context-kit` baked in).
12. Wait ~24h.
13. Post the X/Twitter thread.

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
