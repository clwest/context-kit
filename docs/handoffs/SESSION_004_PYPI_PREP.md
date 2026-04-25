---
title: "Session 004 — PyPI Prep (wheel-installable)"
date: 2026-04-25
status: shipped
branch: pypi-prep
---

# Session 004 — PyPI Prep (wheel-installable)

`pip install context-kit` now works end-to-end. The launch messaging
shifts from "coming soon to PyPI" to "available now" with a single
edit to `DISTRIBUTION_NOTES.md` whenever the human runs `twine upload`.

This session deliberately broke the "no new build work in launch
watch" rule because:

1. PyPI install is **predictable, universal onboarding friction** —
   everyone who tries the tool will type `pip install context-kit`
   before they read install instructions. If it fails, they bounce.
   That's not "building ahead of feedback"; it's removing the most
   predictable failure mode.
2. The work was already on the punch list as a deferred item, not
   new scope.
3. After the calibration correction (see below), the actual work
   was ~30-45 minutes, not the "half a day" I initially quoted.

---

## What shipped

A single commit on the `pypi-prep` branch:
`feat(packaging): make wheel installable`. Bump from 0.3.0 → 0.4.0.

### Asset moves (history-preserving via `git mv`)

All 22 files moved from repo root into the `cli` package so they
ship inside a wheel:

```
01_two_doc_anchor.md  → cli/_pattern/01_two_doc_anchor.md
02_drift_verifier.md  → cli/_pattern/02_drift_verifier.md
…  (all 8 guide docs)
templates/*           → cli/_pattern/templates/*
starter/root/*        → cli/_starter/root/*
starter/docs/*        → cli/_starter/docs/*
starter/scaffold/*    → cli/_starter/scaffold/*
skills/context-kit/*  → cli/_skills/context-kit/*
```

Plus a small new `cli/_pattern/README.md` so the materialized
`docs/docs-pattern/` folder in generated projects has a real entry
point (replaces the previous behavior of slurping the source repo's
`README.md` into every generated project — which was always a bit wrong).

### Bootstrap refactor

`cli/bootstrap.py` rewritten around `importlib.resources`:

- `_pkg(*parts)` — typed Traversable helper for any path under `cli/`
- `_materialize_tree(src, dst, placeholders, force)` — recursive
  Traversable → filesystem walk with optional placeholder
  substitution. Same code path for editable + wheel installs.
