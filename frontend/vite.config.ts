import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'

const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8001'
const base = process.env.GITHUB_PAGES ? '/llm_test/' : '/'

// https://vite.dev/config/
export default defineConfig({
  base,
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/react') || id.includes('/node_modules/react-dom')) {
            return 'react-vendor'
          }
          if (id.includes('/node_modules/@ant-design/icons')) {
            return 'antd-icons'
          }
          if (
            id.includes('/node_modules/@ant-design') ||
            id.includes('/node_modules/@rc-component') ||
            id.includes('/node_modules/rc-')
          ) {
            return 'antd-internals'
          }
          if (id.includes('/node_modules/antd')) {
            return 'antd'
          }
          if (
            id.includes('/node_modules/react-markdown') ||
            id.includes('/node_modules/remark-gfm') ||
            id.includes('/node_modules/unified') ||
            id.includes('/node_modules/micromark')
          ) {
            return 'markdown'
          }
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
