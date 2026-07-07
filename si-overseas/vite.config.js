import { fileURLToPath, URL } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig } from 'vite';

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
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
