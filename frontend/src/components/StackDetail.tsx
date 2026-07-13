import { useEffect, useState } from 'react'
import { AlertTriangle, ExternalLink } from 'lucide-react'
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels'
import {
  deleteStack,
  fetchStackRaw,
  logsSocketUrl,
  stackUrl,
  updateStackMetadata,
  updateStackRaw,
  type ContainerInfo,
  type Stack,
  type StackState,
} from '../api'
import { HEALTH_BADGE, STATUS_BADGE } from '../statusStyles'
import { formatYaml } from '../yamlFormat'
import { IconPicker } from './IconPicker'
import { LogPanel } from './LogPanel'
import { StackIcon } from './StackIcon'
import { TabBar } from './TabBar'
import { Terminal } from './Terminal'
import { YamlDiffView } from './YamlDiffView'
import { YamlEditor } from './YamlEditor'

interface StackDetailProps {
  stack: Stack
  httpsPort: number
  status: StackState | null
  containers: ContainerInfo[]
  busy: boolean
  onToggle: () => void
  onRestart: () => void
  onUpdate: () => void
  onSaved: () => void
  onDeleted: () => void
}

const KNOWN_FIELDS = new Set(['domain', 'port', 'service', 'icon'])

const H_HANDLE = 'mx-1 w-1 shrink-0 cursor-col-resize rounded bg-neutral-200 transition-colors hover:bg-neutral-400 data-[resize-handle-active]:bg-neutral-400 dark:bg-neutral-800 dark:hover:bg-neutral-600 dark:data-[resize-handle-active]:bg-neutral-600'
const V_HANDLE = 'my-1 h-1 shrink-0 cursor-row-resize rounded bg-neutral-200 transition-colors hover:bg-neutral-400 data-[resize-handle-active]:bg-neutral-400 dark:bg-neutral-800 dark:hover:bg-neutral-600 dark:data-[resize-handle-active]:bg-neutral-600'

