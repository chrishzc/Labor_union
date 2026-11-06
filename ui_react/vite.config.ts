/**
 * File: vite.config.ts
 * Description: Vite 建置設定，含受控環境隔離、manifest 輸出、vendor 拆分與開發代理。
 */
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiTarget = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8000';
const publicPrefix = process.env.VITE_PUBLIC_PATH_PREFIX ?? '';
if (publicPrefix && !/^\/[a-zA-Z0-9_-]+(?:\/[a-zA-Z0-9_-]+)*$/.test(publicPrefix)) {
  throw new Error('VITE_PUBLIC_PATH_PREFIX must be an absolute path without a trailing slash');
}

export default defineConfig({
  // Managed Windows builds use explicit process settings only. In particular,
  // Vite must not discover .env files when preparing a portable artifact.
  envDir:
    process.env.WINDOWS_REMOTE_BUILD === '1' || process.env.REACT_ADMIN_ARTIFACT_BUILD === '1'
      ? false
      : undefined,
  base: publicPrefix ? `${publicPrefix}/` : '/admin/',
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
        changeOrigin: false,
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
  build: {
    manifest: '.vite/manifest.json',
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          if (
            id.includes('/react/') ||
            id.includes('\\react\\') ||
            id.includes('/react-dom/') ||
            id.includes('\\react-dom\\') ||
            id.includes('/scheduler/') ||
            id.includes('\\scheduler\\')
          ) {
            return 'vendor-react';
          }
          if (id.includes('lucide-react')) {
            return 'vendor-icons';
          }
          return 'vendor-utils';
        },
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
