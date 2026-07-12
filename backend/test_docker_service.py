from docker_service import DockerService
from stacks_service import Stack


def test_compose_cmd_uses_project_name_and_compose_file() -> None:
    stack = Stack(name="example", path="/opt/litethaus/stacks/example/docker-compose.yaml")
    svc = DockerService()

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
        path="/opt/litethaus/stacks/example/compose.yaml",
        override_file="compose.override.yaml",
    )
    svc = DockerService()

    assert svc._compose_cmd(stack, "up", "-d") == [
        "docker",
        "compose",
        "-p",
        "example",
        "-f",
        stack.path,
        "-f",
        "/opt/litethaus/stacks/example/compose.override.yaml",
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
    # mixed healthchecked + non-healthchecked containers: any bad signal wins,
    # otherwise it's only "healthy" once every checked container agrees
    assert (
        DockerService.summarize_health(
            [
                {"name": "a", "state": "running", "health": "healthy", "restart_count": 0},
                {"name": "b", "state": "running", "health": None, "restart_count": 0},
            ]
        )
        == "healthy"
    )


if __name__ == "__main__":
    test_compose_cmd_uses_project_name_and_compose_file()
    test_compose_cmd_adds_override_file_when_present()
    test_status_from_details()
    test_summarize_health_prefers_restarting_over_unhealthy()
    test_summarize_health_unhealthy_and_healthy_and_unknown()
    print("ok")
