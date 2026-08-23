/**
 * File: client_beclass_workbook_client.test.ts
 * Description: 驗證Client BeClass immutable snapshot、typed Preview／Apply、Apply錯誤與無Session零fetch。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { CLIENT_BECLASS_WORKBOOK_APPLY_PATH, CLIENT_BECLASS_WORKBOOK_PREVIEW_PATH, ClientBeClassWorkbookSnapshot, applyClientBeClassWorkbook, previewClientBeClassWorkbook } from '../api/case_import/client_beclass_workbook/client';
import { ClientBeClassWorkbookApplyError, ClientBeClassWorkbookUnauthenticatedError } from '../api/case_import/client_beclass_workbook/errors';
import { ClientBeClassWorkbookPreviewSchema } from '../api/case_import/client_beclass_workbook/schemas';

function setSession(): void {
  sessionClient.setSession('client-beclass-preview-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
}

describe('Client BeClass workbook Preview client', () => {
  beforeEach(() => { vi.restoreAllMocks(); setSession(); });
  afterEach(() => { sessionClient.clearSession(); vi.restoreAllMocks(); });

  it('只送出workbook multipart並嚴格回傳typed aggregate', async () => {
    const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(new File(['beclass'], 'beclass.xlsx'));
    const data = { source_content_digest: snapshot.sha256, sheet_identity: 'b'.repeat(64), source_row_count: 4, create_count: 1, review_required_count: 1, existing_conflict_count: 1, existing_source_count: 1, preview_fingerprint: 'c'.repeat(64) };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;

    await expect(previewClientBeClassWorkbook(snapshot)).resolves.toEqual(data);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(CLIENT_BECLASS_WORKBOOK_PREVIEW_PATH);
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(Array.from(form.keys())).toEqual(['workbook']);
  });

  it('Apply送出fingerprint form與冪等headers並回傳typed receipt', async () => {
    const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(new File(['beclass'], 'beclass.xlsx'));
    const receipt = { source_content_digest: snapshot.sha256, source_row_count: 1, created_count: 1, exact_replay_count: 0, review_required_count: 0, existing_conflict_count: 0, existing_source_count: 0, replayed_workbook: false };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, message: 'ok', data: receipt, error: null }), { status: 200, headers: { 'content-type': 'application/json' } }));
    globalThis.fetch = fetchMock;
    await expect(applyClientBeClassWorkbook(snapshot, 'c'.repeat(64), { idempotencyKey: 'beclass-apply-1', correlationId: 'beclass-correlation-1' })).resolves.toEqual(receipt);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(CLIENT_BECLASS_WORKBOOK_APPLY_PATH);
    const form = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(form.get('preview_fingerprint')).toBe('c'.repeat(64));
    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(headers.get('Idempotency-Key')).toBe('beclass-apply-1');
    expect(headers.get('X-Correlation-ID')).toBe('beclass-correlation-1');
  });

  it('Apply暫時不可用時回傳Apply typed error與相同識別重試說明', async () => {
    const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(new File(['beclass'], 'beclass.xlsx'));
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 503, headers: { 'content-type': 'application/json' } }));
    await expect(applyClientBeClassWorkbook(snapshot, 'c'.repeat(64), { idempotencyKey: 'beclass-apply-1', correlationId: 'beclass-correlation-1' }))
      .rejects.toMatchObject({ name: 'ClientBeClassWorkbookApplyError', retryable: true });
    await expect(applyClientBeClassWorkbook(snapshot, 'c'.repeat(64), { idempotencyKey: 'beclass-apply-1', correlationId: 'beclass-correlation-2' }))
      .rejects.toBeInstanceOf(ClientBeClassWorkbookApplyError);
  });

  it('無Session時零fetch', async () => {
    sessionClient.clearSession();
    globalThis.fetch = vi.fn();
    const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(new File(['x'], 'beclass.xlsx'));
    await expect(previewClientBeClassWorkbook(snapshot)).rejects.toBeInstanceOf(ClientBeClassWorkbookUnauthenticatedError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('strict schema拒絕extra、null與無效digest', () => {
    const base = { source_content_digest: 'a'.repeat(64), sheet_identity: 'b'.repeat(64), source_row_count: 0, create_count: 0, review_required_count: 0, existing_conflict_count: 0, existing_source_count: 0, preview_fingerprint: 'c'.repeat(64) };
    expect(ClientBeClassWorkbookPreviewSchema.safeParse({ ...base, extra: true }).success).toBe(false);
    expect(ClientBeClassWorkbookPreviewSchema.safeParse({ ...base, create_count: null }).success).toBe(false);
    expect(ClientBeClassWorkbookPreviewSchema.safeParse({ ...base, preview_fingerprint: 'BAD' }).success).toBe(false);
  });
});
