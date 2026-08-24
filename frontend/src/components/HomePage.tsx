import { useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, PackageOpen } from "lucide-react";
import {
  sortStacksByStatus,
  type Stack,
  type StackState,
  type StackStatus,
} from "../api";
import { BAD_HEALTH } from "../statusStyles";
import { StackIcon } from "./StackIcon";

interface HomePageProps {
  stacks: Stack[];
  statuses: Record<string, StackState>;
  health: Record<string, StackStatus>;
  onOpenStack: (name: string) => void;
}

type SortKey = "stack" | "container" | "cpu" | "mem" | "gpu";

interface ContainerRow {
  stack: string;
  container: string;
  cpu: number | null;
  mem: number | null;
  gpu: number | null;
}

function fmtBytes(bytes: number | null): string {
  if (bytes === null) return "–";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value >= 100 || i === 0 ? Math.round(value) : value.toFixed(1)} ${units[i]}`;
}

export function HomePage({
  stacks,
  statuses,
  health,
  onOpenStack,
}: HomePageProps) {
  const ok = stacks.filter((s) => !s.error && statuses[s.name] !== "stopped");
  const problems = ok.filter((s) =>
    BAD_HEALTH.has(health[s.name]?.health ?? "unknown"),
  );
  const updates = ok.filter((s) => health[s.name]?.update_available);

  const rows = useMemo<ContainerRow[]>(() => {
    const order = new Map(
      sortStacksByStatus(stacks, statuses).map((s) => [s.name, s]),
    );
    const out: ContainerRow[] = [];
    for (const stack of stacks) {
      if (stack.error) continue;
      for (const s of health[stack.name]?.stats ?? []) {
        out.push({
          stack: stack.name,
          container: s.name,
          cpu: s.cpu_percent,
          mem: s.mem_bytes,
          gpu: s.gpu_percent,
        });
      }
    }
    return out.sort(
      (a, b) =>
        [...order.keys()].indexOf(a.stack) - [...order.keys()].indexOf(b.stack),
    );
  }, [stacks, statuses, health]);

  const [sortKey, setSortKey] = useState<SortKey>("cpu");
  const [asc, setAsc] = useState(false);

  const sortedRows = useMemo(() => {
    const dir = asc ? 1 : -1;
    return [...rows].sort((a, b) => {
      if (sortKey === "stack" || sortKey === "container") {
        const primary = a[sortKey].localeCompare(b[sortKey]);
        return primary !== 0
          ? primary * dir
          : a.container.localeCompare(b.container);
      }
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va === null && vb === null) return 0;
      if (va === null) return 1; // nulls always last, regardless of direction
      if (vb === null) return -1;
      return (va - vb) * dir;
    });
  }, [rows, sortKey, asc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setAsc((v) => !v);
    else {
      setSortKey(key);
      setAsc(key === "stack" || key === "container"); // text columns default ascending
    }
  }

  if (stacks.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-center text-neutral-400 dark:text-neutral-500">
        <PackageOpen size={28} />
        <p className="text-sm">No stacks found. Add one under stacks_dir.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat
          label="Running"
          value={`${ok.length} / ${stacks.length}`}
          tone={ok.length < stacks.length ? "warn" : "ok"}
        />
        <Stat
          label="Needs attention"
          value={String(problems.length)}
          tone={problems.length > 0 ? "bad" : "ok"}
        />
        <Stat
          label="Updates available"
          value={String(updates.length)}
          tone={updates.length > 0 ? "warn" : "ok"}
        />
      </section>

      {problems.length > 0 && (
        <StackSection title="Unhealthy">
          {sortStacksByStatus(problems, statuses).map((s) => (
            <Row key={s.name} stack={s} onOpen={onOpenStack} />
          ))}
        </StackSection>
      )}

      {updates.length > 0 && (
        <StackSection title="Updates available">
          {sortStacksByStatus(updates, statuses).map((s) => (
            <Row key={s.name} stack={s} onOpen={onOpenStack} />
          ))}
        </StackSection>
      )}

      <section>
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          Container usage
        </h2>
        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-neutral-400 dark:text-neutral-500">
            No running containers.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-neutral-200 bg-white dark:border-neutral-800 dark:bg-neutral-900">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs text-neutral-500 dark:border-neutral-800 dark:text-neutral-400">
                  <Th
                    label="Stack"
                    active={sortKey === "stack"}
                    asc={asc}
                    onClick={() => toggleSort("stack")}
                  />
                  <Th
                    label="Container"
                    active={sortKey === "container"}
                    asc={asc}
                    onClick={() => toggleSort("container")}
                  />
                  <Th
                    label="CPU"
                    align="right"
                    active={sortKey === "cpu"}
                    asc={asc}
                    onClick={() => toggleSort("cpu")}
                  />
                  <Th
                    label="RAM"
                    align="right"
                    active={sortKey === "mem"}
                    asc={asc}
                    onClick={() => toggleSort("mem")}
                  />
                  <Th
                    label="GPU"
                    align="right"
                    active={sortKey === "gpu"}
                    asc={asc}
                    onClick={() => toggleSort("gpu")}
                  />
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((r) => (
                  <tr
                    key={`${r.stack}:${r.container}`}
                    className="border-b border-neutral-100 last:border-b-0 hover:bg-neutral-50 dark:border-neutral-800/60 dark:hover:bg-neutral-800/40"
                  >
                    <td className="px-3 py-2">
                      <button
                        onClick={() => onOpenStack(r.stack)}
                        className="font-medium text-neutral-900 hover:underline dark:text-neutral-100"
                      >
                        {r.stack}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-neutral-600 dark:text-neutral-300">
                      {r.container}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.cpu === null ? "–" : `${r.cpu.toFixed(1)}%`}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {fmtBytes(r.mem)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {r.gpu === null ? "–" : `${r.gpu.toFixed(0)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {problems.length === 0 && updates.length === 0 && rows.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-10 text-center text-neutral-400 dark:text-neutral-500">
          <PackageOpen size={28} />
          <p className="text-sm">All stacks are healthy and up to date.</p>
        </div>
      )}
    </div>
  );
}

