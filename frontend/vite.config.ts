import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Root .env (shared with the Django backend) declares BACKEND_PORT - load
  // it from there instead of duplicating the port in a frontend-only file.
  // The empty prefix ('') makes loadEnv return unprefixed vars too, not
  // just VITE_*.
  const rootEnv = loadEnv(mode, '..', '')
  const backendPort = rootEnv.BACKEND_PORT || '8000'

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      // Fail fast instead of silently binding to the next free port - a
      // drifted port (5174, 5175, ...) won't be in FRONTEND_ORIGINS and every
      // authenticated request will fail CSRF with a confusing 403.
      strictPort: true,
      proxy: {
        // Same-origin from the browser's point of view, so the session
        // cookie set by Django works without any cross-site cookie dance in
        // dev. Production points VITE_API_BASE_URL at the deployed API
        // origin instead and relies on CORS (see src/lib/api.ts).
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  }
})
