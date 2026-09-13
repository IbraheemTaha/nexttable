import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../lib/api'
import { WAITLIST_STATUS_LABELS } from '../../lib/statusLabels'
import type { GuestStatus } from '../../lib/types'
import { usePolling } from '../../lib/usePolling'

export function GuestStatusPage() {
  const { publicIdentifier } = useParams()
  const [status, setStatus] = useState<GuestStatus | null>(null)

  usePolling(
    () => {
      api.get<GuestStatus>(`/api/check-in/status/${publicIdentifier}/`).then(setStatus)
    },
    15000,
    [publicIdentifier],
  )

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
        <h1 className="page-title text-2xl">You're on the waitlist</h1>

        <dl className="mt-4 grid grid-cols-2 gap-4 border-b border-stone-100 pb-4">
          <div>
            <dt className="field-hint">Guest name</dt>
            <dd className="mt-0.5 font-medium text-stone-900">{status.guest_name}</dd>
          </div>
          <div>
            <dt className="field-hint">Party size</dt>
            <dd className="mt-0.5 font-medium text-stone-900">{status.party_size}</dd>
          </div>
        </dl>

        <div className="mt-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="field-hint">Status</p>
              <p className="mt-0.5 text-lg font-semibold text-stone-900">{WAITLIST_STATUS_LABELS[status.status]}</p>
            </div>
            <div className="text-right">
              <p className="field-hint">Estimated wait</p>
              <p className="mt-0.5 text-lg font-semibold text-ember-700">{status.estimated_wait_minutes} minutes</p>
            </div>
          </div>

          {status.show_table_ready_message && (
            <p className="app-message success mt-4">
              Your table is ready. Please check in with staff or approach the host stand.
            </p>
          )}

          {status.can_cancel ? (
            <p className="mt-4">
              <Link to={`/check-in/status/${publicIdentifier}/cancel`} className="link">
                Cancel waitlist spot
              </Link>
            </p>
          ) : (
            <p className="mt-4 text-sm text-stone-500">Cancellation is not available for this status.</p>
          )}
        </div>
      </div>
    </div>
  )
}
