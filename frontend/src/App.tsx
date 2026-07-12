import { useEffect, useState } from 'react'

function App() {
  const [status, setStatus] = useState('checking...')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus('unreachable'))
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-900 text-neutral-100">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold">litethaus</h1>
        <p className="text-neutral-400">backend: {status}</p>
      </div>
    </div>
  )
}

export default App
