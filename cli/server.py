"""context-kit `start` subcommand: localhost onboarding server.

Serves a single self-contained HTML page that welcomes the developer to
their new project and points them at the load-bearing files. Standard
library only — no external dependencies.
"""

from __future__ import annotations

import argparse
import html
import http.server
import re
import socket
import sys
import webbrowser
from pathlib import Path

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


class _OnboardingHandler(http.server.BaseHTTPRequestHandler):
    """Serves a single page on / and /index.html; 404 everywhere else."""

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        if self.path not in ("/", "/index.html"):
            self.send_error(404, "Not Found")
            return
        body: bytes = getattr(self.server, "onboarding_html", "").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - shadow OK
        # Silence the default per-request access log. Parameter names must
        # match ``BaseHTTPRequestHandler.log_message`` exactly; ``del``
        # marks them intentionally unused.
        del format, args


def run_start(args: argparse.Namespace) -> int:
    """Entry point for the ``start`` subcommand dispatched from context_kit.py."""
    project_root = Path.cwd().resolve()

    looks_like_project = (
        (project_root / "00-START-NEXT-SESSION.md").exists()
        or (project_root / "docs" / "docs-pattern").is_dir()
    )
    if not looks_like_project:
        sys.stderr.write(
            f"warning: {project_root} does not look like a context-kit project "
            f"(no 00-START-NEXT-SESSION.md or docs/docs-pattern/ found). "
            f"Continuing anyway.\n"
        )

    port = _pick_port(args.port, args.host)
    url = f"http://{args.host}:{port}/"
    body = _render_html(project_root, url)

    server = http.server.HTTPServer((args.host, port), _OnboardingHandler)
    # Attach the rendered HTML so the handler can read it off self.server.
    server.onboarding_html = body  # type: ignore[attr-defined]

    print(f"context-kit: onboarding server running at {url}")
    print("context-kit: press Ctrl+C to stop.")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # pragma: no cover — webbrowser is best-effort
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncontext-kit: shutting down.")
    finally:
        server.server_close()

    return 0
