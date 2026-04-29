/* eslint-disable no-undef */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Bind to all interfaces so multiplayer guests can reach the dev SPA over LAN.
// Override TT_FRONTEND_HOST=127.0.0.1 to restrict to localhost only.
const host = (typeof process !== 'undefined' && process.env && process.env.TT_FRONTEND_HOST) || '0.0.0.0'

export default defineConfig({
  plugins: [react()],
  server: {
    host,
  },
  preview: {
    host,
  },
})
