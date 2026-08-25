/**
 * File: line_identity_client.test.ts
 * Description: 驗證 LINE 身分查詢、審核、更正、解除與維護端點、逐次 Session、嚴格解碼及錯誤映射。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  applyLineIdentityRevocation,
  applyLineIdentityReplacement,
  getLineIdentityBinding,
  getLineIdentityReview,
  getLineIdentityReviewSummary,
  listLineIdentityBindings,
  listLineIdentityReviews,
  manualCompleteLineIdentityRevocation,
  previewLineIdentityRevocation,
  previewLineIdentityReplacement,
  previewLineIdentityReviewDecision,
  retryLineIdentityRevocation,
  applyLineIdentityReviewDecision,
} from '../api/line_identity/line_identity_client';
import { LineIdentityClientError } from '../api/line_identity/line_identity_errors';
import {
  BINDING_PAGE_FIXTURE,
  BOUND_IDENTITY_FIXTURE,
  FIXTURE_LINE_USER_ID,
  REVOCATION_APPLY_REQUEST_FIXTURE,
  REVOCATION_PREVIEW_FIXTURE,
  REVOCATION_REQUEST_FIXTURE,
  envelope,
} from './fixtures/line_identity/line_identity_contract_fixtures';

function jsonResponse(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => data,
  };
}

const REVIEW_FIXTURE = {
  request_id: 71,
  review_type: 'staff_verification' as const,
  status: 'pending' as const,
  version: 3,
  subject_type: 'staff' as const,
  subject_reference: 'STAFF-REVIEW-071',
  assigned_admin_id: null,
  due_at: null,
  line_user_id_masked: 'Urev•••7890',
  display_name: '待審月嫂甲',
  decision_reason: null,
  reviewed_by_actor_id: null,
  reviewed_at: null,
  created_at: '2026-08-24T10:00:00+08:00',
};

const REVIEW_SUMMARY_FIXTURE = {
  pending_total: 4,
  staff_pending: 2,
  rebind_pending: 1,
  processed_today: 3,
  stale_pending: 1,
  stale_hours: 24,
};

const REVIEW_PREVIEW_FIXTURE = {
  request_id: 71,
  decision: 'approve' as const,
  before_status: 'pending' as const,
  after_status: 'approved' as const,
  expected_version: 3,
  resulting_version: 4,
  subject_type: 'staff' as const,
  subject_reference: 'STAFF-REVIEW-071',
  line_user_id_masked: 'Urev•••7890',
  preview_fingerprint: 'review-preview-fixture-071',
};

describe('LINE Identity Client（Phase 3A Lane D）', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.setSession('line-memory-token-a', {
      id: 1,
      username: 'line-operator',
      display_name: 'LINE Operator',
      role: 'admin',
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    globalThis.fetch = originalFetch;
  });

  it('list 只呼叫核准 GET path、傳遞 typed filters 並注入當下 token', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(envelope(BINDING_PAGE_FIXTURE)));

    const result = await listLineIdentityBindings({
      status: 'bound',
      subject_type: 'customer',
      search: '測試',
      page: 1,
      page_size: 25,
    });

    expect(result).toEqual(BINDING_PAGE_FIXTURE);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe(
      '/api/v1/line/identity-bindings?status=bound&subject_type=customer&search=%E6%B8%AC%E8%A9%A6&page=1&page_size=25'
    );
    expect(options?.method).toBe('GET');
    const headers = options?.headers as Record<string, string> | undefined;
    expect(headers?.Authorization).toBe('Bearer line-memory-token-a');
  });

  it('detail URL 安全編碼且一次動作只有一個 GET', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(envelope(BOUND_IDENTITY_FIXTURE)));

    await getLineIdentityBinding('Ufixture/with?reserved');

    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe('/api/v1/line/identity-bindings/Ufixture%2Fwith%3Freserved');
    expect(options?.method).toBe('GET');
  });

  it('review list、summary 與 detail 只呼叫 frozen typed GET paths', async () => {
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(envelope({ items: [REVIEW_FIXTURE], next_cursor: null })))
      .mockResolvedValueOnce(jsonResponse(envelope(REVIEW_SUMMARY_FIXTURE)))
      .mockResolvedValueOnce(jsonResponse(envelope(REVIEW_FIXTURE)));

    await expect(listLineIdentityReviews({
      review_status: 'pending',
      review_type: 'staff_verification',
      page_size: 25,
    })).resolves.toEqual({ items: [REVIEW_FIXTURE], next_cursor: null });
    await expect(getLineIdentityReviewSummary()).resolves.toEqual(REVIEW_SUMMARY_FIXTURE);
    await expect(getLineIdentityReview(71)).resolves.toEqual(REVIEW_FIXTURE);

    expect(vi.mocked(globalThis.fetch).mock.calls.map(([url]) => url)).toEqual([
      '/api/v1/line/identity/reviews?review_status=pending&review_type=staff_verification&page_size=25',
      '/api/v1/line/identity/reviews/summary',
      '/api/v1/line/identity/reviews/71',
    ]);
  });

  it('review decision 固定走 Preview 再 Apply，Apply 攜帶 fingerprint 與 idempotency key', async () => {
    const approved = {
      ...REVIEW_FIXTURE,
      status: 'approved' as const,
      version: 4,
      decision_reason: '人工確認資料無誤',
      reviewed_by_actor_id: 'admin:1',
      reviewed_at: '2026-08-24T10:30:00+08:00',
      outcome: 'created' as const,
      receipt_identity: 'line-review:71:approved',
    };
    globalThis.fetch = vi.fn()
      .mockResolvedValueOnce(jsonResponse(envelope(REVIEW_PREVIEW_FIXTURE)))
      .mockResolvedValueOnce(jsonResponse(envelope(approved)));

    await previewLineIdentityReviewDecision(71, 'approve', {
      expected_version: 3,
      reason: ' 人工確認資料無誤 ',
    });
    await applyLineIdentityReviewDecision(71, 'approve', {
      expected_version: 3,
      idempotency_key: 'review-decision-071',
      reason: ' 人工確認資料無誤 ',
      preview_fingerprint: 'review-preview-fixture-071',
    });

    const [previewUrl, previewOptions] = vi.mocked(globalThis.fetch).mock.calls[0];
    const [applyUrl, applyOptions] = vi.mocked(globalThis.fetch).mock.calls[1];
    expect(previewUrl).toBe('/api/v1/line/identity/reviews/71/approve/preview');
    expect(applyUrl).toBe('/api/v1/line/identity/reviews/71/approve/apply');
    expect(JSON.parse(String(previewOptions?.body))).toEqual({
      expected_version: 3,
      reason: '人工確認資料無誤',
    });
    expect(JSON.parse(String(applyOptions?.body))).toEqual({
      expected_version: 3,
      idempotency_key: 'review-decision-071',
      reason: '人工確認資料無誤',
      preview_fingerprint: 'review-preview-fixture-071',
    });
  });

  it('review 無效 id／decision 與多餘 response 在網路前後均 fail closed', async () => {
    globalThis.fetch = vi.fn();
    await expect(getLineIdentityReview(0)).rejects.toMatchObject({ code: 'REQUEST_INVALID' });
    await expect(previewLineIdentityReviewDecision(71, 'cancel' as never, {
      expected_version: 3,
      reason: '測試非法決定',
    })).rejects.toMatchObject({ code: 'REQUEST_INVALID' });
    expect(globalThis.fetch).not.toHaveBeenCalled();

    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(envelope({
      ...REVIEW_PREVIEW_FIXTURE,
      provider_delivery: 'must-not-pass',
    })));
    await expect(previewLineIdentityReviewDecision(71, 'approve', {
      expected_version: 3,
      reason: '測試嚴格契約',
    })).rejects.toMatchObject({ code: 'CONTRACT_MISMATCH' });
  });

  it('detail 接受 MySQL datetime 經 Pydantic 產生的 local ISO 格式', async () => {
    const localDateTimeBinding = {
      ...BOUND_IDENTITY_FIXTURE,
      updated_at: '2026-08-16T02:30:00',
    };
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(envelope(localDateTimeBinding)));

    const result = await getLineIdentityBinding(FIXTURE_LINE_USER_ID);

    expect(result.updated_at).toBe('2026-08-16T02:30:00');
  });

  it('Preview 使用唯一核准 POST path、無 JSON body 且只發一次', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(envelope(REVOCATION_PREVIEW_FIXTURE)));

    const result = await previewLineIdentityRevocation(FIXTURE_LINE_USER_ID);

    expect(result).toEqual(REVOCATION_PREVIEW_FIXTURE);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    expect(url).toBe(
      `/api/v1/line/identity-bindings/${FIXTURE_LINE_USER_ID}/revocation/preview`
    );
    expect(options?.method).toBe('POST');
    expect(options?.body).toBeUndefined();
  });

  it('Apply 將 trim 後原因與 keys 放在 JSON body，不自行改成 header', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(envelope(REVOCATION_REQUEST_FIXTURE)));

    const result = await applyLineIdentityRevocation(
      FIXTURE_LINE_USER_ID,
      REVOCATION_APPLY_REQUEST_FIXTURE
    );

    expect(result).toEqual(REVOCATION_REQUEST_FIXTURE);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = vi.mocked(globalThis.fetch).mock.calls[0];
    const headers = options?.headers as Record<string, string>;
    expect(url).toBe(
      `/api/v1/line/identity-bindings/${FIXTURE_LINE_USER_ID}/revocation/apply`
    );
    expect(options?.method).toBe('POST');
    expect(JSON.parse(String(options?.body))).toEqual({
      expected_version: 7,
      reason: '客戶已確認解除 LINE 身分綁定',
      idempotency_key: 'line-revoke-idempotency-fixture-001',
      correlation_id: 'line-revoke-correlation-fixture-001',
    });
    expect(headers['Idempotency-Key']).toBeUndefined();
    expect(headers['X-Correlation-ID']).toBeUndefined();
  });

  it('replacement Preview 使用 query parameter，Apply 保留 caller identity 並嚴格解碼', async () => {
    const preview = {
      binding: BOUND_IDENTITY_FIXTURE,
      target_subject_reference: 'CLIENT TARGET/002',
      target_subject_name: '更正客戶乙',
      blockers: [],
    };
    const replaced = {
      ...BOUND_IDENTITY_FIXTURE,
      version: 8,
      subject_reference: 'CLIENT TARGET/002',
      subject_name: '更正客戶乙',
    };
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(envelope(preview)))
      .mockResolvedValueOnce(jsonResponse(envelope(replaced)));

    await expect(
      previewLineIdentityReplacement(FIXTURE_LINE_USER_ID, ' CLIENT TARGET/002 ')
    ).resolves.toEqual(preview);
    await expect(
      applyLineIdentityReplacement(FIXTURE_LINE_USER_ID, {
        expected_version: 7,
        target_subject_reference: ' CLIENT TARGET/002 ',
        reason: ' 綁定到錯誤客戶 ',
        idempotency_key: 'replacement-intent-001',
        correlation_id: 'replacement-correlation-001',
      })
    ).resolves.toEqual(replaced);

    expect(vi.mocked(globalThis.fetch).mock.calls[0][0]).toBe(
      `/api/v1/line/identity-bindings/${FIXTURE_LINE_USER_ID}/replacement/preview?target_subject_reference=CLIENT+TARGET%2F002`
    );
    expect(JSON.parse(String(vi.mocked(globalThis.fetch).mock.calls[1][1]?.body))).toEqual({
      expected_version: 7,
      target_subject_reference: 'CLIENT TARGET/002',
      reason: '綁定到錯誤客戶',
      idempotency_key: 'replacement-intent-001',
      correlation_id: 'replacement-correlation-001',
    });
  });

  it('retry 與 manual-complete 只傳既有 public contract 的 reason', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(envelope(REVOCATION_REQUEST_FIXTURE)));

    await retryLineIdentityRevocation(91, { reason: ' 重新執行安全回復 ' });
    await manualCompleteLineIdentityRevocation(91, { reason: ' 已確認永久失敗 ' });

    const [retryUrl, retryOptions] = vi.mocked(globalThis.fetch).mock.calls[0];
    const [manualUrl, manualOptions] = vi.mocked(globalThis.fetch).mock.calls[1];
    expect(retryUrl).toBe('/api/v1/line/identity-bindings/revocations/91/retry');
    expect(manualUrl).toBe('/api/v1/line/identity-bindings/revocations/91/manual-complete');
    expect(JSON.parse(String(retryOptions?.body))).toEqual({ reason: '重新執行安全回復' });
    expect(JSON.parse(String(manualOptions?.body))).toEqual({ reason: '已確認永久失敗' });
  });

  it('maintenance request id 與空白 replacement target 在網路前 fail closed', async () => {
    globalThis.fetch = vi.fn();

    await expect(
      retryLineIdentityRevocation(0, { reason: '重試' })
    ).rejects.toMatchObject({ code: 'REQUEST_INVALID' });
    await expect(
      previewLineIdentityReplacement(FIXTURE_LINE_USER_ID, '   ')
    ).rejects.toMatchObject({ code: 'REQUEST_INVALID' });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('每次 request 都重新取得 current memory token，不快取舊 token', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(envelope(BOUND_IDENTITY_FIXTURE)));

    await getLineIdentityBinding(FIXTURE_LINE_USER_ID);
    sessionClient.setSession('line-memory-token-b', {
      id: 1,
      username: 'line-operator',
      display_name: 'LINE Operator',
      role: 'admin',
    });
    await getLineIdentityBinding(FIXTURE_LINE_USER_ID);

    const firstHeaders = vi.mocked(globalThis.fetch).mock.calls[0][1]?.headers as Record<
      string,
      string
    >;
    const secondHeaders = vi.mocked(globalThis.fetch).mock.calls[1][1]?.headers as Record<
      string,
      string
    >;
    expect(firstHeaders.Authorization).toBe('Bearer line-memory-token-a');
    expect(secondHeaders.Authorization).toBe('Bearer line-memory-token-b');
  });

  it('缺少 Session 時在送出網路請求前 fail closed', async () => {
    sessionClient.clearSession();
    globalThis.fetch = vi.fn();

    await expect(getLineIdentityBinding(FIXTURE_LINE_USER_ID)).rejects.toMatchObject({
      code: 'UNAUTHENTICATED',
      outcomeUnknown: false,
    });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('接受 Pydantic 可缺省且可為 null 的身分查詢欄位', async () => {
    const minimalBinding = {
      line_user_id: FIXTURE_LINE_USER_ID,
      status: 'bound',
      version: 7,
      subject_type: 'customer',
      subject_reference: 'CLIENT-FIXTURE-001',
      subject_name: '測試客戶甲',
    };
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(envelope(minimalBinding)))
      .mockResolvedValueOnce(jsonResponse(envelope({
        ...REVOCATION_PREVIEW_FIXTURE,
        binding: minimalBinding,
        default_menu_publication_id: undefined,
        provider_menu_id: undefined,
      })));

    const binding = await getLineIdentityBinding(FIXTURE_LINE_USER_ID);
    const preview = await previewLineIdentityRevocation(FIXTURE_LINE_USER_ID);

    expect(binding.updated_at).toBeUndefined();
    expect(binding.revocation_status).toBeUndefined();
    expect(preview.default_menu_publication_id).toBeUndefined();
    expect(preview.provider_menu_id).toBeUndefined();
  });

  it('空白 reason 在送出前 fail closed，網路呼叫為零', async () => {
    globalThis.fetch = vi.fn();

    await expect(
      applyLineIdentityRevocation(FIXTURE_LINE_USER_ID, {
        ...REVOCATION_APPLY_REQUEST_FIXTURE,
        reason: '   ',
      })
    ).rejects.toMatchObject({ code: 'REQUEST_INVALID', outcomeUnknown: false });
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it.each([
    ['missing required', { ...BOUND_IDENTITY_FIXTURE, version: undefined }],
    ['wrong primitive', { ...BOUND_IDENTITY_FIXTURE, version: '7' }],
    ['unknown field', { ...BOUND_IDENTITY_FIXTURE, unexpected: true }],
    ['null violation', { ...BOUND_IDENTITY_FIXTURE, subject_name: null }],
    ['enum drift', { ...BOUND_IDENTITY_FIXTURE, status: 'disabled' }],
  ])('detail 對 %s payload 嚴格拒絕', async (_caseName, invalidData) => {
    globalThis.fetch = vi.fn().mockResolvedValue(jsonResponse(envelope(invalidData)));

    await expect(getLineIdentityBinding(FIXTURE_LINE_USER_ID)).rejects.toMatchObject({
      code: 'CONTRACT_MISMATCH',
      retryable: false,
    });
  });

  it('Preview 拒絕多餘 provider 欄位，Apply 拒絕缺少 actor 欄位', async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          envelope({ ...REVOCATION_PREVIEW_FIXTURE, provider_message: 'must-not-pass' })
        )
      )
      .mockResolvedValueOnce(
        jsonResponse(
          envelope({ ...REVOCATION_REQUEST_FIXTURE, requested_by_actor_id: undefined })
        )
      );

    await expect(
      previewLineIdentityRevocation(FIXTURE_LINE_USER_ID)
    ).rejects.toMatchObject({ code: 'CONTRACT_MISMATCH' });
    await expect(
      applyLineIdentityRevocation(
        FIXTURE_LINE_USER_ID,
        REVOCATION_APPLY_REQUEST_FIXTURE
      )
    ).rejects.toMatchObject({ code: 'CONTRACT_MISMATCH' });
  });

  it('raw detail.code 只做 exact allowlist 映射，不以 message substring 分支或外洩', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: 'line_identity_binding_version_conflict',
            message: 'private line id and provider details must not escape',
          },
        },
        409
      )
    );

    const error = await getLineIdentityBinding(FIXTURE_LINE_USER_ID).catch(
      (caught: unknown) => caught
    );
    expect(error).toBeInstanceOf(LineIdentityClientError);
    expect(error).toMatchObject({
      code: 'CONFLICT',
      domainCode: 'line_identity_binding_version_conflict',
      status: 409,
    });
    expect(String(error)).not.toContain('private line id');
  });

  it('未知 409 code 使用固定安全衝突文案，不保留 raw message', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      jsonResponse(
        {
          detail: {
            code: 'cannot transition LINE binding from revoked to revoked',
            message: 'raw private failure',
          },
        },
        409
      )
    );

    const error = await previewLineIdentityRevocation(FIXTURE_LINE_USER_ID).catch(
      (caught: unknown) => caught
    );
    expect(error).toMatchObject({ code: 'CONFLICT', domainCode: undefined });
    expect(String(error)).not.toContain('raw private failure');
    expect(String(error)).not.toContain('cannot transition');
  });
});
