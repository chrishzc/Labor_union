/**
 * File: order_service_completion_client.test.ts
 * Description: 驗證服務完成 React client 的 Preview binding、Apply headers 與 receipt strict contract。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { sessionClient } from '../api/auth/session_client';
import { orderServiceCompletionClient } from '../api/orders/order_service_completion_client';

const fingerprint = 'a'.repeat(64);
const commandFingerprint = 'b'.repeat(64);
const response = (data: object) => new Response(
  JSON.stringify({ success: true, message: 'ok', data, error: null }),
  { status: 200, headers: { 'content-type': 'application/json' } },
);

describe('orderServiceCompletionClient', () => {
  beforeEach(() => {
    sessionClient.setSession('completion-token', {
      id: 7,
      username: 'admin',
      display_name: 'Admin',
      role: 'admin',
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('binds Preview facts to canonical Apply and decodes receipt', async () => {
    const preview = {
      case_no: '115000151',
      expected_order_version: 5,
      resulting_order_version: 6,
      current_status: '服務中',
      completion_instant: '2026-08-09T17:00:00+08:00',
      evaluation_at: '2026-08-24T17:00:00+08:00',
      official_service_dates: ['2026-08-03', '2026-08-04', '2026-08-05', '2026-08-08', '2026-08-09'],
      fingerprint,
    };
    const receipt = {
      case_no: '115000151',
      idempotency_key: 'completion-key',
      order_version: 6,
      lifecycle_event_id: 9,
      completion_instant: preview.completion_instant,
      evaluation_at: preview.evaluation_at,
      command_fingerprint: commandFingerprint,
    };
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(response(preview))
      .mockResolvedValueOnce(response(receipt));

    const loaded = await orderServiceCompletionClient.preview('115000151');
    await expect(
      orderServiceCompletionClient.apply(
        '115000151',
        loaded,
        '已核對服務完成',
        'completion-key',
      ),
    ).resolves.toEqual(receipt);

    const [, applyOptions] = vi.mocked(globalThis.fetch).mock.calls[1] ?? [];
    expect(new Headers(applyOptions?.headers).get('Idempotency-Key')).toBe('completion-key');
    expect(JSON.parse(String(applyOptions?.body))).toMatchObject({
      expected_order_version: 5,
      preview_fingerprint: fingerprint,
      reason: '已核對服務完成',
    });
  });

  it('rejects receipt payloads with extra raw fields', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      case_no: '115000151',
      idempotency_key: 'completion-key',
      order_version: 6,
      lifecycle_event_id: 9,
      completion_instant: '2026-08-09T17:00:00+08:00',
      evaluation_at: '2026-08-24T17:00:00+08:00',
      command_fingerprint: commandFingerprint,
      raw_payload: {},
    }));

    await expect(
      orderServiceCompletionClient.apply(
        '115000151',
        {
          case_no: '115000151',
          expected_order_version: 5,
          resulting_order_version: 6,
          current_status: '服務中',
          completion_instant: '2026-08-09T17:00:00+08:00',
          evaluation_at: '2026-08-24T17:00:00+08:00',
          official_service_dates: ['2026-08-09'],
          fingerprint,
        },
        '已核對服務完成',
        'completion-key',
      ),
    ).rejects.toThrow('回應結構異常');
  });
});
