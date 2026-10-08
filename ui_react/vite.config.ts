/**
 * @file vite.config.ts
 * @description Vite 構建配置，包含後端 API 代理設定與 Vitest happy-dom 測試環境。
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  base: '/admin/',
  plugins: [react(), {
    name: 'line-webhook-declared-size-limit',
    configureServer(server) {
      // Same transport limit as api/line_webhook_boundary.py. Reject before
      // proxy writes can race the API's early 413; chunked bodies remain bounded by the API.
      server.middlewares.use((request, response, next) => {
        const path = request.url?.split('?')[0];
        const aliases = ['/webhook', '/webhook/', '/webhook/line', '/webhook/line/'];
        const length = request.headers['content-length'];
        if (request.method === 'POST' && aliases.includes(path ?? '')
          && length !== undefined && Number(length) > 1024 * 1024) {
          response.writeHead(413, { 'Content-Type': 'application/json', Connection: 'close' });
          response.end(JSON.stringify({ detail: 'LINE webhook body too large' }));
          return;
        }
        next();
      });
    },
  }],
  server: {
    port: 5173,
    host: true,
    allowedHosts: ['uncured-dismay-patience.ngrok-free.dev'],
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/line-': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/webhook': {
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
