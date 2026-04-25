---
title: "Session 003 — Launch Templates and Demo Script"
date: 2026-04-25
status: shipped
---

# Session 003 — Launch Templates and Demo Script

A docs-only polish pass to set up the public launch loop. No new
engine work. The deliverables are the things that turn the four
shipped features (orient, skill, hotpath, inventory) into something
the public can actually try and report back on.

---

## What shipped

A single commit: `docs: add launch templates and demo script`.

### `.github/ISSUE_TEMPLATE/` — 4 templates + config

| File | Purpose |
|---|---|
| `config.yml` | Disable blank issues; redirect open-ended questions to GitHub Discussions |
| `bug_report.md` | Behavior diverges from docs/CLI help. Captures repro + environment |
| `feature_request.md` | New subcommand, flag, or behavior. Asks why it fits the pattern |
| `drift_report.md` | The thing context-kit exists to surface — `inventory --check` says one thing, runtime says another. Asks for `--check` and `--json` output by default |
| `dogfood_report.md` | "I tried it on a real project." Optional checklist of how far they got, what worked, what broke. The most valuable feedback we can get |

All four use markdown form (not GitHub's YAML form) for simplicity
and easier editing. Markdown is universal; the form UX is nice but
the maintenance burden is real and we're early.

### `examples/demo.sh` — 30-second demo

Runs the three-command loop:

1. `context-kit orient` (head -40 to fit a screen)
2. `context-kit inventory --check` (with success/failure narration)
3. `context-kit hotpath` (tail -20 for the summary)

Plus a closing block: "this repo knows what it is, what exists, and
where bloat may grow." Tunable pause via `DEMO_PAUSE` env var (set to
`0` to run silently in CI; default `1.2` for live recording).

Designed for `asciinema rec demo.cast -c examples/demo.sh`. No
external deps beyond bash and Python.

### `docs/DISTRIBUTION_NOTES.md` — launch drafts

Maintainer-only file. Drafts (not finals) for:

- Long-form LinkedIn follow-up post
- Twitter/X short thread
- Reply snippets for Damian, Brian, and Austin under their original
  LinkedIn comments
- Suggested launch ordering (replies → long post → thread → PyPI)
- A "what we deliberately aren't doing" section to keep the launch
  honest

The point is to convert the ~232 impressions + 12 comments on the
original post into a handful of *actual* dogfood reports, not into a
metrics screenshot.

---

## Verification

```
inventory --write   →  context-kit: updated docs/CONTEXT_KIT_INVENTORY.md
inventory --check   →  context-kit: inventory is current
inventory --json    →  valid JSON, 17 top-level keys, tracked count reflects staged state
orient              →  all 5 sections, latest handoff = SESSION_003_LAUNCH_TEMPLATES
hotpath             →  STATUS: OK, top 10 sum ~88-90 KB / total ~270 KB
unittest discover   →  89 tests, OK
demo.sh (DEMO_PAUSE=0) →  exits 0, all three commands run cleanly
```

---

## Files changed

```
A  .github/ISSUE_TEMPLATE/config.yml
A  .github/ISSUE_TEMPLATE/bug_report.md
A  .github/ISSUE_TEMPLATE/feature_request.md
A  .github/ISSUE_TEMPLATE/drift_report.md
A  .github/ISSUE_TEMPLATE/dogfood_report.md
A  examples/demo.sh                                  (executable)
A  docs/DISTRIBUTION_NOTES.md
A  docs/handoffs/SESSION_003_LAUNCH_TEMPLATES.md     (this file)
M  docs/CONTEXT_KIT_INVENTORY.md                     (regen + new handoff count)
M  00-START-NEXT-SESSION.md                          (advance to Session 4)
```

---

## Workflow lesson surfaced this session

Inventory `--check` failed during the demo smoke test because of a
real ordering bug in my workflow:

1. I created new files (`.github/ISSUE_TEMPLATE/*`, `examples/demo.sh`).
2. I ran `inventory --write`. At that moment, `git ls-files` reported
   the count of *currently-tracked* files only — the new files were
   still untracked, so they didn't increment the count.
3. I ran the demo. The demo runs `inventory --check`. By that point,
   `git ls-files` would still report the same count *because nothing
   was staged* — but the new SESSION_003 handoff (when I write it
   below) and any other staged changes will shift the count.

The honest fix is workflow discipline: stage everything → run
`inventory --write` → re-stage the inventory file → commit. Logged in
the queued investigations of `00-START-NEXT-SESSION.md` as a
candidate for a pre-commit hook in a later session.

---

## AI Notes

- The demo script's first version had `set -e` plus a bare
  `$CKIT inventory --check`, which made the script abort
  mid-recording when inventory was stale. Fixed by wrapping the
  check in an `if/then/else` that prints either "current. CI would
  pass" or "stale. Developer fix: --write." Better narration *and*
  more robust to either outcome.
- I almost wrote the LinkedIn / Twitter drafts in voice that wasn't
  the human's. Caught it: the repo's existing voice (README, guide
  docs) is plain, declarative, no emoji, no marketing-speak. The
  drafts in `DISTRIBUTION_NOTES.md` follow that — but flagged at the
  top of the file that every section is a starting point, not
  ready-to-ship copy.
- The `[dogfood]` issue template is the one I'm most curious to see
  used. Bug reports tell you about the tool; dogfood reports tell
  you about the *fit* between the tool and someone's real life. The
  template is structured to encourage even partial reports ("I gave
  up at step 2 because X" is valuable signal).
- One small judgment call: I opted to keep `docs/DISTRIBUTION_NOTES.md`
  in `docs/` rather than create a new top-level dir. It belongs with
  the other narrative docs about the repo, even though its audience
  is just the maintainer. If anyone reading it later finds it
  awkward there, easy to move.
- No engine work this session, by design. The PATTERN_EXCLUDES gap
  for `tests/` is still untouched (Session 2 / Session 4 candidate),
  and the workflow ordering issue is logged as a future pre-commit
  hook rather than a code change.
