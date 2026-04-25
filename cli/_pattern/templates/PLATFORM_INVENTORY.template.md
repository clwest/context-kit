---
title: "<APP> Platform Inventory"
status: generated
generator: core/services/platform_inventory.py
command: python manage.py generate_platform_inventory
---

# <App> Platform Inventory

> **This document is regenerated.** Do not hand-edit. Run
> `python manage.py generate_platform_inventory` to refresh.
> Last regenerated: <timestamp>.

Companion to [`<APP>_WHAT_IT_IS.md`](<APP>_WHAT_IT_IS.md) — narrative /
conceptual doc. This is the runtime-truth complement.

---

## Executive Summary

| Metric | Value | Source |
|---|---|---|
| Agents (total) | N | `<registry>` |
| Models (concrete) | N | `apps.get_models()` |
| Celery tasks | N | `CELERY.tasks` |
| API routes | N | `URLResolver` |
| Services | N | `services/*.py` |
| Workers | N | `Procfile` |
| LOC (core + frontend) | N | `cloc` |

<Summary table is the TL;DR of the inventory. Everything below is detail.>

---

## Table of Contents

1. [Agents](#agents)
2. [Services](#services)
3. [Celery Tasks](#celery-tasks)
4. [Celery Beat Schedule](#celery-beat-schedule)
5. [Personal Assistant Tools](#personal-assistant-tools)
6. [Database Models](#database-models)
7. [URL Routes](#url-routes)
8. [View Files](#view-files)
9. [Management Commands](#management-commands)
10. [Integrations](#integrations)
11. [LLM Providers](#llm-providers)
12. [Infrastructure](#infrastructure)
13. [Code Statistics](#code-statistics)
14. [Doc-vs-Reality Verifier State](#doc-vs-reality-verifier-state)

<Add / remove sections based on your stack. The pattern: one section per
category that has a "count" worth verifying.>

---

## Agents

**Headline:** N agents registered.
**Code location:** `<path>`.

| Name | Module | Status | Category |
|---|---|---|---|

<Auto-populated. Sort alphabetically. Include status so readers can see
which are active vs dormant.>

---

## Services

**Headline:** N service classes.
**Code location:** `<path>`.

| Service | File | Purpose |
|---|---|---|

---

## Celery Tasks

**Headline:** N registered Celery tasks (excluding framework internals).
**Code location:** `<path>`.

| Task | Module | Queue |
|---|---|---|

---

## Celery Beat Schedule

**Headline:** N `PeriodicTask` rows (M enabled, K disabled).
**Source:** `django_celery_beat.PeriodicTask` table.

| Task | Schedule | Enabled | Queue |
|---|---|---|---|

---

## Personal Assistant Tools

**Headline:** N tool schemas, M tool handlers.
**Code location:** `<path>`.

| Tool | Handler | Purpose |
|---|---|---|

---

## Database Models

**Headline:** N concrete models across K apps.

### By app:

| App | Models |
|---|---|

### Model details:

<Optionally: one row per model with key fields. Or cross-link to
docs/current/MODELS.md if you have auto-generated details.>

---

## URL Routes

**Headline:** N routes.

| Path | View | Name |
|---|---|---|

---

## View Files

**Headline:** N view files across K modules.

| File | Endpoints |
|---|---|

---

## Management Commands

**Headline:** N custom commands.

| Command | Module | Purpose |
|---|---|---|

---

## Integrations

**Headline:** N external integrations.

| Integration | Purpose | Auth |
|---|---|---|

---

## LLM Providers

**Headline:** N LLM providers configured.

| Provider | Models used | Purpose |
|---|---|---|

---

## Infrastructure

### Procfile workers

| Process | Command | Purpose |
|---|---|---|

### Redis databases

| DB | Purpose |
|---|---|

### PostgreSQL

- Version: N
- Extensions: <pgvector, etc.>
- Connection pool: N

---

## Code Statistics

| Directory | Files | Lines |
|---|---|---|

---

## Doc-vs-Reality Verifier State

**Headline:** N claims registered, M drifts, K OK.

| Doc | OK | Drift | Error |
|---|---|---|---|

Full drift list: `python manage.py verify_doc_claims --only-drift`.

---

*Generated at <timestamp> by `generate_platform_inventory`. When this
disagrees with any other doc, this wins.*
