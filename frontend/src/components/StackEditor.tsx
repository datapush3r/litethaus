import { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { formatYaml } from '../yamlFormat'
import { YamlEditor } from './YamlEditor'

interface StackEditorProps {
  title: string
  initialName?: string
  nameEditable: boolean
  initialContent: string
  onSave: (name: string, content: string) => Promise<void>
  onCancel: () => void
}

export function StackEditor({ title, initialName = '', nameEditable, initialContent, onSave, onCancel }: StackEditorProps) {
  const [name, setName] = useState(initialName)
  const [content, setContent] = useState(initialContent)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [formatError, setFormatError] = useState<string | null>(null)

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
      await onSave(name, content)
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
