import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { api, ApiError } from '../../lib/api'
import type { FieldErrors, RestaurantTable, TableStatus } from '../../lib/types'

interface FormState {
  identifier: string
  capacity: string
  status: TableStatus
}

const EMPTY_FORM: FormState = { identifier: '', capacity: '', status: 'free' }

export function TableConfigFormPage() {
  const { tableId } = useParams()
  const isEdit = Boolean(tableId)
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isEdit) return
    api.get<RestaurantTable[]>('/api/table-config/').then((tables) => {
      const table = tables.find((t) => t.id === Number(tableId))
      if (table) {
        setForm({ identifier: table.identifier, capacity: String(table.capacity), status: table.status })
      }
    })
  }, [isEdit, tableId])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      if (isEdit) {
        await api.put(`/api/table-config/${tableId}/`, form)
      } else {
        await api.post('/api/table-config/', form)
      }
      navigate('/manager/tables')
    } catch (error) {
      if (error instanceof ApiError && error.body && typeof error.body === 'object' && 'errors' in error.body) {
        setErrors((error.body as { errors: FieldErrors }).errors)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1 className="page-title">{isEdit ? 'Edit Table' : 'Create Table'}</h1>

      <div className="card mt-6 max-w-lg">
        <form onSubmit={handleSubmit}>
          <FormError errors={errors.__all__} />

          <div className="mt-4 first:mt-0">
            <label className="field-label" htmlFor="identifier">
              Identifier
            </label>
            <input
              id="identifier"
              type="text"
              value={form.identifier}
              onChange={(e) => setForm({ ...form, identifier: e.target.value })}
              required
            />
            <FormError errors={errors.identifier} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="capacity">
              Capacity
            </label>
            <input
              id="capacity"
              type="number"
              min={1}
              value={form.capacity}
              onChange={(e) => setForm({ ...form, capacity: e.target.value })}
              required
            />
            <FormError errors={errors.capacity} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="status">
              Status
            </label>
            <select
              id="status"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as TableStatus })}
            >
              <option value="free">Free</option>
              <option value="reserved">Reserved</option>
              <option value="occupied">Occupied</option>
              <option value="cleaning">Cleaning</option>
            </select>
            <FormError errors={errors.status} />
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {isEdit ? 'Save changes' : 'Create table'}
            </button>
            <Link to="/manager/tables" className="link">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
