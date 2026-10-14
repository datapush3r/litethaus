import asyncio
import logging
import os
import re
import threading
from contextlib import aclosing, asynccontextmanager, suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from auth_service import SESSION_COOKIE, SESSION_TTL_SECONDS, LockedOutError, auth_service
from caddy_service import caddy_service
from cert_service import cert_service
from config_service import config_service
from docker_service import docker_service
from health_service import health_service
from sensors_service import sensors_service
from stacks_service import stack_service
from terminal_service import terminal_service

_NOISY_ACCESS_LOG_RE = re.compile(r'"(?:GET|HEAD) (?:/stacks(?:/[^/ ]+/status)?|/health|/host/(?:mem|cpu|sensors|disk))(?:\?[^ ]*)? HTTP')


class _SuppressPollingAccessLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _NOISY_ACCESS_LOG_RE.search(record.getMessage())


logging.getLogger("uvicorn.access").addFilter(_SuppressPollingAccessLogs())


async def _watch_disconnect(websocket: WebSocket) -> None:
    with suppress(WebSocketDisconnect):
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(message.get("code", 1000))


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack_service.scan()
    threading.Thread(target=stack_service.watch_forever, daemon=True).start()
    threading.Thread(target=health_service.watch_forever, daemon=True).start()
    caddy_service.sync_with_retry(stack_service.list_stacks())
    yield


