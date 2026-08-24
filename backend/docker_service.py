import asyncio
import json
import logging
import os
import pty
import re
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import docker
from docker.errors import NotFound

from config_service import ConfigService, config_service as _default_config_service
from stacks_service import Stack

logger = logging.getLogger(__name__)

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

    def compose_check_update(self, stack: Stack) -> bool:
        pull = subprocess.run(self._compose_cmd(stack, "pull"), capture_output=True, text=True)
        if pull.returncode != 0:
            logger.warning("update check pull failed for %s: %s", stack.name, pull.stderr)
            return False
        containers = self.client.containers.list(
            filters={"label": f"com.docker.compose.project={self._project_name(stack)}"}
        )
        for container in containers:
            image_ref = container.attrs["Config"]["Image"]
            try:
                fresh = self.client.images.get(image_ref)
            except NotFound:
                continue
            if fresh.id != container.image.id:
                return True
        return False

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
        cmd = (
            ["docker", "logs", "-f", "--tail", "100", container]
            if container
            else self._compose_cmd(stack, "logs", "-f", "--no-color", "--tail", "100")
        )
        async for line in self._stream_process_lines(cmd):
            yield line

    async def stream_container_logs(self, container_name: str) -> AsyncIterator[str]:
        async for line in self._stream_process_lines(["docker", "logs", "-f", "--tail", "100", container_name]):
            yield line

    def container_details(self, stack: Stack) -> list[dict[str, Any]]:
        containers = self.client.containers.list(
            all=True, filters={"label": f"com.docker.compose.project={self._project_name(stack)}"}
        )
        return [self._describe(c) for c in containers]

    def container_stats(self, stack: Stack) -> list[dict[str, Any]]:
        """Live resource usage for this stack's running containers (cpu %, mem bytes, gpu %).

        Takes one `docker stats --no-stream` snapshot of the whole host and keeps
        only rows belonging to this stack. Callers checking many stacks should
        share a single snapshot instead of calling this per-stack.
        """
        running = {d["name"] for d in self.container_details(stack) if d["state"] == "running"}
        if not running:
            return []
        proc = self._run_docker_stats()
        if proc is None:
            return []

        rows: list[dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3 or parts[0] not in running:
                continue
            rows.append(
                {
                    "name": parts[0],
                    "cpu_percent": self._parse_percent(parts[1]),
                    "mem_bytes": self._parse_mem_usage(parts[2]),
                    "gpu_percent": self._parse_percent(parts[3]) if len(parts) > 3 else None,
                }
            )
        return rows

    def host_container_stats(self, stacks: list[Stack]) -> list[dict[str, Any]]:
        """One `docker stats` snapshot of the whole host, tagged with stack names.

        Cheaper than calling container_stats per stack (which re-runs the
        snapshot each time). Rows carry {stack, name, cpu_percent, mem_bytes,
        gpu_percent}; stacks with no running containers contribute nothing.
        """
        by_container: dict[str, str] = {}
        for s in stacks:
            for d in self.container_details(s):
                if d["state"] == "running":
                    by_container.setdefault(d["name"], s.name)
        if not by_container:
            return []
        proc = self._run_docker_stats()
        if proc is None:
            return []

        rows: list[dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 3 or parts[0] not in by_container:
                continue
            rows.append(
                {
                    "stack": by_container[parts[0]],
                    "name": parts[0],
                    "cpu_percent": self._parse_percent(parts[1]),
                    "mem_bytes": self._parse_mem_usage(parts[2]),
                    "gpu_percent": self._parse_percent(parts[3]) if len(parts) > 3 else None,
                }
            )
        return rows

    def _run_docker_stats(self) -> subprocess.CompletedProcess[str] | None:
        """One `docker stats --no-stream` snapshot of every running container.

        GPUUsage needs Docker >= 28; older daemons error on the template, so
        fall back to a format without it. Returns None on failure.
        """
        fmt = '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.GPUUsage}}'
        try:
            proc = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", fmt],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0 and "GPUUsage" in (proc.stderr or ""):
                logger.info("docker stats: GPU column unsupported, retrying without it")
                fmt = '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'
                proc = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", fmt],
                    capture_output=True, text=True, timeout=30,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("docker stats failed: %s", exc)
            return None
        if proc.returncode != 0:
            logger.warning("docker stats exited %d: %s", proc.returncode, proc.stderr.strip())
            return None
        return proc

    @staticmethod
    def _parse_percent(value: str) -> float | None:
        m = re.search(r"([\d.]+)%", value)
        return float(m.group(1)) if m else None

    @staticmethod
    def _parse_mem_usage(value: str) -> int | None:
        """Parse docker stats 'USED / TOTAL' into used bytes (None on parse fail)."""
        m = re.match(r"([\d.]+)([a-zA-Z]*)\s*/", value)
        if not m:
            return None
        number, unit = float(m.group(1)), m.group(2)
        # docker stats uses binary units: kB=KiB, MB=MiB, GB=GiB
        factor = {"": 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}.get(unit[:1].lower())
        return int(number * factor) if factor is not None else None

    def find_container(self, stack: Stack, container_name: str) -> Any | None:
        for c in self.client.containers.list(
            all=True, filters={"label": f"com.docker.compose.project={self._project_name(stack)}"}
        ):
            if c.name == container_name:
                return c
        return None

    def find_caddy_container(self) -> Any | None:
        override = self._config.load().get("caddy_container_name") or ""
        if override:
            try:
                return self.client.containers.get(override)
            except NotFound:
                return None
        containers = self.client.containers.list(filters={"label": CADDY_SERVICE_LABEL})
        if not containers:
            return None
        if len(containers) > 1:
            logger.warning(
                "Multiple containers matched %s: %s - picking alphabetically first",
                CADDY_SERVICE_LABEL,
                sorted(c.name for c in containers),
            )
        return sorted(containers, key=lambda c: c.name)[0]

    def exec_run(self, container_name: str, cmd: list[str]) -> tuple[int, bytes]:
        container = self.client.containers.get(container_name)
        result = container.exec_run(cmd)
        return result.exit_code, result.output

    def exec_shell(self, container_name: str) -> tuple[int, subprocess.Popen]:
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
            "image": (container.attrs.get("Config") or {}).get("Image", ""),
            "created": container.attrs.get("Created", ""),
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
