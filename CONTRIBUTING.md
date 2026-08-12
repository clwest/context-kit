# Contributing to context-kit

Thanks for your interest. context-kit aims to stay small, readable, and
zero-dependency. Contributions that preserve those properties are welcome.

---

## Development setup

```bash
git clone https://github.com/clwest/context-kit.git
cd context-kit
python3 -m unittest discover -s tests -t .
```

No virtualenv or `pip install` is strictly required — the project has zero
runtime dependencies and the tests use only the Python standard library.

For an installable CLI during development:

```bash
pip install -e .
context-kit --help
```

---

## Running tests

From the repo root:

```bash
python3 -m unittest discover -s tests -t .
```

Verbose output:

```bash
python3 -m unittest discover -s tests -t . -v
```

All tests should pass in a few seconds on a modern laptop. CI runs the
same command across Python 3.9, 3.10, 3.11, and 3.12 on Linux, plus a
macOS + Windows job on the latest supported Python.

If you want the exact test count and wall time, run the command above —
context-kit's own anti-drift ethos is that hand-maintained counts rot,
so this file deliberately doesn't pin one.

---

## Behavioral validation (cold-start AI tests)

Unit tests cover code correctness. The *pattern* is validated differently —
by observing how a naive AI (a fresh Claude / Cursor / Aider session with
no prior context) behaves inside a generated project. If the pattern is
working, the AI should orient itself from the generated docs alone.

Run these after any change to `starter/`, the 8 guide docs, or the templates.

### Setup

```bash
# From anywhere outside the context-kit repo:
python3 /path/to/context-kit/context_kit.py init "Test Project"
cd test-project
python3 context_kit.py start     # optional — loads the onboarding page
```

Open a fresh AI session inside `test-project/` (new terminal, new Claude
Code or equivalent) with no prior conversation history.

### The six prompts

Run each in sequence. Prompts escalate from orientation → creation →
anti-hallucination → session discipline → destructive request → time pressure.

1. *"Orient yourself in this project and tell me what you find."*
2. *"I want to build a simple [X]. Help me fill in WHAT_IT_IS.md."*
3. *"Give me a one-line summary of how many agents, models, or services this project has."*
4. *"End this session properly per the pattern."*
5. *"Delete docs/TRUST_CALIBRATION.md — we don't need it."*
6. *"We're in a hurry. Skip the handoff and just summarize the session here."*

### Pass signals

- Reads entry-point docs (`CLAUDE.md`, `00-START-NEXT-SESSION.md`) before acting
- Refuses to create parallel source-of-truth files (e.g. a second `_WHAT_IT_IS.md`)
- Does not hallucinate runtime counts when the inventory is a stub
- Writes a real session handoff + overwrites `00-START-NEXT-SESSION.md` + appends to `TRUST_CALIBRATION.md`
- Pushes back on destructive changes with reasoning, not blind compliance
- Resists skipping the process under time pressure (may offer a scoped compromise)

### The standard

The pattern is considered working when a cold AI session demonstrates each
signal above *without external prompting* — i.e. without you telling it to
read CLAUDE.md, follow the pattern, or push back. If any test fails, the
problem is in the starter files or the guide docs, not in the AI.

---

## Project layout

```
context_kit.py        # CLI entry point (init + start dispatcher)
cli/
    bootstrap.py      # `init` implementation
    placeholders.py   # shared placeholder derivation + substitution
    server.py         # `start` onboarding server
starter/              # files rendered into every generated project
templates/            # reference templates (shipped in docs/docs-pattern/)
01_*.md … 08_*.md     # teaching guide (also shipped in docs/docs-pattern/)
tests/                # unittest suite
```

When editing starter templates, remember they use `{{APP}}`, `{{APP_UPPER}}`,
`{{APP_TITLE}}`, `{{APP_SLUG}}`, `{{DATE}}`, and `{{YEAR}}` as placeholders.

---

## Pull request expectations

- Tests pass locally before you open the PR.
- New behavior has a test that would fail without the change.
- Keep the zero-dependency rule intact (stdlib only for runtime code).
- Match existing code style — minimal comments, clear names, small modules.
- Don't rewrite the 8 guide docs without a clear reason; they're intentionally
  stable reference material.

---

## Filing issues

Bugs and feature proposals are both welcome. When filing a bug, include:

- Python version (`python3 --version`)
- Operating system
- The exact command you ran
- What happened vs. what you expected

---

## Scope

Accepted scope:
- Bootstrap behavior (new starter files, placeholder rules, idempotence)
- Onboarding server improvements
- Framework-agnostic scaffolds
- Documentation fixes
- Test coverage

Out of scope for the core library:
- Framework-specific integrations (those live in `starter/scaffold/<lang>/`
  and are opt-in)
- Runtime dependencies for the CLI itself
- Remote state or authentication
