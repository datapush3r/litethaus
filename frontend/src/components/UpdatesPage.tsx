import { useEffect, useState } from "react";
import {
  fetchConfig,
  runUpdatesNow,
  setAutoUpdateAll,
  updateConfig,
  sortStacksByStatus,
  updateStackMetadata,
  type ContainerInfo,
  type Stack,
  type StackState,
  type StackStatus,
} from "../api";

interface UpdatesPageProps {
  stacks: Stack[];
  statuses: Record<string, StackState>;
  health: Record<string, StackStatus>;
  onStacksChanged: () => void;
}

export function UpdatesPage({
  stacks,
  statuses,
  health,
  onStacksChanged,
}: UpdatesPageProps) {
  const [checkEnabled, setCheckEnabled] = useState(true);
  const [autoUpdateTime, setAutoUpdateTime] = useState("03:00");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [runningNow, setRunningNow] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);
  const [bulkToggling, setBulkToggling] = useState(false);

  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        setCheckEnabled(Boolean(cfg.update_check_enabled ?? true));
        setAutoUpdateTime(String(cfg.auto_update_time || "03:00"));
      })
      .catch(() => {});
  }, []);

  async function save(patch: Record<string, unknown>) {
    setSaving(true);
    setSaveError(null);
    try {
      await updateConfig(patch);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "failed to save");
    } finally {
      setSaving(false);
    }
  }

  const checkableStacks = sortStacksByStatus(stacks, statuses).filter(
    (s) => !s.error,
  );
  const runningStacks = checkableStacks.filter(
    (s) => statuses[s.name] === "running",
  );
  const allAutoUpdate =
    runningStacks.length > 0 &&
    runningStacks.every((s) => Boolean(s.x_litethaus.auto_update));
  const someAutoUpdate = runningStacks.some((s) =>
    Boolean(s.x_litethaus.auto_update),
  );

  async function toggleAll(checked: boolean) {
    setBulkToggling(true);
    try {
      await setAutoUpdateAll(checked);
      onStacksChanged();
    } finally {
      setBulkToggling(false);
    }
  }

  async function handleRunNow() {
    if (
      !confirm(
        "Run auto-update now for every opted-in, running stack with a newer image available?",
      )
    )
      return;
    setRunningNow(true);
    setRunResult(null);
    try {
      const { results } = await runUpdatesNow();
      const failed = results.filter((r) => !r.ok);
      setRunResult(
        results.length === 0
          ? "no opted-in stacks had an update available"
          : failed.length === 0
            ? `updated ${results.length} stack${results.length === 1 ? "" : "s"}`
            : `updated ${results.length - failed.length}/${results.length} - failed: ${failed.map((r) => r.stack).join(", ")}`,
      );
      onStacksChanged();
    } catch (err) {
      setRunResult(err instanceof Error ? err.message : "failed to run");
    } finally {
      setRunningNow(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-6">
      <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">
            Settings
          </h2>
          <button
            onClick={handleRunNow}
            disabled={runningNow}
            className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {runningNow ? "Updating…" : "Update Now"}
          </button>
        </div>
        <p className="mb-3 text-xs text-neutral-500 dark:text-neutral-400">
          Replaces watchtower: every running stack is checked for newer images
          periodically. Auto-update (schedule or Update Now) only touches stacks
          opted in per-row below - every other stack stays check-only, updated
          by hand from its own Update button.
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={checkEnabled}
              onChange={(e) => {
                setCheckEnabled(e.target.checked);
                save({ update_check_enabled: e.target.checked });
              }}
            />
            Check for updates
          </label>
          <label className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-200">
            Auto-update run time
            <input
              type="time"
              value={autoUpdateTime}
              onChange={(e) => setAutoUpdateTime(e.target.value)}
              onBlur={() => save({ auto_update_time: autoUpdateTime })}
              disabled={!checkEnabled}
              className="rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none disabled:opacity-40 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
          </label>
          {saving && (
            <span className="text-xs text-neutral-400 dark:text-neutral-500">
              saving…
            </span>
          )}
          {saved && !saving && (
            <span className="text-xs text-green-600 dark:text-green-400">
              saved
            </span>
          )}
          {saveError && (
            <span className="text-xs text-red-600 dark:text-red-400">
              {saveError}
            </span>
          )}
          {runResult && (
            <span className="text-xs text-neutral-500 dark:text-neutral-400">
              {runResult}
            </span>
          )}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-xs uppercase text-neutral-400 dark:text-neutral-500">
          Stacks
        </h2>
        <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
                <th className="px-3 py-2">Stack</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Version</th>
                <th className="px-3 py-2">Last updated</th>
                <th className="px-3 py-2">Update</th>
                <th className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={allAutoUpdate}
                      ref={(el) => {
                        if (el)
                          el.indeterminate = !allAutoUpdate && someAutoUpdate;
                      }}
                      onChange={(e) => toggleAll(e.target.checked)}
                      disabled={runningStacks.length === 0 || bulkToggling}
                      title="Enable/disable auto-update for every running stack"
                    />
                    Auto-update
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {checkableStacks.map((stack) => (
                <UpdateRow
                  key={stack.name}
                  stack={stack}
                  status={statuses[stack.name] ?? null}
                  containers={health[stack.name]?.containers ?? []}
                  updateAvailable={
                    health[stack.name]?.update_available ?? false
                  }
                  onSaved={onStacksChanged}
                />
              ))}
              {checkableStacks.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-3 py-2 text-neutral-400 dark:text-neutral-500"
                  >
                    no stacks found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function imageTag(image: string): string {
  const noDigest = image.split("@")[0];
  const lastColon = noDigest.lastIndexOf(":");
  const lastSlash = noDigest.lastIndexOf("/");
  return lastColon > lastSlash ? noDigest.slice(lastColon + 1) : "latest";
}

function UpdateRow({
  stack,
  status,
  containers,
  updateAvailable,
  onSaved,
}: {
  stack: Stack;
  status: StackState | null;
  containers: ContainerInfo[];
  updateAvailable: boolean;
  onSaved: () => void;
}) {
  const autoUpdate = Boolean(stack.x_litethaus.auto_update);
  const running = status === "running";

  const tags = [
    ...new Set(containers.map((c) => imageTag(c.image)).filter(Boolean)),
  ];
  const version =
    tags.length === 0
      ? "—"
      : tags.length === 1
        ? tags[0]
        : `${tags.length} versions`;

  const created = containers
    .map((c) => c.created)
    .filter(Boolean)
    .sort()
    .at(-1);
  const lastUpdated = created ? new Date(created).toLocaleString() : "—";

  async function toggle(checked: boolean) {
    await updateStackMetadata(stack.name, { auto_update: checked || null });
    onSaved();
  }

  return (
    <tr className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
      <td className="px-3 py-1.5 text-neutral-700 dark:text-neutral-200">
        {stack.name}
      </td>
      <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">
        {status ?? "—"}
      </td>
      <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">
        {version}
      </td>
      <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">
        {lastUpdated}
      </td>
      <td className="px-3 py-1.5">
        {updateAvailable ? (
          <span className="text-amber-600 dark:text-amber-400">available</span>
        ) : (
          <span className="text-neutral-400 dark:text-neutral-500">
            up to date
          </span>
        )}
      </td>
      <td className="px-3 py-1.5">
        <input
          type="checkbox"
          checked={autoUpdate}
          onChange={(e) => toggle(e.target.checked)}
          disabled={!running}
          title={
            running
              ? "Automatically update this stack at the scheduled time when a newer image is available"
              : "start the stack to enable auto-update"
          }
        />
      </td>
    </tr>
  );
}
