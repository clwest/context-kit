# Real-World Workflow: Audit → Plan → Execute (Stacked PR Example)

This doc records a real run of the `audit → fix → exec → execute` loop
against a large external project, end-to-end. It is here to give a
concrete example to anyone evaluating whether `context-kit` is worth
adopting on their own repo.

The workflow ran on 2026-04-28 against a Django + Celery + Channels
platform with **7,928 tracked files** and ~919K LOC of application
Python. Numbers in this doc are real, not illustrative.

---

## Context

The target repo (private) was mid-cleanup at session ~1100, with a
working two-doc anchor (`PLATFORM_WHAT_IT_IS.md` +
`PLATFORM_INVENTORY.md`), an active drift verifier
(`core/services/doc_claim_verification.py`), and 662 session handoffs
under `docs/handoffs/`. The discipline was already in place; the
problem was that the discipline had accumulated a backlog the
verifier hadn't been pointed at, plus several P0 bloat items that
compound across every clone and every agent session.

The motivation for trying `context-kit` here was *not* "we don't
know what to fix." The motivation was: get an outside read, written
into the repo's own format, that we can hand to an agent and execute
incrementally without losing context between sessions.

---

## Step 1 — Audit

Ran from the project root:

```bash
context-kit audit --write
```

Two things happened:

1. `docs/audit/` was created with empty `AUDIT_V1.md` + `CLEANUP_PLAN.md`
   scaffolds. Existing `docs/audits/` and `docs/audit-2026/` were
   untouched (no path collision).
2. The audit prompt printed to stdout below a numbered "Next steps"
   block, ready to paste into an agent.

The agent then performed the audit (read-only inspection: `orient`,
`hotpath`, anchor docs, recent handoffs, `git ls-files`) and wrote
findings into `AUDIT_V1.md` and a phased cleanup plan into
`CLEANUP_PLAN.md`.

Concrete findings the audit surfaced:

- **P0 anchor drift.** `PLATFORM_INVENTORY.md` was 9 days stale
  (generated at HEAD `1f252cbb`, current HEAD was `9b5ce72e`).
  `00-START-NEXT-SESSION.md` was anchored on Session 1099 while the
  most recent commits were Session 1100. Two competing
  `*_INVENTORY.md` files existed — `BACKEND_INVENTORY.md` carried a
  doc-pointer warning *and* maintained its own stat block.
- **P0 repo bloat.** `context-kit hotpath` flagged a top-15 sum of
  **74.01 MB**: a 24 MB PNG logo, a 17.86 MB vendored doc, a 3.23 MB
  one-off pyright dump, multi-MB test artifacts, and an entire
  `venv_ml/` virtualenv tracked in git (311 files).
- **P1 process.** No CI gate on the drift verifier. ROOT_CLEANUP_PLAN
  progress was recorded only in commit messages, not the plan itself.
  Six `.env*` template variants. Three parallel audit workspaces.
- **P2 hygiene.** 103 top-level `docs/` entries. 662 session handoffs
  under one flat directory. A production-default URL in
  `tools/pa_chat.py:38` documented as a "remember to override" trap
  rather than fixed in code.
