---
title: "context-kit — Runtime Flow Map"
status: active
generated: 2026-11-16
last_revised: 2026-11-16 (SESSION 23)
---

# context-kit — Runtime Flow Map

Companion to the [narrative anchor](CONTEXT_KIT_WHAT_IT_IS.md),
[runtime inventory](CONTEXT_KIT_INVENTORY.md), and
[behavior contract](CONTEXT_KIT_BEHAVIOR_LAYER.md). Runtime implementation
wins over these descriptions. This map covers terminal/report flows;
there is no graphical UI in these flows. The separate `start` onboarding
server is described in the [CLI reference](../README.md).

## Execution paths and authority

[context_kit.py](../context_kit.py) parses arguments, dispatches most
commands through lazy module imports, and dispatches `handoff write`
through its own action handler. Deterministic commands own collection,
selection, file writes, and report formatting. Model text is an answer
based on supplied context, not an authoritative verification result.

| Entry point | Collection / guards | Output and side effects | Model boundary |
|---|---|---|---|
| `orient` | Recognizes start guide or docs-pattern directory; discovers anchors and highest numbered handoff | Ordered plain-text previews, priorities, runtime/doctor drift summary; `--short` reduces detail | No model call |
| `inspect` | Validates directory/scope; collects files and applies scope/history filters; filename, manifest and regex probes plus git metadata | Markdown to stdout; `--output` also writes Markdown; `--json` prints structured data instead | No model call |
| `doctor` | Environment/version probes, anchor presence, inventory freshness and continuity checks | Text or JSON diagnostics; exit 1 for blocking findings, 0 for advisory warnings only, 2 for invalid project | No model call; may run diagnostic subprocesses |
| `inventory` | Parser introspection, filesystem counts, test-definition parsing, git/file metadata | `--json` prints; `--write` replaces managed inventory block; `--check` compares with timestamps normalized (0 current, 1 stale) | No model call; discovered tests are not executed |
| `handoff write N` | Requires an existing numbered handoff; uses explicit date, handoff date, or UTC date | Re-stamps eligible anchor frontmatter; read-only calibration-promotion audit; does not author the handoff or trust log | No model call; advisory calibration warnings do not fail it |
| `start-codex` | Builds startup prompt from project state | Prints prompt; can create missing `.context-kit/verify.yaml` | Prompt generation only |
| `codex` | Builds same prompt; checks external Codex availability | Can create missing `.context-kit/verify.yaml` while preparing the prompt; clipboard/fallback handling; launches interactive Codex or `codex exec` | External process owns subsequent agent/model activity |
| `chat` | Validates project; assembles orientation, persona and evidence; routes each user question | Sends messages to Ollama; prints response; in-memory history in interactive mode | Actual HTTP model call |

Sources: [orient.py](../cli/orient.py), [inspect.py](../cli/inspect.py),
[doctor.py](../cli/doctor.py), [inventory.py](../cli/inventory.py),
[handoff.py](../cli/handoff.py), [start_codex.py](../cli/start_codex.py).
The `audit` prompt surface is also distinct from running a model: see
[audit.py](../cli/audit.py) and the CLI reference. Bundled pattern templates
are scaffold/reference files, not running queues or agents.

## Chat request path

1. [chat.py](../cli/chat.py) resolves the project and builds compact
   `render_chat_orient` context: source order, narrative preview,
   non-low-signal inventory preview, latest handoff, and active next-task
   summary. This differs from full `orient` and is not a full repository dump.
2. Normal mode adds `CHAT_BEHAVIOR_PREAMBLE`, project identity and optional
   persona lines. Explicit `--include-inspect`, `--include-capabilities`,
   `--include-doctor`, `--include-hotpath`, and `--include-behavior` collect
   reports at bundle construction. Inspect is also in the base system message
   when explicitly included.
3. Per-turn keyword routing selects capabilities, inspection, diagnostics,
   hotpath, or behavior evidence. Missing reports are generated lazily and
   cached. Explicit sections are included regardless of auto routing;
   `--no-auto-context` disables automatic selection. Live-state questions
   select no automatic report. Omitted sections prove nothing about the repo.
4. The request contains system context, retained conversation, any selected
   turn-only evidence block, and the current task wrapper (unless disabled).
   Interactive normal mode adds a synthetic identity priming exchange unless
   `--no-prime`; one-shot mode starts with the system message only.
5. [ollama.py](../cli/ollama.py) POSTs JSON to `/api/chat` with `stream: false`.
   Model resolution is `--model`, then `OLLAMA_MODEL`, then `llama3`.
   `OLLAMA_BASE_URL` defaults to `http://localhost:11434`; environment defaults
   are read at import. The client supports a base URL argument, but chat uses
   the configured environment/default endpoint. This can be remote: injected
   project context and conversation leave the process for that endpoint.
   Local-only handling is not guaranteed.
6. The client checks HTTP/JSON/message-content shape and returns text.
   Chat prints `response.rstrip()`; it performs no factual, citation,
   capability-format or security scrub. `OllamaError` yields exit 2.

Planner mode is a separate prompt path: project path plus a one-command
planning contract, no orientation/persona/evidence bundle, auto routing or
priming. It still calls Ollama and cannot execute its proposed command.

## State, matching and drift surfaces

| Surface | Lifetime / owner | Boundary |
|---|---|---|
| Anchors, start guide, numbered handoffs | Files across sessions | Humans/agents author continuity; generated inventory block is replaced by its generator |
| Base orientation and persona | Chat process | Not refreshed by `/reset` |
| Optional reports | Generated explicitly at startup or lazily on first selection; cached in bundle | Not a live monitor; later turns reuse cached text |
| Conversation | Interactive process memory | Normal mode retains wrapped user tasks and assistant responses; planner retains user tasks only |
| Turn evidence block | One request | Not appended to retained history |

`/reset` retains the base system message and restores optional priming,
clearing conversation history; it does not rebuild cached evidence.
`/orient` renders a fresh short orientation for display only, without
replacing model context. Exit/EOF ends the process; there is no chat-history
persistence implemented here. Persona matching uses the first translation-doc
line containing the requested string, case-insensitively; it is not a profile
lookup. See the [translation layer](CONTEXT_KIT_TRANSLATION_LAYER.md).

Prompt instructions describe evidence as startup snapshots, while lazy
collection can occur on a later turn. Neither mechanism supplies ongoing
live state. Other drift surfaces are regex detector limitations, partial
previews, cached reports, changed endpoint configuration, and unenforced
model instructions. Inspect's findings are static signals, not an LLM audit,
security validation, or proof of implementation correctness.

## Last verified

2026-11-16, Session 022: source inspection and deterministic CLI checks
recorded in the [handoff](handoffs/SESSION_022_CONTEXT_KIT_FLOW_CONTRACTS.md).
No model request, external Codex launch, or unit test suite was run.
