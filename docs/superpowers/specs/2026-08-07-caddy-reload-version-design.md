# Caddy Overview: Reload + Version Display

## Purpose

The Caddy page's Overview tab shows sync status (enabled/last-sync-ok/timestamp) but offers no
way to force a resync without waiting for an unrelated stack/config change, and no visibility
into which Caddy binary is actually running. This adds both, scoped to a single Overview-tab
card — first of five previously-scoped Caddy UI features (see prior brainstorm), the rest
(per-route IP/CIDR access control, Prometheus metrics toggle, on-demand TLS toggle,
redirects/rewrites tab) are separate specs, done later.

## Scope

- A "Reload" action that re-pushes the generated config to Caddy's admin API on demand.
- A read-only Caddy version string shown on the same card.
- Explicitly **not** in scope: a full container restart (drops active connections; only needed
  if Caddy is hung and unresponsive to `/load`, a different and heavier failure mode than "I
  fixed the problem and don't want to wait for the next stack edit to resync").

## Backend

### `CaddyService.version()` (`caddy_service.py`)

```python
def version(self) -> str | None:
    container = docker_service.find_caddy_container()
    if container is None:
        return None
    exit_code, output = docker_service.exec_run(container.name, ["caddy", "version"])
    if exit_code != 0:
        logger.warning("caddy version inside %s exited %s: %r", container.name, exit_code, output[:200])
        return None
    return output.decode(errors="replace").strip()
```

Same shape as `CertService.list_certificates()` (`cert_service.py`): resolve the Caddy
container via `docker_service.find_caddy_container()`, run a one-off `exec_run`, degrade to a
harmless empty/`None` value on any failure rather than raising. `caddy_service.py` is the right
home (Caddy-process-specific, not cert-specific); it doesn't import `docker_service` yet
(currently only `config_service` and `stacks_service.Stack`) so this adds
`from docker_service import docker_service` - no circular import, `docker_service.py` doesn't
import `caddy_service`.

### Routes (`main.py`)

```python
@app.get("/caddy/version")
def caddy_version() -> dict[str, Any]:
    return {"version": caddy_service.version()}


@app.post("/caddy/reload")
def caddy_reload() -> dict[str, Any]:
    caddy_service.sync(stack_service.list_stacks())
    return caddy_service.status()
```

`POST /caddy/reload` does exactly what every other mutating endpoint in `main.py` already
triggers as a side effect (`caddy_service.sync(stack_service.list_stacks())`) — this just
exposes it as a direct, on-demand action instead of only firing implicitly.

## Frontend (`CaddyPage.tsx`, Overview tab's sync-status card)

- New state: `version: string | null`, fetched once in the same `useEffect` that already calls
  `loadStatus()`/`loadConfig()` on mount.
- New state: `reloading: boolean`, true while the reload POST is in flight.
- Version string rendered inline on the existing status line (e.g. next to "Caddy management
  enabled"), falling back to nothing/blank if `null` — no separate error banner, matches how
  `configError`/`statusError` already degrade gracefully elsewhere on this page without
  blocking the rest of the card.
- A "Reload" button next to the existing refresh icon button, using the same `RefreshCw` icon
  convention already on this card. `onClick`: POST `/caddy/reload`, disable the button while
  `reloading`, then call `loadStatus()` + `loadConfig()` again on completion (mirrors the
  existing `onRowSaved` pattern used elsewhere on this page after a mutation) so the card
  reflects the fresh sync result immediately instead of waiting for the next unrelated change.

## Error handling

- Version fetch failure: `version` stays `null`, rendered as blank/omitted. Non-blocking — the
  rest of the Overview tab doesn't depend on it.
- Reload failure: surfaces through the existing `status.ok === false` / `"last sync failed:
  ..."` text already wired to `status.error` — no new error UI needed, the reload button's
  result flows through the same `loadStatus()` call every other status update uses.

## Testing

- `test_docker_service.py` (or the `caddy_service` test file, whichever currently holds
  `CaddyService` coverage): three cases for `version()`, mirroring the existing
  `find_caddy_container`/`exec_run` test pattern (fake container/exec_run objects, no real
  Docker):
  1. container found, `exec_run` exits 0 → returns the stripped/decoded output.
  2. container found, `exec_run` exits non-zero → returns `None`, logs a warning.
  3. container not found → returns `None` without calling `exec_run`.
