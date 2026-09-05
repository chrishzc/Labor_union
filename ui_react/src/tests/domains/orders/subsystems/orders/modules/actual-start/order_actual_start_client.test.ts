/**
 * File: order_actual_start_client.test.ts
 * Description: 驗證實際開工日 Preview／Apply client 的 closed decode、路徑、版本與冪等標頭。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import {
  orderActualStartClient,
  type ActualStartApplyPayload,
} from '../../../../../../../api/orders/order_actual_start_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiDecodeError } from '../../../../../../../api/shared/typed_errors';

const fingerprint = (character: string) => character.repeat(64);

const previewFixture = {
  before_actual_start_date: null,
  after_actual_start_date: '2026-09-01',
  actual_end_date: '2026-09-03',
  order_version: 3,
  scheduling_version: 4,
  scheduling_generation: 2,
  client_finance_version: 5,
  payroll_version: 6,
  actual_start: {
    case_no: 'CASE/1',
    kind: 'first_confirmation',
    expected_order_version: 3,
    expected_scheduling_version: 4,
    source_generation_number: 2,
    original_actual_start_date: null,
    original_scheduling_root_date: '2026-08-01',
    new_actual_start_date: '2026-09-01',
    shift_days: 31,
    assignments: [{
      source_assignment_id: 11,
      staff_id: 22,
      sequence: 1,
      assigned_start_date: '2026-09-01',
      assigned_end_date: '2026-09-03',
      service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      actual_hours: 24,
    }],
    official_service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
    actual_end_date: '2026-09-03',
    fingerprint: fingerprint('a'),
  },
  scheduling: {
    case_no: 'CASE/1',
    generation_number: 3,
    expected_aggregate_version: 4,
    resulting_aggregate_version: 5,
    cancelled_assignment_ids: [11],
    assignments: [{
      candidate_key: 'CASE/1:g3:a1',
      source_assignment_id: 11,
      staff_id: 22,
      sequence: 1,
      assigned_start_date: '2026-09-01',
      assigned_end_date: '2026-09-03',
      service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      actual_hours: 24,
      lineage_source_assignment_ids: [11],
      double_pay_dates: [],
    }],
    buffers: [{
      candidate_key: 'CASE/1:g3:a1:buffer',
      staff_id: 22,
      dates: ['2026-09-04'],
      active: false,
    }],
  },
  client_finance_impact: {
    case_no: 'CASE/1',
    expected_account_version: 5,
    resulting_account_version: 6,
    stage_plans: [{
      payment_stage: 'deposit',
      service_dates: ['2026-09-01'],
      amount: { amount: 1000 },
      due_date: '2026-09-01',
    }],
    actions: [{
      action: 'create_stage',
      payment_stage: 'deposit',
      obligation_identity: 'client-obligation-1',
      before_amount: { amount: 0 },
      after_amount: { amount: 1000 },
      obligation_amount: { amount: 1000 },
      before_due_date: null,
      after_due_date: '2026-09-01',
      source_obligation_identity: null,
      direction: 'additional_charge_due',
      direction_amount_ntd: 1000,
    }],
    settlement: {
      deposit_settled: false,
      all_formal_obligations_settled: false,
      fingerprint: fingerprint('b'),
    },
    blockers: [],
    fingerprint: fingerprint('c'),
  },
  payroll_impact: {
    case_no: 'CASE/1',
    expected_payroll_version: 6,
    resulting_payroll_version: 7,
    payroll: {
      assignments: [{
        assignment_identity: 'CASE/1:g3:a1',
        staff_id: 22,
        official_service_day_count: 3,
        actual_hours: 24,
        double_pay_hours: 0,
        hourly_rate: { amount: 300 },
        service_salary: { amount: 7200 },
        floor_fee_allocated: { amount: 0 },
        effective_adjustments: { amount: 0 },
        total_payable: { amount: 7200 },
      }],
      earned_floor_fee: { amount: 0 },
      total_payable: { amount: 7200 },
      fingerprint: fingerprint('d'),
    },
    carried_rate_snapshots: [{
      assignment_identity: 'CASE/1:g3:a1',
      policy_version: '2026-v1',
      policy_kind: 'citizen',
      hourly_rate: { amount: 300 },
    }],
    actions: [{
      action: 'establish',
      obligation_identity: 'staff-obligation-1',
      source_obligation_identity: null,
      source_assignment_id: 11,
      candidate_assignment_key: 'CASE/1:g3:a1',
      staff_id: 22,
      obligation_kind: 'service_pay',
      direction: 'payable_to_staff',
      amount: { amount: 7200 },
      due_date: '2026-09-10',
    }],
    special_pay_events: [{
      assignment_identity: 'CASE/1:g3:a1',
      assignment_sequence: 1,
      service_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
    }],
    blockers: [],
    fingerprint: fingerprint('e'),
  },
  lifecycle_impact: {
    case_no: 'CASE/1',
    before_status: '訂單成立',
    after_status: '服務中',
    actual_end_date: '2026-09-03',
    completion_instant: '2026-09-03T17:00:00+08:00',
    business_date: '2026-08-23',
    service_completion_reached: false,
    service_data_lock_was_present: false,
    service_data_lock_should_exist: false,
    alert_codes: [],
    fingerprint: fingerprint('f'),
  },
  preview_fingerprint: fingerprint('1'),
} as const;

const applyPayload: ActualStartApplyPayload = {
  new_actual_start_date: '2026-09-01',
  expected_order_version: 3,
  expected_scheduling_version: 4,
  expected_client_finance_version: 5,
  expected_payroll_version: 6,
  preview_fingerprint: fingerprint('1'),
  reason: '客戶確認實際開工日',
};

const receiptFixture = {
  case_no: 'CASE/1',
  order_version: 4,
  scheduling_version: 5,
  scheduling_generation: 3,
  client_finance_version: 6,
  payroll_version: 7,
  lifecycle_status: '服務中',
  service_data_lock_formed: false,
  cancelled_assignment_ids: [11],
  created_assignment_keys: ['CASE/1:g3:a1'],
  official_service_day_count: 3,
  official_service_hours: 24,
  preview_fingerprint: fingerprint('1'),
} as const;

const envelope = (data: unknown) => ({
  success: true,
  message: 'ok',
  data,
  error: null,
});

describe('orderActualStartClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('token');
  });

  it('previews the canonical date with encoded case identity and correlation header', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope(previewFixture));

    await expect(orderActualStartClient.preview(
      ' CASE/1 ',
      { new_actual_start_date: '2026-09-01' },
      { correlationId: 'corr-preview-1' },
    )).resolves.toEqual(previewFixture);

    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE%2F1/actual-start/preview',
      { new_actual_start_date: '2026-09-01' },
      expect.objectContaining({
        token: 'token',
        headers: expect.objectContaining({ 'X-Correlation-ID': 'corr-preview-1' }),
      }),
    );
  });

  it('applies all fresh versions with idempotency and correlation headers', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue(envelope(receiptFixture));

    await expect(orderActualStartClient.apply('CASE/1', applyPayload, {
      idempotencyKey: 'idem-actual-start-1',
      correlationId: 'corr-apply-1',
    })).resolves.toEqual(receiptFixture);

    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE%2F1/actual-start/apply',
      applyPayload,
      expect.objectContaining({
        token: 'token',
        headers: expect.objectContaining({
          'Idempotency-Key': 'idem-actual-start-1',
          'X-Correlation-ID': 'corr-apply-1',
        }),
      }),
    );
  });

  it('fails closed on nested Preview and Receipt contract drift', async () => {
    vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope({
      ...previewFixture,
      actual_start: { ...previewFixture.actual_start, leaked: true },
    }));
    await expect(orderActualStartClient.preview(
      'CASE/1',
      { new_actual_start_date: '2026-09-01' },
    )).rejects.toBeInstanceOf(ApiDecodeError);

    vi.spyOn(transport, 'post').mockResolvedValueOnce(envelope({
      ...receiptFixture,
      hidden_write: true,
    }));
    await expect(orderActualStartClient.apply('CASE/1', applyPayload, {
      idempotencyKey: 'idem-actual-start-2',
    })).rejects.toBeInstanceOf(ApiDecodeError);
  });

  it('rejects invalid dates and blank idempotency before transport', async () => {
    const post = vi.spyOn(transport, 'post');
    await expect(orderActualStartClient.preview(
      'CASE/1',
      { new_actual_start_date: '2026-02-30' },
    )).rejects.toThrow('預期有效的 ISO 日期');

    await expect(orderActualStartClient.apply('CASE/1', applyPayload, {
      idempotencyKey: '   ',
    })).rejects.toThrow('Idempotency-Key 長度必須介於 1 至 191 字元');
    expect(post).not.toHaveBeenCalled();
  });
});
