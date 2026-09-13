import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export function CheckInLinkCard() {
  const [url, setUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.get<{ token: string }>('/api/check-in/current-token/').then(({ token }) => {
      setUrl(`${window.location.origin}/check-in/${token}/`)
    })
  }, [])

  async function handleCopy() {
    if (!url) return
    await navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <section className="card mt-6">
      <h2 className="section-title">Guest check-in link</h2>
      <p className="mt-1 text-sm text-stone-500">
        Share this link (or a QR code pointing to it) at the host stand. It changes every day.
      </p>
      {url && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <code className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-700">
            {url}
          </code>
          <button type="button" className="btn-secondary btn-sm" onClick={handleCopy}>
            {copied ? 'Copied!' : 'Copy link'}
          </button>
        </div>
      )}
    </section>
  )
}
