// In dev, Vite's proxy makes /api same-origin (see vite.config.ts) so the
// Django session cookie just works. In production, set VITE_API_BASE_URL to
// the deployed API's origin; CORS + CSRF_TRUSTED_ORIGINS on the backend must
// list the frontend's own origin for the credentialed cross-origin request
// to succeed (see backend/config/settings.py FRONTEND_ORIGINS).
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    super(typeof body === 'object' && body && 'detail' in body ? String((body as { detail: unknown }).detail) : `API error ${status}`)
    this.status = status
    this.body = body
  }
}

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)

  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  // Django's CSRF protection checks this header against the csrftoken
  // cookie for any unsafe method; GET/HEAD/OPTIONS don't need it.
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = getCookie('csrftoken')
    if (csrfToken) headers.set('X-CSRFToken', csrfToken)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    method,
    headers,
    credentials: 'include',
  })

  if (response.status === 204) return undefined as T

  const contentType = response.headers.get('content-type') ?? ''
  const body = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) throw new ApiError(response.status, body)
  return body as T
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'POST', body: data !== undefined ? JSON.stringify(data) : undefined }),
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: 'PUT', body: data !== undefined ? JSON.stringify(data) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  // Ensures a csrftoken cookie exists before the first mutating request -
  // Django only sets it when a view explicitly asks for a token, so a
  // fresh browser has no cookie (and thus can't send X-CSRFToken) until
  // this fires once.
  ensureCsrfCookie: () => request<{ csrfToken: string }>('/api/auth/csrf/'),
}
