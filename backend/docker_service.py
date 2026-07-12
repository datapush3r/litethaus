import subprocess

import docker
from docker.errors import NotFound

from stacks_service import Stack

NETWORK_NAME = "litethaus"


class DockerService:
    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def ensure_network(self) -> None:
        try:
            self.client.networks.get(NETWORK_NAME)
        except NotFound:
            self.client.networks.create(NETWORK_NAME, driver="bridge")

    def _compose_cmd(self, stack: Stack, *args: str) -> list[str]:
        return ["docker", "compose", "-p", stack.name, "-f", stack.path, *args]

    def compose_up(self, stack: Stack) -> tuple[bool, str]:
        self.ensure_network()
        result = subprocess.run(self._compose_cmd(stack, "up", "-d"), capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr

    def compose_down(self, stack: Stack) -> tuple[bool, str]:
        result = subprocess.run(self._compose_cmd(stack, "down"), capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr

    def container_status(self, stack: Stack) -> str:
        containers = self.client.containers.list(
            all=True, filters={"label": f"com.docker.compose.project={stack.name}"}
        )
        if not containers:
            return "stopped"
        states = {c.status for c in containers}
        if states == {"running"}:
            return "running"
        if "running" in states:
            return "partial"
        return "stopped"


docker_service = DockerService()
