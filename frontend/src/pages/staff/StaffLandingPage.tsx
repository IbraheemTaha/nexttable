import { Link } from 'react-router-dom'
import { CheckInLinkCard } from '../../components/CheckInLinkCard'

export function StaffLandingPage() {
  return (
    <div>
      <p className="eyebrow">Host stand</p>
      <h1 className="page-title mt-1">Staff dashboard</h1>

      <nav className="mt-6 grid gap-4 sm:grid-cols-2">
        <Link to="/staff/waitlist" className="card block transition-shadow hover:shadow-md">
          <p className="section-title">Waitlist</p>
          <p className="mt-1 text-sm text-stone-500">
            Check guests in, track wait times, and seat tables as they open up.
          </p>
        </Link>
        <Link to="/staff/tables" className="card block transition-shadow hover:shadow-md">
          <p className="section-title">Table status</p>
          <p className="mt-1 text-sm text-stone-500">
            See what's free, occupied, or being cleaned across the floor.
          </p>
        </Link>
      </nav>

      <CheckInLinkCard />
    </div>
  )
}