- **Calibration miss.** One finding (a top-level `"docs` "shell
  artifact") later turned out to be a misread of `git ls-files`'s
  default quoting of em-dashed filenames. Documented under §
  *Audit calibration miss* below.

The audit also explicitly named what was already going well, so the
plan didn't read as "this repo is broken" — it read as "the
discipline you've already adopted has a backlog."

---

## Step 2 — Plan Validation

```bash
context-kit fix
context-kit fix --phase 1
context-kit fix --next
```

`fix` parses `CLEANUP_PLAN.md` and prints it as a structured outline.
`--phase N` scopes to one phase; `--next` returns the first single
step. This is read-only — no file changes, no agent calls.

The point of this step was a sanity-check before letting any agent
act on the plan: are the bullets parseable, do the phases divide work
sensibly, does `--next` return something actionable. They did.

---

## Step 3 — Execution Prompt

```bash
context-kit exec --phase 1
context-kit exec --phase 2
```

`exec` reads the same `CLEANUP_PLAN.md` and renders it as a structured
prompt with six fixed sections: **Goal / Context / Instructions /
Phase tasks / Constraints / Output expectations**. The Constraints
block is doing real work — *"Do not modify source files outside the
scope of the listed tasks. Do not invent new tasks. Do not commit on
a broken test suite. Read-only operations first."* The Output
expectations block asks the agent to report back like a teammate
(concise, specific, action-oriented; what was checked / changed /
remains open / needed next).

The output is plain text, copy-pasteable, agent-ready. Where `fix`
answers *"what's the next thing to do"*, `exec` answers *"what should
I tell the agent to make it do the right thing safely."*

---

## Step 4 — Safe Execution

The agent's first move on Phase 2 was **not** to make changes. It was
a dry-run inspection that produced a teammate-style report:

- Existence + size + tracked-status of every Phase 2 target
- Code references that would break on untrack (e.g. `venv_ml/` is
  imported from `self_awareness/embeddings.py` — a real risk)
- Realistic reclaim estimate (~30 MB safe-only, vs. the plan's
  optimistic <5 MB top-15 target)
- Explicit drop list (the `"docs` false-positive task)
- Explicit deferral list (`venv_ml`, the 24 MB logo, the vendored
  doc, `.rag/corpus.jsonl`)

The user then approved a **subset** of the dry-run plan — only the
unambiguously safe items. Phase 2 split into:

- **Low-risk, this PR (executed):** untrack `.pyright-after.txt`
  (~3 MB), untrack `tests/artifacts/*.png` (16 files, ~26 MB),
  log audit calibration notes.
- **High-risk, deferred:** `venv_ml/` untrack (needs a
  venv-recreate setup script first), 24 MB logo (verify whether
  it's actually rendered live before resizing), 17.86 MB vendored
  doc (chapter-split, not "link to source repo"),
  `.rag/corpus.jsonl` (regen path not yet located),
  `docs/_index.json` (deferred pending stronger regen-equivalence
  check than `--dry-run` provides).

Each landed item was its own commit with a verifiable claim
(*"reclaims 3.2 MB"*, *"untracks 16 files"*) and a code-grep cited
in the message. Files stayed on disk via `git rm --cached` rather
than `git rm`, so a fresh checkout still works locally even before
the regen-on-bootstrap conventions land.

---

## Step 5 — Stacked PR Workflow

Two PRs, each with one focused scope:

- **Phase 1 — truth restore.** Branch `docs/phase-1-truth-restore`.
  Two commits: regen `PLATFORM_INVENTORY.md`, anchor
  `00-START-NEXT-SESSION.md` on the current session, dedupe
  `BACKEND_INVENTORY.md`'s stat block, rename
  `SESSION_ROADMAP_DISCONNECTED_FIXES.md` to drop the lex-sort-trap
  prefix. Plus a follow-up commit logging two open issues into a new
  `docs/cleanup/FOLLOWUPS.md`.
- **Phase 2 — low-risk bloat cleanup.** Branch
  `chore/phase-2-low-risk-cleanup`, **stacked on**
  `docs/phase-1-truth-restore`. Three commits: the audit calibration
  notes (correcting the `"docs` false positive and the unrealistic
  hotpath target), the `.pyright-after.txt` untrack, the
  `tests/artifacts/*.png` untrack. PR opened against
  `docs/phase-1-truth-restore` so the diff shows only the three
  Phase 2 commits, not the Phase 1 commits underneath. When Phase 1
  merges, Phase 2 retargets to `main` cleanly via the GitHub UI's
  base-branch edit — no rebase needed.

The stacking decision matters. PR-against-`main` would have shown
five commits across two unrelated themes. PR-against-the-parent
isolates the diff to one logical change set, which is what reviewers
actually want.

---

## Key Outcomes

- **Repo bloat reduced.** `context-kit hotpath` top-15 sum dropped
  **74.01 MB → 63.57 MB** (−10.44 MB) from this PR alone. The
  remaining ~15 MB to hit the corrected 25 MB-reduction target sits
  in the deferred items and will land in their own focused PRs.
- **Anchor drift fixed.** `PLATFORM_INVENTORY.md` regenerated against
  current HEAD. `00-START-NEXT-SESSION.md` now reflects Session 1100.
  `BACKEND_INVENTORY.md`'s duplicated stat table replaced with a
  one-paragraph pointer.
- **One handoff lex-sort trap closed.** `SESSION_ROADMAP_*.md` no
  longer wins selection. (A deeper layer remains — 3-digit
  `SESSION_999_*` lex-sorts after 4-digit `SESSION_1098_*` because
  ASCII `'9' > '1'` — fixed upstream in `context-kit` itself in a
  separate commit.)
- **Audit calibration miss logged.** The `"docs` false positive went
  into `docs/cleanup/FOLLOWUPS.md` as `AUDIT-CAL-2026-04-28` with the
  root cause (git's quoting behavior) and a "lesson for future
  audits" line. Same file holds the corrected hotpath target.
- **Two PRs, both reviewable.** No stack-rebase headaches. Each PR
  has one verifiable claim a reviewer can check in 30 seconds.

---

## Key Insight

The value of `context-kit` in this run was **not** one-shot
generation. The audit prompt is ~200 words; the prompts `fix` and
`exec` produce are similarly small. None of them write code.

The value was the **iteration shape** they enforced:

1. `audit --write` made the agent's findings persistent in the repo,
   not just in chat history.
2. `fix --phase N` let the human re-validate the plan before any
   action.
3. `exec --phase N` produced an agent-ready prompt with explicit
   anti-scope-creep constraints — so when the agent asked *"can I
   also fix this other thing I noticed"*, the constraint block had
   already said no.
4. The agent's dry-run-first habit meant the human approved a
   **smaller** scope than the plan called for. The plan said "Phase
   2"; what shipped was "the safe two-thirds of Phase 2 that don't
   need ecosystem prep work first."

The agent was treated as a teammate the whole way through — same
report-back format an engineer would use after a focused work block.
Concise, specific, what-changed-and-what's-next. The team-reporting
framing was added to `audit` and `exec` prompts mid-session
(`feat(prompts): ask agents to report back like teammates`) when it
became clear that *how* the agent reported back was as important as
what it found.

---

## When to use this workflow

- **Large repos** where a single-shot audit can't fit in one context
  window — the workspace files (`AUDIT_V1.md`, `CLEANUP_PLAN.md`,
  `FOLLOWUPS.md`) are how knowledge survives between sessions.
- **Drifted documentation** where the anchor docs and the runtime
  disagree but no one knows by how much. Pair `context-kit audit`
  with the project's existing drift verifier (if one exists) for
  numeric specificity.
- **Cleanup / refactor phases** that are too big for one PR but
  shouldn't be one rolling branch of churn. The audit-driven phase
  split + stacked PRs gives you reviewable, mergeable units.
- **Any multi-step AI-assisted work** where you want the constraint
  language ("don't expand scope, don't commit on broken tests, run
  read-only ops first, append findings to FOLLOWUPS.md") baked into
  the prompt rather than re-typed every session.

When **not** to use it: small repos that fit in one context window,
one-off scripts, anything where the answer to "what should I fix" is
already obvious. The overhead of `audit --write` + a populated
`docs/audit/` workspace is worth it when the alternative is
re-discovering the same findings every session.

---

## Audit calibration miss

One finding from Step 1 was wrong, in a way worth recording so future
audits don't repeat it.

The audit flagged a top-level entry `"docs` (with a leading
double-quote) as a probable shell-redirection artifact. It wasn't.
`git ls-files` quotes any filename containing characters outside its
safe set with a wrapping pair of double-quotes. The repo has many
filenames with em-dashes (encoded as `\342\200\224`); splitting that
quoted output on `/` and taking the first field produces the string
`"docs` — which is the open-quote plus the first path component, not
a real path. Confirmed during Phase 2 dry-run via `ls -d docs/...`.

Two lessons captured under `AUDIT-CAL-2026-04-28` in
`docs/cleanup/FOLLOWUPS.md`:

- `git ls-files` output is not safe to split on `/` blindly. Use
  `git ls-files -z` and split on NUL when scripting against it.
- An `ls -d <path>` cross-check should precede any "this looks like
  a stray file" finding before it lands in an audit.

The corresponding bullet was dropped from Phase 2's execution scope
and the calibration entry now lives alongside the open follow-ups.
That's the loop closing on itself: an audit finding turns out to be
wrong, the workflow has a place to record that, and the next audit
gets better instead of repeating the mistake.
