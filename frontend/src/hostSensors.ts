// Pure helpers for the homepage's host sensor cards (GET /api/host/sensors).

export interface HostSensor {
  chip: string;
  kind: "temp" | "fan" | "voltage";
  label: string;
  value: number;
  unit: string;
}

export interface HostSensorsResponse {
  available: boolean;
  sensors: HostSensor[];
}

/** Group sensors by chip, preserving first-seen chip order. */
export function groupSensors(sensors: HostSensor[]): [string, HostSensor[]][] {
  const groups = new Map<string, HostSensor[]>();
  for (const s of sensors) {
    const g = groups.get(s.chip) ?? [];
    g.push(s);
    groups.set(s.chip, g);
  }
  return [...groups.entries()];
}

/** Color threshold for a temperature in °C. */
export function tempTone(c: number): "ok" | "warn" | "bad" {
  if (c >= 85) return "bad";
  if (c >= 70) return "warn";
  return "ok";
}

/** 0 RPM means "no fan / fan stopped" — show a dash instead of "0 RPM". */
export function formatFan(rpm: number | null): string {
  if (rpm === null || rpm === 0) return "–";
  return `${rpm} RPM`;
}
