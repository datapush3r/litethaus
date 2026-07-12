import { useState } from 'react'
import { Box } from 'lucide-react'

// Icons from https://github.com/homarr-labs/dashboard-icons, served via jsdelivr.
const ICON_BASE = 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons@main/svg'

interface StackIconProps {
  icon?: unknown
  size?: number
  className?: string
}

export function StackIcon({ icon, size = 18, className }: StackIconProps) {
  const [failed, setFailed] = useState(false)
  const slug = typeof icon === 'string' ? icon.trim() : ''

  if (!slug || failed) {
    return <Box size={size} className={className ?? 'shrink-0 text-neutral-400 dark:text-neutral-500'} />
  }

  return (
    <img
      src={`${ICON_BASE}/${slug}.svg`}
      alt=""
      width={size}
      height={size}
      className={className ?? 'shrink-0 object-contain'}
      onError={() => setFailed(true)}
    />
  )
}
