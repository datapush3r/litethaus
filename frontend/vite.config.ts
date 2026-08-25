import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        // Defaults to the dev-compose backend service; override to point
        // this dev server at any other running backend, e.g.
        // VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
        //
        // No path rewrite: the backend's real routes live under "/api/*"
        // (see main.py's `api` router) - that prefix is what the auth
        // middleware gates on, not a proxy-only convention, so it must be
        // forwarded through unchanged rather than stripped.
        target: process.env.VITE_API_PROXY_TARGET || 'http://backend:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
