---
title: "context-kit Repo Inventory"
status: auto-with-narrative
companion_doc: CONTEXT_KIT_WHAT_IT_IS.md
---

# context-kit Repo Inventory

> **Numbers are runtime-derived as of Session 2.** All counts and tables
> below the markers are produced by `python3 context_kit.py inventory --write`
> from real repo state. Everything *outside* the markers is human-written
> commentary that the generator does not touch.
>
> When narrative and the auto-block disagree, the auto-block wins. When
> the auto-block disagrees with the running test suite or the actual
> filesystem, that is a generator bug — file an issue.

---

## How to use this file

```bash
# Refresh the auto-block from current repo state
python3 context_kit.py inventory --write

# Verify the auto-block matches reality (CI-friendly; exits 1 if stale)
python3 context_kit.py inventory --check

# Pipe machine-readable inventory to another tool
python3 context_kit.py inventory --json | jq .
```

Run `--check` in CI to fail builds when the inventory drifts from the
code that ships in the same commit.

---

## Subcommand inventory (narrative)

The auto-block lists subcommand names. The narrative below adds
properties the agent needs to behave well — read-only vs mutating,
whether they touch the network, where they live in the codebase. Worth
keeping by hand because it changes rarely and is risk-relevant.

| Command | Module | Read-only? | Network? |
|---|---|---|---|
| `adopt` | `cli/adopt.py` | Dry-run is read-only; `--write` mutates generated docs in target | No |
| `audit` | `cli/audit.py` | Default is read-only; `--write` creates audit docs if absent | No |
| `behavior` | `cli/behavior.py` | Yes | No |
| `codex` | `cli/start_codex.py` | Yes | No |
| `connections` | `cli/connections.py` | Yes | No |
| `coverage` | `cli/coverage.py` | Yes | No |
| `doctor` | `cli/doctor.py` | Yes | No |
| `exec` | `cli/exec.py` | Yes | No |
| `fix` | `cli/fix.py` | Yes | No |
| `hotpath` | `cli/hotpath.py` | Yes | No |
| `init` | `cli/bootstrap.py` | No (writes to target) | No |
| `inspect` | `cli/inspect.py` | Yes | No |
| `inventory` | `cli/inventory.py` | `--write` mutates this file; `--check` and `--json` read-only | No |
| `orient` | `cli/orient.py` | Yes | No |
| `recommend-stack` | `cli/recommend_stack.py` | Yes | No |
| `refactor` | `cli/refactor.py` + `cli/_refactor/` | Yes | No |
| `seed` | `cli/seed.py` | No (writes generated docs from an idea file) | No |
| `start` | `cli/server.py` | No (binds localhost) | No (loopback only) |
| `start-codex` | `cli/start_codex.py` | Yes | No |
| `translation-init` | `cli/translation_init.py` | Yes | No |
| `verify` | `cli/verify.py` | Yes | No |

---

## Guide-doc topics (narrative)

The auto-block lists guide-doc filenames. The narrative below maps each
filename to the topic it teaches. Worth keeping by hand because the
topics are the value, not the filenames.

| File | Topic |
|---|---|
| `01_two_doc_anchor.md` | Narrative vs runtime split |
| `02_drift_verifier.md` | How runtime stays authoritative |
| `03_topic_docs.md` | Embeddable subsystem docs |
| `04_session_handoffs.md` | Append-only build history |
| `05_start_here.md` | Why `00-START-NEXT-SESSION.md` exists |
| `06_dos_and_donts.md` | Anti-patterns from real failures |
| `07_bootstrap_checklist.md` | First-session sequence |
| `08_collaboration_roles.md` | How AI and human share work |

---

## Drift notes

Things a human reader should know that the generator can't tell them:

- **`tests/` is not in `PATTERN_EXCLUDES`** (see `cli/bootstrap.py`),
  so generated projects ship our test files inside
  `docs/docs-pattern/tests/`. Harmless but noisy. Worth fixing in a
  small follow-up commit; tracked in `00-START-NEXT-SESSION.md` queued
  investigations.
- **The narrative anchor's TL;DR has its own scale line** that
  duplicates a few of the auto-block counts. The generator does not
  rewrite the narrative anchor. If you change the scale line, the
  burden is on you to keep it consistent with the auto-block.
- **Self-reference exclusion.** The auto-block deliberately omits the
  inventory file itself from `docs/` count and the hot-path summary.
  Without that, `--check` would fail immediately after `--write`
  because writing the file changes the file. See
  `cli/inventory.py:_docs_files` and `_hotpath_summary`.

---

## Release history

See `CHANGELOG.md` for the canonical version log. The auto-block above
mirrors the *current* package metadata from `pyproject.toml`; the
changelog has the human-written *why* behind each version.

**0.7.0** through **0.15.0** are published release lines. See
`CHANGELOG.md` for exact release dates, shipped features, and test
counts at each release boundary.

- **0.8.0** added the adopt "decision layer" (depth-2
  workspace walk + Adopt Summary card + Stack reality +
  Project type + Suggested next actions + workspace-aware
  detection + diagnostic-signals copy softening + context-
  aware actions). See
  `docs/handoffs/SESSION_010_ADOPT_V0_8_DECISION_LAYER.md`.
