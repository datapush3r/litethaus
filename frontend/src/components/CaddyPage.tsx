import { useEffect, useState } from 'react'
import { Copy, RefreshCw } from 'lucide-react'
import {
  fetchCaddyConfig,
  fetchCaddyLive,
  fetchCaddyStatus,
  fetchConfig,
  updateConfig,
  type CaddyStatus,
  type Stack,
} from '../api'
import { CaddyCertificatesTab } from './CaddyCertificatesTab'
import { CaddyLogsTab } from './CaddyLogsTab'
import { CaddyRoutesTab } from './CaddyRoutesTab'
import { JsonEditor } from './JsonEditor'
import { TabBar } from './TabBar'

// Config is stored as compact JSON; reformat it for humans to read/edit.
// Falls back to the raw string on parse failure - errors show up in the editor's lint gutter instead.
function prettify(raw: string): string {
  if (!raw.trim()) return raw
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

interface CaddyPageProps {
  stacks: Stack[]
  onStacksChanged: () => void
}

export function CaddyPage({ stacks, onStacksChanged }: CaddyPageProps) {
  const [status, setStatus] = useState<CaddyStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [generatedConfig, setGeneratedConfig] = useState<Record<string, unknown> | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)

  const [liveOpen, setLiveOpen] = useState(false)
  const [liveLoading, setLiveLoading] = useState(false)
  const [liveConfig, setLiveConfig] = useState<Record<string, unknown> | null>(null)
  const [liveError, setLiveError] = useState<string | null>(null)

  const [extraRoutesJson, setExtraRoutesJson] = useState('')
  const [extraRoutesError, setExtraRoutesError] = useState<string | null>(null)
  const [savingExtraRoutes, setSavingExtraRoutes] = useState(false)
  const [extraRoutesSaved, setExtraRoutesSaved] = useState(false)

  const TABS = ['Overview', 'Routes', 'TLS Certificates', 'Access Logs', 'Advanced']
  const [tab, setTab] = useState(TABS[0])

  function loadStatus() {
    setStatusError(null)
    fetchCaddyStatus()
      .then(setStatus)
      .catch((err) => setStatusError(err instanceof Error ? err.message : 'failed to load status'))
  }

  function loadConfig() {
    setConfigError(null)
    fetchCaddyConfig()
      .then(setGeneratedConfig)
      .catch((err) => setConfigError(err instanceof Error ? err.message : 'failed to load config'))
  }

  useEffect(() => {
    loadStatus()
    loadConfig()
    fetchConfig().then((cfg) => setExtraRoutesJson(prettify(String(cfg.caddy_extra_routes_json ?? ''))))
  }, [])

  function loadLive() {
    setLiveLoading(true)
    setLiveError(null)
    fetchCaddyLive()
      .then(setLiveConfig)
      .catch((err) => setLiveError(err instanceof Error ? err.message : 'Caddy unreachable'))
      .finally(() => setLiveLoading(false))
  }

  function toggleLive() {
    const next = !liveOpen
    setLiveOpen(next)
    if (next && liveConfig === null && !liveLoading) loadLive()
  }

  async function copyGenerated() {
    if (generatedConfig) await navigator.clipboard.writeText(JSON.stringify(generatedConfig, null, 2))
  }

  async function saveExtraRoutes() {
    setExtraRoutesError(null)
    if (extraRoutesJson.trim()) {
      try {
        const parsed = JSON.parse(extraRoutesJson)
        if (!Array.isArray(parsed)) throw new Error('must be a JSON array')
      } catch (err) {
        setExtraRoutesError(err instanceof Error ? err.message : 'invalid JSON')
        return
      }
    }
    setSavingExtraRoutes(true)
    setExtraRoutesSaved(false)
    try {
      await updateConfig({ caddy_extra_routes_json: extraRoutesJson })
      setExtraRoutesSaved(true)
      loadStatus()
      loadConfig()
    } catch (err) {
      setExtraRoutesError(err instanceof Error ? err.message : 'failed to save')
    } finally {
      setSavingExtraRoutes(false)
    }
  }

  function onRowSaved() {
    onStacksChanged()
    loadConfig()
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-col gap-4">
      <TabBar items={TABS} active={tab} onSelect={setTab} />

      {tab === 'Overview' && (
        <div className="flex min-h-0 flex-1 flex-col gap-6">
          <div className="rounded border border-neutral-200 p-3 dark:border-neutral-800">
            <div className="flex items-center justify-between">
              <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Sync status</h2>
              <button
                onClick={loadStatus}
                aria-label="Refresh status"
                className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-300"
              >
                <RefreshCw size={14} />
              </button>
            </div>
            {statusError && <p className="mt-1 text-sm text-red-600 dark:text-red-400">{statusError}</p>}
            {status && (
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                <span
                  className={
                    status.enabled ? 'text-neutral-700 dark:text-neutral-200' : 'text-neutral-400 dark:text-neutral-500'
                  }
                >
                  {status.enabled ? 'Caddy management enabled' : 'Caddy management disabled'}
                </span>
                {status.enabled && status.ok !== undefined && (
                  <span className={status.ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}>
                    {status.ok ? 'last sync ok' : `last sync failed: ${status.error}`}
                  </span>
                )}
                {status.at && (
                  <span className="text-xs text-neutral-400 dark:text-neutral-500">{new Date(status.at).toLocaleString()}</span>
                )}
              </div>
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Generated Caddy config</h2>
              <button
                onClick={copyGenerated}
                className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
              >
                <Copy size={12} /> Copy
              </button>
            </div>
            {configError && <p className="text-sm text-red-600 dark:text-red-400">{configError}</p>}
            {generatedConfig && (
              <div className="min-h-0 flex-1">
                <JsonEditor
                  value={JSON.stringify(generatedConfig, null, 2)}
                  readOnly
                  className="h-full rounded border border-neutral-200 dark:border-neutral-800"
                />
              </div>
            )}

            <button
              onClick={toggleLive}
              className="mt-3 shrink-0 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
            >
              {liveOpen ? 'Hide' : 'Show'} live config on Caddy
            </button>
            {liveOpen && (
              <div className="mt-2 flex min-h-0 flex-1 flex-col">
                {liveLoading && <p className="text-sm text-neutral-400 dark:text-neutral-500">loading…</p>}
                {liveError && <p className="text-sm text-red-600 dark:text-red-400">{liveError}</p>}
                {liveConfig && (
                  <div className="min-h-0 flex-1">
                    <JsonEditor
                      value={JSON.stringify(liveConfig, null, 2)}
                      readOnly
                      className="h-full rounded border border-neutral-200 dark:border-neutral-800"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'Routes' && <CaddyRoutesTab stacks={stacks} onStacksChanged={onRowSaved} />}
      {tab === 'TLS Certificates' && <CaddyCertificatesTab />}
      {tab === 'Access Logs' && (
        <div className="min-h-0 flex-1">
          <CaddyLogsTab />
        </div>
      )}

      {tab === 'Advanced' && (
        <div className="flex min-h-0 flex-1 flex-col">
          <p className="mb-2 shrink-0 text-xs text-neutral-400 dark:text-neutral-500">
            Raw Caddy route objects (JSON array), appended after the routes generated in the Routes tab. Leave blank
            to skip. Invalid JSON is ignored rather than breaking sync.
          </p>
          <div className="min-h-0 flex-1">
            <JsonEditor
              value={extraRoutesJson}
              onChange={setExtraRoutesJson}
              className="h-full w-full rounded border border-neutral-300 dark:border-neutral-700"
            />
          </div>
          <div className="mt-2 flex shrink-0 items-center gap-3">
            <button
              onClick={saveExtraRoutes}
              disabled={savingExtraRoutes}
              className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
            >
              {savingExtraRoutes ? 'Saving…' : 'Save'}
            </button>
            {extraRoutesSaved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
            {extraRoutesError && <span className="text-xs text-red-600 dark:text-red-400">{extraRoutesError}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
