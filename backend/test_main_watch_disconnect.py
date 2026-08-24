import asyncio

from main import _watch_disconnect


class _FakeWebSocket:
    def __init__(self) -> None:
        self._disconnected = False

    async def receive(self) -> dict:
        if self._disconnected:
            raise RuntimeError('Cannot call "receive" once a disconnect message has been received.')
        self._disconnected = True
        return {"type": "websocket.disconnect", "code": 1000}


def test_watch_disconnect_returns_cleanly_on_single_disconnect_message() -> None:
    asyncio.run(_watch_disconnect(_FakeWebSocket()))


if __name__ == "__main__":
    test_watch_disconnect_returns_cleanly_on_single_disconnect_message()
    print("ok")
