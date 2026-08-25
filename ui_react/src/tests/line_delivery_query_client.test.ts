/**
 * File: line_delivery_query_client.test.ts
 * Description: 驗證 LINE Delivery 三個 masked GET、fresh Session、strict schema 與 identity/aggregate fail closed。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { lineDeliveryQueryClient } from '../api/line_delivery/line_delivery_query_client';
import { adaptLineDeliveryItem } from '../adapters/line_delivery/line_delivery_query_adapter';

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { 'content-type': 'application/json' } });
}

function envelope(data: unknown) { return { success: true, message: 'ok', data, error: null }; }

const summary = {
  total: 3, pending: 1, processing: 0, sent: 2, retryable_failed: 0, failed: 0,
  cancelled: 0, overdue: 0, sent_today: 1, next_run_at: '2026-08-23T12:00:00+08:00',
  worker_running: true, worker_status: 'healthy',
};

const task = {
  id: 17, task_id: 17, task_type: 'follow_up', source_type: 'customer_service', status: 'sent',
  scheduled_at: '2026-08-23T10:00:00+08:00', completed_attempts: 1, max_attempts: 3,
  next_retry_at: null, sent_at: '2026-08-23T10:01:00+08:00', failed_at: null,
  created_at: '2026-08-23T09:00:00+08:00', updated_at: '2026-08-23T10:01:00+08:00',
};

function setSession(token = 'delivery-token-a'): void {
  sessionClient.setSession(token, {
    id: 7, username: 'delivery-reader', display_name: '發送查詢', role: 'operator',
    linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1,
  });
}

describe('LINE delivery query client', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('以 fresh bearer 依序查 summary/list/detail，且 adapter 不產生敏感欄位', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(envelope(summary)))
      .mockResolvedValueOnce(response(envelope({ items: [task], page: 1, page_size: 20, total: 1, total_pages: 1 })))
      .mockResolvedValueOnce(response(envelope({ task, attempts: [{
        attempt_number: 1, outcome: 'success', retry_after_seconds: null,
        started_at: '2026-08-23T10:00:00+08:00', completed_at: '2026-08-23T10:01:00+08:00',
      }] })));
    globalThis.fetch = fetchMock;

    await lineDeliveryQueryClient.summary();
    setSession('delivery-token-b');
    const page = await lineDeliveryQueryClient.list({ status: 'sent', sourceType: 'customer_service', page: 1, pageSize: 20 });
    const detail = await lineDeliveryQueryClient.detail(17);

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/line/tasks/summary',
      '/api/v1/line/tasks?status=sent&source_type=customer_service&page=1&page_size=20',
      '/api/v1/line/tasks/17',
    ]);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer delivery-token-a');
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe('Bearer delivery-token-b');
    expect(fetchMock.mock.calls.every((call) => call[1]?.method === 'GET')).toBe(true);
    expect(page.items).toHaveLength(1);
    expect(detail.attempts).toHaveLength(1);
    const adapted = adaptLineDeliveryItem(page.items[0]);
    expect(JSON.stringify(adapted)).not.toContain('recipient');
    expect(adapted.statusLabel).toBe('已送出');
    expect(adapted.statusLabel).not.toContain('已送達');
  });

  it('拒絕 extra/raw sensitive payload、aggregate 漂移與 request identity 漂移', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(envelope({ ...task, recipient_identity: 'raw-user' })));
    await expect(lineDeliveryQueryClient.detail(17)).rejects.toMatchObject({ code: 'LINE_DELIVERY_SCHEMA_MISMATCH' });

    globalThis.fetch = vi.fn().mockResolvedValue(response(envelope({ ...summary, total: 99 })));
    await expect(lineDeliveryQueryClient.summary()).rejects.toMatchObject({ code: 'LINE_DELIVERY_AGGREGATE_MISMATCH' });

    globalThis.fetch = vi.fn().mockResolvedValue(response(envelope({ task: { ...task, id: 18, task_id: 18 }, attempts: [] })));
    await expect(lineDeliveryQueryClient.detail(17)).rejects.toMatchObject({ code: 'LINE_DELIVERY_IDENTITY_MISMATCH' });
  });

  it('未登入與非法 pageSize 皆在發出 request 前 fail closed', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();
    await expect(lineDeliveryQueryClient.summary()).rejects.toMatchObject({ code: 'LINE_DELIVERY_UNAUTHENTICATED' });
    setSession();
    await expect(lineDeliveryQueryClient.list({ pageSize: 101 })).rejects.toMatchObject({ code: 'LINE_DELIVERY_VALIDATION' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
