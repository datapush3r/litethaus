# litethaus

A stateless, database-free, all-in-one homelab dashboard, docker-compose manager, and automated reverse proxy.

litethaus scans a directory of docker-compose stacks, gives you a dashboard to start/stop them and watch their logs in real time, and automatically wires up [Caddy](https://caddyserver.com/) as a reverse proxy for whichever ones you expose — no labels in your compose files, no database, no separate proxy config to maintain by hand.

## Features

- **Stack discovery** — scans a directory for one subfolder per stack, each with its own `compose.yaml` (or `compose.yml` / `docker-compose.yaml` / `docker-compose.yml`)
- **Start/stop/logs** — control stacks and stream their logs live from the browser
- **Stack authoring** — create, edit, and delete stacks from the UI via a raw compose YAML editor
- **Automatic reverse proxy** — add an `x-litethaus:` block to a stack's compose file with a domain and port, and litethaus wires it into Caddy automatically
- **Automatic HTTPS** — self-signed certs via Caddy's local CA (for `.home.arpa`/`.local` domains) or real ACME/Let's Encrypt certs for publicly resolvable domains
- **Health monitoring** — per-container health and restart-loop status in the dashboard, with an optional webhook alert
- **Single-user login** — a simple password gate for the dashboard itself
- **Light/dark/system theme**, responsive layout

## How it works

- The host file system is the source of truth — there's no database. Litethaus just reads and writes the compose files already in your stacks directory.
- Per-stack metadata (domain, port, icon) lives in each stack's own compose file, in a root-level `x-litethaus:` extension field — invisible to `docker compose` itself, but read by litethaus.
- Global settings (which directory to scan, HTTPS mode, theme, etc.) live in a single `config.yaml`, edited either directly or through the Settings page.
- The reverse proxy is a bundled Caddy instance, configured entirely through Caddy's native admin API — litethaus never touches your services' compose files to add proxy labels.

## Getting started

Requires Docker and Docker Compose.

```bash
git clone <this repo>
cd litethaus
docker compose -f docker-compose.dev.yaml up --build
```

Then open `http://localhost:5173`. On first run you'll be asked to set up an admin username and password. Once you're in, go to **Settings** and point `Stacks directory` at wherever your own compose stacks live (a bind mount, in the containerized setup above).

## Configuration

Global settings live in `config.yaml`, generated automatically with defaults on first run (also editable from the Settings page). It holds instance-specific state including the admin password hash, so it's gitignored rather than tracked — there's nothing to seed or copy manually:

| Key | Description |
|---|---|
| `stacks_dir` | Directory containing one subfolder per stack |
| `caddy_admin_url` | Base URL for Caddy's admin API |
| `https_mode` | `off`, `internal` (self-signed), or `acme` (Let's Encrypt) |
| `acme_email` | Registration email, required when `https_mode` is `acme` |
| `theme` | `light`, `dark`, or `system` |
| `webhook_url` | Optional webhook POSTed to when a stack becomes unhealthy or restart-loops |

Per-stack settings live in each stack's compose file under `x-litethaus:`:

```yaml
x-litethaus:
  domain: myapp.home.arpa
  port: 8080
  service: web      # optional: which service to proxy to, if there's more than one
  icon: mdi:server  # optional
```

## Development

- **Backend:** `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && uvicorn main:app --reload`
- **Frontend:** `cd frontend && npm install && npm run dev`
- **Full stack:** `docker compose -f docker-compose.dev.yaml up --build`
