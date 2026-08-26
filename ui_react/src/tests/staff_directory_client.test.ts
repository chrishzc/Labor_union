/**
 * File: staff_directory_client.test.ts
 * Description: 驗證 Staff 摘要 client 的 strict decode、最新 Session、cursor 與唯讀 GET 邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createStaffDirectoryClient,
  loadAllStaffDirectoryPages,
} from '../api/staff_directory/staff_directory_client';
import {
  StaffDirectoryUnauthenticatedError,
  StaffDirectoryAbortedError,
  StaffDirectoryValidationError,
} from '../api/staff_directory/staff_directory_errors';
import {
  STAFF_EMPTY_RESPONSE,
  STAFF_RESPONSE_DUPLICATE_IDS,
  STAFF_RESPONSE_EXTRA_FIELD,
  STAFF_RESPONSE_ONE,
  STAFF_RESPONSE_TWO,
} from './fixtures/staff/staff_directory_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('staff directory client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('staff-token-1', {
      id: 7,
      username: 'staff-reader',
      display_name: 'Staff Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('sends one GET with current memory token and strict cursor params', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_RESPONSE_ONE));
    const client = createStaffDirectoryClient();

    const page = await client.queryPage({ pageSize: 200 });

    expect(page).toEqual(STAFF_RESPONSE_ONE.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/staff/summaries?page_size=200');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({ Authorization: 'Bearer staff-token-1' });
  });

  it('reads the rotated token for every request and rejects caller Authorization', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();
    await client.queryPage({}, { headers: { Authorization: 'Bearer injected' } });
    sessionClient.setSession('staff-token-2', {
      id: 8,
      username: 'rotated',
      display_name: 'Rotated',
      role: 'admin',
    });
    await client.queryPage({ afterId: 12 });

    expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject({
      Authorization: 'Bearer staff-token-2',
    });
  });

  it('fails before fetch without a memory session', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();

    await expect(createStaffDirectoryClient().queryPage()).rejects.toBeInstanceOf(
      StaffDirectoryUnauthenticatedError
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('strictly rejects extra fields and duplicate identities', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_EXTRA_FIELD))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_DUPLICATE_IDS));
    const client = createStaffDirectoryClient();

    await expect(client.queryPage()).rejects.toBeInstanceOf(StaffDirectoryValidationError);
    await expect(client.queryPage()).rejects.toBeInstanceOf(StaffDirectoryValidationError);
  });

  it('rejects non-forward and repeated cursors without auto retry', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response({
        ...STAFF_RESPONSE_TWO,
        data: { items: STAFF_RESPONSE_TWO.data.items, next_cursor: 12 },
      }));
    const client = createStaffDirectoryClient();
    await client.queryPage();

    await expect(client.queryPage({ afterId: 12 })).rejects.toBeInstanceOf(
      StaffDirectoryValidationError
    );
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('allows an operator retry after a failed next-page request', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockRejectedValueOnce(new TypeError('temporary network failure'))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();
    await client.queryPage();

    await expect(client.queryPage({ afterId: 12 })).rejects.toBeTruthy();
    await expect(client.queryPage({ afterId: 12 })).resolves.toEqual(STAFF_RESPONSE_TWO.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
  });

  it('loads every staff page for operator selectors', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_RESPONSE_ONE))
      .mockResolvedValueOnce(response(STAFF_RESPONSE_TWO));
    const client = createStaffDirectoryClient();

    const page = await loadAllStaffDirectoryPages(client.queryPage.bind(client), { pageSize: 200 });

    expect(page.items).toEqual([...STAFF_RESPONSE_ONE.data.items, ...STAFF_RESPONSE_TWO.data.items]);
    expect(page.next_cursor).toBeNull();
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it('validates bounds and supports an empty page', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_EMPTY_RESPONSE));
    const client = createStaffDirectoryClient();

    await expect(client.queryPage({ pageSize: 0 })).rejects.toBeInstanceOf(
      StaffDirectoryValidationError
    );
    await expect(client.queryPage({ afterId: 1, staffId: 2 })).rejects.toBeInstanceOf(
      StaffDirectoryValidationError
    );
    await expect(client.queryPage()).resolves.toEqual(STAFF_EMPTY_RESPONSE.data);
  });

  it('maps an already-aborted signal without issuing fetch', async () => {
    const controller = new AbortController();
    controller.abort();
    globalThis.fetch = vi.fn();

    await expect(
      createStaffDirectoryClient().queryPage({}, { signal: controller.signal })
    ).rejects.toBeInstanceOf(StaffDirectoryAbortedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
