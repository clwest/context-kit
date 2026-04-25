# Next Session — Start Here

> **Source of truth (read in this order):**
> 1. `docs/CONTEXT_KIT_WHAT_IT_IS.md` — narrative anchor
> 2. `docs/CONTEXT_KIT_INVENTORY.md` — runtime anchor (auto-generated)
> 3. Most recent `docs/handoffs/SESSION_NNN_*.md`
> 4. `docs/LAUNCH_FEEDBACK.md` — running feedback log (live)
>
> When any other doc disagrees with the above, the above wins.

---

## MODE: launch watch

context-kit is in the public launch period. **No new build work
until 3-5 real feedback signals are in.**

Decision gate is in `docs/LAUNCH_FEEDBACK.md`. Re-read it before
proposing any new feature, refactor, or polish. Easy to
post-rationalize a handful of "looks cool" comments as validation —
the gate exists to keep us honest.

---

## What the human is doing (off-keyboard)

Path A from Session 3: launch first, polish later. The actions live
on platforms I (the AI) can't reach directly:

1. **Reply** to Damian, Brian, Austin under their original LinkedIn
   comments using the snippets in `docs/DISTRIBUTION_NOTES.md`.
   Edit to taste. Include the demo (asciinema cast or a screen
   recording of `examples/demo.sh`).
2. **Wait ~24 hours.**
3. **Post** the long-form LinkedIn update (draft in
   `DISTRIBUTION_NOTES.md`).
4. **Wait ~24 hours.**
5. **Post** the X/Twitter thread (draft in `DISTRIBUTION_NOTES.md`).
6. PyPI publish whenever ready; messaging is "coming soon" until
   then.

The drafts are starting points, not final copy. Edit them in your
voice before posting.

---

## What I can do (on-keyboard) while you launch

- **Open a GitHub issue from any feedback signal you paste me.** I'll
  label it (`drift` / `onboarding` / `confusion` / `missing-feature` /
  `dogfood` / `feedback`) and append to `LAUNCH_FEEDBACK.md` with
  source + paraphrase + my read.
- **Help draft replies** to commenters when you want a second pair
  of eyes — but you send them, not me.
- **Triage a reproduction** when someone reports a bug or drift —
  scaffold a temp project, run the failing path, isolate the cause.
- **Pause and resume** — if a real fix becomes urgent (multiple
  people hit the same blocker), I can branch off launch-watch and
  fix it without breaking the bigger discipline.

---

## What we are NOT doing this session

- Not building new features. Not even small ones.
- Not refactoring "while we're here."
- Not polishing the README again.
- Not adding more docs unless directly in service of a feedback signal.

If you find yourself thinking "let me just quickly…" — stop. Log it
in `LAUNCH_FEEDBACK.md` under "Queued for after the recap" instead.

---

## Queued for after the recap

These were on the punch list before launch and remain on it. Pick
them up after the 3-5 signal recap, prioritized by what feedback
actually points at:

- **Add `tests` to `PATTERN_EXCLUDES`** in `cli/bootstrap.py`
  (Session 1+2 carryover; tiny fix; only do if anyone trips over it).
- **Wire `inventory --check` into CI** at `.github/workflows/`
  (proves the drift verifier prevents drift in practice).
- **PyPI publish.** Move `starter/` and the guide docs inside the
  `cli/` package as `package_data`.
- **Pre-commit hook** for inventory currency (Session 3 surfaced
  this; auto-runs `--write` then re-stages the inventory file).
- **`_cli_subcommands` introspection of generated projects' own
  entry script** (Session 2 carryover; only matters if anyone heavily
  customizes their `context_kit.py`).

---

## AI / Assistant Context

- Sessions 1-3 followed the pattern. Session 4 is *waiting on
  external signal*, which is itself part of the pattern (you don't
  build in the dark).
- `docs/TRUST_CALIBRATION.md` has one entry. Re-read before shipping
  anything that "teaches a lesson" by being wrong.
- When feedback comes in, the next handoff (`SESSION_004_*`) writes
  itself: which signals arrived, in what order, what they pointed at,
  what we decided.
