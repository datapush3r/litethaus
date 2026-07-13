import os
import threading
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

CONFIG_PATH = Path(os.environ.get("LITETHAUS_CONFIG_PATH", "/opt/litethaus/config.yaml"))

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
stacks_dir: /opt/litethaus/stacks

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

# UI theme: "light", "dark", or "system"
theme: system

# Webhook URL to POST to when a stack becomes unhealthy or enters a restart
# loop (JSON body: {"stack": name, "health": "unhealthy"|"restarting"}).
# Leave blank to disable.
webhook_url: ""
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
