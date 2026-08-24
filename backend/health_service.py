import json
import logging
import threading
import time
import urllib.request
from collections import deque
from datetime import date, datetime, timezone
from typing import Any

from caddy_service import caddy_service
from cert_service import cert_service
from config_service import config_service
from ddns_service import ddns_service
from docker_service import BAD_HEALTH_STATES, docker_service
from stacks_service import stack_service

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 15
HEALTH_LOG_MAXLEN = 500
CERT_CHECK_INTERVAL_SECONDS = 24 * 60 * 60
CERT_EXPIRY_WARNING_DAYS = 14
DDNS_CHECK_INTERVAL_SECONDS = 300
CADDY_RESYNC_INTERVAL_SECONDS = 60
UPDATE_CHECK_INTERVAL_SECONDS = 12 * 60 * 60
AUTO_UPDATE_DEFAULT_TIME = "03:00"


class HealthService:
    def __init__(self) -> None:
        self._last_health: dict[str, str] = {}
        self._health_log: deque[dict[str, str]] = deque(maxlen=HEALTH_LOG_MAXLEN)
        self._stop_event: threading.Event | None = None
        self._last_cert_check: float = float("-inf")
        self._alerted_certs: set[str] = set()
        self._last_ddns_check: float = float("-inf")
        self._ddns_failing: set[str] = set()
        self._last_update_check: float = float("-inf")
        self._update_available: dict[str, bool] = {}
        self._update_notified: set[str] = set()
        self._last_auto_update_date: date | None = None
        self._container_stats: list[dict[str, Any]] = []
        self._last_caddy_resync: float = float("-inf")

    def check_once(self) -> None:
        cfg = config_service.load()
        webhook_url = cfg.get("webhook_url") or ""
        # One docker-stats snapshot covers every running container on the host;
        # calling container_stats per stack would re-run it once per stack.
        self._container_stats = docker_service.host_container_stats(
            [s for s in stack_service.list_stacks() if not s.error]
        )
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
        self._check_updates_once(webhook_url)
        self._run_auto_updates_once(webhook_url)
        self._ping_healthchecks(cfg.get("healthchecks_url") or "")
        self._check_caddy_sync_once()

    def _check_caddy_sync_once(self) -> None:
        # Caddy holds its entire route config in the admin API only (the
        # Caddyfile is an admin-socket stub), so any caddy restart wipes all
        # routes until someone re-syncs. Re-push every 60s; sync() is a no-op
        # POST when caddy is unreachable, and cheap when it isn't.
        now = time.monotonic()
        if now - self._last_caddy_resync < CADDY_RESYNC_INTERVAL_SECONDS:
            return
        self._last_caddy_resync = now
        if not config_service.load().get("caddy_enabled", True):
            return
        caddy_service.sync(stack_service.list_stacks())

    def _ping_healthchecks(self, url: str) -> None:
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

    def _check_updates_once(self, webhook_url: str) -> None:
        now = time.monotonic()
        if now - self._last_update_check < UPDATE_CHECK_INTERVAL_SECONDS:
            return
        self._last_update_check = now
        cfg = config_service.load()
        if not cfg.get("update_check_enabled", True):
            return
        for stack in stack_service.list_stacks():
            if stack.error or docker_service.container_status(stack) == "stopped":
                continue
            available = docker_service.compose_check_update(stack)
            self._update_available[stack.name] = available
            if available:
                if stack.name not in self._update_notified and webhook_url:
                    self._notify_update_available(webhook_url, stack.name)
                self._update_notified.add(stack.name)
            else:
                self._update_notified.discard(stack.name)

    def _notify_update_available(self, webhook_url: str, stack_name: str) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"stack_update_available": stack_name}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send update-available webhook for %s", stack_name)

    def update_available(self, stack_name: str) -> bool:
        return self._update_available.get(stack_name, False)

    def clear_update_flag(self, stack_name: str) -> None:
        self._update_available[stack_name] = False
        self._update_notified.discard(stack_name)

    def _run_auto_updates_once(self, webhook_url: str) -> None:
        today = date.today()
        if self._last_auto_update_date == today:
            return
        cfg = config_service.load()
        if not cfg.get("update_check_enabled", True):
            return
        time_str = cfg.get("auto_update_time") or AUTO_UPDATE_DEFAULT_TIME
        try:
            target = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            target = datetime.strptime(AUTO_UPDATE_DEFAULT_TIME, "%H:%M").time()
        if datetime.now().time() < target:
            return
        self._last_auto_update_date = today
        self._apply_auto_updates(webhook_url)

    def run_auto_updates_now(self) -> list[dict[str, object]]:
        cfg = config_service.load()
        if not cfg.get("update_check_enabled", True):
            return []
        self._last_auto_update_date = date.today()
        return self._apply_auto_updates(cfg.get("webhook_url") or "")

    def _apply_auto_updates(self, webhook_url: str) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for stack in stack_service.list_stacks():
            if stack.error or not stack.x_litethaus.get("auto_update"):
                continue
            if docker_service.container_status(stack) != "running":
                continue
            if not docker_service.compose_check_update(stack):
                continue
            ok, output = docker_service.compose_update(stack)
            if ok:
                self.clear_update_flag(stack.name)
            if webhook_url:
                self._notify_auto_update(webhook_url, stack.name, ok, output)
            results.append({"stack": stack.name, "ok": ok})
        return results

    def _notify_auto_update(self, webhook_url: str, stack_name: str, ok: bool, output: str) -> None:
        payload: dict[str, object] = {"stack_auto_updated": stack_name, "ok": ok}
        if not ok:
            payload["detail"] = output[-500:]
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send auto-update webhook for %s", stack_name)

    def health_log(self, stack_name: str) -> list[dict[str, str]]:
        return [e for e in self._health_log if e["stack"] == stack_name]

    def container_stats(self, stack_name: str | None = None) -> list[dict[str, Any]]:
        """Latest cached per-container usage rows (all stacks, or one stack)."""
        if stack_name is not None:
            return [r for r in self._container_stats if r.get("stack") == stack_name]
        return self._container_stats

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
