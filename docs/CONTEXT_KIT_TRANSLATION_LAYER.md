# context-kit Translation Layer

## Purpose

Core rule: Same truth → different explanation, zero distortion.

This document defines how to explain context-kit to different audiences without changing facts, confidence, or evidence boundaries.

## Source of Truth Inputs

- `docs/CONTEXT_KIT_WHAT_IT_IS.md`
- `docs/CONTEXT_KIT_INVENTORY.md`
- latest `docs/handoffs/SESSION_*.md`
- `context-kit capabilities --format shortlist`

## Personas / Audiences

### Developer
Cares about: CLI commands, source files, tests, implementation boundaries, evidence citations.
Ignores: hype, vague product claims, business fluff.

### CTO
Cares about: architecture, maintainability, integration boundaries, operational reliability, adoption risk.
Ignores: low-level tutorial detail unless it affects risk or cost.

### Operations Manager
Cares about: process clarity, onboarding, handoffs, checklists, what to do next.
Ignores: code paths, framework names, and implementation jargon unless translated.

## Translation Modes

| Mode | Audience | Shape |
|---|---|---|
| Technical bullets | Developer | Commands, files, evidence, boundaries |
| Business-impact paragraph | CTO | What risk or operational problem this reduces |
| Executive bullets | CTO | Strategic value, adoption path, constraints |
| QA checklist | Developer / Operations Manager | What to verify and how |
| What should I do next? | Operations Manager | Clear next actions, no jargon |

## Truth Preservation Rules

- Do not change facts between audiences.
- Do not upgrade confidence.
- Do not invent benefits, metrics, or outcomes.
- If a translation cannot be made without inventing or implying unsupported facts, fall back to a neutral summary.
- Label speculation explicitly.
- Preserve implementation evidence when claims depend on code.

## Live Chat Mode

### Universal rules

- Source-of-truth still wins.
- Refuse or fall back to neutral when a clean answer would require unsupported facts.
- No invented analogies.
- Stay in the requested audience mode until changed.

### Per-persona contracts

#### Operations Manager

Trigger phrases:
- "Hi, I'm Operations"
- "Explain this for ops"

Avoid / use instead:

| Avoid | Use instead |
|---|---|
| endpoint | command or system action |
| repo | project folder |
| commit | saved change |
| CLI | command tool |
| implementation | what is built |

Grounding rule:
Explain only what the source supports. If a code detail matters, translate it into process impact.

## Example: Same Truth, Different Explanation

Source fact: `context-kit capabilities --format shortlist` detects the `orient` command with high confidence from `cli/orient.py` and `context_kit.py`.

### Developer
`orient` is a high-confidence CLI capability. Evidence shows `run_orient` in `cli/orient.py` and dispatcher wiring in `context_kit.py`.

### CTO
context-kit has a verified orientation command that helps standardize how project context is loaded before work begins. This supports consistency, but measured productivity impact is not documented here.

### Operations Manager
context-kit has a command that helps people start with the same project understanding before they work. It reduces confusion risk, but this document does not prove a measured time savings.

## What Each Person Needs Next

- Developer: verify command behavior against tests before changing implementation.
- CTO: review whether context-kit should be positioned as project onboarding, drift prevention, or local AI grounding.
- Operations Manager: use `context-kit orient` before starting a new work session.

## Last Verified

2026-05-05 — GPT-5.5 Thinking — Session 014