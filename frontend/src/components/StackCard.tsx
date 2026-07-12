import { AlertTriangle, Box, ExternalLink } from 'lucide-react'
import type { Stack, StackState } from '../api'
import { STATUS_BADGE } from '../statusStyles'

interface StackCardProps {
  stack: Stack
  status: StackState | null
  busy: boolean
  onToggle: () => void
  onOpen: () => void
}

export function StackCard({ stack, status, busy, onToggle, onOpen }: StackCardProps) {
  const domain = typeof stack.x_litethaus.domain === 'string' ? stack.x_litethaus.domain : null

  return (
    <div
      onClick={onOpen}
      className="flex cursor-pointer flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 hover:border-neutral-300 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Box size={18} className="text-neutral-400 dark:text-neutral-500" />
          <span className="font-medium text-neutral-900 dark:text-neutral-100">{stack.name}</span>
        </div>
        {status && (
          <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_BADGE[status]}`}>{status}</span>
        )}
      </div>

      {stack.error ? (
        <div className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
          <AlertTriangle size={14} />
          <span className="truncate" title={stack.error}>
            {stack.error}
          </span>
        </div>
      ) : domain ? (
        <a
          href={`http://${domain}`}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          {domain}
          <ExternalLink size={12} />
        </a>
      ) : (
        <span className="text-xs text-neutral-400 dark:text-neutral-600">no domain configured</span>
      )}

      <div className="mt-auto pt-1">
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          disabled={busy || !!stack.error}
          className="w-full rounded border border-neutral-300 px-2 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {status === 'running' ? 'Stop' : 'Start'}
        </button>
      </div>
    </div>
  )
}
