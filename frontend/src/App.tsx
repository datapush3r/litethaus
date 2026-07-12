import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Loader2, Menu, PackageOpen } from 'lucide-react'
import {
  authLogout,
  createStack,
  fetchAuthStatus,
  fetchConfig,
  fetchStacks,
  fetchStatus,
  stackDown,
  stackUp,
  type AuthStatus,
  type Stack,
  type StackState,
  type StackStatus,
} from './api'
import { AuthScreen } from './components/AuthScreen'
import { StackCard } from './components/StackCard'
import { StackDetail } from './components/StackDetail'
import { StackEditor } from './components/StackEditor'
import { SettingsPage } from './components/SettingsPage'
import { Sidebar } from './components/Sidebar'
import { parseRoute, routePath, type Route } from './routing'
import { setThemePreference } from './theme'

const STATUS_POLL_MS = 5000

const NEW_STACK_TEMPLATE = `x-litethaus:
  domain: app.home.arpa
  port: 80

services:
  app:
    image: nginx:alpine
    restart: unless-stopped
    networks:
      - litethaus

networks:
  litethaus:
    external: true
`

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
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null)

  const checkAuth = useCallback(() => {
    fetchAuthStatus()
      .then(setAuthStatus)
      .catch(() => setAuthStatus({ configured: true, authenticated: false }))
  }, [])

  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  if (!authStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-neutral-50 dark:bg-neutral-950">
        <Loader2 size={20} className="animate-spin text-neutral-400" />
      </div>
    )
  }

  // "not configured yet" is intentionally reported as authenticated=true by
  // the backend (so a fresh install is API-usable without a chicken-and-egg
  // login), but the UI still needs to prompt for setup rather than skipping
  // straight past onboarding into the dashboard.
  if (!authStatus.configured) {
    return <AuthScreen mode="setup" onAuthenticated={checkAuth} />
  }

  if (!authStatus.authenticated) {
    return <AuthScreen mode="login" onAuthenticated={checkAuth} />
  }

  return <Dashboard onLogout={checkAuth} />
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [stacks, setStacks] = useState<Stack[] | null>(null)
  const [statuses, setStatuses] = useState<Record<string, StackState>>({})
  const [health, setHealth] = useState<Record<string, StackStatus>>({})
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
    setStatuses(Object.fromEntries(entries.map(([name, info]) => [name, info.status])))
    setHealth(Object.fromEntries(entries))
  }, [])

  const refreshStacks = useCallback(async () => {
    const list = await fetchStacks()
    setStacks(list)
    await refreshStatuses(list)
  }, [refreshStatuses])

  async function handleCreate(name: string, content: string) {
    await createStack(name, content)
    await refreshStacks()
    navigate({ view: 'stack', name })
  }

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
      const info = await fetchStatus(stack.name)
      setStatuses((prev) => ({ ...prev, [stack.name]: info.status }))
      setHealth((prev) => ({ ...prev, [stack.name]: info }))
    } finally {
      setBusy((prev) => ({ ...prev, [stack.name]: false }))
    }
  }

  const selectedStack = route.view === 'stack' ? (stacks?.find((s) => s.name === route.name) ?? null) : null

  const listView = route.view === 'stacks' || route.view === 'stack'

  const heading =
    route.view === 'settings'
      ? 'Settings'
      : route.view === 'new'
        ? 'New Stack'
        : `Stacks${route.view === 'stack' ? ` / ${route.name}` : ''}`

  return (
    <div className="flex h-screen overflow-hidden bg-neutral-50 text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
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
        health={health}
        loading={stacks === null}
        route={route}
        open={sidebarOpen}
        onSelectStack={(name) => navigate(name ? { view: 'stack', name } : { view: 'stacks' })}
        onOpenSettings={() => navigate({ view: 'settings' })}
        onNewStack={() => navigate({ view: 'new' })}
        onLogout={() => authLogout().then(onLogout)}
      />

      <div className="flex h-full min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center gap-3 border-b border-neutral-200 px-4 py-4 sm:px-6 dark:border-neutral-800">
          <button
            onClick={() => setSidebarOpen((o) => !o)}
            className="text-neutral-500 hover:text-neutral-800 sm:hidden dark:text-neutral-400 dark:hover:text-neutral-200"
            aria-label="Toggle navigation"
          >
            <Menu size={20} />
          </button>
          <h1 className="text-sm text-neutral-500 dark:text-neutral-400">{heading}</h1>
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4 sm:p-6">
          {route.view === 'settings' && <SettingsPage />}

          {route.view === 'new' && (
            <StackEditor
              title="New Stack"
              nameEditable
              initialContent={NEW_STACK_TEMPLATE}
              onSave={handleCreate}
              onCancel={() => navigate({ view: 'stacks' })}
            />
          )}

          {listView && error && (
            <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
              <AlertTriangle size={16} />
              {error}
            </div>
          )}

          {listView && !error && stacks === null && (
            <div className="flex items-center gap-2 text-sm text-neutral-400 dark:text-neutral-500">
              <Loader2 size={16} className="animate-spin" />
              Loading stacks…
            </div>
          )}

          {listView && stacks !== null && stacks.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-16 text-center text-neutral-400 dark:text-neutral-500">
              <PackageOpen size={28} />
              <p className="text-sm">No stacks found. Add one under stacks_dir.</p>
            </div>
          )}

          {route.view === 'stack' && stacks !== null && selectedStack && (
            <StackDetail
              stack={selectedStack}
              status={statuses[selectedStack.name] ?? null}
              containers={health[selectedStack.name]?.containers ?? []}
              busy={!!busy[selectedStack.name]}
              onToggle={() => handleToggle(selectedStack)}
              onSaved={refreshStacks}
              onDeleted={() => {
                navigate({ view: 'stacks' })
                refreshStacks()
              }}
            />
          )}

          {route.view === 'stacks' && stacks !== null && stacks.length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {stacks.map((stack) => (
                <StackCard
                  key={stack.name}
                  stack={stack}
                  status={statuses[stack.name] ?? null}
                  health={health[stack.name]?.health ?? null}
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
