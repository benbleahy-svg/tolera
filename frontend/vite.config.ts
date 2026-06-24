import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev the SPA is served on :5173 and proxies backend routes to FastAPI
// (:8000), so React -> FastAPI -> Postgres round-trips without CORS.
const API_TARGET = process.env.VITE_API_PROXY ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': API_TARGET,
      '/healthz': API_TARGET,
      '/readyz': API_TARGET,
      '/metrics': API_TARGET,
    },
  },
})
