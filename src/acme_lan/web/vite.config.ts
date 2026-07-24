import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  build: { outDir: 'dist', emptyOutDir: true },
  server: {
    // During `npm run dev`, proxy API calls to the running acme-lan backend.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
