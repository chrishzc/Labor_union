/**
 * File: test_windows_remote_router.mjs
 * Description: 驗證 Windows 遠端 path-router 的 Access 邊界、版本化純 JS／CSS 私有快取例外與負向阻擋。
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import router from '../../../../../../../deployment/windows-remote/path-router.mjs';

const VALID_PROOF = `v1;artifact=${'a'.repeat(64)};sha256=${'b'.repeat(64)}`;
const ACCESS_HEADERS = {
  'Cf-Access-Jwt-Assertion': 'synthetic-assertion',
  Cookie: 'unrelated=private; CF_Authorization=synthetic-cookie',
};

test('only the exact test segment with an Access assertion reaches the new origin', async () => {
  for (const url of ['https://chrishzc.com/', 'https://chrishzc.com/testing', 'https://elsewhere.invalid/test/']) {
    const notFound = await router.fetch(new Request(url));
    assert.equal(notFound.status, 404);
    assert.equal(notFound.headers.get('Cache-Control'), 'no-store');
  }
  const unauthorized = await router.fetch(new Request('https://chrishzc.com/test/'));
  assert.equal(unauthorized.status, 401);
  assert.equal(unauthorized.headers.get('Cache-Control'), 'no-store');
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

test('verified versioned JS and CSS assets receive browser-private immutable cache and strip internal proof', async () => {
  const originalFetch = globalThis.fetch;
  try {
    const cases = [
      {
        method: 'GET',
        path: '/test/assets/index-CsNYCnR6.js',
        contentType: 'text/javascript; charset=utf-8',
        body: 'export const ready = true;\n',
      },
      {
        method: 'HEAD',
        path: '/test/assets/vendor-react-Bx123456.js',
        contentType: 'application/javascript',
        body: '',
      },
      {
        method: 'GET',
        path: '/test/assets/index-Da987654.css',
        contentType: 'text/css; charset=utf-8',
        body: '#root{display:block}\n',
      },
    ];
    for (const item of cases) {
      let forwardedRequest;
      globalThis.fetch = async request => {
        forwardedRequest = request;
        return new Response(item.body, {
          status: 200,
          headers: {
            'Content-Type': item.contentType,
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
            Vary: 'Accept-Encoding',
          },
        });
      };
      const response = await router.fetch(new Request(`https://chrishzc.com${item.path}`, {
        method: item.method,
        headers: ACCESS_HEADERS,
      }));
      assert.equal(forwardedRequest.cache, 'no-store');
      assert.equal(response.status, 200);
      assert.equal(response.headers.get('Cache-Control'), 'private, max-age=31536000, immutable');
      assert.equal(response.headers.get('X-React-Admin-Asset-Eligibility'), null);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('non-assets, forged proofs, wrong MIME, cookies, redirects, APIs and errors remain no-store', async () => {
  const originalFetch = globalThis.fetch;
  try {
    const scenarios = [
      {
        name: 'HTML root entry',
        url: 'https://chrishzc.com/test/',
        upstream: { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } },
      },
      {
        name: 'artifact manifest',
        url: 'https://chrishzc.com/test/artifact-manifest.json',
        upstream: { status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } },
      },
      {
        name: 'client forged eligibility request header without origin proof',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        requestHeaders: { 'X-React-Admin-Asset-Eligibility': VALID_PROOF },
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
          },
        },
        checkForwarded(forwarded) {
          assert.equal(forwarded.headers.get('X-React-Admin-Asset-Eligibility'), null);
        },
      },
      {
        name: 'upstream public cache header alone without private/proof',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'public, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'long unversioned filename without hash segment',
        url: 'https://chrishzc.com/test/assets/plainlongfilename.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'hyphenated long unversioned filename lacking origin proof',
        url: 'https://chrishzc.com/test/assets/accounting-parameters.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'no-store',
          },
        },
      },
      {
        name: 'asset URL with query string',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js?v=1',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'API route disguised with hashed JS path and JS MIME',
        url: 'https://chrishzc.com/test/api/v1/assets/index-CsNYCnR6.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'SVG asset with hash-like filename',
        url: 'https://chrishzc.com/test/assets/logo-CsNYCnR6.svg',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'image/svg+xml',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'mismatched MIME on JS path',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'mismatched MIME on CSS path',
        url: 'https://chrishzc.com/test/assets/index-Da987654.css',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: 'Set-Cookie on asset response',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
            'Set-Cookie': 'session=unexpected; Secure; HttpOnly',
          },
        },
      },
      {
        name: 'Vary wildcard or Cookie on asset response',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
            Vary: 'Accept-Encoding, Cookie',
          },
        },
      },
      {
        name: 'POST method on versioned JS path',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        method: 'POST',
        upstream: {
          status: 200,
          headers: {
            'Content-Type': 'text/javascript',
            'Cache-Control': 'private, max-age=31536000, immutable',
            'X-React-Admin-Asset-Eligibility': VALID_PROOF,
          },
        },
      },
      {
        name: '304 Not Modified without complete body/MIME contract',
        url: 'https://chrishzc.com/test/assets/index-CsNYCnR6.js',
        upstream: {
          status: 304,
          headers: {
            'Cache-Control': 'private, max-age=31536000, immutable',
          },
        },
      },
      {
        name: '404 missing asset',
        url: 'https://chrishzc.com/test/assets/missing-CsNYCnR6.js',
        upstream: {
          status: 404,
          headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
        },
      },
      {
        name: '307 redirect rewrites origin hostname to public hostname and stays no-store',
        url: 'https://chrishzc.com/test',
        upstream: {
          status: 307,
          headers: { Location: 'https://lu-windows-origin.chrishzc.com/test/' },
        },
        checkResponse(response) {
          assert.equal(response.headers.get('Location'), 'https://chrishzc.com/test/');
        },
      },
    ];

    for (const scenario of scenarios) {
      let forwardedRequest;
      globalThis.fetch = async request => {
        forwardedRequest = request;
        return new Response(scenario.upstream.status === 304 ? null : 'synthetic', scenario.upstream);
      };
      const response = await router.fetch(new Request(scenario.url, {
        method: scenario.method || 'GET',
        headers: { ...ACCESS_HEADERS, ...(scenario.requestHeaders || {}) },
      }));
      if (scenario.checkForwarded) scenario.checkForwarded(forwardedRequest);
      if (scenario.checkResponse) scenario.checkResponse(response);
      assert.equal(response.headers.get('Cache-Control'), 'no-store', scenario.name);
      assert.equal(response.headers.get('X-React-Admin-Asset-Eligibility'), null, scenario.name);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }
});
