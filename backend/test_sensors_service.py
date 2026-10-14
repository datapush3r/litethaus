import os
import tempfile
from contextlib import contextmanager

from sensors_service import SensorService, _chip_display_name


@contextmanager
def _with_sysfs():
    """Point the service at throwaway hwmon/thermal dirs; restores env after."""
    saved = {k: os.environ.get(k) for k in ("LITETHAUS_HWMON_DIR", "LITETHAUS_THERMAL_DIR")}
    with tempfile.TemporaryDirectory() as tmp:
        hwmon = os.path.join(tmp, "hwmon")
        thermal = os.path.join(tmp, "thermal")
        os.makedirs(hwmon)
        os.makedirs(thermal)
        os.environ["LITETHAUS_HWMON_DIR"] = hwmon
        os.environ["LITETHAUS_THERMAL_DIR"] = thermal
        yield hwmon, thermal
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _make_chip(hwmon: str, idx: int, name: str, files: dict) -> None:
    entry = os.path.join(hwmon, f"hwmon{idx}")
    os.makedirs(entry)
    with open(os.path.join(entry, "name"), "w") as f:
        f.write(name)
    for fname, content in files.items():
        with open(os.path.join(entry, fname), "w") as f:
            f.write(content)


def test_parses_temps_fans_and_labeled_voltages() -> None:
    with _with_sysfs() as (hwmon, thermal):
        _make_chip(hwmon, 0, "coretemp", {
            "temp1_input": "52300",
            "temp1_label": "Core 0",
            "temp2_input": "51100",
        })
        _make_chip(hwmon, 1, "nct6775", {
            "fan1_input": "1150",
            "fan1_label": "CPU FAN",
            "in1_input": "1234",
            "in1_label": "VCore",
            "in2_input": "5000",  # no label -> excluded
        })
        zone = os.path.join(thermal, "thermal_zone0")
        os.makedirs(zone)
        with open(os.path.join(zone, "type"), "w") as f:
            f.write("x86_pkg_temp")
        with open(os.path.join(zone, "temp"), "w") as f:
            f.write("41000")

        sensors = SensorService().read()["sensors"]
        assert {"chip": "CPU", "kind": "temp", "label": "Core 0", "value": 52.3, "unit": "°C"} in sensors
        assert {"chip": "CPU", "kind": "temp", "label": "Temperature 2", "value": 51.1, "unit": "°C"} in sensors
        assert {"chip": "Motherboard", "kind": "fan", "label": "CPU FAN", "value": 1150, "unit": "RPM"} in sensors
        assert {"chip": "Motherboard", "kind": "voltage", "label": "VCore", "value": 1.23, "unit": "V"} in sensors
        # the unlabeled voltage must not appear at all
        assert not [s for s in sensors if s["kind"] == "voltage" and s["chip"] == "Motherboard" and s["label"] != "VCore"]
        assert {"chip": "CPU", "kind": "temp", "label": "CPU package", "value": 41.0, "unit": "°C"} in sensors


def test_fan_label_fallback() -> None:
    with _with_sysfs() as (hwmon, _):
        _make_chip(hwmon, 0, "nct6775", {"fan1_input": "800"})
        fan = [s for s in SensorService().read()["sensors"] if s["kind"] == "fan"][0]
        assert fan["label"] == "Fan 1"
        assert fan["value"] == 800


def test_missing_dirs_means_unavailable() -> None:
    with _with_sysfs():
        os.environ["LITETHAUS_HWMON_DIR"] = "/nonexistent-hwmon"
        os.environ["LITETHAUS_THERMAL_DIR"] = "/nonexistent-thermal"
        assert SensorService().read() == {"available": False, "sensors": []}


def test_empty_dirs_means_unavailable() -> None:
    with _with_sysfs():
        # dirs exist but expose no hwmon*/thermal_zone* chips
        assert SensorService().read() == {"available": False, "sensors": []}


def test_junk_temp_file_is_skipped() -> None:
    with _with_sysfs() as (hwmon, _):
        _make_chip(hwmon, 0, "coretemp", {"temp1_input": "EIO", "temp2_input": "40000"})
        sensors = SensorService().read()["sensors"]
        assert len(sensors) == 1
        assert sensors[0]["value"] == 40.0


def test_chip_display_names() -> None:
    assert _chip_display_name("coretemp") == "CPU"
    assert _chip_display_name("k10temp") == "CPU"
    assert _chip_display_name("nv4") == "GPU"
    assert _chip_display_name("amdgpu") == "GPU"
    assert _chip_display_name("nct6775") == "Motherboard"
    assert _chip_display_name("f71882f") == "Motherboard"
    assert _chip_display_name("nvme") == "NVMe"
    assert _chip_display_name("someoddchip") == "Someoddchip"


if __name__ == "__main__":
    test_parses_temps_fans_and_labeled_voltages()
    test_fan_label_fallback()
    test_missing_dirs_means_unavailable()
    test_empty_dirs_means_unavailable()
    test_junk_temp_file_is_skipped()
    test_chip_display_names()
    print("ok")
