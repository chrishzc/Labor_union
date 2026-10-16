import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { HcmWorkbookSnapshot, applyHcmWorkbook, previewHcmWorkbook } from '../../../../../../../api/case_import/hcm_workbook_client';
import { HCM_WORKBOOK_PREVIEW_FIXTURE } from '../../../../../../fixtures/hcm_workbook_contract_fixtures';

const command = { idempotencyKey: 'hcm-timeout-test', correlationId: 'hcm-timeout-correlation' };
const fingerprint = 'c'.repeat(64);

function response(data: object): Response {
  return new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), { headers: { 'content-type': 'application/json' } });
}

function receipt(digest: string) {
  return { source_content_digest: digest, source_row_count: 1, inserted_count: 1, inserted_with_warning_count: 0, exact_replay_count: 0, review_required_count: 0, failed_count: 0, skipped_existing_count: 0, replayed_workbook: false, row_outcomes_available: true, legacy_summary_only: false, row_outcomes: [] };
}

describe('HCM workbook slow responses', () => {
  beforeEach(() => {
    sessionClient.setSession('hcm-timeout-test-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    sessionClient.clearSession();
  });

  it.each(['preview', 'apply'] as const)('%s 接受超過 30 秒才完成的結果，僅送出一次請求', async (operation) => {
    const snapshot = await HcmWorkbookSnapshot.fromFile(new File(['slow-hcm'], 'hcm.xlsx'));
    const data = operation === 'preview'
      ? { ...HCM_WORKBOOK_PREVIEW_FIXTURE, source_content_digest: snapshot.sha256 }
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
    const request = operation === 'preview' ? previewHcmWorkbook(snapshot) : applyHcmWorkbook(snapshot, fingerprint, command);
    const result = expect(request).resolves.toEqual(data);
    await vi.advanceTimersByTimeAsync(45_000);
    expect(signal.aborted).toBe(false);
    complete(response(data));
    await result;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('真正逾時時標示結果待確認，並指引使用者查詢原操作', async () => {
    const snapshot = await HcmWorkbookSnapshot.fromFile(new File(['slow-hcm'], 'hcm.xlsx'));
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_path: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    })));
    const request = applyHcmWorkbook(snapshot, fingerprint, command);
    const result = expect(request).rejects.toMatchObject({ code: 'hcm_apply_timeout', retryable: true, message: expect.stringContaining('資料可能已寫入') });
    await vi.advanceTimersByTimeAsync(60_000);
    await result;
    await expect(request).rejects.toMatchObject({ message: expect.stringContaining('查詢這次匯入結果') });
    await expect(request).rejects.toMatchObject({ message: expect.not.stringContaining('Idempotency-Key') });
  });
});
