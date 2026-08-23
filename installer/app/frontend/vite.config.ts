import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base /ui/ : servi par installer/app/backend/server.py sur 127.0.0.1:9877/ui/
// build directement dans backend/static/ (le backend stdlib sert ce dossier).
export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  resolve: {
    alias: {
      // source unique des mascottes, partagee avec le TUI de l'installeur
      '@mascots': fileURLToPath(new URL('../../assets/mascots.json', import.meta.url)),
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
  },
  server: {
    fs: { allow: ['..', '../../assets'] },
    proxy: {
      '/api': { target: 'http://127.0.0.1:9877', changeOrigin: true },
    },
  },
})
