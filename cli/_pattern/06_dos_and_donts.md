---
title: "Dos and Don'ts — Lessons From 1100 Sessions"
status: active
---

# Dos and Don'ts

Rules distilled from building `unified-donkey-betz` with an AI pair across ~1100 sessions. Each has a real incident attached so you know *why* the rule exists.

---

## 11 DOs

### DO 1: Use directories, never scatter .md files at the root of /docs/
Flat `/docs/` becomes unmaintainable around ~20 files. The AI can't find anything, humans can't find anything, and nothing has a clear owner.
**Groupings that worked:** `docs/topics/`, `docs/current/`, `docs/handoffs/`, `docs/audit-2026/`, `docs/docs-pattern/`.
**Incident:** by Session 700, `/docs/` root had 60+ files. Nobody could remember what was where. Recovering took multiple sessions of pure reorganization.

### DO 2: Anchor ONE canonical doc per quantitative claim; every other doc points at it
Pick `PLATFORM_WHAT_IT_IS.md` or `PLATFORM_INVENTORY.md` as the source of truth for any given number. Every other doc that mentions it gets a pointer header.
**Incident:** "PA tool count" was claimed as 77 / 85+ / 86 / 89 / 231 across five different docs. Actual was 101. Three of the five docs were "current" by Git timestamp.

### DO 3: Regenerable beats hand-maintained — if a number can be computed, compute it
`PLATFORM_INVENTORY.md` is ~2,200 lines of runtime-derived counts. It drifts only when the command isn't run. No individual fact in it is hand-maintained.
**Incident:** Hand-maintained stats tables in `CAPABILITIES.md`, `AGENTS.md`, `SERVICES.md` all independently drifted by 20–40% between Sessions 600 and 1099. A regenerable inventory would have caught every drift same-day.

### DO 4: Build a verifier — expect drift, automate detection
Docs stale. Humans forget. A `verify_doc_claims`-style framework that runs in <5 seconds catches drift on every session start.
**Incident:** Drove Session 1099 itself — the audit surfaced 45 registered drifts across 24 docs in a single pass. Nothing else would have found them.

### DO 5: Embed docs into LLM context — if the AI can't see it, it doesn't exist
`build_docs_index` produces `docs/INDEX.md` + `docs/_index.json`, which the PA retrieves from on every user question. Docs that aren't embedded aren't documentation — they're folklore.
**Incident:** A subsystem was well-documented in `docs/topics/` but `build_docs_index` hadn't been run in 2 weeks. The AI kept answering from the old embedding. "Why doesn't it know this?" was the bug.

### DO 6: Write handoffs at session END, not next session START
Knowledge decays overnight. The *why* behind a choice is only in your head at the moment you make it.
**Incident:** Multiple Session-N+1 handoffs had to reconstruct decisions from git log + Slack. Failed 2 out of 3 times. Session-N end-of-day handoffs preserved the reasoning.

### DO 7: When a doc drifts, tag it with a pointer header instead of chasing every number
Session 1099 added a `DOC-POINTER-V1` HTML comment + pointer block to 19 drifting docs. Total time: 10 minutes. Chasing every inline number would have taken 6 hours.
**Pattern:**
```markdown
<!-- DOC-POINTER-V1 -->
> ⚠ Stats in this doc may drift from code. For current verified numbers see
> [`PLATFORM_WHAT_IT_IS.md`](/docs/PLATFORM_WHAT_IT_IS.md). Run
> `python manage.py verify_doc_claims --only-drift` for live drift.
```

### DO 8: Short docs beat long docs — embedding chunks favor scannable
Topic docs target 100–250 lines. Stats table → architecture → files → known issues. The embedding's first chunk is the stats table, which is what most queries match against.
**Incident:** A 900-line topic doc was matched for every query because it had more chunks. A 100-line precise doc about the same subsystem was ignored. Trimmed the long one; precision jumped.

### DO 9: Include "Known Issues / Drift" in every topic doc
Honest drift beats hidden drift. The AI reading a doc with a "Known Issues" section hedges correctly. The AI reading a doc that pretends everything is perfect confidently hallucinates.
**Incident:** Topic docs without known-issues sections produced confidently wrong answers about half-broken subsystems. Adding the section fixed the hedging.

### DO 10: Commit `docs/INDEX.md` + `docs/_index.json` with every code change
Embedded context lags behind code otherwise. On this platform there's a memory rule + pre-commit hook that enforces it.
**Incident:** `INDEX.md` went 3 weeks out of date in Session 850-ish. Every PA answer was subtly wrong until it was rebuilt.