function Th({
  label,
  align = "left",
  active,
  asc,
  onClick,
}: {
  label: string;
  align?: "left" | "right";
  active: boolean;
  asc: boolean;
  onClick: () => void;
}) {
  return (
    <th
      className={`px-3 py-2 font-medium ${align === "right" ? "text-right" : ""}`}
    >
      <button
        onClick={onClick}
        className={`inline-flex items-center gap-1 hover:text-neutral-800 dark:hover:text-neutral-200 ${
          active ? "text-neutral-900 dark:text-neutral-100" : ""
        }`}
      >
        {label}
        <span className="text-[10px]">{active ? (asc ? "▲" : "▼") : ""}</span>
      </button>
    </th>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "ok" | "warn" | "bad";
}) {
  const toneClass =
    tone === "bad"
      ? "text-red-600 dark:text-red-400"
      : tone === "warn"
        ? "text-amber-600 dark:text-amber-400"
        : "text-neutral-900 dark:text-neutral-100";
  return (
    <div className="rounded-lg border border-neutral-200 bg-white px-4 py-3 dark:border-neutral-800 dark:bg-neutral-900">
      <div className={`text-2xl font-semibold ${toneClass}`}>{value}</div>
      <div className="text-xs text-neutral-500 dark:text-neutral-400">
        {label}
      </div>
    </div>
  );
}

function StackSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {title}
      </h2>
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function Row({
  stack,
  onOpen,
}: {
  stack: Stack;
  onOpen: (name: string) => void;
}) {
  return (
    <button
      onClick={() => onOpen(stack.name)}
      className="flex items-center gap-3 rounded-lg border border-neutral-200 bg-white px-4 py-2.5 text-left hover:border-neutral-300 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
    >
      <StackIcon icon={stack.x_litethaus.icon} size={22} />
      <span className="font-medium text-neutral-900 dark:text-neutral-100">
        {stack.name}
      </span>
      {stack.error && (
        <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
          <AlertTriangle size={12} />
          <span className="truncate">{stack.error}</span>
        </span>
      )}
      <ArrowRight size={14} className="ml-auto shrink-0 text-neutral-400" />
    </button>
  );
}
