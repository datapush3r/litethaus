import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config_service import config_service
from stacks_service import stack_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    stack_service.scan()
    threading.Thread(target=stack_service.watch_forever, daemon=True).start()
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
