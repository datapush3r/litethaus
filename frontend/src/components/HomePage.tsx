import { ExternalLink, PackageOpen } from 'lucide-react'
import { domainList, stackUrl, type Stack, type StackState } from '../api'
import { StackIcon } from './StackIcon'

interface HomePageProps {
  stacks: Stack[]
  statuses: Record<string, StackState>
  extraRoutesJson: string
  httpsPort: number
}

interface HomeEntry {
  key: string
  name: string | null
  domain: string
  icon: unknown
  url: string
}

export function buildHomeEntries(
  stacks: Stack[],
  statuses: Record<string, StackState>,
  extraRoutesJson: string,
  httpsPort: number,
): HomeEntry[] {
  const entries: HomeEntry[] = []

  for (const stack of stacks) {
    if (stack.error) continue
    if (statuses[stack.name] === 'stopped') continue
    // One row per domain - a stack with multiple hostnames (e.g. a short
    // alias alongside the full name) gets one launcher entry each, since
    // every domain is an independently working way to reach it.
    for (const domain of domainList(stack.x_litethaus.domain)) {
      entries.push({
        key: `stack:${stack.name}:${domain}`,
        name: stack.name,
        domain,
        icon: stack.x_litethaus.icon,
        url: stackUrl(domain, httpsPort),
      })
    }
  }

  for (const domain of extractExtraRouteHosts(extraRoutesJson)) {
    entries.push({ key: `route:${domain}`, name: null, domain, icon: null, url: stackUrl(domain, httpsPort) })
  }

  entries.sort((a, b) => (a.name ?? a.domain).localeCompare(b.name ?? b.domain))
  return entries
}

// Extracts every `host` string out of a caddy_extra_routes_json array, i.e.
// every route shaped like {"match": [{"host": ["foo.example.com"]}], ...}.
// Malformed JSON (or JSON that isn't an array) yields no hosts, same
// silent-skip behavior as caddy_service.py's own fallback server-side.
function extractExtraRouteHosts(extraRoutesJson: string): string[] {
  if (!extraRoutesJson.trim()) return []
  let parsed: unknown
  try {
    parsed = JSON.parse(extraRoutesJson)
  } catch {
    return []
  }
  if (!Array.isArray(parsed)) return []

  const hosts = new Set<string>()
  for (const route of parsed) {
    const matches = (route as { match?: unknown } | null)?.match
    if (!Array.isArray(matches)) continue
    for (const matcher of matches) {
      const hostList = (matcher as { host?: unknown } | null)?.host
      if (!Array.isArray(hostList)) continue
      for (const host of hostList) {
        if (typeof host === 'string' && host && !host.includes('*')) hosts.add(host)
      }
    }
  }
  return [...hosts]
}

export function HomePage({ stacks, statuses, extraRoutesJson, httpsPort }: HomePageProps) {
  const entries = buildHomeEntries(stacks, statuses, extraRoutesJson, httpsPort)

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-center text-neutral-400 dark:text-neutral-500">
        <PackageOpen size={28} />
        <p className="text-sm">No running stacks or custom routes with a domain configured yet.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      {entries.map((entry) => (
        <a
          key={entry.key}
          href={entry.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-3 rounded-lg border border-neutral-200 bg-white px-4 py-2.5 hover:border-neutral-300 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
        >
          <StackIcon icon={entry.icon} size={22} />
          {entry.name && <span className="font-medium text-neutral-900 dark:text-neutral-100">{entry.name}</span>}
          <span className="ml-auto flex items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400">
            {entry.domain}
            <ExternalLink size={12} />
          </span>
        </a>
      ))}
    </div>
  )
}
