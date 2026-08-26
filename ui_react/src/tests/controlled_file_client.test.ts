/**
 * File: controlled_file_client.test.ts
 * Description: 驗證 controlled-file React client 的 strict decode、closed pairing與 bounded download錯誤契約。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  downloadControlledFile,
  listControlledFiles,
  type ControlledFileView,
} from '../api/storage/controlled_file_client';
import { ADMIN_SESSION_UNAUTHORIZED_EVENT } from '../api/shared/transport';
import { ApiHttpError, ApiTimeoutError } from '../api/shared/typed_errors';

const FILE: ControlledFileView = {
  file_id: 'cf_0123456789abcdef0123456789abcdef',
  owner: 'orders',
  purpose: 'order_notice',
  subject_reference: 'ORDER-1',
  filename: 'notice.pdf',
  logical_folder: 'orders/ORDER-1/contracts',
  version: 1,
  mime_type: 'application/pdf',
  size_bytes: 3,
  status: 'registered',
  applied_at: '2026-08-26T08:00:00Z',
};

function envelope(data: unknown): unknown {
  return { success: true, message: 'Success', data, error: null };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('controlled-file client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('storage-test-token', {
      id: 1,
      username: 'storage-admin',
      display_name: 'Storage Admin',
      role: 'system_admin',
      capabilities: ['system.administration'],
      is_root: true,
      access_control_version: 1,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('strictly decodes a canonical list response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(envelope({ items: [FILE] })));

    await expect(listControlledFiles()).resolves.toEqual([FILE]);
  });

  it.each([
    ['nested locator', envelope({ items: [{ ...FILE, storage_locator: 'C:/secret/file' }] })],
    ['top-level locator', { ...envelope({ items: [FILE] }) as object, public_url: 'https://public.test/file' }],
    ['invalid timezone', envelope({ items: [{ ...FILE, applied_at: '2026-08-26 08:00:00' }] })],
    ['invalid owner purpose pairing', envelope({ items: [{ ...FILE, owner: 'staff', purpose: 'order_notice' }] })],
  ])('rejects %s instead of leaking untyped data', async (_label, payload) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload));

    await expect(listControlledFiles()).rejects.toThrow();
  });

  it('preserves typed Global download errors', async () => {
    const payload = {
      detail: {
        error: {
          category: 'unavailable',
          code: 'controlled_file_mount_unavailable',
          message: '檔案庫目前無法使用',
          field_errors: [],
          domain_blockers: [],
          retryable: true,
          correlation_id: 'storage-test',
          current_version: null,
        },
      },
    };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload, 503));

    const failure = downloadControlledFile(FILE).catch((error: unknown) => error);
    await expect(failure).resolves.toMatchObject({
      name: 'ApiHttpError',
      code: 'controlled_file_mount_unavailable',
      retryable: true,
    });
  });

  it('dispatches the shared unauthorized event for an authenticated download', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}, 401));
    const listener = vi.fn();
    window.addEventListener(ADMIN_SESSION_UNAUTHORIZED_EVENT, listener);

    await expect(downloadControlledFile(FILE)).rejects.toBeInstanceOf(ApiHttpError);

    window.removeEventListener(ADMIN_SESSION_UNAUTHORIZED_EVENT, listener);
    expect(listener).toHaveBeenCalledTimes(1);
    const unauthorizedEvent = listener.mock.calls[0]?.[0];
    expect(unauthorizedEvent).toBeInstanceOf(CustomEvent);
    expect((unauthorizedEvent as CustomEvent).detail).toEqual({ rejectedToken: 'storage-test-token' });
  });

  it('aborts a download at its bounded timeout', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockImplementation((_input, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));

    const failure = downloadControlledFile(FILE, 25);
    const assertion = expect(failure).rejects.toBeInstanceOf(ApiTimeoutError);
    await vi.advanceTimersByTimeAsync(25);

    await assertion;
  });
});
