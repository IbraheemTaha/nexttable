import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { api, ApiError } from '../../lib/api'
import type { FieldErrors, RestaurantSettings } from '../../lib/types'

export function GracePeriodFormPage() {
  const navigate = useNavigate()
  const [minutes, setMinutes] = useState('')
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .get<{ settings: RestaurantSettings }>('/api/eta/')
      .then((data) => setMinutes(String(data.settings.grace_period_minutes)))
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      await api.put('/api/eta/grace-period/', { grace_period_minutes: minutes })
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
      <h1 className="page-title">Edit Grace Period</h1>

      <div className="card mt-6 max-w-lg">
        <form onSubmit={handleSubmit}>
          <FormError errors={errors.__all__} />

          <div>
            <label className="field-label" htmlFor="grace_period_minutes">
              Grace period minutes
            </label>
            <input
              id="grace_period_minutes"
              type="number"
              min={1}
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              required
            />
            <FormError errors={errors.grace_period_minutes} />
          </div>

          <div className="mt-5 flex items-center gap-3">
            <button type="submit" className="btn-primary" disabled={submitting}>
              Save changes
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
