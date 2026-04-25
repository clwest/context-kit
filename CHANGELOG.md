# Changelog

All notable changes to context-kit are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `context-kit orient` — prints the project's assembled session-start
  context (start-here doc, two-doc anchor preview, latest handoff,
  pattern pointers) so an agent or returning human reads from a single
  authoritative path instead of guessing which file to open first.
- Claude Code skill at `skills/context-kit/SKILL.md`, copied into every
  generated project at `.claude/skills/context-kit/SKILL.md`. An agent
  loads the skill, runs `orient`, and follows the priority order — no
  human prompt required to bootstrap a new session.
- `context-kit hotpath` — read-only file-size dashboard. Lists the
  largest files in a project and warns when any single file exceeds
  50 KB or the top 10 sum exceeds 200 KB (both tunable). Prefers
  `git ls-files` when inside a git repo, falls back to a recursive
  walk (with sensible ignores). Inspired by Damian Tedrow's "hot
  path" observation that file size is a strong proxy for whether a
  region of code will fit comfortably in an AI session's context.

## [0.3.0] — 2026-04-21

First public release.

### Added
- `context-kit init <NAME>` — scaffold an AI-friendly project with the
  docs-pattern framework: narrative + runtime anchors, drift verifier,
  session handoffs, and AI/human collaboration conventions.
- `context-kit start` — localhost onboarding server that shows the
  first-session checklist and auto-discovers key files in the project.
- 8 guide docs distilled from ~1,100 AI-assisted build sessions over
  ~18 months (`01_two_doc_anchor.md` through `08_collaboration_roles.md`).
- Reference templates for the two-doc anchor, session handoffs, and
  drift verifier (under `templates/`).
- Starter tree with placeholder substitution: `{{APP}}`, `{{APP_SLUG}}`,
  `{{APP_UPPER}}`, `{{APP_TITLE}}`, `{{DATE}}`, `{{YEAR}}`.
- Optional Python scaffold via `--with-scaffold`: drift verifier
  (`doc_claim_verification.py`) and docs index builder
  (`build_docs_index.py`).
- `pyproject.toml` with the `context-kit` console script.
- MIT `LICENSE`.
- GitHub Actions CI across Python 3.9, 3.10, 3.11, and 3.12.
- `unittest` test suite (49 tests) covering placeholder derivation,
  end-to-end bootstrap, and the live onboarding server.
- `CONTRIBUTING.md` with development setup and PR expectations.

### Known limitations
- Wheel distribution (`pip install context-kit` from a built wheel)
  currently ships without the starter tree and guide docs. Use editable
  installs (`pip install -e .`) for now. Proper package-data packaging
  is planned for a future release.
