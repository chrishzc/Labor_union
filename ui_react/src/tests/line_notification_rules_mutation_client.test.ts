/**
 * File: line_notification_rules_mutation_client.test.ts
 * Description: 驗證通知規則 Preview、Save、Delete 的路徑、fresh Session、body 與 fail-closed 解碼。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  deleteLineNotificationRule,
  previewLineNotificationRules,
  saveLineNotificationRules,
} from '../api/line_notification_rules/line_notification_rules_mutation_client';
import {
  LineNotificationRulesMutationRequestError,
  LineNotificationRulesMutationUnauthenticatedError,
} from '../api/line_notification_rules/line_notification_rules_mutation_errors';

const FINGERPRINT = 'a'.repeat(64);
const DEFINITION = {
  rules: [{
    id: 'deposit_notice',
    event_code: 'deposit_confirmed' as const,
    recipient_selector: 'client' as const,
    template_id: 'deposit_template',
    enabled: true,
    schedule: { kind: 'immediate' as const },
    frequency: { kind: 'once' as const },
    predicates: [],
  }],
};

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setSession(token: string): void {
  sessionClient.setSession(token, {
    id: 61,
    username: 'line-rule-test',
    display_name: 'LINE 規則測試',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

describe('LINE notification rules mutation client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setSession('line-rule-token-a');
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('依序呼叫 Preview、PUT Save 與帶 body 的 DELETE，逐次使用 fresh Session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({
        success: true,
        message: 'Success',
        data: {
          before_revision: 3,
          resulting_revision: 4,
          definition: DEFINITION,
          fingerprint: FINGERPRINT,
        },
        error: null,
      }))
      .mockResolvedValueOnce(response({
        success: true,
        message: 'Success',
        data: {
          revision: 4,
          preview_fingerprint: FINGERPRINT,
          cancelled_intent_count: 1,
          cancelled_task_count: 2,
        },
        error: null,
      }))
      .mockResolvedValueOnce(response({
        success: true,
        message: 'Success',
        data: {
          rule_id: 'deposit_notice',
          revision: 5,
          preview_fingerprint: FINGERPRINT,
          cancelled_intent_count: 0,
          cancelled_task_count: 1,
        },
        error: null,
      }));
    globalThis.fetch = fetchMock;

    await previewLineNotificationRules({ expected_revision: 3, definition: DEFINITION });
    setSession('line-rule-token-b');
    await saveLineNotificationRules({
      expected_revision: 3,
      preview_fingerprint: FINGERPRINT,
      definition: DEFINITION,
      reason: '  核准通知規則更新  ',
      idempotency_key: 'save-idem-1',
      correlation_id: 'save-corr-1',
    });
    await deleteLineNotificationRule('deposit_notice', {
      expected_revision: 4,
      preview_fingerprint: FINGERPRINT,
      reason: '核准刪除規則',
      idempotency_key: 'delete-idem-1',
      correlation_id: 'delete-corr-1',
    });

    expect(fetchMock.mock.calls.map((call) => [call[0], call[1]?.method])).toEqual([
      ['/api/v1/line/notification-rules/preview', 'POST'],
      ['/api/v1/line/notification-rules', 'PUT'],
      ['/api/v1/line/notification-rules/deposit_notice', 'DELETE'],
    ]);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe(
      'Bearer line-rule-token-a'
    );
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe(
      'Bearer line-rule-token-b'
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body)).reason).toBe(
      '核准通知規則更新'
    );
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toMatchObject({
      expected_revision: 4,
      reason: '核准刪除規則',
      idempotency_key: 'delete-idem-1',
      correlation_id: 'delete-corr-1',
    });
  });

  it('未登入、非法 rule id 與重複 definition 在網路請求前 fail closed', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();
    await expect(previewLineNotificationRules({
      expected_revision: 3,
      definition: DEFINITION,
    })).rejects.toBeInstanceOf(LineNotificationRulesMutationUnauthenticatedError);

    setSession('line-rule-token-a');
    await expect(deleteLineNotificationRule('../bad', {
      expected_revision: 3,
      preview_fingerprint: FINGERPRINT,
      reason: '刪除',
      idempotency_key: 'delete-idem',
      correlation_id: 'delete-corr',
    })).rejects.toBeInstanceOf(LineNotificationRulesMutationRequestError);
    await expect(previewLineNotificationRules({
      expected_revision: 3,
      definition: { rules: [DEFINITION.rules[0], DEFINITION.rules[0]] },
    })).rejects.toBeInstanceOf(LineNotificationRulesMutationRequestError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('成功回應含 extra 欄位時拒絕 raw payload', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      success: true,
      message: 'Success',
      data: {
        before_revision: 3,
        resulting_revision: 4,
        definition: DEFINITION,
        fingerprint: FINGERPRINT,
        provider_secret: 'must-not-pass',
      },
      error: null,
    }));

    await expect(previewLineNotificationRules({
      expected_revision: 3,
      definition: DEFINITION,
    })).rejects.toMatchObject({
      code: 'line_notification_rule_contract_mismatch',
    });
  });
});
