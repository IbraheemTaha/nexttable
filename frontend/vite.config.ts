import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Same-origin from the browser's point of view, so the session
      // cookie set by Django works without any cross-site cookie dance in
      // dev. Production points VITE_API_BASE_URL at the deployed API
      // origin instead and relies on CORS (see src/lib/api.ts).
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
