/**
 * File: order_cancellation_client.test.ts
 * Description: 驗證訂單取消 Query／零寫入 Preview 的路徑、typed decode 與識別防漂移。
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
  scheduling: {},
  client_finance_impact: {},
  payroll_impact: {},
  lifecycle_impact: {},
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
});
