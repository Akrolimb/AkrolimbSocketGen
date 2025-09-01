import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    fs: {
      allow: ['..']
    },
    proxy: {
      // Optional: Serve /data from the host’s testModel folder if running in dev
    }
  },
})