export function StackDetail({
  stack,
  httpsPort,
  status,
  containers,
  busy,
  onToggle,
  onRestart,
  onUpdate,
  onSaved,
  onDeleted,
}: StackDetailProps) {
  const [lines, setLines] = useState<string[]>([])
  const [rawContent, setRawContent] = useState<string | null>(null)
  const [draftContent, setDraftContent] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [formatError, setFormatError] = useState<string | null>(null)
  const [confirmingSave, setConfirmingSave] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [selectedTerminalContainer, setSelectedTerminalContainer] = useState<string | null>(null)
  const [selectedLogsContainer, setSelectedLogsContainer] = useState<string | null>(null)
  const [activeFile, setActiveFile] = useState<string | null>(null)
  const [domainDraft, setDomainDraft] = useState('')
  const [portDraft, setPortDraft] = useState('')
  const [metaError, setMetaError] = useState<string | null>(null)
  const [iconPickerOpen, setIconPickerOpen] = useState(false)

  const meta = stack.x_litethaus
  const domain = typeof meta.domain === 'string' ? meta.domain : null
  const port = meta.port != null ? String(meta.port) : null
  const icon = typeof meta.icon === 'string' ? meta.icon : ''
  const service = typeof meta.service === 'string' ? meta.service : (stack.services[0] ?? null)
  const extraFields = Object.entries(meta).filter(([key]) => !KNOWN_FIELDS.has(key))

  const primaryContainer = containers.find((c) => c.state === 'running')?.name ?? containers[0]?.name ?? null
  const activeTerminalContainer = containers.some((c) => c.name === selectedTerminalContainer)
    ? selectedTerminalContainer
    : primaryContainer
  const activeLogsContainer = containers.some((c) => c.name === selectedLogsContainer)
    ? selectedLogsContainer
    : primaryContainer
  const effectiveFile = stack.compose_files.includes(activeFile ?? '') ? activeFile : (stack.compose_files[0] ?? null)

  useEffect(() => {
    setLines([])
    const ws = new WebSocket(logsSocketUrl(stack.name, activeLogsContainer))
    ws.onmessage = (event) => setLines((prev) => [...prev, event.data])
    return () => ws.close()
  }, [stack.name, activeLogsContainer])

  useEffect(() => {
    setDeleteError(null)
    setSaveError(null)
    setFormatError(null)
    setConfirmingSave(false)
    setRawContent(null)
    setDraftContent(null)
    fetchStackRaw(stack.name, effectiveFile ?? undefined).then((content) => {
      setRawContent(content)
      setDraftContent(content)
    })
  }, [stack.name, effectiveFile])

  useEffect(() => {
    setDomainDraft(domain ?? '')
    setPortDraft(port ?? '')
    setMetaError(null)
    setIconPickerOpen(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stack.name])

  async function saveMetadata(patch: { icon?: string | null; port?: number | null; domain?: string | null }) {
    setMetaError(null)
    try {
      await updateStackMetadata(stack.name, patch)
      onSaved()
      // keep the raw YAML editor in sync, but only if the user has no unsaved edits in it
      if (draftContent === rawContent) {
        const content = await fetchStackRaw(stack.name, effectiveFile ?? undefined)
        setRawContent(content)
        setDraftContent(content)
      }
    } catch (err) {
      setMetaError(err instanceof Error ? err.message : 'failed to save')
    }
  }

  function handleDomainBlur() {
    const next = domainDraft.trim()
    if (next === (domain ?? '')) return
    saveMetadata({ domain: next || null })
  }

  function handlePortBlur() {
    const next = portDraft.trim()
    if (next === (port ?? '')) return
    if (next === '') {
      saveMetadata({ port: null })
      return
    }
    const parsed = Number(next)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
      setMetaError('port must be a whole number between 1 and 65535')
      setPortDraft(port ?? '')
      return
    }
    saveMetadata({ port: parsed })
  }

  function handleIconSelect(slug: string) {
    setIconPickerOpen(false)
    if (slug === icon) return
    saveMetadata({ icon: slug || null })
  }

  function handleFormat() {
    if (draftContent === null) return
    const formatted = formatYaml(draftContent)
    if (formatted === null) {
      setFormatError('fix YAML errors before formatting')
      return
    }
    setFormatError(null)
    setDraftContent(formatted)
  }

  async function handleConfirmSave() {
    if (draftContent === null) return
    setSaving(true)
    setSaveError(null)
    try {
      await updateStackRaw(stack.name, draftContent, effectiveFile ?? undefined)
      setRawContent(draftContent)
      setConfirmingSave(false)
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

  const hasContainers = containers.length > 0

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setIconPickerOpen(true)}
            title="Change icon"
            className="rounded transition-opacity hover:opacity-70"
          >
            <StackIcon icon={meta.icon} size={22} />
          </button>
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
            onClick={onRestart}
            disabled={busy || !!stack.error || status !== 'running'}
            title={status !== 'running' ? 'start the stack before restarting it' : undefined}
            className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            Restart
          </button>
          <button
            onClick={onUpdate}
            disabled={busy || !!stack.error}
            title="Pull latest images and recreate containers"
            className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            Update
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <dl className={`grid grid-cols-2 gap-x-6 gap-y-3 text-sm ${hasContainers ? '' : 'lg:col-span-2 sm:grid-cols-3'}`}>
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Domain</dt>
            <dd className="mt-0.5 flex items-center gap-1 text-neutral-700 dark:text-neutral-200">
              <input
                type="text"
                value={domainDraft}
                onChange={(e) => setDomainDraft(e.target.value)}
                onBlur={handleDomainBlur}
                placeholder="not set"
                className="w-full min-w-0 rounded border border-transparent bg-transparent px-1 py-0.5 outline-none placeholder:text-neutral-400 hover:border-neutral-300 focus:border-neutral-400 dark:placeholder:text-neutral-600 dark:hover:border-neutral-700 dark:focus:border-neutral-600"
              />
              {domain && (
                <a
                  href={stackUrl(domain, httpsPort)}
                  target="_blank"
                  rel="noreferrer"
                  className="shrink-0 text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200"
                >
                  <ExternalLink size={12} />
                </a>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Port</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">
              <input
                type="text"
                inputMode="numeric"
                value={portDraft}
                onChange={(e) => setPortDraft(e.target.value)}
                onBlur={handlePortBlur}
                placeholder="not set"
                className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 outline-none placeholder:text-neutral-400 hover:border-neutral-300 focus:border-neutral-400 dark:placeholder:text-neutral-600 dark:hover:border-neutral-700 dark:focus:border-neutral-600"
              />
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Proxied service</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{service ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Services</dt>
            <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{stack.services.join(', ') || '—'}</dd>
          </div>
          {extraFields.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs uppercase text-neutral-400 dark:text-neutral-500">{key}</dt>
              <dd className="mt-0.5 text-neutral-700 dark:text-neutral-200">{String(value)}</dd>
            </div>
          ))}
        </dl>

        {hasContainers && (
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
      </div>

      {metaError && (
        <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle size={16} />
          {metaError}
        </div>
      )}

      {iconPickerOpen && (
        <IconPicker value={icon} onSelect={handleIconSelect} onClose={() => setIconPickerOpen(false)} />
      )}

      <PanelGroup direction="horizontal" autoSaveId="litethaus-stackdetail-h" className="min-h-[24rem] flex-1">
        <Panel defaultSize={35} minSize={20}>
          <div className="flex h-full min-h-0 flex-col gap-2 pr-1">
            <div className="flex items-center justify-between gap-2">
              {confirmingSave ? (
                <h3 className="shrink-0 text-xs uppercase text-neutral-400 dark:text-neutral-500">Review changes</h3>
              ) : stack.compose_files.length > 1 ? (
                <TabBar
                  items={stack.compose_files}
                  active={effectiveFile}
                  onSelect={setActiveFile}
                  titles={
                    stack.override_file
                      ? { [stack.override_file]: 'Automatically merged over the primary file at runtime' }
                      : undefined
                  }
                />
              ) : (
                <h3 className="shrink-0 text-xs uppercase text-neutral-400 dark:text-neutral-500">
                  {stack.compose_files[0] ?? 'compose.yaml'}
                </h3>
              )}
              <div className="flex shrink-0 items-center gap-2">
                {isDirty && !confirmingSave && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">unsaved</span>
                )}
                {confirmingSave ? (
                  <>
                    <button
                      onClick={() => setConfirmingSave(false)}
                      disabled={saving}
                      className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    >
                      Keep editing
                    </button>
                    <button
                      onClick={handleConfirmSave}
                      disabled={saving}
                      className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    >
                      {saving ? 'Saving…' : 'Confirm & Save'}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={handleFormat}
                      disabled={draftContent === null}
                      className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    >
                      Format
                    </button>
                    <button
                      onClick={() => setConfirmingSave(true)}
                      disabled={!isDirty}
                      className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
                    >
                      Save
                    </button>
                  </>
                )}
              </div>
            </div>
            {draftContent === null ? (
              <div className="flex min-h-0 flex-1 items-center justify-center rounded border border-neutral-200 text-xs text-neutral-400 dark:border-neutral-800 dark:text-neutral-600">
                Loading…
              </div>
            ) : confirmingSave ? (
              <YamlDiffView
                original={rawContent ?? ''}
                modified={draftContent}
                className="min-h-0 flex-1 overflow-auto rounded border border-neutral-300 text-xs dark:border-neutral-700"
              />
            ) : (
              <YamlEditor
                value={draftContent}
                onChange={setDraftContent}
                className="min-h-0 flex-1 overflow-auto rounded border border-neutral-300 text-xs dark:border-neutral-700"
              />
            )}
            {formatError && <p className="text-xs text-red-600 dark:text-red-400">{formatError}</p>}
            {saveError && <p className="text-xs text-red-600 dark:text-red-400">{saveError}</p>}
          </div>
        </Panel>

        <PanelResizeHandle className={H_HANDLE} />

        <Panel defaultSize={65} minSize={30}>
          <PanelGroup direction="vertical" autoSaveId="litethaus-stackdetail-v" className="pl-1">
            <Panel defaultSize={50} minSize={15}>
              <div className="flex h-full min-h-0 flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="shrink-0 text-xs uppercase text-neutral-400 dark:text-neutral-500">Terminal</h3>
                  <TabBar
                    items={containers.map((c) => c.name)}
                    active={activeTerminalContainer}
                    onSelect={setSelectedTerminalContainer}
                  />
                </div>
                <div className="min-h-0 flex-1">
                  <Terminal stackName={stack.name} containerName={activeTerminalContainer} />
                </div>
              </div>
            </Panel>

            <PanelResizeHandle className={V_HANDLE} />

            <Panel defaultSize={50} minSize={15}>
              <div className="flex h-full min-h-0 flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="shrink-0 text-xs uppercase text-neutral-400 dark:text-neutral-500">Logs</h3>
                  <TabBar
                    items={containers.map((c) => c.name)}
                    active={activeLogsContainer}
                    onSelect={setSelectedLogsContainer}
                  />
                </div>
                <div className="min-h-0 flex-1">
                  <LogPanel lines={lines} />
                </div>
              </div>
            </Panel>
          </PanelGroup>
        </Panel>
      </PanelGroup>
    </div>
  )
}
