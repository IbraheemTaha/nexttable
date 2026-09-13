import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../lib/api'
import type { TableStatusResponse } from '../../lib/types'
import { usePolling } from '../../lib/usePolling'

const NEXT_STATUS: Record<string, { target: string; label: string; className: string }> = {
  free: { target: 'occupied', label: 'Seat walk-in', className: 'btn-primary btn-sm' },
  occupied: { target: 'cleaning', label: 'Mark cleaning', className: 'btn-secondary btn-sm' },
  cleaning: { target: 'free', label: 'Mark free', className: 'btn-secondary btn-sm' },
  reserved: { target: 'free', label: 'Mark free', className: 'btn-secondary btn-sm' },
}

export function TableStatusPage() {
  const [data, setData] = useState<TableStatusResponse | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [assignEntryId, setAssignEntryId] = useState('')
  const [assignTableId, setAssignTableId] = useState('')

  const load = () => {
    api
      .get<TableStatusResponse>('/api/tables/')
      .then(setData)
      .catch(() => undefined)
  }

  usePolling(load, 15000, [])

  async function runAction(tableId: number, targetStatus: string) {
    try {
      await api.post(`/api/tables/${tableId}/status/${targetStatus}/`)
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

  const eligibleEntries = data?.eligible_entries ?? []
  const freeTables = data?.free_tables ?? []
  const statusGroups = data?.status_groups ?? []

  return (
    <div>
      <h1 className="page-title">Table status</h1>

      {message && (
        <ul className="mt-4 space-y-2">
          <li className="app-message error">{message}</li>
        </ul>
      )}

      {eligibleEntries.length > 0 && freeTables.length > 0 && (
        <section className="card mb-6 mt-6">
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

      {statusGroups.map((group) => {
        const action = NEXT_STATUS[group.status]
        return (
          <section key={group.status} className="mt-6 first:mt-0">
            <h2 className="section-title flex items-center gap-2">
              {group.label}
              <span className={`badge badge-${group.status}`}>{group.tables.length}</span>
            </h2>
            {group.tables.length === 0 ? (
              <p className="empty-state mt-3">No tables with this status.</p>
            ) : (
              <table className="data-table mt-3">
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Capacity</th>
                    <th>Guest</th>
                    <th>Party</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {group.tables.map((table) => (
                    <tr key={table.id}>
                      <td className="font-medium text-stone-900">{table.identifier}</td>
                      <td>{table.capacity}</td>
                      {table.current_guest_entry ? (
                        <>
                          <td>{table.current_guest_entry.guest_name}</td>
                          <td>{table.current_guest_entry.party_size}</td>
                        </>
                      ) : (
                        <>
                          <td className="text-stone-400">—</td>
                          <td className="text-stone-400">—</td>
                        </>
                      )}
                      <td>
                        {action && (
                          <button
                            type="button"
                            className={action.className}
                            onClick={() => runAction(table.id, action.target)}
                          >
                            {action.label}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )
      })}

      <p className="mt-6">
        <Link to="/staff" className="link">
          ← Back to dashboard
        </Link>
      </p>
    </div>
  )
}
