import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from caddy_service import caddy_service
from config_service import config_service
from docker_service import docker_service
from stacks_service import stack_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack_service.scan()
    threading.Thread(target=stack_service.watch_forever, daemon=True).start()
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


@app.patch("/config")
def update_config(patch: dict[str, Any]) -> dict[str, Any]:
    return dict(config_service.update(patch))


@app.get("/stacks")
def list_stacks() -> list[dict[str, Any]]:
    return [asdict(s) for s in stack_service.list_stacks()]


def _get_stack(name: str):
    stacks = {s.name: s for s in stack_service.list_stacks()}
    if name not in stacks:
        raise HTTPException(status_code=404, detail="stack not found")
    return stacks[name]


@app.get("/stacks/{name}/status")
def stack_status(name: str) -> dict[str, str]:
    return {"status": docker_service.container_status(_get_stack(name))}


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
