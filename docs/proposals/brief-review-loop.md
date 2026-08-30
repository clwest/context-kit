---
title: "Proposal — brief/review loop + an `adopt` launch-prompt fix"
status: proposed
created: 2026-08-26
implemented: false
source: dogfooded in ~/Donkey_Betz/scout (Sessions 1–5)
related:
  - docs/proposals/SESSION_009_ADOPT.md
  - 04_session_handoffs.md
  - 08_collaboration_roles.md
---

# Proposal — brief/review loop + an `adopt` launch-prompt fix

Conventions invented while building `~/Donkey_Betz/scout` under a
three-role split (operator routes, a review-role Claude reviews, Claude
Code builds). Scout is the testbed; context-kit is the product. This file
is **append-as-we-learn** — it accumulates deltas during Scout and becomes
the input to a context-kit session afterwards.

Nothing here is implemented in context-kit yet.

---

## Finding 0 — `adopt` writes a launch prompt that is wrong for planned repos

**This is a bug, not a feature request, and it affects every adopter with
a session plan.**

`context-kit adopt --write` embeds a full "Agent Launch Prompt" inside the
managed block of `00-START-NEXT-SESSION.md`. That file is high in the
read order, so every future agent session reads it. In a repo that already
has its own scoped build sequence, four of its instructions are actively
harmful:

| Generated instruction | Why it is wrong in a planned repo |
|---|---|
| "Propose a concrete first task before making changes." | The next task is the next unstarted session. Never self-selected. |
| "go directly to identifying the highest-value next task" | Same. Session order is fixed. |
| "Do not default to documentation updates unless the user explicitly asked" | Handoffs are a global rule; documentation is never optional. |
| "Ask before broad refactors that touch more than 3-5 files." | A "NOT this session" list is *binding* and cannot be unlocked by asking. |

There is **no flag to suppress it** (`adopt --help` offers `--write`,
`--html`, `--html-out`, `--no-browser`, `--project-summary`,
`--next-task`, `--notes`), and the block regenerates on re-run, so it
cannot be edited away. Scout's workaround was a hand-written override note
outside the markers plus a durable pointer in `CLAUDE.md` — which is a
patch every adopter would have to reinvent.

**Proposed fixes, cheapest first:**

1. `--no-launch-prompt` flag, and/or
2. `adopt` detects an existing plan/contract doc (`SESSION_PLAN.md`,
   `BUILD_PLAN.md`, a `docs/*CONTRACT*.md`) and suppresses the launch
   prompt automatically, since its whole purpose is orienting an agent in
   a repo that has no plan, and/or
3. the generated prompt defers explicitly: "If this repo has a session
   plan or job contract, follow it and ignore everything below."

Option 2 is the most in keeping with "behavior as a function of structure."

---

## Finding 1 — a pre-session document class (`BRIEF`)

context-kit has `docs/handoffs/` (what the last session shipped) and
`00-START-NEXT-SESSION.md` (what the next one should do, written by the
builder). There is no channel for **constraints known before a session
starts that the builder did not author** — the reviewer's "here is what
will bite you in this specific session."

Scout added `docs/reviews/SESSION_NNN_BRIEF.md`:

- frontmatter `status: open` → `consumed`, flipped in the session's commit
- read after the plan, before writing code
- **hard rule: a brief can never expand scope.** It constrains how a
  session does its own work; the "NOT this session" list is untouched by
  it. Without this rule a brief is a backdoor around the non-goals list,
  which is the mechanism keeping sessions small.
- carries a Disposition table the builder fills in during the session

Observed value: Session 4's brief pre-empted two defects that would
otherwise have shipped — a timestamp that would have been silently wrong
(`retrieved_at` from `now()` instead of the source fetch time, which no
test would catch), and a contract/plan seam the builder would have had to
resolve by guessing.

---

## Finding 2 — a post-session document class (`REVIEW`)

`docs/reviews/SESSION_NNN_REVIEW.md`:

- frontmatter `status: open` → `addressed`
- **an open review blocks the next session** — the builder checks
  `docs/reviews/` for `status: open` before starting anything, and an open
  review *is* the next task, overriding `00-START-NEXT-SESSION.md`
- findings are subordinate to the contract: a finding that contradicts the
  job contract is wrong by definition and gets flagged, not followed
- every finding carries reproduced evidence — real command output, not
  illustrative
- Disposition table the builder fills in

The blocking rule is what makes it structural rather than advisory. It
means the operator never has to remember to enforce a review; the repo
enforces it.

Across five Scout sessions this caught, among others: a rate limiter that
was present but unprovable, a host blocklist bypassable with a trailing
dot, a page cap that bounded stored pages instead of requests (41 requests
issued under a cap of 10), and a redirect that could carry a fetch
off-host. All four passed a green test suite.

---

## Finding 3 — the disposition-accuracy rule

