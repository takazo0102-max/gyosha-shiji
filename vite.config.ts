import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base is '/' for dev, '/gyosha-shiji/' for production (GitHub Pages)
export default defineConfig({
  plugins: [react()],
  base: process.env.NODE_ENV === 'production' ? '/gyosha-shiji/' : '/',
})
