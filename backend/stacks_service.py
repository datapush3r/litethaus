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
from icon_service import icon_service

logger = logging.getLogger(__name__)

_yaml = YAML()
_yaml_lock = threading.Lock()


def _yaml_load(stream: Any) -> Any:
    with _yaml_lock:
        return _yaml.load(stream)


def _yaml_dump(data: Any, stream: Any) -> None:
    with _yaml_lock:
        _yaml.dump(data, stream)


COMPOSE_FILENAMES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
DEFAULT_COMPOSE_FILENAME = COMPOSE_FILENAMES[0]
STACK_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
METADATA_FILENAME = ".litethaus.yaml"


def _override_candidates(primary_filename: str) -> tuple[str, ...]:
    family = "docker-compose" if primary_filename.startswith("docker-compose") else "compose"
    return (f"{family}.override.yaml", f"{family}.override.yml")


def _image_basename(image: str) -> str:
    image = image.split("@", 1)[0]
    last_segment = image.rsplit("/", 1)[-1]
    return last_segment.split(":", 1)[0]


def _icon_candidates(name: str, data: dict[str, Any]) -> list[str]:
    services = data.get("services") or {}
    candidates: list[str] = []
    for svc in services.values():
        image = (svc or {}).get("image")
        if image:
            candidates.append(_image_basename(str(image)))
    candidates.append(name)
    candidates.extend(services.keys())
    return candidates


@dataclass
class Stack:
    name: str
    path: str
    x_litethaus: dict[str, Any] = field(default_factory=dict)
    services: list[str] = field(default_factory=list)
    error: str | None = None
    compose_files: list[str] = field(default_factory=list)
    override_file: str | None = None


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
            try:
                compose_paths = self._find_compose_files(entry)
                if not compose_paths:
                    continue
                override_path = self._find_override_file(entry, compose_paths[0].name)
                stacks[entry.name] = self._parse(entry.name, compose_paths, override_path)
            except OSError:
                logger.warning("Skipping unreadable stack dir %s", entry, exc_info=True)

        for stack in stacks.values():
            self._backfill_icon(stack)

        with self._lock:
            self._stacks = stacks
        return list(stacks.values())

    def _guess_icon(self, name: str, data: dict[str, Any]) -> str | None:
        if not config_service.load().get("auto_icon_enabled", True):
            return None
        return icon_service.guess(_icon_candidates(name, data))

    def _read_metadata_node(self, meta_path: Path) -> Any:
        if not meta_path.exists():
            return {}
        with meta_path.open("r") as f:
            return _yaml_load(f) or {}

    def _read_metadata_file(self, meta_path: Path) -> dict[str, Any]:
        try:
            return dict(self._read_metadata_node(meta_path))
        except Exception:
            return {}

    def _atomic_write_yaml(self, path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w") as f:
            _yaml_dump(data, f)
        tmp.replace(path)

    def _backfill_icon(self, stack: Stack) -> None:
        if stack.error is not None or "icon" in stack.x_litethaus:
            return
        compose_path = Path(stack.path)
        try:
            with compose_path.open("r") as f:
                data = _yaml_load(f) or {}
        except Exception:
            return
        guessed = self._guess_icon(stack.name, data)
        if not guessed:
            return
        meta_path = compose_path.parent / METADATA_FILENAME
        try:
            meta = self._read_metadata_node(meta_path)
            meta["icon"] = guessed
            self._atomic_write_yaml(meta_path, meta)
        except Exception:
            logger.exception("Failed to backfill icon for %s", stack.name)
            return
        stack.x_litethaus = dict(meta)

    def _find_compose_files(self, entry: Path) -> list[Path]:
        return [entry / filename for filename in COMPOSE_FILENAMES if (entry / filename).exists()]

    def _find_override_file(self, entry: Path, primary_filename: str) -> Path | None:
        for filename in _override_candidates(primary_filename):
            candidate = entry / filename
            if candidate.exists():
                return candidate
        return None

    def _parse(self, name: str, compose_paths: list[Path], override_path: Path | None) -> Stack:
        compose_path = compose_paths[0]
        compose_files = [compose_path.name] + ([override_path.name] if override_path else []) + [
            p.name for p in compose_paths[1:]
        ]
        override_file = override_path.name if override_path else None
        try:
            with compose_path.open("r") as f:
                data = _yaml_load(f) or {}
            meta_path = compose_path.parent / METADATA_FILENAME
            if meta_path.exists():
                x_litethaus = self._read_metadata_file(meta_path)
            elif data.get("x-litethaus"):
                embedded = data["x-litethaus"]
                self._atomic_write_yaml(meta_path, embedded)
                x_litethaus = dict(embedded)
                del data["x-litethaus"]
                self._atomic_write_yaml(compose_path, data)
            else:
                x_litethaus = {}
            return Stack(
                name=name,
                path=str(compose_path),
                x_litethaus=x_litethaus,
                services=list((data.get("services") or {}).keys()),
                compose_files=compose_files,
                override_file=override_file,
            )
        except Exception as exc:
            logger.exception("Failed to parse %s", compose_path)
            return Stack(
                name=name, path=str(compose_path), error=str(exc), compose_files=compose_files, override_file=override_file
            )

    def list_stacks(self) -> list[Stack]:
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

    def update_metadata(self, name: str, patch: dict[str, Any]) -> Stack:
        self._write_metadata_file(name, patch)
        self.scan()
        return self._require(name)

    def update_metadata_bulk(self, names: list[str], patch: dict[str, Any]) -> list[Stack]:
        for name in names:
            self._write_metadata_file(name, patch)
        self.scan()
        return [self._require(name) for name in names]

    def _write_metadata_file(self, name: str, patch: dict[str, Any]) -> None:
        meta_path = Path(self._require(name).path).parent / METADATA_FILENAME
        meta = self._read_metadata_node(meta_path)
        for key, value in patch.items():
            if value is None:
                meta.pop(key, None)
            else:
                meta[key] = value
        self._atomic_write_yaml(meta_path, meta)

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
        _yaml_load(content)

    def _watch_paths(self) -> list[Path]:
        stacks_dir = self.stacks_dir
        return [stacks_dir] + [d for d in stacks_dir.iterdir() if d.is_dir()]

    def watch_forever(self) -> None:
        while True:
            stop_event = threading.Event()
            self._watch_stop_event = stop_event
            for _ in watch(*self._watch_paths(), recursive=False, stop_event=stop_event):
                self.scan()
                break

    def restart_watcher(self) -> None:
        if self._watch_stop_event is not None:
            self._watch_stop_event.set()


stack_service = StackService()