The loop runs on the operator being able to read a Disposition table and
trust it without re-deriving the work. Scout hit the failure mode
immediately: a disposition claimed a calibration entry was "promoted to
`docs/TRUST_CALIBRATION.md`" when the file had not been touched in that
commit. The omission was trivial; the false claim was not — one
unverifiable row turns "spot-check the findings" into "check everything."

The fix generalizes, and it is the same rule Scout's own Job Contract §6
applies to briefs — *no claim without a source, enforced in code not by
prompt*:

1. every disposition row names its artifact — path, test name, or commit
2. each cited artifact is verified to exist before `status:` flips
3. **"not done, because X" is a legal entry; a false claim is not.**
   Deferred work goes in an open task, never in a disposition that also
   flips the status

Rule 3 matters most. The moment admitting a miss feels costly, tables
drift toward optimism, which is precisely the failure being prevented.

This generalizes past reviews — it applies to any context-kit artifact
asserting that work was done, handoffs included.

---

## Finding 4 — three roles, not two

`08_collaboration_roles.md` covers AI + human. Scout ran a third seat: an
operator who routes, a **review role** that reads the committed tree but
never builds in it, and a builder. Worth documenting as a supported shape,
including the discipline that makes it work:

- the reviewer stays out of the tree while the builder works; it reviews
  **commits**, not moving targets
- the reviewer verifies from *outside* the test suite — driving the code
  with fabricated inputs — because a wrong assumption baked into both the
  code and its tests survives a green run. Every high-severity Scout
  finding was invisible to the suite.
- the reviewer has no authority over the contract, and the operator is the
  only check on the reviewer
- product decisions get routed back to the operator rather than resolved
  by either AI (Scout: whether a later add should backfill a blank
  business name)

---

## Finding 5 — an out-of-scope channel (`OPEN_ITEMS.md`)

Split into its own proposal: `docs/proposals/open-items-channel.md`. A
scoped plan works by refusing work, and an agent that correctly declines
to build something currently has nowhere to put what it noticed. Includes
the in/out rules, an argument against silent expiry (age items to a
decision, never to a delete), and a CLI surface.

---

## Open question — where these live

Scout put briefs and reviews together in `docs/reviews/`, which is
slightly odd naming for a directory holding forward-looking documents. A
`docs/briefs/` + `docs/reviews/` split reads better; one directory keeps
all review-role output in one place. Undecided — revisit when this is
lifted into `init` / `adopt` scaffolding.

---

## Next

Append to this file as Scout Sessions 5–8 surface more. After Scout's §13
falsification test, this becomes the agenda for a context-kit session:
Finding 0 is a bug fix, Findings 1–3 are scaffolding changes to `init` and
`adopt`, Finding 4 is a guide-doc edit.

---

# Appended 2026-08-29 — deltas from a full estate session

Source is different from Findings 0–5. Those came from building Scout under
the three-role split. These came from a day spent *reading* the estate with
Cowork Claude holding memory and Claude Code executing — a config repair, a
skills extraction, three database digs, an outside assessment of
`unified-donkey-betz`, and a survey. The roles were the same; the work was
archaeology rather than construction, which surfaced a different failure class.

Eight instrument failures happened in that one day. Six of them are the same
shape and that shape is a tool opportunity.

---

## Finding 6 — a managed block is a contract, and nothing states it

`adopt` writes `<!-- context-kit:adopt:start -->` / `end` markers and a comment
saying edits outside them are preserved. That mechanism is correct and it is
the resolution to a collision that now exists: when a Cowork-layer assistant
also writes `00-START-NEXT-SESSION.md`, both parties want the same file.

The failure was live. A `session-handoff` skill was extracted from
`docs-pattern` on 2026-08-29 and shipped saying the start-here doc is
"**overwritten** every time." Run in any adopt'd repo that eats the managed
block, which then silently reappears on the next `adopt` and fights whatever
replaced it.

**Implies for context-kit:** state the contract where a writer will hit it, not
only in a comment inside the block. `orient` should report whether the current
repo has managed blocks and which files carry them, so any agent — human or
otherwise — knows which regions are not theirs before it writes. Consider a
`context-kit check-managed` that fails if a managed region has drifted from what
the tool would generate.

---

## Finding 7 — the unit of scope is sessions, not weeks

Every estimate produced across the day was given in weeks or months, and every
one was wrong by roughly an order of magnitude, because weeks price a *human
writing code*. Measured from Scout's own git history: first commit 2026-08-26
14:53, last 2026-08-27 09:28 — **19 hours** for 24,442 lines of Python and 599
tests across nine reviewed sessions.

What is actually expensive is not typing. It is coupling, decisions,
human-in-the-loop steps (operating a UI, credentials, a phone call, a customer
conversation), and verification by the operator. **A thing needing eight
sessions and no operator is smaller than a thing needing two sessions and a
customer conversation.**

**Implies for context-kit:** anywhere scaffolding asks for an estimate — session
plans, milestone planning, `adopt`'s next-actions — the unit should be sessions
plus a count of human-in-the-loop steps. Never elapsed time.

