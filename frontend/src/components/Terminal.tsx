import { useEffect, useRef } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { terminalSocketUrl } from '../api'

interface TerminalProps {
  stackName: string
  containerName: string | null
}

export function Terminal({ stackName, containerName }: TerminalProps) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!hostRef.current || !containerName) return

    const term = new XTerm({ convertEol: true, fontSize: 12 })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(hostRef.current)
    fit.fit()

    const ws = new WebSocket(terminalSocketUrl(stackName, containerName))
    ws.binaryType = 'arraybuffer'
    ws.onmessage = (event) => term.write(new Uint8Array(event.data))
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(data))
    })

    const onResize = () => fit.fit()
    window.addEventListener('resize', onResize)

    return () => {
      window.removeEventListener('resize', onResize)
      ws.close()
      term.dispose()
    }
  }, [stackName, containerName])

  if (!containerName) {
    return (
      <div className="flex h-full items-center justify-center rounded border border-neutral-200 bg-white text-xs text-neutral-400 dark:border-neutral-800 dark:bg-neutral-900 dark:text-neutral-600">
        No running container to attach to
      </div>
    )
  }

  return <div ref={hostRef} className="h-full overflow-hidden rounded border border-neutral-200 bg-black p-1 dark:border-neutral-800" />
}
