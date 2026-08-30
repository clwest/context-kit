---
title: "Session 020 — guardrails subcommand landed"
date: 2026-08-29
status: shipped `context-kit guardrails` subcommand + workflow template + new skill
previous_handoff: ./SESSION_019_FLEET_NETWORK_PATTERN.md
---

# Session 020 — guardrails subcommand landed

## Why this handoff exists

Executed the UDB harvest program's session 4 brief
(`~/Donkey_Betz/TASK_udb-harvest-04-ci-guardrails.md`): extract the one
shippable thing the harvest survey found and land it as a first-class
context-kit surface. The source pack was
`unified-donkey-betz/scripts/verify_repo_guardrails.py` (817 lines) plus
`.github/workflows/repo-guardrails.yml`. The extraction discipline was
"port the shape, not the checks" — the source pack had 8 checks; 6 were
UDB furniture (Postgres application-name tags on Procfile entries,
DOC-AUTOGEN markers on named docs, ORM shape-signature scans) and did
not belong in a shipped tool.

The brief itself was written from a read of the source pack, not from
having done the extraction; sections below flag where the extraction
found the brief right and where it changed.

## Current state

| Surface | Value |
|---|---|
| `pyproject.toml` version | `0.16.0` (unchanged; new work sits under `[Unreleased]`) |
| Latest tag | `v0.16.0` |
| Branch | `main`, ahead of `origin/main` (SESSION_020 commit pending) |
| Working tree before this session | clean, one commit ahead of origin (SESSION_020-refresh) |
| Tests | **1116 / 1116 passing** (28 net-new for `guardrails`) |
| Doctor | not re-run — no anchor-doc churn this session |

## What shipped

### `cli/guardrails.py` — new subcommand module

Two built-in checks:

- **`verify-conflicts`** — calls `cli.verify.collect_verification` in-process
  and fails on any `CONFLICT` finding. `DOC_ONLY` findings are surfaced
  as advisory messages. Uses the existing verify subsystem — no new
  drift detector, no duplication.
- **`tracked-generated-paths`** — reads
  `.context-kit/guardrails.yaml`'s `forbidden_paths:` list and fails if
  any pattern matches a git-tracked file. Uses `git ls-files` when the
  project is a git repo, walks the tree with `fnmatch` when it isn't
  (so the check still runs before `git init`). Empty or missing config
  → no-op.

Plug-in point: `.context-kit/guardrails.py` in the consuming repo. If
present, it must expose `CHECKS: list[Check]`. Broken plug-ins surface
as a failing `plugin-load` check — a shape error or ImportError cannot
silently drop the real checks.

Advisory-vs-strict rule carried over from the source pack, intact: any
check can be downgraded to non-blocking via `--advisory NAME`
(repeatable) on the CLI. The rule is that the downgrade must be visible
in the invocation, not hidden in the code. CI workflows using the
template can add `--advisory NAME` when a check cannot honestly run in
their environment; the reader of the workflow sees exactly what is
downgraded.

### `cli/_static/guardrails/workflow_template.yml` — CI workflow

Installed by `context-kit guardrails install-workflow`. Installs
`contextkit-ai` from PyPI, runs `context-kit guardrails run` in strict
mode. **No repository secret, no cross-repo token, no fine-grained PAT.**
The source workflow needed a `CONTEXT_KIT_REPO_TOKEN` secret to
`pip install git+https://…@github.com/clwest/context-kit.git@main`
because the comment said context-kit was "not yet published to PyPI
under the name `context-kit`." That comment was stale — the distribution
is `contextkit-ai`, has 17 releases on PyPI (currently `0.16.0`), and
has been installable by anyone since April 2026.

### `cli/_skills/context-kit-guardrails/SKILL.md` — new bundled skill

Distinct from the existing `context-kit` orientation skill. Explicit
about the boundary: orientation fires at session start inside a
context-kit project; guardrails fires when a project needs standing CI
hygiene (first workflow, failing existing gate, post-`adopt` question).
The two are related jobs on the same CLI but different human moments;
never bundle them.

### `tests/test_guardrails.py` — 28 tests

Covers the tiny YAML parser, config loading, both built-in checks
(with `collect_verification` stubbed so the test suite stays fast),
plug-in loader error paths, and the CLI entry (strict / no-strict /
install-workflow / overwrite refusal / force overwrite / unknown check
name warnings).

### Registered

- `context_kit.py` — `guardrails` added to `_COMMANDS`, subparser
  group with `run` and `install-workflow` sub-actions.
- `pyproject.toml` — `_static/guardrails/*` and
  `_skills/context-kit-guardrails/*` added to package-data so the
  wheel carries them.
- `CHANGELOG.md` — entry under `[Unreleased]`. **Version bump not
  applied**; the brief said "propose both; Chris ships." Proposed:
  minor bump to `0.17.0` (new user-visible subcommand family + new
  skill + one added package-data glob; no breaking change).

