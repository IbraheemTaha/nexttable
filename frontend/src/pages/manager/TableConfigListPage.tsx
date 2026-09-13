import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../lib/api'
import { TABLE_STATUS_LABELS } from '../../lib/statusLabels'
import type { RestaurantTable } from '../../lib/types'

export function TableConfigListPage() {
  const [tables, setTables] = useState<RestaurantTable[]>([])
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string } | null>(null)

  const load = () => api.get<RestaurantTable[]>('/api/table-config/').then(setTables)

  useEffect(() => {
    load()
  }, [])

  async function handleRemove(table: RestaurantTable) {
    if (!confirm(`Remove table "${table.identifier}"? This cannot be undone.`)) return
    try {
      await api.delete(`/api/table-config/${table.id}/`)
      setMessage(null)
      load()
    } catch (error) {
      setMessage({
        type: 'error',
        text: error instanceof ApiError ? String(error.message) : 'Could not remove table.',
      })
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="page-title">Tables</h1>
        <Link to="/manager/tables/new" className="btn-primary btn-sm">
          Create table
        </Link>
      </div>

      {message && (
        <ul className="mt-4 space-y-2">
          <li className={`app-message ${message.type}`}>{message.text}</li>
        </ul>
      )}

      <table className="data-table mt-6">
        <thead>
          <tr>
            <th>Identifier</th>
            <th>Capacity</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {tables.length === 0 && (
            <tr className="is-empty">
              <td colSpan={4}>No tables configured.</td>
            </tr>
          )}
          {tables.map((table) => (
            <tr key={table.id}>
              <td className="font-medium text-stone-900">{table.identifier}</td>
              <td>{table.capacity}</td>
              <td>
                <span className={`badge badge-${table.status}`}>{TABLE_STATUS_LABELS[table.status]}</span>
              </td>
              <td className="space-x-3">
                <Link to={`/manager/tables/${table.id}`} className="link">
                  Edit
                </Link>
                <button type="button" className="link" onClick={() => handleRemove(table)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
