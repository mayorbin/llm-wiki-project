import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 将 /api/* 请求代理到后端 FastAPI (开发环境)
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 大文件上传和长时间 LLM 调用需要更长超时
        timeout: 300000,       // 5 分钟
        proxyTimeout: 300000,
      },
    },
  },
})
