/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// PrintLoop FastAPI backend on :8788 (8080 is taken; 8787 is used by MarginSwarm on the same machine).
// `npm run dev:fixtures` (mode "fixtures") works without a backend on the replies in ../web/fixtures.
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
