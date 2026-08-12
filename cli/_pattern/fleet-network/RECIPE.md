# Fleet Network Recipe

The manual setup that the future `context-kit fleet-net init` subcommand
would automate. Follow these steps once per laptop to stand up a fleet
network, then once per new app to attach.

## Inputs

Before you start, know:

- **Fleet root directory**: where you keep your apps (e.g.
  `~/dev/`)
- **Currently running data containers** you want on the network — for each:
  - Container name (`docker ps --format '{{.Names}}'`)
  - Which app owns it (for the manifest)
  - Internal port (for the documentation)
- **Host-port policy**: which app owns each common port (`:8000`, `:8001`,
  `:5432`, `:5433`, etc.) — codify before things conflict

## One-time per laptop: create the network

```bash
# 1. Create the anchor directory at the fleet root
mkdir -p ~/dev/infra

# 2. Create the external Docker network (idempotent — if it exists, this
#    errors but doesn't break anything)
docker network create fleet-net

# 3. Drop in the anchor compose file (declares fleet-net as external)
cp templates/docker-compose.yml ~/dev/infra/

# 4. Drop in the manifest template and fill it out for your fleet
cp templates/README.md ~/dev/infra/
$EDITOR ~/dev/infra/README.md
```

## One-time per existing container: attach

```bash
# Attach by container name. Idempotent — survives container restarts.
docker network connect fleet-net <container_name>

# Verify it's reachable from a throwaway container on the network
docker run --rm --network fleet-net postgres:15 \
  pg_isready -h <container_name> -p <internal_port>

# Update the manifest with the new container + its hostname:port
```

## Handle the Docker Desktop multi-network host-port bug

After attaching a running container to `fleet-net`, the host-port mapping for
that container sometimes silently breaks on Docker Desktop (macOS). Native
processes that reached `localhost:<port>` start hanging.

If you see `connection refused` or `timeout expired` from host processes
right after an attach:

```bash
docker restart <container_name>
```

That re-establishes the host-port bridge. No data loss; volumes are
unaffected. Document the affected container + the time in your manifest's
"Known caveats" section so the next person doesn't re-discover this from
cold.

## Per new app: declare fleet-net external in its compose

If the app already ships its own `docker-compose.yml`, add:

```yaml
networks:
  fleet-net:
    external: true
    name: fleet-net
```

Then attach each service that needs cross-fleet reachability:

```yaml
services:
  my-service:
    # ... existing config
    networks:
      - fleet-net
      - default  # keep existing internal network too
```

The new service can now reach any other `fleet-net` member by container name
(e.g. `app-a-postgres:5432`).

## Host-port collision policy

Native processes (Django runserver, Vite, uvicorn) can't share host ports.
When two apps want `:8000`, one has to move. Conventions to codify in your
manifest:

- **One app per common port** — anchor the "canonical owner" of each port
  (e.g. `app-a` owns `:8000` because its Procfile + Makefile assume it).
- **Document the swap point** — if you move an app to a non-default port,
  add a line to its README so the move is reversible.
- **Apps inside `fleet-net` containers are unaffected** — different network
  namespaces; multiple containers can bind their internal `:8000` simultaneously
  as long as host-port mappings don't collide.

## Verification

After setup, every fleet member should pass:

```bash
# Network exists
docker network inspect fleet-net >/dev/null && echo "fleet-net exists"

# All expected containers attached
docker network inspect fleet-net \
  --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}'

# DNS resolution works between members
docker run --rm --network fleet-net alpine sh -c \
  "for h in <expected-hostnames>; do nslookup \$h; done"
```

## Refresh cadence

The manifest needs to be re-edited any time:

- A new container is attached → list it in the manifest table
- A host-port assignment changes → update the policy section
- Docker Desktop is upgraded → re-verify the multi-network bug status
- A container is removed → delete it from the manifest

## See also

- `templates/docker-compose.yml` — the anchor file with no services
- `templates/README.md` — manifest template with placeholders to fill in
- `README.md` — the pattern overview and worked example
