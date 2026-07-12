import { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { logsSocketUrl } from '../api'

interface LogViewerProps {
  stackName: string
  onClose: () => void
}

export function LogViewer({ stackName, onClose }: LogViewerProps) {
  const [lines, setLines] = useState<string[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setLines([])
    const ws = new WebSocket(logsSocketUrl(stackName))
    ws.onmessage = (event) => {
      setLines((prev) => [...prev, event.data])
    }
    return () => ws.close()
  }, [stackName])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [lines])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex h-full max-h-[80vh] w-full max-w-3xl flex-col rounded-lg border border-neutral-700 bg-neutral-900">
        <div className="flex items-center justify-between border-b border-neutral-700 px-4 py-2">
          <h2 className="font-mono text-sm text-neutral-200">{stackName} — logs</h2>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-100" aria-label="Close">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs text-neutral-300">
          {lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap">
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}
