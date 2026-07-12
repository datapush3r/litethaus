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

# Precedence order docker compose itself uses when no -f is given.
COMPOSE_FILENAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")


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
        self._watch_stop_event: threading.Event | None = None

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
            if not entry.is_dir():
                continue
            compose_path = self._find_compose_file(entry)
            if compose_path is None:
                continue
            stacks[entry.name] = self._parse(entry.name, compose_path)

        with self._lock:
            self._stacks = stacks
        return list(stacks.values())

    def _find_compose_file(self, entry: Path) -> Path | None:
        for filename in COMPOSE_FILENAMES:
            candidate = entry / filename
            if candidate.exists():
                return candidate
        return None

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
        # Re-reads self.stacks_dir on every restart, so a config change picked
        # up via restart_watcher() moves the watch to the new directory
        # instead of leaving it stuck watching wherever it started.
        while True:
            stop_event = threading.Event()
            self._watch_stop_event = stop_event
            for _ in watch(self.stacks_dir, recursive=True, stop_event=stop_event):
                self.scan()

    def restart_watcher(self) -> None:
        if self._watch_stop_event is not None:
            self._watch_stop_event.set()


stack_service = StackService()
