import json
import logging
import threading
import urllib.request

from config_service import config_service
from docker_service import BAD_HEALTH_STATES, docker_service
from stacks_service import stack_service

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15


class HealthService:
    def __init__(self) -> None:
        self._last_health: dict[str, str] = {}
        self._stop_event: threading.Event | None = None

    def check_once(self) -> None:
        webhook_url = config_service.load().get("webhook_url") or ""
        for stack in stack_service.list_stacks():
            if stack.error:
                continue
            health = docker_service.summarize_health(docker_service.container_details(stack))
            became_bad = health in BAD_HEALTH_STATES and self._last_health.get(stack.name) != health
            self._last_health[stack.name] = health
            if became_bad and webhook_url:
                self._notify(webhook_url, stack.name, health)

    def _notify(self, webhook_url: str, stack_name: str, health: str) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"stack": stack_name, "health": health}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send health webhook for %s", stack_name)

    def watch_forever(self) -> None:
        stop_event = threading.Event()
        self._stop_event = stop_event
        while not stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                logger.exception("Health check failed")
            stop_event.wait(POLL_INTERVAL_SECONDS)


health_service = HealthService()
