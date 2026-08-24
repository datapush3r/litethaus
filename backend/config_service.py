import os
import threading
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

CONFIG_PATH = Path(os.environ.get("LITETHAUS_CONFIG_PATH", "/config/config.yaml"))

_yaml = YAML()
_yaml.preserve_quotes = True

DEFAULT_CONFIG = """\
# litethaus global configuration
# Settings here control the dashboard and reverse proxy behavior.

# Whether the single-user login gate is enforced. Set to false to disable
# auth entirely - useful for local testing, but leaves every API endpoint
# and websocket open with no authentication.
auth_enabled: true

# Directory containing one subfolder per stack, each with its own docker-compose.yaml
stacks_dir: /config/stacks

# Prepended to every Compose project name and to the shared "litethaus" Docker
# network. Set this if another litethaus instance runs on the same host, so
# the two never resolve to the same Compose project/containers/network.
project_prefix: ""

# Whether litethaus manages the bundled Caddy reverse proxy. Set to false if
# you're fronting your own stacks with a different reverse proxy - litethaus
# will skip pushing config to Caddy entirely (domain/port fields in stacks
# are simply ignored).
caddy_enabled: true

# Whether litethaus guesses an icon for stacks that don't have one set, by
# matching image/stack/service names against the dashboard-icons catalog.
# Set to false to leave icon-less stacks alone entirely.
auto_icon_enabled: true

# Base URL for the Caddy admin API used to push proxy config
caddy_admin_url: http://localhost:2019

# External port stack links should use, e.g. 8443 if host port 443 is already
# taken by something else. Cosmetic only - doesn't change what Caddy binds to,
# just what the dashboard puts in the "open" links it generates.
https_port: 443

# HTTPS mode for the reverse proxy: "off" (HTTP only), "internal" (self-signed
# certs via Caddy's local CA - fine for .home.arpa/.local domains), or "acme"
# (real certs via Let's Encrypt - requires stacks' domains to be publicly
# resolvable and port 80/443 reachable from the internet)
https_mode: "off"

# Email for ACME/Let's Encrypt certificate registration, required when https_mode is "acme"
acme_email: ""

# Cloudflare API token for DNS-01 ACME challenges (needs Zone:Read + DNS:Edit
# permissions for the domain in use). Leave blank to use Caddy's default
# HTTP-01/TLS-ALPN-01 challenges instead.
cloudflare_api_token: ""

# Wildcard domain for ACME certs, e.g. "example.com" issues one "*.example.com"
# cert covering every stack instead of a cert per stack domain. Requires
# cloudflare_api_token (DNS-01 is the only way to prove ownership of a
# wildcard). Leave blank to keep today's per-stack-domain certs.
wildcard_domain: ""

# Domains to keep pointed at this host's current public IP via Cloudflare's
# API. Requires cloudflare_api_token above. Each domain must already have an
# A record in Cloudflare - litethaus updates the IP, never creates records or
# touches proxied/TTL. Leave empty to disable.
ddns_domains: []

# Background check for newer container images on each running stack (12h
# interval) - replaces watchtower's blanket auto-update with visibility
# only. Never recreates a container by itself; the manual Update button on
# each stack still does that. Set false to disable the check entirely.
update_check_enabled: true

# Time of day (24h "HH:MM", local time) the auto-update pass runs. Only
# touches stacks with auto_update: true set in their own .litethaus.yaml
# (opt-in, off by default) - everything else stays check-only, same as the
# manual Update button. Requires update_check_enabled above.
auto_update_time: "03:00"

# Advanced: raw Caddy route objects (JSON array) appended after the routes
# litethaus generates per-stack, for cases the domain/port/service model
# doesn't cover. Leave blank to skip. Invalid JSON is ignored (logged) rather
# than breaking the sync.
caddy_extra_routes_json: ""

# Override for which container is "the" Caddy container, used by the TLS
# certificate tracker and access log viewer. Leave blank to auto-resolve via
# the "com.docker.compose.service=caddy" label Compose always sets (works
# regardless of an explicit container_name: override) - only set this if
# Caddy runs outside litethaus's own Compose project.
caddy_container_name: ""

# Whether Caddy emits access logs (one line per request) to its own
# container log, viewable from the Caddy page's Access Logs tab. Off by
# default - noisy for a home reverse proxy unless you're debugging routing.
caddy_access_log_enabled: false

# Whether Caddy adds hardening response headers (X-Content-Type-Options,
# X-Frame-Options: SAMEORIGIN, Referrer-Policy, and Strict-Transport-Security
# when https_mode isn't "off") to every stack route. Off by default - some
# self-hosted apps embed each other in iframes and would break under
# X-Frame-Options, so this is opt-in rather than forced on everyone.
caddy_security_headers_enabled: false

# UI theme: "light", "dark", or "system"
theme: system

# Webhook URL to POST to when a stack becomes unhealthy or enters a restart
# loop (JSON body: {"stack": name, "health": "unhealthy"|"restarting"}).
# Leave blank to disable.
webhook_url: ""

# healthchecks.io (or compatible) dead-man's-switch ping URL, e.g.
# https://hc-ping.com/<uuid>. Pinged on every health-check poll tick so an
# external monitor can alert if litethaus itself stops running. Leave blank
# to disable.
healthchecks_url: ""
"""


class ConfigService:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(DEFAULT_CONFIG)
            with self.path.open("r") as f:
                return _yaml.load(f)

    def save(self, data: dict[str, Any]) -> None:
        with self._lock:
            with self.path.open("w") as f:
                _yaml.dump(data, f)

    def update(self, patch: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        for key, value in patch.items():
            data[key] = value
        self.save(data)
        return data


config_service = ConfigService()
