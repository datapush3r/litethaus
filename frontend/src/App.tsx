import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2, Menu, PackageOpen } from 'lucide-react'
import { fetchConfig, fetchStacks, fetchStatus, stackDown, stackUp, type Stack, type StackState } from './api'
import { StackCard } from './components/StackCard'
import { StackDetail } from './components/StackDetail'
import { SettingsPage } from './components/SettingsPage'
import { Sidebar } from './components/Sidebar'
import { parseRoute, routePath, type Route } from './routing'
import { setThemePreference } from './theme'

const STATUS_POLL_MS = 5000

function useRoute(): [Route, (route: Route) => void] {
  const [path, setPath] = useState(() => window.location.pathname)

  useEffect(() => {
    const onPopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const navigate = useCallback((route: Route) => {
    const next = routePath(route)
    window.history.pushState({}, '', next)
    setPath(next)
  }, [])

  const route = useMemo(() => parseRoute(path), [path])

  return [route, navigate]
}

function App() {
  const [stacks, setStacks] = useState<Stack[] | null>(null)
  const [statuses, setStatuses] = useState<Record<string, StackState>>({})
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const [route, navigate] = useRoute()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    fetchConfig()
      .then((cfg) => setThemePreference(String(cfg.theme ?? 'system')))
      .catch(() => {
        /* fall back to whatever theme.ts's default already applied */
      })
  }, [])

  const refreshStatuses = useCallback(async (list: Stack[]) => {
    const entries = await Promise.all(
      list.filter((s) => !s.error).map(async (s) => [s.name, await fetchStatus(s.name)] as const),
    )
    setStatuses(Object.fromEntries(entries))
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const list = await fetchStacks()
        if (cancelled) return
        setStacks(list)
        setError(null)
        await refreshStatuses(list)
      } catch {
        if (!cancelled) setError('backend unreachable')
      }
    }

    load()
    const interval = setInterval(load, STATUS_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [refreshStatuses])

  useEffect(() => {
    if (stacks && route.view === 'stack' && !stacks.some((s) => s.name === route.name)) {
      navigate({ view: 'stacks' })
    }
  }, [stacks, route, navigate])

  useEffect(() => {
    setSidebarOpen(false)
  }, [route])

  async function handleToggle(stack: Stack) {
    setBusy((prev) => ({ ...prev, [stack.name]: true }))
    try {
      const running = statuses[stack.name] === 'running'
      await (running ? stackDown(stack.name) : stackUp(stack.name))
      const status = await fetchStatus(stack.name)
      setStatuses((prev) => ({ ...prev, [stack.name]: status }))
    } finally {
      setBusy((prev) => ({ ...prev, [stack.name]: false }))
    }
  }

  const selectedStack = route.view === 'stack' ? (stacks?.find((s) => s.name === route.name) ?? null) : null

  const heading =
    route.view === 'settings' ? 'Settings' : `Stacks${route.view === 'stack' ? ` / ${route.name}` : ''}`

  return (
    <div className="flex min-h-screen bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 sm:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      <Sidebar
        stacks={stacks ?? []}
        statuses={statuses}
        loading={stacks === null}
        route={route}
        open={sidebarOpen}
        onSelectStack={(name) => navigate(name ? { view: 'stack', name } : { view: 'stacks' })}
        onOpenSettings={() => navigate({ view: 'settings' })}
      />

      <div className="min-w-0 flex-1">
        <header className="flex items-center gap-3 border-b border-neutral-200 px-4 py-4 sm:px-6 dark:border-neutral-800">
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className="text-neutral-500 hover:text-neutral-800 sm:hidden dark:text-neutral-400 dark:hover:text-neutral-200"
            aria-label="Toggle navigation"
          >
            <Menu size={20} />
          </button>
          <h1 className="text-sm text-neutral-500 dark:text-neutral-400">{heading}</h1>
        </header>

        <main className="p-4 sm:p-6">
          {route.view === 'settings' && <SettingsPage />}

          {route.view !== 'settings' && error && (
            <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
              <AlertTriangle size={16} />
              {error}
            </div>
          )}

          {route.view !== 'settings' && !error && stacks === null && (
            <div className="flex items-center gap-2 text-sm text-neutral-400 dark:text-neutral-500">
              <Loader2 size={16} className="animate-spin" />
              Loading stacks…
            </div>
          )}

          {route.view !== 'settings' && stacks !== null && stacks.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-16 text-center text-neutral-400 dark:text-neutral-500">
              <PackageOpen size={28} />
              <p className="text-sm">No stacks found. Add one under stacks_dir.</p>
            </div>
          )}

          {route.view === 'stack' && stacks !== null && selectedStack && (
            <StackDetail
              stack={selectedStack}
              status={statuses[selectedStack.name] ?? null}
              busy={!!busy[selectedStack.name]}
              onToggle={() => handleToggle(selectedStack)}
            />
          )}

          {route.view === 'stacks' && stacks !== null && stacks.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {stacks.map((stack) => (
                <StackCard
                  key={stack.name}
                  stack={stack}
                  status={statuses[stack.name] ?? null}
                  busy={!!busy[stack.name]}
                  onToggle={() => handleToggle(stack)}
                  onOpen={() => navigate({ view: 'stack', name: stack.name })}
                />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

export default App
