/**
 * File: line_order_group_query_client.test.ts
 * Description: 驗證 LINE 訂單群組 numbered GET、strict metadata、identity fail closed 與顯示去識別。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { lineOrderGroupQueryClient } from '../api/line_order_groups/line_order_group_query_client';
import { adaptLineOrderGroupEvent, adaptLineOrderGroupRecord } from '../adapters/line_order_groups/line_order_group_query_adapter';

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status: 200, headers: { 'content-type': 'application/json' } });
}

const record = { case_no: 'CASE-2026-001', group_id: 'C0123456789ABCDEF', status: 'active', version: 3 };
const event = {
  event_id: 9, case_no: record.case_no, event_type: 'group_activated', actor_id: 'admin-123456789',
  occurred_at: '2026-08-23T15:30:00+08:00', invitation_fingerprint: 'abcdef0123456789',
};

function setSession(token = 'group-token-a'): void {
  sessionClient.setSession(token, {
    id: 8, username: 'group-reader', display_name: '群組查詢', role: 'operator',
    linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1,
  });
}

describe('LINE order group query client', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('查詢 list/detail/events 並以 adapter 遮蔽 group、actor 與 fingerprint', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ items: [record], page: 2, page_size: 20, total: 21, total_pages: 2 }))
      .mockResolvedValueOnce(response(record))
      .mockResolvedValueOnce(response({ items: [event], page: 1, page_size: 10, total: 1, total_pages: 1 }));
    globalThis.fetch = fetchMock;

    const page = await lineOrderGroupQueryClient.list({ status: 'active', page: 2, pageSize: 20 });
    const detail = await lineOrderGroupQueryClient.detail(record.case_no);
    const events = await lineOrderGroupQueryClient.events(record.case_no, { page: 1, pageSize: 10 });

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/line/order-groups/numbered?status=active&page=2&page_size=20',
      '/api/v1/line/order-groups/CASE-2026-001',
      '/api/v1/line/order-groups/CASE-2026-001/events/numbered?page=1&page_size=10',
    ]);
    expect(fetchMock.mock.calls.every((call) => call[1]?.method === 'GET')).toBe(true);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer group-token-a');
    const rendered = JSON.stringify([adaptLineOrderGroupRecord(page.items[0]), adaptLineOrderGroupRecord(detail), adaptLineOrderGroupEvent(events.items[0])]);
    expect(rendered).not.toContain(record.group_id);
    expect(rendered).not.toContain(event.actor_id);
    expect(rendered).not.toContain(event.invitation_fingerprint);
  });

  it('拒絕 extra schema drift 與 detail/event case identity 漂移', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({ items: [{ ...record, invitation_url: 'raw-secret' }], page: 1, page_size: 25, total: 1, total_pages: 1 }));
    await expect(lineOrderGroupQueryClient.list()).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_SCHEMA_MISMATCH' });

    globalThis.fetch = vi.fn().mockResolvedValue(response({ ...record, case_no: 'OTHER' }));
    await expect(lineOrderGroupQueryClient.detail(record.case_no)).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_IDENTITY_MISMATCH' });

    globalThis.fetch = vi.fn().mockResolvedValue(response({ items: [{ ...event, case_no: 'OTHER' }], page: 1, page_size: 25, total: 1, total_pages: 1 }));
    await expect(lineOrderGroupQueryClient.events(record.case_no)).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_IDENTITY_MISMATCH' });
  });

  it('未登入、空白 caseNo 與超界 pageSize 在 request 前 fail closed', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();
    await expect(lineOrderGroupQueryClient.list()).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_UNAUTHENTICATED' });
    setSession();
    await expect(lineOrderGroupQueryClient.detail(' CASE ')).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_VALIDATION' });
    await expect(lineOrderGroupQueryClient.events(record.case_no, { pageSize: 201 })).rejects.toMatchObject({ code: 'LINE_ORDER_GROUP_VALIDATION' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
