from pathlib import Path

import pytest

import sensors_service as mod
from sensors_service import SensorService, _chip_display_name


@pytest.fixture
def dirs(tmp_path: Path):
    hwmon = tmp_path / "hwmon"
    thermal = tmp_path / "thermal"
    return hwmon, thermal


@pytest.fixture
def svc(dirs, monkeypatch):
    monkeypatch.setenv("LITETHAUS_HWMON_DIR", str(dirs[0]))
    monkeypatch.setenv("LITETHAUS_THERMAL_DIR", str(dirs[1]))
    return SensorService()


_CHIP_COUNTER = 0


def _make_chip(hwmon: Path, name: str, files: dict[str, str]) -> None:
    global _CHIP_COUNTER
    entry = hwmon / f"hwmon{_CHIP_COUNTER}"
    _CHIP_COUNTER += 1
    entry.mkdir(parents=True)
    (entry / "name").write_text(name)
    for fname, content in files.items():
        (entry / fname).write_text(content)


@pytest.fixture(autouse=True)
def _reset_chip_counter():
    global _CHIP_COUNTER
    _CHIP_COUNTER = 0
    yield


def test_parses_temps_fans_and_labeled_voltages(dirs, svc) -> None:
    hwmon, thermal = dirs
    _make_chip(hwmon, "coretemp", {
        "temp1_input": "52300",
        "temp1_label": "Core 0",
        "temp2_input": "51100",
    })
    _make_chip(hwmon, "nct6775", {
        "fan1_input": "1150",
        "fan1_label": "CPU FAN",
        "in1_input": "1234",
        "in1_label": "VCore",
        "in2_input": "5000",  # no label -> excluded
    })
    thermal.mkdir()
    zone = thermal / "thermal_zone0"
    zone.mkdir()
    (zone / "type").write_text("x86_pkg_temp")
    (zone / "temp").write_text("41000")

    result = svc.read()
    assert result["available"] is True
    sensors = result["sensors"]
    assert {"chip": "CPU", "kind": "temp", "label": "Core 0", "value": 52.3, "unit": "°C"} in sensors
    assert {"chip": "CPU", "kind": "temp", "label": "Temperature 2", "value": 51.1, "unit": "°C"} in sensors
    assert {"chip": "Motherboard", "kind": "fan", "label": "CPU FAN", "value": 1150, "unit": "RPM"} in sensors
    assert {"chip": "Motherboard", "kind": "voltage", "label": "VCore", "value": 1.23, "unit": "V"} in sensors
    assert all(s["label"] != "in2" for s in sensors)
    # unlabeled voltage must not appear at all
    assert all(not (s["kind"] == "voltage" and s["chip"] == "Motherboard" and s["label"] != "VCore") for s in sensors)
    assert {"chip": "CPU", "kind": "temp", "label": "CPU package", "value": 41.0, "unit": "°C"} in sensors


def test_fan_label_fallback(dirs, svc) -> None:
    hwmon, _ = dirs
    _make_chip(hwmon, "nct6775", {"fan1_input": "800"})
    fan = [s for s in svc.read()["sensors"] if s["kind"] == "fan"][0]
    assert fan["label"] == "Fan 1"
    assert fan["value"] == 800


def test_missing_dirs_means_unavailable(dirs, svc) -> None:
    assert svc.read() == {"available": False, "sensors": []}


def test_junk_temp_file_is_skipped(dirs, svc) -> None:
    hwmon, _ = dirs
    _make_chip(hwmon, "coretemp", {"temp1_input": "EIO", "temp2_input": "40000"})
    sensors = svc.read()["sensors"]
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
