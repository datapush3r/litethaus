import os
import threading
from typing import Callable

from docker_service import docker_service

SCROLLBACK_BYTES = 64 * 1024


class TerminalSession:
    def __init__(self, container_name: str) -> None:
        self.master_fd, self.process = docker_service.exec_shell(container_name)
        self.closed = False
        self._scrollback = bytearray()
        self._lock = threading.Lock()
        self._subscribers: set[Callable[[bytes], None]] = set()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        while True:
            try:
                data = os.read(self.master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            with self._lock:
                self._scrollback = (self._scrollback + data)[-SCROLLBACK_BYTES:]
                subscribers = list(self._subscribers)
            for on_data in subscribers:
                on_data(data)
        self.closed = True
        self.process.wait()

    def subscribe(self, on_data: Callable[[bytes], None]) -> bytes:
        with self._lock:
            self._subscribers.add(on_data)
            return bytes(self._scrollback)

    def unsubscribe(self, on_data: Callable[[bytes], None]) -> None:
        with self._lock:
            self._subscribers.discard(on_data)

    def write(self, data: bytes) -> None:
        os.write(self.master_fd, data)


class TerminalService:
    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, container_name: str) -> TerminalSession:
        with self._lock:
            session = self._sessions.get(container_name)
            if session is None or session.closed:
                session = TerminalSession(container_name)
                self._sessions[container_name] = session
            return session


terminal_service = TerminalService()
