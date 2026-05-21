---
title: "Proposal — `context-kit spokesperson` subcommand"
status: proposed
created: 2026-05-21
implemented: false
related:
  - cli/_pattern/spokesperson-corpus/
---

# Proposal — `context-kit spokesperson` subcommand

Lift the bundled `cli/_pattern/spokesperson-corpus/` sub-pattern into a first-class CLI
subcommand so context-kit adopters can scaffold, refresh, and verify a public-voice
corpus the same way they scaffold the rest of the pattern.

## Status

**Proposed, not implemented.** The pattern itself ships in `cli/_pattern/spokesperson-corpus/`
as of this PR. Adopters can `cp -r` it manually today. This proposal maps what the
CLI surface would look like once the shape proves out across a second or third real
instance.

## Why

`translation-init` is the closest precedent in the existing CLI: a read-only subcommand
that prints a structured prompt instructing an AI to populate a layer doc. Spokesperson
corpus generation is the same shape, just bigger:

- Inputs: project's `WHAT_IT_IS`, `INVENTORY`, `BEHAVIOR_LAYER` (if present), latest
  handoff, public taxonomy source
- Output: a directory of small markdown chunks, one per concept the spokesperson needs
  to know about, each with structured facts + voice prose + off-limits
- Refresh: should re-run when source-of-truth shifts and when the downstream
  spokesperson system (Character OS, chat widget) needs new embeddings

Without a CLI, every adopter copies the pattern manually, fills in templates by hand,
and has no built-in way to verify the corpus stays sanitized as the project ships new
work. With a CLI, the pattern becomes operationally indistinguishable from the rest
of context-kit.

## Proposed surface

Three subcommands under `spokesperson`:

### `context-kit spokesperson init`

**Behavior:** read-only prompt printer (matches `translation-init`).

```
context-kit spokesperson init [--project PATH] [--audience TIER] [--target DIR]
```

- `--project PATH` — project root (default: cwd)
- `--audience TIER` — `public-everyone` (default) | `public-builders` | `operator-only`
- `--target DIR` — corpus target directory (default: `docs/spokesperson/`)

Prints a structured prompt to stdout that instructs the AI to:

1. Read the project's source-of-truth chain (`PLATFORM_WHAT_IT_IS`, `PLATFORM_INVENTORY`,
   `BEHAVIOR_LAYER`, latest handoff)
2. Read any public-taxonomy source the user nominates (a `products.ts`, marketing CMS
   export, public website map)
3. Read `cli/_pattern/spokesperson-corpus/RECIPE.md` and `VOICE_GUIDE.md`
4. Scaffold the target directory with `README.md`, `00_overview.md`, `01_voice.md`,
   `90_facts.md`, and one chunk per public entity in the taxonomy
5. Apply the sanitization checklist from the recipe to every chunk
6. Stop and ask the user to vet voice before scaling out the remaining chunks

Read-only by contract: never modifies files, never invokes an AI, never overwrites a
hand-edited spokesperson corpus.

### `context-kit spokesperson refresh`

**Behavior:** read-only prompt printer.

```
context-kit spokesperson refresh [--project PATH] [--target DIR]
```

Prints a prompt instructing the AI to:

1. Read the current corpus (every file under `--target`)
2. Read the source-of-truth chain
3. For each chunk, verify cited numbers against the current `PLATFORM_INVENTORY` and
   public taxonomy
4. Update `90_facts.md` source dates where re-verified
5. Flag chunks whose facts have drifted (and update them or flag for human review)
6. Add new chunks for any new public entities in the taxonomy that don't yet have one
7. Touch nothing outside the corpus directory

Re-run after every meaningful platform change.

### `context-kit spokesperson doctor`

**Behavior:** validation only — no prompt, no AI, no mutation.

```
context-kit spokesperson doctor [--project PATH] [--target DIR] [--strict]
```

Checks every chunk under `--target` against the contract:

| Check | Severity |
|---|---|
| Frontmatter present and complete | error |
| `section` field is one of the known section types | error |
| `audience` field is one of the three known tiers | error |
| `sources` field is non-empty | error |
| `updated` field is within 90 days | warn |
| `Off-limits` section exists and is non-empty | error |
| No banned vocabulary from default deny list | error |
| No banned vocabulary from project's `01_voice.md` extensions | error |
| Every number cited in chunk prose also appears in `90_facts.md` | error in `--strict`, warn otherwise |
| Chunk word count within 200-1200 range | warn |
| Internal codenames not used (configurable per project in `01_voice.md`) | error |

Exit codes match the rest of context-kit (0 = clean, 1 = warnings, 2 = errors).

## Integration with existing commands

### `context-kit init`

The pattern bundle already ships `cli/_pattern/spokesperson-corpus/`. `init --force`
keeps it fresh. No change needed.

### `context-kit doctor`

Add a new check to the project-level doctor that detects the presence of `docs/spokesperson/`
and runs `spokesperson doctor` against it. Skipped if the corpus directory doesn't exist.

### `context-kit orient`

Add `docs/spokesperson/README.md` to the list of optional anchor docs orient surfaces.

## Implementation outline

Roughly mirrors `cli/translation_init.py`:

```python
# cli/spokesperson.py
def run_init(args): ...
def run_refresh(args): ...
def run_doctor(args): ...

# context_kit.py — register subparser
sp = sub.add_parser("spokesperson", help="Manage a spokesperson corpus")
sp_sub = sp.add_subparsers(dest="spokesperson_command", required=True)
sp_init = sp_sub.add_parser("init", help="Print scaffold prompt")
sp_refresh = sp_sub.add_parser("refresh", help="Print refresh prompt")
sp_doctor = sp_sub.add_parser("doctor", help="Validate corpus")
# ... argument wiring
```

Tests at `tests/test_spokesperson.py` matching the shape of `tests/test_behavior.py` and
`tests/test_doctor.py`.

## Estimated effort

- `cli/spokesperson.py` + the three subcommands: ~1 day
- Doctor checks (frontmatter, banned vocab, facts-table cross-reference): ~1 day
- Tests: ~half day
- Integration with `context-kit doctor` and `orient`: ~half day
- Documentation in `docs-pattern/README.md` + a `09_spokesperson_corpus.md` guide doc
  matching the existing 08-doc structure: ~half day

Total ~3-4 days of focused work. Wait until the pattern proves out on a second instance
before committing the CLI API surface.

## Validation gate

Don't ship this subcommand until at least two real projects (different shapes — e.g. a
solo OSS tool and a multi-product studio) have generated corpora using the pattern
manually. The CLI surface should be informed by what the manual workflow felt friction
in, not designed in the abstract.

## Open questions

- Should `init` and `refresh` write files directly (matching `init --force`) or stay
  read-only prompt printers (matching `translation-init`)? The translation-init pattern
  is safer; the init-pattern is faster. Lean toward read-only first.
- Should `doctor` parse banned-vocab extensions from `01_voice.md` automatically, or
  require a separate config file? Auto-parse from frontmatter is cleaner if voice
  anchor adopts a standard frontmatter schema.
- Does the corpus need its own `INDEX.md` (autogenerated, like the project-level
  `docs/INDEX.md`)? Probably yes — same drift problem.
- Should the CLI know about downstream embedders (Character OS, LangChain, custom)?
  Initial answer: no. The corpus is a markdown directory; ingestion is the embedder's job.
