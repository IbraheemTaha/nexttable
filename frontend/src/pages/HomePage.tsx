import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'

export function HomePage() {
  const [checkInUrl, setCheckInUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.get<{ token: string }>('/api/check-in/current-token/').then(({ token }) => {
      setCheckInUrl(`${window.location.origin}/check-in/${token}/`)
    })
  }, [])

  async function handleCopy() {
    if (!checkInUrl) return
    await navigator.clipboard.writeText(checkInUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-8">
      <p className="app-brand text-center">NextTable</p>

      <div className="card mt-4">
        <h1 className="page-title text-2xl">Join the waitlist</h1>
        <p className="mt-1 text-stone-500">Tap the link below to check in as a guest.</p>

        {checkInUrl ? (
          <div className="mt-4">
            <a href={checkInUrl} className="link break-all text-base">
              {checkInUrl}
            </a>
            <div className="mt-3">
              <button type="button" className="btn-secondary btn-sm" onClick={handleCopy}>
                {copied ? 'Copied!' : 'Copy link'}
              </button>
            </div>
          </div>
        ) : (
          <p className="mt-4 text-stone-500">Loading…</p>
        )}
      </div>

      <div className="card mt-4 flex items-center justify-between">
        <div>
          <p className="section-title">Staff &amp; manager access</p>
          <p className="mt-1 text-sm text-stone-500">Log in to manage the waitlist, tables, and settings.</p>
        </div>
        <Link to="/login" className="btn-primary btn-sm shrink-0">
          Log in
        </Link>
      </div>
    </div>
  )
}
