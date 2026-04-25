"""context-kit `start` subcommand: localhost onboarding server.

Two pages:

- ``/``        — the existing project-view onboarding page (when the user
                 already has an init'd context-kit project)
- ``/wizard``  — the beginner wizard (when the user has nothing yet, or
                 has scaffolded but not seeded)

Plus three small JSON APIs the wizard calls into:

- ``GET  /api/state``                              — classify cwd
- ``POST /api/idea``                                — write idea.md
- ``GET  /api/check?step={init|seed}&project_dir`` — verify a CLI step ran

The wizard writes only ``idea.md``. Every CLI step (`init`, `seed`,
`doctor`) is copy-paste — the wizard polls the filesystem to verify
they ran before advancing.

Standard library only — no external dependencies.
"""

from __future__ import annotations

import argparse
import html
import http.server
import importlib.resources as resources
import json
import os
import re
import socket
import sys
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

# Single-page onboarding template. Placeholders use ``{{NAME}}`` syntax so
# the substitution matches the rest of context-kit.
ONBOARDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Welcome to your {{PROJECT_TITLE}} project</title>
<style>
  :root {
    --bg: #0f1117;
    --panel: #151822;
    --border: #262a35;
    --text: #e5e7eb;
    --muted: #9ca3af;
    --accent: #6ee7b7;
    --danger: #f87171;
    --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg: #fafbfc;
      --panel: #ffffff;
      --border: #e5e7eb;
      --text: #111827;
      --muted: #6b7280;
      --accent: #059669;
      --danger: #dc2626;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
  }
  .wrap { max-width: 780px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }
  h1 { font-size: 1.9rem; margin: 0 0 .25rem; letter-spacing: -0.01em; }
  .tag { color: var(--muted); font-size: .9rem; margin-bottom: 1rem; }
  .project-root {
    font-family: var(--mono);
    font-size: .8rem;
    color: var(--muted);
    word-break: break-all;
    margin-bottom: 2rem;
  }
  section {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1.25rem;
  }
  h2 { font-size: 1.1rem; margin: 0 0 .75rem; }
  p { margin: .25rem 0 .75rem; }
  ul, ol { margin: .25rem 0; padding-left: 1.25rem; }
  li { margin: .3rem 0; }
  code {
    font-family: var(--mono);
    background: var(--border);
    padding: .1rem .35rem;
    border-radius: 4px;
    font-size: .9em;
  }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
  .do h2 { color: var(--accent); }
  .dont h2 { color: var(--danger); }
  .missing { color: var(--muted); font-size: .85em; }
  footer { color: var(--muted); font-size: .85rem; margin-top: 2rem; }
  kbd {
    font-family: var(--mono);
    background: var(--border);
    border-radius: 4px;
    padding: .05rem .4rem;
    font-size: .85em;
  }
</style>
</head>
<body>
  <div class="wrap">
    <h1>Welcome to your {{PROJECT_TITLE}} project</h1>
    <div class="tag">Powered by <strong>context-kit</strong> &mdash; first-session onboarding</div>
    <div class="project-root">{{PROJECT_ROOT}}</div>

    <section>
      <h2>First Steps</h2>
      <ol>
        <li>Open <code>00-START-NEXT-SESSION.md</code>.</li>
        <li>Read the <em>SOURCE OF TRUTH</em> section at the top.</li>
        <li>Begin your first AI session with that file in the assistant's context.</li>
      </ol>
    </section>

    <section>
      <h2>Why this exists</h2>
      <p>context-kit helps you maintain context across AI sessions by separating
      <em>narrative truth</em> from <em>runtime truth</em> and enforcing
      structure that future AI sessions can rely on. Without it, docs drift,
      the AI hallucinates confidently, and every new session starts from cold.</p>
    </section>

    <div class="grid">
      <section class="do">
        <h2>Do</h2>
        <ul>
          <li>Keep docs structured (use subdirectories under <code>docs/</code>).</li>
          <li>Write a session handoff at every session <em>end</em>, not next session's start.</li>
          <li>Use the inventory as runtime truth when docs disagree.</li>
          <li>Let the AI push back when something looks wrong.</li>
        </ul>
      </section>
      <section class="dont">
        <h2>Don't</h2>
        <ul>
          <li>Duplicate numbers across multiple docs.</li>
          <li>Trust stale data &mdash; re-run the verifier before citing.</li>
          <li>Skip session handoffs &mdash; zero exceptions, ever.</li>
          <li>Delete docs to &ldquo;clean up clutter.&rdquo; Archive instead.</li>
        </ul>
      </section>
    </div>

    <section>
      <h2>Key Files</h2>
      <ul>
        {{KEY_FILES_LIST}}
      </ul>
    </section>

    <section>
      <h2>Next commands</h2>
      <ul>
        <li><code>open 00-START-NEXT-SESSION.md</code> &mdash; or read it in your editor</li>
        <li><code>ls docs/docs-pattern/</code> &mdash; the full teaching guide</li>
        <li>If you bootstrapped with <code>--with-scaffold</code>:
            <code>python3 scaffold/python/build_docs_index.py</code></li>
      </ul>
    </section>

    <footer>
      Running at <code>{{URL}}</code> &mdash; press <kbd>Ctrl+C</kbd> in the terminal to stop.
    </footer>
  </div>
