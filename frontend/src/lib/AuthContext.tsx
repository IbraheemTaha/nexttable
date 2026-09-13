import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import type { CurrentUser } from './types'

interface AuthContextValue {
  user: CurrentUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .ensureCsrfCookie()
      .then(() => api.get<CurrentUser>('/api/auth/me/'))
      .then(setUser)
      .catch((error) => {
        if (!(error instanceof ApiError && error.status === 403)) {
          console.error(error)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const loggedInUser = await api.post<CurrentUser>('/api/auth/login/', { username, password })
    setUser(loggedInUser)
  }, [])

  const logout = useCallback(async () => {
    await api.post('/api/auth/logout/')
    setUser(null)
  }, [])

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
