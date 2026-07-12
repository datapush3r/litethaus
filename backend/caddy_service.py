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

    def build_config(
        self,
        stacks: list[Stack],
        https_mode: str = "off",
        acme_email: str = "",
        cloudflare_api_token: str = "",
        wildcard_domain: str = "",
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
        config = self.build_config(
            stacks,
            https_mode=cfg.get("https_mode", "off"),
            acme_email=cfg.get("acme_email", ""),
            cloudflare_api_token=cfg.get("cloudflare_api_token", ""),
            wildcard_domain=cfg.get("wildcard_domain", ""),
        )
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
