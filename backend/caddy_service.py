import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any

from config_service import config_service
from stacks_service import Stack

logger = logging.getLogger(__name__)

# Applied to a stack's route when its .litethaus.yaml sets lan_only: true -
# same private-address ranges a typical LAN-allowlist reverse-proxy rule uses.
LAN_ONLY_RANGES = ["10.0.0.0/8", "172.0.0.0/16", "192.168.0.0/16"]


class CaddyService:
    def __init__(self, admin_url: str | None = None) -> None:
        self._admin_url_override = admin_url
        self._last_sync: dict[str, Any] | None = None

    @property
    def admin_url(self) -> str:
        if self._admin_url_override is not None:
            return self._admin_url_override
        return config_service.load()["caddy_admin_url"]

    def status(self) -> dict[str, Any]:
        return {"enabled": config_service.load().get("caddy_enabled", True), **(self._last_sync or {})}

    def fetch_live_config(self) -> dict[str, Any]:
        # Proxies Caddy's own /config/ so the UI can show what Caddy is
        # actually running, not just what we last tried to push - also
        # doubles as a reachability check (raises if Caddy can't be reached).
        with urllib.request.urlopen(f"{self.admin_url}/config/", timeout=5) as resp:
            return json.load(resp)

    def build_config(
        self,
        stacks: list[Stack],
        https_mode: str = "off",
        acme_email: str = "",
        cloudflare_api_token: str = "",
        wildcard_domain: str = "",
        extra_routes_json: str = "",
    ) -> dict[str, Any]:
        routes = []
        domains = []
        for stack in stacks:
            if stack.error:
                continue
            meta = stack.x_litethaus
            domain = meta.get("domain")
            port = meta.get("port")
            if not domain or not port:
                continue
            domains.append(domain)
            upstream_service = meta.get("service") or (stack.services[0] if stack.services else stack.name)
            match: dict[str, Any] = {"host": [domain]}
            if meta.get("lan_only"):
                match["remote_ip"] = {"ranges": LAN_ONLY_RANGES}
            routes.append(
                {
                    "match": [match],
                    "handle": [
                        {
                            "handler": "reverse_proxy",
                            "upstreams": [{"dial": f"{upstream_service}:{port}"}],
                        }
                    ],
                }
            )

        if extra_routes_json:
            try:
                extra = json.loads(extra_routes_json)
                if not isinstance(extra, list):
                    raise ValueError("extra_routes_json must be a JSON array")
                routes.extend(extra)
            except Exception:
                logger.exception("Failed to parse caddy_extra_routes_json, skipping")

        # When HTTPS is on, listen on :443 only and let Caddy's automatic_https
        # feature synthesize the :80 -> :443 redirect itself. If we listened on
        # :80 ourselves with these same host-matched routes, our own route would
        # shadow that redirect and serve plaintext HTTP right alongside HTTPS.
        listen = [":443"] if https_mode != "off" else [":80"]

        config: dict[str, Any] = {
            # A JSON config pushed via /load that omits "admin" resets the
            # listener to Caddy's built-in default (localhost:2019), which
            # cuts the backend off from Caddy's admin API on the very next
            # sync (it reaches Caddy over the docker network, not loopback).
            # Pinning it here keeps it stable across every reload; it must
            # match the Caddyfile's `{admin 0.0.0.0:2019}` bootstrap value.
            "admin": {"listen": "0.0.0.0:2019"},
            "apps": {
                "http": {
                    "servers": {
                        "litethaus": {
                            "listen": listen,
                            "routes": routes,
                        }
                    }
                }
            }
        }

        # Caddy defaults to ACME for anything listening on :443, so "internal"
        # mode must be spelled out explicitly to get self-signed certs instead
        # (the right default for .home.arpa/.local domains with no public DNS).
        if https_mode == "internal":
            config["apps"]["tls"] = {"automation": {"policies": [{"subjects": domains, "issuers": [{"module": "internal"}]}]}}
        elif https_mode == "acme":
            issuer: dict[str, Any] = {"module": "acme", "email": acme_email}
            if cloudflare_api_token:
                # Explicit resolvers, not the container's default (which may
                # be a home router doing split-horizon DNS): Caddy's zone/SOA
                # lookup and propagation checks need to see the real public
                # DNS, not a LAN-only override of the challenge domain.
                issuer["challenges"] = {
                    "dns": {
                        "provider": {"name": "cloudflare", "api_token": cloudflare_api_token},
                        "resolvers": ["1.1.1.1:53", "8.8.8.8:53"],
                    }
                }
            subjects = [f"*.{wildcard_domain}"] if wildcard_domain else domains
            config["apps"]["tls"] = {"automation": {"policies": [{"subjects": subjects, "issuers": [issuer]}]}}

        return config

    def sync(self, stacks: list[Stack]) -> None:
        cfg = config_service.load()
        if not cfg.get("caddy_enabled", True):
            return
        config = self.build_config(
            stacks,
            https_mode=cfg.get("https_mode", "off"),
            acme_email=cfg.get("acme_email", ""),
            cloudflare_api_token=cfg.get("cloudflare_api_token", ""),
            wildcard_domain=cfg.get("wildcard_domain", ""),
            extra_routes_json=cfg.get("caddy_extra_routes_json", ""),
        )
        req = urllib.request.Request(
            f"{self.admin_url}/load",
            data=json.dumps(config).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception as exc:
            logger.exception("Failed to sync Caddy config")
            self._last_sync = {"ok": False, "at": datetime.now(timezone.utc).isoformat(), "error": str(exc)}
        else:
            self._last_sync = {"ok": True, "at": datetime.now(timezone.utc).isoformat(), "error": None}


caddy_service = CaddyService()
