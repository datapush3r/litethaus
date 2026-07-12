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

# Directory containing one subfolder per stack, each with its own docker-compose.yaml
stacks_dir: /opt/litethaus/stacks

# Base URL for the Caddy admin API used to push proxy config
caddy_admin_url: http://localhost:2019

# HTTPS mode for the reverse proxy: "off" (HTTP only), "internal" (self-signed
# certs via Caddy's local CA - fine for .home.arpa/.local domains), or "acme"
# (real certs via Let's Encrypt - requires stacks' domains to be publicly
# resolvable and port 80/443 reachable from the internet)
https_mode: "off"

# Email for ACME/Let's Encrypt certificate registration, required when https_mode is "acme"
acme_email: ""

# UI theme: "light", "dark", or "system"
theme: system
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
