import asyncio
import os
import threading
from contextlib import aclosing, asynccontextmanager, suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from auth_service import SESSION_COOKIE, SESSION_TTL_SECONDS, auth_service
from caddy_service import caddy_service
from config_service import config_service
from docker_service import docker_service
from health_service import health_service
from stacks_service import stack_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack_service.scan()
    threading.Thread(target=stack_service.watch_forever, daemon=True).start()
    threading.Thread(target=health_service.watch_forever, daemon=True).start()
    caddy_service.sync(stack_service.list_stacks())
    yield


app = FastAPI(title="litethaus", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_PATHS = {"/health", "/auth/status", "/auth/setup", "/auth/login"}


@app.middleware("http")
async def enforce_auth(request: Request, call_next):
    # In production the built frontend and the API are served from the same
    # origin, with the frontend calling "/api/*" (matching its dev-time Vite
    # proxy rewrite - see vite.config.ts). Requests outside "/api/" are static
    # SPA assets and always pass through untouched; "/api/*" gets the prefix
    # stripped before routing so the existing handlers below (registered
    # without the prefix) don't need to change.
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    request.scope["path"] = path[len("/api") :] or "/"

    # Open by default until a password is actually set (first-run UX, like
    # most self-hosted dashboards) or while auth_enabled is set to false in
    # config.yaml (local testing); once configured, everything except the
    # small public/auth surface requires a valid session cookie.
    if request.scope["path"] in PUBLIC_PATHS or not auth_service.enabled() or not auth_service.is_configured():
        return await call_next(request)
    if not auth_service.is_valid_session(request.cookies.get(SESSION_COOKIE)):
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    return await call_next(request)


def _set_session_cookie(response: Response) -> None:
    response.set_cookie(
        SESSION_COOKIE, auth_service.create_session(), httponly=True, samesite="lax", max_age=SESSION_TTL_SECONDS
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/auth/status")
def auth_status(request: Request) -> dict[str, bool]:
    if not auth_service.enabled():
        return {"configured": True, "authenticated": True}
    configured = auth_service.is_configured()
    authenticated = (not configured) or auth_service.is_valid_session(request.cookies.get(SESSION_COOKIE))
    return {"configured": configured, "authenticated": authenticated}


@app.post("/auth/setup")
def auth_setup(body: dict[str, Any], response: Response) -> dict[str, bool]:
    try:
        auth_service.setup(str(body.get("username", "")), str(body.get("password", "")))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    _set_session_cookie(response)
    return {"ok": True}


@app.post("/auth/login")
def auth_login(body: dict[str, Any], response: Response) -> dict[str, bool]:
    if not auth_service.verify_login(str(body.get("username", "")), str(body.get("password", ""))):
        raise HTTPException(status_code=401, detail="invalid username or password")
    _set_session_cookie(response)
    return {"ok": True}


@app.post("/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, bool]:
    auth_service.revoke_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.post("/auth/change-password")
def auth_change_password(body: dict[str, Any]) -> dict[str, bool]:
    try:
        auth_service.change_password(str(body.get("current_password", "")), str(body.get("new_password", "")))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True}


@app.get("/config")
def get_config() -> dict[str, Any]:
    data = dict(config_service.load())
    data.pop("auth", None)
    return data


CADDY_RELEVANT_KEYS = {"stacks_dir", "https_mode", "acme_email", "caddy_admin_url", "cloudflare_api_token", "wildcard_domain", "caddy_enabled"}


@app.patch("/config")
def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    # auth credentials only ever change through the dedicated /auth endpoints,
    # which hash the password before it touches config.yaml.
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


@app.get("/stacks")
def list_stacks() -> list[dict[str, Any]]:
    return [asdict(s) for s in stack_service.list_stacks()]


def _get_stack(name: str):
    stacks = {s.name: s for s in stack_service.list_stacks()}
    if name not in stacks:
        raise HTTPException(status_code=404, detail="stack not found")
    return stacks[name]


@app.post("/stacks")
def create_stack(body: dict[str, Any]) -> dict[str, Any]:
    try:
        stack = stack_service.create_stack(str(body["name"]), str(body["content"]))
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    caddy_service.sync(stack_service.list_stacks())
    return asdict(stack)


@app.get("/stacks/{name}/raw")
def get_stack_raw(name: str, file: str | None = None) -> dict[str, str]:
    _get_stack(name)
    try:
        return {"content": stack_service.read_raw(name, file)}
    except KeyError:
        raise HTTPException(status_code=404, detail="file not found")


@app.put("/stacks/{name}/raw")
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


@app.patch("/stacks/{name}/metadata")
def update_stack_metadata(name: str, body: dict[str, Any]) -> dict[str, Any]:
    _get_stack(name)
    allowed = {"icon", "port", "domain", "service", "favorite"}
    patch = {k: v for k, v in body.items() if k in allowed}
    try:
        stack = stack_service.update_metadata(name, patch)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    caddy_service.sync(stack_service.list_stacks())
    return asdict(stack)


@app.delete("/stacks/{name}")
def remove_stack(name: str) -> dict[str, bool]:
    stack = _get_stack(name)
    if docker_service.container_status(stack) != "stopped":
        raise HTTPException(status_code=409, detail="stop the stack before deleting it")
    stack_service.delete_stack(name)
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": True}


@app.get("/stacks/{name}/status")
def stack_status(name: str) -> dict[str, Any]:
    details = docker_service.container_details(_get_stack(name))
    return {
        "status": docker_service.status_from_details(details),
        "health": docker_service.summarize_health(details),
        "containers": details,
    }


@app.post("/stacks/{name}/up")
def stack_up(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_up(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@app.post("/stacks/{name}/down")
def stack_down(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_down(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@app.post("/stacks/{name}/restart")
def stack_restart(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_restart(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@app.post("/stacks/{name}/update")
def stack_update(name: str) -> dict[str, Any]:
    ok, output = docker_service.compose_update(_get_stack(name))
    caddy_service.sync(stack_service.list_stacks())
    return {"ok": ok, "output": output}


@app.websocket("/api/stacks/{name}/logs")
async def stack_logs(websocket: WebSocket, name: str, container: str | None = None) -> None:
    # HTTP middleware doesn't run for websocket connections, so the session
    # cookie (sent automatically on the same-origin upgrade request) needs
    # its own check here.
    if auth_service.enabled() and auth_service.is_configured() and not auth_service.is_valid_session(websocket.cookies.get(SESSION_COOKIE)):
        await websocket.close(code=4401)
        return

    stacks = {s.name: s for s in stack_service.list_stacks()}
    stack = stacks.get(name)
    if stack is None:
        await websocket.close(code=4004)
        return

    # `container`, when given, must resolve to an actual container of this
    # stack - not trusted as a raw `docker logs` target.
    if container is not None and docker_service.find_container(stack, container) is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    async def forward_logs() -> None:
        # `docker compose logs -f`/`docker logs -f` exit as soon as there's
        # nothing to tail (stack not up yet, or just stopped) rather than
        # waiting for a container to appear. Re-attach instead of treating
        # that as done, so a client watching a stopped stack picks up logs
        # once it starts.
        while True:
            async with aclosing(docker_service.stream_logs(stack, container)) as lines:
                async for line in lines:
                    await websocket.send_text(line)
            await asyncio.sleep(1)

    async def watch_disconnect() -> None:
        # A client that only receives (never sends) leaves us blocked on the
        # next docker log line forever unless we watch for the disconnect
        # frame concurrently instead of discovering it lazily on send.
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

    # `container` must resolve to an actual container of this stack - not
    # trusted as a raw docker exec target.
    target = docker_service.find_container(stack, container)
    if target is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    master_fd, process = docker_service.exec_shell(target.name)
    loop = asyncio.get_event_loop()

    async def pump_output() -> None:
        while True:
            try:
                data = await loop.run_in_executor(None, os.read, master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            await websocket.send_bytes(data)

    async def pump_input() -> None:
        with suppress(WebSocketDisconnect):
            while True:
                data = await websocket.receive_bytes()
                await loop.run_in_executor(None, os.write, master_fd, data)

    output_task = asyncio.create_task(pump_output())
    input_task = asyncio.create_task(pump_input())
    done, pending = await asyncio.wait({output_task, input_task}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    process.terminate()
    os.close(master_fd)


# Built frontend assets (backend/Dockerfile copies the Vite `dist/` build
# here). Absent in dev (`uvicorn --reload`, no build step), so this route is
# simply never registered there. Registered last so every "/api/*" route
# above always matches first.
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.is_dir():

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
