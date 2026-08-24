import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { fetchConfig, updateConfig } from '../api'

const LAN_ONLY_RANGES = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']

interface SimpleRoute {
  key: string
  hosts: string[]
  dial: string
  lanOnly: boolean
  insecureTls: boolean
}

function parseSimpleRoute(route: unknown, index: number): SimpleRoute | null {
  if (typeof route !== 'object' || route === null) return null
  const r = route as Record<string, unknown>

  const match = r.match
  if (!Array.isArray(match) || match.length !== 1) return null
  const matcher = match[0] as Record<string, unknown>
  const hosts = matcher.host
  if (!Array.isArray(hosts) || hosts.length === 0 || !hosts.every((h) => typeof h === 'string' && h)) return null
  const matcherKeys = Object.keys(matcher).filter((k) => k !== 'host' && k !== 'remote_ip')
  if (matcherKeys.length > 0) return null

  let lanOnly = false
  if ('remote_ip' in matcher) {
    const remoteIp = matcher.remote_ip as Record<string, unknown> | undefined
    if (!remoteIp || !Array.isArray(remoteIp.ranges)) return null
    lanOnly = true
  }

  const handle = r.handle
  if (!Array.isArray(handle) || handle.length !== 1) return null
  const handler = handle[0] as Record<string, unknown>
  if (handler.handler !== 'reverse_proxy') return null
  const upstreams = handler.upstreams
  if (!Array.isArray(upstreams) || upstreams.length !== 1) return null
  const dial = (upstreams[0] as Record<string, unknown>)?.dial
  if (typeof dial !== 'string' || !dial) return null

  const handlerKeys = Object.keys(handler).filter((k) => k !== 'handler' && k !== 'upstreams' && k !== 'transport')
  if (handlerKeys.length > 0) return null

  let insecureTls = false
  if ('transport' in handler) {
    const transport = handler.transport as Record<string, unknown> | undefined
    const tls = transport?.tls as Record<string, unknown> | undefined
    if (transport?.protocol !== 'http' || tls?.insecure_skip_verify !== true || Object.keys(transport).length !== 2) {
      return null
    }
    insecureTls = true
  }

  return { key: `route-${index}`, hosts: hosts as string[], dial, lanOnly, insecureTls }
}

function buildRoute(route: SimpleRoute): unknown {
  const matcher: Record<string, unknown> = { host: route.hosts }
  if (route.lanOnly) matcher.remote_ip = { ranges: LAN_ONLY_RANGES }
  const handler: Record<string, unknown> = { handler: 'reverse_proxy', upstreams: [{ dial: route.dial }] }
  if (route.insecureTls) handler.transport = { protocol: 'http', tls: { insecure_skip_verify: true } }
  return { match: [matcher], handle: [handler] }
}

interface CaddyCustomRoutesTabProps {
  onSaved: () => void
}

export function CaddyCustomRoutesTab({ onSaved }: CaddyCustomRoutesTabProps) {
  const [routes, setRoutes] = useState<SimpleRoute[]>([])
  const [opaqueRoutes, setOpaqueRoutes] = useState<unknown[]>([])
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchConfig().then((cfg) => {
      const raw = String(cfg.caddy_extra_routes_json ?? '').trim()
      let parsed: unknown[] = []
      if (raw) {
        try {
          const arr = JSON.parse(raw)
          if (Array.isArray(arr)) parsed = arr
        } catch {
        }
      }
      const simple: SimpleRoute[] = []
      const opaque: unknown[] = []
      parsed.forEach((route, i) => {
        const s = parseSimpleRoute(route, i)
        if (s) simple.push(s)
        else opaque.push(route)
      })
      setRoutes(simple)
      setOpaqueRoutes(opaque)
      setLoaded(true)
    })
  }, [])

  function addRoute() {
    setRoutes((prev) => [...prev, { key: `new-${Date.now()}`, hosts: [], dial: '', lanOnly: false, insecureTls: false }])
  }

  function updateRoute(key: string, patch: Partial<SimpleRoute>) {
    setRoutes((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)))
  }

  function removeRoute(key: string) {
    setRoutes((prev) => prev.filter((r) => r.key !== key))
  }

  async function save() {
    setError(null)
    const complete = routes.filter((r) => r.hosts.length > 0 && r.dial.trim())
    if (complete.length !== routes.length) {
      setError('every route needs at least one host and a target')
      return
    }
    setSaving(true)
    setSaved(false)
    try {
      const combined = [...opaqueRoutes, ...complete.map(buildRoute)]
      await updateConfig({ caddy_extra_routes_json: JSON.stringify(combined) })
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) return <p className="text-sm text-neutral-400 dark:text-neutral-500">loading…</p>

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-neutral-400 dark:text-neutral-500">
        Route a domain to something that isn't a litehaus-managed stack - a VM, another host on your LAN, a router's
        admin page. For a stack's own container, set its domain on the stack itself instead.
      </p>

      <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
              <th className="px-3 py-2">Host(s)</th>
              <th className="px-3 py-2">Target (host:port)</th>
              <th className="px-3 py-2">LAN only</th>
              <th className="px-3 py-2">Self-signed HTTPS</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {routes.map((route) => (
              <tr key={route.key} className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
                <td className="px-3 py-1.5">
                  <input
                    value={route.hosts.join(', ')}
                    onChange={(e) =>
                      updateRoute(route.key, {
                        hosts: e.target.value
                          .split(',')
                          .map((h) => h.trim())
                          .filter(Boolean),
                      })
                    }
                    placeholder="ha.example.com"
                    className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  />
                </td>
                <td className="px-3 py-1.5">
                  <input
                    value={route.dial}
                    onChange={(e) => updateRoute(route.key, { dial: e.target.value })}
                    placeholder="192.168.1.8:8123"
                    className="w-full rounded border border-neutral-300 bg-white px-2 py-1 text-xs text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
                  />
                </td>
                <td className="px-3 py-1.5 text-center">
                  <input
                    type="checkbox"
                    checked={route.lanOnly}
                    onChange={(e) => updateRoute(route.key, { lanOnly: e.target.checked })}
                    title="Restrict to private/LAN IP ranges only"
                  />
                </td>
                <td className="px-3 py-1.5 text-center">
                  <input
                    type="checkbox"
                    checked={route.insecureTls}
                    onChange={(e) => updateRoute(route.key, { insecureTls: e.target.checked })}
                    title="Target serves HTTPS with a self-signed certificate (e.g. Proxmox, router admin UIs)"
                  />
                </td>
                <td className="px-3 py-1.5">
                  <button
                    onClick={() => removeRoute(route.key)}
                    aria-label="Remove route"
                    className="text-neutral-400 hover:text-red-600 dark:hover:text-red-400"
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
            {routes.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-2 text-neutral-400 dark:text-neutral-500">
                  no custom routes
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <button
        onClick={addRoute}
        className="flex w-fit items-center gap-1 rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
      >
        <Plus size={12} /> Add route
      </button>

      {opaqueRoutes.length > 0 && (
        <p className="text-xs text-neutral-400 dark:text-neutral-500">
          {opaqueRoutes.length} more route{opaqueRoutes.length === 1 ? '' : 's'} too complex to edit here (kept as-is)
          - use the Advanced tab.
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
        {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
      </div>
    </div>
  )
}
