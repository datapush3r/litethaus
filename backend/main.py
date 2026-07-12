import asyncio
import threading
from contextlib import aclosing, asynccontextmanager, suppress
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def get_config() -> dict[str, Any]:
    return dict(config_service.load())


CADDY_RELEVANT_KEYS = {"stacks_dir", "https_mode", "acme_email", "caddy_admin_url"}


@app.patch("/config")
def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    old = config_service.load()
    updated = config_service.update(patch)
    if updated.get("stacks_dir") != old.get("stacks_dir"):
        stack_service.scan()
        stack_service.restart_watcher()
    if any(updated.get(k) != old.get(k) for k in CADDY_RELEVANT_KEYS):
        caddy_service.sync(stack_service.list_stacks())
    return dict(updated)


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
def get_stack_raw(name: str) -> dict[str, str]:
    _get_stack(name)
    return {"content": stack_service.read_raw(name)}


@app.put("/stacks/{name}/raw")
def update_stack_raw(name: str, body: dict[str, Any]) -> dict[str, Any]:
    _get_stack(name)
    try:
        stack = stack_service.write_raw(name, str(body["content"]))
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


@app.websocket("/stacks/{name}/logs")
async def stack_logs(websocket: WebSocket, name: str) -> None:
    stacks = {s.name: s for s in stack_service.list_stacks()}
    stack = stacks.get(name)
    if stack is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()

    async def forward_logs() -> None:
        # `docker compose logs -f` exits as soon as there's nothing to tail
        # (stack not up yet, or just stopped) rather than waiting for a
        # container to appear. Re-attach instead of treating that as done,
        # so a client watching a stopped stack picks up logs once it starts.
        while True:
            async with aclosing(docker_service.stream_logs(stack)) as lines:
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
