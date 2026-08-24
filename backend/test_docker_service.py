import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from config_service import ConfigService
from docker_service import DockerService
from stacks_service import Stack


def _svc(overrides: dict[str, object] | None = None) -> DockerService:
    config = ConfigService(Path(tempfile.mkdtemp()) / "config.yaml")
    if overrides:
        config.update(overrides)
    return DockerService(config=config)


class _RecordingContainers:
    """Stand-in for docker-py's client.containers - records what filters/
    names it was called with instead of hitting a real Docker daemon."""

    def __init__(self, list_result: list | None = None, get_result: object | None = None) -> None:
        self.list_calls: list[dict | None] = []
        self.get_calls: list[str] = []
        self._list_result = list_result or []
        self._get_result = get_result

    def list(self, filters: dict | None = None) -> list:
        self.list_calls.append(filters)
        return self._list_result

    def get(self, name: str) -> object:
        self.get_calls.append(name)
        if self._get_result is None:
            from docker.errors import NotFound
            raise NotFound(name)
        return self._get_result


def test_compose_cmd_uses_project_name_and_compose_file() -> None:
    stack = Stack(name="example", path="/config/stacks/example/docker-compose.yaml")
    svc = _svc()

    assert svc._compose_cmd(stack, "up", "-d") == [
        "docker",
        "compose",
        "-p",
        "example",
        "-f",
        stack.path,
        "up",
        "-d",
    ]
    assert svc._compose_cmd(stack, "logs", "-f", "--no-color", "--tail", "100") == [
        "docker",
        "compose",
        "-p",
        "example",
        "-f",
        stack.path,
        "logs",
        "-f",
        "--no-color",
        "--tail",
        "100",
    ]


def test_compose_cmd_adds_override_file_when_present() -> None:
    stack = Stack(
        name="example",
        path="/config/stacks/example/compose.yaml",
        override_file="compose.override.yaml",
    )
    svc = _svc()

    assert svc._compose_cmd(stack, "up", "-d") == [
        "docker",
        "compose",
        "-p",
        "example",
        "-f",
        stack.path,
        "-f",
        "/config/stacks/example/compose.override.yaml",
        "up",
        "-d",
    ]


def test_status_from_details() -> None:
    assert DockerService.status_from_details([]) == "stopped"
    running = {"name": "a", "state": "running", "health": None, "restart_count": 0}
    exited = {"name": "b", "state": "exited", "health": None, "restart_count": 0}
    assert DockerService.status_from_details([running]) == "running"
    assert DockerService.status_from_details([exited]) == "stopped"
    assert DockerService.status_from_details([running, exited]) == "partial"


def test_summarize_health_prefers_restarting_over_unhealthy() -> None:
    details = [
        {"name": "a", "state": "restarting", "health": None, "restart_count": 4},
        {"name": "b", "state": "running", "health": "unhealthy", "restart_count": 0},
    ]
    assert DockerService.summarize_health(details) == "restarting"


def test_summarize_health_unhealthy_and_healthy_and_unknown() -> None:
    assert DockerService.summarize_health([]) == "unknown"
    assert DockerService.summarize_health([{"name": "a", "state": "running", "health": None, "restart_count": 0}]) == "unknown"
    assert (
        DockerService.summarize_health([{"name": "a", "state": "running", "health": "unhealthy", "restart_count": 0}])
        == "unhealthy"
    )
    assert (
        DockerService.summarize_health([{"name": "a", "state": "running", "health": "healthy", "restart_count": 0}])
        == "healthy"
    )
    assert (
        DockerService.summarize_health(
            [
                {"name": "a", "state": "running", "health": "healthy", "restart_count": 0},
                {"name": "b", "state": "running", "health": None, "restart_count": 0},
            ]
        )
        == "healthy"
    )


def test_find_caddy_container_resolves_by_compose_service_label() -> None:
    svc = _svc()
    fake_container = SimpleNamespace(name="myproj-caddy-1")
    containers = _RecordingContainers(list_result=[fake_container])
    svc._client = SimpleNamespace(containers=containers)

    result = svc.find_caddy_container()

    assert result is fake_container
    assert containers.list_calls == [{"label": "com.docker.compose.service=caddy"}]


def test_find_caddy_container_uses_override_name_when_configured() -> None:
    svc = _svc({"caddy_container_name": "my-caddy"})
    fake_container = SimpleNamespace(name="my-caddy")
    containers = _RecordingContainers(get_result=fake_container)
    svc._client = SimpleNamespace(containers=containers)

    result = svc.find_caddy_container()

    assert result is fake_container
    assert containers.get_calls == ["my-caddy"]


