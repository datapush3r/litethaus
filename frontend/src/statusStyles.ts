import type { StackState } from './api'

export const STATUS_DOT: Record<StackState, string> = {
  running: 'bg-green-500',
  partial: 'bg-yellow-500',
  stopped: 'bg-neutral-500',
}

export const STATUS_BADGE: Record<StackState, string> = {
  running: 'bg-green-500/15 text-green-400 border-green-500/30',
  partial: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  stopped: 'bg-neutral-500/15 text-neutral-400 border-neutral-500/30',
}
