import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from watchfiles import watch

from config_service import config_service

logger = logging.getLogger(__name__)

_yaml = YAML()


@dataclass
class Stack:
    name: str
    path: str
    x_litethaus: dict[str, Any] = field(default_factory=dict)
    services: list[str] = field(default_factory=list)
    error: str | None = None


class StackService:
    def __init__(self, stacks_dir: Path | None = None) -> None:
        self._stacks_dir_override = stacks_dir
        self._lock = threading.Lock()
        self._stacks: dict[str, Stack] = {}

    @property
    def stacks_dir(self) -> Path:
        if self._stacks_dir_override is not None:
            return self._stacks_dir_override
        return Path(config_service.load()["stacks_dir"])

    def scan(self) -> list[Stack]:
        stacks_dir = self.stacks_dir
        stacks_dir.mkdir(parents=True, exist_ok=True)

        stacks: dict[str, Stack] = {}
        for entry in sorted(stacks_dir.iterdir()):
            compose_path = entry / "docker-compose.yaml"
            if not entry.is_dir() or not compose_path.exists():
                continue
            stacks[entry.name] = self._parse(entry.name, compose_path)

        with self._lock:
            self._stacks = stacks
        return list(stacks.values())

    def _parse(self, name: str, compose_path: Path) -> Stack:
        try:
            with compose_path.open("r") as f:
                data = _yaml.load(f) or {}
            return Stack(
                name=name,
                path=str(compose_path),
                x_litethaus=dict(data.get("x-litethaus") or {}),
                services=list((data.get("services") or {}).keys()),
            )
        except Exception as exc:
            logger.exception("Failed to parse %s", compose_path)
            return Stack(name=name, path=str(compose_path), error=str(exc))

    def list_stacks(self) -> list[Stack]:
        with self._lock:
            if not self._stacks:
                return self.scan()
            return list(self._stacks.values())

    def watch_forever(self) -> None:
        for _ in watch(self.stacks_dir, recursive=True):
            self.scan()


stack_service = StackService()
