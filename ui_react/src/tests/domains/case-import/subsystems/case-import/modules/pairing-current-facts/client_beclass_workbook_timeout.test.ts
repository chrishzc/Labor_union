import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { ClientBeClassWorkbookSnapshot, applyClientBeClassWorkbook, previewClientBeClassWorkbook } from '../../../../../../../api/case_import/client_beclass_workbook/client';

const command = { idempotencyKey: 'beclass-timeout-test', correlationId: 'beclass-timeout-correlation' };
const fingerprint = 'c'.repeat(64);

function response(data: object): Response {
  return new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { headers: { 'content-type': 'application/json' } });
}

function receipt(digest: string, replayed = false) {
  return { source_content_digest: digest, source_row_count: 1, created_count: 1, exact_replay_count: 0, review_required_count: 0, existing_conflict_count: 0, existing_source_count: 0, replayed_workbook: replayed };
}

describe('Client BeClass workbook slow responses', () => {
  beforeEach(() => {
    sessionClient.setSession('beclass-timeout-test-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    sessionClient.clearSession();
  });

  it.each(['preview', 'apply'] as const)('%s 接受超過 30 秒才完成的結果，僅送出一次請求', async (operation) => {
    const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(new File(['slow-beclass'], 'beclass.xlsx'));
    const data = operation === 'preview'
      ? { source_content_digest: snapshot.sha256, sheet_identity: 'b'.repeat(64), source_row_count: 1, create_count: 1, review_required_count: 0, existing_conflict_count: 0, existing_source_count: 0, preview_fingerprint: fingerprint }
      : receipt(snapshot.sha256);
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
    const request = operation === 'preview' ? previewClientBeClassWorkbook(snapshot) : applyClientBeClassWorkbook(snapshot, fingerprint, command);
    const result = expect(request).resolves.toEqual(data);
    await vi.advanceTimersByTimeAsync(45_000);
    expect(signal.aborted).toBe(false);
    complete(response(data));
    await result;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('逾時後使用相同操作識別讀回已寫入收據', async () => {
    const snapshot = await ClientBeClassWorkbookSnapshot.fromFile(new File(['slow-beclass'], 'beclass.xlsx'));
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockImplementationOnce((_path: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      }))
      .mockResolvedValueOnce(response(receipt(snapshot.sha256, true)));
    vi.stubGlobal('fetch', fetchMock);
    const request = applyClientBeClassWorkbook(snapshot, fingerprint, command);
    const result = expect(request).rejects.toMatchObject({ code: 'client_beclass_apply_timeout', retryable: true, message: expect.stringContaining('資料可能已寫入') });
    await vi.advanceTimersByTimeAsync(179_999);
    expect((vi.mocked(fetch).mock.calls[0]?.[1]?.signal as AbortSignal).aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await result;
    await expect(request).rejects.toMatchObject({ message: expect.stringContaining('查詢這次匯入結果') });
    await expect(request).rejects.toMatchObject({ message: expect.not.stringContaining('Idempotency-Key') });
    await expect(applyClientBeClassWorkbook(snapshot, fingerprint, command)).resolves.toMatchObject({ replayed_workbook: true, created_count: 1 });
    const first = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    const second = new Headers(fetchMock.mock.calls[1]?.[1]?.headers);
    expect(first.get('Idempotency-Key')).toBe(command.idempotencyKey);
    expect(second.get('Idempotency-Key')).toBe(first.get('Idempotency-Key'));
  });
});
