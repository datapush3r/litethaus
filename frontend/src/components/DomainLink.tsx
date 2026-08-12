import { ExternalLink } from 'lucide-react'

interface DomainLinkProps {
  href: string
  label: string
}

export function DomainLink({ href, label }: DomainLinkProps) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      className="flex items-center gap-1 text-xs text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200"
    >
      {label}
      <ExternalLink size={12} />
    </a>
  )
}
