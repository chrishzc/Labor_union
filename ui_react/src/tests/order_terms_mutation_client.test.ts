/**
 * File: order_terms_mutation_client.test.ts
 * Description: 驗證 Orders Terms Query／Preview／Apply 的 strict decode、payload 與 command headers。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { orderTermsMutationClient } from '../api/orders/order_terms_mutation_client';
import { transport } from '../api/shared/transport';

const terms = {
  planned_start_date: '2026-08-10',
  service_days: 5,
  service_hours_per_day: 8,
  requires_cooking: false,
  floor_fee_ntd: 0,
  service_time: {
    start_time: '09:00:00',
    end_time: '17:00:00',
    end_day_offset: 0,
  },
};

const query = {
  case_no: 'CASE-1',
  order_version: 2,
  scheduling_version: 3,
  scheduling_generation: 1,
  client_finance_version: 4,
  payroll_version: 5,
  service_data_locked: false,
  terms,
};

const preview = {
  before: terms,
  after: { ...terms, requires_cooking: true },
  order_version: 2,
  scheduling_version: 3,
  scheduling_generation: 1,
  client_finance_version: 4,
  payroll_version: 5,
  scheduling: {},
  client_finance_impact: {},
  payroll_impact: {},
  lifecycle_impact: {},
  preview_fingerprint: 'a'.repeat(64),
};

const receipt = {
  case_no: 'CASE-1',
  order_version: 3,
  scheduling_version: 4,
  scheduling_generation: 2,
  client_finance_version: 5,
  payroll_version: 6,
  lifecycle_status: '訂單成立',
  service_data_lock_formed: false,
  cancelled_assignment_ids: [7],
  created_assignment_keys: ['assignment-8'],
  official_service_day_count: 5,
  official_service_hours: 40,
  preview_fingerprint: 'a'.repeat(64),
};

const proposed = { proposed_terms: preview.after };
const applyPayload = {
  ...proposed,
  expected_order_version: 2,
  expected_scheduling_version: 3,
  expected_client_finance_version: 4,
  expected_payroll_version: 5,
  preview_fingerprint: 'a'.repeat(64),
  reason: '補登明確料理需求',
};

describe('orderTermsMutationClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('token');
  });

  it('queries and rejects extra response fields', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValueOnce({
      success: true, message: 'ok', data: query, error: null,
    });
    await expect(orderTermsMutationClient.query(' CASE-1 ')).resolves.toEqual(query);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/terms',
      expect.objectContaining({ token: 'token' }),
    );

    get.mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...query, leaked: true }, error: null,
    });
    await expect(orderTermsMutationClient.query('CASE-1')).rejects.toThrow();
  });

  it('previews a closed payload with an explicit correlation identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true, message: 'ok', data: preview, error: null,
    });
    await expect(orderTermsMutationClient.preview(
      'CASE-1',
      proposed,
      { correlationId: 'terms-preview-1' },
    )).resolves.toEqual(preview);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/terms/preview',
      proposed,
      expect.objectContaining({
        token: 'token',
        headers: { 'X-Correlation-ID': 'terms-preview-1' },
      }),
    );

    await expect(orderTermsMutationClient.preview('CASE-1', {
      ...proposed,
      leaked: true,
    } as never)).rejects.toThrow();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('applies fresh versions with stable command headers and strict receipt decode', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true, message: 'ok', data: receipt, error: null,
    });
    await expect(orderTermsMutationClient.apply('CASE-1', applyPayload, {
      idempotencyKey: 'terms-command-1',
      correlationId: 'terms-apply-1',
    })).resolves.toEqual(receipt);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/terms/apply',
      applyPayload,
      expect.objectContaining({
        token: 'token',
        headers: {
          'X-Correlation-ID': 'terms-apply-1',
          'Idempotency-Key': 'terms-command-1',
        },
      }),
    );

    post.mockResolvedValueOnce({
      success: true,
      message: 'ok',
      data: { ...receipt, case_no: 'CASE-2' },
      error: null,
    });
    await expect(orderTermsMutationClient.apply('CASE-1', applyPayload, {
      idempotencyKey: 'terms-command-2',
    })).rejects.toThrow('收據案件識別不一致');
  });
});
