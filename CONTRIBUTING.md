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

All 49 tests should pass in under a second. CI runs the same command across
Python 3.9, 3.10, 3.11, and 3.12.

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
