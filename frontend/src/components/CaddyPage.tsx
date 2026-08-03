import { useEffect, useState } from 'react'
import { Copy, RefreshCw } from 'lucide-react'
import {
  fetchCaddyConfig,
  fetchCaddyLive,
  fetchCaddyStatus,
  fetchConfig,
  updateConfig,
  updateStackMetadata,
  type CaddyStatus,
  type Stack,
} from '../api'

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

  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [extraRoutesJson, setExtraRoutesJson] = useState('')
  const [extraRoutesError, setExtraRoutesError] = useState<string | null>(null)
  const [savingExtraRoutes, setSavingExtraRoutes] = useState(false)
  const [extraRoutesSaved, setExtraRoutesSaved] = useState(false)

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
    fetchConfig().then((cfg) => setExtraRoutesJson(String(cfg.caddy_extra_routes_json ?? '')))
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

  const routableStacks = stacks.filter((s) => !s.error)

  function onRowSaved() {
    onStacksChanged()
    loadConfig()
  }

  return (
    <div className="flex max-w-3xl flex-col gap-6">
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

      <div>
        <h2 className="mb-2 text-xs uppercase text-neutral-400 dark:text-neutral-500">Stack routes</h2>
        <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
                <th className="px-3 py-2">Stack</th>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">Service</th>
                <th className="px-3 py-2">Port</th>
              </tr>
            </thead>
            <tbody>
              {routableStacks.map((stack) => (
                <RouteRow key={stack.name} stack={stack} onSaved={onRowSaved} />
              ))}
              {routableStacks.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-3 py-2 text-neutral-400 dark:text-neutral-500">
                    no stacks found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div>
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
          <pre className="max-h-96 overflow-auto rounded border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
            {JSON.stringify(generatedConfig, null, 2)}
          </pre>
        )}

        <button
          onClick={toggleLive}
          className="mt-3 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          {liveOpen ? 'Hide' : 'Show'} live config on Caddy
        </button>
        {liveOpen && (
          <div className="mt-2">
            {liveLoading && <p className="text-sm text-neutral-400 dark:text-neutral-500">loading…</p>}
            {liveError && <p className="text-sm text-red-600 dark:text-red-400">{liveError}</p>}
            {liveConfig && (
              <pre className="max-h-96 overflow-auto rounded border border-neutral-200 bg-neutral-50 p-3 text-xs text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
                {JSON.stringify(liveConfig, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>

      <div className="border-t border-neutral-200 pt-4 dark:border-neutral-800">
        <button
          onClick={() => setAdvancedOpen((o) => !o)}
          className="text-xs uppercase text-neutral-400 dark:text-neutral-500"
        >
          {advancedOpen ? '▾' : '▸'} Advanced: raw route passthrough
        </button>
        {advancedOpen && (
          <div className="mt-2 flex flex-col gap-2">
            <p className="text-xs text-neutral-400 dark:text-neutral-500">
              Raw Caddy route objects (JSON array), appended after the routes generated above. Leave blank to skip.
              Invalid JSON is ignored rather than breaking sync.
            </p>
            <textarea
              value={extraRoutesJson}
              onChange={(e) => setExtraRoutesJson(e.target.value)}
              rows={6}
              placeholder='[{"match": [{"host": ["extra.example.com"]}], "handle": [...]}]'
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 font-mono text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <div className="flex items-center gap-3">
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
    </div>
  )
}

function RouteRow({ stack, onSaved }: { stack: Stack; onSaved: () => void }) {
  const meta = stack.x_litethaus
  const domain = typeof meta.domain === 'string' ? meta.domain : null
  const port = meta.port != null ? String(meta.port) : null
  const service = typeof meta.service === 'string' ? meta.service : (stack.services[0] ?? '')

  const [domainDraft, setDomainDraft] = useState(domain ?? '')
  const [portDraft, setPortDraft] = useState(port ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDomainDraft(domain ?? '')
    setPortDraft(port ?? '')
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stack.name, domain, port])

  async function save(patch: { domain?: string | null; port?: number | null; service?: string | null }) {
    setError(null)
    try {
      await updateStackMetadata(stack.name, patch)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to save')
    }
  }

  function handleDomainBlur() {
    const next = domainDraft.trim()
    if (next === (domain ?? '')) return
    save({ domain: next || null })
  }

  function handlePortBlur() {
    const next = portDraft.trim()
    if (next === (port ?? '')) return
    if (next === '') {
      save({ port: null })
      return
    }
    const parsed = Number(next)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 65535) {
      setError('port must be a whole number between 1 and 65535')
      setPortDraft(port ?? '')
      return
    }
    save({ port: parsed })
  }

  return (
    <tr className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
      <td className="px-3 py-1.5 text-neutral-700 dark:text-neutral-200">{stack.name}</td>
      <td className="px-3 py-1.5">
        <input
          value={domainDraft}
          onChange={(e) => setDomainDraft(e.target.value)}
          onBlur={handleDomainBlur}
          placeholder="not proxied"
          className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </td>
      <td className="px-3 py-1.5">
        <select
          value={service}
          onChange={(e) => save({ service: e.target.value || null })}
          className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          {stack.services.map((svc) => (
            <option key={svc} value={svc}>
              {svc}
            </option>
          ))}
        </select>
      </td>
      <td className="px-3 py-1.5">
        <input
          value={portDraft}
          onChange={(e) => setPortDraft(e.target.value)}
          onBlur={handlePortBlur}
          placeholder="—"
          className="w-20 rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
      </td>
    </tr>
  )
}
