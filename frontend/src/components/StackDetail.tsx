import { useEffect, useState } from 'react'
import { AlertTriangle, Box, ExternalLink } from 'lucide-react'
import {
  deleteStack,
  fetchStackRaw,
  logsSocketUrl,
  updateStackRaw,
  type ContainerInfo,
  type Stack,
  type StackState,
} from '../api'
import { HEALTH_BADGE, STATUS_BADGE } from '../statusStyles'
import { LogPanel } from './LogPanel'
import { Terminal } from './Terminal'

interface StackDetailProps {
  stack: Stack
  status: StackState | null
  containers: ContainerInfo[]
  busy: boolean
  onToggle: () => void
  onSaved: () => void
  onDeleted: () => void
}

const KNOWN_FIELDS = new Set(['domain', 'port', 'service', 'icon'])

export function StackDetail({ stack, status, containers, busy, onToggle, onSaved, onDeleted }: StackDetailProps) {
  const [lines, setLines] = useState<string[]>([])
  const [rawContent, setRawContent] = useState<string | null>(null)
  const [draftContent, setDraftContent] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  useEffect(() => {
    setLines([])
    const ws = new WebSocket(logsSocketUrl(stack.name))
    ws.onmessage = (event) => setLines((prev) => [...prev, event.data])
    return () => ws.close()
  }, [stack.name])

  useEffect(() => {
    setDeleteError(null)
    setSaveError(null)
    setRawContent(null)
    setDraftContent(null)
    fetchStackRaw(stack.name).then((content) => {
      setRawContent(content)
      setDraftContent(content)
    })
  }, [stack.name])

  async function handleSaveRaw() {
    if (draftContent === null) return
    setSaving(true)
    setSaveError(null)
    try {
      await updateStackRaw(stack.name, draftContent)
      setRawContent(draftContent)
      onSaved()
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'failed to save')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    if (!confirm(`Delete stack "${stack.name}"? This removes its directory from disk.`)) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteStack(stack.name)
      onDeleted()
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'failed to delete')
      setDeleting(false)
    }
  }

  const isDirty = draftContent !== null && draftContent !== rawContent
  const primaryContainer = containers.find((c) => c.state === 'running')?.name ?? containers[0]?.name ?? null

  const meta = stack.x_litethaus
  const domain = typeof meta.domain === 'string' ? meta.domain : null
  const port = meta.port != null ? String(meta.port) : null
  const service = typeof meta.service === 'string' ? meta.service : (stack.services[0] ?? null)
  const extraFields = Object.entries(meta).filter(([key]) => !KNOWN_FIELDS.has(key))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Box size={22} className="text-neutral-400 dark:text-neutral-500" />
          <h2 className="text-lg font-medium text-neutral-900 dark:text-neutral-100">{stack.name}</h2>
          {status && (
            <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_BADGE[status]}`}>{status}</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onToggle}
            disabled={busy || !!stack.error}
            className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {status === 'running' ? 'Stop' : 'Start'}
          </button>
          <button
            onClick={handleDelete}
            disabled={deleting || status !== 'stopped'}
            title={status !== 'stopped' ? 'stop the stack before deleting it' : undefined}
            className="rounded border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40"
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>

      {deleteError && (
        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle size={16} />
          {deleteError}
        </div>
      )}

      {stack.error && (
        <div className="flex items-start gap-2 rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">{stack.error}</pre>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Domain</dt>
          <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">
            {domain ? (
              <a
                href={`http://${domain}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 hover:text-neutral-900 dark:hover:text-neutral-100"
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
          <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Port</dt>
          <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{port ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Proxied service</dt>
          <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{service ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Services</dt>
          <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{stack.services.join(', ') || '—'}</dd>
        </div>
        <div className="col-span-2 sm:col-span-3">
          <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Compose file</dt>
          <dd className="mt-0.5 truncate font-mono text-xs text-neutral-500 dark:text-neutral-400">{stack.path}</dd>
        </div>
        {extraFields.map(([key, value]) => (
          <div key={key}>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">{key}</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{String(value)}</dd>
          </div>
        ))}
      </dl>

      {containers.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs uppercase text-neutral-400 dark:text-neutral-500">Containers</h3>
          <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-neutral-200 text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
                <tr>
                  <th className="px-3 py-2 font-normal">Container</th>
                  <th className="px-3 py-2 font-normal">State</th>
                  <th className="px-3 py-2 font-normal">Health</th>
                  <th className="px-3 py-2 font-normal">Restarts</th>
                </tr>
              </thead>
              <tbody>
                {containers.map((c) => {
                  const health = c.health ?? 'unknown'
                  return (
                    <tr key={c.name} className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
                      <td className="px-3 py-2 font-mono text-xs text-neutral-700 dark:text-neutral-200">{c.name}</td>
                      <td className="px-3 py-2 text-neutral-700 dark:text-neutral-200">{c.state}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`rounded-full border px-2 py-0.5 text-xs ${HEALTH_BADGE[health as keyof typeof HEALTH_BADGE] ?? HEALTH_BADGE.unknown}`}
                        >
                          {health}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-neutral-700 dark:text-neutral-200">{c.restart_count}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="grid h-[36rem] grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="flex min-h-0 flex-col gap-2 lg:col-span-1">
          <div className="flex items-center justify-between">
            <h3 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">compose.yaml</h3>
            <div className="flex items-center gap-2">
              {isDirty && <span className="text-xs text-neutral-400 dark:text-neutral-500">unsaved</span>}
              <button
                onClick={handleSaveRaw}
                disabled={!isDirty || saving}
                className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
          <textarea
            value={draftContent ?? ''}
            onChange={(e) => setDraftContent(e.target.value)}
            spellCheck={false}
            disabled={draftContent === null}
            className="min-h-0 flex-1 resize-none rounded border border-neutral-300 bg-white p-3 font-mono text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          {saveError && <p className="text-xs text-red-600 dark:text-red-400">{saveError}</p>}
        </div>

        <div className="flex min-h-0 flex-col gap-4 lg:col-span-2">
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            <h3 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Terminal</h3>
            <div className="min-h-0 flex-1">
              <Terminal stackName={stack.name} containerName={primaryContainer} />
            </div>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            <h3 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Logs</h3>
            <div className="min-h-0 flex-1">
              <LogPanel lines={lines} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
