// @vitest-environment node
/** Real development ingress rejects oversized declared webhook uploads before forwarding. */
import { createServer as createHttpServer, request } from 'node:http';
import { type AddressInfo } from 'node:net';
import { createServer } from 'vite';
import { expect, test } from 'vitest';

const requestTimeoutMs = 30_000;

test('declared webhook limit is checked before proxy I/O; ordinary routes still forward', async () => {
  let upstreamCalls = 0;
  let upstreamBytes = 0;
  const upstream = createHttpServer((req, res) => {
    upstreamCalls++;
    req.on('data', chunk => { upstreamBytes += chunk.length; });
    req.resume();
    req.on('end', () => res.writeHead(200).end('upstream'));
  });
  await new Promise<void>(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const previous = process.env.VITE_DEV_API_TARGET;
  process.env.VITE_DEV_API_TARGET = `http://127.0.0.1:${(upstream.address() as AddressInfo).port}`;
  const vite = await createServer({
    logLevel: 'silent',
    // HTTP policy is static; unrelated repository test fixtures must not trigger HMR/restarts.
    server: { host: '127.0.0.1', port: 0, watch: null },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    await vite.listen();
    const port = (vite.httpServer!.address() as AddressInfo).port;
    const send = (path: string, size: number, sendBody = true) => new Promise<number>((resolve, reject) => {
      const req = request({ host: '127.0.0.1', port, path, method: 'POST', headers: { 'Content-Length': size } }, res => {
        res.resume();
        res.on('end', () => resolve(res.statusCode!));
      });
      req.on('error', reject);
      req.setTimeout(requestTimeoutMs, () => req.destroy(new Error(`HTTP timeout: POST ${path}, declared bytes=${size}, upstream bytes=${upstreamBytes}`)));
      if (sendBody) req.end(Buffer.alloc(size));
      else req.flushHeaders();
    });
    for (const alias of ['/webhook', '/webhook/', '/webhook/line', '/webhook/line/']) {
      const before = upstreamCalls;
      expect(await send(`${alias}?test=1`, 1024 * 1024 + 1, false)).toBe(413);
      expect(upstreamCalls).toBe(before);
      const bytesBefore = upstreamBytes;
      expect(await send(alias, 1024 * 1024)).toBe(200);
      expect(upstreamCalls).toBe(before + 1);
      expect(upstreamBytes).toBe(bytesBefore + 1024 * 1024);
    }
    const before = upstreamCalls;
    expect(await send('/api/test', 1024 * 1024 + 1)).toBe(200);
    expect(upstreamCalls).toBe(before + 1);
  } finally {
    upstream.closeAllConnections();
    if (vite.httpServer && 'closeAllConnections' in vite.httpServer) vite.httpServer.closeAllConnections();
    await vite.close();
    await new Promise<void>(resolve => upstream.close(() => resolve()));
    if (previous === undefined) delete process.env.VITE_DEV_API_TARGET;
    else process.env.VITE_DEV_API_TARGET = previous;
  }
// This verifies size/forwarding policy, not localhost throughput under concurrent test load.
}, requestTimeoutMs * 9 + 30_000);
