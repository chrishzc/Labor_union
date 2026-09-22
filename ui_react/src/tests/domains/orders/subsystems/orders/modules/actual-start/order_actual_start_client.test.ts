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
  operation: 'reschedule',
  before_actual_start_date: null,
  after_actual_start_date: '2026-09-01',
  actual_end_date: '2026-09-03',
  order_version: 3,
  scheduling_version: 4,
  scheduling_generation: 2,
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
  operation: 'reschedule',
  new_actual_start_date: '2026-09-01',
  expected_order_version: 3,
  expected_scheduling_version: 4,
  preview_fingerprint: fingerprint('1'),
  reason: '客戶確認實際開工日',
};

const receiptFixture = {
  operation: 'reschedule',
  case_no: 'CASE/1',
  order_version: 4,
  scheduling_version: 5,
  scheduling_generation: 3,
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

  it('accepts a date-only preview and result without downstream versions', async () => {
    const dateOnlyPreview = {
      operation: 'date_only',
      case_no: 'CASE/1',
      before_actual_start_date: null,
      after_actual_start_date: '2026-09-01',
      order_version: 3,
      scheduling_version: null,
      scheduling_generation: null,
      client_finance_version: null,
      payroll_version: null,
      preview_fingerprint: fingerprint('2'),
    } as const;
    const dateOnlyResult = {
      operation: 'date_only',
      case_no: 'CASE/1',
      actual_start_date: '2026-09-01',
      order_version: 4,
      scheduling_version: null,
      scheduling_generation: null,
      client_finance_version: null,
      payroll_version: null,
      preview_fingerprint: fingerprint('2'),
      changed: true,
    } as const;
    vi.spyOn(transport, 'post')
      .mockResolvedValueOnce(envelope(dateOnlyPreview))
      .mockResolvedValueOnce(envelope(dateOnlyResult));

    await expect(orderActualStartClient.preview(
      'CASE/1',
      { new_actual_start_date: '2026-09-01' },
    )).resolves.toEqual(dateOnlyPreview);
    await expect(orderActualStartClient.apply('CASE/1', {
      operation: 'date_only',
      new_actual_start_date: '2026-09-01',
      expected_order_version: 3,
      preview_fingerprint: fingerprint('2'),
    }, { idempotencyKey: 'date-only-1' })).resolves.toEqual(dateOnlyResult);
  });

  it('rejects retired downstream impact fields in a reschedule preview', async () => {
    const payload = {
      ...previewFixture,
      client_finance_impact: {
        actions: [],
        blockers: [],
      },
    };
    vi.spyOn(transport, 'post').mockResolvedValue(envelope(payload));

    await expect(orderActualStartClient.preview(
      'CASE/1',
      { new_actual_start_date: '2026-09-01' },
    )).rejects.toBeInstanceOf(ApiDecodeError);
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
