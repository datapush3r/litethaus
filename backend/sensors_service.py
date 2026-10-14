"""Reads host hardware sensors from kernel sysfs (hwmon + thermal zones).

Paths are env-overridable (LITETHAUS_HWMON_DIR / LITETHAUS_THERMAL_DIR) so the
service works whether the container's sysfs exposes them directly or a host
directory is bind-mounted somewhere else (e.g. Proxmox LXC setups).
"""

import os
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
_MOTHERBOARD_PREFIXES = ("nct6775", "nct6776", "w83627", "it86", "it87", "f7188", "adt7475", "lm90", "lm87")


def _chip_display_name(raw: str) -> str:
    if raw in _CHIP_NAMES:
        return _CHIP_NAMES[raw]
    if raw == "nvme":
        return "NVMe"
    if raw.startswith("nv"):  # NVIDIA hwmon chips are nv0..nvN
        return "GPU"
    if raw.startswith(_MOTHERBOARD_PREFIXES):
        return "Motherboard"
    if raw == "nvme":
        return "NVMe"
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


class SensorService:
    def __init__(self) -> None:
        self._hwmon_dir = Path(os.environ.get("LITETHAUS_HWMON_DIR", "/sys/class/hwmon"))
        self._thermal_dir = Path(os.environ.get("LITETHAUS_THERMAL_DIR", "/sys/class/thermal"))

    def read(self) -> dict[str, object]:
        sensors: list[dict[str, Any]] = []
        sensors.extend(self._read_hwmon())
        sensors.extend(self._read_thermal())
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
                    if val is None:
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


sensors_service = SensorService()
