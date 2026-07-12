import { AlertTriangle, Box, ExternalLink, ScrollText } from 'lucide-react'
import type { Stack, StackState } from '../api'

const STATE_STYLES: Record<StackState, string> = {
  running: 'bg-green-500/15 text-green-400 border-green-500/30',
  partial: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  stopped: 'bg-neutral-500/15 text-neutral-400 border-neutral-500/30',
}

interface StackCardProps {
  stack: Stack
  status: StackState | null
  busy: boolean
  onToggle: () => void
  onViewLogs: () => void
}

export function StackCard({ stack, status, busy, onToggle, onViewLogs }: StackCardProps) {
  const domain = typeof stack.x_litethaus.domain === 'string' ? stack.x_litethaus.domain : null

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-800 bg-neutral-900 p-4">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Box size={18} className="text-neutral-500" />
          <span className="font-medium text-neutral-100">{stack.name}</span>
        </div>
        {status && (
          <span className={`rounded-full border px-2 py-0.5 text-xs ${STATE_STYLES[status]}`}>{status}</span>
        )}
      </div>

      {stack.error ? (
        <div className="flex items-center gap-1.5 text-xs text-red-400">
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
          className="flex items-center gap-1 text-xs text-neutral-400 hover:text-neutral-200"
        >
          {domain}
          <ExternalLink size={12} />
        </a>
      ) : (
        <span className="text-xs text-neutral-600">no domain configured</span>
      )}

      <div className="mt-auto flex gap-2 pt-1">
        <button
          onClick={onToggle}
          disabled={busy || !!stack.error}
          className="flex-1 rounded border border-neutral-700 px-2 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
        >
          {status === 'running' ? 'Stop' : 'Start'}
        </button>
        <button
          onClick={onViewLogs}
          className="flex items-center gap-1 rounded border border-neutral-700 px-2 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800"
        >
          <ScrollText size={14} />
          Logs
        </button>
      </div>
    </div>
  )
}
