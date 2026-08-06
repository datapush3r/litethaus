# Caddy Overview: Reload + Version Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Reload" button and a read-only Caddy version string to the Caddy page's Overview tab.

**Architecture:** `CaddyService.version()` docker-execs `caddy version` inside the Caddy container (mirrors `CertService.list_certificates()`'s exec pattern exactly). Two new thin FastAPI routes expose it and a manual re-trigger of the sync `caddy_service.sync()` already performs as a side effect elsewhere. The frontend adds one API call pair and wires a button + text into the existing sync-status card - no new component.

**Tech Stack:** FastAPI (backend), React + TypeScript (frontend), `unittest.mock` for backend tests (no pytest in this repo - see `backend/test_caddy_service.py`'s `if __name__ == "__main__":` pattern).

## Global Constraints

- Full spec: `docs/superpowers/specs/2026-08-07-caddy-reload-version-design.md`.
- Backend tests are plain-assert functions run directly (`python3 test_caddy_service.py`), not pytest - every new test function must also be added to the file's `if __name__ == "__main__":` call list or it silently never runs.
- Run backend tests with `LITETHAUS_CONFIG_PATH` pointed at a scratch path (the repo's default `/config/config.yaml` isn't writable outside the container): `LITETHAUS_CONFIG_PATH=/tmp/litethaus-test-config.yaml python3 test_caddy_service.py`.
- No frontend test runner exists in this repo (no vitest/jest in `frontend/package.json`) - frontend verification is `npx oxlint <files>` + `npm run build`, matching how every prior frontend change in this project was verified.
- New `CaddyService` tests must mock at the same points existing tests in the file already do (e.g. `patch("caddy_service.config_service.load", ...)`, `patch("caddy_service.urllib.request.urlopen", ...)`) - i.e. patch names as imported into `caddy_service`'s own namespace, not `docker_service`'s.

---

### Task 1: `CaddyService.version()`

**Files:**
- Modify: `backend/caddy_service.py`
- Test: `backend/test_caddy_service.py`

**Interfaces:**
- Consumes: `docker_service.find_caddy_container() -> Any | None` (returns an object with a `.name` attribute, or `None`); `docker_service.exec_run(container_name: str, cmd: list[str]) -> tuple[int, bytes]` - both already exist in `backend/docker_service.py`.
- Produces: `CaddyService.version(self) -> str | None` - `None` if the Caddy container can't be found or the exec exits non-zero; otherwise the decoded, stripped stdout of `caddy version`. Task 2 calls this.

- [ ] **Step 1: Write the three failing tests**

Open `backend/test_caddy_service.py`. Change the top import line from:

```python
from unittest.mock import patch, MagicMock
```

to:

```python
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
```

Then add these three test functions anywhere below the existing `test_fetch_upstreams_returns_parsed_json` function:

```python
def test_version_returns_stripped_output_when_container_found() -> None:
    fake_container = SimpleNamespace(name="litethaus-caddy-1")
    with patch("caddy_service.docker_service.find_caddy_container", return_value=fake_container), \
         patch("caddy_service.docker_service.exec_run", return_value=(0, b"v2.8.4 h1:abc123\n")):
        result = CaddyService(admin_url="http://caddy:2019").version()
    assert result == "v2.8.4 h1:abc123"


def test_version_returns_none_when_exec_fails() -> None:
    fake_container = SimpleNamespace(name="litethaus-caddy-1")
    with patch("caddy_service.docker_service.find_caddy_container", return_value=fake_container), \
         patch("caddy_service.docker_service.exec_run", return_value=(1, b"exec failed\n")):
        result = CaddyService(admin_url="http://caddy:2019").version()
    assert result is None


def test_version_returns_none_when_container_not_found() -> None:
    with patch("caddy_service.docker_service.find_caddy_container", return_value=None), \
         patch("caddy_service.docker_service.exec_run") as exec_run:
        result = CaddyService(admin_url="http://caddy:2019").version()
    assert result is None
    exec_run.assert_not_called()
```

Add all three calls to the `if __name__ == "__main__":` block at the bottom of the file, right before `print("ok")`:

```python
    test_version_returns_stripped_output_when_container_found()
    test_version_returns_none_when_exec_fails()
    test_version_returns_none_when_container_not_found()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend
source .venv/bin/activate
LITETHAUS_CONFIG_PATH=/tmp/litethaus-test-config.yaml python3 test_caddy_service.py
```

Expected: `AttributeError: 'CaddyService' object has no attribute 'version'` (or a `patch` failure on `caddy_service.docker_service`, since `caddy_service.py` doesn't import `docker_service` yet).

- [ ] **Step 3: Implement `version()`**

In `backend/caddy_service.py`, change the import block at the top from:

```python
from config_service import config_service
from stacks_service import Stack
```

to:

```python
from config_service import config_service
from docker_service import docker_service
from stacks_service import Stack
```

Then add this method to `CaddyService`, right after `fetch_upstreams`:

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

- [ ] **Step 4: Run the tests to verify they pass**

```bash
LITETHAUS_CONFIG_PATH=/tmp/litethaus-test-config.yaml python3 test_caddy_service.py
```

Expected: `ok` printed at the end, no `AssertionError`/`AttributeError` (ignore the intentionally-logged tracebacks from unrelated pre-existing tests like `test_sync_failure_records_error_status` - those are expected noise from tests that deliberately trigger a logged failure path).

- [ ] **Step 5: Commit**

```bash
cd /home/tnorris/git/litehaus/.claude/worktrees/caddy-ui-management
git add backend/caddy_service.py backend/test_caddy_service.py
git commit -m "feat: add CaddyService.version() via docker exec"
```

---

### Task 2: `GET /caddy/version` and `POST /caddy/reload` routes

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `CaddyService.version() -> str | None` (Task 1); `caddy_service.sync(stacks: list[Stack]) -> None` and `caddy_service.status() -> dict[str, Any]` (already exist); `stack_service.list_stacks() -> list[Stack]` (already used identically by every other mutating route in this file).
- Produces: `GET /api/caddy/version` returning `{"version": str | None}`; `POST /api/caddy/reload` returning the same shape as `GET /api/caddy/status`. Task 3's frontend API client calls both.

- [ ] **Step 1: Add the two routes**

In `backend/main.py`, find the existing `caddy_status` route:

```python
@app.get("/caddy/status")
def caddy_status() -> dict[str, Any]:
    return caddy_service.status()
```

Add these two routes directly after it:

```python
@app.get("/caddy/version")
def caddy_version() -> dict[str, Any]:
    return {"version": caddy_service.version()}


@app.post("/caddy/reload")
def caddy_reload() -> dict[str, Any]:
    caddy_service.sync(stack_service.list_stacks())
    return caddy_service.status()
```

There's no per-route test file for `main.py` in this repo (`backend/test_*.py` covers services, not routes - see the file listing in `backend/CLAUDE.md`'s Development section), so verification here is a manual curl check against the real running backend rather than a new automated test.

- [ ] **Step 2: Verify against the running backend**

The prod backend container is already running and mounts real data; hit it directly:

```bash
curl -s http://localhost:8000/caddy/version
```

Expected: `{"version":null}` if this endpoint is hit before Task 1's image is rebuilt into that container, since the running container doesn't have the new code yet - that's fine, this step is just confirming the route wires up and returns 200 rather than 404/500 once your dev loop (`VITE_API_PROXY_TARGET` local frontend, or a rebuilt image) is pointed at code that includes this change. If you're running the backend locally instead (`uvicorn main:app --reload` per `backend/CLAUDE.md`), curl `http://localhost:8000/caddy/version` there and expect a real version string (or `null` if no Caddy container is reachable from that environment) - either is a valid 200 response, confirming the route works.

```bash
curl -s -X POST http://localhost:8000/caddy/reload
```

Expected: 200 with a JSON body matching `GET /caddy/status`'s shape (`{"enabled": ..., "ok": ..., "at": ..., "error": ...}`).

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add GET /caddy/version and POST /caddy/reload routes"
```

---

### Task 3: Frontend - Overview tab UI

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/CaddyPage.tsx`

**Interfaces:**
- Consumes: `GET /api/caddy/version`, `POST /api/caddy/reload` (Task 2).
- Produces: `fetchCaddyVersion(): Promise<{ version: string | null }>` and `reloadCaddy(): Promise<CaddyStatus>` in `api.ts`, used only by `CaddyPage.tsx`.

- [ ] **Step 1: Add the two API client functions**

In `frontend/src/api.ts`, find:

```typescript
export async function fetchCaddyStatus(): Promise<CaddyStatus> {
  const res = await fetch('/api/caddy/status')
  return unwrap<CaddyStatus>(res, 'failed to load Caddy status')
}
```

Add directly after it:

```typescript
export async function fetchCaddyVersion(): Promise<{ version: string | null }> {
  const res = await fetch('/api/caddy/version')
  return unwrap(res, 'failed to load Caddy version')
}

export async function reloadCaddy(): Promise<CaddyStatus> {
  const res = await fetch('/api/caddy/reload', { method: 'POST' })
  return unwrap<CaddyStatus>(res, 'failed to reload Caddy')
}
```

- [ ] **Step 2: Wire state and handlers into `CaddyPage.tsx`**

In `frontend/src/components/CaddyPage.tsx`, change the import block from:

```typescript
import {
  fetchCaddyConfig,
  fetchCaddyLive,
  fetchCaddyStatus,
  fetchConfig,
  updateConfig,
  type CaddyStatus,
  type Stack,
} from '../api'
```

to:

```typescript
import {
  fetchCaddyConfig,
  fetchCaddyLive,
  fetchCaddyStatus,
  fetchCaddyVersion,
  fetchConfig,
  reloadCaddy,
  updateConfig,
  type CaddyStatus,
  type Stack,
} from '../api'
```

Change:

```typescript
  const [status, setStatus] = useState<CaddyStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [generatedConfig, setGeneratedConfig] = useState<Record<string, unknown> | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
```

to:

```typescript
  const [status, setStatus] = useState<CaddyStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [version, setVersion] = useState<string | null>(null)
  const [reloading, setReloading] = useState(false)
  const [generatedConfig, setGeneratedConfig] = useState<Record<string, unknown> | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
```

Change:

```typescript
  function loadStatus() {
    setStatusError(null)
    fetchCaddyStatus()
      .then(setStatus)
      .catch((err) => setStatusError(err instanceof Error ? err.message : 'failed to load status'))
  }
```

to:

```typescript
  function loadStatus() {
    setStatusError(null)
    fetchCaddyStatus()
      .then(setStatus)
      .catch((err) => setStatusError(err instanceof Error ? err.message : 'failed to load status'))
  }

  function loadVersion() {
    fetchCaddyVersion()
      .then((res) => setVersion(res.version))
      .catch(() => setVersion(null))
  }

  async function handleReload() {
    setReloading(true)
    try {
      await reloadCaddy()
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : 'failed to reload')
    } finally {
      setReloading(false)
      loadStatus()
      loadConfig()
    }
  }
```

Change the mount effect from:

```typescript
  useEffect(() => {
    loadStatus()
    loadConfig()
    fetchConfig().then((cfg) => setExtraRoutesJson(prettify(String(cfg.caddy_extra_routes_json ?? ''))))
  }, [])
```

to:

```typescript
  useEffect(() => {
    loadStatus()
    loadVersion()
    loadConfig()
    fetchConfig().then((cfg) => setExtraRoutesJson(prettify(String(cfg.caddy_extra_routes_json ?? ''))))
  }, [])
```

- [ ] **Step 3: Add the Reload button and version text to the sync-status card**

Change:

```typescript
          <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
            <div className="flex items-center justify-between">
              <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Sync status</h2>
              <button
                onClick={loadStatus}
                aria-label="Refresh status"
                className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
              >
                <RefreshCw size={14} />
              </button>
            </div>
```

to:

```typescript
          <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
            <div className="flex items-center justify-between">
              <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Sync status</h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleReload}
                  disabled={reloading}
                  className="text-xs text-neutral-500 hover:text-neutral-800 disabled:opacity-40 dark:text-neutral-400 dark:hover:text-neutral-200"
                >
                  {reloading ? 'Reloading…' : 'Reload'}
                </button>
                <button
                  onClick={loadStatus}
                  aria-label="Refresh status"
                  className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            </div>
```

Change:

```typescript
                {status.at && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">{new Date(status.at).toLocaleString()}</span>
                )}
              </div>
            )}
          </div>
```

to:

```typescript
                {status.at && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">{new Date(status.at).toLocaleString()}</span>
                )}
                {version && <span className="text-xs text-neutral-400 dark:text-neutral-500">Caddy {version}</span>}
              </div>
            )}
          </div>
```

- [ ] **Step 4: Lint and build**

```bash
cd frontend
npx oxlint src/api.ts src/components/CaddyPage.tsx
npm run build
```

Expected: both exit 0, no TypeScript errors, no lint findings.

- [ ] **Step 5: Manual verification**

With the local dev loop running (`VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev`, per this session's earlier setup) and the backend running Task 1+2's code:

1. Open the Caddy page's Overview tab. Confirm a version string ("Caddy v2.x.x ...") appears next to the sync-status line.
2. Click "Reload". Confirm the button shows "Reloading…" briefly, then the "last sync ok"/timestamp updates.
3. Stop the Caddy container (or point at an unreachable admin URL) and click "Reload" again - confirm the existing "last sync failed: ..." text appears instead of a crash or silent no-op.

- [ ] **Step 6: Commit**

```bash
cd /home/tnorris/git/litehaus/.claude/worktrees/caddy-ui-management
git add frontend/src/api.ts frontend/src/components/CaddyPage.tsx
git commit -m "feat: add Reload button and Caddy version display to Overview tab"
git push origin worktree-caddy-ui-management
```
