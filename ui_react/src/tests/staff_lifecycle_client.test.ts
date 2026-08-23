/**
 * File: staff_lifecycle_client.test.ts
 * Description: 驗證 lifecycle client 的 strict decode、action allowlist 與 header 契約。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { createStaffLifecycleClient } from '../api/staff_lifecycle/staff_lifecycle_client';
import {
  StaffLifecycleUnauthenticatedError,
  StaffLifecycleValidationError,
} from '../api/staff_lifecycle/staff_lifecycle_errors';
import {
  STAFF_LIFECYCLE_APPLY_PAYLOAD,
  STAFF_LIFECYCLE_PREVIEW_RESPONSE,
  STAFF_LIFECYCLE_QUERY_RESPONSE,
  STAFF_LIFECYCLE_RECEIPT_RESPONSE,
  STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
} from './fixtures/staff/staff_lifecycle_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('staff lifecycle client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('lifecycle-token-1', {
      id: 7,
      username: 'lifecycle-reader',
      display_name: 'Lifecycle Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('queries server lifecycle state with a request-scoped correlation header', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_LIFECYCLE_QUERY_RESPONSE));
    const view = await createStaffLifecycleClient().query(7, {
      correlationId: 'lifecycle-query-test',
    });

    expect(view).toEqual(STAFF_LIFECYCLE_QUERY_RESPONSE.data);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/staff/7/lifecycle');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({
      Authorization: 'Bearer lifecycle-token-1',
      'X-Correlation-ID': 'lifecycle-query-test',
    });
  });

  it('uses only retirement/reactivation action paths and exact apply headers', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_LIFECYCLE_PREVIEW_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_LIFECYCLE_RECEIPT_RESPONSE));
    const client = createStaffLifecycleClient();
    await client.preview(7, 'retirement', STAFF_LIFECYCLE_PREVIEW_PAYLOAD, {
      correlationId: 'lifecycle-preview-test',
    });
    await client.apply(7, 'retirement', STAFF_LIFECYCLE_APPLY_PAYLOAD, {
      correlationId: 'lifecycle-apply-test',
      idempotencyKey: 'lifecycle-apply-7-01',
    });

    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe('/api/v1/staff/7/retirement/preview');
    expect(vi.mocked(globalThis.fetch).mock.calls[1][0]).toBe('/api/v1/staff/7/retirement/apply');
    expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject({
      'X-Correlation-ID': 'lifecycle-apply-test',
      'Idempotency-Key': 'lifecycle-apply-7-01',
    });
  });

  it('rejects invalid action, naive datetime, uppercase fingerprint and absent session before fetch', async () => {
    globalThis.fetch = vi.fn();
    const invalidActionClient = createStaffLifecycleClient();
    await expect(
      Promise.resolve().then(() => Reflect.apply(invalidActionClient.preview, invalidActionClient, [
        7,
        'promote',
        STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
      ]))
    ).rejects.toBeInstanceOf(StaffLifecycleValidationError);
    await expect(
      createStaffLifecycleClient().preview(7, 'retirement', {
        ...STAFF_LIFECYCLE_PREVIEW_PAYLOAD,
        effective_at: '2026-08-15T09:00:00',
      })
    ).rejects.toBeInstanceOf(StaffLifecycleValidationError);
    await expect(
      createStaffLifecycleClient().apply(7, 'retirement', {
        ...STAFF_LIFECYCLE_APPLY_PAYLOAD,
        preview_fingerprint: 'A'.repeat(64),
      }, { idempotencyKey: 'invalid-fingerprint' })
    ).rejects.toBeInstanceOf(StaffLifecycleValidationError);
    sessionClient.clearSession();
    await expect(createStaffLifecycleClient().query(7)).rejects.toBeInstanceOf(StaffLifecycleUnauthenticatedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('rejects strict response drift', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...STAFF_LIFECYCLE_QUERY_RESPONSE,
      data: { ...STAFF_LIFECYCLE_QUERY_RESPONSE.data, unexpected: true },
    }));
    await expect(createStaffLifecycleClient().query(7)).rejects.toBeInstanceOf(StaffLifecycleValidationError);
  });

  it('binds query, preview and apply receipts to the requested staff identity', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response({
        ...STAFF_LIFECYCLE_QUERY_RESPONSE,
        data: { ...STAFF_LIFECYCLE_QUERY_RESPONSE.data, staff_id: 8 },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_LIFECYCLE_PREVIEW_RESPONSE,
        data: { ...STAFF_LIFECYCLE_PREVIEW_RESPONSE.data, staff_id: 8 },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_LIFECYCLE_RECEIPT_RESPONSE,
        data: { ...STAFF_LIFECYCLE_RECEIPT_RESPONSE.data, staff_id: 8 },
      }));
    const client = createStaffLifecycleClient();

    await expect(client.query(7)).rejects.toBeInstanceOf(StaffLifecycleValidationError);
    await expect(client.preview(7, 'retirement', STAFF_LIFECYCLE_PREVIEW_PAYLOAD)).rejects.toBeInstanceOf(StaffLifecycleValidationError);
    await expect(client.apply(7, 'retirement', STAFF_LIFECYCLE_APPLY_PAYLOAD, {
      idempotencyKey: 'lifecycle-identity-01',
    })).rejects.toBeInstanceOf(StaffLifecycleValidationError);
  });
});
