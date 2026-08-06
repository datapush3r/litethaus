import asyncio
import os
import pty
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import docker
from docker.errors import NotFound

from config_service import ConfigService, config_service as _default_config_service
from stacks_service import Stack

BAD_HEALTH_STATES = {"unhealthy", "restarting"}
CADDY_SERVICE_LABEL = "com.docker.compose.service=caddy"


class DockerService:
    def __init__(self, config: ConfigService = _default_config_service) -> None:
        self._client: docker.DockerClient | None = None
        self._config = config

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    def _prefix(self) -> str:
        return self._config.load().get("project_prefix", "") or ""

    def _project_name(self, stack: Stack) -> str:
        return f"{self._prefix()}{stack.name}"

    def _network_name(self) -> str:
        return f"{self._prefix()}litethaus"

    def ensure_network(self) -> None:
        network_name = self._network_name()
        try:
            self.client.networks.get(network_name)
        except NotFound:
            self.client.networks.create(network_name, driver="bridge")

    def _compose_cmd(self, stack: Stack, *args: str) -> list[str]:
        cmd = ["docker", "compose", "-p", self._project_name(stack), "-f", stack.path]
        if stack.override_file:
            cmd += ["-f", str(Path(stack.path).parent / stack.override_file)]
        return cmd + list(args)

    def compose_up(self, stack: Stack) -> tuple[bool, str]:
        self.ensure_network()
        result = subprocess.run(self._compose_cmd(stack, "up", "-d"), capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr

    def compose_down(self, stack: Stack) -> tuple[bool, str]:
        result = subprocess.run(self._compose_cmd(stack, "down"), capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr

    def compose_restart(self, stack: Stack) -> tuple[bool, str]:
        result = subprocess.run(self._compose_cmd(stack, "restart"), capture_output=True, text=True)
        return result.returncode == 0, result.stdout + result.stderr

    def compose_update(self, stack: Stack) -> tuple[bool, str]:
        pull = subprocess.run(self._compose_cmd(stack, "pull"), capture_output=True, text=True)
        if pull.returncode != 0:
            return False, pull.stdout + pull.stderr
        self.ensure_network()
        up = subprocess.run(self._compose_cmd(stack, "up", "-d"), capture_output=True, text=True)
        return up.returncode == 0, pull.stdout + pull.stderr + up.stdout + up.stderr

    async def _stream_process_lines(self, cmd: list[str]) -> AsyncIterator[str]:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield line.decode(errors="replace").rstrip("\n")
        finally:
            if process.returncode is None:
                process.terminate()

    async def stream_logs(self, stack: Stack, container: str | None = None) -> AsyncIterator[str]:
        # A single container's logs are streamed directly via `docker logs`
        # rather than `docker compose logs <service>` - the caller already
        # resolves `container` to an actual container name (see
        # find_container()), which docker logs takes directly with no need
        # to also know the service name from the compose file.
        cmd = (
            ["docker", "logs", "-f", "--tail", "100", container]
            if container
            else self._compose_cmd(stack, "logs", "-f", "--no-color", "--tail", "100")
        )
        async for line in self._stream_process_lines(cmd):
            yield line

    async def stream_container_logs(self, container_name: str) -> AsyncIterator[str]:
        # Same as stream_logs(container=...) above but for a container that
        # isn't part of any litethaus-scanned stack - i.e. Caddy itself.
        async for line in self._stream_process_lines(["docker", "logs", "-f", "--tail", "100", container_name]):
            yield line

    def container_details(self, stack: Stack) -> list[dict[str, Any]]:
        containers = self.client.containers.list(
            all=True, filters={"label": f"com.docker.compose.project={self._project_name(stack)}"}
        )
        return [self._describe(c) for c in containers]

    def find_container(self, stack: Stack, container_name: str) -> Any | None:
        for c in self.client.containers.list(
            all=True, filters={"label": f"com.docker.compose.project={self._project_name(stack)}"}
        ):
            if c.name == container_name:
                return c
        return None

    def find_caddy_container(self) -> Any | None:
        # Caddy isn't a scanned "stack" (it's not under stacks_dir), so it has
        # no project label to filter by the way container_details() does.
        # Compose always sets com.docker.compose.service=caddy regardless of
        # an explicit container_name: override, so that's the reliable
        # zero-config match; caddy_container_name in config.yaml is only for
        # the rare case Caddy runs outside litethaus's own Compose project.
        override = self._config.load().get("caddy_container_name") or ""
        if override:
            try:
                return self.client.containers.get(override)
            except NotFound:
                return None
        containers = self.client.containers.list(filters={"label": CADDY_SERVICE_LABEL})
        return containers[0] if containers else None

    def exec_run(self, container_name: str, cmd: list[str]) -> tuple[int, bytes]:
        # One-off non-interactive exec via docker-py's high-level exec_run -
        # a genuinely different code path from exec_shell()'s CLI+pty socket
        # workaround above (that EOF bug was specific to the low-level
        # client.api.exec_start(..., socket=True) hijack; exec_run() doesn't
        # use it).
        container = self.client.containers.get(container_name)
        result = container.exec_run(cmd)
        return result.exit_code, result.output

    def exec_shell(self, container_name: str) -> tuple[int, subprocess.Popen]:
        # Shells out to the `docker` CLI over a real pty, same approach as
        # stream_logs() below - docker-py's low-level exec socket hijack
        # (client.api.exec_start(..., socket=True)) delivers an immediate
        # EOF on first read in this environment for reasons that didn't
        # trace back to anything in our control; the CLI+pty path is what
        # every terminal emulator does anyway and just works.
        # Falls back to sh on minimal (alpine) images that have no bash.
        # `command -v bash && exec bash || exec sh` (not `exec bash || exec
        # sh`) - in POSIX shells, exec failing to find its target terminates
        # the shell immediately rather than falling through to `||`.
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            ["docker", "exec", "-i", "-t", container_name, "sh", "-c",
             "command -v bash >/dev/null 2>&1 && exec bash || exec sh"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
        )
        os.close(slave_fd)
        return master_fd, process

    @staticmethod
    def _describe(container: Any) -> dict[str, Any]:
        health = ((container.attrs.get("State") or {}).get("Health") or {}).get("Status")
        return {
            "name": container.name,
            "state": container.status,
            "health": health,
            "restart_count": container.attrs.get("RestartCount", 0),
        }

    def container_status(self, stack: Stack) -> str:
        return self.status_from_details(self.container_details(stack))

    @staticmethod
    def status_from_details(details: list[dict[str, Any]]) -> str:
        if not details:
            return "stopped"
        states = {d["state"] for d in details}
        if states == {"running"}:
            return "running"
        if "running" in states:
            return "partial"
        return "stopped"

    @staticmethod
    def summarize_health(details: list[dict[str, Any]]) -> str:
        if not details:
            return "unknown"
        # A container's own "restarting" state is Docker's live signal for a
        # restart loop - more reliable than RestartCount, which is a lifetime
        # total that never resets and says nothing about "right now".
        if "restarting" in {d["state"] for d in details}:
            return "restarting"
        healths = {d["health"] for d in details if d["health"] is not None}
        if "unhealthy" in healths:
            return "unhealthy"
        if "starting" in healths:
            return "starting"
        if healths and healths == {"healthy"}:
            return "healthy"
        return "unknown"


docker_service = DockerService()
