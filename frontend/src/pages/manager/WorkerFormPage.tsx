import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { api, ApiError } from '../../lib/api'
import type { FieldErrors, Worker } from '../../lib/types'

interface FormState {
  username: string
  first_name: string
  last_name: string
  email: string
  password1: string
  password2: string
  is_active: boolean
  role: 'staff' | 'manager'
}

const EMPTY_FORM: FormState = {
  username: '',
  first_name: '',
  last_name: '',
  email: '',
  password1: '',
  password2: '',
  is_active: true,
  role: 'staff',
}

export function WorkerFormPage() {
  const { userId } = useParams()
  const isEdit = Boolean(userId)
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isEdit) return
    api.get<Worker[]>('/api/workers/').then((workers) => {
      const worker = workers.find((w) => w.id === Number(userId))
      if (worker) {
        setForm((prev) => ({
          ...prev,
          username: worker.username,
          first_name: worker.first_name,
          last_name: worker.last_name,
          email: worker.email,
          is_active: worker.is_active,
          role: worker.role,
        }))
      }
    })
  }, [isEdit, userId])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      if (isEdit) {
        await api.put(`/api/workers/${userId}/`, {
          username: form.username,
          first_name: form.first_name,
          last_name: form.last_name,
          email: form.email,
          is_active: form.is_active,
          role: form.role,
        })
      } else {
        await api.post('/api/workers/', form)
      }
      navigate('/manager/workers')
    } catch (error) {
      if (error instanceof ApiError && error.body && typeof error.body === 'object' && 'errors' in error.body) {
        setErrors((error.body as { errors: FieldErrors }).errors)
      }
    } finally {
      setSubmitting(false)
    }
  }

  const nonFieldErrors = errors.__all__

  return (
    <div>
      <h1 className="page-title">{isEdit ? 'Edit Worker Account' : 'Create Worker Account'}</h1>

      <div className="card mt-6 max-w-lg">
        <form onSubmit={handleSubmit}>
          <FormError errors={nonFieldErrors} />

          <div className="mt-4 first:mt-0">
            <label className="field-label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
            <FormError errors={errors.username} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="first_name">
              First name
            </label>
            <input
              id="first_name"
              type="text"
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            />
            <FormError errors={errors.first_name} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="last_name">
              Last name
            </label>
            <input
              id="last_name"
              type="text"
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            />
            <FormError errors={errors.last_name} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <FormError errors={errors.email} />
          </div>

          {!isEdit && (
            <>
              <div className="mt-4">
                <label className="field-label" htmlFor="password1">
                  Password
                </label>
                <input
                  id="password1"
                  type="password"
                  value={form.password1}
                  onChange={(e) => setForm({ ...form, password1: e.target.value })}
                  required
                />
                <FormError errors={errors.password1} />
              </div>

              <div className="mt-4">
                <label className="field-label" htmlFor="password2">
                  Password confirmation
                </label>
                <input
                  id="password2"
                  type="password"
                  value={form.password2}
                  onChange={(e) => setForm({ ...form, password2: e.target.value })}
                  required
                />
                <FormError errors={errors.password2} />
              </div>
            </>
          )}

          <div className="mt-4">
            <label className="field-label" htmlFor="role">
              Role
            </label>
            <select
              id="role"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as 'staff' | 'manager' })}
            >
              <option value="staff">Staff</option>
              <option value="manager">Manager</option>
            </select>
            <FormError errors={errors.role} />
          </div>

          <div className="mt-4 flex items-center gap-2">
            <input
              id="is_active"
              type="checkbox"
              className="!mt-0 !w-auto"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
            />
            <label className="field-label !mt-0" htmlFor="is_active">
              Active
            </label>
            <FormError errors={errors.is_active} />
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {isEdit ? 'Save changes' : 'Create account'}
            </button>
            <Link to="/manager/workers" className="link">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
