import { useState } from 'react'
import { ChevronDown, ChevronRight, Folder, Settings as SettingsIcon } from 'lucide-react'
import type { Stack, StackState } from '../api'
import type { Route } from '../routing'
import { STATUS_DOT } from '../statusStyles'

interface SidebarProps {
  stacks: Stack[]
  statuses: Record<string, StackState>
  route: Route
  onSelectStack: (name: string | null) => void
  onOpenSettings: () => void
}

export function Sidebar({ stacks, statuses, route, onSelectStack, onOpenSettings }: SidebarProps) {
  const [expanded, setExpanded] = useState(true)
  const selected = route.view === 'stack' ? route.name : null

  return (
    <nav className="flex h-screen w-60 shrink-0 flex-col border-r border-neutral-800 bg-neutral-950 p-3">
      <div className="mb-4 px-2 text-sm font-semibold text-neutral-100">litethaus</div>

      <div className="flex items-center gap-1 rounded px-1 py-1.5 hover:bg-neutral-900">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="text-neutral-500 hover:text-neutral-300"
          aria-label={expanded ? 'Collapse Stacks' : 'Expand Stacks'}
        >
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <button
          onClick={() => onSelectStack(null)}
          className={`flex flex-1 items-center gap-1.5 text-left text-sm ${
            route.view === 'stacks' ? 'font-medium text-neutral-100' : 'text-neutral-300'
          }`}
        >
          <Folder size={14} className="text-neutral-500" />
          Stacks
        </button>
        <span className="pr-1 text-xs text-neutral-600">{stacks.length}</span>
      </div>

      {expanded && (
        <ul className="mt-0.5 ml-3 border-l border-neutral-800 pl-2">
          {stacks.map((stack) => (
            <li key={stack.name}>
              <button
                onClick={() => onSelectStack(stack.name)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left text-sm ${
                  selected === stack.name
                    ? 'bg-neutral-800 text-neutral-100'
                    : 'text-neutral-400 hover:bg-neutral-900 hover:text-neutral-200'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                    stack.error ? 'bg-red-500' : STATUS_DOT[statuses[stack.name] ?? 'stopped']
                  }`}
                />
                <span className="truncate">{stack.name}</span>
              </button>
            </li>
          ))}
          {stacks.length === 0 && <li className="px-2 py-1 text-xs text-neutral-600">no stacks found</li>}
        </ul>
      )}

      <div className="mt-auto border-t border-neutral-800 pt-2">
        <button
          onClick={onOpenSettings}
          className={`flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-sm ${
            route.view === 'settings'
              ? 'bg-neutral-800 font-medium text-neutral-100'
              : 'text-neutral-300 hover:bg-neutral-900'
          }`}
        >
          <SettingsIcon size={14} className="text-neutral-500" />
          Settings
        </button>
      </div>
    </nav>
  )
}