**Important exception, easy to over-correct into:** a *falsification test*
measured in weeks is correct and must not be converted. Those measure human
behaviour over time — "over four weeks, capture at least one decision per
working day", "ask the pilot thirty days later whether they still use it." A
kill test that runs as fast as the build is not testing anything.

---

## Finding 8 — removal is verified by a call that fails

Four MCP servers and two filesystem servers were removed from a config on
2026-08-29. The config file no longer mentioned them; they were still loaded and
still answering, because the host process had not restarted. **A file that
stopped naming a component is not evidence the component is absent.**

The same rule in the other direction: before reporting anything as empty or
gone, point the same reader at something known to be present and show it fires.
That check caught a test count of 98,102 that was actually 8,171 (the search had
walked into `.venv`), and a count of 0 that was actually 599 (the files were
named `tests_*.py`, not `test_*.py`).

**Implies for context-kit:** `doctor` and `verify` already check presence. Add
the negative case as a first-class result — a check that asserts absence should
be required to demonstrate its reader works, and a "0" should be reportable as
either *verified absent* or *unverifiable*, never bare.

---

## Finding 9 — an assessment needs a verdict for "keep, not shippable"

A survey of `unified-donkey-betz` scored every app against one bar: could this
reach a real person within weeks. That bar is right for the earning question and
wrong as a universal filter. Applied alone it marks the two most valuable things
in the repo — a ten-category AI-failure-mode taxonomy, and a schema for tracking
whether the human or the AI turned out to be right — as rejects, because neither
ships.

A fourth verdict was added mid-survey: **WORKSHOP** — not a product, not judged
on reach, kept because it is a useful tool for how the work is done or because it
is worth returning to. Explicitly not a soft NO. A survey producing zero WORKSHOP
entries gets re-checked.

**Implies for context-kit:** `adopt`'s assessment output classifies a repo *for
adoption*. It has no vocabulary for disposition — keep and work on, keep and
freeze, mine and archive, abandon. A repo being retrofitted is often one where
that question is live, and the tool currently makes the reader invent the
categories.

---

## Finding 10 — a decisions ledger belongs beside the handoffs

Finding 4 established three roles. It did not establish where the *outcomes* of
those roles get recorded. Across one working day the operator and the review-role
Claude produced eight decisions with real disagreement — the AI wrong outright
once, the human correcting a framing three times, several genuinely mixed. All of
it lived in prose.

`~/Donkey_Betz/DECISIONS.md` now records them append-only, using a vocabulary
lifted from a schema in `unified-donkey-betz/coleadership` that had never held a
row: **stance** (support / concern / objection / alternative / neutral),
**outcome** (pending / success / failure / mixed), **attribution** (ai / human /
both / **unknown**), and a reflection line under a stated no-shaming rule.

The two entries that matter most are the ones attributing to `human` and to
`unknown`. A ledger that only records wins is a highlight reel.

**Implies for context-kit:** a third append-only document class alongside
handoffs and the trust-calibration log. Handoffs record what happened;
calibration records where the AI was miscalibrated; a decisions ledger records
*who was right when they disagreed*, which is the only one of the three that
measures the collaboration rather than the work.

---

## Finding 11 — orientation is not optional, and the tool should make skipping it hard

An outside assessment of `unified-donkey-betz` was written from archived feature
docs, database row counts, file-size distribution and git statistics — and
without opening `00-START-NEXT-SESSION.md` or `CLAUDE.md`. It concluded the
platform was a dormant quarry.

The start-here doc says: session **3051**, a PR merged days earlier, a versioned
constitutional protocol at Playbook v0.11.0, a 37-session verify-before-build
streak, and an in-progress customer product slice with role-based access and
subscription tiers. The verdict had to be withdrawn.

The sharp part: two skills stating "read the start-here doc first" had been
extracted from that same repo and shipped **four hours earlier**. Having the rule
written down, packaged, and installed did not cause it to be followed.

**Implies for context-kit:** this is the strongest argument yet for Finding 0.
`orient` exists precisely to make this failure impossible, and it only works if
running it is the cheapest path to context. Anything that makes orientation
optional — a generic launch prompt that reads like it *is* the orientation, an
`adopt` output that looks complete on its own — actively competes with the tool's
core function.

A tool cannot enforce that an agent reads. It can make the unread path obviously
incomplete.

---

## Next, revised

Findings 0–5 remain the Scout-derived agenda. Findings 6–11 are estate-derived
and split differently:

- **6 and 11** are `orient` / `adopt` surface changes and should ship together —
  they are the same problem seen from two sides.
- **7** is a wording change across scaffolding templates, cheap, with one
  carve-out that must not be lost.
- **8** is a `doctor` / `verify` semantics change.
- **9** is new `adopt` output vocabulary.
- **10** is a new document class, and the only one requiring a new file in
  `init` scaffolding.
