import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: {
    outDir: '../backend/static/frontend',
    emptyOutDir: true,
  },
})