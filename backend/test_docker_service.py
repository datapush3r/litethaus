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


if __name__ == "__main__":
    test_compose_cmd_uses_project_name_and_compose_file()
    print("ok")
