import { fileURLToPath, URL } from 'node:url';

import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vitest/config';

const proxyTarget = process.env.PROXY_TARGET || 'http://localhost:8000';
const previewAllowedHosts = process.env.PREVIEW_ALLOWED_HOSTS
  ? process.env.PREVIEW_ALLOWED_HOSTS.split(',').map(s => s.trim()).filter(Boolean)
  : [];

export default defineConfig({
  plugins: [vue()],
  cacheDir: '.vite-cache',
  optimizeDeps: {
    entries: ['index.html'],
  },
  resolve: {
    extensions: ['.ts', '.tsx', '.vue', '.mjs', '.js', '.json'],
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    allowedHosts: ['.lhr.life', '.localhost.run', '.ngrok.io', '.ngrok-free.app'],
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000,
      },
    },
  },
  preview: {
    allowedHosts: previewAllowedHosts.length > 0 ? previewAllowedHosts : ['localhost'],
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
  },
});
