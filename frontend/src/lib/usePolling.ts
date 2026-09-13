import { useEffect } from 'react'

// Mirrors the old HTMX `hx-trigger="load, every Ns"` pattern: run once
// immediately, then on an interval, until the component unmounts or a
// dependency changes.
export function usePolling(callback: () => void, intervalMs: number, deps: unknown[] = []) {
  useEffect(() => {
    callback()
    const id = setInterval(callback, intervalMs)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}
