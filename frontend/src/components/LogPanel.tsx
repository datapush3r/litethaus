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
    <div className="h-96 overflow-y-auto rounded border border-neutral-800 bg-neutral-900 p-3 font-mono text-xs text-neutral-300">
      {lines.length === 0 && <p className="text-neutral-600">Waiting for logs…</p>}
      {lines.map((line, i) => (
        <div key={i} className="whitespace-pre-wrap">
          {line}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
