---
name: context-kit-guardrails
description: Use when you notice a Python project has no CI drift protection, is about to add its first GitHub Actions workflow, or is failing an existing `context-kit guardrails` run. Adds a portable CI gate that fails PRs when documentation drifts from runtime and when generated artifacts get committed. Related to but distinct from the `context-kit` orientation skill — that skill is for session start, this skill is for standing CI hygiene.
---

# context-kit-guardrails — portable CI drift gate

You are helping a project stand up (or fix) automated drift protection.
`context-kit guardrails` is the runner; this skill tells you when to
suggest it, how to install it, and where the extension points are.

## When this skill applies

Any of:

- The project has a `pyproject.toml` and no `.github/workflows/` folder,
  or a workflows folder with no drift/lint gate.
- A CI run for an existing repo-guardrails workflow just failed and the
  user is asking why.
- The user has just adopted context-kit (`context-kit adopt`) and asked
  what to wire into CI.
- The user asks about "doc drift", "keeping docs honest", or "catching
  stale claims before merge."

Do NOT apply when:

- The project is not a Python repo (guardrails is language-agnostic in
  concept, but the current runner is a Python CLI).
- The user is mid-way through a different task and CI hygiene is a
  detour they did not ask for.

## Relation to the sibling `context-kit` skill

They are separate jobs:

- **`context-kit`** — session-start orientation. Loads anchors, reads
  the latest handoff, tells the agent what state the project is in.
  Fires on every session inside a context-kit project.
- **`context-kit-guardrails`** — standing CI hygiene. Fires occasionally,
  when a project is being wired for the first time or when its CI is
  failing. The runner is a subcommand of the same CLI, but the human
  moment is different.

If the user has both concerns in one session — "orient me, then set up
CI" — do orientation first, then guardrails. Never bundle them into one
step. They deserve separate attention.

## Step 1 — Install the workflow template

From the project root:

```bash
context-kit guardrails install-workflow
```

This writes `.github/workflows/repo-guardrails.yml`. The template
installs `contextkit-ai` from PyPI and runs `context-kit guardrails run`
in strict mode on every PR to `main` and every push to `main`. No
tokens, no repository secrets, no cross-repo access.

If the workflow already exists, the command exits without overwriting.
Pass `--force` to overwrite (rare — usually you want to keep local
edits and only extend the checker via the plug-in point below).

## Step 2 — Run the checks locally

```bash
context-kit guardrails run
```

This runs two built-in checks and any plug-in checks the repo has
declared. Built-ins:

- **`verify-conflicts`** — fails on any CONFLICT finding from
  `context-kit verify`. This is the doc-vs-runtime drift gate.
- **`tracked-generated-paths`** — fails when a git-tracked path
  matches any pattern in `.context-kit/guardrails.yaml` under
  `forbidden_paths:`. Empty list = no-op.

Sample `.context-kit/guardrails.yaml`:

```yaml
# Paths that should never be committed. Standard glob syntax
# (via fnmatch), matched against git-tracked files.
forbidden_paths:
  - dist/**
  - build/**
  - "**/*.pyc"
  - docs/_index.json
```

## Step 3 — Add repo-specific checks (plug-in point)

The extracted pack **intentionally does not ship** the six UDB-specific
checks (Postgres application-name tags on Procfile entries, DOC-AUTOGEN
markers on named docs, ORM shape-signature scans). Those belong to
their repo, not to the tool. When a project needs its own assertions,
add them here:

```python
# .context-kit/guardrails.py
from pathlib import Path
from cli.guardrails import Check, CheckResult

def check_no_todo_in_readme(project: Path) -> CheckResult:
    readme = project / "README.md"
    if not readme.exists():
        return CheckResult(name="readme-no-todo", ok=True, messages=["no README"])
    lines_with_todo = [
        f"line {i}: {ln.strip()}"
        for i, ln in enumerate(readme.read_text().splitlines(), 1)
        if "TODO" in ln
    ]
    ok = not lines_with_todo
    return CheckResult(
        name="readme-no-todo",
        ok=ok,
        blocking=not ok,
        messages=lines_with_todo or ["README has no TODOs"],
        detail=f"{len(lines_with_todo)} TODO(s)",
    )

CHECKS = [Check(name="readme-no-todo", fn=check_no_todo_in_readme)]
```

The plug-in is loaded once per run; import errors and shape errors are
surfaced as a failing `plugin-load` check, so a broken plug-in cannot
silently drop the real checks.

## Step 4 — Advisory downgrades belong in the workflow file

Some checks can only run where their environment supports them. The
canonical UDB example: an inventory-freshness check that needs a live
Postgres the CI runner does not have.

The rule: **make the downgrade visible in the invocation, not hidden
in the code.** A repo-specific plug-in check that can be advisory
under CI should be listed in the workflow file, not have the "skip in
CI" logic baked into its Python:

```yaml
      - name: Run guardrails (strict, some checks advisory)
        run: context-kit guardrails run --advisory inventory-freshness
```

A reader of the workflow now sees exactly what's downgraded.

## What NOT to suggest

- Don't suggest porting the UDB-specific checks by name. They referred
  to files (`docs/PLATFORM_INVENTORY.md`, `docs/INDEX.md`,
  `docs/CAPABILITY_AUDIT.md`, …) that do not exist in the target repo.
  Extract the *shape* instead: "your generated file needs a
  DOC-AUTOGEN marker on its first non-blank line" is a shape; the
  filename is a repo detail. Put the specific version in the plug-in
  file.
- Don't add a dependency to context-kit to make a check easier. The
  tool's whole character is zero runtime deps. If a check needs a
  library, write the library into the plug-in file's project, not
  into context-kit.
- Don't quietly weaken checks. If a check is failing legitimately,
  the fix is the code or the doc, not a `# noqa` in the plug-in.

## Related commands

- `context-kit verify` — runs the same drift subsystem the
  `verify-conflicts` check uses, but human-readable. Good for
  diagnosing a failing check.
- `context-kit doctor` — environment-level checks (Python version,
  git presence, expo). Complementary — doctor is about the
  *environment* running the code, guardrails is about the *state*
  of the code.

---

*This skill ships with [context-kit](https://github.com/clwest/context-kit).
The runner is `cli/guardrails.py` in that repo.*
