import { AlertTriangle, ExternalLink, Star } from 'lucide-react'
import { stackUrl, type HealthState, type Stack, type StackState } from '../api'
import { BAD_HEALTH, STATUS_BADGE } from '../statusStyles'
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
  onOpen: () => void
  onToggleFavorite: () => void
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
  onOpen,
  onToggleFavorite,
}: StackCardProps) {
  const domain = typeof stack.x_litethaus.domain === 'string' ? stack.x_litethaus.domain : null

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
    <a
      href={stackUrl(domain, httpsPort)}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
    >
      {domain}
      <ExternalLink size={12} />
    </a>
  ) : (
    <span className="text-xs text-neutral-400 dark:text-neutral-600">no domain configured</span>
  )

  function toggleButton(fullWidth: boolean) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
        disabled={busy || !!stack.error}
        className={`rounded border border-neutral-300 px-2 py-1.5 text-xs text-neutral-700 hover:bg-neutral-100 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800 ${fullWidth ? 'w-full' : 'shrink-0'}`}
      >
        {status === 'running' ? 'Stop' : 'Start'}
      </button>
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
        {toggleButton(false)}
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

      <div className="mt-auto pt-1">{toggleButton(true)}</div>
    </div>
  )
}
