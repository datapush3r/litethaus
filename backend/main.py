from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config_service import config_service

app = FastAPI(title="litethaus")

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
