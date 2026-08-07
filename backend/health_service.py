import json
import logging
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone

from cert_service import cert_service
from config_service import config_service
from ddns_service import ddns_service
from docker_service import BAD_HEALTH_STATES, docker_service
from stacks_service import stack_service

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15
HEALTH_LOG_MAXLEN = 500  # ponytail: global ring buffer, split per-stack if one noisy stack starts crowding others out
CERT_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
CERT_EXPIRY_WARNING_DAYS = 14
DDNS_CHECK_INTERVAL_SECONDS = 300


class HealthService:
    def __init__(self) -> None:
        self._last_health: dict[str, str] = {}
        self._health_log: deque[dict[str, str]] = deque(maxlen=HEALTH_LOG_MAXLEN)
        self._stop_event: threading.Event | None = None
        self._last_cert_check: float = float("-inf")
        self._alerted_certs: set[str] = set()
        self._last_ddns_check: float = float("-inf")
        self._ddns_failing: set[str] = set()

    def check_once(self) -> None:
        cfg = config_service.load()
        webhook_url = cfg.get("webhook_url") or ""
        for stack in stack_service.list_stacks():
            if stack.error:
                continue
            health = docker_service.summarize_health(docker_service.container_details(stack))
            changed = self._last_health.get(stack.name) != health
            if changed:
                self._health_log.append(
                    {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "stack": stack.name,
                        "health": health,
                    }
                )
            became_bad = health in BAD_HEALTH_STATES and changed
            self._last_health[stack.name] = health
            if became_bad and webhook_url:
                self._notify(webhook_url, stack.name, health)
        self._check_certs_once(webhook_url)
        self._check_ddns_once(webhook_url)
        self._ping_healthchecks(cfg.get("healthchecks_url") or "")

    def _ping_healthchecks(self, url: str) -> None:
        # Dead-man's-switch ping (https://healthchecks.io): fired every poll
        # tick just like the rest of check_once() - a missed ping is what
        # tells healthchecks.io (not litethaus) that this process died, so
        # it must not be gated behind any of check_once()'s own logic.
        if not url:
            return
        try:
            urllib.request.urlopen(url, timeout=5)
        except Exception:
            logger.exception("Failed to ping healthchecks.io")

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

    def _check_certs_once(self, webhook_url: str) -> None:
        # Cert expiry moves over days, not seconds - polling it on the same
        # 15s cadence as container health would be pure waste, so this gates
        # itself to once a day independent of watch_forever()'s loop period.
        now = time.monotonic()
        if now - self._last_cert_check < CERT_CHECK_INTERVAL_SECONDS:
            return
        self._last_cert_check = now
        if not webhook_url:
            return
        still_soon: set[str] = set()
        for cert in cert_service.list_certificates():
            domain = cert["domains"][0] if cert["domains"] else "unknown"
            expires_at = datetime.fromisoformat(cert["expires_at"])
            days_left = (expires_at - datetime.now(timezone.utc)).days
            if days_left > CERT_EXPIRY_WARNING_DAYS:
                continue
            still_soon.add(domain)
            if domain not in self._alerted_certs:
                self._notify_cert_expiry(webhook_url, domain, days_left)
        self._alerted_certs = still_soon

    def _notify_cert_expiry(self, webhook_url: str, domain: str, days_left: int) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"cert_domain": domain, "days_until_expiry": days_left}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send cert-expiry webhook for %s", domain)

    def _check_ddns_once(self, webhook_url: str) -> None:
        now = time.monotonic()
        if now - self._last_ddns_check < DDNS_CHECK_INTERVAL_SECONDS:
            return
        self._last_ddns_check = now
        cfg = config_service.load()
        token = cfg.get("cloudflare_api_token") or ""
        domains = cfg.get("ddns_domains") or []
        if not token or not domains:
            return
        still_failing: set[str] = set()
        for result in ddns_service.sync(token, domains):
            domain = result["domain"]
            if result["status"] == "updated":
                if webhook_url:
                    self._notify_ddns_change(webhook_url, domain, result["old_ip"], result["new_ip"])
            elif result["status"] == "error":
                if domain not in self._ddns_failing and webhook_url:
                    self._notify_ddns_error(webhook_url, domain, result["detail"])
                still_failing.add(domain)
        self._ddns_failing = still_failing

    def _notify_ddns_change(self, webhook_url: str, domain: str, old_ip: str | None, new_ip: str | None) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"ddns_domain": domain, "old_ip": old_ip, "new_ip": new_ip}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send DDNS-change webhook for %s", domain)

    def _notify_ddns_error(self, webhook_url: str, domain: str, detail: str | None) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"ddns_error": domain, "detail": detail}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send DDNS-error webhook for %s", domain)

    def health_log(self, stack_name: str) -> list[dict[str, str]]:
        return [e for e in self._health_log if e["stack"] == stack_name]

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
