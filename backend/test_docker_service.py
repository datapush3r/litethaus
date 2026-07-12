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


if __name__ == "__main__":
    test_compose_cmd_uses_project_name_and_compose_file()
    print("ok")
