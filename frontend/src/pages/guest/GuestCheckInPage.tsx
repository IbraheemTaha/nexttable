import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { FormError } from '../../components/FormError'
import { api, ApiError } from '../../lib/api'
import type { FieldErrors } from '../../lib/types'

type TokenState = 'valid' | 'expired' | 'invalid' | 'loading'

interface FormState {
  guest_name: string
  party_size: string
  phone_number: string
  location_preference: string
  seating_preference: string
  accessibility_requirements: string
  high_chair_needed: string
  notes: string
}

const EMPTY_FORM: FormState = {
  guest_name: '',
  party_size: '',
  phone_number: '',
  location_preference: 'no_preference',
  seating_preference: 'no_preference',
  accessibility_requirements: '',
  high_chair_needed: 'no',
  notes: '',
}

export function GuestCheckInPage() {
  const { token } = useParams()
  const navigate = useNavigate()
  const [tokenState, setTokenState] = useState<TokenState>('loading')
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<FieldErrors>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .get<{ token_state: TokenState }>(`/api/check-in/${token}/`)
      .then((data) => setTokenState(data.token_state))
      .catch((error) => {
        if (error instanceof ApiError && error.body && typeof error.body === 'object' && 'token_state' in error.body) {
          setTokenState((error.body as { token_state: TokenState }).token_state)
        } else {
          setTokenState('invalid')
        }
      })
  }, [token])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors({})
    try {
      const { public_identifier } = await api.post<{ public_identifier: string }>(`/api/check-in/${token}/`, form)
      navigate(`/check-in/status/${public_identifier}`)
    } catch (error) {
      if (error instanceof ApiError && error.body && typeof error.body === 'object' && 'errors' in error.body) {
        setErrors((error.body as { errors: FieldErrors }).errors)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-lg px-4 py-8">
      <p className="app-brand text-center">NextTable</p>
      <div className="card mt-4">
        <h1 className="page-title text-2xl">Join the waitlist</h1>

        {tokenState === 'loading' && <p className="mt-2 text-stone-600">Loading…</p>}

        {tokenState === 'valid' && (
          <>
            <p className="mt-1 text-stone-500">We'll text you when your table is almost ready.</p>
            <form className="mt-5" onSubmit={handleSubmit}>
              <FormError errors={errors.__all__} />

              <div className="mt-4 first:mt-0">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="guest_name">
                    Guest name
                  </label>
                  <span className="field-required">Required</span>
                </div>
                <input
                  id="guest_name"
                  type="text"
                  value={form.guest_name}
                  onChange={(e) => setForm({ ...form, guest_name: e.target.value })}
                  required
                />
                <FormError errors={errors.guest_name} />
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="party_size">
                    Party size
                  </label>
                  <span className="field-required">Required</span>
                </div>
                <input
                  id="party_size"
                  type="number"
                  min={1}
                  value={form.party_size}
                  onChange={(e) => setForm({ ...form, party_size: e.target.value })}
                  required
                />
                <FormError errors={errors.party_size} />
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="phone_number">
                    Phone number
                  </label>
                  <span className="field-hint">Optional</span>
                </div>
                <input
                  id="phone_number"
                  type="tel"
                  value={form.phone_number}
                  onChange={(e) => setForm({ ...form, phone_number: e.target.value })}
                />
                <FormError errors={errors.phone_number} />
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="location_preference">
                    Indoor/outdoor preference
                  </label>
                  <span className="field-hint">Optional</span>
                </div>
                <select
                  id="location_preference"
                  value={form.location_preference}
                  onChange={(e) => setForm({ ...form, location_preference: e.target.value })}
                >
                  <option value="no_preference">No preference</option>
                  <option value="indoor">Indoor</option>
                  <option value="outdoor">Outdoor</option>
                </select>
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="seating_preference">
                    Seating preference
                  </label>
                  <span className="field-hint">Optional</span>
                </div>
                <select
                  id="seating_preference"
                  value={form.seating_preference}
                  onChange={(e) => setForm({ ...form, seating_preference: e.target.value })}
                >
                  <option value="no_preference">No preference</option>
                  <option value="standard">Standard table</option>
                  <option value="booth">Booth</option>
                  <option value="bar">Bar seating</option>
                </select>
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="accessibility_requirements">
                    Accessibility requirements
                  </label>
                  <span className="field-hint">Optional</span>
                </div>
                <textarea
                  id="accessibility_requirements"
                  rows={3}
                  value={form.accessibility_requirements}
                  onChange={(e) => setForm({ ...form, accessibility_requirements: e.target.value })}
                />
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <span className="field-label">High chair need</span>
                  <span className="field-hint">Optional</span>
                </div>
                <div className="mt-1 flex gap-4">
                  <label className="flex items-center gap-1.5 text-sm text-stone-700">
                    <input
                      type="radio"
                      name="high_chair_needed"
                      value="no"
                      checked={form.high_chair_needed === 'no'}
                      onChange={(e) => setForm({ ...form, high_chair_needed: e.target.value })}
                    />
                    No
                  </label>
                  <label className="flex items-center gap-1.5 text-sm text-stone-700">
                    <input
                      type="radio"
                      name="high_chair_needed"
                      value="yes"
                      checked={form.high_chair_needed === 'yes'}
                      onChange={(e) => setForm({ ...form, high_chair_needed: e.target.value })}
                    />
                    Yes
                  </label>
                </div>
              </div>

              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <label className="field-label" htmlFor="notes">
                    Notes
                  </label>
                  <span className="field-hint">Optional</span>
                </div>
                <textarea
                  id="notes"
                  rows={3}
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                />
              </div>

              <button type="submit" className="btn-primary mt-5 w-full" disabled={submitting}>
                Join waitlist
              </button>
            </form>
          </>
        )}

        {tokenState === 'expired' && (
          <p className="mt-2 text-stone-600">
            This check-in link has expired. Please scan today's code or ask the host for help.
          </p>
        )}

        {tokenState === 'invalid' && (
          <p className="mt-2 text-stone-600">
            This check-in link is not available. Please scan today's code or ask the host for help.
          </p>
        )}
      </div>
    </div>
  )
}
