import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const backendTarget = process.env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  cacheDir: '.cache/vite',
  server: {
    port: 5173,
    strictPort: true,
    // 浏览器请求 /api，由开发服务器转交后端，组件无需写死服务器地址。
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 240000,
        proxyTimeout: 240000,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
