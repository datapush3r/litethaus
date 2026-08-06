import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { detectStackMetadata, fetchConfig, type DetectedMetadata } from '../api'
import { formatYaml } from '../yamlFormat'
import { YamlEditor } from './YamlEditor'

export interface StackEditorMetadata {
  domain: string | null
  port: number | null
  service: string | null
}

interface StackEditorProps {
  title: string
  initialName?: string
  nameEditable: boolean
  initialContent: string
  onSave: (name: string, content: string, metadata: StackEditorMetadata) => Promise<void>
  onCancel: () => void
}

const DETECT_DEBOUNCE_MS = 400

export function StackEditor({ title, initialName = '', nameEditable, initialContent, onSave, onCancel }: StackEditorProps) {
  const [name, setName] = useState(initialName)
  const [content, setContent] = useState(initialContent)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formatError, setFormatError] = useState<string | null>(null)

  const [wildcardDomain, setWildcardDomain] = useState('')
  const [detected, setDetected] = useState<DetectedMetadata | null>(null)
  const [selectedService, setSelectedService] = useState('')
  const [domain, setDomain] = useState('')
  const [domainTouched, setDomainTouched] = useState(false)
  const [port, setPort] = useState('')
  const [portTouched, setPortTouched] = useState(false)

  // Only the New Stack flow (nameEditable) auto-detects - editing an
  // existing stack's compose file already has its own metadata UI.
  useEffect(() => {
    if (!nameEditable) return
    fetchConfig()
      .then((cfg) => setWildcardDomain(cfg.wildcard_domain ?? ''))
      .catch(() => {})
  }, [nameEditable])

  useEffect(() => {
    if (!nameEditable) return
    // Skip the untouched placeholder template - otherwise detection fires on
    // page load, before the user has pasted anything, and shows a premature
    // "couldn't detect" hint for a compose file they didn't write.
    if (content === initialContent) return
    if (formatYaml(content) === null) return
    const timer = setTimeout(() => {
      detectStackMetadata(content)
        .then(setDetected)
        .catch(() => {})
    }, DETECT_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [content, nameEditable, initialContent])

  useEffect(() => {
    if (!detected) return
    if (!name.trim() && detected.suggested_name) setName(detected.suggested_name)
    const stillValid = detected.services.some((s) => s.name === selectedService)
    if (!stillValid) setSelectedService(detected.services[0]?.name ?? '')
  }, [detected]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedService) return
    // wildcard_domain is meant to be stored bare (e.g. "example.com" - see
    // SettingsPage's placeholder and caddy_service.py, which prepends "*."
    // itself for the ACME cert subject), but strip a leading "*." defensively
    // in case it was entered with the star already.
    const baseDomain = wildcardDomain.replace(/^\*\.?/, '')
    if (!domainTouched) setDomain(baseDomain ? `${selectedService}.${baseDomain}` : selectedService)
    if (!portTouched) {
      const svc = detected?.services.find((s) => s.name === selectedService)
      setPort(svc?.port != null ? String(svc.port) : '')
    }
  }, [selectedService, wildcardDomain]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleFormat() {
    const formatted = formatYaml(content)
    if (formatted === null) {
      setFormatError('fix YAML errors before formatting')
      return
    }
    setFormatError(null)
    setContent(formatted)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      await onSave(name, content, {
        domain: domain.trim() || null,
        port: port.trim() ? Number(port) : null,
        service: detected && detected.services.length > 1 ? selectedService || null : null,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-medium text-neutral-900 dark:text-neutral-100">{title}</h2>

      {nameEditable && (
        <div>
          <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">Stack name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="my-stack"
            className="w-full max-w-xs rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
        </div>
      )}

      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className="block text-xs uppercase text-neutral-400 dark:text-neutral-500">compose.yaml</label>
          <button
            onClick={handleFormat}
            className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
          >
            Format
          </button>
        </div>
        <YamlEditor
          value={content}
          onChange={setContent}
          className="h-[32rem] overflow-auto rounded border border-neutral-300 text-xs dark:border-neutral-700"
        />
        {formatError && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{formatError}</p>}
      </div>

      {nameEditable && detected && detected.services.length > 0 && (
        <div className="flex flex-col gap-3 rounded border border-neutral-200 p-3 dark:border-neutral-800">
          {detected.services.length > 1 && (
            <div>
              <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
                Service to proxy
              </label>
              <select
                value={selectedService}
                onChange={(e) => {
                  setSelectedService(e.target.value)
                  setDomainTouched(false)
                  setPortTouched(false)
                }}
                className="w-full max-w-xs rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              >
                {detected.services.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <div>
              <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">Domain</label>
              <input
                value={domain}
                onChange={(e) => {
                  setDomain(e.target.value)
                  setDomainTouched(true)
                }}
                placeholder="app.example.com"
                className="w-full max-w-xs rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">Port</label>
              <input
                value={port}
                onChange={(e) => {
                  setPort(e.target.value)
                  setPortTouched(true)
                }}
                placeholder="8080"
                inputMode="numeric"
                className="w-28 rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
              />
              {!port && (
                <p className="mt-1 max-w-xs text-xs text-neutral-500 dark:text-neutral-400">
                  couldn't detect - enter the port this service listens on
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs">{error}</pre>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || (nameEditable && !name.trim())}
          className="rounded border border-neutral-300 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={onCancel}
          className="text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
