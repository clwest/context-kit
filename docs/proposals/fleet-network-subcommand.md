---
title: "Proposal — `context-kit fleet-net` subcommand"
status: proposed
created: 2026-05-21
implemented: false
related:
  - cli/_pattern/fleet-network/
  - docs/proposals/spokesperson-corpus-subcommand.md
---

# Proposal — `context-kit fleet-net` subcommand

Lift the bundled `cli/_pattern/fleet-network/` sub-pattern into a first-class CLI
subcommand so context-kit adopters can scaffold and attach to a laptop-local fleet
network the same way they scaffold the rest of the pattern.

## Status

**Proposed, not implemented.** The pattern itself ships in
`cli/_pattern/fleet-network/` as of SESSION_019. Adopters can `cp -r` it manually
today. This proposal maps what the CLI surface would look like once the shape
proves out across a second or third real instance.

## Why

The pattern's two manual touch points — *creating* the fleet anchor on a new
laptop and *attaching* an existing container to it — are simple shell sequences
today, but they have load-bearing convention attached:

- The host-port policy lives in the manifest README. Forget to update it after a
  new attach, and the next person re-discovers the collision the hard way.
- The Docker Desktop multi-network caveat (host-port bridge silently breaking on
  the second `network connect`) is a `docker restart` away from invisible, but
  only if you remember it's a thing. The first time it happens cold it eats an
  hour.
- The verification step (`docker network inspect`, cross-container `nslookup`)
  is something you only run when something feels wrong — meaning new attaches
  usually skip it.

A subcommand can:

- Make the anchor creation idempotent and aware of "already exists" cases.
- Update the manifest table automatically on attach (no manual edit step to
  forget).
- Run the verification on every attach as a default — catch the multi-network
  bug at attach time, not at first cross-app call.
- Codify the host-port policy as a structured config file the CLI can read
  back, not free-form prose the AI rewrites.

`translation-init` and the proposed `spokesperson` subcommand are the closest
precedents — read-only or scoped-write surfaces that automate manual setup
sequences the user otherwise re-discovers from prose. Fleet-net is the same
shape with a different verb set (`init`, `attach`, `verify`, `doctor`).

## Proposed surface

Four subcommands under `fleet-net`:

### `context-kit fleet-net init`

**Behavior:** scoped write — creates the anchor directory and templates,
nothing more.

```
context-kit fleet-net init [<fleet-name>] [--root PATH] [--network-name NAME] [--force]
```

- `<fleet-name>` — display name baked into the manifest README (default:
  basename of `--root`).
- `--root PATH` — fleet root directory (default: `$HOME/development`).
- `--network-name NAME` — the external Docker network name (default:
  `fleet-net`).
- `--force` — overwrite existing files at the target.

Creates:

- `<root>/infra/docker-compose.yml` — the network anchor (no services).
- `<root>/infra/README.md` — the manifest with the host-port convention
  pre-filled with `<fleet-name>` substituted in.

Runs `docker network create <network-name>` (idempotent — swallows
"already exists" errors). Prints a `Next steps` block telling the operator
which currently-running containers it detected and what to attach.

### `context-kit fleet-net attach`

**Behavior:** scoped write — attaches a running container to the fleet network
and updates the manifest.

```
context-kit fleet-net attach <container-name> [--app NAME] [--service SERVICE_TYPE] [--port N] [--root PATH] [--verify/--no-verify]
```

- `<container-name>` — the running Docker container to attach.
- `--app NAME` — which app owns this container (for the manifest table).
- `--service SERVICE_TYPE` — `postgres` / `redis` / `mysql` / arbitrary string.
- `--port N` — the container's internal port (for the manifest's "inside the
  network" hostname:port column).
- `--verify` (default) — run the cross-network DNS + reachability check after
  attaching. If the verify step uncovers the Docker Desktop multi-network
  host-port bug (host port hangs), automatically run `docker restart
  <container-name>` and re-verify.

Side effects:

1. `docker network connect <fleet-net> <container-name>`.
2. Append a row to `<root>/infra/README.md`'s container table.
3. Verify cross-network resolution from a throwaway alpine container.
4. If host port stops responding to `nc -z localhost <port>` after attach,
   restart the container automatically and log it in the manifest's
   "Known caveats" section.

### `context-kit fleet-net verify`

**Behavior:** read-only validation.

```
context-kit fleet-net verify [--root PATH] [--strict]
```

Runs against the current fleet:

| Check | Severity |
|---|---|
| Network exists (`docker network inspect`) | error |
| Every container in the manifest table is currently attached | error |
| Every attached container appears in the manifest table | warn |
| Cross-container DNS resolves for every (container, container) pair | error |
| Host-port mapping responds for every container with an exposed port | error |
| Docker Desktop multi-network bug not currently active | warn |

