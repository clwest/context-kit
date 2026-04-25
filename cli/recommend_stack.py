"""context-kit `recommend-stack` subcommand: deterministic stack guidance.

For non-technical builders who know the problem but not whether they
need React or Flutter or Django. Rules are plain Python data; signals
are case-insensitive substrings. The highest-priority matching primary
rule drives the recommendation; modifier rules (lower priority) show
up in "Also detected" with a one-line note.

Always exits 0 — this is advisory, not gating. Use `--json` for
machine-readable output.

Shared with `seed`: when an idea file's `## Tech stack` section is
missing, `seed` calls `recommend()` and bakes the result into
`docs/BUILD_PLAN.md`. Dependency direction is **seed -> recommend_stack**;
never invert.

Last reviewed: 2026-04-25. Stack picks drift; bump
`LAST_REVIEWED` and audit the rules at least once per quarter.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = 1
LAST_REVIEWED = "2026-04-25"
ALSO_DETECTED_CAP = 3


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Recommendation:
    stack: list[str]
    why: list[str]
    avoid_yet: list[str]
    risks: list[str]
    upgrade_when: list[str]


@dataclass
class Rule:
    name: str
    signals: list[str]
    priority: int                    # higher = wins as primary
    recommendation: Recommendation
    is_modifier: bool = False        # modifiers can never be primary
    note: str = ""                   # one-line lens for "Also detected"


@dataclass
class Match:
    rule: Rule
    matched_signals: list[str]


@dataclass
class RecommendationResult:
    primary: Optional[Rule]
    also_detected: list[Match]
    recommendation: Recommendation   # the primary's, or fallback


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


_PRACTICAL_PRIVACY_NOTE = (
    "Personal local-only use avoids most privacy/compliance complexity. "
    "If you later store/share health data for multiple users, talk to a lawyer."
)


RULES: list[Rule] = [
    Rule(
        name="medication-reminders",
        priority=10,
        signals=[
            "medication", "medications", "medicine", "medicines",
            "pills", "pill",
            "dose", "doses", "dosage",
            "remind to take", "med tracker", "med reminder",
        ],
        recommendation=Recommendation(
            stack=[
                "Expo React Native (one codebase for iPhone + Android)",
                "Expo Notifications (local push reminders)",
                "expo-sqlite (local-first medication + dose history)",
                "react-native-paper (accessible, large-touch UI components)",
                "No backend, no accounts",
            ],
            why=[
                "Reminders need real push notifications — that means a real mobile app, not a web page.",
                "Local-first storage keeps medical data on the device — simple, private, no servers to manage.",
                "Expo lets you ship to TestFlight without ever opening Xcode or Android Studio.",
                "Accessibility matters: design for large tap targets, simple language, "
                "high contrast, and minimal screens. Most v0 medication apps overdo the UI.",
            ],
            avoid_yet=[
                "Cloud backend",
                "User accounts / login",
                "Cross-device sync",
                "Caregiver / family-sharing dashboard",
                "Multi-step flows when one screen will do",
                "Apple HealthKit integration (only add later if it earns its keep)",
            ],
            risks=[
                "Push notifications only fire when the user accepts the OS prompt — "
                "first-run UX matters.",
                "Local-only data means a phone reset wipes everything — add an "
                "'export to PDF/email' button as a poor man's backup.",
                _PRACTICAL_PRIVACY_NOTE,
            ],
            upgrade_when=[
                "A caregiver needs to see reminders too -> add a small Django + "
                "Postgres backend with caregiver invites.",
                "You want medication info auto-filled (drug name, dose ranges) -> "
                "use a free public API like RxNorm.",
                "You grow to a real product with shared health data -> now you "
                "need real compliance (HIPAA, etc.); talk to a lawyer first.",
            ],
        ),
    ),

    Rule(
        name="mobile-personal-tracking",
        priority=8,
        signals=[
            "track daily", "daily tracking", "habit", "habits",
            "journal", "journaling", "diary",
            "kids", "fitness", "steps", "water", "mood", "streak",
            "personal log",
        ],
        recommendation=Recommendation(
            stack=[
                "Expo React Native (mobile-first)",
                "AsyncStorage (or expo-sqlite) for local data",
                "Expo Sensors (optional — pedometer, motion)",
                "No backend, no accounts",
            ],
            why=[
                "A phone is the right form factor for daily personal tracking; web won't get used.",
                "Local storage is plenty for one user (or one family) — no shared state means no servers.",
                "Expo + AsyncStorage is the smallest amount of moving parts that ships a working app.",
            ],
            avoid_yet=[
                "Cloud backend, accounts, logins",
                "Leaderboards or social features",
                "Cross-device sync",
                "Apple HealthKit / Google Fit (add only if you want auto-pulled data)",
            ],
            risks=[
                "Daily-tracking apps often get abandoned in week 2 — design for re-engagement early.",
                "Kids' apps face Apple/Google parental-control constraints; some APIs are restricted.",
            ],
            upgrade_when=[
                "Streak data needs to survive a phone reset -> add iCloud/Google Drive backup before any real backend.",
                "Multiple people want to compete or share -> add a small backend (Django + Postgres) with simple auth.",
                "You want a parent / coach view -> separate web dashboard (Next.js) reading the same backend.",
            ],
        ),
    ),

    Rule(
        name="business-dashboard",
        priority=8,
        signals=[
            "dashboard", "admin", "internal tool",
            "business", "small business",
            "inventory", "sales", "customers", "invoices", "invoice",
            "crm", "operations",
        ],
        recommendation=Recommendation(
            stack=[
                "Next.js (App Router) — web, accessible from any device",
                "SQLite (local) or Postgres on Neon/Supabase free tier",
                "Tailwind CSS for styling",
                "Single-user, no auth (just don't share the URL) for v0",
            ],
            why=[
                "Web is the right form factor for an admin tool — works on phone or laptop, no app stores.",
                "Single-user means you can skip auth entirely until an employee actually needs access.",
                "SQLite scales to thousands of records; you don't need Postgres until you do.",
            ],
            avoid_yet=[
                "Mobile app version (PWA the web app instead if you want home-screen feel)",
                "Multi-user / employee logins",
                "Customer-facing portal (separate concern, separate build)",
                "QuickBooks / Stripe integrations (start with PDF export)",
            ],
            risks=[
                "A SQLite file on your laptop is a single source of truth — back it up to iCloud/Dropbox.",
                "Vercel hosting is free for personal projects; check pricing if usage grows.",
            ],
            upgrade_when=[
                "You add an employee -> time for auth (Clerk is the easy path) and Postgres.",
                "Customers need to see their own data -> add a separate /portal route with read-only auth.",
                "You want to send invoices automatically -> integrate Stripe or QuickBooks.",
            ],
        ),
    ),

    Rule(
        name="content-website",
        priority=6,
        signals=[
            "landing page", "marketing site", "marketing page",
            "blog", "portfolio", "personal site", "static site",
            "brochure",
        ],
        recommendation=Recommendation(
            stack=[
                "Astro (or Next.js if you already know it)",
                "Tailwind CSS",
                "Markdown files for content (no CMS yet)",
                "Hosted free on Vercel or Cloudflare Pages",
            ],
            why=[
                "Static sites are cheap, fast, and hard to break.",
                "Astro is the simplest path for a content-heavy site; Next.js if you might add interactivity later.",
                "Markdown lets you focus on writing, not on a database.",
            ],
            avoid_yet=[
                "A CMS (Sanity / Contentful / Strapi)",
                "User accounts",
                "A backend",
                "A custom domain CDN setup (Vercel/Cloudflare handle this for you)",
            ],
            risks=[
                "If non-developers need to edit content, you'll outgrow Markdown — plan to add a CMS later.",
            ],
            upgrade_when=[
                "Non-technical editors need to update content -> add a small CMS (Sanity is the easy path).",
                "You want a newsletter -> add a third-party service (Buttondown, ConvertKit) — don't build it.",
                "You want comments / community -> consider Discord/Slack instead of building it in.",
            ],
        ),
    ),

    Rule(
        name="local-automation",
        priority=8,
        signals=[
            "script", "automate", "automation", "automated",
            "files", "rename", "organize", "batch",
            "cron", "cli", "command line", "terminal",
        ],
        recommendation=Recommendation(
            stack=[
                "Python 3.11+",
                "Standard library only (pathlib, datetime, subprocess)",
                "Pillow for image work, requests for HTTP, if needed",
                "A single .py file — no packaging, no web UI",
            ],
            why=[
                "This is a 100-line script, not an app.",
                "Python's standard library covers 95% of file/automation work.",
                "Single-file scripts are the cheapest thing that could possibly work.",
            ],
            avoid_yet=[
                "A web UI (you'll never use it)",
                "A GUI (Tkinter and friends are a tar pit)",
                "Packaging as a published CLI tool",
                "A database (the filesystem IS the database)",
            ],
            risks=[
                "On the first run, copy files to a new tree and verify before deleting originals.",
                "Edge cases (missing metadata, weird filenames) are 80% of the work.",
            ],
            upgrade_when=[
                "Other people need to use it -> wrap in a tiny Click CLI, publish to PyPI.",
                "You want it to run on a schedule -> cron job (macOS/Linux) or launchd plist (macOS).",
                "Family wants a button to click -> don't build a GUI; teach them drag-and-drop into a folder a script watches.",
            ],
        ),
    ),

    Rule(
        name="web-api",
        priority=7,
        signals=[
            "api", "rest api", "graphql",
            "webhook", "webhooks",
            "backend service", "microservice",
            "integration", "third-party",
        ],
        recommendation=Recommendation(
            stack=[
                "Django REST Framework + Postgres (mature, batteries-included)",
                "or FastAPI + Postgres (lighter, async-first)",
                "Hosted on Railway, Fly.io, or Render free tier",
                "Auth via a service (Clerk, Auth0) when needed — don't roll your own",
            ],
            why=[
                "Django is the easy path if you'll have an admin UI; FastAPI is the easy path if you won't.",
                "Postgres is boring and battle-tested — you won't outgrow it.",
                "Hosted Postgres + a free-tier app host gets you to production fast.",
            ],
            avoid_yet=[
                "Microservices (one monolith first, always)",
                "Kubernetes",
                "A custom auth system (use Clerk, Auth0, or Django's built-in)",
                "A complex queue / message bus (start with cron + database)",
            ],
            risks=[
                "Free hosting tiers throttle aggressively — verify the limits match your traffic.",
                "Webhook reliability (retries, idempotency) is harder than it looks.",
            ],
            upgrade_when=[
                "Background jobs are queued up -> add Celery (if Django) or Arq (if FastAPI) with Redis.",
                "You hit hosting limits -> move to AWS/GCP only when the bill justifies the complexity.",
                "Multi-tenant SaaS -> now think about auth, billing (Stripe), and data isolation seriously.",
            ],
        ),
    ),

    # --- Modifiers (can never be primary) ---

    Rule(
        name="privacy-sensitive",
        priority=5,
        is_modifier=True,
        note="medical/personal data detected; bias toward local-first, defer accounts",
        signals=[
            "medical", "health data", "private", "privacy",
            "custody", "diary", "journal", "personal data",
            "sensitive",
        ],
        recommendation=Recommendation(
            stack=[],
            why=[],
            avoid_yet=["Cloud backend or accounts until they're truly necessary"],
            risks=[_PRACTICAL_PRIVACY_NOTE],
            upgrade_when=[],
        ),
    ),

    Rule(
        name="simple-mvp",
        priority=3,
        is_modifier=True,
        note="MVP/prototype framing; explicit 'no backend until you need it'",
        signals=[
            "mvp", "prototype", "weekend project",
            "just a", "just want", "simple", "tiny",
        ],
        recommendation=Recommendation(
            stack=[],
            why=[],
            avoid_yet=["Backend, accounts, or any infrastructure not strictly required for v0"],
            risks=[],
            upgrade_when=[],
        ),
    ),
]


FALLBACK_RECOMMENDATION = Recommendation(
    stack=[
        "Python CLI (a single .py file) — for anything that processes data or files",
        "or a static HTML page (one file, opened in a browser) — for anything visual",
    ],
    why=[
        "Without strong signals about phone vs web vs server, the cheapest first step "
        "is whichever single-file thing matches your goal: Python for logic, HTML for presentation.",
        "Both can grow into something bigger, but neither obligates you to a stack you'd regret.",
    ],
    avoid_yet=[
        "Frameworks, build systems, package managers — until the single-file version "
        "actually demands them",
        "Hosting, accounts, databases — until you have something worth hosting",
    ],
    risks=[
        "If your idea has a phone-vs-web-vs-script answer that's obvious to you, "
        "rewrite the idea file with more signal so we can recommend more specifically.",
    ],
    upgrade_when=[
        "When the single-file version stops fitting -> re-run "
        "`context-kit recommend-stack` with more detail in your idea file.",
    ],
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def recommend(idea_text: str) -> RecommendationResult:
    text_lower = idea_text.lower()

    # Find matches
    matches: list[Match] = []
    for rule in RULES:
        hits = [s for s in rule.signals if s.lower() in text_lower]
        if hits:
            matches.append(Match(rule=rule, matched_signals=hits))

    # Pick primary: highest-priority non-modifier
    primary: Optional[Rule] = None
    primary_match: Optional[Match] = None
    for m in sorted(matches, key=lambda x: x.rule.priority, reverse=True):
        if not m.rule.is_modifier:
            primary = m.rule
            primary_match = m
            break

    # Also-detected: everything else, capped
    also_detected = [
        m for m in matches if m is not primary_match
    ]
    also_detected.sort(key=lambda x: x.rule.priority, reverse=True)
    also_detected = also_detected[:ALSO_DETECTED_CAP]

    rec = primary.recommendation if primary else FALLBACK_RECOMMENDATION
    return RecommendationResult(
        primary=primary,
        also_detected=also_detected,
        recommendation=rec,
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


_HUMBLE_FOOTER = (
    "These are opinionated picks for a first-time builder. "
    "If you have a stack you already know, use that — context-kit doesn't care."
)


def _ideatitle_from_text(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and not s.startswith("## "):
            return s[2:].strip()
    return ""


def format_human(idea_text: str, result: RecommendationResult) -> str:
    title = _ideatitle_from_text(idea_text)
    lines: list[str] = []
    head = "context-kit recommend-stack"
    if title:
        head += f' — "{title}"'
    lines.append(head)
    lines.append("")

    if result.primary is not None:
        lines.append(f"Primary signal:  {result.primary.name}")
    else:
        lines.append("Primary signal:  (no specific match — using fallback)")
    if result.also_detected:
        for m in result.also_detected:
            note = m.rule.note or "additional signal"
            lines.append(f"Also detected:   {m.rule.name}  ({note})")
    lines.append("")

    rec = result.recommendation
    sections = [
        ("Recommended v0 stack", rec.stack),
        ("Why this stack fits",  rec.why),
        ("What NOT to add yet",  rec.avoid_yet),
        ("Risks / open questions", rec.risks),
        ("When to upgrade later", rec.upgrade_when),
    ]
    for header, items in sections:
        if not items:
            continue
        lines.append(header)
        for item in items:
            lines.append(f"  - {item}")
        lines.append("")

    lines.append("Next steps")
    lines.append("  context-kit seed idea.md     # bake this into BUILD_PLAN.md")
    lines.append("  context-kit doctor           # verify your env is ready")
    lines.append("")
    lines.append(_HUMBLE_FOOTER)
    return "\n".join(lines)


def format_for_build_plan(result: RecommendationResult) -> str:
    """Return markdown body for the Tech stack section in BUILD_PLAN.md.

    Same content as the human format, but with subheading levels suited
    to living inside an existing `## Tech stack` section.
    """
    lines: list[str] = []
    lines.append("> *Auto-suggested by `context-kit recommend-stack` because the "
                 "idea file had no `## Tech stack` section. Edit `idea.md` and "
                 "re-run `seed` if you'd rather pick your own.*")
    lines.append("")

    if result.primary is not None:
        lines.append(f"**Primary signal:** `{result.primary.name}`")
    else:
        lines.append("**Primary signal:** (no specific match — fallback recommendation)")
    if result.also_detected:
        names = ", ".join(f"`{m.rule.name}`" for m in result.also_detected)
        lines.append(f"**Also detected:** {names}")
    lines.append("")

    rec = result.recommendation
    sections = [
        ("Recommended v0 stack", rec.stack),
        ("Why this stack fits",  rec.why),
        ("What NOT to add yet",  rec.avoid_yet),
        ("Risks / open questions", rec.risks),
        ("When to upgrade later", rec.upgrade_when),
    ]
    for header, items in sections:
        if not items:
            continue
        lines.append(f"#### {header}")
        for item in items:
            lines.append(f"- {item}")
        lines.append("")

    lines.append(f"_{_HUMBLE_FOOTER}_")
    return "\n".join(lines)


def _emit_json(idea_text: str, result: RecommendationResult) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "primary": (
            {"name": result.primary.name, "priority": result.primary.priority}
            if result.primary else None
        ),
        "also_detected": [
            {
                "name": m.rule.name,
                "priority": m.rule.priority,
                "is_modifier": m.rule.is_modifier,
                "note": m.rule.note,
                "matched_signals": m.matched_signals,
            }
            for m in result.also_detected
        ],
        "recommendation": asdict(result.recommendation),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_recommend_stack(args: argparse.Namespace) -> int:
    idea_path = Path(args.idea).resolve()
    if not idea_path.is_file():
        print(f"context-kit: idea file not found: {idea_path}")
        return 2
    idea_text = idea_path.read_text(encoding="utf-8")
    result = recommend(idea_text)
    if args.json:
        _emit_json(idea_text, result)
    else:
        print(format_human(idea_text, result))
    return 0
