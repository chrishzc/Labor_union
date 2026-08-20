/**
 * File: line_identity_adapter.test.ts
 * Description: 驗證 LINE 身分展示模型遮罩、解除未完成語意與機密欄位不穿透。
 */
import { describe, expect, it } from 'vitest';
import {
  adaptLineIdentityBinding,
  adaptLineIdentityBindingPage,
  adaptLineIdentityRevocationAccepted,
  adaptLineIdentityRevocationPreview,
  maskLineUserId,
} from '../adapters/line_identity/line_identity_adapter';
import {
  BINDING_PAGE_FIXTURE,
  BLOCKED_REVOCATION_PREVIEW_FIXTURE,
  BOUND_IDENTITY_FIXTURE,
  FIXTURE_LINE_USER_ID,
  REVOCATION_PREVIEW_FIXTURE,
  REVOCATION_REQUEST_FIXTURE,
} from './fixtures/line_identity/line_identity_contract_fixtures';

describe('LINE Identity Adapter（Phase 3A Lane D）', () => {
  it('完整 LINE User ID 只輸出首尾遮罩且不等於原值', () => {
    const masked = maskLineUserId(FIXTURE_LINE_USER_ID);

    expect(masked).toBe('U123••••cdef');
    expect(masked).not.toBe(FIXTURE_LINE_USER_ID);
    expect(masked).not.toContain(FIXTURE_LINE_USER_ID);
  });

  it.each(['', 'U', 'U1', 'U1234'])('短或異常值仍不回傳完整原值：%s', (value) => {
    expect(maskLineUserId(value)).not.toBe(value);
  });

  it('binding row 僅保留展示欄位，不穿透 subject reference 或完整 ID', () => {
    const result = adaptLineIdentityBinding(BOUND_IDENTITY_FIXTURE);
    const serialized = JSON.stringify(result);

    expect(result.statusLabel).toBe('已綁定');
    expect(result.subjectTypeLabel).toBe('客戶');
    expect(result.maskedLineUserId).toBe('U123••••cdef');
    expect(serialized).not.toContain(FIXTURE_LINE_USER_ID);
    expect(serialized).not.toContain(BOUND_IDENTITY_FIXTURE.subject_reference);
  });

  it('page adapter 保留 server pagination，不自行推導總數', () => {
    const result = adaptLineIdentityBindingPage(BINDING_PAGE_FIXTURE);

    expect(result.total).toBe(1);
    expect(result.page).toBe(1);
    expect(result.pageSize).toBe(25);
    expect(result.items).toHaveLength(1);
  });

  it('Preview 只呈現 publication 存在與安全 blocker，不呈現 provider ID', () => {
    const ready = adaptLineIdentityRevocationPreview(REVOCATION_PREVIEW_FIXTURE);
    const blocked = adaptLineIdentityRevocationPreview(
      BLOCKED_REVOCATION_PREVIEW_FIXTURE
    );

    expect(ready.defaultMenuPublished).toBe(true);
    expect(ready.hasBlockers).toBe(false);
    expect(blocked.defaultMenuPublished).toBe(false);
    expect(blocked.blockers).toEqual(['預設 Rich Menu 尚未發布']);
    expect(JSON.stringify(ready)).not.toContain(
      String(REVOCATION_PREVIEW_FIXTURE.provider_menu_id)
    );
  });

  it('未知 blocker 不將 raw server 字串送入 presentation', () => {
    const result = adaptLineIdentityRevocationPreview({
      ...REVOCATION_PREVIEW_FIXTURE,
      blockers: ['provider-secret-in-blocker'],
    });

    expect(result.blockers).toEqual(['伺服器回報未識別的解除阻擋原因']);
    expect(JSON.stringify(result)).not.toContain('provider-secret-in-blocker');
  });

  it('pending apply result 明確表示申請受理而非已解除', () => {
    const result = adaptLineIdentityRevocationAccepted(REVOCATION_REQUEST_FIXTURE);

    expect(result.status).toBe('pending_menu_reset');
    expect(result.notice).toContain('申請已受理');
    expect(result.notice).toContain('重新查詢');
    expect(result.notice).not.toContain('已解除完成');
  });

  it.each(['completed', 'manual_completed'] as const)(
    'Apply 回傳 %s 時仍只表示申請已受理，完成必須等待重新查詢',
    (status) => {
      const result = adaptLineIdentityRevocationAccepted({
        ...REVOCATION_REQUEST_FIXTURE,
        status,
      });

      expect(result.notice).toContain('申請已受理');
      expect(result.notice).toContain('重新查詢');
      expect(result.notice).not.toContain('身分解除完成');
      expect('completionObserved' in result).toBe(false);
    }
  );

  it('Apply adapter 不輸出 full LINE ID、provider、actor、reason 或 raw message', () => {
    const requestWithPrivateFailure = {
      ...REVOCATION_REQUEST_FIXTURE,
      last_error_code: 'provider_failed',
      last_error_message: 'private raw provider response',
    };

    const serialized = JSON.stringify(
      adaptLineIdentityRevocationAccepted(requestWithPrivateFailure)
    );
    expect(serialized).not.toContain(FIXTURE_LINE_USER_ID);
    expect(serialized).not.toContain(REVOCATION_REQUEST_FIXTURE.provider_menu_id);
    expect(serialized).not.toContain(REVOCATION_REQUEST_FIXTURE.requested_by_actor_id);
    expect(serialized).not.toContain(REVOCATION_REQUEST_FIXTURE.reason);
    expect(serialized).not.toContain('private raw provider response');
  });
});