## What the brief got wrong

- **Session 1 was right that the source had exactly one shippable thing
  and hadn't shipped it — but the barrier the brief expected (private
  PyPI blocker) did not exist.** The extracted pack installs from PyPI
  today, needs no token, and lands as a standard `pip install
  contextkit-ai` in the CI workflow. Verified against PyPI at
  extraction time: `contextkit-ai 0.16.0`, 17 releases.
- **The brief flagged scout's `.context-kit` marker file as possibly
  incomplete adoption.** Confirmed: scout has the `context-kit:adopt`
  block in `00-START-NEXT-SESSION.md` (adopted 2026-08-26) but no
  `.context-kit/` marker directory. Adoption is *partial*. The kill
  test still ran cleanly — the guardrails pack does not require full
  adoption state, only a project root, git presence, and (optionally)
  a `.context-kit/guardrails.yaml` config. That's a signal the runner
  is correctly decoupled from adoption; it was not a signal to change
  scout.
- **The 10-workflow triage in the brief was approximately right but
  worth re-checking directly.** The confirmation:
  - `repo-guardrails.yml` — the target, extracted.
  - `secret-scan.yml` — generic gitleaks scan, portable, worth
    carrying in a **future** session. Not carried today because it is
    not part of the drift-gate scope and belongs in its own skill /
    template.
  - `docs-sync.yml` — heavily UDB-specific (four Django management
    commands hitting a UDB Postgres). Belongs with the docs-pattern
    skills as the brief suspected.
  - The other seven (`eas-build`, `eas-preview`, `mobile-contracts`,
    `check-llm-sdk`, `check-reasoning-contract`,
    `check-envelope-migration`, `security-conformance`) — UDB / mobile
    / LLM-SDK specific. Not portable. Left.

## Kill test verdict — the pack lives

Target: `~/Donkey_Betz/scout`, per the brief. Fallback (`norman-handyman-mvp`)
not needed.

- **Clean scout `main`** → `context-kit guardrails run` exits **0**,
  reports two checks OK plus 4 DOC_ONLY findings surfaced as advisory
  (unverified count claims in scout's own inventory — pre-existing,
  not caused by this session).
- **Scratch branch `harvest-04-killtest`** — seeded a single commit
  that (a) added `.context-kit/guardrails.yaml` with
  `forbidden_paths: [dist/**]` and (b) force-added `dist/bundle.js`
  (scout's `.gitignore` excludes `dist/`, so tracking required
  `git add -f` — the exact scenario the check is designed to catch:
  a generated artifact that snuck past ignore rules).
- **Guardrails on the bad commit** → exit **1**, both built-in checks
  independently fired:
  - `verify-conflicts` — `context-kit verify`'s own tracked-artifact
    detector caught it and returned a CONFLICT finding.
  - `tracked-generated-paths` — the new check matched `dist/bundle.js`
    against the config pattern.
- **No edits to the extracted pack between the runs.** Same commit of
  `cli/guardrails.py`, same workflow template.
- **Cleanup** — checked back out to `main`, deleted the scratch branch.
  Scout is byte-identical to what it was before the test, at commit
  `1986c52` on `main`.

## Version bump and changelog — proposed, unapplied

Draft entry landed under `[Unreleased]` in `CHANGELOG.md`. The brief was
explicit: propose, do not apply. Chris ships.

Proposed next tag: **`v0.17.0`** — minor, because this adds a new
user-visible subcommand family plus a new bundled skill, and does not
change or remove any existing surface.

## AI Notes

- The plug-in error path is the load-bearing correctness choice in this
  module: a repo that ships a `guardrails.py` plug-in with a typo needs
  the CI job to fail visibly, not to run only the built-ins with a
  quiet "no plug-in loaded" log line. Every plug-in load failure
  (missing `CHECKS`, wrong type, import raise) produces a `plugin-load`
  Check with `blocking=True`. Tested.
- The tiny YAML parser is deliberate. Adding PyYAML would break the
  zero-dep character of the tool for the sake of loading two lists.
  The parser only understands the exact shape the config file uses and
  will not silently misparse anything else. If the config grows past
  flat lists, replace the parser then; do not add PyYAML preemptively.
- The `_git_ls_files` fallback (fnmatch walk when the project isn't a
  git repo) is a small extra of tests-passing usefulness — the check
  correctly reports "no matches" on a fresh scaffold rather than
  crashing. Skips the standard heavy dirs (`.git`, `.venv`,
  `node_modules`, `__pycache__`).
- Two Pyright false-positives were reported at write time and cleared:
  an unused `sys` import (removed) and an unused `_project` parameter
  in a nested closure (renamed to `_` per convention).
