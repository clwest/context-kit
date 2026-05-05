# AGENTS — AI Session Entry Point

> **Source of truth for numbers:** `docs/{{APP_UPPER}}_WHAT_IT_IS.md` (narrative)
> + `docs/{{APP_UPPER}}_INVENTORY.md` (runtime-derived, regenerable).
> When this doc disagrees with either, INVENTORY wins.

---

## Read This First

1. Read `00-START-NEXT-SESSION.md`.
2. Read `docs/BUILD_PLAN.md` if it exists.
3. Read `docs/{{APP_UPPER}}_WHAT_IT_IS.md`.
4. Read `docs/{{APP_UPPER}}_INVENTORY.md`.
5. Run `context-kit doctor`.
6. Run `context-kit orient`.

---

## Working Rules

- Do not edit code until you have oriented on the project.
- Prefer scoped audits over broad scans.
- Close the loop before you leave:
  - if behavior changes, update the relevant docs
  - if commands, routes, or features change, refresh or verify the inventory
  - if generated artifacts appear, remove them, ignore them, or mark them intentionally tracked
  - before handoff, run `context-kit verify` and `context-kit doctor` where applicable
  - after major work, write or update a handoff note
- Runtime truth wins over stale docs, but stale docs should be corrected before you close the task.
- Avoid committing generated artifacts unless the project explicitly tracks them.
- Keep `CLAUDE.md` behavior unchanged if both files are present; follow the repo's existing entry instructions.
- When you make changes, report the commands you ran and the tests you executed.
