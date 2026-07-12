import { useEffect, useRef } from 'react'

interface LogPanelProps {
  lines: string[]
}

export function LogPanel({ lines }: LogPanelProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [lines])

  return (
    <div className="h-full overflow-y-auto rounded border border-neutral-200 bg-white p-3 font-mono text-xs text-neutral-700 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-300">
      {lines.length === 0 && <p className="text-neutral-400 dark:text-neutral-600">Waiting for logs…</p>}
      {lines.map((line, i) => (
        <div key={i} className="whitespace-pre-wrap">
          {line}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
