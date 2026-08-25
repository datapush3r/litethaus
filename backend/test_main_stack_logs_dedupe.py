import asyncio
from dataclasses import dataclass, field
from typing import Any

import main


@dataclass
class _FakeWebSocket:
    sent: list[str] = field(default_factory=list)
    disconnects: int = 0

    async def close(self, code: int = 1000) -> None:
        self.disconnects += 1

    async def accept(self) -> None:
        pass

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def receive(self) -> dict[str, Any]:
        # Signal disconnect immediately; the handler waits for forward/disconnect tasks.
        return {"type": "websocket.disconnect", "code": 1000}


async def _run_stack_logs(lines: list[str], monkeypatch) -> list[str]:
    ws = _FakeWebSocket()

    async def fake_stream_logs(stack, container=None):
        for line in lines:
            yield line
        # Simulate the process dying (compose error case); the handler loops.

    class _Stacks:
        def list_stacks(self):
            from stacks_service import Stack

            return [Stack(name="plex", path="/tmp/plex")]

    monkeypatch.setattr(main.auth_service, "enabled", lambda: False)
    monkeypatch.setattr(main.stack_service, "list_stacks", _Stacks().list_stacks)
    monkeypatch.setattr(main.docker_service, "stream_logs", fake_stream_logs)

    # Give the forward loop one pass before the disconnect task wins the race.
    await asyncio.sleep(0.05)
    await main.stack_logs(ws, name="plex")
    return ws.sent


def test_compose_error_lines_are_deduped_per_connection(monkeypatch) -> None:
    sent = asyncio.run(_run_stack_logs(
        [
            "Error response from daemon: invalid compose file",
            "Error response from daemon: invalid compose file",
            "some normal log line",
            "some normal log line",
            "Error response from daemon: a different failure",
        ],
        monkeypatch,
    ))
    assert sent == [
        "Error response from daemon: invalid compose file",
        "some normal log line",
        "some normal log line",
        "Error response from daemon: a different failure",
    ]



