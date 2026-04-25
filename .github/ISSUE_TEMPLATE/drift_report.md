---
name: Drift report
about: The inventory generator says one thing; the runtime says another (or vice versa)
title: "[drift] "
labels: ["drift", "bug"]
assignees: []
---

> Use this template when `context-kit inventory --check` (or your own
> manual reading) reveals a disagreement between the auto-generated
> block and what's actually true in your project. This is the kind of
> bug context-kit exists to surface — please file it.

## What does --check say

```
$ python3 context_kit.py inventory --check
```

## What does --json say

<details>
<summary>Full JSON</summary>

```json
```

</details>

## What's actually true

<!-- The number / file / fact that doesn't match. How did you confirm? -->

## Where the drift is visible

- [ ] In the auto-generated block in `docs/CONTEXT_KIT_INVENTORY.md`
- [ ] In the JSON output
- [ ] In `orient` output
- [ ] In `hotpath` output
- [ ] Other (describe)

## Repository state

- Branch / commit:
- Was this in the source repo, a generated project, or another repo entirely?
- Anything unusual about your file layout? (custom `cli/`, missing `tests/`, etc.)

## Hypothesis

<!-- Optional. What do you think is causing the drift? A discovery rule that
     doesn't match your structure? A self-reference like the one we hit
     in Session 2? Something else? -->
