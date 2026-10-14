import { describe, expect, it } from "vitest";
import { formatFan, groupSensors, tempTone, type HostSensor } from "./hostSensors";

function sensor(chip: string, kind: HostSensor["kind"], label: string, value: number): HostSensor {
  return { chip, kind, label, value, unit: kind === "temp" ? "°C" : kind === "fan" ? "RPM" : "V" };
}

describe("groupSensors", () => {
  it("groups by chip, preserving first-seen order", () => {
    const groups = groupSensors([
      sensor("CPU", "temp", "Core 0", 50),
      sensor("Motherboard", "fan", "CPU FAN", 1000),
      sensor("CPU", "temp", "Core 1", 52),
      sensor("GPU", "temp", "GPU Core", 38),
      sensor("Motherboard", "voltage", "VCore", 1.2),
    ]);
    expect(groups.map(([chip]) => chip)).toEqual(["CPU", "Motherboard", "GPU"]);
    expect(groups[0][1].map((s) => s.label)).toEqual(["Core 0", "Core 1"]);
  });

  it("returns [] for no sensors", () => {
    expect(groupSensors([])).toEqual([]);
  });
});

describe("tempTone", () => {
  it("uses the 70/85 °C thresholds", () => {
    expect(tempTone(40)).toBe("ok");
    expect(tempTone(69.9)).toBe("ok");
    expect(tempTone(70)).toBe("warn");
    expect(tempTone(84.9)).toBe("warn");
    expect(tempTone(85)).toBe("bad");
  });
});

describe("formatFan", () => {
  it("shows a dash for missing or stopped fans", () => {
    expect(formatFan(null)).toBe("–");
    expect(formatFan(0)).toBe("–");
    expect(formatFan(1150)).toBe("1150 RPM");
  });
});
