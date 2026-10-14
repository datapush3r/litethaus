import logging

from main import _SuppressPollingAccessLogs

_FILTER = _SuppressPollingAccessLogs()


def _record(method: str, path: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("1.2.3.4:1", method, path, "1.1", 200),
        exc_info=None,
    )


def test_suppresses_status_polling_and_health() -> None:
    assert _FILTER.filter(_record("GET", "/stacks")) is False
    assert _FILTER.filter(_record("GET", "/stacks/foo/status")) is False
    assert _FILTER.filter(_record("GET", "/health")) is False
    assert _FILTER.filter(_record("GET", "/host/mem")) is False
    assert _FILTER.filter(_record("GET", "/host/cpu")) is False
    assert _FILTER.filter(_record("GET", "/host/sensors")) is False


def test_keeps_real_traffic() -> None:
    assert _FILTER.filter(_record("POST", "/stacks/foo/up")) is True
    assert _FILTER.filter(_record("GET", "/stacks/foo/health-log")) is True
    assert _FILTER.filter(_record("DELETE", "/stacks/foo")) is True


if __name__ == "__main__":
    test_suppresses_status_polling_and_health()
    test_keeps_real_traffic()
    print("ok")
