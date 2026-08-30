---
title: "Proposal — role: frontmatter for docs, so audits stop guessing"
status: proposed
created: 2026-08-27
implemented: false
source: surfaced during the 2026-08 doc-audit program (scout + context-kit sessions)
related:
  - docs/proposals/brief-review-loop.md
  - docs/proposals/open-items-channel.md
  - ~/Donkey_Betz/DOC_AUDIT_PROTOCOL.md
---

# Proposal — `role:` frontmatter for docs

Add a single frontmatter key that says whether a document is a
current-state claim, an append-only record, or an archived
snapshot. Teach `doctor` and `verify` to read it. That is the whole
proposal.

## The problem, in one paragraph

Every doc-audit session so far has spent measurable time deciding
whether a given file is "history" (do not touch — a five-month-old
number is a record of what was true then) or "current-state" (must
match runtime, worth fixing on sight). The signal today is a
patchwork of filename patterns, `status:` values, dates in
frontmatter, whether the file lives in `handoffs/` or `archive/`,
and prose disclaimers like "numbers are runtime-derived." Auditors
guess. Sometimes they guess wrong — the worst possible outcome is
overwriting a record.

## The proposal

Introduce a `role:` key that every context-kit-scaffolded doc
carries in frontmatter. Exactly one of three values:

```yaml
role: current-state    # must match runtime today; fixable on sight
role: append-only      # dated entries; never touch existing entries
role: archive          # historical snapshot; do not touch at all
```

Docs without the key stay unclassified — the tool does not guess
for them. `doctor` reports the unclassified set as a warning after
some grace period.

## Concrete decisions

- **`current-state`** — anchor docs (`*_WHAT_IT_IS.md`),
  `*_INVENTORY.md`, `README.md`, `CLAUDE.md`, `00-START-NEXT-
  SESSION.md`, contract docs. Auditor may fix a stale number,
  a stale path, a broken internal link, or a wrong `status:`
  field on inspection.
- **`append-only`** — `TRUST_CALIBRATION.md`, `FALSIFICATION_LOG.md`,
  `docs/handoffs/*`, `docs/reviews/*` (once addressed), field-review
  files. Entries are dated evidence. New entries are appended;
  earlier entries are never edited.
- **`archive`** — anything under `docs/archive/` or explicitly
  moved out of active use. Read-only for every audit path.

## Why context-kit

Two audit sessions have now surfaced this. Scout has the
`TRUST_CALIBRATION` case that makes the "do not touch history"
rule load-bearing (286, 528, 542, 599 are all correct on the days
they were written). context-kit has multiple in-scope current-
state docs where the auditor had to infer role from filename plus
frontmatter, and one file (`docs/proposals/*`) whose role is
genuinely ambiguous — a proposal is neither current-state nor
history, and treating it as either loses information.

The audit protocol at `~/Donkey_Betz/DOC_AUDIT_PROTOCOL.md`
currently substitutes a table for the missing convention:

> | Treat as a claim (must match today) | Treat as history (never touch) |
> |---|---|
> | README.md | docs/handoffs/* |
> | 00-START-NEXT-SESSION.md | docs/TRUST_CALIBRATION.md |
> | *_WHAT_IT_IS.md | docs/reviews/* (closed ones) |
> | *_INVENTORY.md | docs/FALSIFICATION_LOG.md entries |
> | CLAUDE.md | anything under archive/ |

This is a mnemonic, not a machine-checkable convention. If it
lived in frontmatter and `doctor` read it, every auditor (human
or AI) would inherit the classification instead of re-deriving it.

## How `doctor` should use it

Add a check:

- **`check_doc_role_frontmatter`** — for each doc that carries
  `role:`, verify:
  - `current-state` docs whose last-modified timestamp is older
    than N sessions get a warning (they are claims that have
    gone unverified for too long).
  - `append-only` docs get a warning if the newest entry's date
    predates the last commit that touched the file by more than
    K days (something was rewritten in place).
  - `archive` docs get a warning if they have been modified in
    the last N days (archives should be frozen).

The exact thresholds are tuning. The value of the check is that it
becomes possible at all — today, the tool can't tell what kind of
staleness matters for which doc.

## How `adopt` should emit it

Every doc `adopt` scaffolds ships with `role: current-state` by
default; the templates for `handoffs/`, `reviews/`, and
`TRUST_CALIBRATION.md` ship with `role: append-only`. Users can
override — the point is that the classification exists from the
first commit.

## What this doesn't do

- Not a permissions system. `role:` is documentation for humans
  and auditing tools; nothing physically prevents editing an
  append-only file. The value is that "role: append-only" plus a
  hand-edit that removed a dated entry is now a doctor warning
  instead of a mystery.
- Not a versioning scheme. Handoffs are still numbered; archives
  still get moved by hand.
- Not a substitute for the runtime anchor. `INVENTORY.md` is
  authoritative for numbers regardless of role.

## Related, previously-proposed

- `docs/proposals/brief-review-loop.md` proposes conventions
  scout invented (brief pre-session, review post-session, open
  review blocks next session). If those land as first-class
  context-kit conventions, they need role labels: briefs are
  effectively `current-state` while `status: open`, then flip
  to `append-only` on `status: consumed`.
- `docs/proposals/open-items-channel.md` proposes an OPEN_ITEMS
  channel. That doc is `current-state` for open items and
  `append-only` for closed ones — an edge case worth naming.

## Cost

Small. A CLI check that reads frontmatter and reports mismatches.
An `adopt`-templates update to ship the new key. A one-time pass
over context-kit's own docs to classify them. Nothing that
touches shipped user projects.

## Success criterion

The next audit session (character-os) opens a doc, reads
`role: current-state`, and knows whether it is allowed to fix a
number without going back to the audit brief. If that decision
takes zero cognitive load, the proposal earned its keep.