### DO 11: Archive, never delete — your docs are primary-source material
Stale handoffs, superseded topic docs, old audit dossiers — keep them. `git mv` into `docs/archive/`, prepend `status: superseded`, add a pointer header to the replacement. The corpus of 676+ session handoffs on this platform is the only record of *why* decisions were made. You can't reconstruct "we tried approach X but rejected it for reason Y" from code. One day the whole corpus might get distilled into a white paper or retrospective — you can't distill what you deleted.
**Incident:** Chris explicitly flagged this (Session 1099 wrap, 2026-04-20): *"Let's not delete any documentation... one of these days those thousands of documents might be able to be turned into a white paper."* Prune-happy cleanup is a net loss even when the file looks like cruft.
**Only exceptions:** regenerable auto-generated files (`INDEX.md`, `_index.json`) and accidentally-committed build artifacts (bytecode, `node_modules`).

---

## 11 DON'Ts

### DON'T 1: Duplicate numbers across docs without an anchor
Every duplicated number is a future contradiction. Either anchor one doc as canonical + pointer from others, or use a regenerable inventory.
**Incident:** See DO 2 — five docs, five different PA tool counts.

### DON'T 2: Put exact live-counter numbers inline in narrative docs
`SpiderItemHash` grows continuously; claiming "1,142,847 rows" is wrong within minutes. Use `~1.14M rows` + "live counter" annotation.
**Incident:** `PLATFORM_WHAT_IT_IS.md` had exact live counters in draft 1. Verifier showed drift within hours. Switched to `~values` annotation — stable ever since.

### DON'T 3: Let per-topic stats tables drift silently
If `docs/topics/agent-system.md` says "84 agents" but the verifier says 83, either fix the doc or add a pointer header. Silent drift kills trust.

### DON'T 4: Write docs only one human remembers — embed them
If you write a note in a Slack DM, a whiteboard, or an uncommitted text file, it doesn't exist. Put it in `docs/topics/` or a session handoff.
**Incident:** Three weeks of context about why a decision was made lived only in Slack DMs. Cross-referencing in Session 600 was impossible.

### DON'T 5: Bury the source of truth
The pointer to `PLATFORM_WHAT_IT_IS.md` goes at the **top** of `CLAUDE.md` and `00-START-NEXT-SESSION.md`. Not section 3. Not "Related Reading." The top.
**Incident:** Source-of-truth block was buried at line 240 of CLAUDE.md pre-Session 1099. Sessions would read past it and trust whatever random stats table they hit first.

### DON'T 6: Create a new .md at the repo root for "just this one thing"
"TODO.md", "NOTES.md", "REFACTOR_PLAN.md" — every one of these was "just this one thing" at some point. The repo root has one acceptable dynamic doc: `00-START-NEXT-SESSION.md`. Everything else goes in `/docs/<directory>/`.
**Incident:** This platform had `CLEANUP.md`, `TODO.md`, `WORK_IN_PROGRESS.md` all at the root simultaneously. None were current — they should have been moved into `docs/archive/` or a `docs/scratchpad/` directory instead of sitting at the root confusing future sessions (see DO 11 — don't delete).

### DON'T 7: Trust timestamps on topic docs — trust the verifier
A doc with `updated: 2026-03-01` at the top can still be wrong. Timestamps lie. The verifier tells you what's actually out of sync.

### DON'T 8: Rewrite everything when a stat changes
When `AGENT_MAP` goes from 80 → 83, don't edit 30 docs. Update the two anchor docs, run the verifier, add pointer headers to anything that still drifts. Total time: 15 minutes vs 3 hours.

### DON'T 9: Treat handoffs as optional
Zero exceptions across 1100 sessions. Every skipped handoff became a confused next session.

### DON'T 10: Skip `build_docs_index` after doc changes
The embedding layer is your AI's *eyes*. Not running `build_docs_index` is blindfolding it. Put it in a pre-commit hook.

### DON'T 11: `rm` a doc to "clean up clutter"
If a doc is stale, move it to `docs/archive/<year>/`. If it's been superseded, tag it `status: superseded` in frontmatter and add a pointer to the replacement. If it's a one-off note that never grew up, rename it with a `_DRAFT_` prefix. **The cost of keeping a stale doc is ~0. The cost of deleting a good one is irrecoverable.** The whole corpus, including the messy parts, is potential white-paper / retrospective material. See DO 11 for the full reasoning.

---

## Meta-Rule

**If you catch yourself adding a new rule to this list, add it here the same day.** The pattern's value compounds when the lessons are captured while they're still raw. A week later, you'll have forgotten exactly which PR the incident happened in.

The platform's failure modes are surprisingly few — ~22 rules covers most of them. Adding rule 23 means you've found a new one.

---

*"The docs are the platform." If you believe that, these rules are free. If you don't, you'll relearn each one the hard way.*
