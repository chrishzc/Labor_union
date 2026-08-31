/**
 * File: order_cancellation_client.test.ts
 * Description: 驗證訂單取消 Query／Preview／Apply 的路徑、typed decode 與識別防漂移。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { orderCancellationClient } from '../api/orders/order_cancellation_client';
import { transport } from '../api/shared/transport';

const queryFixture = {
  case_no: 'CASE-1',
  lifecycle_status: '訂單成立',
  actual_start_date: null,
  contracted_service_days: 25,
  service_hours_per_day: 8,
  service_started: false,
  service_data_locked: false,
  order_version: 0,
  scheduling_version: 0,
  scheduling_generation: 0,
  client_finance_version: 0,
  payroll_version: 0,
  confirmed_service_days: [],
  caregiver_options: [],
};

const previewFixture = {
  cancellation_date: '2026-08-23',
  actual_end_date: null,
  confirmed_service_days: [],
  official_service_day_count: 0,
  official_service_hours: 0,
  order_version: 0,
  scheduling_version: 0,
  scheduling_generation: 0,
  client_finance_version: 0,
  payroll_version: 0,
  scheduling: {
    case_no: 'CASE-1', generation_number: 1, expected_aggregate_version: 0,
    resulting_aggregate_version: 1, cancelled_assignment_ids: [], assignments: [], buffers: [],
  },
  client_finance_impact: {
    case_no: 'CASE-1', expected_account_version: 0, resulting_account_version: 1,
    stage_plans: [], actions: [{
      action: 'create_refund', payment_stage: 'first',
      obligation_identity: 'client-obligation:CASE-1:first',
      before_amount: { amount: 10000 }, after_amount: { amount: 8000 },
      obligation_amount: { amount: 2000 }, before_due_date: '2026-08-01',
      after_due_date: '2026-08-02', source_obligation_identity: null,
      direction: 'refund_due', direction_amount_ntd: 2000,
    }], settlement: { deposit_settled: false, all_formal_obligations_settled: false, fingerprint: 'b'.repeat(64) }, blockers: [], fingerprint: 'c'.repeat(64),
  },
  payroll_impact: {
    case_no: 'CASE-1', expected_payroll_version: 0, resulting_payroll_version: 1,
    payroll: { assignments: [], earned_floor_fee: { amount: 0 }, total_payable: { amount: 0 }, fingerprint: 'd'.repeat(64) },
    carried_rate_snapshots: [], actions: [], special_pay_events: [{
      assignment_identity: 'CASE-1:g2:a1', assignment_sequence: 1,
      service_dates: ['2026-08-08'],
    }], blockers: [], fingerprint: 'e'.repeat(64),
  },
  lifecycle_impact: {
    case_no: 'CASE-1', before_status: '訂單成立', after_status: '訂單取消', actual_end_date: null,
    cancellation_effective: true, fingerprint: 'f'.repeat(64),
  },
  preview_fingerprint: 'a'.repeat(64),
};

const receiptFixture = {
  case_no: 'CASE-1',
  order_version: 1,
  scheduling_version: 1,
  scheduling_generation: 1,
  client_finance_version: 1,
  payroll_version: 1,
  lifecycle_status: '訂單取消',
  actual_end_date: null,
  official_service_day_count: 0,
  official_service_hours: 0,
  cancelled_assignment_ids: [],
  created_assignment_keys: [],
  preview_fingerprint: 'a'.repeat(64),
};

describe('orderCancellationClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('token');
  });

  it('queries and strictly decodes cancellation root facts', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue({
      success: true, message: 'ok', data: queryFixture, error: null,
    });
    await expect(orderCancellationClient.query('CASE-1')).resolves.toEqual(queryFixture);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/cancellation',
      expect.objectContaining({ token: 'token' }),
    );
  });

  it('previews with confirmed days and a correlation identity', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true, message: 'ok', data: previewFixture, error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).resolves.toEqual(previewFixture);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/cancellation/preview',
      { confirmed_service_days: [] },
      expect.objectContaining({
        token: 'token',
        headers: expect.objectContaining({ 'X-Correlation-ID': expect.stringContaining('orders-cancellation-preview-CASE-1-') }),
      }),
    );
  });

  it('gets and strictly decodes a cancellation receipt with the same idempotency key', async () => {
    const get = vi.spyOn(transport, 'get').mockResolvedValue({
      success: true, message: 'ok', data: receiptFixture, error: null,
    });
    const signal = new AbortController().signal;
    await expect(orderCancellationClient.receipt('CASE-1', ' cancel-case-1 ', signal))
      .resolves.toEqual(receiptFixture);
    expect(get).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/cancellation/receipt',
      expect.objectContaining({
        token: 'token',
        signal,
        headers: { 'Idempotency-Key': 'cancel-case-1' },
      }),
    );
  });

  it('rejects receipt identity drift and extra fields', async () => {
    vi.spyOn(transport, 'get').mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...receiptFixture, case_no: 'CASE-2' }, error: null,
    });
    await expect(orderCancellationClient.receipt('CASE-1', 'cancel-case-1'))
      .rejects.toThrow('案件識別不一致');

    vi.spyOn(transport, 'get').mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...receiptFixture, leaked: true }, error: null,
    });
    await expect(orderCancellationClient.receipt('CASE-1', 'cancel-case-1')).rejects.toThrow();
  });

  it('applies with fresh versions, explicit reason, idempotency and correlation identities', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true, message: 'ok', data: receiptFixture, error: null,
    });
    const payload = {
      confirmed_service_days: [],
      expected_order_version: 0,
      expected_scheduling_version: 0,
      expected_client_finance_version: 0,
      expected_payroll_version: 0,
      preview_fingerprint: 'a'.repeat(64),
      reason: '客戶電話確認取消',
    };
    await expect(orderCancellationClient.apply('CASE-1', payload, { idempotencyKey: 'cancel-case-1' }))
      .resolves.toEqual(receiptFixture);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/cancellation/apply',
      payload,
      expect.objectContaining({
        token: 'token',
        headers: expect.objectContaining({
          'Idempotency-Key': 'cancel-case-1',
          'X-Correlation-ID': expect.stringContaining('orders-cancellation-apply-CASE-1-'),
        }),
      }),
    );
  });

  it('rejects query identity drift and extra preview fields', async () => {
    vi.spyOn(transport, 'get').mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...queryFixture, case_no: 'CASE-2' }, error: null,
    });
    await expect(orderCancellationClient.query('CASE-1')).rejects.toThrow('案件識別不一致');

    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true, message: 'ok', data: { ...previewFixture, leaked: true }, error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });

  it('rejects unknown owner-impact fields instead of passing untyped payloads through', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true,
      message: 'ok',
      data: { ...previewFixture, client_finance_impact: { ...previewFixture.client_finance_impact, unexpected_owner_fact: true } },
      error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });

  it('rejects a Client Finance action without the server-owned direction', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true,
      message: 'ok',
      data: {
        ...previewFixture,
        client_finance_impact: {
          ...previewFixture.client_finance_impact,
          actions: [{
            ...previewFixture.client_finance_impact.actions[0],
            direction: undefined,
          }],
        },
      },
      error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });

  it('rejects a financial direction with zero amount', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true,
      message: 'ok',
      data: {
        ...previewFixture,
        client_finance_impact: {
          ...previewFixture.client_finance_impact,
          actions: [{
            ...previewFixture.client_finance_impact.actions[0],
            direction_amount_ntd: 0,
          }],
        },
      },
      error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });

  it('rejects no-finance-change with a nonzero amount', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true,
      message: 'ok',
      data: {
        ...previewFixture,
        client_finance_impact: {
          ...previewFixture.client_finance_impact,
          actions: [{
            ...previewFixture.client_finance_impact.actions[0],
            direction: 'no_finance_change',
            direction_amount_ntd: 1,
          }],
        },
      },
      error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });
});
