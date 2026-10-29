import { afterEach, describe, expect, it, vi } from 'vitest';
import { applicationFetch, applicationUrl } from '../../../../../../../api/shared/application_fetch';
import { transport } from '../../../../../../../api/shared/transport';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('remote public path', () => {
  it('keeps ordinary local URLs unchanged', () => {
    vi.stubEnv('VITE_PUBLIC_PATH_PREFIX', '');
    expect(applicationUrl('/api/v1/admin/auth/me')).toBe('/api/v1/admin/auth/me');
  });

  it('prefixes shared requests and direct binary downloads without changing auth or bodies', async () => {
    vi.stubEnv('VITE_PUBLIC_PATH_PREFIX', '/test');
    const fetch = vi.fn().mockImplementation(async () => new Response('{"ok":true}', {
      headers: { 'content-type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetch);
    await transport.post('/api/v1/admin/auth/login/challenges', { username: 'synthetic' });
    const body = new FormData();
    body.append('file', new Blob(['synthetic']), 'test.csv');
    await applicationFetch('/api/v1/registries/import?mode=preview', {
      method: 'POST', body, headers: { Authorization: 'Bearer synthetic' },
    });
    expect(fetch.mock.calls[0][0]).toBe('/test/api/v1/admin/auth/login/challenges');
    expect(fetch.mock.calls[1][0]).toBe('/test/api/v1/registries/import?mode=preview');
    expect(fetch.mock.calls[1][1].body).toBe(body);
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer synthetic');
  });

  it('leaves external, already prefixed and blob URLs alone', () => {
    vi.stubEnv('VITE_PUBLIC_PATH_PREFIX', '/test');
    for (const path of ['https://example.invalid/api/a', '//example.invalid/api/a',
      '/test/api/a', 'blob:synthetic', '#login']) {
      expect(applicationUrl(path)).toBe(path);
    }
  });
});
