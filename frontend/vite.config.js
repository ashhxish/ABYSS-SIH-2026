import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend never hardcodes a backend host: requests go to /api, which this
// dev server proxies to the Phase 13 intelligence service. That keeps the browser
// on a single origin (no CORS surprises) and needs no API keys.
// For production builds set VITE_API_BASE_URL, e.g. VITE_API_BASE_URL=https://host/api
const API_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    port: 4173,
    host: true,
  },
})
