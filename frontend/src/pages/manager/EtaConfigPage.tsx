import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import type { EtaRule, RestaurantSettings } from '../../lib/types'

export function EtaConfigPage() {
  const [settings, setSettings] = useState<RestaurantSettings | null>(null)
  const [rules, setRules] = useState<EtaRule[]>([])

  useEffect(() => {
    api.get<{ settings: RestaurantSettings; rules: EtaRule[] }>('/api/eta/').then((data) => {
      setSettings(data.settings)
      setRules(data.rules)
    })
  }, [])

  return (
    <div>
      <h1 className="page-title">ETA configuration</h1>

      <section className="card mt-6">
        <h2 className="section-title">Grace period</h2>
        <p className="mt-2 text-stone-600">
          Notified guest grace period: <strong>{settings?.grace_period_minutes} minutes</strong>
        </p>
        <p className="mt-3">
          <Link to="/manager/eta/grace-period" className="link">
            Edit grace period
          </Link>
        </p>
      </section>

      <section className="mt-6">
        <div className="flex items-center justify-between">
          <h2 className="section-title">Party-size ETA rules</h2>
          <Link to="/manager/eta/rules/new" className="btn-primary btn-sm">
            Create ETA rule
          </Link>
        </div>

        <table className="data-table mt-4">
          <thead>
            <tr>
              <th>Min party</th>
              <th>Max party</th>
              <th>Estimated wait</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && (
              <tr className="is-empty">
                <td colSpan={5}>No ETA rules configured.</td>
              </tr>
            )}
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td>{rule.min_party_size}</td>
                <td>{rule.max_party_size ?? <span className="text-stone-400">Open-ended</span>}</td>
                <td>{rule.estimated_wait_minutes} minutes</td>
                <td>
                  {rule.is_active ? (
                    <span className="badge badge-free">Active</span>
                  ) : (
                    <span className="badge badge-left">Inactive</span>
                  )}
                </td>
                <td>
                  <Link to={`/manager/eta/rules/${rule.id}`} className="link">
                    Edit
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
