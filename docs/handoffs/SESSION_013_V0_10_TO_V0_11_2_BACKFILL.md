---
title: "Session 013 — v0.10.0 → v0.11.2 backfill + Phase 1 truth restore"
date: 2026-04-28
status: backfill handoff covering four undocumented releases + first audit-driven cleanup
---

# Session 013 — v0.10.0 → v0.11.2 backfill + Phase 1 truth restore

## Why this handoff exists

Four releases shipped after SESSION_012 with no corresponding session
handoff — a direct violation of the project's own load-bearing rule
("every session ends with a handoff"). An audit caught it. This file
backfills the gap from `CHANGELOG.md` and `git log`, then records the
Phase 1 "tell the truth" cleanup that closed the audit's P0 findings.

Treat this as one logical session covering the four-release window plus
the corrective work, not as a per-release reconstruction.

---

## What shipped between v0.9.0 and v0.11.2

The whole window was one continuous adopt-feature arc — *Agent Launch
Prompt → notes preservation → behavior shaping → preserve-context loop* —
plus one new top-level command (`audit`). No detection-rule changes
after v0.9.0. No new dependencies. Zero-runtime-deps invariant intact.

### v0.10.0 — Agent Launch Prompt milestone

The headline feature of the window. `context-kit adopt` now produces a
single copy-paste block the user hands to any AI coding agent (Claude
Code, Cursor, Aider) as the first message of a session. The prompt is
self-contained — project shape, primary detection, recommended first
action, safety rules, and the user's own framing — so the agent starts
without a question loop.

- `derive_agent_launch_prompt` builds an `AgentLaunchPrompt` from the
  same data the Adopt Summary already uses. Five fixed sections.
  Confidence mirrors `StackReality.confidence`.
- `_agent_first_action_for` selects a project-type-aware first action
  from 7 branches (Full-stack, Smart contract, Mobile, Web3 dApp, Rust,
  Go, generic). Each is 3–4 read-only inspection steps.
- Surfaces in three docs after `--write` (`00-START-NEXT-SESSION.md`,
  `CLAUDE.md`, `BUILD_PLAN.md`) and prints above the dry-run plan
  before `--write`.
- New flags `--project-summary TEXT` and `--next-task TEXT` make a full
  adopt run non-interactive when paired. Useful for CI, scripted
  dogfood, recorded demos.
- Fixed: split-monorepo full-stack classification (`backend/` +
  `frontend/`, `server/` + `web/`, `api/` + `client/`) — closed the
  contract-concierge gap. Recognized roles live in `_BACKEND_ROLES` /
  `_FRONTEND_ROLES`.
- Fixed: pre-`--write` rendering self-fences when generated docs don't
  exist yet. Placeholder soft-framing across three doc generators
  (`[adopt: please describe]` + "do not block read-only inspection on
  these placeholders") prevents agents from stalling on unfilled
  context.
- Post-write CLI footer rewrites to lead with the Agent Launch Prompt
  as the canonical next step.

Commits: `367cf7b`, `c0af9e4`, `263bbd5`, `9834006`, `9360688`,
`3033ac6`, `73d62d6`, `0e0b420`.

### v0.11.0 — `--notes TEXT` discovered-context preservation

Closed a trust-loss case the v0.10.0 release flow exposed: a user runs
`adopt --html` in probe mode, finds something useful (port collision,
deployment quirk, demo credentials, etc.), then later runs `--write`
with a sharper `--project-summary` — and their findings vanish from the
generated docs. `--notes` is the escape hatch.

- Flag-only (never prompted). When omitted, no notes section appears
  anywhere in adopt's output (no empty headings).
- Surfaces in four places when provided: Agent Launch Prompt's
  `DISCOVERED NOTES / CONTEXT` section, `BUILD_PLAN.md`'s `## Discovered
  notes`, `00-START-NEXT-SESSION.md`'s `## Discovered notes`, and the
  `CLAUDE.md` adopt-managed block's `### Discovered notes`.
- Multi-line notes preserve line breaks via `_format_notes_block`
  (centralized renderer). Whitespace-only collapses to "no notes".
- `AdoptionInputs` gains `notes: str = ""`. `collect_inputs` gains a
  `notes=None` kwarg. `run_adopt` reads `getattr(args, "notes", None)`
  so legacy test namespaces keep working.

Commits: `2a94fb0`, `69ff38a`.

### v0.11.1 — agent-behavior shaping in the launch prompt

Two scoped prompt-body improvements driven by real-repo testing
(mentorforge, flow-name-service, norman-handyman-mvp). No new flags, no
API changes, no detection logic — just the text agents read.

- New `HOW TO APPROACH THIS REPO` section: three-tier inspection rule
  scaling depth to confidence (low → full structured read-through;
  medium → quick inspection; high → skip read-through, go to highest-
  value next task). Replaces the v0.11.0 single-tier rule that made
  agents over-prepare on simple cases and under-prepare on hard ones.
- New `WHAT TO PRIORITIZE` section: anti-doc-fallback rule. *"Prefer
  identifying real risks, inconsistencies, missing wiring, or unused /
  incomplete features over surface-level tasks. Do not default to
  documentation updates unless the user explicitly asked for them."*
  Real-repo testing showed agents defaulting to "let me update the
  README" when handed a clear, healthy project.
- Fixed: the unclear-project `RECOMMENDED FIRST ACTION` used to say
  "wait for the user before proposing any concrete next step" — which
  contradicted the new HOW TO APPROACH rule. Rewrote as "infer first,
  ask only for residual gaps."

Commits: `48cf591`, `c898a43`, `8172e83`.

### v0.11.2 — preserve-context loop closed

The v0.11.0 / v0.11.1 work made agents do good initial inspection. The
user then had to hand-summarize those findings into a `--notes` flag
manually for the follow-up `--write`. v0.11.2 closes that loop in one
paste.

- New `TO PRESERVE THIS CONTEXT` section between SAFETY INSTRUCTIONS
  and the closing wrap-up of the Agent Launch Prompt. Embeds an exact
  `context-kit adopt . --write` command pre-wired with three
  placeholders the agent fills in (`<refined one-sentence project
  summary>`, `<recommended next task>`, `<key findings from this
  inspection>`).
- Five guardrails: notes must be concise but specific; no secrets; quote
  escaping; omit `--notes` when empty; emit-don't-run.
- Validated against mentorforge (FastAPI + React/Vite split with real
  Stripe / CORS / auth findings).

Commits: `e92ffea`, `4623e21`.

### Unreleased — `audit` command (this session)

New top-level `context-kit audit` command. Prints a static senior-
engineer audit prompt to stdout: stale docs, duplicated logic, dead
code, risky areas, runtime/doc inconsistencies, with P0/P1/P2
prioritization and a phased cleanup plan. No flags. ~30 LOC; 5 tests.

Commit: `9b56acc feat(audit): add senior-engineer repo audit prompt`.

This was the *first* feature added by an audit run that exposed real
drift in the project's own docs — an instance of the tool being used
on itself. The audit it produced drove the rest of this session.

---

## Phase 1 — truth restore (this session)

The audit identified four P0 findings and three P1s rooted in doc /
runtime drift. Phase 1 closes the P0s; P1s remain open.

### Closed in this session

1. **Inventory regenerated.** Auto-block now reflects the audit
   command (10 subcommands, 12 cli modules, 12 test files, **494
   tests**). `inventory --check` exits clean.
2. **Backfill handoff written.** This file. Closes the four-release
   handoff gap.
3. **Start-here doc rewritten.** `00-START-NEXT-SESSION.md` now anchors
   on v0.11.2 / 494 tests, and names the next session's priorities
   (audit feature expansion, adopt refactor, doc drift cleanup).
4. **`__version__` drift fixed.** `cli/__init__.py:11` replaced with
   `from importlib.metadata import version; __version__ =
   version("contextkit-ai")` — sources the version from the same place
   as the build, eliminating an 8-version-stale constant.

### Open after Phase 1 (Phase 2 work)

- Stale skill paths in `CLAUDE.md`, `README.md`,
  `docs/CONTEXT_KIT_WHAT_IT_IS.md`, `docs/DISTRIBUTION_NOTES.md` still
  reference a root-level `skills/` that doesn't exist. Source is
  `cli/_skills/context-kit/SKILL.md`; mirror is
  `.claude/skills/context-kit/SKILL.md`.
- Inventory's narrative subcommand table (`docs/CONTEXT_KIT_INVENTORY.md`
  near line 46) only lists 5 of 10 commands. Missing: `adopt`, `audit`,
  `doctor`, `recommend-stack`, `seed`.