def test_find_caddy_container_picks_deterministically_by_name_when_multiple_match() -> None:
    svc = _svc()
    later = SimpleNamespace(name="zzz-caddy-2")
    earlier = SimpleNamespace(name="aaa-caddy-1")
    containers = _RecordingContainers(list_result=[later, earlier])
    svc._client = SimpleNamespace(containers=containers)

    result = svc.find_caddy_container()

    assert result is earlier


def test_find_caddy_container_returns_none_when_not_found() -> None:
    svc = _svc()
    svc._client = SimpleNamespace(containers=_RecordingContainers(list_result=[]))
    assert svc.find_caddy_container() is None


def _fake_run(returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout="", stderr="")


def test_compose_check_update_detects_image_change() -> None:
    stack = Stack(name="example", path="/config/stacks/example/compose.yaml")
    svc = _svc()
    container = SimpleNamespace(
        attrs={"Config": {"Image": "nginx:latest"}}, image=SimpleNamespace(id="sha256:old")
    )
    containers = _RecordingContainers(list_result=[container])
    images = SimpleNamespace(get=lambda ref: SimpleNamespace(id="sha256:new"))
    svc._client = SimpleNamespace(containers=containers, images=images)

    with patch("docker_service.subprocess.run", return_value=_fake_run()):
        assert svc.compose_check_update(stack) is True


def test_compose_check_update_false_when_image_unchanged() -> None:
    stack = Stack(name="example", path="/config/stacks/example/compose.yaml")
    svc = _svc()
    container = SimpleNamespace(
        attrs={"Config": {"Image": "nginx:latest"}}, image=SimpleNamespace(id="sha256:same")
    )
    containers = _RecordingContainers(list_result=[container])
    images = SimpleNamespace(get=lambda ref: SimpleNamespace(id="sha256:same"))
    svc._client = SimpleNamespace(containers=containers, images=images)

    with patch("docker_service.subprocess.run", return_value=_fake_run()):
        assert svc.compose_check_update(stack) is False


def test_compose_check_update_digest_pinned_image_reports_no_update() -> None:
    stack = Stack(name="example", path="/config/stacks/example/compose.yaml")
    svc = _svc()
    container = SimpleNamespace(
        attrs={"Config": {"Image": "nginx@sha256:abc123"}}, image=SimpleNamespace(id="sha256:abc123")
    )
    containers = _RecordingContainers(list_result=[container])
    images = SimpleNamespace(get=lambda ref: SimpleNamespace(id="sha256:abc123"))
    svc._client = SimpleNamespace(containers=containers, images=images)

    with patch("docker_service.subprocess.run", return_value=_fake_run()):
        assert svc.compose_check_update(stack) is False


def test_compose_check_update_returns_false_when_pull_fails() -> None:
    stack = Stack(name="example", path="/config/stacks/example/compose.yaml")
    svc = _svc()

    with patch("docker_service.subprocess.run", return_value=_fake_run(returncode=1)):
        assert svc.compose_check_update(stack) is False


def test_compose_check_update_false_when_stack_has_no_running_containers() -> None:
    stack = Stack(name="example", path="/config/stacks/example/compose.yaml")
    svc = _svc()
    svc._client = SimpleNamespace(containers=_RecordingContainers(list_result=[]))

    with patch("docker_service.subprocess.run", return_value=_fake_run()):
        assert svc.compose_check_update(stack) is False


def test_exec_run_returns_exit_code_and_output() -> None:
    svc = _svc()
    fake_container = SimpleNamespace(exec_run=lambda cmd: SimpleNamespace(exit_code=0, output=b"hello\n"))
    svc._client = SimpleNamespace(containers=_RecordingContainers(get_result=fake_container))

    exit_code, output = svc.exec_run("some-container", ["echo", "hello"])

    assert exit_code == 0
    assert output == b"hello\n"


if __name__ == "__main__":
    test_compose_cmd_uses_project_name_and_compose_file()
    test_compose_cmd_adds_override_file_when_present()
    test_status_from_details()
    test_summarize_health_prefers_restarting_over_unhealthy()
    test_summarize_health_unhealthy_and_healthy_and_unknown()
    test_find_caddy_container_resolves_by_compose_service_label()
    test_find_caddy_container_picks_deterministically_by_name_when_multiple_match()
    test_find_caddy_container_uses_override_name_when_configured()
    test_find_caddy_container_returns_none_when_not_found()
    test_compose_check_update_detects_image_change()
    test_compose_check_update_false_when_image_unchanged()
    test_compose_check_update_digest_pinned_image_reports_no_update()
    test_compose_check_update_returns_false_when_pull_fails()
    test_compose_check_update_false_when_stack_has_no_running_containers()
    test_exec_run_returns_exit_code_and_output()
    print("ok")
