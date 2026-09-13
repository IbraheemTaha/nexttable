import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { api, ApiError } from '../../lib/api'
import type { EtaRule, FieldErrors } from '../../lib/types'

interface FormState {
  min_party_size: string
  max_party_size: string
  estimated_wait_minutes: string
  is_active: boolean
}

const EMPTY_FORM: FormState = {
  min_party_size: '',
  max_party_size: '',
  estimated_wait_minutes: '',
  is_active: true,
}

export function EtaRuleFormPage() {
  const { ruleId } = useParams()
  const isEdit = Boolean(ruleId)
  const navigate = useNavigate()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!isEdit) return
    api.get<{ rules: EtaRule[] }>('/api/eta/').then((data) => {
      const rule = data.rules.find((r) => r.id === Number(ruleId))
      if (rule) {
        setForm({
          min_party_size: String(rule.min_party_size),
          max_party_size: rule.max_party_size !== null ? String(rule.max_party_size) : '',
          estimated_wait_minutes: String(rule.estimated_wait_minutes),
          is_active: rule.is_active,
        })
      }
    })
  }, [isEdit, ruleId])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      const payload = {
        min_party_size: form.min_party_size,
        max_party_size: form.max_party_size || null,
        estimated_wait_minutes: form.estimated_wait_minutes,
        is_active: form.is_active,
      }
      if (isEdit) {
        await api.put(`/api/eta/rules/${ruleId}/`, payload)
      } else {
        await api.post('/api/eta/rules/', payload)
      }
      navigate('/manager/eta')
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
      <h1 className="page-title">{isEdit ? 'Edit ETA Rule' : 'Create ETA Rule'}</h1>

      <div className="card mt-6 max-w-lg">
        <form onSubmit={handleSubmit}>
          <FormError errors={errors.__all__} />

          <div className="mt-4 first:mt-0">
            <label className="field-label" htmlFor="min_party_size">
              Minimum party size
            </label>
            <input
              id="min_party_size"
              type="number"
              min={1}
              value={form.min_party_size}
              onChange={(e) => setForm({ ...form, min_party_size: e.target.value })}
              required
            />
            <FormError errors={errors.min_party_size} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="max_party_size">
              Maximum party size
            </label>
            <input
              id="max_party_size"
              type="number"
              min={1}
              value={form.max_party_size}
              onChange={(e) => setForm({ ...form, max_party_size: e.target.value })}
            />
            <p className="field-hint">Leave blank for an open-ended range.</p>
            <FormError errors={errors.max_party_size} />
          </div>

          <div className="mt-4">
            <label className="field-label" htmlFor="estimated_wait_minutes">
              Estimated wait (minutes)
            </label>
            <input
              id="estimated_wait_minutes"
              type="number"
              min={1}
              value={form.estimated_wait_minutes}
              onChange={(e) => setForm({ ...form, estimated_wait_minutes: e.target.value })}
              required
            />
            <FormError errors={errors.estimated_wait_minutes} />
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
          </div>
          <FormError errors={errors.is_active} />

          <div className="mt-5 flex items-center gap-3">
            <button type="submit" className="btn-primary" disabled={submitting}>
              {isEdit ? 'Save changes' : 'Create rule'}
            </button>
            <Link to="/manager/eta" className="link">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </div>
  )
}
