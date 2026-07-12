import json
import logging
import urllib.request
from typing import Any

from config_service import config_service
from stacks_service import Stack

logger = logging.getLogger(__name__)


class CaddyService:
    def __init__(self, admin_url: str | None = None) -> None:
        self._admin_url_override = admin_url

    @property
    def admin_url(self) -> str:
        if self._admin_url_override is not None:
            return self._admin_url_override
        return config_service.load()["caddy_admin_url"]

    def build_config(self, stacks: list[Stack]) -> dict[str, Any]:
        routes = []
        for stack in stacks:
            if stack.error:
                continue
            meta = stack.x_litethaus
            domain = meta.get("domain")
            port = meta.get("port")
            if not domain or not port:
                continue
            upstream_service = meta.get("service") or (stack.services[0] if stack.services else stack.name)
            routes.append(
                {
                    "match": [{"host": [domain]}],
                    "handle": [
                        {
                            "handler": "reverse_proxy",
                            "upstreams": [{"dial": f"{upstream_service}:{port}"}],
                        }
                    ],
                }
            )
        return {
            "apps": {
                "http": {
                    "servers": {
                        "litethaus": {
                            "listen": [":80"],
                            "routes": routes,
                        }
                    }
                }
            }
        }

    def sync(self, stacks: list[Stack]) -> None:
        config = self.build_config(stacks)
        req = urllib.request.Request(
            f"{self.admin_url}/load",
            data=json.dumps(config).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to sync Caddy config")


caddy_service = CaddyService()
