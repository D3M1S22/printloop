/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Backend FastAPI di PrintLoop su :8788 (8080 occupata; 8787 usata da MarginSwarm sulla stessa macchina).
// `npm run dev:fixtures` (mode "fixtures") lavora senza backend sulle risposte in ../web/fixtures.
const API_TARGET = process.env.PRINTLOOP_API ?? 'http://localhost:8788'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { '/api': { target: API_TARGET, changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