- **0.9.0** added ecosystem coverage (Rust, Go, Smart contract
  project type, mixed-root JS/Python source-dominance
  correction, React Native vs Next.js disambiguation) plus a
  prep-caught determinism fix. See
  `docs/handoffs/SESSION_012_V0_9_0_RELEASE_CLOSEOUT.md`.
- **0.10.0** added the Agent Launch Prompt (single copy-paste
  block the user pastes as the first message to their AI
  agent), `--project-summary` / `--next-task` flags for
  fully-non-interactive runs, the split backend/frontend
  Full-stack project type rule, placeholder soft-framing so
  agents don't block on unfilled context, and the post-write
  Agent-Launch-Prompt-centric next-step in CLI +
  `00-START-NEXT-SESSION.md`.
- **0.11.0** added `--notes TEXT` to preserve discovered
  context across the dry-run → `--write` boundary. Findings
  surface verbatim in the Agent Launch Prompt under
  `DISCOVERED NOTES / CONTEXT` and inside the managed block
  of every generated doc (BUILD_PLAN, 00-START-NEXT-SESSION,
  CLAUDE.md). Multi-line notes preserve line breaks; omission
  produces no empty sections.
- **0.11.1** is a prompt-body-only patch driven by real-repo
  testing. Adds `HOW TO APPROACH THIS REPO` (three-tier
  inspection rule scaling depth to confidence) + `WHAT TO
  PRIORITIZE` (anti-doc-fallback rule) to the Agent Launch
  Prompt, and rewrites the unclear-project first action to
  "infer first, ask only for residual gaps" instead of "wait
  for user before doing anything" — fixing a contradiction
  with the new tiered rule. No flags, no API changes, no
  detection changes; just the text agents read.
- **0.11.2** closes the preserve-context loop. Adds `TO
  PRESERVE THIS CONTEXT` to the Agent Launch Prompt.
- **0.12.0** adds the audit execution loop: `audit --write`,
  `fix`, `exec`, numbered latest-handoff selection in `orient`,
  team-reporting tone, engagement tracking, and the real-world
  workflow writeup.
- **0.13.0** adds `inspect`, a deterministic repo system map,
  plus the source-checkout-safe `cli.__version__` fallback.
- **0.14.0** bridges `audit` to `inspect` and adds Documentation
  Intelligence to detect docs as an active context / memory layer.
- **0.15.0** adds `refactor`, a read-only progress reporter
  for long-running Python module-extraction refactors.

`[Unreleased]` currently contains the pipeline / behavior /
translation-layer scaffold work, `translation-init`, Live Chat Mode,
`orient --short` / doctor context-shape diagnostics, the Truth /
State Layer drift checks, and `start-codex`.

---

<!-- The block below was added by `context-kit inventory --write`. -->
<!-- It will be regenerated on every `--write`. Edit outside the markers freely. -->

<!-- context-kit:inventory:start -->
<!-- Auto-generated by `context-kit inventory --write`. Do not edit by hand. -->
<!-- Last generated: 2026-05-15T16:14:51+00:00 -->
<!-- Schema version: 1 -->

## Auto-generated counts

| Item | Count | Notes |
|---|---|---|
| CLI subcommands | 24 | adopt, audit, audit-response, behavior, capabilities, chat, codex, connections, coverage, doctor, exec, fix, hotpath, init, inspect, inventory, orient, recommend-stack, refactor, seed, start, start-codex, translation-init, verify |
| Python modules in `cli/` | 27 | __init__.py, adopt.py, audit.py, audit_response.py, behavior.py, bootstrap.py, capabilities.py, chat.py, connections.py, coverage.py, doctor.py, exec.py, fix.py, hotpath.py, inspect.py, inventory.py, ollama.py, orient.py, placeholders.py, recommend_stack.py, refactor.py, seed.py, server.py, start_codex.py, state.py, translation_init.py, verify.py |
| Top-level guide docs | 8 | matches `0[1-8]_*.md` |
| `docs/` files (top-level) | 6 | excludes handoffs |
| Session handoffs | 15 | `docs/handoffs/` |
| Templates | 0 | `templates/` |
| Starter files (excl. scaffold) | 0 | `starter/` |
| Scaffold files | 0 | `starter/scaffold/` |
| Test files | 29 | `tests/test_*.py` |
| Tests collected | 1042 | from `def test_` parse |
| Skill files | 2 | `skills/**/SKILL.md` |
| Tracked files | 140 | from `git ls-files` |

## Package metadata (from `pyproject.toml`)

- **name:** contextkit-ai
- **version:** 0.15.0
- **description:** Bootstrap tool for AI-assisted projects that preserves context across sessions, prevents doc drift, and scaffolds a memory layer around your code.
- **requires-python:** >=3.9

## Hot-path summary

- **Source:** git ls-files
- **Files scanned:** 139
- **Top 10 sum:** 1.06 MB
- **Total size:** 2.36 MB
<!-- context-kit:inventory:end -->
