import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { StaffHistoricalWorkbookSnapshot, applyStaffHistoricalWorkbook, previewStaffHistoricalWorkbook } from '../../../../../../../api/case_import/staff_historical_workbook/client';

const command = { idempotencyKey: 'staff-timeout-test', correlationId: 'staff-timeout-correlation' };
const fingerprint = 'c'.repeat(64);

function response(data: object): Response {
  return new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { headers: { 'content-type': 'application/json' } });
}

describe('Staff Historical workbook slow responses', () => {
  beforeEach(() => {
    sessionClient.setSession('staff-timeout-test-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    sessionClient.clearSession();
  });

  it.each(['preview', 'apply'] as const)('%s 接受超過 30 秒才完成的結果，僅送出一次請求', async (operation) => {
    const snapshot = await StaffHistoricalWorkbookSnapshot.fromFile(new File(['slow-staff'], 'staff.xlsx'));
    const preview = { source_content_digest: snapshot.sha256, source_row_count: 1, created_count: 1, adopted_existing_count: 0, blocked_identity_count: 0, identity_conflict_count: 0, review_required_count: 0, preview_fingerprint: fingerprint };
    const data = operation === 'preview' ? preview : { ...preview, exact_replay_count: 0, replayed_workbook: false };
    vi.useFakeTimers();
    let complete!: (value: Response) => void;
    let signal!: AbortSignal;
    const fetchMock = vi.fn((_path: string, init: RequestInit) => {
      signal = init.signal as AbortSignal;
      return new Promise<Response>((resolve, reject) => {
        complete = resolve;
        signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const request = operation === 'preview' ? previewStaffHistoricalWorkbook(snapshot) : applyStaffHistoricalWorkbook(snapshot, fingerprint, command);
    const result = expect(request).resolves.toEqual(data);
    await vi.advanceTimersByTimeAsync(45_000);
    expect(signal.aborted).toBe(false);
    complete(response(data));
    await result;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('真正逾時時標示結果待確認，並指引使用者查詢原操作', async () => {
    const snapshot = await StaffHistoricalWorkbookSnapshot.fromFile(new File(['slow-staff'], 'staff.xlsx'));
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_path: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    })));
    const request = applyStaffHistoricalWorkbook(snapshot, fingerprint, command);
    const result = expect(request).rejects.toMatchObject({ code: 'staff_historical_apply_timeout', retryable: true, message: expect.stringContaining('資料可能已寫入') });
    await vi.advanceTimersByTimeAsync(179_999);
    expect((vi.mocked(fetch).mock.calls[0]?.[1]?.signal as AbortSignal).aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await result;
    await expect(request).rejects.toMatchObject({ message: expect.stringContaining('查詢這次匯入結果') });
    await expect(request).rejects.toMatchObject({ message: expect.not.stringContaining('Idempotency-Key') });
  });
});
