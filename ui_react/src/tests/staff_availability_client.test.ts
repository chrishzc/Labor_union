/**
 * File: staff_availability_client.test.ts
 * Description: 驗證 Availability client 的 strict decode、fresh token 與 header 契約。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  createStaffAvailabilityClient,
} from '../api/staff_availability/staff_availability_client';
import {
  StaffAvailabilityUnauthenticatedError,
  StaffAvailabilityValidationError,
} from '../api/staff_availability/staff_availability_errors';
import {
  STAFF_AVAILABILITY_APPLY_PAYLOAD,
  STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_PREVIEW_RESPONSE,
  STAFF_AVAILABILITY_QUERY_RESPONSE,
  STAFF_AVAILABILITY_RECEIPT_RESPONSE,
} from './fixtures/staff/staff_availability_contract_fixtures';

function response(body: object, ok = true, status = 200) {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => body,
  };
}

describe('staff availability client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    sessionClient.setSession('availability-token-1', {
      id: 7,
      username: 'availability-reader',
      display_name: 'Availability Reader',
      role: 'admin',
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('sends a query GET with exact range and correlation headers', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(STAFF_AVAILABILITY_QUERY_RESPONSE));
    const blocks = await createStaffAvailabilityClient().getBlocks(7, '2026-09-01', '2026-10-31', {
      correlationId: 'availability-query-test',
    });

    expect(blocks).toEqual(STAFF_AVAILABILITY_QUERY_RESPONSE.data);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/scheduling/staff/7/availability-blocks?range_start=2026-09-01&range_end=2026-10-31');
    expect(options?.method).toBe('GET');
    expect(options?.headers).toMatchObject({
      Authorization: 'Bearer availability-token-1',
      'X-Correlation-ID': 'availability-query-test',
    });
  });

  it('uses preview POST and apply POST with correlation and idempotency headers', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_AVAILABILITY_PREVIEW_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_AVAILABILITY_RECEIPT_RESPONSE));
    const client = createStaffAvailabilityClient();
    await client.previewChange(7, {
      action: 'create_pause',
      reason: '去敏暫停接案',
      start_date: '2026-10-01',
    }, { correlationId: 'availability-preview-test' });
    await client.applyChange(7, STAFF_AVAILABILITY_APPLY_PAYLOAD, {
      correlationId: 'availability-apply-test',
      idempotencyKey: 'availability-apply-7-01',
    });

    const previewCall = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(previewCall[0]).toBe('/api/v1/scheduling/staff/7/availability-blocks/preview');
    expect(previewCall[1]?.method).toBe('POST');
    expect(previewCall[1]?.headers).toMatchObject({ 'X-Correlation-ID': 'availability-preview-test' });
    const applyCall = vi.mocked(globalThis.fetch).mock.calls[1];
    expect(applyCall[0]).toBe('/api/v1/scheduling/staff/7/availability-blocks/apply');
    expect(applyCall[1]?.headers).toMatchObject({
      'X-Correlation-ID': 'availability-apply-test',
      'Idempotency-Key': 'availability-apply-7-01',
    });
  });

  it('reads the rotated memory token on every request and never accepts caller Authorization', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(STAFF_AVAILABILITY_QUERY_RESPONSE))
      .mockResolvedValueOnce(response(STAFF_AVAILABILITY_QUERY_RESPONSE));
    const client = createStaffAvailabilityClient();
    await client.getBlocks(7, '2026-09-01', '2026-09-30', {
      headers: { Authorization: 'Bearer injected', 'X-Correlation-ID': 'injected' },
    });
    sessionClient.setSession('availability-token-2', {
      id: 8,
      username: 'rotated',
      display_name: 'Rotated',
      role: 'admin',
    });
    await client.getBlocks(7, '2026-09-01', '2026-09-30');

    expect(vi.mocked(globalThis.fetch).mock.calls[0][1]?.headers).toMatchObject({
      Authorization: 'Bearer availability-token-1',
    });
    expect(vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers).toMatchObject({
      Authorization: 'Bearer availability-token-2',
    });
  });

  it('fails closed before fetch without a memory session', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();

    await expect(
      createStaffAvailabilityClient().getBlocks(7, '2026-09-01', '2026-09-30')
    ).rejects.toBeInstanceOf(StaffAvailabilityUnauthenticatedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('rejects strict response drift and invalid fingerprint before fetch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...STAFF_AVAILABILITY_QUERY_RESPONSE,
      data: [{ ...STAFF_AVAILABILITY_QUERY_RESPONSE.data[0], extra: true }],
    }));
    await expect(
      createStaffAvailabilityClient().getBlocks(7, '2026-09-01', '2026-09-30')
    ).rejects.toBeInstanceOf(StaffAvailabilityValidationError);

    globalThis.fetch = vi.fn();
    await expect(
      createStaffAvailabilityClient().applyChange(7, {
        ...STAFF_AVAILABILITY_APPLY_PAYLOAD,
        preview_fingerprint: 'A'.repeat(64),
      }, { idempotencyKey: 'availability-invalid' })
    ).rejects.toBeInstanceOf(StaffAvailabilityValidationError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('binds query blocks, preview targets and apply receipts to the requested staff identity', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response({
        ...STAFF_AVAILABILITY_QUERY_RESPONSE,
        data: [{ ...STAFF_AVAILABILITY_QUERY_RESPONSE.data[0], staff_id: 8 }],
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_AVAILABILITY_PREVIEW_RESPONSE,
        data: { ...STAFF_AVAILABILITY_PREVIEW_RESPONSE.data, staff_id: 8 },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE,
        data: {
          ...STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE.data,
          staff_id: 7,
          target_block: {
            ...STAFF_AVAILABILITY_END_PAUSE_PREVIEW_RESPONSE.data.target_block,
            staff_id: 8,
          },
        },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_AVAILABILITY_RECEIPT_RESPONSE,
        data: { ...STAFF_AVAILABILITY_RECEIPT_RESPONSE.data, staff_id: 8 },
      }))
      .mockResolvedValueOnce(response({
        ...STAFF_AVAILABILITY_RECEIPT_RESPONSE,
        data: {
          ...STAFF_AVAILABILITY_RECEIPT_RESPONSE.data,
          block: { ...STAFF_AVAILABILITY_RECEIPT_RESPONSE.data.block, staff_id: 8 },
        },
      }));
    const client = createStaffAvailabilityClient();

    await expect(client.getBlocks(7, '2026-09-01', '2026-09-30')).rejects.toBeInstanceOf(StaffAvailabilityValidationError);
    await expect(client.previewChange(7, {
      action: 'create_pause',
      reason: 'identity 驗證',
      start_date: '2026-10-01',
    })).rejects.toBeInstanceOf(StaffAvailabilityValidationError);
    await expect(client.previewChange(7, {
      action: 'end_pause',
      block_id: 92,
      resume_date: '2026-10-15',
      reason: 'identity 驗證',
    })).rejects.toBeInstanceOf(StaffAvailabilityValidationError);
    await expect(client.applyChange(7, STAFF_AVAILABILITY_APPLY_PAYLOAD, {
      idempotencyKey: 'availability-identity-top-level-01',
    })).rejects.toBeInstanceOf(StaffAvailabilityValidationError);
    await expect(client.applyChange(7, STAFF_AVAILABILITY_APPLY_PAYLOAD, {
      idempotencyKey: 'availability-identity-01',
    })).rejects.toBeInstanceOf(StaffAvailabilityValidationError);
  });
});
