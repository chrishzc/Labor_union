import assert from 'node:assert/strict';
import { test } from 'node:test';
import router from '../../../../../../../deployment/windows-remote/path-router.mjs';

test('only the exact test segment with an Access assertion reaches the new origin', async () => {
  for (const url of ['https://chrishzc.com/', 'https://chrishzc.com/testing', 'https://elsewhere.invalid/test/']) {
    assert.equal((await router.fetch(new Request(url))).status, 404);
  }
  assert.equal((await router.fetch(new Request('https://chrishzc.com/test/'))).status, 401);
});

test('preserve uploads, session, query, typed conflict and binary response without unrelated cookies', async () => {
  const originalFetch = globalThis.fetch;
  try {
    let received;
    globalThis.fetch = async request => {
      received = request;
      assert.equal(await request.text(), 'synthetic-upload');
      return new Response(new Uint8Array([0, 255, 65]), { status: 409, headers: { 'Content-Type': 'application/pdf' } });
    };
    const response = await router.fetch(new Request('https://chrishzc.com/test/api/import?mode=preview', {
      method: 'POST', body: 'synthetic-upload', headers: {
        'Cf-Access-Jwt-Assertion': 'synthetic-assertion', Authorization: 'Bearer synthetic-session',
        Cookie: 'unrelated=private; CF_Authorization=synthetic-cookie', 'Idempotency-Key': 'synthetic-key',
      },
    }));
    assert.equal(received.url, 'https://lu-windows-origin.chrishzc.com/test/api/import?mode=preview');
    assert.equal(received.headers.get('Authorization'), 'Bearer synthetic-session');
    assert.equal(received.headers.get('Cookie'), 'CF_Authorization=synthetic-cookie');
    assert.equal(received.headers.get('Idempotency-Key'), 'synthetic-key');
    assert.equal(received.cache, 'no-store');
    assert.equal(response.status, 409);
    assert.deepEqual(new Uint8Array(await response.arrayBuffer()), new Uint8Array([0, 255, 65]));
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
