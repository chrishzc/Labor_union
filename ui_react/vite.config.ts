/**
 * @file vite.config.ts
 * @description Vite 構建配置，包含後端 API 代理設定與 Vitest happy-dom 測試環境。
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  base: '/admin/',
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/line-': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  // @ts-expect-error vitest configuration is read directly by vitest runner
  test: {
    globals: true,
    environment: 'happy-dom',
    setupFiles: './src/tests/setup.ts',
    include: ['src/tests/**/*.{test,spec}.{ts,tsx}'],
  },
});
