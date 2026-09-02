/**
 * File: historical_order_workbook_client.test.ts
 * Description: 驗證Historical Orders immutable snapshot、typed Preview／Apply、Apply錯誤與無Session零fetch。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { HISTORICAL_ORDER_WORKBOOK_APPLY_PATH, HISTORICAL_ORDER_WORKBOOK_PREVIEW_PATH, HISTORICAL_ORDER_WORKBOOK_TIMEOUT_MS, HistoricalOrderWorkbookSnapshot, applyHistoricalOrderWorkbook, previewHistoricalOrderWorkbook } from '../api/orders/historical_order_workbook/client';
import { HistoricalOrderWorkbookApplyError, HistoricalOrderWorkbookPreviewError, HistoricalOrderWorkbookUnauthenticatedError } from '../api/orders/historical_order_workbook/errors';
import { HistoricalOrderWorkbookPreviewSchema, HistoricalOrderWorkbookReceiptSchema } from '../api/orders/historical_order_workbook/schemas';

function setSession(): void {
  sessionClient.setSession('historical-order-preview-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
}

describe('Historical Orders workbook Preview client', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('只送出workbook multipart並嚴格回傳typed aggregate', async () => {
    const snapshot = await HistoricalOrderWorkbookSnapshot.fromFile(new File(['orders'], 'orders.xlsx'));
    const data = { source_content_digest: snapshot.sha256, sheet_identity: 'b'.repeat(64), source_row_count: 4, adopted_count: 2, unmatched_case_count: 1, review_required_count: 1, current_conflict_count: 0, assignment_candidate_count: 1, evidence_only_pairing_count: 1, absent_order_cancellation_count: 2, status_counts: { cancelled_0: 1, deposit_paid_1: 1, discussion_2: 1, invalid_or_blank: 1 }, result_counts: { not_adopted: 1, matching_pending_deposit: 1, historical_unserved: 1, historical_in_service: 1, historical_service_completed: 0 }, preview_fingerprint: 'c'.repeat(64) };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;

    await expect(previewHistoricalOrderWorkbook(snapshot)).resolves.toEqual(data);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(HISTORICAL_ORDER_WORKBOOK_PREVIEW_PATH);
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(Array.from(form.keys())).toEqual(['workbook']);
    expect(HISTORICAL_ORDER_WORKBOOK_TIMEOUT_MS).toBe(120_000);
  });

  it('Apply送出fingerprint form與冪等headers並回傳typed receipt', async () => {
    const snapshot = await HistoricalOrderWorkbookSnapshot.fromFile(new File(['orders'], 'orders.xlsx'));
    const receipt = { source_content_digest: snapshot.sha256, source_row_count: 1, adopted_count: 1, unmatched_case_count: 0, review_required_count: 1, current_conflict_count: 0, absent_order_cancellation_count: 1, assignments_created: 1, replayed_rows: 0, replayed_workbook: false, status_counts: { cancelled_0: 0, deposit_paid_1: 1, discussion_2: 0, invalid_or_blank: 0 }, result_counts: { not_adopted: 0, matching_pending_deposit: 0, historical_unserved: 1, historical_in_service: 0, historical_service_completed: 0 }, review_references: ['historical-order-review:one'] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data: receipt, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;
    await expect(applyHistoricalOrderWorkbook(snapshot, 'c'.repeat(64), { idempotencyKey: 'orders-apply-1', correlationId: 'orders-correlation-1' })).resolves.toEqual(receipt);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(HISTORICAL_ORDER_WORKBOOK_APPLY_PATH);
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get('preview_fingerprint')).toBe('c'.repeat(64));
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get('Idempotency-Key')).toBe('orders-apply-1');
    expect(headers.get('X-Correlation-ID')).toBe('orders-correlation-1');
  });

  it('Apply暫時不可用時不會誤報成Preview錯誤', async () => {
    const snapshot = await HistoricalOrderWorkbookSnapshot.fromFile(new File(['orders'], 'orders.xlsx'));
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 503, headers: { 'content-type': 'application/json' } }));
    const request = applyHistoricalOrderWorkbook(snapshot, 'c'.repeat(64), { idempotencyKey: 'orders-apply-1', correlationId: 'orders-correlation-1' });
    await expect(request).rejects.toBeInstanceOf(HistoricalOrderWorkbookApplyError);
  });

  it('Preview會顯示歷史指派不足的實際開工 blocker', async () => {
    const snapshot = await HistoricalOrderWorkbookSnapshot.fromFile(new File(['orders'], 'orders.xlsx'));
    const error = {
      category: 'domain_blocked',
      code: 'historical_assignment_required_for_actual_start',
      message: '歷史訂單缺少重建實際開工所需的目前資料。',
      field_errors: [],
      domain_blockers: ['historical_assignment_required_for_actual_start'],
      retryable: false,
      correlation_id: 'historical-preview-blocker',
      current_version: null,
    };
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: { error } }), { status: 409, headers: { 'content-type': 'application/json' } }));

    await expect(previewHistoricalOrderWorkbook(snapshot)).rejects.toMatchObject({
      name: HistoricalOrderWorkbookPreviewError.name,
      code: 'historical_assignment_required_for_actual_start',
      message: '歷史訂單缺少已完成的歷史服務指派，無法重建實際開工資料。',
      status: 409,
    });
  });

  it('無Session時零fetch', async () => {
    sessionClient.clearSession();
    globalThis.fetch = vi.fn();
    const snapshot = await HistoricalOrderWorkbookSnapshot.fromFile(new File(['x'], 'orders.xlsx'));
    await expect(previewHistoricalOrderWorkbook(snapshot)).rejects.toBeInstanceOf(HistoricalOrderWorkbookUnauthenticatedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('strict schema拒絕extra、null與無效digest', () => {
    const base = { source_content_digest: 'a'.repeat(64), sheet_identity: 'b'.repeat(64), source_row_count: 0, adopted_count: 0, unmatched_case_count: 0, review_required_count: 0, current_conflict_count: 0, assignment_candidate_count: 0, evidence_only_pairing_count: 0, absent_order_cancellation_count: 0, status_counts: { cancelled_0: 0, deposit_paid_1: 0, discussion_2: 0, invalid_or_blank: 0 }, result_counts: { not_adopted: 0, matching_pending_deposit: 0, historical_unserved: 0, historical_in_service: 0, historical_service_completed: 0 }, preview_fingerprint: 'c'.repeat(64) };
    expect(HistoricalOrderWorkbookPreviewSchema.safeParse({ ...base, extra: true }).success).toBe(false);
    expect(HistoricalOrderWorkbookPreviewSchema.safeParse({ ...base, adopted_count: null }).success).toBe(false);
    expect(HistoricalOrderWorkbookPreviewSchema.safeParse({ ...base, sheet_identity: 'BAD' }).success).toBe(false);
    expect(HistoricalOrderWorkbookPreviewSchema.safeParse({ ...base, source_row_count: 1 }).success).toBe(false);
    const receipt = { source_content_digest: 'a'.repeat(64), source_row_count: 1, adopted_count: 1, unmatched_case_count: 0, review_required_count: 0, current_conflict_count: 0, absent_order_cancellation_count: 1, assignments_created: 0, replayed_rows: 0, replayed_workbook: false, status_counts: base.status_counts, result_counts: base.result_counts, review_references: [] };
    expect(HistoricalOrderWorkbookReceiptSchema.safeParse(receipt).success).toBe(false);
  });
});