Exit codes match the rest of context-kit (0 = clean, 1 = warnings, 2 = errors).

### `context-kit fleet-net doctor`

**Behavior:** read-only — sub-set of `verify` that runs as part of the regular
`context-kit doctor` check chain.

The standalone `context-kit doctor` should detect the presence of
`<HOME>/development/infra/` (or whatever `--root` was used) and run
`fleet-net doctor` against it. Skipped if the anchor directory doesn't exist.

## Integration with existing commands

### `context-kit init`

The pattern bundle already ships `cli/_pattern/fleet-network/`. `init --force`
keeps it fresh. No change needed.

### `context-kit doctor`

Add a new check that detects an `infra/` anchor directory at common locations
(`<HOME>/development/`, `<HOME>/`, configurable) and runs `fleet-net doctor`
against it. Skipped if the directory doesn't exist.

### `context-kit orient`

Add `infra/README.md` (or the fleet manifest path) to the list of optional
infra anchors orient surfaces, when the current project is part of a fleet.
Detection: project's `docker-compose.yml` references the fleet network as
`external: true`.

## Implementation outline

Roughly mirrors `cli/translation_init.py` + `cli/inventory.py`:

```python
# cli/fleet_network.py
def run_init(args): ...
def run_attach(args): ...
def run_verify(args): ...
def run_doctor(args): ...

# Helpers
def _docker_network_exists(name): ...
def _container_running(name): ...
def _attach_container(container, network): ...
def _verify_dns(container_a, container_b): ...
def _verify_host_port(container, port): ...
def _restart_container(name): ...

# context_kit.py — register subparser
fn = sub.add_parser("fleet-net", help="Manage a laptop-local app fleet network")
fn_sub = fn.add_subparsers(dest="fleet_net_command", required=True)
fn_init = fn_sub.add_parser("init", help="Create the fleet anchor")
fn_attach = fn_sub.add_parser("attach", help="Attach a container to the fleet")
fn_verify = fn_sub.add_parser("verify", help="Validate the fleet")
fn_doctor = fn_sub.add_parser("doctor", help="Lighter-weight verify for the doctor chain")
# ... argument wiring
```

Tests at `tests/test_fleet_network.py` matching the shape of
`tests/test_behavior.py` and `tests/test_doctor.py`. The Docker dependency
makes some tests environment-conditional; use the same pattern other
docker-aware tests use (skip when no docker socket).

## Estimated effort

- `cli/fleet_network.py` + the four subcommands: ~2 days (more than
  spokesperson because of the Docker side effects).
- Doctor / verify checks (DNS resolution, host-port bridge detection,
  multi-network bug auto-recovery): ~1 day.
- Tests: ~1 day (Docker-aware tests are slower to write than pure-file ones).
- Integration with `context-kit doctor` and `orient`: ~half day.
- Documentation in `docs-pattern/README.md` and a `10_fleet_network.md` guide
  doc (if guide docs grow beyond eight): ~half day.

Total ~4-5 days of focused work. Wait until the pattern proves out on a
second instance before committing the CLI API surface.

## Validation gate

Don't ship this subcommand until at least one additional laptop fleet (a
different operator, a different OS, or a different stack mix) has used the
pattern manually. The Docker Desktop caveat is the most likely place real
shape will diverge from what the worked instance in
`/Users/donkeyking/development/infra/` taught us.

## Open questions

- **Where does `--root` default?** `$HOME/development` matches this operator's
  layout but is not universal. Should the default be `cwd` (matching most
  other context-kit subcommands), `$HOME`, or a discovered path (search
  upward for an existing `infra/` directory)?
- **Should `attach` ever auto-restart?** The Docker Desktop multi-network
  caveat is silent breakage; auto-restart on detection is operationally
  correct but surprises operators expecting "this command is purely additive."
  Lean toward auto-restart-with-warning rather than fail-and-instruct.
- **Should the manifest table be machine-readable?** Currently the manifest
  is prose markdown with a table. A YAML sidecar (`infra/fleet.yaml` ->
  list of `{container, app, service, port}`) would let the CLI read back its
  own state instead of parsing markdown. Probably worth it once `verify`
  exists — markdown-parsing-as-state is a known drift surface.
- **Does the pattern need a sibling for production?** This is local-dev only
  by design. If adopters routinely want a similar "shared network on
  Railway/Fly/Kubernetes" surface, that's a separate sub-pattern (different
  primitives, different caveats), not a flag on this one.
- **Should `init` detect the existing `cli/_pattern/fleet-network/`
  templates and copy them verbatim, or should it embed the templates in the
  Python source?** Copy-verbatim keeps the bundle as the source of truth;
  embed is simpler to ship. Follow whatever spokesperson lands on.