</body>
</html>
"""


def _find_project_title(project_root: Path) -> str:
    """Extract the project's display title from the narrative anchor doc."""
    for md in sorted(project_root.glob("docs/*_WHAT_IT_IS.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        if not match:
            continue
        title_match = re.search(
            r'^title:\s*"?([^"\n]+?)"?\s*$', match.group(1), re.MULTILINE
        )
        if title_match:
            # Strip common narrative-doc suffix like " — What It Actually Is".
            return re.sub(r"\s*[—-].*$", "", title_match.group(1)).strip()
    return project_root.name


def _key_files(project_root: Path) -> list[tuple[str, bool]]:
    """Return the canonical key-file list with presence flags."""
    entries: list[tuple[str, bool]] = []

    # Root-level entry points.
    for name in ("00-START-NEXT-SESSION.md", "CLAUDE.md"):
        entries.append((name, (project_root / name).exists()))

    # Discovered anchor docs (generic fallback if none present).
    whats = sorted(project_root.glob("docs/*_WHAT_IT_IS.md"))
    invs = sorted(project_root.glob("docs/*_INVENTORY.md"))
    if whats:
        for md in whats:
            entries.append((f"docs/{md.name}", True))
    else:
        entries.append(("docs/<APP>_WHAT_IT_IS.md", False))
    if invs:
        for md in invs:
            entries.append((f"docs/{md.name}", True))
    else:
        entries.append(("docs/<APP>_INVENTORY.md", False))

    # Remaining canonical paths.
    more = [
        ("docs/topics/", (project_root / "docs" / "topics").is_dir()),
        ("docs/handoffs/", (project_root / "docs" / "handoffs").is_dir()),
        ("docs/TRUST_CALIBRATION.md", (project_root / "docs" / "TRUST_CALIBRATION.md").exists()),
        ("docs/docs-pattern/", (project_root / "docs" / "docs-pattern").is_dir()),
    ]
    entries.extend(more)
    return entries


def _render_html(project_root: Path, url: str) -> str:
    title = html.escape(_find_project_title(project_root))
    file_items: list[str] = []
    for name, exists in _key_files(project_root):
        safe_name = html.escape(name)
        if exists:
            file_items.append(f"<li><code>{safe_name}</code></li>")
        else:
            file_items.append(
                f'<li><code>{safe_name}</code> '
                f'<span class="missing">(not yet created)</span></li>'
            )
    return (
        ONBOARDING_HTML
        .replace("{{PROJECT_TITLE}}", title)
        .replace("{{PROJECT_ROOT}}", html.escape(str(project_root)))
        .replace("{{URL}}", html.escape(url))
        .replace("{{KEY_FILES_LIST}}", "\n        ".join(file_items))
    )


def _pick_port(preferred: int, host: str) -> int:
    """Return a bindable port. Honor ``preferred`` if free, else OS-picks."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, preferred))
        except OSError:
            s.bind((host, 0))
        return s.getsockname()[1]


def _detect_project_state(cwd: Path) -> str:
    """Classify the project at ``cwd`` for wizard branching.

    Returns one of:
      - ``"none"``      no context-kit markers found
      - ``"scaffold"``  init'd, ``state: scaffold`` frontmatter
      - ``"seeded"``    seed has run (frontmatter ``state: seeded``)
      - any other state value the user has written into the frontmatter
    """
    start = cwd / "00-START-NEXT-SESSION.md"
    if not start.is_file():
        return "none"
    try:
        text = start.read_text(encoding="utf-8")
    except OSError:
        return "none"
    if not text.startswith("---\n"):
        return "scaffold"  # init'd but no frontmatter (older template)
    end_idx = text.find("\n---\n", 4)
    if end_idx < 0:
        return "scaffold"
    fm = text[4:end_idx]
    for line in fm.splitlines():
        s = line.strip()
        if s.startswith("state:"):
            return s[len("state:"):].strip() or "scaffold"
    return "scaffold"


def _safe_project_path(cwd: Path, requested: str) -> Path:
    """Resolve ``requested`` relative to ``cwd``; reject traversal.

    Raises ``ValueError`` if the resolved path escapes ``cwd``.
    """
    cwd = cwd.resolve()
    if requested in ("", ".", "./"):
        return cwd
    candidate = (cwd / requested).resolve()
    try:
        candidate.relative_to(cwd)
    except ValueError as exc:
        raise ValueError(
            f"path {requested!r} resolves outside the project root {cwd}"
        ) from exc
    return candidate


def _load_wizard_html() -> Optional[str]:
    """Read the bundled wizard HTML from the cli package's ``_static`` dir.

    Returns ``None`` when the asset isn't present (e.g., in a generated
    project's reduced ``cli`` package). Callers should fall back to
    redirecting the user at ``/`` in that case.
    """
    try:
        return (resources.files("cli") / "_static" / "wizard.html").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return None


class _OnboardingHandler(http.server.BaseHTTPRequestHandler):
    """Routes:

    - ``/``, ``/index.html``               existing project-view page
    - ``/wizard``                          beginner wizard HTML
    - ``GET  /api/state``                  JSON classify cwd
    - ``GET  /api/check?step=...&...``     JSON poll filesystem
    - ``POST /api/idea``                   write idea.md to a project subdir

    Per-route handler context lives on ``self.server``:
    - ``onboarding_html``  pre-rendered HTML for ``/``
    - ``wizard_html``      pre-loaded HTML for ``/wizard`` (or fallback)
    - ``cwd``              the cwd ``run_start`` was invoked from
    """

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._send_html(getattr(self.server, "onboarding_html", ""))
            return
        if path == "/wizard":
            wizard = getattr(self.server, "wizard_html", None)
            if wizard:
                self._send_html(wizard)
            else:
                # No wizard available (running from a generated project's
                # local cli/ which doesn't ship _static/). Send a friendly
                # redirect-style note rather than 404.
                self._send_html(
                    "<!doctype html><meta charset=utf-8>"
                    "<title>Wizard not available</title>"
                    "<body style='font-family:system-ui;max-width:40rem;"
                    "margin:3rem auto;padding:0 1rem'>"
                    "<h1>Wizard not available here</h1>"
                    "<p>The beginner wizard ships in the installed "
                    "<code>contextkit-ai</code> package but not in a "
                    "generated project's local copy. <a href='/'>Open the "
                    "project view instead</a>.</p></body>"
                )
            return
        if path == "/api/state":
            self._handle_api_state()
            return
        if path == "/api/check":
            params = urllib.parse.parse_qs(query)
            self._handle_api_check(params)
            return
        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802 — http.server API
        path, _, _ = self.path.partition("?")
        if path == "/api/idea":
            self._handle_api_idea()
            return
        self.send_error(404, "Not Found")

    # ---- handlers -----------------------------------------------------

    def _handle_api_state(self) -> None:
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        state = _detect_project_state(cwd)
        if state == "none":
            suggested = "welcome"
        elif state == "scaffold":
            suggested = "recommend-stack"
        else:
            suggested = "open-existing"
        self._send_json({
            "cwd": str(cwd),
            "project_state": state,
            "suggested_step": suggested,
        })

    def _handle_api_idea(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_error_json(400, "invalid Content-Length")
            return
        if length <= 0 or length > 256_000:
            self._send_error_json(400, "request body must be 1..256000 bytes")
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send_error_json(400, "request body is not valid JSON")
            return
        project_dir = payload.get("project_dir", "")
        content = payload.get("content", "")
        if not isinstance(project_dir, str) or not isinstance(content, str):
            self._send_error_json(400, "project_dir and content must be strings")
            return
        if not content.strip():
            self._send_error_json(400, "content is empty")
            return
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        try:
            target_dir = _safe_project_path(cwd, project_dir)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "idea.md"
            tmp = target.with_suffix(".md.tmp")
            tmp.write_text(content, encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:
            self._send_error_json(500, f"failed to write idea.md: {exc}")
            return
        self._send_json({"written": True, "path": str(target)})

    def _handle_api_check(self, params: dict) -> None:
        step = (params.get("step") or [""])[0]
        project_dir = (params.get("project_dir") or ["."])[0]
        cwd = getattr(self.server, "cwd", Path.cwd()).resolve()
        try:
            target_dir = _safe_project_path(cwd, project_dir)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return
        if step == "init":
            satisfied = (target_dir / "00-START-NEXT-SESSION.md").is_file()
            reason = "00-START-NEXT-SESSION.md present" if satisfied \
                else "00-START-NEXT-SESSION.md not found in project_dir"
        elif step == "seed":
            satisfied = (target_dir / "docs" / "BUILD_PLAN.md").is_file()
            reason = "docs/BUILD_PLAN.md present" if satisfied \
                else "docs/BUILD_PLAN.md not found in project_dir"
        else:
            self._send_error_json(400, f"unknown step: {step!r} (expected init|seed)")
            return
        self._send_json({"satisfied": satisfied, "reason": reason})

    # ---- low-level send helpers --------------------------------------

    def _send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - shadow OK
        # Silence the default per-request access log. Parameter names must
        # match ``BaseHTTPRequestHandler.log_message`` exactly; ``del``
        # marks them intentionally unused.
        del format, args


def run_start(args: argparse.Namespace) -> int:
    """Entry point for the ``start`` subcommand dispatched from context_kit.py."""
    project_root = Path.cwd().resolve()

    port = _pick_port(args.port, args.host)
    base_url = f"http://{args.host}:{port}"
    body = _render_html(project_root, base_url + "/")
    wizard_body = _load_wizard_html()

    # Decide which page to open in the browser. If we're in a fresh dir
    # (no project markers), the wizard is the right beginner entry. If
    # a project is already seeded, open the existing project view.
    state = _detect_project_state(project_root)
    if state in ("none", "scaffold") and wizard_body:
        landing_path = "/wizard"
    else:
        landing_path = "/"
    landing_url = base_url + landing_path

    # Only warn when the user landed on the project view but the dir
    # doesn't actually look like a project. (When the wizard is opening,
    # "no project here yet" is the expected state, not a warning.)
    if landing_path == "/" and state == "none":
        sys.stderr.write(
            f"warning: {project_root} does not look like a context-kit project "
            f"(no 00-START-NEXT-SESSION.md or docs/docs-pattern/ found). "
            f"Continuing anyway.\n"
        )

    server = http.server.HTTPServer((args.host, port), _OnboardingHandler)
    # Attach handler context (read in the request handler off self.server).
    server.onboarding_html = body  # type: ignore[attr-defined]
    server.wizard_html = wizard_body  # type: ignore[attr-defined]
    server.cwd = project_root  # type: ignore[attr-defined]

    print(f"context-kit: server running at {base_url}")
    print(f"context-kit: opening {landing_url}")
    print("context-kit: press Ctrl+C to stop.")

    if not args.no_browser:
        try:
            webbrowser.open(landing_url)
        except Exception:  # pragma: no cover — webbrowser is best-effort
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncontext-kit: shutting down.")
    finally:
        server.server_close()

    return 0
