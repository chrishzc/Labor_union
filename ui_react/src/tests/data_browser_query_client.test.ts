/**
 * File: data_browser_query_client.test.ts
 * Description: 驗證 Data Browser client 的 GET、exact-key coalescing、strict decode 與 auth。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { queryDataBrowserSource } from '../api/data_browser/data_browser_query_client';
import { DataBrowserQueryError } from '../api/data_browser/data_browser_query_errors';
import { VALID_DATA_BROWSER_ENVELOPE } from './fixtures/data_browser/data_browser_query_contract_fixtures';

describe('Data Browser query client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('data-browser-test-token', {
      id: 1,
      username: 'root',
      display_name: 'Root',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('sends one bounded GET with current bearer and decodes strict page', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => VALID_DATA_BROWSER_ENVELOPE,
    });
    const page = await queryDataBrowserSource({
      sourceId: 'orders', limit: 25, after: '115000000', query: '服務中',
    });
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toContain('/api/v1/admin/data-browser/sources/orders');
    expect(url).toContain('after=115000000');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({ Authorization: 'Bearer data-browser-test-token' });
    expect(page.items[0].row_identity).toBe('115000001');
  });

  it('rejects extra raw rows and missing session before fetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => ({ ...VALID_DATA_BROWSER_ENVELOPE, raw_rows: [] }),
    });
    await expect(queryDataBrowserSource({ sourceId: 'orders' })).rejects.toBeInstanceOf(DataBrowserQueryError);
    sessionClient.clearSession();
    await expect(queryDataBrowserSource({ sourceId: 'orders' })).rejects.toMatchObject({ code: 'unauthenticated' });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  it('coalesces only the same no-signal in-flight GET', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => VALID_DATA_BROWSER_ENVELOPE,
    });

    await Promise.all([
      queryDataBrowserSource({ sourceId: 'orders', limit: 25 }),
      queryDataBrowserSource({ limit: 25, sourceId: 'orders' }),
    ]);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    await Promise.all([
      queryDataBrowserSource({ sourceId: 'orders', limit: 25, query: 'A' }),
      queryDataBrowserSource({ sourceId: 'orders', limit: 25, query: 'B' }),
    ]);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('does not coalesce caller-owned AbortSignal requests', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => VALID_DATA_BROWSER_ENVELOPE,
    });
    const first = new AbortController();
    const second = new AbortController();
    await Promise.all([
      queryDataBrowserSource({ sourceId: 'orders' }, { signal: first.signal }),
      queryDataBrowserSource({ sourceId: 'orders' }, { signal: second.signal }),
    ]);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('maps malformed runtime source and cursor inputs to typed invalid errors before fetch', async () => {
    globalThis.fetch = vi.fn();

    const invalidSource = Reflect.apply(queryDataBrowserSource, undefined, [{ sourceId: 'unknown' }]);
    await expect(invalidSource).rejects.toMatchObject({ code: 'invalid', status: 422 });

    const invalidCursor = Reflect.apply(queryDataBrowserSource, undefined, [{
      sourceId: 'orders',
      after: 123,
    }]);
    await expect(invalidCursor).rejects.toMatchObject({ code: 'invalid', status: 422 });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
