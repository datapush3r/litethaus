import { useState } from 'react'
import { Lock } from 'lucide-react'
import { authLogin, authSetup } from '../api'

interface AuthScreenProps {
  mode: 'setup' | 'login'
  onAuthenticated: () => void
}

export function AuthScreen({ mode, onAuthenticated }: AuthScreenProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await (mode === 'setup' ? authSetup(username, password) : authLogin(username, password))
      onAuthenticated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'something went wrong')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-neutral-50 px-4 dark:bg-neutral-950">
      <form
        onSubmit={handleSubmit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-lg border border-neutral-200 bg-white p-6 dark:border-neutral-800 dark:bg-neutral-900"
      >
        <div className="flex items-center gap-2 text-neutral-900 dark:text-neutral-100">
          <Lock size={18} />
          <h1 className="text-sm font-semibold">{mode === 'setup' ? 'Set up litethaus' : 'litethaus'}</h1>
        </div>
        {mode === 'setup' && (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Choose an admin username and password to secure this dashboard.
          </p>
        )}

        <div>
          <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">Username</label>
          <input
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
          {mode === 'setup' && (
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">At least 8 characters.</p>
          )}
        </div>

        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="rounded border border-neutral-300 px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {submitting ? 'Please wait…' : mode === 'setup' ? 'Create account' : 'Log in'}
        </button>
      </form>
    </div>
  )
}
