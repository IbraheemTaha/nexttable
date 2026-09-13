import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/AuthContext'

const STAFF_LINKS = [
  { to: '/staff/waitlist', label: 'Waitlist' },
  { to: '/staff/tables', label: 'Tables' },
]

const MANAGER_LINKS = [
  { to: '/manager/workers', label: 'Workers' },
  { to: '/manager/tables', label: 'Tables' },
  { to: '/manager/eta', label: 'ETA rules' },
]

export function AppLayout({ variant }: { variant: 'staff' | 'manager' }) {
  const { user, logout } = useAuth()
  const links = variant === 'staff' ? STAFF_LINKS : MANAGER_LINKS
  const brandHref = variant === 'staff' ? '/staff' : '/manager'

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="app-header">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <NavLink to={brandHref} className="app-brand">
              NextTable
            </NavLink>
            <nav className="flex items-center gap-1">
              {links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) => `app-nav-link${isActive ? ' is-active' : ''}`}
                >
                  {link.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-stone-500 sm:inline">{user?.username}</span>
            <button type="button" className="btn-ghost btn-sm" onClick={() => logout()}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
