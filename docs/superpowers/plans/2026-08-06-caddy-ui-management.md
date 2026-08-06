# Caddy UI Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give litethaus's Caddy page live route health, TLS certificate tracking, and an access-log viewer, and fix the per-stack Caddy settings gap on each stack's own detail page (`service`/`lan_only` weren't really editable there).

**Architecture:** CaddyPage.tsx becomes a tabbed shell (reusing the existing `TabBar` component) over five sections: Overview (unchanged), Routes (existing editable table + 3 new live-health columns), TLS Certificates (new), Access Logs (new), Advanced (unchanged). Backend reads TLS certs and streams access logs from the Caddy container via `docker exec`/`docker logs` (litethaus already shells out to `docker` for stack terminals/logs — same pattern, pointed at Caddy instead of a stack), and reads route health from Caddy's own admin API (`/reverse_proxy/upstreams`) with zero new Caddy config required. StackDetail.tsx's metadata block gets `service`/`lan_only` wired up to the same `PATCH /stacks/{name}/metadata` endpoint CaddyPage's table already uses, plus a read-only cert-expiry line.

**Tech Stack:** Python 3.11+ (FastAPI, stdlib `urllib.request`, `docker` SDK, new `cryptography` dep), TypeScript/React 19 + Tailwind, no new frontend dependencies.

## Global Constraints

- YAML edits (`config.yaml`, `.litethaus.yaml`) go through `ruamel.yaml` only — not touched by this plan (no new YAML-shape changes beyond flat `config.yaml` keys, which `config_service.py`'s existing `_yaml` instance already handles).
- Backend HTTP calls to Caddy's admin API use stdlib `urllib.request` only (matches `caddy_service.py`'s existing `fetch_live_config()`/`sync()`) — no `requests`/`httpx`.
- No pytest: every `backend/test_*.py` is plain-`assert` + a manual `if __name__ == "__main__":` runner block. New tests follow that exact shape.
- One service class per concern (`CLAUDE.md`): new backend logic goes in `cert_service.py` (TLS certs), not bolted onto `caddy_service.py` or `docker_service.py`.
- Auth: any new websocket duplicates the inline session-cookie check already used by `/api/stacks/{name}/logs` and `/api/stacks/{name}/terminal` in `main.py` — the HTTP auth middleware doesn't run on websocket upgrades.
- Filesystem/Compose stays the source of truth — no database, no new persistent litethaus-owned state beyond `config.yaml` fields.
- Frontend has no test runner (no jest/vitest in `package.json`); verification for frontend tasks is `npm run build` (type-check) + `npm run lint` (oxlint) + manual browser check, matching the repo's current practice.

---

### Task 1: TLS certificate parsing (`cert_service.py`)

**Files:**
- Create: `backend/cert_service.py`
- Test: `backend/test_cert_service.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `parse_certificates(pem_data: bytes) -> list[dict[str, Any]]`, where each dict is `{"domains": list[str], "issuer": str, "expires_at": str}` (`expires_at` is an ISO-8601 UTC string). Later tasks (2, 6) call this via `cert_service.list_certificates()`.

- [ ] **Step 1: Add the `cryptography` dependency**

Edit `backend/requirements.txt` — add a line `cryptography` (bare, no pin, matching every other line in this file).

- [ ] **Step 2: Write the failing tests**

Create `backend/test_cert_service.py`:

```python
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cert_service import parse_certificates


def _make_cert_pem(domain: str, issuer_cn: str, days_until_expiry: int) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days_until_expiry))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def test_parse_certificates_extracts_domain_issuer_and_expiry() -> None:
    pem = _make_cert_pem("app.home.arpa", "litethaus internal CA", 30)
    certs = parse_certificates(pem)

    assert len(certs) == 1
    assert certs[0]["domains"] == ["app.home.arpa"]
    assert certs[0]["issuer"] == "litethaus internal CA"
    expires = datetime.fromisoformat(certs[0]["expires_at"])
    assert 29 <= (expires - datetime.now(timezone.utc)).days <= 30


def test_parse_certificates_handles_multiple_concatenated_pem_blocks() -> None:
    combined = _make_cert_pem("a.example.com", "CA", 10) + _make_cert_pem("b.example.com", "CA", 20)
    certs = parse_certificates(combined)
    assert [c["domains"] for c in certs] == [["a.example.com"], ["b.example.com"]]


def test_parse_certificates_skips_unparseable_blocks_without_raising() -> None:
    garbage = b"-----BEGIN CERTIFICATE-----\nnotarealcert\n-----END CERTIFICATE-----\n"
    assert parse_certificates(garbage) == []


def test_parse_certificates_returns_empty_list_for_empty_input() -> None:
    assert parse_certificates(b"") == []


if __name__ == "__main__":
    test_parse_certificates_extracts_domain_issuer_and_expiry()
    test_parse_certificates_handles_multiple_concatenated_pem_blocks()
    test_parse_certificates_skips_unparseable_blocks_without_raising()
    test_parse_certificates_returns_empty_list_for_empty_input()
    print("ok")
```

- [ ] **Step 2b: Run the test to verify it fails**

Run (inside the running dev backend container, or a local venv with `pip install -r backend/requirements.txt`):
`python3 backend/test_cert_service.py`
Expected: `ModuleNotFoundError: No module named 'cert_service'`

- [ ] **Step 3: Implement `cert_service.py`**

Create `backend/cert_service.py`:

```python
import logging
import re
from typing import Any

from cryptography import x509
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)

_PEM_BLOCK = re.compile(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL)

# Where Caddy's file storage module keeps ACME/internal-CA-issued leaf certs
# inside its container - see caddy/Dockerfile and docker-compose's caddy_data
# volume. Not configurable; it's Caddy's own fixed layout.
CADDY_CERT_DIR = "/data/caddy/certificates"


def parse_certificates(pem_data: bytes) -> list[dict[str, Any]]:
    """Parse one or more concatenated PEM certificates (as returned by `find
    ... -exec cat {} +` inside the Caddy container) into summary dicts. A
    block that fails to parse is logged and skipped rather than raising, so
    one corrupt file doesn't blank out the whole certificate list."""
    results = []
    for block in _PEM_BLOCK.findall(pem_data):
        try:
            cert = x509.load_pem_x509_certificate(block)
        except Exception:
            logger.exception("Failed to parse a certificate block, skipping")
            continue
        try:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            domains = san.value.get_values_for_type(x509.DNSName)
        except x509.ExtensionNotFound:
            domains = []
        issuer_cn = next(
            (attr.value for attr in cert.issuer if attr.oid == NameOID.COMMON_NAME),
            cert.issuer.rfc4514_string(),
        )
        results.append(
            {
                "domains": domains,
                "issuer": issuer_cn,
                "expires_at": cert.not_valid_after_utc.isoformat(),
            }
        )
    return results
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 backend/test_cert_service.py`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/cert_service.py backend/test_cert_service.py backend/requirements.txt
git commit -m "feat: add TLS certificate PEM parsing"
```

---

### Task 2: Caddy container resolution + one-off exec (`docker_service.py`)

**Files:**
- Modify: `backend/docker_service.py`
- Modify: `backend/test_docker_service.py`
- Modify: `backend/config_service.py` (add `caddy_container_name` default)

