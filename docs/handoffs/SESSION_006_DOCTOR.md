---
title: "Session 006 — context-kit doctor (environment diagnostics)"
date: 2026-04-25
status: shipped
---

# Session 006 — context-kit doctor

`context-kit doctor` shipped: read-only environment + setup
diagnostics. Seven checks, human + JSON output, exit `1` only on
blocking issues. The first feature spec'd entirely from real
incidents rather than imagined need.

## Provenance — Expo / React Native dogfood

Every check in this command traces back to a specific moment of pain
on the parallel dogfood app (an Expo / React Native project the human
was building alongside context-kit):

| Check | Originating incident |
|---|---|
| **File watcher / `ulimit`** | Metro crashed with `EMFILE: too many open files` after watchman wasn't installed and `ulimit -n` defaulted to 256 on macOS. Surfaced as `blocking` when Expo + low ulimit + no watchman, with explicit `ulimit -n 65536` / `brew install watchman` fix lines. |
| **Expo SDK + config** | Expo Go on the App Store had jumped to SDK 54 while the project was on SDK 51; `npx expo start` produced a confusing "this project's SDK is too old" error in the QR code flow. Doctor warns whenever Expo is detected, with a pointer to `npx expo-doctor` and `npx expo install expo@latest`. Bonus check: `app.json` / `app.config.js` / `app.config.ts` presence (one of those failures was an incomplete Expo init). |
| **Expo CLI deprecation** | `expo doctor` (the legacy global `expo-cli` command) had moved to `npx expo-doctor`. Friction was *finding the new command*. Doctor names the new one explicitly and warns if the legacy global `expo` binary is still on PATH. |
| **Node version pressure** | Node v23 caused watcher trouble with Expo/Metro on the same machine. Doctor warns when Node is outside `KNOWN_STABLE_NODE_MAJORS = (18, 19, 20, 21, 22)` and points at the LTS as the safe default. |

The other three checks (Python, git, project state, inventory
freshness) are general environment hygiene — included because doctor
should be useful for non-Expo projects too.

## Architecture

`cli/doctor.py` — same shape as the other commands:

- `CheckResult` dataclass with normalized `fix` (always a list or None
  in JSON output)
- 7 near-pure check functions, each returning a `CheckResult`
- Human and JSON emitters
- `_exit_code(results)` — 1 if any blocking, 0 otherwise (warnings
  never affect exit code, per design agreement)
- Direct import of `cli.inventory.check_inventory` (dependency
  direction: doctor → inventory; never invert)
- Mockable seams for tests (`shutil.which`, `subprocess.run`, optional
  kwargs on `check_python_version`)

`KNOWN_STABLE_NODE_MAJORS` is hardcoded with a comment noting it
needs periodic bumps. Acceptable trade-off vs network calls; flagged
in the design discussion as a real risk.

## Tests

40 new tests in `tests/test_doctor.py` covering:

