import { useCallback, useEffect, useState } from 'react'
import { fetchStacks, fetchStatus, stackDown, stackUp, type Stack, type StackState } from './api'
import { StackCard } from './components/StackCard'
import { StackDetail } from './components/StackDetail'
import { SettingsPage } from './components/SettingsPage'
import { Sidebar } from './components/Sidebar'
import { parseRoute, routePath, type Route } from './routing'

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

  return [parseRoute(path), navigate]
}

function App() {
  const [stacks, setStacks] = useState<Stack[] | null>(null)
  const [statuses, setStatuses] = useState<Record<string, StackState>>({})
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [error, setError] = useState<string | null>(null)
  const [route, navigate] = useRoute()

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
    <div className="flex min-h-screen bg-neutral-950 text-neutral-100">
      <Sidebar
        stacks={stacks ?? []}
        statuses={statuses}
        route={route}
        onSelectStack={(name) => navigate(name ? { view: 'stack', name } : { view: 'stacks' })}
        onOpenSettings={() => navigate({ view: 'settings' })}
      />

      <div className="flex-1">
        <header className="border-b border-neutral-800 px-6 py-4">
          <h1 className="text-sm text-neutral-400">{heading}</h1>
        </header>

        <main className="p-6">
          {route.view === 'settings' && <SettingsPage />}

          {route.view !== 'settings' && error && <p className="text-sm text-red-400">{error}</p>}

          {route.view !== 'settings' && !error && stacks === null && (
            <p className="text-sm text-neutral-500">Loading stacks…</p>
          )}

          {route.view !== 'settings' && stacks !== null && stacks.length === 0 && (
            <p className="text-sm text-neutral-500">No stacks found. Add one under stacks_dir.</p>
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