**Interfaces:**
- Consumes: `DockerService._config.load()` (existing), `NotFound` from `docker.errors` (already imported).
- Produces: `docker_service.find_caddy_container() -> Any | None` and `docker_service.exec_run(container_name: str, cmd: list[str]) -> tuple[int, bytes]`. Task 3 (`cert_service.list_certificates()`) and Task 6 (`main.py`'s new endpoints/websocket) call both.

- [ ] **Step 1: Add `caddy_container_name` to `config.yaml`'s defaults**

In `backend/config_service.py`, insert after the `caddy_extra_routes_json` block (after line 73, before the `theme` line):

```python
# Override for which container is "the" Caddy container, used by the TLS
# certificate tracker and access log viewer. Leave blank to auto-resolve via
# the "com.docker.compose.service=caddy" label Compose always sets (works
# regardless of an explicit container_name: override) - only set this if
# Caddy runs outside litethaus's own Compose project.
caddy_container_name: ""

```

- [ ] **Step 2: Write the failing tests**

In `backend/test_docker_service.py`, replace the existing `_svc()` helper (lines 9-12) with one that accepts overrides, and add the new tests. Replace:

```python
def _svc() -> DockerService:
    # A fresh, unbootstrapped config path so tests never touch the real
    # /config/config.yaml or depend on project_prefix being unset there.
    return DockerService(config=ConfigService(Path(tempfile.mkdtemp()) / "config.yaml"))
```

with:

```python
def _svc(overrides: dict[str, object] | None = None) -> DockerService:
    # A fresh, unbootstrapped config path so tests never touch the real
    # /config/config.yaml or depend on project_prefix being unset there.
    config = ConfigService(Path(tempfile.mkdtemp()) / "config.yaml")
    if overrides:
        config.update(overrides)
    return DockerService(config=config)


class _RecordingContainers:
    """Stand-in for docker-py's client.containers - records what filters/
    names it was called with instead of hitting a real Docker daemon."""

    def __init__(self, list_result: list | None = None, get_result: object | None = None) -> None:
        self.list_calls: list[dict | None] = []
        self.get_calls: list[str] = []
        self._list_result = list_result or []
        self._get_result = get_result

    def list(self, filters: dict | None = None) -> list:
        self.list_calls.append(filters)
        return self._list_result

    def get(self, name: str) -> object:
        self.get_calls.append(name)
        if self._get_result is None:
            from docker.errors import NotFound
            raise NotFound(name)
        return self._get_result
```

Then add before the `if __name__ == "__main__":` block:

```python
def test_find_caddy_container_resolves_by_compose_service_label() -> None:
    svc = _svc()
    fake_container = SimpleNamespace(name="myproj-caddy-1")
    containers = _RecordingContainers(list_result=[fake_container])
    svc._client = SimpleNamespace(containers=containers)

    result = svc.find_caddy_container()

    assert result is fake_container
    assert containers.list_calls == [{"label": "com.docker.compose.service=caddy"}]


def test_find_caddy_container_uses_override_name_when_configured() -> None:
    svc = _svc({"caddy_container_name": "my-caddy"})
    fake_container = SimpleNamespace(name="my-caddy")
    containers = _RecordingContainers(get_result=fake_container)
    svc._client = SimpleNamespace(containers=containers)

    result = svc.find_caddy_container()

    assert result is fake_container
    assert containers.get_calls == ["my-caddy"]


def test_find_caddy_container_returns_none_when_not_found() -> None:
    svc = _svc()
    svc._client = SimpleNamespace(containers=_RecordingContainers(list_result=[]))
    assert svc.find_caddy_container() is None


def test_exec_run_returns_exit_code_and_output() -> None:
    svc = _svc()
    fake_container = SimpleNamespace(exec_run=lambda cmd: SimpleNamespace(exit_code=0, output=b"hello\n"))
    svc._client = SimpleNamespace(containers=_RecordingContainers(get_result=fake_container))

    exit_code, output = svc.exec_run("some-container", ["echo", "hello"])

    assert exit_code == 0
    assert output == b"hello\n"
```

Add `from types import SimpleNamespace` to the top of `backend/test_docker_service.py`'s imports.

- [ ] **Step 2b: Run the tests to verify they fail**

Run: `python3 backend/test_docker_service.py`
Expected: `AttributeError: 'DockerService' object has no attribute 'find_caddy_container'`

- [ ] **Step 3: Implement `find_caddy_container()` and `exec_run()`**

In `backend/docker_service.py`, add a module-level constant after `BAD_HEALTH_STATES` (line 15):

```python
CADDY_SERVICE_LABEL = "com.docker.compose.service=caddy"
```

Add these two methods to `DockerService`, right after `find_container()` (after line 110, before `exec_shell()`):

```python
    def find_caddy_container(self) -> Any | None:
        # Caddy isn't a scanned "stack" (it's not under stacks_dir), so it has
        # no project label to filter by the way container_details() does.
        # Compose always sets com.docker.compose.service=caddy regardless of
        # an explicit container_name: override, so that's the reliable
        # zero-config match; caddy_container_name in config.yaml is only for
        # the rare case Caddy runs outside litethaus's own Compose project.
        override = self._config.load().get("caddy_container_name") or ""
        if override:
            try:
                return self.client.containers.get(override)
            except NotFound:
                return None
        containers = self.client.containers.list(filters={"label": CADDY_SERVICE_LABEL})
        return containers[0] if containers else None

    def exec_run(self, container_name: str, cmd: list[str]) -> tuple[int, bytes]:
        # One-off non-interactive exec via docker-py's high-level exec_run -
        # a genuinely different code path from exec_shell()'s CLI+pty socket
        # workaround above (that EOF bug was specific to the low-level
        # client.api.exec_start(..., socket=True) hijack; exec_run() doesn't
        # use it).
        container = self.client.containers.get(container_name)
        result = container.exec_run(cmd)
        return result.exit_code, result.output
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 backend/test_docker_service.py`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/docker_service.py backend/test_docker_service.py backend/config_service.py
git commit -m "feat: resolve Caddy's container and add one-off docker exec"
```

---

### Task 3: Wire cert reading to Docker (`cert_service.list_certificates()`)

**Files:**
- Modify: `backend/cert_service.py`
- Modify: `backend/test_cert_service.py`

**Interfaces:**
- Consumes: `docker_service.find_caddy_container()`, `docker_service.exec_run()` (Task 2); `parse_certificates()` (Task 1, same file).
- Produces: `cert_service.list_certificates() -> list[dict[str, Any]]` (module-level singleton, same pattern as `caddy_service`/`docker_service`). Task 6 (`main.py`'s `GET /caddy/certificates`) and Task 7 (`health_service.py`'s expiry check) call this.

- [ ] **Step 1: Write the failing test**

Append to `backend/test_cert_service.py`, before the `if __name__ == "__main__":` block:

```python
from types import SimpleNamespace
from unittest.mock import patch


def test_list_certificates_returns_empty_when_no_caddy_container() -> None:
    with patch("cert_service.docker_service.find_caddy_container", return_value=None):
        assert cert_service.list_certificates() == []


def test_list_certificates_execs_find_and_parses_output() -> None:
    pem = _make_cert_pem("app.home.arpa", "CA", 30)
    fake_container = SimpleNamespace(name="litethaus-caddy")
    with patch("cert_service.docker_service.find_caddy_container", return_value=fake_container), \
         patch("cert_service.docker_service.exec_run", return_value=(0, pem)) as exec_run:
        result = cert_service.list_certificates()

    assert result[0]["domains"] == ["app.home.arpa"]
    exec_run.assert_called_once_with(
        "litethaus-caddy", ["find", "/data/caddy/certificates", "-name", "*.crt", "-exec", "cat", "{}", "+"]
    )
```

Add `from cert_service import cert_service` to the existing `from cert_service import parse_certificates` import line (combine into one `from cert_service import cert_service, parse_certificates`).

- [ ] **Step 1b: Run the test to verify it fails**

Run: `python3 backend/test_cert_service.py`
Expected: `ImportError: cannot import name 'cert_service'`

- [ ] **Step 2: Implement `CertService`**

Append to `backend/cert_service.py`:

```python
from docker_service import docker_service

CERT_FIND_CMD = ["find", CADDY_CERT_DIR, "-name", "*.crt", "-exec", "cat", "{}", "+"]


class CertService:
    def list_certificates(self) -> list[dict[str, Any]]:
        container = docker_service.find_caddy_container()
        if container is None:
            return []
        exit_code, output = docker_service.exec_run(container.name, CERT_FIND_CMD)
        if exit_code != 0:
            logger.warning("cert listing inside %s exited %s: %r", container.name, exit_code, output[:200])
        return parse_certificates(output)


cert_service = CertService()
```

(Move the `from docker_service import docker_service` import to the top of the file with the other imports, and `CERT_FIND_CMD`/`class CertService`/`cert_service = CertService()` to the bottom, after `parse_certificates`.)

- [ ] **Step 3: Run the tests to verify they pass**

Run: `python3 backend/test_cert_service.py`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/cert_service.py backend/test_cert_service.py
git commit -m "feat: read TLS certs out of the Caddy container"
```

---

### Task 4: Route health (`caddy_service.fetch_upstreams()`)

**Files:**
- Modify: `backend/caddy_service.py`
- Modify: `backend/test_caddy_service.py`

**Interfaces:**
- Produces: `caddy_service.fetch_upstreams() -> list[dict[str, Any]]` (raw pass-through of Caddy's `/reverse_proxy/upstreams` JSON — each entry roughly `{"address": str, "num_requests": int, "fails": int}`, per Caddy's admin API; not reshaped here). Task 6 (`main.py`'s `GET /caddy/upstreams`) calls this.

- [ ] **Step 1: Write the failing test**

Add to `backend/test_caddy_service.py`, before the `if __name__ == "__main__":` block:

```python
from unittest.mock import MagicMock


def test_fetch_upstreams_returns_parsed_json() -> None:
    svc = CaddyService(admin_url="http://caddy:2019")
    payload = b'[{"address": "web:8080", "num_requests": 5, "fails": 0}]'
    fake_resp = MagicMock()
    fake_resp.__enter__.return_value.read.return_value = payload
    with patch("caddy_service.urllib.request.urlopen", return_value=fake_resp):
        result = svc.fetch_upstreams()
    assert result == [{"address": "web:8080", "num_requests": 5, "fails": 0}]
```

- [ ] **Step 1b: Run the test to verify it fails**

Run: `python3 backend/test_caddy_service.py`
Expected: `AttributeError: 'CaddyService' object has no attribute 'fetch_upstreams'`

- [ ] **Step 2: Implement `fetch_upstreams()`**

In `backend/caddy_service.py`, add right after `fetch_live_config()` (after line 36):

```python
    def fetch_upstreams(self) -> list[dict[str, Any]]:
        # Caddy's reverse_proxy handler always tracks passive upstream health
        # (request/fail counts) with zero extra config - this just surfaces
        # it for the Routes tab's live-health columns.
        with urllib.request.urlopen(f"{self.admin_url}/reverse_proxy/upstreams", timeout=5) as resp:
            return json.load(resp)
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `python3 backend/test_caddy_service.py`
Expected: `ok`

- [ ] **Step 4: Add the `caddy_access_log_enabled` param to `build_config()`**

This step is TDD too — write the tests first, then the two-line implementation.

Add to `backend/test_caddy_service.py`:

```python
def test_build_config_adds_logs_key_when_access_log_enabled() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([], access_log_enabled=True)
    assert cfg["apps"]["http"]["servers"]["litethaus"]["logs"] == {}


def test_build_config_omits_logs_key_by_default() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([])
    assert "logs" not in cfg["apps"]["http"]["servers"]["litethaus"]
```

Run `python3 backend/test_caddy_service.py`, confirm it fails (`build_config() got an unexpected keyword argument`), then in `backend/caddy_service.py`:

- Add `access_log_enabled: bool = False,` to `build_config()`'s signature (line 45, after `extra_routes_json: str = "",`).
- Inside the `config` dict's `"litethaus"` server block (lines 118-127), add a `"logs"` key when enabled — after building `config`, before `return config` (after line 152, right before `return config`):

```python
        if access_log_enabled:
            # {} turns on access logging using Caddy's default logger, which
            # writes to stderr - already captured by `docker logs`/our own
            # stream_container_logs(), same as every other container's
            # stdout+stderr. Revisit with an explicit encoder/writer only if
            # manual testing (see Task 6) shows the default format is unusable.
            config["apps"]["http"]["servers"]["litethaus"]["logs"] = {}

        return config
```

(This replaces the bare `return config` line 154 - delete that line since the new block ends with `return config` itself.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 backend/test_caddy_service.py`
Expected: `ok`

- [ ] **Step 6: Wire `access_log_enabled` through `sync()`**

In `backend/caddy_service.py`'s `sync()` (lines 156-167), add `access_log_enabled=cfg.get("caddy_access_log_enabled", False),` to the `build_config(...)` call, after `extra_routes_json=cfg.get("caddy_extra_routes_json", ""),`.

- [ ] **Step 7: Commit**

```bash
git add backend/caddy_service.py backend/test_caddy_service.py
git commit -m "feat: expose Caddy upstream health and an access-log toggle"
```

---

### Task 5: `config.yaml` default for `caddy_access_log_enabled`

**Files:**
- Modify: `backend/config_service.py`

**Interfaces:**
- Produces: `config.yaml`'s `caddy_access_log_enabled` key (bool, default `false`). Consumed by Task 4's `sync()` wiring and Task 6's `caddy_config()` endpoint.

- [ ] **Step 1: Add the default**

In `backend/config_service.py`, insert after the `caddy_container_name` block added in Task 2 Step 1 (i.e. right after `caddy_extra_routes_json`, before `caddy_container_name`, or directly after it — order doesn't matter, keep both together in the Caddy-settings cluster):

```python
# Whether Caddy emits access logs (one line per request) to its own
# container log, viewable from the Caddy page's Access Logs tab. Off by
# default - noisy for a home reverse proxy unless you're debugging routing.
caddy_access_log_enabled: false

```

- [ ] **Step 2: Verify by hand**

Run: `python3 -c "from config_service import ConfigService; from pathlib import Path; import tempfile; c = ConfigService(Path(tempfile.mkdtemp())/'config.yaml'); print(c.load()['caddy_access_log_enabled'])"` (from `backend/`)
Expected: `False`

- [ ] **Step 3: Commit**

```bash
git add backend/config_service.py
git commit -m "feat: add caddy_access_log_enabled config default"
```

---

### Task 6: Backend API surface (`main.py`)

**Files:**
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: `caddy_service.fetch_upstreams()` (Task 4), `cert_service.list_certificates()` (Task 3), `docker_service.find_caddy_container()`/`stream_container_logs()` (Task 2 and this task's Step 3), `cfg.get("caddy_access_log_enabled", False)` (Task 5).
- Produces: `GET /caddy/upstreams`, `GET /caddy/certificates`, `@app.websocket("/api/caddy/logs")`. Frontend Tasks 9-11 call these.

- [ ] **Step 1: Add `docker_service.stream_container_logs()`**

Factor the log-streaming subprocess loop out of `stream_logs()` so a plain container name (no `Stack`) can reuse it. In `backend/docker_service.py`, replace `stream_logs()` (lines 72-96) with:

```python
    async def _stream_process_lines(self, cmd: list[str]) -> AsyncIterator[str]:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield line.decode(errors="replace").rstrip("\n")
        finally:
            if process.returncode is None:
                process.terminate()

    async def stream_logs(self, stack: Stack, container: str | None = None) -> AsyncIterator[str]:
        # A single container's logs are streamed directly via `docker logs`
        # rather than `docker compose logs <service>` - the caller already
        # resolves `container` to an actual container name (see
        # find_container()), which docker logs takes directly with no need
        # to also know the service name from the compose file.
        cmd = (
            ["docker", "logs", "-f", "--tail", "100", container]
            if container
            else self._compose_cmd(stack, "logs", "-f", "--no-color", "--tail", "100")
        )
        async for line in self._stream_process_lines(cmd):
            yield line

    async def stream_container_logs(self, container_name: str) -> AsyncIterator[str]:
        # Same as stream_logs(container=...) above but for a container that
        # isn't part of any litethaus-scanned stack - i.e. Caddy itself.
        async for line in self._stream_process_lines(["docker", "logs", "-f", "--tail", "100", container_name]):
            yield line
```

- [ ] **Step 2: Verify the refactor didn't break stack log streaming**

Run: `python3 backend/test_docker_service.py` (unaffected, but confirms nothing else broke on import) — Expected: `ok`. Then manually: `docker compose -f docker-compose.dev.yaml up --build`, open a running stack's Logs panel in the UI, confirm log lines still stream (this path has no automated test today, same as before the refactor).

- [ ] **Step 3: Add the two GET endpoints**

In `backend/main.py`, add after `caddy_live()` (after line 194):

```python
@app.get("/caddy/upstreams")
def caddy_upstreams() -> list[dict[str, Any]]:
    try:
        return caddy_service.fetch_upstreams()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Caddy unreachable: {exc}")


@app.get("/caddy/certificates")
def caddy_certificates() -> list[dict[str, Any]]:
    return cert_service.list_certificates()
```

Add `from cert_service import cert_service` to the imports at the top of `main.py` (alongside the existing `from caddy_service import caddy_service` on line 14).

- [ ] **Step 4: Update `caddy_config()` to pass `access_log_enabled`**

In `caddy_config()` (lines 174-185), add `access_log_enabled=cfg.get("caddy_access_log_enabled", False),` to the `caddy_service.build_config(...)` call, after `extra_routes_json=cfg.get("caddy_extra_routes_json", ""),`.

- [ ] **Step 5: Add `caddy_access_log_enabled` to `CADDY_RELEVANT_KEYS`**

In `CADDY_RELEVANT_KEYS` (lines 128-137), add `"caddy_access_log_enabled",` to the set (so toggling it via `PATCH /config` triggers a resync).

- [ ] **Step 6: Add the `/api/caddy/logs` websocket**

Add after the `stack_terminal` websocket (after line 404, before the `STATIC_DIR` block):

```python
@app.websocket("/api/caddy/logs")
async def caddy_logs(websocket: WebSocket) -> None:
    if auth_service.enabled() and auth_service.is_configured() and not auth_service.is_valid_session(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4401)
        return

    container = docker_service.find_caddy_container()
    if container is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    async def forward_logs() -> None:
        while True:
            async with aclosing(docker_service.stream_container_logs(container.name)) as lines:
                async for line in lines:
                    await websocket.send_text(line)
            await asyncio.sleep(1)

    async def watch_disconnect() -> None:
        with suppress(WebSocketDisconnect):
            while True:
                await websocket.receive()

    forward_task = asyncio.create_task(forward_logs())
    disconnect_task = asyncio.create_task(watch_disconnect())
    done, pending = await asyncio.wait({forward_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    for task in done:
        with suppress(WebSocketDisconnect):
            task.result()
```

- [ ] **Step 7: Manual verification**

`docker compose -f docker-compose.dev.yaml up --build --profile caddy`, then from another shell:
`curl http://localhost:8080/api/caddy/upstreams` → expect `[]` or a JSON array (empty if no stacks have traffic yet).
`curl http://localhost:8080/api/caddy/certificates` → expect `[]` (no certs yet in `https_mode: off`, the default) without a 500.
Confirm both return valid JSON, not a stack trace.

- [ ] **Step 8: Commit**

```bash
git add backend/main.py backend/docker_service.py
git commit -m "feat: add Caddy upstream/certificate/log API endpoints"
```

---

### Task 7: Cert-expiry webhook alert (`health_service.py`)

**Files:**
- Modify: `backend/health_service.py`
- Create: `backend/test_health_service.py`

**Interfaces:**
- Consumes: `cert_service.list_certificates()` (Task 3), existing `webhook_url` config field, existing `_notify`-style POST pattern.
- Produces: `HealthService._check_certs_once(webhook_url: str) -> None`, called from `check_once()`. No other module depends on this (leaf feature).

- [ ] **Step 1: Write the failing tests**

Create `backend/test_health_service.py`:

```python
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from health_service import HealthService


def _svc() -> HealthService:
    svc = HealthService()
    svc._last_cert_check = 0.0
    return svc


def test_check_certs_skips_when_no_webhook_configured() -> None:
    svc = _svc()
    with patch("health_service.cert_service.list_certificates") as list_certs:
        svc._check_certs_once("")
        list_certs.assert_not_called()


def test_check_certs_respects_time_gate() -> None:
    svc = _svc()
    svc._last_cert_check = time.monotonic()
    with patch("health_service.cert_service.list_certificates") as list_certs:
        svc._check_certs_once("http://hook.example.com")
        list_certs.assert_not_called()


def test_check_certs_notifies_once_for_soon_expiring_cert() -> None:
    svc = _svc()
    soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    certs = [{"domains": ["app.example.com"], "issuer": "Let's Encrypt", "expires_at": soon}]
    with patch("health_service.cert_service.list_certificates", return_value=certs), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_certs_once("http://hook.example.com")
        assert urlopen.call_count == 1

        svc._last_cert_check = 0.0  # force past the time-gate again
        svc._check_certs_once("http://hook.example.com")
        assert urlopen.call_count == 1  # same cert, no repeat alert


def test_check_certs_does_not_notify_for_cert_far_from_expiry() -> None:
    svc = _svc()
    later = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    certs = [{"domains": ["app.example.com"], "issuer": "Let's Encrypt", "expires_at": later}]
    with patch("health_service.cert_service.list_certificates", return_value=certs), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_certs_once("http://hook.example.com")
        urlopen.assert_not_called()


if __name__ == "__main__":
    test_check_certs_skips_when_no_webhook_configured()
    test_check_certs_respects_time_gate()
    test_check_certs_notifies_once_for_soon_expiring_cert()
    test_check_certs_does_not_notify_for_cert_far_from_expiry()
    print("ok")
```

- [ ] **Step 1b: Run the tests to verify they fail**

Run: `python3 backend/test_health_service.py`
Expected: `AttributeError: 'HealthService' object has no attribute '_check_certs_once'`

- [ ] **Step 2: Implement the cert-expiry check**

In `backend/health_service.py`, add imports and constants at the top:

```python
import json
import logging
import threading
import time
import urllib.request
from datetime import datetime, timezone

from cert_service import cert_service
from config_service import config_service
from docker_service import BAD_HEALTH_STATES, docker_service
from stacks_service import stack_service

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15
CERT_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
CERT_EXPIRY_WARNING_DAYS = 14
```

Update `HealthService.__init__` (lines 16-18) to add the new tracking state:

```python
    def __init__(self) -> None:
        self._last_health: dict[str, str] = {}
        self._stop_event: threading.Event | None = None
        self._last_cert_check: float = 0.0
        self._alerted_certs: set[str] = set()
```

Update `check_once()` (lines 20-29) to also run the cert check, and add `_check_certs_once()`/`_notify_cert_expiry()` after `_notify()`:

```python
    def check_once(self) -> None:
        webhook_url = config_service.load().get("webhook_url") or ""
        for stack in stack_service.list_stacks():
            if stack.error:
                continue
            health = docker_service.summarize_health(docker_service.container_details(stack))
            became_bad = health in BAD_HEALTH_STATES and self._last_health.get(stack.name) != health
            self._last_health[stack.name] = health
            if became_bad and webhook_url:
                self._notify(webhook_url, stack.name, health)
        self._check_certs_once(webhook_url)
```

```python
    def _check_certs_once(self, webhook_url: str) -> None:
        # Cert expiry moves over days, not seconds - polling it on the same
        # 15s cadence as container health would be pure waste, so this gates
        # itself to once a day independent of watch_forever()'s loop period.
        now = time.monotonic()
        if now - self._last_cert_check < CERT_CHECK_INTERVAL_SECONDS:
            return
        self._last_cert_check = now
        if not webhook_url:
            return
        still_soon: set[str] = set()
        for cert in cert_service.list_certificates():
            domain = cert["domains"][0] if cert["domains"] else "unknown"
            expires_at = datetime.fromisoformat(cert["expires_at"])
            days_left = (expires_at - datetime.now(timezone.utc)).days
            if days_left > CERT_EXPIRY_WARNING_DAYS:
                continue
            still_soon.add(domain)
            if domain not in self._alerted_certs:
                self._notify_cert_expiry(webhook_url, domain, days_left)
        self._alerted_certs = still_soon

    def _notify_cert_expiry(self, webhook_url: str, domain: str, days_left: int) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"cert_domain": domain, "days_until_expiry": days_left}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send cert-expiry webhook for %s", domain)
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `python3 backend/test_health_service.py`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/health_service.py backend/test_health_service.py
git commit -m "feat: alert on soon-to-expire TLS certs via the health webhook"
```

---

### Task 8: Dev Compose volume for Caddy's `/data`

**Files:**
- Modify: `docker-compose.dev.yaml`

**Interfaces:** None (infra-only change).

- [ ] **Step 1: Add the named volume**

In `docker-compose.dev.yaml`, update the `caddy` service's `volumes:` (currently just `- ./caddy/Caddyfile:/etc/caddyfile`) to:

```yaml
    volumes:
      - ./caddy/Caddyfile:/etc/caddyfile
      - caddy_data:/data
```

Add a top-level `volumes:` section at the end of the file (it doesn't have one today):

```yaml

volumes:
  caddy_data:
```

- [ ] **Step 2: Verify**

Run: `docker compose -f docker-compose.dev.yaml config --profile caddy` — expect no YAML errors and the `caddy_data` volume listed under the `caddy` service's mounts and the top-level `volumes` key.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.dev.yaml
git commit -m "fix: persist Caddy's /data dir in dev so TLS certs survive restarts"
```

---

### Task 9: Frontend API client additions (`api.ts`)

**Files:**
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Produces: `CaddyUpstream` type, `fetchCaddyUpstreams()`, `CaddyCertificate` type, `fetchCaddyCertificates()`, `caddyLogsSocketUrl()`. Consumed by Tasks 10-12.

- [ ] **Step 1: Add the new types and functions**

In `frontend/src/api.ts`, add after `fetchCaddyLive()` (after line 221):

```typescript
export interface CaddyUpstream {
  address: string
  num_requests: number
  fails: number
}

export async function fetchCaddyUpstreams(): Promise<CaddyUpstream[]> {
  const res = await fetch('/api/caddy/upstreams')
  return unwrap(res, 'failed to load route health')
}

export interface CaddyCertificate {
  domains: string[]
  issuer: string
  expires_at: string
}

export async function fetchCaddyCertificates(): Promise<CaddyCertificate[]> {
  const res = await fetch('/api/caddy/certificates')
  return unwrap(res, 'failed to load certificates')
}

export function caddyLogsSocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/caddy/logs`
}
```

- [ ] **Step 2: Add the two new `Config` fields**

In the `Config` interface (lines 125-140), add after `caddy_extra_routes_json: string`:

```typescript
  caddy_access_log_enabled: boolean
  caddy_container_name: string
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run build` — expect it to succeed (type-check only, no consumers of the new exports yet so nothing to break).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api.ts
git commit -m "feat: add API client support for Caddy upstreams/certificates/logs"
```

---

### Task 10: `CaddyRoutesTab.tsx` (existing table + live health columns)

**Files:**
- Create: `frontend/src/components/CaddyRoutesTab.tsx`
- Modify: `frontend/src/components/CaddyPage.tsx` (remove the routes table it replaces; wired up in Task 13)

**Interfaces:**
- Consumes: `Stack[]`, `updateStackMetadata()`, `fetchCaddyUpstreams()` (Task 9).
- Produces: `export function CaddyRoutesTab({ stacks, onStacksChanged }: { stacks: Stack[]; onStacksChanged: () => void })`. Rendered by Task 13's `CaddyPage.tsx`.

- [ ] **Step 1: Create the file, moving `RouteRow` and the table, plus 3 new columns**

Create `frontend/src/components/CaddyRoutesTab.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { fetchCaddyUpstreams, updateStackMetadata, type CaddyUpstream, type Stack } from '../api'

interface CaddyRoutesTabProps {
  stacks: Stack[]
  onStacksChanged: () => void
}

export function CaddyRoutesTab({ stacks, onStacksChanged }: CaddyRoutesTabProps) {
  const [upstreams, setUpstreams] = useState<CaddyUpstream[]>([])

  function loadUpstreams() {
    fetchCaddyUpstreams()
      .then(setUpstreams)
      .catch(() => setUpstreams([]))
  }

  useEffect(() => {
    loadUpstreams()
    const interval = setInterval(loadUpstreams, 10000)
    return () => clearInterval(interval)
  }, [])

  const routableStacks = stacks.filter((s) => !s.error)

  function onRowSaved() {
    onStacksChanged()
    loadUpstreams()
  }

  return (
    <div>
      <h2 className="mb-2 text-xs uppercase text-neutral-400 dark:text-neutral-500">Stack routes</h2>
      <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
              <th className="px-3 py-2">Stack</th>
              <th className="px-3 py-2">Domain</th>
              <th className="px-3 py-2">Service</th>
              <th className="px-3 py-2">Port</th>
              <th className="px-3 py-2">LAN only</th>
              <th className="px-3 py-2">Health</th>
              <th className="px-3 py-2">Requests</th>
            </tr>
          </thead>
          <tbody>
            {routableStacks.map((stack) => (
              <RouteRow key={stack.name} stack={stack} upstreams={upstreams} onSaved={onRowSaved} />
            ))}
            {routableStacks.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-2 text-neutral-400 dark:text-neutral-500">
                  no stacks found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RouteRow({
  stack,
  upstreams,
  onSaved,
}: {
  stack: Stack
  upstreams: CaddyUpstream[]
  onSaved: () => void
}) {
  const meta = stack.x_litethaus
  const domain = typeof meta.domain === 'string' ? meta.domain : null
  const port = meta.port != null ? String(meta.port) : null
  const service = typeof meta.service === 'string' ? meta.service : (stack.services[0] ?? '')
  const lanOnly = Boolean(meta.lan_only)

  const [domainDraft, setDomainDraft] = useState(domain ?? '')
  const [portDraft, setPortDraft] = useState(port ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDomainDraft(domain ?? '')
    setPortDraft(port ?? '')
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stack.name, domain, port])

  async function save(patch: {
    domain?: string | null
    port?: number | null
    service?: string | null
    lan_only?: boolean | null
  }) {
    setError(null)
    try {
      await updateStackMetadata(stack.name, patch)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to save')
    }
  }

  function handleDomainBlur() {
    const next = domainDraft.trim()
    if (next === (domain ?? '')) return
    save({ domain: next || null })
  }

  function handlePortBlur() {
    const next = portDraft.trim()
    if (next === (port ?? '')) return
    if (next === '') {
      save({ port: null })
      return
    }
    const parsed = Number(next)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
      setError('port must be a whole number between 1 and 65535')
      setPortDraft(port ?? '')
      return
    }
    save({ port: parsed })
  }

  const dialAddress = service && port ? `${service}:${port}` : null
  const upstream = dialAddress ? upstreams.find((u) => u.address === dialAddress) : undefined

  return (
    <tr className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
      <td className="px-3 py-1.5 text-neutral-700 dark:text-neutral-200">{stack.name}</td>
      <td className="px-3 py-1.5">
        <input
          value={domainDraft}
          onChange={(e) => setDomainDraft(e.target.value)}
          onBlur={handleDomainBlur}
          placeholder="not proxied"
          className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </td>
      <td className="px-3 py-1.5">
        <select
          value={service}
          onChange={(e) => save({ service: e.target.value || null })}
          className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          {stack.services.map((svc) => (
            <option key={svc} value={svc}>
              {svc}
            </option>
          ))}
        </select>
      </td>
      <td className="px-3 py-1.5">
        <input
          value={portDraft}
          onChange={(e) => setPortDraft(e.target.value)}
          onBlur={handlePortBlur}
          placeholder="—"
          className="w-20 rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
      </td>
      <td className="px-3 py-1.5 text-center">
        <input
          type="checkbox"
          checked={lanOnly}
          onChange={(e) => save({ lan_only: e.target.checked || null })}
          title="Restrict to private/LAN IP ranges only"
        />
      </td>
      <td className="px-3 py-1.5">
        {!domain ? (
          <span className="text-neutral-400 dark:text-neutral-500">—</span>
        ) : !upstream ? (
          <span className="text-neutral-400 dark:text-neutral-500">no traffic yet</span>
        ) : upstream.fails > 0 ? (
          <span className="text-red-600 dark:text-red-400">degraded ({upstream.fails} fails)</span>
        ) : (
          <span className="text-green-600 dark:text-green-400">healthy</span>
        )}
      </td>
      <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">{upstream?.num_requests ?? '—'}</td>
    </tr>
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run build && npm run lint` — expect both to pass (this file isn't imported anywhere yet, so it's dead code until Task 13, but must still type-check and lint clean on its own).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CaddyRoutesTab.tsx
git commit -m "feat: add CaddyRoutesTab with live upstream health columns"
```

---

### Task 11: `CaddyCertificatesTab.tsx`

**Files:**
- Create: `frontend/src/components/CaddyCertificatesTab.tsx`

**Interfaces:**
- Consumes: `fetchCaddyCertificates()` (Task 9).
- Produces: `export function CaddyCertificatesTab()`. Rendered by Task 13's `CaddyPage.tsx`. Also reused by Task 14's `StackDetail.tsx` (which calls `fetchCaddyCertificates()` directly, not this component — this component is the full-table view, StackDetail needs one line).

- [ ] **Step 1: Create the component**

Create `frontend/src/components/CaddyCertificatesTab.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { fetchCaddyCertificates, type CaddyCertificate } from '../api'

const WARNING_DAYS = 14

function daysUntil(isoDate: string): number {
  return Math.floor((new Date(isoDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
}

export function CaddyCertificatesTab() {
  const [certs, setCerts] = useState<CaddyCertificate[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCaddyCertificates()
      .then(setCerts)
      .catch((err) => setError(err instanceof Error ? err.message : 'failed to load certificates'))
  }, [])

  return (
    <div>
      <h2 className="mb-2 text-xs uppercase text-neutral-400 dark:text-neutral-500">TLS certificates</h2>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
              <th className="px-3 py-2">Domain</th>
              <th className="px-3 py-2">Issuer</th>
              <th className="px-3 py-2">Expires</th>
              <th className="px-3 py-2">Days left</th>
            </tr>
          </thead>
          <tbody>
            {certs?.map((cert) => {
              const days = daysUntil(cert.expires_at)
              return (
                <tr key={cert.domains.join(',') + cert.expires_at} className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
                  <td className="px-3 py-1.5 text-neutral-700 dark:text-neutral-200">{cert.domains.join(', ') || '—'}</td>
                  <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">{cert.issuer}</td>
                  <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">{new Date(cert.expires_at).toLocaleDateString()}</td>
                  <td className={`px-3 py-1.5 ${days < WARNING_DAYS ? 'text-red-600 dark:text-red-400' : 'text-neutral-500 dark:text-neutral-400'}`}>
                    {days}
                  </td>
                </tr>
              )
            })}
            {certs?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-2 text-neutral-400 dark:text-neutral-500">
                  no certificates found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run build && npm run lint` — expect both to pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CaddyCertificatesTab.tsx
git commit -m "feat: add CaddyCertificatesTab"
```

---

### Task 12: `CaddyLogsTab.tsx`

**Files:**
- Create: `frontend/src/components/CaddyLogsTab.tsx`

**Interfaces:**
- Consumes: `caddyLogsSocketUrl()` (Task 9), `fetchConfig()`/`updateConfig()` (existing, for the access-log toggle), `LogPanel` component (existing, `frontend/src/components/LogPanel.tsx`).
- Produces: `export function CaddyLogsTab()`. Rendered by Task 13's `CaddyPage.tsx`.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/CaddyLogsTab.tsx`:

```typescript
import { useEffect, useState } from 'react'
import { caddyLogsSocketUrl, fetchConfig, updateConfig } from '../api'
import { LogPanel } from './LogPanel'

export function CaddyLogsTab() {
  const [lines, setLines] = useState<string[]>([])
  const [enabled, setEnabled] = useState(false)
  const [toggling, setToggling] = useState(false)

  useEffect(() => {
    fetchConfig().then((cfg) => setEnabled(Boolean(cfg.caddy_access_log_enabled)))
  }, [])

  useEffect(() => {
    const ws = new WebSocket(caddyLogsSocketUrl())
    ws.onmessage = (event) => setLines((prev) => [...prev, event.data])
    return () => ws.close()
  }, [])

  async function toggle() {
    setToggling(true)
    try {
      const cfg = await updateConfig({ caddy_access_log_enabled: !enabled })
      setEnabled(Boolean(cfg.caddy_access_log_enabled))
    } finally {
      setToggling(false)
    }
  }

  return (
    <div className="flex h-96 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Access logs</h2>
        <label className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
          <input type="checkbox" checked={enabled} disabled={toggling} onChange={toggle} />
          Log every request
        </label>
      </div>
      {!enabled && (
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          Access logging is off - Caddy's own error/startup log still streams below, but requests won't be logged
          until enabled.
        </p>
      )}
      <div className="flex-1 min-h-0">
        <LogPanel lines={lines} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run build && npm run lint` — expect both to pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CaddyLogsTab.tsx
git commit -m "feat: add CaddyLogsTab with access-log toggle"
```

---

### Task 13: `CaddyPage.tsx` tab shell

**Files:**
- Modify: `frontend/src/components/CaddyPage.tsx`

**Interfaces:**
- Consumes: `CaddyRoutesTab` (Task 10), `CaddyCertificatesTab` (Task 11), `CaddyLogsTab` (Task 12), `TabBar` (existing, `frontend/src/components/TabBar.tsx`).

- [ ] **Step 1: Replace the routes table section with the tab shell**

Rewrite `frontend/src/components/CaddyPage.tsx`. Keep the existing `status`/`generatedConfig`/`liveConfig`/`extraRoutesJson` state and logic (lines 1-98) exactly as-is; replace the JSX return (lines 107-243) to wrap Overview/Advanced in tab panels and delegate Routes/TLS/Logs to the new components, and delete the now-unused `RouteRow` function (lines 245-345, moved to `CaddyRoutesTab.tsx` in Task 10) and its now-unused `updateStackMetadata` import.

Change the imports (lines 1-12) to:

```typescript
import { useEffect, useState } from 'react'
import { Copy, RefreshCw } from 'lucide-react'
import {
  fetchCaddyConfig,
  fetchCaddyLive,
  fetchCaddyStatus,
  fetchConfig,
  updateConfig,
  type CaddyStatus,
  type Stack,
} from '../api'
import { CaddyCertificatesTab } from './CaddyCertificatesTab'
import { CaddyLogsTab } from './CaddyLogsTab'
import { CaddyRoutesTab } from './CaddyRoutesTab'
import { TabBar } from './TabBar'
```

Add a tab-state constant and hook right after the existing state declarations (after line 34, before `function loadStatus()`):

```typescript
  const TABS = ['Overview', 'Routes', 'TLS Certificates', 'Access Logs', 'Advanced']
  const [tab, setTab] = useState(TABS[0])
```

Replace the entire `return (...)` block (lines 107-243) with:

```typescript
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <TabBar items={TABS} active={tab} onSelect={setTab} />

      {tab === 'Overview' && (
        <div className="flex flex-col gap-6">
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
            {statusError && <p className="mt-1 text-sm text-red-600 dark:text-red-400">{statusError}</p>}
            {status && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <span
                  className={
                    status.enabled ? 'text-neutral-700 dark:text-neutral-200' : 'text-neutral-400 dark:text-neutral-500'
                  }
                >
                  {status.enabled ? 'Caddy management enabled' : 'Caddy management disabled'}
                </span>
                {status.enabled && status.ok !== undefined && (
                  <span className={status.ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                    {status.ok ? 'last sync ok' : `last sync failed: ${status.error}`}
                  </span>
                )}
                {status.at && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">{new Date(status.at).toLocaleString()}</span>
                )}
              </div>
            )}
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Generated Caddy config</h2>
              <button
                onClick={copyGenerated}
                className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
              >
                <Copy size={12} /> Copy
              </button>
            </div>
            {configError && <p className="text-sm text-red-600 dark:text-red-400">{configError}</p>}
            {generatedConfig && (
              <pre className="max-h-96 overflow-auto rounded border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
                {JSON.stringify(generatedConfig, null, 2)}
              </pre>
            )}

            <button
              onClick={toggleLive}
              className="mt-3 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
            >
              {liveOpen ? 'Hide' : 'Show'} live config on Caddy
            </button>
            {liveOpen && (
              <div className="mt-2">
                {liveLoading && <p className="text-sm text-neutral-400 dark:text-neutral-500">loading…</p>}
                {liveError && <p className="text-sm text-red-600 dark:text-red-400">{liveError}</p>}
                {liveConfig && (
                  <pre className="max-h-96 overflow-auto rounded border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
                    {JSON.stringify(liveConfig, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'Routes' && <CaddyRoutesTab stacks={stacks} onStacksChanged={onRowSaved} />}
      {tab === 'TLS Certificates' && <CaddyCertificatesTab />}
      {tab === 'Access Logs' && <CaddyLogsTab />}

      {tab === 'Advanced' && (
        <div>
          <p className="mb-2 text-xs text-neutral-400 dark:text-neutral-500">
            Raw Caddy route objects (JSON array), appended after the routes generated in the Routes tab. Leave blank
            to skip. Invalid JSON is ignored rather than breaking sync.
          </p>
          <textarea
            value={extraRoutesJson}
            onChange={(e) => setExtraRoutesJson(e.target.value)}
            rows={6}
            placeholder='[{"match": [{"host": ["extra.example.com"]}], "handle": [...]}]'
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 font-mono text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={saveExtraRoutes}
              disabled={savingExtraRoutes}
              className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {savingExtraRoutes ? 'Saving…' : 'Save'}
            </button>
            {extraRoutesSaved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
            {extraRoutesError && <span className="text-xs text-red-600 dark:text-red-400">{extraRoutesError}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
```

Delete the standalone `RouteRow` function that followed the old return block (old lines 245-345) — it now lives in `CaddyRoutesTab.tsx`. Also delete the now-dead `advancedOpen`/`setAdvancedOpen` state (line 30) and the `routableStacks` local (old line 100) — the Advanced section is now a plain tab panel, no longer collapsible, and `routableStacks` moved into `CaddyRoutesTab`. Rename `onRowSaved` (old lines 102-105) is still needed and unchanged (used by the `Routes` tab wiring above) — keep it as-is.

- [ ] **Step 2: Verify**

Run: `cd frontend && npm run build && npm run lint` — expect both to pass with zero unused-import/unused-variable errors (oxlint will flag `updateStackMetadata` or leftover `RouteRow` if either wasn't fully removed).

- [ ] **Step 3: Manual verification**

`docker compose -f docker-compose.dev.yaml up --build --profile caddy`, open the Caddy page in the browser, click through all 5 tabs, confirm: Overview shows sync status + config viewers as before; Routes shows the same editable table plus Health/Requests columns; TLS Certificates and Access Logs render without errors (empty states are fine with no certs/logs yet); Advanced shows the raw-passthrough textarea and still saves.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CaddyPage.tsx
git commit -m "feat: restructure CaddyPage into tabs"
```

---

### Task 14: `StackDetail.tsx` per-stack Caddy settings fix

**Files:**
- Modify: `frontend/src/components/StackDetail.tsx`

**Interfaces:**
- Consumes: `updateStackMetadata()` (existing), `fetchCaddyCertificates()` (Task 9).

- [ ] **Step 1: Add `lan_only` to `KNOWN_FIELDS`**

Change line 38 from:

```typescript
const KNOWN_FIELDS = new Set(['domain', 'port', 'service', 'icon'])
```

to:

```typescript
const KNOWN_FIELDS = new Set(['domain', 'port', 'service', 'icon', 'lan_only'])
```

- [ ] **Step 2: Read `lan_only` and add cert-lookup state**

After line 76 (`const service = ...`), add:

```typescript
  const lanOnly = Boolean(meta.lan_only)
```

Add a new import at the top (alongside the existing `../api` import block, i.e. add `fetchCaddyCertificates` and `type CaddyCertificate` to the existing `import { ... } from '../api'` list on lines 4-14):

```typescript
  fetchCaddyCertificates,
```

and

```typescript
  type CaddyCertificate,
```

Add new state near the other `useState` declarations (after line 70, `const [iconPickerOpen, setIconPickerOpen] = useState(false)`):

```typescript
  const [certs, setCerts] = useState<CaddyCertificate[]>([])
```

Add a fetch effect near the other top-level `useEffect`s (after the effect at lines 108-114 that resets drafts on `stack.name` change):

```typescript
  useEffect(() => {
    fetchCaddyCertificates()
      .then(setCerts)
      .catch(() => setCerts([]))
  }, [])
```

- [ ] **Step 3: Widen `saveMetadata()`'s patch type**

Change line 116 from:

```typescript
  async function saveMetadata(patch: { icon?: string | null; port?: number | null; domain?: string | null }) {
```

to:

```typescript
  async function saveMetadata(patch: {
    icon?: string | null
    port?: number | null
    domain?: string | null
    service?: string | null
    lan_only?: boolean | null
  }) {
```

- [ ] **Step 4: Make "Proxied service" editable and add "LAN only" + "Cert expires" fields**

Replace the "Proxied service" `<div>` block (lines 309-312):

```typescript
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Proxied service</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{service ?? '—'}</dd>
          </div>
```

with:

```typescript
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Proxied service</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">
              <select
                value={service ?? ''}
                onChange={(e) => saveMetadata({ service: e.target.value || null })}
                className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 outline-none hover:border-neutral-300 focus:border-neutral-400 dark:hover:border-neutral-700 dark:focus:border-neutral-600"
              >
                {stack.services.map((svc) => (
                  <option key={svc} value={svc}>
                    {svc}
                  </option>
                ))}
              </select>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">LAN only</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">
              <input
                type="checkbox"
                checked={lanOnly}
                onChange={(e) => saveMetadata({ lan_only: e.target.checked || null })}
                title="Restrict to private/LAN IP ranges only"
              />
            </dd>
          </div>
```

Add a "Cert expires" block right after the "Services" `<div>` (after line 316, before the `extraFields.map(...)` block):

```typescript
          {(() => {
            const cert = domain ? certs.find((c) => c.domains.includes(domain)) : undefined
            if (!domain || !cert) return null
            return (
              <div>
                <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Cert expires</dt>
                <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">
                  {new Date(cert.expires_at).toLocaleDateString()}
                </dd>
              </div>
            )
          })()}
```

- [ ] **Step 5: Verify**

Run: `cd frontend && npm run build && npm run lint` — expect both to pass.

- [ ] **Step 6: Manual verification**

Open a stack's detail page: confirm "Proxied service" is now a dropdown that saves on change, "LAN only" is a checkbox that saves on change, and (once `https_mode` is on and a cert exists for that stack's domain) "Cert expires" renders a date. Confirm the raw `lan_only: true/false` row that used to appear in the generic extra-fields dump is gone.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/StackDetail.tsx
git commit -m "fix: make service/lan_only editable on the stack detail page, show cert expiry"
```

---

### Task 15: Full verification pass

**Files:** None (verification only).

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend
python3 test_caddy_service.py
python3 test_cert_service.py
python3 test_docker_service.py
python3 test_health_service.py
python3 test_config_service.py
python3 test_auth_service.py
python3 test_icon_service.py
python3 test_stacks_service.py
```

Expected: every file prints `ok`.

- [ ] **Step 2: Run the full frontend build/lint**

```bash
cd frontend
npm run build
npm run lint
```

Expected: both succeed with zero errors.

- [ ] **Step 3: End-to-end manual pass**

```bash
docker compose -f docker-compose.dev.yaml up --build --profile caddy
```

- Set `https_mode: internal` in Settings (or via `PATCH /api/config`) and add a domain to a stack, confirm Caddy issues an internal cert and the TLS Certificates tab shows it with a real expiry date.
- Enable the Access Logs toggle, hit the stack's domain a few times, confirm request lines start appearing in the Access Logs tab (verify the actual `logs` JSON shape Caddy needs was correct — if lines don't appear, check Caddy's own log output via `docker logs litethaus-caddy` for a config-rejection error, and adjust `build_config()`'s `"logs"` value in Task 4 from `{}` to an explicit `{"default_logger_name": ""}` or add a `"logging"` app block with an explicit encoder if needed).
- Confirm the Routes tab's Health/Requests columns update after generating some traffic to a stack's domain.
- Confirm a stopped/never-started stack shows "no traffic yet" rather than an error.
- Open a stack's detail page, confirm service/lan_only edits round-trip and match what's shown in the CaddyPage Routes tab for the same stack.

- [ ] **Step 4: Final commit (if Step 3 required adjustments)**

```bash
git add -A
git commit -m "fix: adjust Caddy access-log config shape based on live testing"
```

(Skip this commit if Step 3 required no code changes.)
