import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Backend that serves /api, /media and the WebSocket endpoints.
const backend = process.env.BACKEND_URL ?? 'http://localhost:8000'

const proxy = {
  '/api': {
    target: backend,
    changeOrigin: true,
    ws: true,
  },
  '/media': {
    target: backend,
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    allowedHosts: true,
    proxy,
  },
  // `vite preview` serves the production build; it needs the same proxy so the
  // SPA can reach the API/WebSocket same-origin, and must accept the public
  // tunnel hostname (Vite 5.4+ enforces host checking).
  preview: {
    port: 5173,
    host: true,
    allowedHosts: true,
    proxy,
  },
})