- `README.md:265` still frames v0.8.0–v0.9.0 as the current frontier.
- Inventory drift-notes section still references "queued investigations"
  that no longer exist.
- CI (`.github/workflows/test.yml`) does not run `inventory --check`.
  Without that gate, every release of this kind of drift is structurally
  inevitable.

### Out-of-scope for this session

- `scripts/track_engagement.py` and `metrics/engagement.csv` — the
  user's engagement-tracking thread of work, deliberately untouched.
- `.gitignore` modifications associated with that thread, untouched.

---

## State at session end

| Surface | Value |
|---|---|
| `pyproject.toml` version | `0.11.2` |
| `cli/__init__.py.__version__` | resolves to `0.11.2` via `importlib.metadata` |
| Tests | **494 / 494 passing** |
| Inventory | current (`inventory --check` clean) |
| Latest handoff | this file |
| `00-START-NEXT-SESSION.md` | rewritten to point at v0.11.2 + Phase 2 priorities |
| Working tree (audit-feature scope) | clean |
| Working tree (out-of-scope) | `.gitignore`, `scripts/` still uncommitted by design |
| `[Unreleased]` in CHANGELOG.md | empty (next release will be `[0.12.0]` and will include the `audit` command) |

---

## Suggested next session focus

Phase 2 of the audit (no commitment yet — confirm with the user before
committing):

1. **Doc-drift cleanup (P1).** Replace stale `skills/context-kit/...`
   references; extend or delete the inventory's narrative subcommand
   table; refresh README's version framing.
2. **CI guardrail (the durable fix).** Add `python3 context_kit.py
   inventory --check` to `.github/workflows/test.yml`. Without this,
   the drift this session just fixed will recur.
3. **Adopt refactor scoping (P1).** `cli/adopt.py` is 4,776 lines;
   `tests/test_adopt.py` is 6,337. Run `coverage run -m unittest
   tests.test_adopt` to find dead branches before deciding the split.

Defer the `cli/adopt/` package split itself to a multi-session block
once Phases 2–3 stabilize.

---

## AI Notes

This session is the first time `context-kit` was audited *by itself*.
The flow — `context-kit audit` → fresh audit by the agent → Phase 1
truth restore — worked end-to-end. Worth noting because it validates
the underlying premise: a tool whose value is making projects
self-aware should be self-aware enough to expose its own drift.

The audit also surfaced an honest weakness: nothing structural
prevents the drift it just caught. The CHANGELOG shows four releases
of accumulating drift across two days; the `inventory --check` command
that would have caught it on every PR has existed the whole time but
isn't wired into CI. Phase 3 of the audit plan addresses this; Phase 1
does not. Worth flagging that this session's "fix" is informational,
not structural — the next release cycle will recreate the drift unless
Phase 3 happens before then.
