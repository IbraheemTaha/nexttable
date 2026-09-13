import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { api, ApiError } from '../../lib/api'
import { WAITLIST_STATUS_LABELS } from '../../lib/statusLabels'
import type { WaitlistEntry, WaitlistResponse, WaitlistStatus } from '../../lib/types'
import { usePolling } from '../../lib/usePolling'

const ARRIVED_ELIGIBLE: WaitlistStatus[] = ['waiting', 'notified', 'late_demoted']
const SEATED_ELIGIBLE: WaitlistStatus[] = ['arrived', 'notified']
const LEFT_ELIGIBLE: WaitlistStatus[] = ['seated']
const CANCEL_ELIGIBLE: WaitlistStatus[] = ['waiting', 'notified', 'arrived', 'late_demoted']

export function WaitlistPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const statusFilter = searchParams.get('status') === 'waiting' ? 'waiting' : 'all'
  const [data, setData] = useState<WaitlistResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [assignEntryId, setAssignEntryId] = useState('')
  const [assignTableId, setAssignTableId] = useState('')

  const load = () => {
    api
      .get<WaitlistResponse>(`/api/waitlist/${statusFilter === 'waiting' ? '?status=waiting' : ''}`)
      .then(setData)
      .catch(() => undefined)
  }

  usePolling(load, 15000, [statusFilter])

  async function runAction(entry: WaitlistEntry, action: string) {
    try {
      await api.post(`/api/waitlist/${entry.id}/action/${action}/`)
      setMessage(null)
      load()
    } catch (error) {
      setMessage(error instanceof ApiError ? String(error.message) : 'Something went wrong.')
    }
  }

  async function handleAssign(event: React.FormEvent) {
    event.preventDefault()
    try {
      await api.post('/api/waitlist/assign/', { entry_id: assignEntryId, table_id: assignTableId })
      setMessage(null)
      load()
    } catch (error) {
      setMessage(error instanceof ApiError ? String(error.message) : 'Could not assign table.')
    }
  }

  const entries = data?.entries ?? []
  const eligibleEntries = data?.eligible_entries ?? []
  const freeTables = data?.free_tables ?? []

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="page-title">Waitlist</h1>
        <nav className="flex gap-1 rounded-lg border border-stone-200 bg-white p-1">
          <button
            type="button"
            onClick={() => setSearchParams({})}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              statusFilter === 'all' ? 'bg-ember-600 text-white' : 'text-stone-600 hover:bg-stone-100'
            }`}
          >
            All active
          </button>
          <button
            type="button"
            onClick={() => setSearchParams({ status: 'waiting' })}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              statusFilter === 'waiting' ? 'bg-ember-600 text-white' : 'text-stone-600 hover:bg-stone-100'
            }`}
          >
            Waiting only
          </button>
        </nav>
      </div>

      {message && (
        <ul className="mt-4 space-y-2">
          <li className="app-message error">{message}</li>
        </ul>
      )}

      <div className="mt-6">
        {eligibleEntries.length > 0 && freeTables.length > 0 && (
          <section className="card mt-4">
            <h2 className="section-title">Manually assign a table</h2>
            <form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={handleAssign}>
              <label className="field-label">
                Guest
                <select value={assignEntryId} onChange={(e) => setAssignEntryId(e.target.value)} required>
                  <option value="" disabled>
                    Select a guest
                  </option>
                  {eligibleEntries.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.guest_name} (party of {entry.party_size})
                    </option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                Table
                <select value={assignTableId} onChange={(e) => setAssignTableId(e.target.value)} required>
                  <option value="" disabled>
                    Select a table
                  </option>
                  {freeTables.map((table) => (
                    <option key={table.id} value={table.id}>
                      {table.identifier} (capacity {table.capacity})
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" className="btn-primary">
                Assign table
              </button>
            </form>
          </section>
        )}

        <table className="data-table mt-4">
          <thead>
            <tr>
              <th>Guest</th>
              <th>Party</th>
              <th>Est. wait</th>
              <th>Checked in</th>
              <th>Notes</th>
              <th>Status</th>
              <th>Table</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr className="is-empty">
                <td colSpan={8}>No guests on the waitlist.</td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td className="font-medium text-stone-900">{entry.guest_name}</td>
                <td>{entry.party_size}</td>
                <td>{entry.estimated_wait_minutes} min</td>
                <td>{new Date(entry.checked_in_at).toLocaleString()}</td>
                <td className="max-w-[16rem] truncate text-stone-500">{entry.preference_notes}</td>
                <td>
                  <Badge status={entry.status} label={WAITLIST_STATUS_LABELS[entry.status]} />
                </td>
                <td>
                  {entry.assigned_table ? entry.assigned_table.identifier : <span className="text-stone-400">—</span>}
                </td>
                <td>
                  <div className="flex flex-wrap gap-1.5">
                    {ARRIVED_ELIGIBLE.includes(entry.status) && (
                      <button type="button" className="btn-secondary btn-sm" onClick={() => runAction(entry, 'arrived')}>
                        Arrived
                      </button>
                    )}
                    {SEATED_ELIGIBLE.includes(entry.status) && (
                      <button type="button" className="btn-primary btn-sm" onClick={() => runAction(entry, 'seated')}>
                        Seated
                      </button>
                    )}
                    {LEFT_ELIGIBLE.includes(entry.status) && (
                      <button type="button" className="btn-secondary btn-sm" onClick={() => runAction(entry, 'left')}>
                        Left
                      </button>
                    )}
                    {CANCEL_ELIGIBLE.includes(entry.status) && (
                      <>
                        <button type="button" className="btn-ghost btn-sm" onClick={() => runAction(entry, 'cancelled')}>
                          Cancel
                        </button>
                        <button type="button" className="btn-danger btn-sm" onClick={() => runAction(entry, 'no_show')}>
                          No-show
                        </button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-6">
        <Link to="/staff" className="link">
          ← Back to dashboard
        </Link>
      </p>
    </div>
  )
}
