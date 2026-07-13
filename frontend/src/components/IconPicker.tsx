import { useEffect, useMemo, useState } from 'react'
import { Search, X } from 'lucide-react'
import { StackIcon } from './StackIcon'

// Same source as StackIcon.tsx - https://github.com/homarr-labs/dashboard-icons
const METADATA_URL = 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons@main/metadata.json'
const RESULT_LIMIT = 200

interface IconMeta {
  aliases?: string[]
}

// Module-level cache: the icon list is ~1MB and identical for every stack, so fetch it once per session.
let metadataPromise: Promise<Record<string, IconMeta>> | null = null

function loadIconMetadata(): Promise<Record<string, IconMeta>> {
  if (!metadataPromise) {
    metadataPromise = fetch(METADATA_URL)
      .then((res) => res.json())
      .catch(() => ({}))
  }
  return metadataPromise
}

interface IconPickerProps {
  value: string
  onSelect: (slug: string) => void
  onClose: () => void
}

export function IconPicker({ value, onSelect, onClose }: IconPickerProps) {
  const [query, setQuery] = useState('')
  const [icons, setIcons] = useState<Record<string, IconMeta>>({})

  useEffect(() => {
    loadIconMetadata().then(setIcons)
  }, [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const slugs = useMemo(() => {
    const q = query.trim().toLowerCase()
    const entries = Object.entries(icons)
    const matches = q
      ? entries.filter(([slug, meta]) => slug.includes(q) || (meta.aliases ?? []).some((a) => a.toLowerCase().includes(q)))
      : entries
    return matches
      .map(([slug]) => slug)
      .sort()
      .slice(0, RESULT_LIMIT)
  }, [icons, query])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        className="flex max-h-[32rem] w-full max-w-lg flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 shadow-xl dark:border-neutral-700 dark:bg-neutral-900"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-neutral-900 dark:text-neutral-100">Choose icon</h3>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200">
            <X size={16} />
          </button>
        </div>
        <div className="flex items-center gap-2 rounded border border-neutral-300 px-2 py-1.5 dark:border-neutral-700">
          <Search size={14} className="shrink-0 text-neutral-400" />
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search icons…"
            className="w-full bg-transparent text-sm outline-none dark:text-neutral-100"
          />
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-5 gap-2 overflow-y-auto sm:grid-cols-6">
          <button
            onClick={() => onSelect('')}
            className={`flex flex-col items-center gap-1 rounded border p-2 text-[10px] text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800 ${value === '' ? 'border-neutral-400 dark:border-neutral-500' : 'border-transparent'}`}
          >
            <StackIcon icon="" size={24} />
            none
          </button>
          {slugs.map((slug) => (
            <button
              key={slug}
              onClick={() => onSelect(slug)}
              title={slug}
              className={`flex flex-col items-center gap-1 rounded border p-2 text-[10px] hover:bg-neutral-100 dark:hover:bg-neutral-800 ${value === slug ? 'border-neutral-400 dark:border-neutral-500' : 'border-transparent'}`}
            >
              <StackIcon icon={slug} size={24} />
              <span className="w-full truncate text-center text-neutral-500 dark:text-neutral-400">{slug}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
