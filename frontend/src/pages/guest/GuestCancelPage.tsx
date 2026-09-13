import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { WAITLIST_STATUS_LABELS } from '../../lib/statusLabels'
import type { GuestStatus } from '../../lib/types'

export function GuestCancelPage() {
  const { publicIdentifier } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<GuestStatus | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api.get<GuestStatus>(`/api/check-in/status/${publicIdentifier}/`).then(setStatus)
  }, [publicIdentifier])

  async function handleConfirm() {
    setSubmitting(true)
    try {
      await api.post(`/api/check-in/status/${publicIdentifier}/cancel/`)
      navigate(`/check-in/status/${publicIdentifier}`)
    } finally {
      setSubmitting(false)
    }
  }

  if (!status) {
    return (
      <div className="mx-auto max-w-lg px-4 py-8">
        <p className="app-brand text-center">NextTable</p>
        <div className="card mt-4">
          <p className="text-stone-600">Loading…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <p className="app-brand text-center">NextTable</p>
      <div className="card mt-4">
        <h1 className="page-title text-2xl">Cancel your waitlist spot?</h1>
        <p className="mt-2 text-stone-600">
          This will remove {status.guest_name}'s party of {status.party_size} from the active waitlist.
        </p>

        {status.can_cancel ? (
          <div className="mt-4 flex items-center gap-3">
            <button type="button" className="btn-danger" onClick={handleConfirm} disabled={submitting}>
              Confirm cancellation
            </button>
            <Link to={`/check-in/status/${publicIdentifier}`} className="link">
              Keep my spot
            </Link>
          </div>
        ) : (
          <>
            <p className="app-message warning mt-4">
              This waitlist spot can no longer be cancelled because its current status is{' '}
              {WAITLIST_STATUS_LABELS[status.status]}.
            </p>
            <p className="mt-4">
              <Link to={`/check-in/status/${publicIdentifier}`} className="link">
                Return to waiting page
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