- Python version (ok / blocking <3.9 / PATH mismatch warning)
- Git (ok in repo / warning when missing on PATH / warning when not a repo)
- Project state (ok with full scaffold / warning with partial / skipped on empty dir)
- Node (skipped without `package.json` / blocking when missing / ok in stable / warning too old / warning too new)
- Expo (skipped without `package.json` / skipped without `expo` dep / warning when present / warning extra when no `app.json` / version detection from `node_modules/expo/package.json`)
- File watcher (skipped on Windows / skipped without `package.json` / blocking on Expo + low ulimit / warning on low ulimit / ok on high ulimit + watchman)
- Inventory freshness (skipped truly absent / warning when init'd but no managed file / ok after `inventory --write`)
- Output (human format has section headers / JSON valid / JSON has expected top-level keys / JSON checks have expected shape)
- Exit code (0 with no blocking / 1 with blocking)
- No mutation (mtime invariant before/after)
- Integration on freshly init'd project + on non-project directory

Total suite: **167 tests** (was 127; +40).

## Files changed

```
A  cli/doctor.py                                    ~470 lines
A  tests/test_doctor.py                             ~430 lines, 40 tests
A  docs/handoffs/SESSION_006_DOCTOR.md              this file
M  cli/bootstrap.py                                 cli/doctor.py in RUNTIME_COPY
M  context_kit.py                                   subparser + dispatcher
M  cli/_skills/context-kit/SKILL.md                 "run doctor when something feels off in the environment"
M  README.md                                        commands list + doctor options table
M  CHANGELOG.md                                     Unreleased entry
M  docs/TRUST_CALIBRATION.md                        new entry: "real friction beats imagined feature specs"
M  docs/CONTEXT_KIT_INVENTORY.md                    regen
```

## Verification

```
unittest discover                  167 tests, OK (was 127)
inventory --check                  current
orient                             all 5 sections, latest handoff = SESSION_004 (Session 5/6 docs lag flagged)
hotpath                            STATUS OK
doctor (on source repo)            3 ok / 1 warning (inventory stale at the moment) / 3 skipped — exit 0
wheel build                        contextkit_ai-0.4.3.tar.gz + .whl  (after version bump if we publish)
```

## What this is NOT

- Not auto-fixing anything (per design agreement; deferred to v2)
- Not network-aware (no live "current Expo SDK" lookup; deferred)
- Not Windows-aware for file-watcher (skipped explicitly)
- Not a plugin API; the 7 checks are hardcoded for MVP

## Design choices that held up

- **Strict status separation:** warnings never affect exit code. CI
  using `doctor` as a gate gets honest signal — only blocking issues
  fail the build. Suggestion-style warnings can pile up in noisy
  environments without breaking anyone.
- **Skipped, not warning, for "no context-kit project":** doctor is
  useful as a pre-init environment check too. A user can run
  `context-kit doctor` before deciding to scaffold.
- **EMFILE pattern is `blocking`, not `warning`:** the dogfood signal
  was strong enough that an Expo project + low `ulimit -n` + no
  watchman is a near-certain failure within minutes of `npx expo
  start`. Warning would underweight it.
- **Inventory check via direct import** (not subprocess): cleaner,
  same performance, and the dependency direction (doctor → inventory)
  is now explicit and testable.

## Known follow-ups (not in scope for this session)

- The **inventory file naming weirdness** surfaced again: the
  "anchor" inventory (`docs/<APP>_INVENTORY.md`) is a different file
  from the "managed-block" inventory (`docs/CONTEXT_KIT_INVENTORY.md`).
  Doctor's check is now explicit about which file it's looking at,
  but the underlying naming is still a paper cut. Worth a future
  session to either consolidate or rename so the relationship is
  clearer.
- A **Session 5 handoff** for `seed` was deferred during launch mode.
  Worth backfilling at some point so the session history stays
  continuous.
- `KNOWN_STABLE_NODE_MAJORS` will go stale. Consider a tiny GitHub
  Action that opens a PR when a new Node major joins LTS.

## AI Notes

- Caught one real fix during test runs: the inventory check was
  returning `skipped` in freshly-init'd projects (because
  `docs/CONTEXT_KIT_INVENTORY.md` doesn't exist until `inventory
  --write` is run for the first time). That `skipped` was misleading
  — the project IS init'd; the file is just lazily created.
  Refactored to: if `00-START-NEXT-SESSION.md` exists but no managed
  inventory file, return `warning` with `inventory --write` as the
  fix. If neither exists, truly `skipped`.
- The hardcoded `KNOWN_STABLE_NODE_MAJORS` constant is the most
  brittle part of this command. Documented as needing periodic
  bumps, but the failure mode is loud (warning text says "known-stable
  majors: 18-22" so anyone reading the warning sees the staleness).
- Test mocking with `@patch` worked cleanly because the check
  functions kept their seams thin (pull `shutil.which` /
  `subprocess.run` / `_detect_node_version` to module-level names).
  Locked that pattern in for future check-style commands.
- The TRUST_CALIBRATION entry this session is unusual — it's not a
  correction, it's a positive lesson. Real friction beats imagined
  feature specs. The "every check in doctor traces back to a named
  dogfood-app incident" was the cleanest design conversation we've
  had so far. Worth holding to that bar for new features.
