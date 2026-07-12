import { useEffect, useState } from 'react'
import { fetchConfig, updateConfig, type Config } from '../api'

const THEME_OPTIONS = ['system', 'light', 'dark'] as const

interface FormState {
  stacks_dir: string
  caddy_admin_url: string
  theme: string
}

export function SettingsPage() {
  const [config, setConfig] = useState<Config | null>(null)
  const [form, setForm] = useState<FormState>({ stacks_dir: '', caddy_admin_url: '', theme: 'system' })
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetchConfig()
      .then((cfg) => {
        setConfig(cfg)
        setForm({
          stacks_dir: String(cfg.stacks_dir ?? ''),
          caddy_admin_url: String(cfg.caddy_admin_url ?? ''),
          theme: String(cfg.theme ?? 'system'),
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
      setSaved(true)
    } catch {
      setSaveError('failed to save config')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) return <p className="text-sm text-red-400">{loadError}</p>
  if (!config) return <p className="text-sm text-neutral-500">Loading settings…</p>

  return (
    <div className="flex max-w-lg flex-col gap-5">
      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-500">Stacks directory</label>
        <input
          value={form.stacks_dir}
          onChange={(e) => setForm((f) => ({ ...f, stacks_dir: e.target.value }))}
          className="w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-neutral-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-500">Caddy admin URL</label>
        <input
          value={form.caddy_admin_url}
          onChange={(e) => setForm((f) => ({ ...f, caddy_admin_url: e.target.value }))}
          className="w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-neutral-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs uppercase text-neutral-500">Theme</label>
        <select
          value={form.theme}
          onChange={(e) => setForm((f) => ({ ...f, theme: e.target.value }))}
          className="w-full rounded border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 focus:border-neutral-500 focus:outline-none"
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
          className="rounded border border-neutral-700 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-800 disabled:opacity-40"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        {saved && <span className="text-xs text-green-400">Saved</span>}
        {saveError && <span className="text-xs text-red-400">{saveError}</span>}
      </div>
    </div>
  )
}
