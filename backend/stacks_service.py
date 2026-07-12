import logging
import re
import shutil
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
DEFAULT_COMPOSE_FILENAME = COMPOSE_FILENAMES[0]
STACK_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class Stack:
    name: str
    path: str
    x_litethaus: dict[str, Any] = field(default_factory=dict)
    services: list[str] = field(default_factory=list)
    error: str | None = None
    # Every compose-named file found in the stack's directory, in docker
    # compose's own precedence order - path/x_litethaus/services are always
    # parsed from compose_files[0], the rest are only exposed for editing.
    compose_files: list[str] = field(default_factory=list)


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
            compose_paths = self._find_compose_files(entry)
            if not compose_paths:
                continue
            stacks[entry.name] = self._parse(entry.name, compose_paths)

        with self._lock:
            self._stacks = stacks
        return list(stacks.values())

    def _find_compose_files(self, entry: Path) -> list[Path]:
        return [entry / filename for filename in COMPOSE_FILENAMES if (entry / filename).exists()]

    def _parse(self, name: str, compose_paths: list[Path]) -> Stack:
        compose_path = compose_paths[0]
        compose_files = [p.name for p in compose_paths]
        try:
            with compose_path.open("r") as f:
                data = _yaml.load(f) or {}
            return Stack(
                name=name,
                path=str(compose_path),
                x_litethaus=dict(data.get("x-litethaus") or {}),
                services=list((data.get("services") or {}).keys()),
                compose_files=compose_files,
            )
        except Exception as exc:
            logger.exception("Failed to parse %s", compose_path)
            return Stack(name=name, path=str(compose_path), error=str(exc), compose_files=compose_files)

    def list_stacks(self) -> list[Stack]:
        # scan() takes self._lock itself, so it must never be called while
        # already holding it (threading.Lock isn't reentrant) - do the
        # empty-cache check and release the lock first.
        with self._lock:
            has_scanned = bool(self._stacks)
            stacks = list(self._stacks.values())
        if not has_scanned:
            return self.scan()
        return stacks

    def read_raw(self, name: str, filename: str | None = None) -> str:
        return self._resolve_file(self._require(name), filename).read_text()

    def write_raw(self, name: str, content: str, filename: str | None = None) -> Stack:
        path = self._resolve_file(self._require(name), filename)
        self._validate_yaml(content)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        tmp.replace(path)
        self.scan()
        return self._require(name)

    def _resolve_file(self, stack: Stack, filename: str | None) -> Path:
        if filename is None:
            return Path(stack.path)
        if filename not in stack.compose_files:
            raise KeyError(filename)
        return Path(stack.path).parent / filename

    def create_stack(self, name: str, content: str) -> Stack:
        if not STACK_NAME_RE.match(name):
            raise ValueError("stack name must be alphanumeric (dashes/underscores allowed)")
        stack_dir = self.stacks_dir / name
        if stack_dir.exists():
            raise ValueError(f"stack {name!r} already exists")
        self._validate_yaml(content)
        stack_dir.mkdir(parents=True)
        (stack_dir / DEFAULT_COMPOSE_FILENAME).write_text(content)
        self.scan()
        return self._require(name)

    def delete_stack(self, name: str) -> None:
        shutil.rmtree(Path(self._require(name).path).parent)
        self.scan()

    def _require(self, name: str) -> Stack:
        stacks = {s.name: s for s in self.list_stacks()}
        if name not in stacks:
            raise KeyError(name)
        return stacks[name]

    def _validate_yaml(self, content: str) -> None:
        _yaml.load(content)

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
