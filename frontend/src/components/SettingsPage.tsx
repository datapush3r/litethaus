import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { changePassword, fetchConfig, updateConfig, type Config } from '../api'
import { setThemePreference } from '../theme'

const THEME_OPTIONS = ['system', 'light', 'dark'] as const
const HTTPS_MODE_OPTIONS = [
  { value: 'off', label: 'Off (HTTP only)' },
  { value: 'internal', label: 'Internal (self-signed, for .home.arpa/.local domains)' },
  { value: 'acme', label: 'ACME (Let’s Encrypt, requires a public domain)' },
] as const

interface FormState {
  stacks_dir: string
  caddy_admin_url: string
  https_mode: string
  acme_email: string
  theme: string
  webhook_url: string
}

export function SettingsPage() {
  const [config, setConfig] = useState<Config | null>(null)
  const [form, setForm] = useState<FormState>({
    stacks_dir: '',
    caddy_admin_url: '',
    https_mode: 'off',
    acme_email: '',
    theme: 'system',
    webhook_url: '',
  })
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [passwordSaved, setPasswordSaved] = useState(false)

  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        setConfig(cfg)
        setForm({
          stacks_dir: String(cfg.stacks_dir ?? ''),
          caddy_admin_url: String(cfg.caddy_admin_url ?? ''),
          https_mode: String(cfg.https_mode ?? 'off'),
          acme_email: String(cfg.acme_email ?? ''),
          theme: String(cfg.theme ?? 'system'),
          webhook_url: String(cfg.webhook_url ?? ''),
        })
      })
      .catch(() => setLoadError('failed to load config'))
  }, [])

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    setSaveError(null)
    try {
      const updated = await updateConfig({ ...form })
      setConfig(updated)
      setThemePreference(form.theme)
      setSaved(true)
    } catch {
      setSaveError('failed to save config')
    } finally {
      setSaving(false)
    }
  }

  async function handleChangePassword() {
    setPasswordSaving(true)
    setPasswordSaved(false)
    setPasswordError(null)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setPasswordSaved(true)
    } catch (err) {
      setPasswordError(err instanceof Error ? err.message : 'failed to change password')
    } finally {
      setPasswordSaving(false)
    }
  }

  if (loadError) return <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>
  if (!config)
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-400 dark:text-neutral-500">
        <Loader2 size={16} className="animate-spin" />
        Loading settings…
      </div>
    )

  return (
    <div className="flex max-w-lg flex-col gap-5">
      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
          Stacks directory
        </label>
        <input
          value={form.stacks_dir}
          onChange={(e) => setForm((f) => ({ ...f, stacks_dir: e.target.value }))}
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
          Caddy admin URL
        </label>
        <input
          value={form.caddy_admin_url}
          onChange={(e) => setForm((f) => ({ ...f, caddy_admin_url: e.target.value }))}
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">HTTPS</label>
        <select
          value={form.https_mode}
          onChange={(e) => setForm((f) => ({ ...f, https_mode: e.target.value }))}
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          {HTTPS_MODE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {form.https_mode === 'acme' && (
        <div>
          <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
            ACME email
          </label>
          <input
            value={form.acme_email}
            onChange={(e) => setForm((f) => ({ ...f, acme_email: e.target.value }))}
            placeholder="you@example.com"
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
          Health webhook URL
        </label>
        <input
          value={form.webhook_url}
          onChange={(e) => setForm((f) => ({ ...f, webhook_url: e.target.value }))}
          placeholder="https://example.com/hooks/litethaus (optional)"
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
        <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
          POSTed as JSON when a stack becomes unhealthy or enters a restart loop. Leave blank to disable.
        </p>
      </div>

      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">Theme</label>
        <select
          value={form.theme}
          onChange={(e) => setForm((f) => ({ ...f, theme: e.target.value }))}
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        >
          {THEME_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved && <span className="text-xs text-green-600 dark:text-green-400">Saved</span>}
        {saveError && <span className="text-xs text-red-600 dark:text-red-400">{saveError}</span>}
      </div>

      <div className="flex flex-col gap-3 border-t border-neutral-200 pt-5 dark:border-neutral-800">
        <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Change password</h2>

        <input
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          placeholder="Current password"
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />
        <input
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          placeholder="New password (at least 8 characters)"
          className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
        />

        <div className="flex items-center gap-3">
          <button
            onClick={handleChangePassword}
            disabled={passwordSaving || !currentPassword || !newPassword}
            className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            {passwordSaving ? 'Saving…' : 'Change password'}
          </button>
          {passwordSaved && <span className="text-xs text-green-600 dark:text-green-400">Password changed</span>}
          {passwordError && <span className="text-xs text-red-600 dark:text-red-400">{passwordError}</span>}
        </div>
      </div>
    </div>
  )
}
