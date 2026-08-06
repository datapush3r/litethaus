import { useEffect, useState } from 'react'
import { caddyLogsSocketUrl, fetchConfig, updateConfig } from '../api'
import { LogPanel } from './LogPanel'

export function CaddyLogsTab() {
  const [lines, setLines] = useState<string[]>([])
  const [enabled, setEnabled] = useState(false)
  const [toggling, setToggling] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchConfig().then((cfg) => setEnabled(Boolean(cfg.caddy_access_log_enabled)))
  }, [])

  useEffect(() => {
    setError(null)
    const ws = new WebSocket(caddyLogsSocketUrl())
    ws.onmessage = (event) => setLines((prev) => [...prev, event.data])
    ws.onclose = (event) => {
      if (event.code === 4004) setError('Caddy container not found — is the bundled Caddy running?')
      else if (event.code === 4401) setError('Session expired — reload the page')
    }
    return () => ws.close()
  }, [])

  async function toggle() {
    setToggling(true)
    try {
      const cfg = await updateConfig({ caddy_access_log_enabled: !enabled })
      setEnabled(Boolean(cfg.caddy_access_log_enabled))
    } finally {
      setToggling(false)
    }
  }

  return (
    <div className="flex h-full min-h-64 flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Access logs</h2>
        <label className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
          <input type="checkbox" checked={enabled} disabled={toggling} onChange={toggle} />
          Log every request
        </label>
      </div>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {!enabled && (
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          Access logging is off - Caddy's own error/startup log still streams below, but requests won't be logged
          until enabled.
        </p>
      )}
      <div className="flex-1 min-h-0">
        <LogPanel lines={lines} />
      </div>
    </div>
  )
}
