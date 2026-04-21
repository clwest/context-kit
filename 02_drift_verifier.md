---
title: "The Drift Verifier Pattern"
status: active
---

# The Drift Verifier Pattern

Docs go stale the moment they're written. The only sustainable answer is a framework that *automatically detects when a claim in a doc disagrees with runtime reality*. In this repo: `python manage.py verify_doc_claims`.

Built in Session 1099 after a single subsystem audit surfaced ~7 distinct drifts. Codified the pattern into a registry so every drift-detection check is a one-line addition.

---

## The Concept

A **claim** is a quantitative or structural assertion in a doc:
- "83 agents in AGENT_MAP"
- "Intelligence Desks run daily at 6 AM"
- "9 Redis DBs configured"
- "Reviewer panel has 2 always-on reviewers"

A **verifier** is a function that:
1. Reads the claim's subject from runtime (code, config, DB, live service)
2. Compares to the doc's stated value
3. Returns a `ClaimResult` with severity

A **registry** holds all verifiers by doc + claim ID.

A **CLI** runs them and reports drifts.

---

## The 4-Part Framework

### 1. The `ClaimResult` dataclass

```python
@dataclass
class ClaimResult:
    doc: str                    # e.g. "docs/CAPABILITIES.md"
    claim_id: str               # stable ID, e.g. "agent_count"
    description: str            # human-readable claim
    expected: Any               # what the doc says
    actual: Any                 # what runtime shows
    severity: str               # ok | low | medium | high | critical | error
    note: str = ""              # why it matters / what to look at
    fix_suggestion: str = ""    # what to change in the doc

    @classmethod
    def build(cls, expected, actual, severity=None, **kwargs):
        # severity auto-computed if missing based on expected vs actual
        ...
```

Severity matters more than pass/fail. A count drifting by 1 is `low`; a scheduled task that doesn't exist is `critical`.

### 2. The `@register_claim` decorator

```python
@register_claim(
    doc="CLAUDE.md",
    claim_id="agent_count",
    description="CLAUDE.md: '83 agents in AGENT_MAP'",
)
def verify_agent_count() -> ClaimResult:
    from core.agent_router import AGENT_MAP
    expected = 83
    actual = len(AGENT_MAP)
    return ClaimResult.build(
        expected=expected,
        actual=actual,
        severity="ok" if expected == actual else "medium",
        fix_suggestion=f"Update CLAUDE.md to '{actual} agents'",
    )
```

One decorator = one verified claim. No framework overhead.

### 3. The runner

```python
def run_all(doc_filter=None, only_drift=False) -> list[ClaimResult]:
    results = []
    for verifier in _REGISTRY:
        try:
            result = verifier()
        except Exception as e:
            result = ClaimResult(
                doc=verifier.doc, claim_id=verifier.claim_id,
                severity="error", note=f"verifier crashed: {e}",
                ...
            )
        results.append(result)
    return results
```

**Critical property:** verifier exceptions are caught and recorded as `severity="error"`, not raised. One bad verifier can't break the run.

### 4. The CLI

```bash
# Full audit
python manage.py verify_doc_claims

# Only show drifts (hide ok)
python manage.py verify_doc_claims --only-drift

# Filter to one doc
python manage.py verify_doc_claims --doc CLAUDE.md

# Machine-readable for CI
python manage.py verify_doc_claims --format json

# CI mode: fail build on any drift
python manage.py verify_doc_claims --fail-on-drift
```

Output has three shapes: grouped-by-doc (default), JSON, and a summary rollup at the bottom (severity counts + per-doc drift counts).

---

## Seeding Claims — How to Start

Don't try to verify every claim in every doc on day one. Seed in rounds:

**Round 1** — Anchor docs (`WHAT_IT_IS.md`, `CLAUDE.md`): pick the 5–10 most-referenced numbers.
**Round 2** — Category stats (agents, services, tasks, models, routes).
**Round 3** — Structural claims (worker count, queue count, reviewer panel size).
**Round 4** — Scheduling claims (does this task actually run daily?).
**Round 5+** — Per-topic docs, drilling down.

At each round, write verifiers that answer the question "if this changes, who cares?" If nobody cares, don't verify it.

---

## What the Verifier Teaches You

Running it the first time is illuminating. On this platform, the initial run found:

- **Contradictions across docs**: PA tool count claimed as 77 / 85+ / 86 / 89 / 231 in different files — actual was 101.
- **Phantom scheduled tasks**: "4 Intelligence Desks run daily at 6 AM" — the Celery task exists but has no `PeriodicTask` row.
- **Whitelist integrity bugs**: a governor whitelist referenced `DiagnosticAgent` which isn't in `AGENT_MAP`.
- **Chronic undercount**: "271 Celery tasks" — actual 365. Nobody updated the doc in 6 months.

The pattern's real output isn't pass/fail — it's a **diff between how the team thinks the system works and how it actually works.**

---

## Directory layout in this repo

```
core/services/
    doc_claim_verification.py         # registry + ClaimResult + decorator + runner

core/management/commands/
    verify_doc_claims.py              # the CLI (argparse + table formatter)

core/services/
    platform_inventory.py             # companion — runtime collector
core/management/commands/
    generate_platform_inventory.py    # regenerates INVENTORY.md
```

Both commands run in <5 seconds. Cheap to run on every CI build, every session start, every commit.

---

## Anti-patterns

- **Hard-coding `expected`** in the verifier while also hand-writing it in the doc. If the number changes in one place it drifts again. Instead: have the verifier read the doc, or make `INVENTORY.md` regeneration fix both at once.
- **Verifiers that touch the network.** Keep them deterministic and fast. Mock or skip live-API checks.
- **"Hide drift" temptation.** When the verifier says 50 drifts, the instinct is to lower the bar. Don't. The list of drifts is the work.

---

## Companion: `INVENTORY.md` section

The final section of `PLATFORM_INVENTORY.md` prints the verifier rollup. When `generate_platform_inventory` runs, it embeds the drift count per doc as a data row. Two commands, one consistent state:

```bash
python manage.py generate_platform_inventory && \
python manage.py verify_doc_claims --only-drift
```

That's the full loop.

---

*See [`templates/verify_doc_claims.skeleton.py`](templates/verify_doc_claims.skeleton.py) for a copy-paste starting framework.*