app = FastAPI(title="litethaus", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter()

PUBLIC_PATHS = {"/api/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login"}


@app.middleware("http")
async def enforce_auth(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    if path in PUBLIC_PATHS or not auth_service.enabled() or not auth_service.is_configured():
        return await call_next(request)
    if not auth_service.is_valid_session(request.cookies.get(SESSION_COOKIE)):
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    return await call_next(request)


def _set_session_cookie(request: Request, response: Response) -> None:
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        SESSION_COOKIE,
        auth_service.create_session(),
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        secure=secure,
    )


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api.get("/host/mem")
def host_mem() -> dict[str, Any]:
    """Host RAM usage: total bytes (MemTotal) and the % used by all running containers."""
    return {
        "total_bytes": health_service.host_mem_total_bytes() or 0,
        "container_percent": health_service.host_mem_percent(),
    }


@api.get("/host/cpu")
def host_cpu() -> dict[str, Any]:
    """Host CPU usage: core count and the % of all cores used by containers."""
    return {
        "cores": os.cpu_count() or 1,
        "container_percent": health_service.host_cpu_percent(),
    }


@api.get("/host/sensors")
def host_sensors() -> dict[str, Any]:
    """Host hardware sensors (temps, fans, voltages) from kernel sysfs.

    Reports available=false when the container can't see any hwmon/thermal
    data (e.g. an LXC without the host dirs exposed) - the UI hides itself.
    """
    return sensors_service.read()


def host_disk_usage(paths: list[str]) -> list[dict[str, Any]]:
    """df-style usage for each distinct filesystem under the given paths.

    Percent uses df's convention: used / (used + available), not / total -
    so the number matches what `df` prints.
    """
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for p in paths:
        try:
            st = os.stat(p)
            vfs = os.statvfs(p)
        except OSError:
            continue
        if st.st_dev in seen:  # same filesystem mounted twice -> report once
            continue
        seen.add(st.st_dev)
        frsize = vfs.f_frsize
        used = (vfs.f_blocks - vfs.f_bfree) * frsize
        avail = vfs.f_bavail * frsize
        denom = used + avail
        out.append({
            "mount": p,
            "total_bytes": vfs.f_blocks * frsize,
            "used_bytes": used,
            "avail_bytes": avail,
            "percent": round(used / denom * 100, 1) if denom else 0.0,
        })
    return out


@api.get("/host/disk")
def host_disk() -> dict[str, Any]:
    """Disk usage of the root filesystem and the stacks directory."""
    cfg = config_service.load()
    return {"filesystems": host_disk_usage(["/", str(cfg.get("stacks_dir") or "/")])}


@api.get("/auth/status")
def auth_status(request: Request) -> dict[str, bool]:
    if not auth_service.enabled():
        return {"configured": True, "authenticated": True}
    configured = auth_service.is_configured()
    authenticated = (not configured) or auth_service.is_valid_session(request.cookies.get(SESSION_COOKIE))
    return {"configured": configured, "authenticated": authenticated}


@api.post("/auth/setup")
def auth_setup(body: dict[str, Any], request: Request, response: Response) -> dict[str, bool]:
    try:
        auth_service.setup(str(body.get("username", "")), str(body.get("password", "")))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _set_session_cookie(request, response)
    return {"ok": True}


@api.post("/auth/login")
def auth_login(body: dict[str, Any], request: Request, response: Response) -> dict[str, bool]:
    remote_addr = request.client.host if request.client else "unknown"
    try:
        ok = auth_service.verify_login(str(body.get("username", "")), str(body.get("password", "")), remote_addr)
    except LockedOutError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    if not ok:
        raise HTTPException(status_code=401, detail="invalid username or password")
    _set_session_cookie(request, response)
    return {"ok": True}


@api.post("/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, bool]:
    auth_service.revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@api.post("/auth/change-password")
def auth_change_password(body: dict[str, Any]) -> dict[str, bool]:
    try:
        auth_service.change_password(str(body.get("current_password", "")), str(body.get("new_password", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@api.get("/config")
def get_config() -> dict[str, Any]:
    data = dict(config_service.load())
    data.pop("auth", None)
    return data


CADDY_RELEVANT_KEYS = {
    "stacks_dir",
    "https_mode",
    "acme_email",
    "caddy_admin_url",
    "cloudflare_api_token",
    "wildcard_domain",
    "caddy_enabled",
    "caddy_extra_routes_json",
    "caddy_access_log_enabled",
    "caddy_security_headers_enabled",
}


@api.patch("/config")
def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    patch = {k: v for k, v in patch.items() if k != "auth"}
    old = config_service.load()
    updated = config_service.update(patch)
    if updated.get("stacks_dir") != old.get("stacks_dir"):
        stack_service.scan()
        stack_service.restart_watcher()
    if any(updated.get(k) != old.get(k) for k in CADDY_RELEVANT_KEYS):
        caddy_service.sync(stack_service.list_stacks())
    updated = dict(updated)
    updated.pop("auth", None)
    return updated


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***redacted***" if k == "api_token" else _redact_secrets(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_secrets(v) for v in value]
    return value


@api.get("/caddy/status")
def caddy_status() -> dict[str, Any]:
    return caddy_service.status()


@api.get("/caddy/version")
def caddy_version() -> dict[str, Any]:
    return {"version": caddy_service.version()}


@api.post("/caddy/reload")
def caddy_reload() -> dict[str, Any]:
    caddy_service.sync(stack_service.list_stacks())
    return caddy_service.status()


@api.get("/caddy/config")
def caddy_config() -> dict[str, Any]:
    cfg = config_service.load()
    config = caddy_service.build_config(
        stack_service.list_stacks(),
        https_mode=cfg.get("https_mode", "off"),
        acme_email=cfg.get("acme_email", ""),
        cloudflare_api_token=cfg.get("cloudflare_api_token", ""),
        wildcard_domain=cfg.get("wildcard_domain", ""),
        extra_routes_json=cfg.get("caddy_extra_routes_json", ""),
        access_log_enabled=cfg.get("caddy_access_log_enabled", False),
        security_headers_enabled=cfg.get("caddy_security_headers_enabled", False),
    )
    return _redact_secrets(config)


@api.get("/caddy/live")
def caddy_live() -> dict[str, Any]:
    try:
        config = caddy_service.fetch_live_config()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Caddy unreachable: {exc}")
    return _redact_secrets(config)


@api.get("/caddy/upstreams")
def caddy_upstreams() -> list[dict[str, Any]]:
    try:
        return caddy_service.fetch_upstreams()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Caddy unreachable: {exc}")


@api.get("/caddy/certificates")
def caddy_certificates() -> list[dict[str, Any]]:
    try:
        return cert_service.list_certificates()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Caddy unreachable: {exc}")


@api.get("/stacks")
def list_stacks() -> list[dict[str, Any]]:
    return [asdict(s) for s in stack_service.list_stacks()]


def _get_stack(name: str):
    stacks = {s.name: s for s in stack_service.list_stacks()}
    if name not in stacks:
        raise HTTPException(status_code=404, detail="stack not found")
    return stacks[name]


@api.post("/stacks")
def create_stack(body: dict[str, Any]) -> dict[str, Any]:
    try:
        stack = stack_service.create_stack(str(body["name"]), str(body["content"]))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    caddy_service.sync(stack_service.list_stacks())
    return asdict(stack)


@api.get("/stacks/{name}/raw")
def get_stack_raw(name: str, file: str | None = None) -> dict[str, str]:
    _get_stack(name)
    try:
        return {"content": stack_service.read_raw(name, file)}
    except KeyError:
        raise HTTPException(status_code=404, detail="file not found")


@api.put("/stacks/{name}/raw")
def update_stack_raw(name: str, body: dict[str, Any]) -> dict[str, Any]:
    _get_stack(name)
    try:
        stack = stack_service.write_raw(name, str(body["content"]), body.get("file"))
    except KeyError:
        raise HTTPException(status_code=404, detail="file not found")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    caddy_service.sync(stack_service.list_stacks())
    return asdict(stack)


@api.patch("/stacks/{name}/metadata")
def update_stack_metadata(name: str, body: dict[str, Any]) -> dict[str, Any]:
    _get_stack(name)
    allowed = {"icon", "port", "domain", "service", "favorite", "lan_only", "passive_health_check", "auto_update"}
    patch = {k: v for k, v in body.items() if k in allowed}
    try:
        stack = stack_service.update_metadata(name, patch)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    caddy_service.sync(stack_service.list_stacks())
    return asdict(stack)


@api.delete("/stacks/{name}")
def remove_stack(name: str) -> dict[str, bool]:
    stack = _get_stack(name)
    if docker_service.container_status(stack) != "stopped":
        raise HTTPException(status_code=409, detail="stop the stack before deleting it")
    stack_service.delete_stack(name)
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": True}


@api.get("/stacks/{name}/status")
def stack_status(name: str) -> dict[str, Any]:
    details = docker_service.container_details(_get_stack(name))
    return {
        "status": docker_service.status_from_details(details),
        "health": docker_service.summarize_health(details),
        "containers": details,
        "update_available": health_service.update_available(name),
        "stats": health_service.container_stats(name),
    }


@api.get("/stacks/{name}/health-log")
def stack_health_log(name: str) -> list[dict[str, str]]:
    _get_stack(name)
    return health_service.health_log(name)


@api.post("/stacks/{name}/up")
def stack_up(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_up(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@api.post("/stacks/{name}/down")
def stack_down(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_down(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@api.post("/stacks/{name}/restart")
def stack_restart(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_restart(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@api.post("/stacks/{name}/update")
def stack_update(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_update(_get_stack(name))
    if ok:
        health_service.clear_update_flag(name)
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@api.post("/updates/run-now")
def run_updates_now() -> dict[str, Any]:
    results = health_service.run_auto_updates_now()
    caddy_service.sync(stack_service.list_stacks())
    return {"results": results}


@api.post("/updates/auto-update-all")
def set_auto_update_all(body: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(body.get("enabled"))
    names = [
        s.name for s in stack_service.list_stacks() if not s.error and docker_service.container_status(s) == "running"
    ]
    stack_service.update_metadata_bulk(names, {"auto_update": enabled or None})
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": True, "count": len(names)}


app.include_router(api, prefix="/api")


@app.websocket("/api/stacks/{name}/logs")
async def stack_logs(websocket: WebSocket, name: str, container: str | None = None) -> None:
    if auth_service.enabled() and auth_service.is_configured() and not auth_service.is_valid_session(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4401)
        return

    stacks = {s.name: s for s in stack_service.list_stacks()}
    stack = stacks.get(name)
    if stack is None:
        await websocket.close(code=4004)
        return

    if container is not None and docker_service.find_container(stack, container) is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    seen_errors: set[str] = set()

    async def forward_logs() -> None:
        while True:
            async with aclosing(docker_service.stream_logs(stack, container)) as lines:
                async for line in lines:
                    # ponytail: dedupe by exact line text; compose errors repeat verbatim.
                    if "Error" in line and line in seen_errors:
                        continue
                    if "Error" in line:
                        seen_errors.add(line)
                    await websocket.send_text(line)
            await asyncio.sleep(1)

    forward_task = asyncio.create_task(forward_logs())
    disconnect_task = asyncio.create_task(_watch_disconnect(websocket))
    done, pending = await asyncio.wait({forward_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    for task in done:
        with suppress(WebSocketDisconnect):
            task.result()


@app.websocket("/api/stacks/{name}/terminal")
async def stack_terminal(websocket: WebSocket, name: str, container: str) -> None:
    if auth_service.enabled() and auth_service.is_configured() and not auth_service.is_valid_session(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4401)
        return

    stacks = {s.name: s for s in stack_service.list_stacks()}
    stack = stacks.get(name)
    if stack is None:
        await websocket.close(code=4004)
        return

    target = docker_service.find_container(stack, container)
    if target is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    session = terminal_service.get_or_create(target.name)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_data(data: bytes) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, data)

    backlog = session.subscribe(on_data)
    if backlog:
        await websocket.send_bytes(backlog)

    async def pump_output() -> None:
        while True:
            await websocket.send_bytes(await queue.get())

    async def pump_input() -> None:
        with suppress(WebSocketDisconnect):
            while True:
                data = await websocket.receive_bytes()
                await loop.run_in_executor(None, session.write, data)

    output_task = asyncio.create_task(pump_output())
    input_task = asyncio.create_task(pump_input())
    done, pending = await asyncio.wait({output_task, input_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    session.unsubscribe(on_data)


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

    forward_task = asyncio.create_task(forward_logs())
    disconnect_task = asyncio.create_task(_watch_disconnect(websocket))
    done, pending = await asyncio.wait({forward_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    for task in done:
        with suppress(WebSocketDisconnect):
            task.result()


STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.is_dir():

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
