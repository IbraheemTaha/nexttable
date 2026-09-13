import { Link } from 'react-router-dom'

export function ManagerLandingPage() {
  return (
    <div>
      <p className="eyebrow">Back of house</p>
      <h1 className="page-title mt-1">Manager</h1>

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <Link to="/manager/workers" className="card block transition-shadow hover:shadow-md">
          <p className="section-title">Worker accounts</p>
          <p className="mt-1 text-sm text-stone-500">Add staff, set roles, deactivate access.</p>
        </Link>
        <Link to="/manager/tables" className="card block transition-shadow hover:shadow-md">
          <p className="section-title">Tables</p>
          <p className="mt-1 text-sm text-stone-500">Configure the floor plan and seating capacity.</p>
        </Link>
        <Link to="/manager/eta" className="card block transition-shadow hover:shadow-md">
          <p className="section-title">ETA rules</p>
          <p className="mt-1 text-sm text-stone-500">Tune wait-time estimates by party size.</p>
        </Link>
      </div>
    </div>
  )
}
