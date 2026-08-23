/**
 * File: staff_historical_workbook_client.test.ts
 * Description: 驗證Staff Historical immutable snapshot、typed Preview／Apply、Apply錯誤與無Session零fetch。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { STAFF_HISTORICAL_WORKBOOK_APPLY_PATH, STAFF_HISTORICAL_WORKBOOK_PREVIEW_PATH, StaffHistoricalWorkbookSnapshot, applyStaffHistoricalWorkbook, previewStaffHistoricalWorkbook } from '../api/case_import/staff_historical_workbook/client';
import { StaffHistoricalWorkbookApplyError, StaffHistoricalWorkbookUnauthenticatedError } from '../api/case_import/staff_historical_workbook/errors';
import { StaffHistoricalWorkbookPreviewSchema } from '../api/case_import/staff_historical_workbook/schemas';

function setSession(): void {
  sessionClient.setSession('staff-historical-preview-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
}

describe('Staff Historical workbook Preview client', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('只送出workbook與明示source_revision並回傳typed aggregate', async () => {
    const snapshot = await StaffHistoricalWorkbookSnapshot.fromFile(new File(['staff'], 'staff.xlsx'));
    const data = { source_content_digest: snapshot.sha256, source_row_count: 5, created_count: 1, adopted_existing_count: 1, blocked_identity_count: 1, identity_conflict_count: 1, review_required_count: 1, preview_fingerprint: 'c'.repeat(64) };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;

    await expect(previewStaffHistoricalWorkbook(snapshot, { sourceRevision: 'rev-1' })).resolves.toEqual(data);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(STAFF_HISTORICAL_WORKBOOK_PREVIEW_PATH);
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(Array.from(form.keys())).toEqual(['workbook', 'source_revision']);
  });

  it('Apply送出fingerprint與冪等headers並保留source_revision', async () => {
    const snapshot = await StaffHistoricalWorkbookSnapshot.fromFile(new File(['staff'], 'staff.xlsx'));
    const receipt = { source_content_digest: snapshot.sha256, source_row_count: 1, created_count: 1, adopted_existing_count: 0, blocked_identity_count: 0, identity_conflict_count: 0, review_required_count: 0, preview_fingerprint: 'c'.repeat(64), exact_replay_count: 0, replayed_workbook: false };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data: receipt, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;
    await expect(applyStaffHistoricalWorkbook(snapshot, 'c'.repeat(64), { sourceRevision: 'rev-1', idempotencyKey: 'staff-apply-1', correlationId: 'staff-correlation-1' })).resolves.toEqual(receipt);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(STAFF_HISTORICAL_WORKBOOK_APPLY_PATH);
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get('source_revision')).toBe('rev-1');
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get('X-Preview-Fingerprint')).toBe('c'.repeat(64));
    expect(headers.get('Idempotency-Key')).toBe('staff-apply-1');
    expect(headers.get('X-Correlation-ID')).toBe('staff-correlation-1');
  });

  it('Apply暫時不可用時不會誤報成Preview錯誤', async () => {
    const snapshot = await StaffHistoricalWorkbookSnapshot.fromFile(new File(['staff'], 'staff.xlsx'));
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 503, headers: { 'content-type': 'application/json' } }));
    const request = applyStaffHistoricalWorkbook(snapshot, 'c'.repeat(64), { idempotencyKey: 'staff-apply-1', correlationId: 'staff-correlation-1' });
    await expect(request).rejects.toBeInstanceOf(StaffHistoricalWorkbookApplyError);
  });

  it('無Session時零fetch', async () => {
    sessionClient.clearSession();
    globalThis.fetch = vi.fn();
    const snapshot = await StaffHistoricalWorkbookSnapshot.fromFile(new File(['x'], 'staff.xlsx'));
    await expect(previewStaffHistoricalWorkbook(snapshot)).rejects.toBeInstanceOf(StaffHistoricalWorkbookUnauthenticatedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('strict schema拒絕extra、null與無效digest', () => {
    const base = { source_content_digest: 'a'.repeat(64), source_row_count: 0, created_count: 0, adopted_existing_count: 0, blocked_identity_count: 0, identity_conflict_count: 0, review_required_count: 0, preview_fingerprint: 'c'.repeat(64) };
    expect(StaffHistoricalWorkbookPreviewSchema.safeParse({ ...base, extra: true }).success).toBe(false);
    expect(StaffHistoricalWorkbookPreviewSchema.safeParse({ ...base, created_count: null }).success).toBe(false);
    expect(StaffHistoricalWorkbookPreviewSchema.safeParse({ ...base, source_content_digest: 'BAD' }).success).toBe(false);
  });
});
