import { useState } from 'react'
import { AlertTriangle, Download, Play, RotateCw, Square, Star, Trash2 } from 'lucide-react'
import { deleteStack, domainList, stackUrl, type HealthState, type Stack, type StackState } from '../api'
import { BAD_HEALTH, STATUS_BADGE } from '../statusStyles'
import { DomainLink } from './DomainLink'
import { StackIcon } from './StackIcon'

interface StackCardProps {
  stack: Stack
  httpsPort: number
  status: StackState | null
  health: HealthState | null
  busy: boolean
  layout: 'grid' | 'list'
  favorite: boolean
  onToggle: () => void
  onRestart: () => void
  onUpdate: () => void
  onOpen: () => void
  onToggleFavorite: () => void
  onDeleted: () => void
}

export function StackCard({
  stack,
  httpsPort,
  status,
  health,
  busy,
  layout,
  favorite,
  onToggle,
  onRestart,
  onUpdate,
  onOpen,
  onToggleFavorite,
  onDeleted,
}: StackCardProps) {
  const [deleting, setDeleting] = useState(false)
  // Card space is tight (grid tiles especially) - show only the primary
  // (first-listed) domain here; the full list is editable on the stack's
  // detail page, and the homepage launcher lists every domain separately.
  const domain = domainList(stack.x_litethaus.domain)[0] ?? null

  async function handleDelete() {
    if (!confirm(`Delete stack "${stack.name}"? This removes its directory from disk.`)) return
    setDeleting(true)
    try {
      await deleteStack(stack.name)
      onDeleted()
    } finally {
      setDeleting(false)
    }
  }

  const favoriteButton = (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onToggleFavorite()
      }}
      aria-label={favorite ? 'Unfavorite' : 'Favorite'}
      className="text-neutral-300 hover:text-yellow-500 dark:text-neutral-600 dark:hover:text-yellow-400"
    >
      <Star size={14} className={favorite ? 'fill-yellow-400 text-yellow-400' : undefined} />
    </button>
  )

  const domainLink = stack.error ? (
    <div className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
      <AlertTriangle size={14} />
      <span className="truncate" title={stack.error}>
        {stack.error}
      </span>
    </div>
  ) : domain ? (
    <DomainLink href={stackUrl(domain, httpsPort)} label={domain} />
  ) : (
    <span className="text-xs text-neutral-400 dark:text-neutral-600">no domain configured</span>
  )

  const canRestart = !busy && !stack.error && status === 'running'
  const canDelete = !deleting && status === 'stopped'

  // Icon-only action row for grid tiles (space is tight); labeled buttons for list rows.
  function iconActions() {
    return (
      <div className="flex items-center gap-1">
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          disabled={busy || !!stack.error}
          title={status !== 'stopped' ? 'Stop' : 'Start'}
          aria-label={status !== 'stopped' ? 'Stop' : 'Start'}
          className="rounded border border-neutral-300 p-1.5 text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {status !== 'stopped' ? <Square size={14} /> : <Play size={14} />}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRestart()
          }}
          disabled={!canRestart}
          title={status !== 'running' ? 'start the stack before restarting it' : 'Restart'}
          aria-label="Restart"
          className="rounded border border-neutral-300 p-1.5 text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          <RotateCw size={14} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onUpdate()
          }}
          disabled={busy || !!stack.error}
          title="Pull latest images and recreate containers"
          aria-label="Update"
          className="rounded border border-neutral-300 p-1.5 text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          <Download size={14} />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            handleDelete()
          }}
          disabled={!canDelete}
          title={status !== 'stopped' ? 'stop the stack before deleting it' : 'Delete'}
          aria-label="Delete"
          className="rounded border border-red-200 p-1.5 text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40"
        >
          <Trash2 size={14} />
        </button>
      </div>
    )
  }

  function labeledActions() {
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggle()
          }}
          disabled={busy || !!stack.error}
          className="rounded border border-neutral-300 px-2 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          {status !== 'stopped' ? 'Stop' : 'Start'}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRestart()
          }}
          disabled={!canRestart}
          title={status !== 'running' ? 'start the stack before restarting it' : undefined}
          className="rounded border border-neutral-300 px-2 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          Restart
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onUpdate()
          }}
          disabled={busy || !!stack.error}
          title="Pull latest images and recreate containers"
          className="rounded border border-neutral-300 px-2 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800"
        >
          Update
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation()
            handleDelete()
          }}
          disabled={!canDelete}
          title={status !== 'stopped' ? 'stop the stack before deleting it' : undefined}
          className="rounded border border-red-200 px-2 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950/40"
        >
          {deleting ? 'Deleting…' : 'Delete'}
        </button>
      </div>
    )
  }

  if (layout === 'list') {
    return (
      <div
        onClick={onOpen}
        className="flex cursor-pointer items-center gap-3 rounded-lg border border-neutral-200 bg-white px-4 py-2.5 hover:border-neutral-300 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
      >
        <StackIcon icon={stack.x_litethaus.icon} size={22} />
        <span className="font-medium text-neutral-900 dark:text-neutral-100">{stack.name}</span>
        {health && BAD_HEALTH.has(health) && (
          <span title={health}>
            <AlertTriangle size={14} className="text-red-500" />
          </span>
        )}
        {status && (
          <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_BADGE[status]}`}>{status}</span>
        )}
        <div className="min-w-0 flex-1 truncate">{domainLink}</div>
        {favoriteButton}
        {labeledActions()}
      </div>
    )
  }

  return (
    <div
      onClick={onOpen}
      className="flex cursor-pointer flex-col gap-3 rounded-lg border border-neutral-200 bg-white p-4 hover:border-neutral-300 dark:border-neutral-800 dark:bg-neutral-900 dark:hover:border-neutral-700"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <StackIcon icon={stack.x_litethaus.icon} size={32} />
          <span className="font-medium text-neutral-900 dark:text-neutral-100">{stack.name}</span>
          {health && BAD_HEALTH.has(health) && (
            <span title={health}>
              <AlertTriangle size={14} className="text-red-500" />
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {favoriteButton}
          {status && (
            <span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_BADGE[status]}`}>{status}</span>
          )}
        </div>
      </div>

      {domainLink}

      <div className="mt-auto pt-1">{iconActions()}</div>
    </div>
  )
}
