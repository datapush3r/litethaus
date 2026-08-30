import { useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Home,
  Folder,
  LogOut,
  Plus,
  RefreshCw,
  Settings as SettingsIcon,
  Waypoints,
} from "lucide-react";
import {
  sortStacksByStatus,
  type Stack,
  type StackState,
  type StackStatus,
} from "../api";
import type { Route } from "../routing";
import { BAD_HEALTH, STATUS_DOT } from "../statusStyles";
import { StackIcon } from "./StackIcon";

interface SidebarProps {
  stacks: Stack[];
  statuses: Record<string, StackState>;
  health: Record<string, StackStatus>;
  loading: boolean;
  route: Route;
  open: boolean;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSelectStack: (name: string | null) => void;
  onOpenHome: () => void;
  onOpenSettings: () => void;
  onOpenCaddy: () => void;
  onOpenUpdates: () => void;
  onNewStack: () => void;
  onLogout: () => void;
}

export function Sidebar({
  stacks,
  statuses,
  health,
  loading,
  route,
  open,
  collapsed,
  onToggleCollapsed,
  onSelectStack,
  onOpenHome,
  onOpenSettings,
  onOpenCaddy,
  onOpenUpdates,
  onNewStack,
  onLogout,
}: SidebarProps) {
  const [expanded, setExpanded] = useState(true);
  const selected = route.view === "stack" ? route.name : null;

  const sortedStacks = useMemo(
    () => sortStacksByStatus(stacks, statuses),
    [stacks, statuses],
  );

  return (
    <nav
      className={`fixed inset-y-0 left-0 z-40 flex h-screen shrink-0 flex-col border-r bg-white transition-all sm:static sm:translate-x-0 dark:bg-neutral-950 ${
        collapsed ? "w-12 p-2" : "w-60 p-3"
      } ${open ? "translate-x-0" : "-translate-x-full"}`}
      aria-hidden={collapsed || undefined}
    >
      <div className="mb-4 flex shrink-0 items-center gap-1">
        {collapsed ? (
          <button
            onClick={onOpenHome}
            aria-label="Home"
            title="Home"
            className={`flex flex-1 justify-center rounded p-2 ${
              route.view === "home"
                ? "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                : "text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-900"
            }`}
          >
            <Home size={16} />
          </button>
        ) : (
          <button
            onClick={onOpenHome}
            aria-label="Home"
            className={`flex-1 rounded px-2 py-1 text-left text-sm font-semibold ${
              route.view === "home"
                ? "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
            }`}
          >
            LITETHAUS
          </button>
        )}
      </div>

      {collapsed ? (
        <button
          onClick={() => onSelectStack(null)}
          title="Stacks"
          className={`flex shrink-0 items-center justify-center gap-1 rounded p-2 ${
            route.view === "stacks" || route.view === "stack"
              ? "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
              : "text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-900"
          }`}
        >
          <Folder size={16} />
        </button>
      ) : (
        <div className="flex items-center gap-1 rounded px-1 py-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-900">
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-300"
            aria-label={expanded ? "Collapse Stacks" : "Expand Stacks"}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
          <button
            onClick={() => onSelectStack(null)}
            className={`flex flex-1 items-center gap-1.5 text-left text-sm ${
              route.view === "stacks"
                ? "font-medium text-neutral-900 dark:text-neutral-100"
                : "text-neutral-600 dark:text-neutral-300"
            }`}
          >
            <Folder
              size={14}
              className="text-neutral-400 dark:text-neutral-500"
            />
            Stacks
          </button>
          <span className="pr-1 text-xs text-neutral-400 dark:text-neutral-600">
            {stacks.length}
          </span>
          <button
            onClick={onNewStack}
            className={`text-neutral-400 hover:text-neutral-700 dark:text-neutral-500 dark:hover:text-neutral-300 ${
              route.view === "new"
                ? "text-neutral-900 dark:text-neutral-100"
                : ""
            }`}
            aria-label="New stack"
          >
            <Plus size={14} />
          </button>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!collapsed && expanded && (
          <ul className="mt-0.5 ml-3 border-l border-neutral-200 pl-2 dark:border-neutral-800">
            {sortedStacks.map((stack) => (
              <li key={stack.name}>
                <button
                  onClick={() => onSelectStack(stack.name)}
                  className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm ${
                    selected === stack.name
                      ? "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                      : "text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800 dark:text-neutral-400 dark:hover:bg-neutral-900 dark:hover:text-neutral-200"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      stack.error
                        ? "bg-red-500"
                        : STATUS_DOT[statuses[stack.name] ?? "stopped"]
                    }`}
                  />
                  <StackIcon icon={stack.x_litethaus.icon} size={14} />
                  <span className="truncate">{stack.name}</span>
                  {health[stack.name] &&
                    BAD_HEALTH.has(health[stack.name].health) && (
                      <AlertTriangle
                        size={12}
                        className="ml-auto shrink-0 text-red-500"
                      />
                    )}
                </button>
              </li>
            ))}
            {!loading && stacks.length === 0 && (
              <li className="px-2 py-1 text-xs text-neutral-400 dark:text-neutral-600">
                no stacks found
              </li>
            )}
            {loading && (
              <li className="px-2 py-1 text-xs text-neutral-400 dark:text-neutral-600">
                loading…
              </li>
            )}
          </ul>
        )}
      </div>

      {collapsed ? (
        <div className="mt-auto flex shrink-0 flex-col items-center gap-1">
          <button
            onClick={onToggleCollapsed}
            title="Expand sidebar"
            aria-label="Expand sidebar"
            className="rounded p-2 text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-900"
          >
            <ChevronRight size={16} />
          </button>
          <RailButton
            label="Settings"
            active={route.view === "settings"}
            onClick={onOpenSettings}
          >
            <SettingsIcon size={16} />
          </RailButton>
          <RailButton
            label="Caddy"
            active={route.view === "caddy"}
            onClick={onOpenCaddy}
          >
            <Waypoints size={16} />
          </RailButton>
          <RailButton
            label="Updates"
            active={route.view === "updates"}
            onClick={onOpenUpdates}
          >
            <RefreshCw size={16} />
          </RailButton>
          <RailButton label="Log out" onClick={onLogout}>
            <LogOut size={16} />
          </RailButton>
        </div>
      ) : (
        <div className="mt-2 shrink-0 border-t border-neutral-200 pt-2 dark:border-neutral-800">
          <button
            onClick={onToggleCollapsed}
            aria-label="Collapse sidebar"
            className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
          >
            <ChevronLeft
              size={14}
              className="text-neutral-400 dark:text-neutral-500"
            />
            Collapse
          </button>
          <button
            onClick={onOpenSettings}
            className={`flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm ${
              route.view === "settings"
                ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
            }`}
          >
            <SettingsIcon
              size={14}
              className="text-neutral-400 dark:text-neutral-500"
            />
            Settings
          </button>
          <button
            onClick={onOpenCaddy}
            className={`flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm ${
              route.view === "caddy"
                ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
            }`}
          >
            <Waypoints
              size={14}
              className="text-neutral-400 dark:text-neutral-500"
            />
            Caddy
          </button>
          <button
            onClick={onOpenUpdates}
            className={`flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm ${
              route.view === "updates"
                ? "bg-neutral-100 font-medium text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
                : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
            }`}
          >
            <RefreshCw
              size={14}
              className="text-neutral-400 dark:text-neutral-500"
            />
            Updates
          </button>
          <button
            onClick={onLogout}
            className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm text-neutral-600 hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-900"
          >
            <LogOut
              size={14}
              className="text-neutral-400 dark:text-neutral-500"
            />
            Log out
          </button>
        </div>
      )}
    </nav>
  );
}

function RailButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`rounded p-2 ${
        active
          ? "bg-neutral-100 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100"
          : "text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-900"
      }`}
    >
      {children}
    </button>
  );
}
