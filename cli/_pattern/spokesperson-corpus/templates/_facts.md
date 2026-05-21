---
title: Verifiable Facts
slug: facts
section: Facts
status: reference
audience: public-everyone
voice: factual
sources:
  - <runtime inventory file>
  - <narrative anchor file>
updated: <YYYY-MM-DD>
---

# Verifiable Facts

Every number and falsifiable claim cited anywhere in the corpus, with a source line
pointing back to where it can be verified. The spokesperson reads this chunk when asked
to defend a claim.

If a claim is in any other chunk but not here, that claim must be removed or paraphrased
into a non-falsifiable form ("dozens", "more than a hundred").

## Format

Each fact is one row in the table below. Add to the table; do not write claims into prose
in this chunk.

| Claim | Source | Source date | Tier |
|---|---|---|---|
| <e.g. "80 spiders across 41 categories"> | PLATFORM_INVENTORY.md | 2026-05-21 | runtime-derived |
| <e.g. "Free → $99/mo for the Pro tier"> | products.ts (public taxonomy) | 2026-05-20 | public-page-derived |
| <e.g. "Founded 2024"> | About page on marketing site | 2026-05-15 | manually maintained |

## Source tiers

- **runtime-derived** — regenerable via a command; trust until the command says otherwise
- **public-page-derived** — visible on a public site; trust until the page changes
- **manually maintained** — written once; review on every corpus refresh

## Refresh

When the runtime inventory regenerates, re-verify every `runtime-derived` row. When the
public taxonomy or marketing site changes, re-verify every `public-page-derived` row.
Update the `Source date` column on any row that's been re-verified.

## Off-limits

- Do not cite a number that isn't in this table.
- Do not paraphrase a number from this table inaccurately (if the table says "80", the
  spokesperson says "80", not "around 100").
- If a row's source date is more than 90 days old, treat that row as soft — paraphrase
  rather than quote until it's re-verified.