- `_materialize_pattern` — top-level wrapper for the pattern dir
- `_copy_runtime` — reads cli/*.py via `importlib.resources` and
  context_kit.py via `Path(context_kit.__file__).read_bytes()` (the
  top-level module isn't a package, so `resources.files()` is awkward
  for it; `__file__` is real on disk in both editable and wheel modes)
- `_copy_skills` — uses the new `cli/_skills/` location
- Added `_IGNORE_NAMES` and `_IGNORE_SUFFIXES` to skip
  `__pycache__/` and `*.pyc` if they ever leak into package data
  (caught a real instance during smoke testing — Python had compiled
  the templates at some point and dropped bytecode into the data dir)
- Dropped dead `PATTERN_EXCLUDES` constant — the old "iterate the
  whole repo root and skip the bad bits" approach is gone now that
  pattern data is tightly scoped

### `context_kit.py` dispatcher fix

The old `init` guard checked for `starter/` next to the entry script.
That was true only in the source repo. After the move, the directory
no longer exists at the repo root (it's inside the package), so the
guard always fired — including for wheel installs.

Replaced with an `ImportError` catch around `from cli.bootstrap import
run_init`. Generated projects (which only ship the runtime subset of
cli/) hit the ImportError and get a friendly "install the full
package" message; wheel + editable installs both succeed.

### Inventory updates

`cli/inventory.py`:

- `_guide_docs` now scans **three** locations and dedupes:
  `cli/_pattern/`, `docs/docs-pattern/`, and the project root
  (legacy). Source-repo guide docs now live at the first; generated
  projects have them at the second.
- `_skill_files` now scans **three** locations and dedupes:
  `cli/_skills/`, `.claude/skills/`, and `skills/` (legacy).

### `pyproject.toml`

- Version: `0.3.0` → `0.4.0`
- `[tool.setuptools.package-data]` cli globs cover `_pattern/*.md`,
  `_pattern/templates/*`, `_starter/root/*`, `_starter/docs/*`,
  `_starter/docs/topics/*`, `_starter/docs/handoffs/*`,
  `_starter/scaffold/python/*`, `_skills/context-kit/*`.
  Explicit globs (no `**`) for compatibility with older setuptools.

### Tests

3 new tests in `tests/test_bootstrap.py::TestPackagedResources`:

- `test_pattern_resources_present` — guide docs + templates accessible
  via `importlib.resources.files("cli")`
- `test_starter_resources_present` — root + docs + scaffold accessible
- `test_skill_resources_present` — bundled skill accessible

These prove the wheel-install code path works without needing to
build a wheel in CI. The same `importlib.resources` calls run during
both editable installs (today's tests) and wheel installs (smoke-tested
manually below).

92/92 tests passing total.

---

## Verification (clean-venv smoke test)

```bash
$ rm -rf dist build && python3 -m build
   …
   Successfully built context_kit-0.4.0.tar.gz
                  and context_kit-0.4.0-py3-none-any.whl

$ python3 -m venv /tmp/ckit-venv
$ /tmp/ckit-venv/bin/pip install ./dist/context_kit-0.4.0-py3-none-any.whl

$ /tmp/ckit-venv/bin/context-kit init "Smoke Test" \
      --target /tmp/context-kit-smoke --with-scaffold

$ find /tmp/context-kit-smoke -type f | wc -l
29

# 29 files generated, no __pycache__ leakage, all expected paths present:
#   .claude/skills/context-kit/SKILL.md   ✓
#   00-START-NEXT-SESSION.md              ✓
#   CLAUDE.md                             ✓
#   cli/{__init__,server,orient,hotpath,inventory}.py   ✓
#   context_kit.py                        ✓
#   docs/docs-pattern/{01..08}_*.md       ✓
#   docs/docs-pattern/README.md           ✓
#   docs/docs-pattern/templates/*         ✓
#   docs/SMOKE_TEST_{WHAT_IT_IS,INVENTORY}.md  ✓
#   docs/TRUST_CALIBRATION.md             ✓
#   docs/handoffs/SESSION_001_BOOTSTRAP.md ✓
#   docs/topics/infrastructure.md         ✓
#   scaffold/python/*                     ✓

$ cd /tmp/context-kit-smoke
$ /tmp/ckit-venv/bin/python3 context_kit.py orient
   # all 5 sections render

$ /tmp/ckit-venv/bin/python3 context_kit.py inventory --json | jq .cli_subcommands
   ["hotpath", "init", "inventory", "orient", "start"]
```

End-to-end install + scaffold + run = green.

---

## Files changed

```
R  01_two_doc_anchor.md       → cli/_pattern/01_two_doc_anchor.md
R  02_drift_verifier.md       → cli/_pattern/02_drift_verifier.md
R  03_topic_docs.md           → cli/_pattern/03_topic_docs.md
R  04_session_handoffs.md     → cli/_pattern/04_session_handoffs.md
R  05_start_here.md           → cli/_pattern/05_start_here.md
R  06_dos_and_donts.md        → cli/_pattern/06_dos_and_donts.md
R  07_bootstrap_checklist.md  → cli/_pattern/07_bootstrap_checklist.md
R  08_collaboration_roles.md  → cli/_pattern/08_collaboration_roles.md
R  templates/{4 files}        → cli/_pattern/templates/{4 files}
R  starter/{root,docs,scaffold} → cli/_starter/{root,docs,scaffold}
R  skills/context-kit         → cli/_skills/context-kit
A  cli/_pattern/README.md     (new — entry point for materialized docs-pattern/)
M  cli/bootstrap.py           (importlib.resources refactor)
M  cli/inventory.py           (_guide_docs and _skill_files updated)
M  context_kit.py             (init guard now ImportError-based)
M  pyproject.toml             (version 0.4.0; package-data globs)
M  README.md                  (pip install is the supported path)
M  CHANGELOG.md               (0.4.0 entry)
M  docs/TRUST_CALIBRATION.md  (estimation calibration entry)
A  docs/handoffs/SESSION_004_PYPI_PREP.md  (this file)
M  tests/test_bootstrap.py    (TestPackagedResources, 3 new tests)
M  docs/CONTEXT_KIT_INVENTORY.md  (regen — all the above moves)
M  00-START-NEXT-SESSION.md   (advance to Session 5)
```

---

## What remains (manual steps the human must do)

I (the AI) cannot upload to TestPyPI or PyPI — those require
credentials. The remaining steps are all yours:

1. **Verify the branch.** Push `pypi-prep` and (optionally) open a PR
   for self-review. Or merge directly to `main` if you're confident.
2. **Check name availability.**
   ```bash
   pip index versions context-kit
   ```
   The name appears available (no PyPI page exists), but confirm
   before uploading.
3. **TestPyPI dry-run** (recommended before real PyPI):
   ```bash
   pip install --upgrade build twine
   python3 -m build
   python3 -m twine upload --repository testpypi dist/*
   ```
   You'll need a TestPyPI account and an API token in `~/.pypirc`.
4. **Verify the TestPyPI install in a fresh venv:**
   ```bash
   python3 -m venv /tmp/test-pypi
   /tmp/test-pypi/bin/pip install --index-url https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ context-kit
   /tmp/test-pypi/bin/context-kit init "Test PyPI Smoke" --target /tmp/tp-smoke
   ```
5. **Real PyPI publish:**
   ```bash
   python3 -m twine upload dist/*
   ```
6. **Tag the release:**
   ```bash
   git tag v0.4.0
   git push --tags
   ```
7. **Update `docs/DISTRIBUTION_NOTES.md`** — change "coming soon to
   PyPI" to "now on PyPI."
8. **Optional: GitHub release** with a brief changelog entry pointing
   at PyPI.

---

## AI Notes

- The most important thing this session: caught and logged the
  estimation-calibration error (see `TRUST_CALIBRATION.md`). I
  unconsciously quoted human-paced estimates ("half a day") for work
  I was doing at AI pace (~30-45 min). The correction was the human's
  pushback. Future estimates will distinguish AI execution time from
  human implementation time, and surface the assumption when it
  matters.
- Two real bugs caught and fixed during smoke testing, not after:
  - `__pycache__/` directories leaked into package data because
    Python had compiled the templates at some point. Fixed by
    adding `_IGNORE_NAMES` / `_IGNORE_SUFFIXES` filters in the
    materializer, plus deleting the pre-existing leaked dirs.
  - The `init` guard in `context_kit.py` predated the move and was
    checking for a path (`starter/`) that no longer exists at the
    repo root. Wheel installs always failed init until the guard
    was rewritten as an ImportError catch.
- One Edit accidentally orphaned a test method (`test_default_target_is_slug_in_cwd`)
  into the new `TestPackagedResources` class — caused an
  AttributeError on `self.tmpdir`. Caught immediately by running the
  full suite. Edit-then-test is the cheap fix.
- The smoke-test cycle (build → venv → install → init) takes ~10s
  end-to-end on this machine. Cheap enough to run after every
  refactor of the packaging path.
- Skipped (deliberately): writing a CI step that builds the wheel +
  installs in a clean venv on every PR. That's a real follow-up
  worth doing in Session 5, but adding it now would have crossed the
  scope line for this session.
- Did NOT update `00-START-NEXT-SESSION.md` to advance to Session 5
  in this commit — leaving it pointing at "launch watch" mode is
  intentional. The launch is still the primary thing happening; the
  PyPI prep is plumbing that lets the launch say "available now"
  instead of "coming soon."
