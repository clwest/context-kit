---
title: "Session 008 — context-kit start beginner wizard"
date: 2026-04-25
status: shipped
---

# Session 008 — `context-kit start` beginner wizard

`context-kit start` is now the beginner entry point. Pip install,
sit in your terminal, run one command, get a guided onboarding page
that walks you through everything else. The CLI is unchanged for
experienced users; the wizard is a guided wrapper, not a replacement.

## Origin

The discoverability problem the human named: a true beginner can
maybe get as far as `pip install contextkit-ai`. After that they're
in a terminal staring at commands they don't yet understand
(`init`, `seed`, `recommend-stack`, `doctor`, `orient`). The CLI is
useful but not discoverable. We needed a single command beginners
can remember. `start` already opened a localhost page; this session
extended it into a 7-step wizard.

## What shipped

`cli/server.py` extended (rather than rewritten) to handle multiple
routes via one `_OnboardingHandler`. New routes:

| Route | Method | Purpose |
|---|---|---|
| `/`, `/index.html` | GET | Existing project-view page (unchanged) |
| `/wizard` | GET | Beginner wizard HTML |
| `/api/state` | GET | Classify cwd: `none` / `scaffold` / `seeded` |
| `/api/idea` | POST | Write `idea.md` to a project subdirectory |
| `/api/check?step=init\|seed&project_dir=…` | GET | Verify a CLI step ran |

`cli/_static/wizard.html` (~480 lines) — single self-contained HTML
file with inline CSS + vanilla JS. No external dependencies, no
framework. Ships as package data via the new `_static/*` glob in
`pyproject.toml`'s `[tool.setuptools.package-data]`.

`run_start` now decides which page to open in the browser:

