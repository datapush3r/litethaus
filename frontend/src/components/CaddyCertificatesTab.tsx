import { useEffect, useState } from 'react'
import { fetchCaddyCertificates, type CaddyCertificate } from '../api'

const WARNING_DAYS = 14

function daysUntil(isoDate: string): number {
  return Math.floor((new Date(isoDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
}

export function CaddyCertificatesTab() {
  const [certs, setCerts] = useState<CaddyCertificate[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchCaddyCertificates()
      .then(setCerts)
      .catch((err) => setError(err instanceof Error ? err.message : 'failed to load certificates'))
  }, [])

  return (
    <div>
      <h2 className="mb-2 text-xs uppercase text-neutral-400 dark:text-neutral-500">TLS certificates</h2>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="overflow-x-auto rounded border border-neutral-200 dark:border-neutral-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase text-neutral-400 dark:border-neutral-800 dark:text-neutral-500">
              <th className="px-3 py-2">Domain</th>
              <th className="px-3 py-2">Issuer</th>
              <th className="px-3 py-2">Expires</th>
              <th className="px-3 py-2">Days left</th>
            </tr>
          </thead>
          <tbody>
            {certs?.map((cert, i) => {
              const days = daysUntil(cert.expires_at)
              return (
                <tr key={`${cert.domains.join(',')}-${cert.expires_at}-${i}`} className="border-b border-neutral-100 last:border-0 dark:border-neutral-900">
                  <td className="px-3 py-1.5 text-neutral-700 dark:text-neutral-200">{cert.domains.join(', ') || '—'}</td>
                  <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">{cert.issuer}</td>
                  <td className="px-3 py-1.5 text-neutral-500 dark:text-neutral-400">{new Date(cert.expires_at).toLocaleDateString()}</td>
                  <td className={`px-3 py-1.5 ${days < WARNING_DAYS ? 'text-red-600 dark:text-red-400' : 'text-neutral-500 dark:text-neutral-400'}`}>
                    {days}
                  </td>
                </tr>
              )
            })}
            {certs?.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-2 text-neutral-400 dark:text-neutral-500">
                  no certificates found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
