# Fleet Infrastructure — `<FLEET_NAME>`

Local-only networking convention for the laptop app fleet (`<list-the-apps>`).
Lets apps reach each other's data services — and eventually each other — by
stable hostname without depending on host-port juggling.

## What exists

A single Docker network named **`fleet-net`** owned by the host. Containers
attached to it can resolve each other by container name as a DNS hostname.

```bash
docker network inspect fleet-net
```

Currently attached (as of `<DATE>`):

| Container | App | Service | Inside the network |
|---|---|---|---|
| `<CONTAINER_1>` | `<APP_1>` | `<SERVICE_TYPE>` | `<CONTAINER_1>:<INTERNAL_PORT>` |
| `<CONTAINER_2>` | `<APP_1>` | `<SERVICE_TYPE>` | `<CONTAINER_2>:<INTERNAL_PORT>` |
| `<CONTAINER_3>` | `<APP_2>` | `<SERVICE_TYPE>` | `<CONTAINER_3>:<INTERNAL_PORT>` |

Verify cross-app resolution:

```bash
docker exec <CONTAINER_1> getent hosts <CONTAINER_3>
# 172.X.0.Y  <CONTAINER_3>
```

## Why this exists

Three problems it solves up front:

1. **Future fleet apps can reach existing data services by name.** A new
   app's container that joins `fleet-net` can connect to e.g.
   `<CONTAINER_1>:<INTERNAL_PORT>` without knowing the host's IP or port
   mapping.
2. **Cross-app HTTP bridges have a stable target.** When an app needs to
   call another (e.g. a tool in one app POSTs to another's API), the target
   becomes `http://<container-name>:<port>` instead of a host-port that
   could change.
3. **A fleet-wide overview exists.** `docker network inspect fleet-net`
   answers "what's reachable from inside the fleet?"

## How a new app joins

### Option A: Existing container

```bash
docker network connect fleet-net <your_container_name>
```

Idempotent. Survives container restarts. Detach with `docker network
disconnect fleet-net <name>`.

### Option B: New compose project

In the app's `docker-compose.yml`:

```yaml
services:
  my-service:
    # ... your config
    networks:
      - fleet-net
      - default  # optional, if you also want internal-only connectivity

networks:
  fleet-net:
    external: true
    name: fleet-net
```

The `external: true` tells compose not to create the network — it expects
`fleet-net` to already exist on the host.

## Host-port collision policy

`fleet-net` solves cross-container reachability. It does **not** solve
host-port collisions between native (non-containerised) processes (Django
runserver, Vite dev server, uvicorn).

When two apps want the same host port:

- Containerised apps inside `fleet-net` are unaffected — different network
  namespaces.
- Native dev processes have to negotiate. Convention so far:
  - **`<APP_1>` Django**: `:<PORT>` (anchor — Procfile / Makefile assumes
    this)
  - **`<APP_2>` Django**: `:<PORT>` by default. Move to `:<ALT_PORT>` when
    concurrent uptime with `<APP_1>` is needed.
  - **`<APP_N>` …**: `:<PORT>`
  - **Vite dev servers**: `:<PORT>` (legacy), `:<PORT>` (next app), etc.
  - **Redis instances**: `:6379` (default), `:6380` (second), etc.
  - **Postgres instances**: `:5432` (default), `:5433` (second), etc.

When you move a port for concurrent-uptime work, document the swap point in
the moved app's README so the swap is reversible.

## What this is NOT

- **Not a docker-compose for the entire fleet.** Each app keeps its own
  compose file in its own repo. This file declares only the shared network.
- **Not a service mesh.** No traffic policy, no automatic TLS, no service
  discovery beyond Docker's built-in DNS.
- **Not a deployment artifact.** Production is per-app and out of scope
  here. This is local-dev plumbing.
- **Not a port reservation system.** The host-port policy above is
  convention, not enforced.

## When to grow this

This file becomes a real `docker-compose.yml` (instead of a network anchor)
when:

- A third app needs containerised data services and we want one `up -d` to
  bring everything online.
- We start standing up shared infrastructure (reverse proxy, tracing
  collector, etc.) that lives at the fleet level rather than per-app.
- A bridge service (e.g. an HTTP proxy for cross-app calls) needs a stable
  home.

Until any of those land, this file's job is just to declare `fleet-net`
and document the convention.

## Known caveats

### Docker Desktop multi-network host-port bug

When you attach a running container to a second Docker network (e.g.
`docker network connect fleet-net <name>`), Docker Desktop on macOS
sometimes silently breaks the container's existing host-port mapping. The
container still listens on its internal port; cross-network DNS keeps
working; but `psql -h localhost -p <mapped-port>` or any host process trying
to reach the mapped port times out.

**Symptom**: native processes (Django runserver, psql, etc.) that
previously connected to `localhost:<mapped-port>` start hanging or timing
out with `connection refused` / `timeout expired` after the network
attach. Other containers on the new network can still reach the service
by name.

**Fix**: restart the container. `docker restart <name>` re-establishes the
host-port bridge. No data loss; volumes are unaffected.

**Prevention**: if you're attaching a container that other native processes
depend on, consider a maintenance window — or stop the native processes
first, attach, restart the container, then bring native processes back up.

This is a Docker Desktop quirk, not a bug in this network configuration.
Reported on Docker Desktop's GitHub repeatedly; status varies by Docker
Desktop version.

## History

- **`<DATE>`** — Network created. `<N>` data containers attached. Manifest
  written. Motivation: `<one-line-why>`.
