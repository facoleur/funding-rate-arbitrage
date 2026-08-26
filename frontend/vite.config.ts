import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_APP_VERSION': JSON.stringify(
      process.env.VITE_APP_VERSION ?? 'local'
    ),
  },
  server: {
    proxy: {
      '/api': process.env.API_URL ?? 'http://localhost:8001',
    },
  },
})
