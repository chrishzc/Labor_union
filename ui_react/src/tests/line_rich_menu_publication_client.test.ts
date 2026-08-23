/**
 * File: line_rich_menu_publication_client.test.ts
 * Description: 驗證 Rich Menu 發布三個 POST 契約、fresh Session、嚴格解碼與請求前 fail closed。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  previewLineRichMenuPublication,
  publishLineRichMenu,
  retryLineRichMenuPublication,
} from '../api/line_rich_menu_publication/line_rich_menu_publication_client';
import {
  LineRichMenuPublicationError,
  LineRichMenuPublicationRequestError,
  LineRichMenuPublicationUnauthenticatedError,
} from '../api/line_rich_menu_publication/line_rich_menu_publication_errors';

const FINGERPRINT = 'a'.repeat(64);

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setSession(token: string): void {
  sessionClient.setSession(token, {
    id: 52,
    username: 'line-rich-menu-test',
    display_name: 'Rich Menu 測試',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

describe('Rich Menu publication client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setSession('line-rich-menu-token-a');
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('依序呼叫 Preview、publish queue 與 retry，逐次使用 fresh Session', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({
        success: true,
        message: '已確認目前版本的預覽，可再次確認後套用',
        data: { preview_id: 41, config_revision: '7', config_fingerprint: FINGERPRINT },
        error: null,
      }))
      .mockResolvedValueOnce(response({
        success: true,
        message: 'Rich Menu 發布工作已建立',
        data: { id: 19, menu_definition_id: 'staff-menu', configuration_revision: 7, status: 'queued' },
        error: null,
      }, 202))
      .mockResolvedValueOnce(response({
        success: true,
        message: '發布工作已重新排入',
        data: { id: 19, menu_definition_id: 'staff-menu', configuration_revision: 7, status: 'queued' },
        error: null,
      }));
    globalThis.fetch = fetchMock;

    await previewLineRichMenuPublication('staff-menu');
    setSession('line-rich-menu-token-b');
    await publishLineRichMenu('staff-menu', {
      preview_id: 41,
      reason: '  核准角色選單更新  ',
      idempotency_key: 'publish-idem-1',
      correlation_id: 'publish-corr-1',
    });
    await retryLineRichMenuPublication(19, {
      reason: '重新排入已確認的失敗工作',
      idempotency_key: 'retry-idem-1',
      correlation_id: 'retry-corr-1',
    });

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/line/rich-menus/staff-menu/publish-preview',
      '/api/v1/line/rich-menus/staff-menu/publish',
      '/api/v1/line/rich-menus/publications/19/retry',
    ]);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe(
      'Bearer line-rich-menu-token-a'
    );
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe(
      'Bearer line-rich-menu-token-b'
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({
      preview_id: 41,
      reason: '核准角色選單更新',
      idempotency_key: 'publish-idem-1',
      correlation_id: 'publish-corr-1',
    });
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual({
      reason: '重新排入已確認的失敗工作',
      idempotency_key: 'retry-idem-1',
      correlation_id: 'retry-corr-1',
    });
  });

  it('未登入或不合法識別值時在網路請求前 fail closed', async () => {
    globalThis.fetch = vi.fn();
    sessionClient.clearSession();
    await expect(previewLineRichMenuPublication('staff-menu')).rejects.toBeInstanceOf(
      LineRichMenuPublicationUnauthenticatedError
    );
    setSession('line-rich-menu-token-a');
    await expect(retryLineRichMenuPublication(0, {
      reason: '重試',
      idempotency_key: 'retry-idem',
      correlation_id: 'retry-corr',
    })).rejects.toBeInstanceOf(LineRichMenuPublicationRequestError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('成功回應包含 extra 欄位或未知狀態時拒絕 raw payload', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce(response({
      success: true,
      message: '已確認目前版本的預覽，可再次確認後套用',
      data: {
        preview_id: 41,
        config_revision: '7',
        config_fingerprint: FINGERPRINT,
        provider_id: 'should-not-pass',
      },
      error: null,
    })).mockResolvedValueOnce(response({
      success: true,
      message: 'Rich Menu 發布工作已建立',
      data: {
        id: 19,
        menu_definition_id: 'staff-menu',
        configuration_revision: 7,
        status: 'provider_success',
      },
      error: null,
    }));

    await expect(previewLineRichMenuPublication('staff-menu')).rejects.toMatchObject({
      code: 'line_rich_menu_publication_contract_mismatch',
    });
    await expect(publishLineRichMenu('staff-menu', {
      preview_id: 41,
      reason: '核准發布',
      idempotency_key: 'publish-idem',
      correlation_id: 'publish-corr',
    })).rejects.toBeInstanceOf(LineRichMenuPublicationError);
  });
});
