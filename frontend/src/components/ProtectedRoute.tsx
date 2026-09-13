import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'
import type { WorkerRole } from '../lib/types'

export function ProtectedRoute({
  role,
  children,
}: {
  role: WorkerRole | 'staff_or_manager'
  children: React.ReactNode
}) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return null

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  const allowed =
    role === 'staff_or_manager' ? user.role === 'staff' || user.role === 'manager' : user.role === role

  if (!allowed) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <p className="section-title">Access denied</p>
        <p className="mt-2 text-stone-600">Your account does not have permission to view this page.</p>
      </div>
    )
  }

  return <>{children}</>
}
