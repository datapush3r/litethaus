import { useEffect, useState } from 'react'
import { AlertTriangle, Box, ExternalLink } from 'lucide-react'
import { logsSocketUrl, type Stack, type StackState } from '../api'
import { STATUS_BADGE } from '../statusStyles'
import { LogPanel } from './LogPanel'

interface StackDetailProps {
  stack: Stack
  status: StackState | null
  busy: boolean
  onToggle: () => void
}

const KNOWN_FIELDS = new Set(['domain', 'port', 'service', 'icon'])

export function StackDetail({ stack, status, busy, onToggle }: StackDetailProps) {
  const [lines, setLines] = useState<string[]>([])

  useEffect(() => {
    setLines([])
    const ws = new WebSocket(logsSocketUrl(stack.name))
    ws.onmessage = (event) => setLines((prev) => [...prev, event.data])
    return () => ws.close()
  }, [stack.name])

  const meta = stack.x_litethaus
  const domain = typeof meta.domain === 'string' ? meta.domain : null
  const port = meta.port != null ? String(meta.port) : null
  const service = typeof meta.service === 'string' ? meta.service : (stack.services[0] ?? null)
  const extraFields = Object.entries(meta).filter(([key]) => !KNOWN_FIELDS.has(key))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Box size={22} className="text-neutral-500" />
          <h2 className="text-lg font-medium text-neutral-100">{stack.name}</h2>
          {status && (
            <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_BADGE[status]}`}>{status}</span>
          )}
        </div>
        <button
          onClick={onToggle}
          disabled={busy || !!stack.error}
          className="rounded border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
        >
          {status === 'running' ? 'Stop' : 'Start'}
        </button>
      </div>

      {stack.error && (
        <div className="flex items-start gap-2 rounded border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">{stack.error}</pre>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase text-neutral-500">Domain</dt>
          <dd className="mt-0.5 text-neutral-200">
            {domain ? (
              <a
                href={`http://${domain}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 hover:text-neutral-100"
              >
                {domain}
                <ExternalLink size={12} />
              </a>
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-neutral-500">Port</dt>
          <dd className="mt-0.5 text-neutral-200">{port ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-neutral-500">Proxied service</dt>
          <dd className="mt-0.5 text-neutral-200">{service ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-neutral-500">Services</dt>
          <dd className="mt-0.5 text-neutral-200">{stack.services.join(', ') || '—'}</dd>
        </div>
        <div className="col-span-2 sm:col-span-3">
          <dt className="text-xs uppercase text-neutral-500">Compose file</dt>
          <dd className="mt-0.5 truncate font-mono text-xs text-neutral-400">{stack.path}</dd>
        </div>
        {extraFields.map(([key, value]) => (
          <div key={key}>
            <dt className="text-xs uppercase text-neutral-500">{key}</dt>
            <dd className="mt-0.5 text-neutral-200">{String(value)}</dd>
          </div>
        ))}
      </dl>

      <div>
        <h3 className="mb-2 text-xs uppercase text-neutral-500">Logs</h3>
        <LogPanel lines={lines} />
      </div>
    </div>
  )
}
