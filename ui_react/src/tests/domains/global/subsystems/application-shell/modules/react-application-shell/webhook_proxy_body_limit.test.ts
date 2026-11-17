// @vitest-environment node
/** Real development ingress rejects oversized declared webhook uploads before forwarding. */
import { createServer as createHttpServer, request } from 'node:http';
import { type AddressInfo } from 'node:net';
import { createServer, type ProxyOptions } from 'vite';
import { expect, test } from 'vitest';

const requestTimeoutMs = 30_000;

test('declared webhook limit is checked before proxy I/O; ordinary routes still forward', async () => {
  let upstreamCalls = 0;
  let upstreamBytes = 0;
  let upstreamPhase = '未收到請求';
  let proxyPhase = '未轉送';
  const observeProxy: ProxyOptions['configure'] = proxy => {
    proxy.on('proxyReq', (_request, incoming) => { proxyPhase = `${incoming.url} 已轉送`; });
    proxy.on('proxyRes', (response, incoming) => { proxyPhase = `${incoming.url} 收到後端回應 ${response.statusCode}`; });
  };
  const responseBody = Buffer.from('upstream');
  const upstream = createHttpServer((req, res) => {
    upstreamCalls++;
    upstreamPhase = `${req.url} 收到標頭`;
    req.on('data', chunk => { upstreamBytes += chunk.length; });
    req.on('end', () => {
      upstreamPhase = `${req.url} 收完本文`;
      res.writeHead(200, { 'Content-Length': responseBody.length, Connection: 'close' }).end(responseBody);
    });
    res.on('finish', () => { upstreamPhase = `${req.url} 回應已送出`; });
  });
  await new Promise<void>(resolve => upstream.listen(0, '127.0.0.1', resolve));
  const previous = process.env.VITE_DEV_API_TARGET;
  process.env.VITE_DEV_API_TARGET = `http://127.0.0.1:${(upstream.address() as AddressInfo).port}`;
  const vite = await createServer({
    logLevel: 'silent',
    // HTTP policy is static; unrelated repository test fixtures must not trigger HMR/restarts.
    server: { host: '127.0.0.1', port: 0, watch: null,
      proxy: { '/api': { configure: observeProxy }, '/webhook': { configure: observeProxy } } },
    optimizeDeps: { noDiscovery: true },
  });
  try {
    await vite.listen();
    const port = (vite.httpServer!.address() as AddressInfo).port;
    const send = (path: string, size: number, sendBody = true) => new Promise<number>((resolve, reject) => {
      let clientPhase = '等待回應標頭';
      const req = request({ host: '127.0.0.1', port, path, method: 'POST', agent: false, headers: { 'Content-Length': size } }, res => {
        clientPhase = `收到回應標頭 ${res.statusCode}`;
        res.on('error', reject);
        res.on('end', () => resolve(res.statusCode!));
        res.resume();
      });
      req.on('error', reject);
      req.setTimeout(requestTimeoutMs, () => req.destroy(new Error(
        `HTTP timeout: POST ${path}, declared bytes=${size}, upstream bytes=${upstreamBytes}, upstream=${upstreamPhase}, proxy=${proxyPhase}, client=${clientPhase}`,
      )));
      // A header-only probe still ends the client request. The size guard must
      // respond without waiting for any of the declared body.
      req.end(sendBody ? Buffer.alloc(size) : undefined);
    });
    for (const alias of ['/webhook', '/webhook/', '/webhook/line', '/webhook/line/']) {
      const before = upstreamCalls;
      const bytesBefore = upstreamBytes;
      expect(await send(alias, 1024 * 1024)).toBe(200);
      expect(upstreamCalls).toBe(before + 1);
      expect(upstreamBytes).toBe(bytesBefore + 1024 * 1024);
    }
    const before = upstreamCalls;
    const bytesBefore = upstreamBytes;
    expect(await send('/api/test', 1024 * 1024 + 1)).toBe(200);
    expect(upstreamCalls).toBe(before + 1);
    expect(upstreamBytes).toBe(bytesBefore + 1024 * 1024 + 1);
    // Run deliberately incomplete bodies after the forwarding checks.
    for (const alias of ['/webhook', '/webhook/', '/webhook/line', '/webhook/line/']) {
      expect(await send(`${alias}?test=1`, 1024 * 1024 + 1, false)).toBe(413);
      expect(upstreamCalls).toBe(before + 1);
      expect(upstreamBytes).toBe(bytesBefore + 1024 * 1024 + 1);
    }
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
