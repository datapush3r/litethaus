import { useEffect, useState } from 'react'
import { fetchCaddyUpstreams, updateStackMetadata, type CaddyUpstream, type Stack } from '../api'

interface CaddyRoutesTabProps {
  stacks: Stack[]
  onStacksChanged: () => void
}

export function CaddyRoutesTab({ stacks, onStacksChanged }: CaddyRoutesTabProps) {
  const [upstreams, setUpstreams] = useState<CaddyUpstream[]>([])

  function loadUpstreams() {
    fetchCaddyUpstreams()
      .then(setUpstreams)
      .catch(() => setUpstreams([]))
  }

  useEffect(() => {
    loadUpstreams()
    const interval = setInterval(loadUpstreams, 10000)
    return () => clearInterval(interval)
  }, [])

  const routableStacks = stacks.filter((s) => !s.error)

  function onRowSaved() {
    onStacksChanged()
    loadUpstreams()
  }

  return (
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
              <th className="px-3 py-2">LAN only</th>
              <th className="px-3 py-2">Health</th>
              <th className="px-3 py-2">Active</th>
            </tr>
          </thead>
          <tbody>
            {routableStacks.map((stack) => (
              <RouteRow key={stack.name} stack={stack} upstreams={upstreams} onSaved={onRowSaved} />
            ))}
            {routableStacks.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-2 text-neutral-400 dark:text-neutral-500">
                  no stacks found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RouteRow({
  stack,
  upstreams,
  onSaved,
}: {
  stack: Stack
  upstreams: CaddyUpstream[]
  onSaved: () => void
}) {
  const meta = stack.x_litethaus
  const domain = typeof meta.domain === 'string' ? meta.domain : null
  const port = meta.port != null ? String(meta.port) : null
  const service = typeof meta.service === 'string' ? meta.service : (stack.services[0] ?? '')
  const lanOnly = Boolean(meta.lan_only)

  const [domainDraft, setDomainDraft] = useState(domain ?? '')
  const [portDraft, setPortDraft] = useState(port ?? '')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDomainDraft(domain ?? '')
    setPortDraft(port ?? '')
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stack.name, domain, port])

  async function save(patch: {
    domain?: string | null
    port?: number | null
    service?: string | null
    lan_only?: boolean | null
  }) {
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

  const dialAddress = service && port ? `${service}:${port}` : null
  const upstream = dialAddress ? upstreams.find((u) => u.address === dialAddress) : undefined

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
      <td className="px-3 py-1.5 text-center">
        <input
          type="checkbox"
          checked={lanOnly}
          onChange={(e) => save({ lan_only: e.target.checked || null })}
          title="Restrict to private/LAN IP ranges only"
        />
      </td>
      <td className="px-3 py-1.5">
        {!domain ? (
          <span className="text-neutral-400 dark:text-neutral-500">—</span>
        ) : !upstream ? (
          <span className="text-neutral-400 dark:text-neutral-500">no traffic yet</span>
        ) : upstream.fails > 0 ? (
          <span className="text-red-600 dark:text-red-400">degraded ({upstream.fails} fails)</span>
        ) : (
          <span className="text-green-600 dark:text-green-400">healthy</span>
        )}
      </td>
      <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">{upstream?.num_requests ?? '—'}</td>
    </tr>
  )
}
