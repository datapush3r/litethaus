import os
import time
from unittest.mock import Mock, patch

from terminal_service import TerminalService


def _fake_exec_shell(container_name: str):
    # Stands in for docker_service.exec_shell(): a real pty pair we can
    # write to/read from directly, plus a Popen-shaped mock (only .wait()
    # is used by TerminalSession, once the pty hits EOF).
    master_fd, slave_fd = os.openpty()
    process = Mock()
    process.wait = Mock()
    return master_fd, slave_fd, process


def test_reconnect_reuses_session_and_replays_scrollback() -> None:
    master_fd, slave_fd, process = _fake_exec_shell("c1")
    with patch("terminal_service.docker_service.exec_shell", return_value=(master_fd, process)):
        svc = TerminalService()
        session = svc.get_or_create("c1")
        assert svc.get_or_create("c1") is session  # reused, not respawned

        os.write(slave_fd, b"hello\n")
        time.sleep(0.05)  # let the background pump thread drain the pty

        received: list[bytes] = []
        backlog = session.subscribe(received.append)
        assert backlog == b"hello\r\n"  # pty output processing turns \n into \r\n

        os.write(slave_fd, b"world\n")
        time.sleep(0.05)
        assert received == [b"world\r\n"]

    os.close(slave_fd)


def test_session_reopens_after_shell_exits() -> None:
    master_fd, slave_fd, process = _fake_exec_shell("c2")
    with patch("terminal_service.docker_service.exec_shell", return_value=(master_fd, process)):
        svc = TerminalService()
        first = svc.get_or_create("c2")
        os.close(slave_fd)  # pty EOF - shell "exited"
        time.sleep(0.05)
        assert first.closed

        master_fd2, slave_fd2, process2 = _fake_exec_shell("c2")
        with patch("terminal_service.docker_service.exec_shell", return_value=(master_fd2, process2)):
            second = svc.get_or_create("c2")
        assert second is not first
    os.close(slave_fd2)


if __name__ == "__main__":
    test_reconnect_reuses_session_and_replays_scrollback()
    test_session_reopens_after_shell_exits()
    print("ok")