| Detected state | Browser opens |
|---|---|
| `none` (no project markers) | `/wizard` (full beginner flow) |
| `scaffold` (init'd, not seeded) | `/wizard` (jumps to step 5) |
| `seeded` or anything else | `/` (existing project view) |

If someone wants to view the existing page even from a fresh
directory, `/` is always reachable; the wizard's footer links to it.

## The 7 wizard steps

1. **Welcome** — plain-language explanation of what context-kit does
2. **Where will the project live?** — app name + project folder name
   (auto-derived; editable)
3. **What are you building?** — textareas matching IDEA_SCHEMA
   structure; `What are we building?` is required, the rest optional
4. **Save your idea.md** — preview + POST to `/api/idea` → server
   writes the file
5. **Initialize the project** — copy-paste `context-kit init "<name>"`,
   then "I ran it" → `/api/check?step=init` polls for `00-START`
6. **(Optional) See the recommended stack** — copy-paste
   `context-kit recommend-stack`. Skippable; seed auto-fills if you
   skip
7. **Seed the project** — copy-paste `context-kit seed idea.md`,
   then "I ran it" → `/api/check?step=seed` polls for `BUILD_PLAN.md`
8. **Doctor + you're ready** — copy-paste `context-kit doctor`, then
   the AI-tool-agnostic ready message:
   *"Open this folder in your AI coding tool. If you use Claude Code,
   run `claude`; the bundled skill should load automatically."*

(Yes, that's 8 sections; the first two were merged in the design but
expanded back to two for input clarity. Functionally still 7 steps
of progress.)

## Hybrid execution model (per design)

- **Wizard writes `idea.md`** via POST to `/api/idea`. The only file
  the wizard itself writes.
- **Every CLI step is copy-paste.** Each step shows the exact
  command in a code block with a one-click "Copy" button.
- **Filesystem polling verifies completion** before advancing.
  Click "I ran it"; server checks for the expected file; advance only
  if found. If not found: friendly "Doesn't look like that worked
  yet — run from your project's parent directory and try again."

This kept MVP scope tight: no subprocess execution, no shelling out,
no error mirroring in the browser. The user sees their commands run
in their own terminal where they can read errors directly.

## State persistence

Browser `localStorage` under key `contextkit:wizard:v1`. Saves on
every input change. Closing the tab and re-running `context-kit start`
prompts: "Resume your in-progress wizard at step N? Cancel to start
over." Server is stateless beyond the cwd.

If the server is killed and restarted, the new server's `/api/state`
re-detects project state from the filesystem. The wizard reconciles:
if state says `scaffold`, the wizard jumps the user to step 5
(rather than re-asking them to create a new project).

## Path safety

`POST /api/idea` resolves the requested `project_dir` against the
server's cwd and rejects anything outside it. Tests cover:

- `..` traversal → 400
- absolute path outside cwd (e.g. `/etc/passwd`) → 400
- nested `dotdot` (e.g. `med-tracker/../../sneaky`) → 400
- empty string or `.` → resolves to cwd itself (allowed)
- simple subdirectory → allowed, created if missing

Writes are atomic (write to `.tmp`, `os.replace` to final).

## Tests

21 new tests in `tests/test_wizard.py`:

- `_detect_project_state` for empty / scaffold / seeded directories
- `_safe_project_path` for the 5 cases above
- `_load_wizard_html` returns the bundled HTML
- Live-server integration: `/`, `/wizard`, `/api/state`, POST
  `/api/idea` (success + 4 failure modes), `/api/check?step=init`
  (satisfied + unsatisfied), `/api/check?step=seed` (unsatisfied),
  unknown step → 400, unknown path → 404

Total suite: **223 tests** (was 202; +21).

## Files changed

```
A  cli/_static/wizard.html                      ~480 lines
A  tests/test_wizard.py                         ~250 lines, 21 tests
A  docs/handoffs/SESSION_008_START_WIZARD.md    this file
M  cli/server.py                                3 new helpers
                                                + extended handler
                                                + run_start decides
                                                landing page from
                                                project state
M  pyproject.toml                               cli/_static/* added
                                                to package-data
M  README.md                                    quickstart now leads
                                                with `context-kit
                                                start` as the beginner
                                                entry point
M  CHANGELOG.md                                 Unreleased entry
M  docs/CONTEXT_KIT_INVENTORY.md                regen
```

## Verification

```
unittest discover                223/223 OK
inventory --check                current
context-kit start (in empty /tmp dir)
                                 server logs "opening /wizard"
                                 (existing onboarding HTML still at /)
context-kit start (in seeded /tmp project)
                                 server logs "opening /"
                                 (existing behavior unchanged)
wheel build                      contextkit_ai-0.5.0.{whl,tar.gz}
                                 includes cli/_static/wizard.html
clean-venv install + start       wizard HTML served at /wizard;
                                 /api/state returns project_state=none;
                                 POST /api/idea writes idea.md;
                                 /api/check?step=init detects after
                                 user runs init in another terminal
```

## Design choices that held up

- **Hybrid (write idea.md, copy-paste commands)** kept MVP scope
  honest. Subprocess execution adds 5x the surface area for ~20%
  more polish; defer to v2 if dogfood feedback says it matters.
- **localStorage** is the right state location — closing the tab
  shouldn't lose work; closing the server shouldn't either; the
  next `start` should pick up where the user left off. Server-side
  state files would have edge cases around "where do I write the
  state file before the project exists?"
- **Conservative project-state detection** — only classify as a
  context-kit project when both `00-START-NEXT-SESSION.md` AND
  recognizable scaffolding signals are present. False positives
  here would route the user to the wrong page.
- **Strict path safety** on `/api/idea` — even though localhost-only,
  a malicious page in another tab could in principle POST to
  `127.0.0.1:<port>/api/idea`. Restricting writes to cwd-and-below is
  cheap defense.
- **AI-tool-agnostic ready message** (per the human's explicit
  refinement). Claude Code is named first ("If you use Claude Code,
  run `claude`; the bundled skill should load automatically") but
  other AI tools are acknowledged.

## Known follow-ups (not in scope this session)

- **Subprocess execution** as opt-in v2 feature. Per-step "Run for
  me" button that POSTs to `/api/run/<command>` with confirmation
  gate.
- **Inline doctor results** in the wizard rather than terminal-only.
- **Stack picker UI** (radio/checkboxes) instead of open-text Tech
  stack textarea.
- **Project gallery** ("Recent projects" / "Open another").
- **CSRF protection** on POST endpoints once the server's attack
  surface grows beyond localhost-only.
- **Wizard accessibility audit** — works for screen readers? Color
  contrast? Tab order? MVP is reasonable but not formally audited.

## AI Notes

- The decision to extend the existing `_OnboardingHandler` rather than
  add a parallel handler kept things clean. The handler's
  responsibility grew from "serve one HTML page" to "dispatch by path
  + handle GET/POST", but it's still a single class with a clear
  responsibility ("the localhost wizard server"). Refactor cost was
  modest.
- Path safety is the most security-relevant code in this module so
  far. `_safe_project_path` lives next to the existing helpers, with
  a clear docstring and tests covering 5 attack patterns. Worth a
  second look before any v2 expands the POST API surface.
- The wizard HTML is intentionally vanilla — no framework, no build
  step, no NPM. It's ~480 lines, all in one file. If/when it grows
  past ~700 lines, split into separate `.html` + `.css` + `.js`
  files (still bundled as package data; bootstrap handler updated to
  serve each). For now, single-file is the right balance.
- The wizard's "I ran it" pattern with filesystem polling caught a
  real UX concern during design: users running commands in the wrong
  cwd. The polling failure message explicitly suggests
  "run from your project's parent directory." Beginners do hit this.
- Localhost-only is the only real security model for now. The server
  binds to 127.0.0.1 by default; the wizard's POST endpoint accepts
  any origin (no CORS check). Acceptable while we're localhost-only;
  flag for v2 if remote use cases appear.
