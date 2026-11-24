/**
 * File: order_cancellation_client.test.ts
 * Description: 驗證訂單取消 Query／Preview／Apply 的路徑、typed decode 與識別防漂移。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { OrderCancellationPreviewSchema, OrderCancellationQuerySchema, OrderCancellationReceiptSchema, OrderCancellationApplyPayloadSchema, orderCancellationClient } from '../api/orders/order_cancellation_client';
import type { HistoricalUnservedCorrection } from '../api/orders/order_cancellation_client';
import { transport } from '../api/shared/transport';

const queryFixture = {
  case_no: 'CASE-1',
  lifecycle_status: '訂單成立',
  actual_start_date: null,
  contracted_service_days: 25,
  service_hours_per_day: 8,
  service_started: false,
  historical_mid_service_confirmation_available: false,
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
  actual_start_date: null,
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
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-a' } as never);
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

  it('decodes historical review codes separately from blockers with no establishment records', async () => {
    const correction = {
      blockers: [], review_codes: ['historical_unserved_establishment_evidence_missing', 'historical_unserved_cash_evidence_requires_review'],
      establishment_lifecycle_event_ids: [], establishment_adoption_receipt_ids: [],
      establishment_owner_status: null, historical_adoption_receipt_ids: [], historical_absence_event_ids: [],
      actual_service_evidence: [], actual_start_date: null, actual_end_date: null, prior_fee_ntd: '0',
      prior_fee_reason: '', net_cash_received_ntd: null, prior_cancellation_event_id: null,
      client_obligations: [], payroll_obligations: [],
    };
    vi.spyOn(transport, 'get').mockResolvedValue({
      success: true, message: 'ok', error: null,
      data: { ...queryFixture, lifecycle_status: '訂單取消', historical_unserved_correction: correction },
    });
    const result = await orderCancellationClient.query('CASE-1');
    expect(result.historical_unserved_correction).toEqual({ ...correction, prior_fee_ntd: 0n });
  });

  it('opens the existing workbench only for explicit historical mid-service confirmation capability', async () => {
    const historical = {
      ...queryFixture,
      lifecycle_status: '訂單取消',
      historical_mid_service_confirmation_available: true,
      caregiver_options: [{ staff_id: 7, display_name: 'Historical Staff' }],
    };
    vi.spyOn(transport, 'get').mockResolvedValue({
      success: true, message: 'ok', data: historical, error: null,
    });

    await expect(orderCancellationClient.query('CASE-1')).resolves.toEqual({
      ...historical,
      service_started: true,
    });
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

  it('decodes zero-service termination and historical recovery evidence', async () => {
    const data = {
      ...previewFixture,
      lifecycle_impact: { ...previewFixture.lifecycle_impact, after_status: '成立後未服務',
        establishment_evidence: { lifecycle_event_ids: [1], historical_adoption_ids: [2], current_owner_status: null } },
      historical_unserved_correction: {
        classification_only: false, client_cash_difference_requires_review: true, retired_adopted_assignment_ids: [3],
        payroll_recoveries: [{ obligation_identity: 'historical-payable', staff_id: 7, paid_ntd: '9500', recovery_increase_ntd: '6000' }],
      },
    };
    const post = vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: 'ok', data, error: null });
    const correction: HistoricalUnservedCorrection = { reason: '', evidence_source: '', confirmed_actual_service_day_count: 0 };
    const result = await orderCancellationClient.preview('CASE-1', [], undefined, { historical_unserved_correction: correction });
    expect(result.lifecycle_impact.after_status).toBe('成立後未服務');
    expect(result.historical_unserved_correction?.client_cash_difference_requires_review).toBe(true);
    expect(result.historical_unserved_correction?.payroll_recoveries[0]?.recovery_increase_ntd).toBe(6000n);
    expect(post).toHaveBeenCalledWith('/api/v1/orders/CASE-1/cancellation/preview',
      { confirmed_service_days: [], historical_unserved_correction: correction }, expect.anything());
    post.mockResolvedValueOnce({
      success: true, message: 'ok', error: null,
      data: {
        ...data,
        historical_unserved_correction: {
          ...data.historical_unserved_correction,
          client_cash_difference_requires_review: 'true',
        },
      },
    });
    await expect(orderCancellationClient.preview('CASE-1', [], undefined, { historical_unserved_correction: correction })).rejects.toThrow();
  });

  it.each([null, { covered_rate: 300, excess_rate: 450, subsidy_hours: 40, directly_subsidized: false }])(
    'decodes current Payroll cancellation assignments and rate snapshots (%j)', async (tiered) => {
      const data = {
        ...previewFixture,
        payroll_impact: {
          ...previewFixture.payroll_impact,
          payroll: {
            ...previewFixture.payroll_impact.payroll,
            assignments: [{
              assignment_identity: 'CASE-1:g2:a1', staff_id: 7,
              official_service_day_count: 3, actual_hours: 24, double_pay_hours: 0,
              hourly_rate: { amount: 300 }, service_salary: { amount: 7200 },
              floor_fee_allocated: { amount: 0 }, effective_adjustments: { amount: 0 },
              total_payable: { amount: 7200 }, covered_salary: tiered ? 7200 : 0,
              excess_salary: 0, directly_subsidized: false, tiered_pricing: tiered !== null,
            }],
            total_payable: { amount: 7200 },
          },
          carried_rate_snapshots: [{
            assignment_identity: 'CASE-1:g2:a1', policy_version: 'test-rates-v1',
            policy_kind: 'citizen', hourly_rate: { amount: 300 }, tiered,
          }],
        },
      };
      vi.spyOn(transport, 'post').mockResolvedValue({ success: true, message: 'ok', data, error: null });
      await expect(orderCancellationClient.preview('CASE-1', [])).resolves.toEqual(data);
      expect(OrderCancellationPreviewSchema.safeParse({
        ...data, payroll_impact: {
          ...data.payroll_impact,
          carried_rate_snapshots: [{ ...data.payroll_impact.carried_rate_snapshots[0],
            tiered: { covered_rate: 300, excess_rate: 450, subsidy_hours: 40, directly_subsidized: false, unknown_rate: 1 },
          }],
        },
      }).success).toBe(false);
    },
  );

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
    await expect(orderCancellationClient.apply('CASE-1', payload, { idempotencyKey: 'cancel-case-1', actor: 'operator-a' }))
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

  it('accepts empty historical notes and rejects nonzero or boolean service day confirmation in Apply', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true, message: 'ok', data: { ...receiptFixture, lifecycle_status: '成立後未服務' }, error: null,
    });
    const payload = {
      confirmed_service_days: [],
      expected_order_version: 0,
      expected_scheduling_version: 0,
      expected_client_finance_version: 0,
      expected_payroll_version: 0,
      preview_fingerprint: 'a'.repeat(64),
      reason: '',
      historical_unserved_correction: { reason: '', evidence_source: '', confirmed_actual_service_day_count: 0 },
    };
    const parsed = OrderCancellationApplyPayloadSchema.parse(payload);
    await orderCancellationClient.apply('CASE-1', parsed, { idempotencyKey: 'correct-case-1', actor: 'operator-a' });
    expect(post).toHaveBeenCalledWith('/api/v1/orders/CASE-1/cancellation/apply', payload, expect.anything());
    for (const count of [1, false, true]) {
      const invalid = { ...payload, historical_unserved_correction: { ...payload.historical_unserved_correction, confirmed_actual_service_day_count: count } };
      expect(OrderCancellationApplyPayloadSchema.safeParse(invalid).success).toBe(false);
    }
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
      success: true, message: 'ok', data: {
        ...previewFixture,
        client_finance_impact: {
          ...previewFixture.client_finance_impact,
          actions: [{ ...previewFixture.client_finance_impact.actions[0], direction: undefined }],
        },
      }, error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });

  it('rejects a financial direction with zero amount', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true, message: 'ok', data: {
        ...previewFixture,
        client_finance_impact: {
          ...previewFixture.client_finance_impact,
          actions: [{ ...previewFixture.client_finance_impact.actions[0], direction_amount_ntd: 0 }],
        },
      }, error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });

  it('rejects no-finance-change with a nonzero amount', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce({
      success: true, message: 'ok', data: {
        ...previewFixture,
        client_finance_impact: {
          ...previewFixture.client_finance_impact,
          actions: [{ ...previewFixture.client_finance_impact.actions[0], direction: 'no_finance_change', direction_amount_ntd: 1 }],
        },
      }, error: null,
    });
    await expect(orderCancellationClient.preview('CASE-1', [])).rejects.toThrow();
  });
});


describe('explicit cancellation owner absence', () => {
  it('accepts null owners in Query, Preview, receipt and Apply; omission remains invalid', () => {
    const versions = { scheduling_version: null, scheduling_generation: null, client_finance_version: null, payroll_version: null };
    expect(OrderCancellationQuerySchema.parse({ ...queryFixture, ...versions }).payroll_version).toBeNull();
    expect(OrderCancellationPreviewSchema.parse({ ...previewFixture, ...versions, scheduling: null, client_finance_impact: null, payroll_impact: null }).scheduling).toBeNull();
    expect(OrderCancellationReceiptSchema.parse({ ...receiptFixture, ...versions }).scheduling_version).toBeNull();
    const payload = { confirmed_service_days: [], expected_order_version: 1, expected_scheduling_version: null, expected_client_finance_version: null, expected_payroll_version: null, preview_fingerprint: 'a'.repeat(64), reason: '客戶取消' };
    expect(OrderCancellationApplyPayloadSchema.parse(payload).expected_payroll_version).toBeNull();
    const { expected_payroll_version: omitted, ...missing } = payload;
    void omitted;
    expect(OrderCancellationApplyPayloadSchema.safeParse(missing).success).toBe(false);
  });
});
