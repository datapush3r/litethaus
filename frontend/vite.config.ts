import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        // Defaults to the dev-compose backend service; override to point
        // this dev server at any other running backend, e.g.
        // VITE_API_PROXY_TARGET=http://localhost:8000 npm run dev
        target: process.env.VITE_API_PROXY_TARGET || 'http://backend:8000',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
