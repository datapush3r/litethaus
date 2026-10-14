import os
import stat
import tempfile
from contextlib import contextmanager

from sensors_service import SensorService, _chip_display_name


def _fake_nvidia_smi(path: str, rows: list[str], count_file: str | None = None) -> None:
    """Write an executable nvidia-smi stand-in emitting the given CSV rows."""
    with open(path, "w") as f:
        f.write("#!/bin/sh\n")
        if count_file:
            f.write(f"echo x >> {count_file}\n")
        for row in rows:
            f.write(f"echo {row!r}\n" if row else "\n")
    os.chmod(path, stat.S_IRWXU)


@contextmanager
def _with_sysfs():
    """Point the service at throwaway hwmon/thermal dirs; restores env after."""
    saved = {k: os.environ.get(k) for k in ("LITETHAUS_HWMON_DIR", "LITETHAUS_THERMAL_DIR", "LITETHAUS_NVIDIA_SMI")}
    with tempfile.TemporaryDirectory() as tmp:
        hwmon = os.path.join(tmp, "hwmon")
        thermal = os.path.join(tmp, "thermal")
        os.makedirs(hwmon)
        os.makedirs(thermal)
        os.environ["LITETHAUS_HWMON_DIR"] = hwmon
        os.environ["LITETHAUS_THERMAL_DIR"] = thermal
        # Keep these tests deterministic on hosts that do have a driver.
        os.environ["LITETHAUS_NVIDIA_SMI"] = "/nonexistent-nvidia-smi"
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


def test_nvidia_smi_produces_per_card_sensors() -> None:
    with _with_sysfs():
        assert SensorService()._read_nvidia() == []

    with _with_sysfs() as (hwmon, _t):
        shim = os.path.join(os.path.dirname(hwmon), "fake-smi")
        _fake_nvidia_smi(shim, [
            "NVIDIA CMP 170HX, 42, 57, [N/A], 97, 60.20",
            "NVIDIA GeForce GTX 1650, 35, N/A, 30, 0, 8.01",
        ])
        os.environ["LITETHAUS_NVIDIA_SMI"] = shim
        sensors = SensorService()._read_nvidia()
        by = {(s["chip"], s["kind"], s["label"]): s for s in sensors}
        # compute card: core + memory temps, no fan, util + power
        assert by[("CMP 170HX", "temp", "GPU core")] == {"chip": "CMP 170HX", "kind": "temp", "label": "GPU core", "value": 42.0, "unit": "°C"}
        assert by[("CMP 170HX", "temp", "Memory")]["value"] == 57.0
        assert by[("CMP 170HX", "util", "Utilization")]["value"] == 97
        assert by[("CMP 170HX", "power", "Power")]["value"] == 60.2
        assert not [s for s in sensors if s["chip"] == "CMP 170HX" and s["kind"] == "fan"]
        # display card: core temp only (no memory sensor), fan as %
        assert by[("GeForce GTX 1650", "fan", "Fan")]["value"] == 30
        assert by[("GeForce GTX 1650", "fan", "Fan")]["unit"] == "%"
        assert not [s for s in sensors if s["chip"] == "GeForce GTX 1650" and s["label"] == "Memory"]


def test_nvidia_smi_result_is_cached() -> None:
    with _with_sysfs() as (hwmon, _t):
        shim = os.path.join(os.path.dirname(hwmon), "fake-smi")
        count = os.path.join(os.path.dirname(hwmon), "count")
        _fake_nvidia_smi(shim, ["NVIDIA Test, 40, N/A, N/A, 5, 30.0"], count_file=count)
        os.environ["LITETHAUS_NVIDIA_SMI"] = shim
        svc = SensorService()
        svc._read_nvidia()
        svc._read_nvidia()
        with open(count) as f:
            assert len(f.read().strip().splitlines()) == 1


def test_nvidia_smi_timeout_is_handled() -> None:
    with _with_sysfs() as (hwmon, _t):
        shim = os.path.join(os.path.dirname(hwmon), "slow-smi")
        with open(shim, "w") as f:
            f.write("#!/bin/sh\nsleep 10\n")
        os.chmod(shim, stat.S_IRWXU)
        os.environ["LITETHAUS_NVIDIA_SMI"] = shim
        os.environ["LITETHAUS_NVIDIA_SMI_TIMEOUT"] = "1"
        assert SensorService()._read_nvidia() == []
        del os.environ["LITETHAUS_NVIDIA_SMI_TIMEOUT"]


def test_chip_display_names() -> None:
    assert _chip_display_name("coretemp") == "CPU"
    assert _chip_display_name("k10temp") == "CPU"
    assert _chip_display_name("nv4") == "GPU"
    assert _chip_display_name("amdgpu") == "GPU"
    assert _chip_display_name("nct6775") == "Motherboard"
    assert _chip_display_name("f71882f") == "Motherboard"
    assert _chip_display_name("nvme") == "NVMe"
    assert _chip_display_name("someoddchip") == "Someoddchip"


def test_inactive_sensor_readings_are_skipped() -> None:
    with _with_sysfs() as (hwmon, _):
        _make_chip(hwmon, 0, "nct6775", {"temp1_input": "-40000", "temp2_input": "30000"})
        sensors = SensorService().read()["sensors"]
        assert len(sensors) == 1
        assert sensors[0]["value"] == 30.0


if __name__ == "__main__":
    test_parses_temps_fans_and_labeled_voltages()
    test_fan_label_fallback()
    test_missing_dirs_means_unavailable()
    test_empty_dirs_means_unavailable()
    test_junk_temp_file_is_skipped()
    test_inactive_sensor_readings_are_skipped()
    test_nvidia_smi_produces_per_card_sensors()
    test_nvidia_smi_result_is_cached()
    test_nvidia_smi_timeout_is_handled()
    test_chip_display_names()
    print("ok")
