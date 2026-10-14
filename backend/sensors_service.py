"""Reads host hardware sensors from kernel sysfs (hwmon + thermal zones)
and, when a driver is present, nvidia-smi for NVIDIA GPUs (which publish
no hwmon entries on most cards).

Paths and tools are env-overridable (LITETHAUS_HWMON_DIR /
LITETHAUS_THERMAL_DIR / LITETHAUS_NVIDIA_SMI) so the service works whether
the container's sysfs exposes the data directly or the host's is
bind-mounted in (e.g. Proxmox LXC setups).
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

# hwmon `name` values -> display chip names. Unknown names are NOT filtered
# out; they fall through to the capitalized raw name.
_CHIP_NAMES: dict[str, str] = {
    "coretemp": "CPU",
    "x86_pkg_temp": "CPU",
    "k10temp": "CPU",
    "amdgpu": "GPU",
    "nouveau": "GPU",
}
_MOTHERBOARD_PREFIXES = ("nct6775", "nct6776", "w83627", "it86", "it87", "f7188", "adt7475", "lm90", "lm87", "asus")

# nvidia-smi query fields, in the order they appear in each CSV row.
_NVIDIA_FIELDS = (
    "name", "temperature.gpu", "temperature.memory",
    "fan.speed", "utilization.gpu", "power.draw",
)

NVIDIA_SMI_TIMEOUT = 5  # seconds
NVIDIA_CACHE_TTL = 10  # seconds — the frontend polls at 5s; NVML re-opens the driver per call


def _chip_display_name(raw: str) -> str:
    if raw in _CHIP_NAMES:
        return _CHIP_NAMES[raw]
    if raw == "nvme":
        return "NVMe"
    if raw.startswith("nv"):  # NVIDIA hwmon chips are nv0..nvN
        return "GPU"
    if raw.startswith(_MOTHERBOARD_PREFIXES):
        return "Motherboard"
    return raw.capitalize()


def _read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return None  # missing file / EIO — both common on hwmon


def _read_int(path: Path) -> int | None:
    raw = _read(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None  # e.g. a driver returning junk instead of a number


def _nvidia_value(raw: str) -> float | None:
    """Parse an nvidia-smi CSV cell; '[N/A]' / 'N/A' means the sensor doesn't exist."""
    v = raw.strip().strip("[]")
    if v in ("", "N/A"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


class SensorService:
    def __init__(self) -> None:
        self._hwmon_dir = Path(os.environ.get("LITETHAUS_HWMON_DIR", "/sys/class/hwmon"))
        self._thermal_dir = Path(os.environ.get("LITETHAUS_THERMAL_DIR", "/sys/class/thermal"))
        self._nvidia_smi = os.environ.get("LITETHAUS_NVIDIA_SMI", "nvidia-smi")
        self._nvidia_smi_timeout = float(os.environ.get("LITETHAUS_NVIDIA_SMI_TIMEOUT", NVIDIA_SMI_TIMEOUT))
        self._nvidia_cache: list[dict[str, Any]] | None = None
        self._nvidia_cached_at: float = 0.0

    def read(self) -> dict[str, object]:
        sensors: list[dict[str, Any]] = []
        sensors.extend(self._read_hwmon())
        sensors.extend(self._read_thermal())
        sensors.extend(self._read_nvidia())
        return {"available": bool(sensors), "sensors": sensors}

    def _read_hwmon(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self._hwmon_dir.is_dir():
            return out
        for entry in sorted(self._hwmon_dir.iterdir()):
            if not entry.is_dir():
                continue
            name = _read(entry / "name") or entry.name
            chip = _chip_display_name(name)
            for f in sorted(entry.iterdir()):
                label_file = _read(f.with_name(f.name.replace("_input", "") + "_label"))
                if f.name.startswith("temp") and f.name.endswith("_input"):
                    val = _read_int(f)
                    # Chips report -40 (or similar deep-negative) for inactive
                    # sensors; real hardware never reads that cold in a server.
                    if val is None or val / 1000 < -25:
                        continue
                    out.append({
                        "chip": chip, "kind": "temp",
                        "label": label_file or f"Temperature {f.name[:-6][4:]}",
                        "value": round(val / 1000, 1), "unit": "°C",
                    })
                elif f.name.startswith("fan") and f.name.endswith("_input"):
                    val = _read_int(f)
                    if val is None:
                        continue
                    out.append({
                        "chip": chip, "kind": "fan",
                        "label": label_file or f"Fan {f.name[:-6][3:]}",
                        "value": val, "unit": "RPM",
                    })
                elif f.name.startswith("in") and f.name.endswith("_input") and label_file:
                    # unnamed analog pins are noise — only show labeled voltages
                    val = _read_int(f)
                    if val is None:
                        continue
                    out.append({
                        "chip": chip, "kind": "voltage",
                        "label": label_file,
                        "value": round(val / 1000, 2), "unit": "V",
                    })
        return out

    def _read_thermal(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not self._thermal_dir.is_dir():
            return out
        for entry in sorted(self._thermal_dir.iterdir()):
            if not entry.is_dir() or not entry.name.startswith("thermal_zone"):
                continue
            ztype = _read(entry / "type") or entry.name
            val = _read_int(entry / "temp")
            if val is None:
                continue
            chip = _chip_display_name(ztype)
            out.append({
                "chip": chip,
                "kind": "temp",
                "label": "CPU package" if chip == "CPU" else ztype,
                "value": round(val / 1000, 1), "unit": "°C",
            })
        return out

    def _read_nvidia(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        if self._nvidia_cache is not None and now - self._nvidia_cached_at < NVIDIA_CACHE_TTL:
            return self._nvidia_cache
        out: list[dict[str, Any]] = []
        if shutil.which(self._nvidia_smi):
            try:
                result = subprocess.run(
                    [self._nvidia_smi,
                     f"--query-gpu={','.join(_NVIDIA_FIELDS)}",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=self._nvidia_smi_timeout,
                )
            except (OSError, subprocess.TimeoutExpired):
                result = None
            if result is not None and result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    parts = line.split(",")
                    if len(parts) != len(_NVIDIA_FIELDS):
                        continue
                    name, core_t, mem_t, fan, util, power = parts
                    chip = name.strip().removeprefix("NVIDIA ")
                    for label, raw in (
                        ("GPU core", core_t),
                        ("Memory", mem_t),
                    ):
                        val = _nvidia_value(raw)
                        if val is not None:
                            out.append({"chip": chip, "kind": "temp",
                                        "label": label, "value": round(val, 1), "unit": "°C"})
                    val = _nvidia_value(fan)
                    if val is not None:
                        out.append({"chip": chip, "kind": "fan",
                                    "label": "Fan", "value": round(val), "unit": "%"})
                    val = _nvidia_value(util)
                    if val is not None:
                        out.append({"chip": chip, "kind": "util",
                                    "label": "Utilization", "value": round(val), "unit": "%"})
                    val = _nvidia_value(power)
                    if val is not None:
                        out.append({"chip": chip, "kind": "power",
                                    "label": "Power", "value": round(val, 1), "unit": "W"})
        self._nvidia_cache = out
        self._nvidia_cached_at = now
        return out


sensors_service = SensorService()
