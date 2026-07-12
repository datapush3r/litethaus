import { useCallback, useEffect, useState } from 'react'
import { fetchStacks, fetchStatus, stackDown, stackUp, type Stack, type StackState } from './api'
import { StackCard } from './components/StackCard'
import { LogViewer } from './components/LogViewer'

const STATUS_POLL_MS = 5000

function App() {
  const [stacks, setStacks] = useState<Stack[] | null>(null)
  const [statuses, setStatuses] = useState<Record<string, StackState>>({})
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [logsFor, setLogsFor] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

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

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-800 px-6 py-4">
        <h1 className="text-lg font-semibold">litethaus</h1>
      </header>

      <main className="p-6">
        {error && <p className="text-sm text-red-400">{error}</p>}

        {!error && stacks === null && <p className="text-sm text-neutral-500">Loading stacks…</p>}

        {stacks !== null && stacks.length === 0 && (
          <p className="text-sm text-neutral-500">No stacks found. Add one under stacks_dir.</p>
        )}

        {stacks !== null && stacks.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {stacks.map((stack) => (
              <StackCard
                key={stack.name}
                stack={stack}
                status={statuses[stack.name] ?? null}
                busy={!!busy[stack.name]}
                onToggle={() => handleToggle(stack)}
                onViewLogs={() => setLogsFor(stack.name)}
              />
            ))}
          </div>
        )}
      </main>

      {logsFor && <LogViewer stackName={logsFor} onClose={() => setLogsFor(null)} />}
    </div>
  )
}

export default App
