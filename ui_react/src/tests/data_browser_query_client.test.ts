/**
 * File: data_browser_query_client.test.ts
 * Description: 驗證 Data Browser client 的 GET、strict decode 與 auth。
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
});
