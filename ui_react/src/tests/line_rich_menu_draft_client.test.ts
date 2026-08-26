/**
 * File: line_rich_menu_draft_client.test.ts
 * Description: 驗證 Rich Menu 草稿專用 Query、Preview、Apply 的 typed 路徑與 fail-closed 解碼。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  LineConfigurationQueryContractError,
  LineConfigurationQueryUnauthenticatedError,
} from '../api/line_configuration/line_configuration_query_errors';
import { lineRichMenuDraftClient } from '../api/line_rich_menu_draft/line_rich_menu_draft_client';
import type {
  RichMenuDraftApplyRequest,
  RichMenuDraftDefinition,
  RichMenuDraftPreviewRequest,
} from '../api/line_rich_menu_draft/line_rich_menu_draft_schemas';

const FINGERPRINT = 'a'.repeat(64);

const DEFINITION: RichMenuDraftDefinition = {
  version: 4,
  menus: [{
    id: 'customer_menu',
    name: '客戶服務選單',
    audience_role: 'customer',
    enabled: true,
    selected: true,
    set_as_default: true,
    chat_bar_text: '服務選單',
    buttons: [
      {
        id: 'message_button',
        label: '聯絡客服',
        bounds: { x: 0, y: 0, width: 625, height: 843 },
        action: { type: 'message', text: '我要聯絡客服' },
      },
      {
        id: 'uri',
        label: '官方網站',
        bounds: { x: 625, y: 0, width: 625, height: 843 },
        action: { type: 'uri', uri: 'https://example.test/help', uri_source: 'literal' },
      },
      {
        id: 'postback_button',
        label: '案件進度',
        bounds: { x: 1250, y: 0, width: 625, height: 843 },
        action: { type: 'postback', data: 'case_progress' },
      },
      {
        id: 'switch_button',
        label: '切換選單',
        bounds: { x: 1875, y: 0, width: 625, height: 843 },
        action: { type: 'richmenuswitch', rich_menu_alias_id: 'customer-menu' },
      },
    ],
  }],
};

const QUERY_DATA = {
  kind: 'rich_menus' as const,
  revision: 4,
  definition: DEFINITION,
  publication_locks: [{
    menu_definition_id: 'customer_menu', configuration_revision: 4,
    state: 'editable' as const, readonly_reason: null,
  }],
};

const QUERY_ENVELOPE = {
  success: true as const,
  message: '草稿查詢成功',
  data: QUERY_DATA,
  error: null,
};

const PREVIEW_REQUEST: RichMenuDraftPreviewRequest = {
  expected_revision: 4,
  definition: DEFINITION,
};

const APPLY_REQUEST: RichMenuDraftApplyRequest = {
  ...PREVIEW_REQUEST,
  preview_fingerprint: FINGERPRINT,
  reason: '更新客戶選單顯示名稱',
  idempotency_key: 'rich-menu-draft-apply-1',
  correlation_id: 'rich-menu-draft-correlation-1',
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setSession(token: string): void {
  sessionClient.setSession(token, {
    id: 52,
    username: 'rich-menu-draft-test',
    display_name: 'Rich Menu 草稿測試',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

function previewEnvelope() {
  return {
    success: true as const,
    message: '預覽成功',
    data: {
      before_revision: 4,
      resulting_revision: 5,
      normalized_definition: DEFINITION,
      preview_fingerprint: FINGERPRINT,
    },
    error: null,
  };
}

function applyEnvelope() {
  return {
    success: true as const,
    message: '草稿已套用',
    data: {
      receipt: {
        outcome: 'created' as const,
        committed_revision: 5,
        receipt_reference: 'line-rich-menu-draft-receipt-5',
      },
      readback: {
        kind: 'rich_menus' as const,
        revision: 5,
        definition: DEFINITION,
        publication_locks: [{
          menu_definition_id: 'customer_menu', configuration_revision: 5,
          state: 'editable' as const, readonly_reason: null,
        }],
      },
    },
    error: null,
  };
}

describe('Rich Menu draft client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setSession('line-rich-menu-draft-token-a');
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('只呼叫 dedicated GET/POST/PUT draft paths，不呼叫 generic configuration 或 provider endpoint', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(QUERY_ENVELOPE))
      .mockResolvedValueOnce(response(previewEnvelope()))
      .mockResolvedValueOnce(response(applyEnvelope()));
    globalThis.fetch = fetchMock;
    const controller = new AbortController();

    await lineRichMenuDraftClient.query({ signal: controller.signal, baseUrl: 'https://draft.test' });
    setSession('line-rich-menu-draft-token-b');
    await lineRichMenuDraftClient.preview(PREVIEW_REQUEST, { baseUrl: 'https://draft.test' });
    await lineRichMenuDraftClient.apply(APPLY_REQUEST, { baseUrl: 'https://draft.test' });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      'https://draft.test/api/v1/line/rich-menus/draft',
      'https://draft.test/api/v1/line/rich-menus/draft/preview',
      'https://draft.test/api/v1/line/rich-menus/draft',
    ]);
    expect(fetchMock.mock.calls.map((call) => call[1]?.method)).toEqual(['GET', 'POST', 'PUT']);
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual(PREVIEW_REQUEST);
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual(APPLY_REQUEST);
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe(
      'Bearer line-rich-menu-draft-token-a'
    );
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe(
      'Bearer line-rich-menu-draft-token-b'
    );
    expect(fetchMock.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it('解碼四種 strict action union，並保留 Preview normalized definition 與 Apply receipt/readback', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(QUERY_ENVELOPE))
      .mockResolvedValueOnce(response(previewEnvelope()))
      .mockResolvedValueOnce(response(applyEnvelope()));
    globalThis.fetch = fetchMock;

    const queried = await lineRichMenuDraftClient.query();
    const actions = queried.definition.menus[0].buttons.map((button) => button.action.type);
    expect(actions).toEqual(['message', 'uri', 'postback', 'richmenuswitch']);
    const preview = await lineRichMenuDraftClient.preview(PREVIEW_REQUEST);
    expect(preview).toMatchObject({ before_revision: 4, resulting_revision: 5, preview_fingerprint: FINGERPRINT });
    const applied = await lineRichMenuDraftClient.apply(APPLY_REQUEST);
    expect(applied.receipt).toEqual({
      outcome: 'created',
      committed_revision: 5,
      receipt_reference: 'line-rich-menu-draft-receipt-5',
    });
    expect(applied.readback.revision).toBe(5);
  });

  it('action discriminator 缺少必要欄位、未知 enum 或帶 extra 欄位時拒絕 raw payload', async () => {
    const invalidActions = [
      { type: 'message' },
      { type: 'unknown', text: '不應接受' },
      { type: 'postback', data: 'case_progress', unexpected: true },
    ];

    for (const action of invalidActions) {
      const invalidPayload = {
        ...QUERY_ENVELOPE,
        data: {
          ...QUERY_DATA,
          definition: {
            ...DEFINITION,
            menus: [{
              ...DEFINITION.menus[0],
              buttons: [{ ...DEFINITION.menus[0].buttons[0], action }],
            }],
          },
        },
      };
      globalThis.fetch = vi.fn().mockResolvedValue(response(invalidPayload));
      await expect(lineRichMenuDraftClient.query()).rejects.toBeInstanceOf(LineConfigurationQueryContractError);
    }
  });

  it('缺少管理員 token 或傳輸失敗時在請求／資料成功前 fail closed', async () => {
    const fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    sessionClient.clearSession();
    await expect(lineRichMenuDraftClient.query()).rejects.toBeInstanceOf(
      LineConfigurationQueryUnauthenticatedError
    );
    expect(fetchMock).not.toHaveBeenCalled();

    setSession('line-rich-menu-draft-token-a');
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('draft network unavailable'));
    await expect(lineRichMenuDraftClient.preview(PREVIEW_REQUEST)).rejects.toMatchObject({
      code: 'line_configuration_query_network',
      retryable: true,
    });
  });

  it('已知草稿驗證、stale 與 fingerprint 錯誤顯示安全業務原因，不穿透 raw backend message', async () => {
    const cases = [
      ['line_rich_menu_draft_invalid', '按鈕動作內容不符合規則；請確認 LIFF 入口、HTTPS 網址格式，以及訊息、資料或選單代號長度。'],
      ['line_rich_menu_draft_revision_stale', 'Rich Menu 草稿已被更新，請重新整理後再試。'],
      ['line_configuration_revision_conflict', 'Rich Menu 草稿版本已變更，請重新整理後再試。'],
      ['line_rich_menu_draft_preview_fingerprint_mismatch', '預覽內容已過期或變更，請重新預覽並確認。'],
      ['line_rich_menu_media_asset_missing', '選取的背景圖已不存在，請重新選擇。'],
      ['line_rich_menu_media_asset_owner_conflict', '選取的背景圖不屬於目前選單，請重新選擇。'],
      ['line_rich_menu_media_asset_deleted', '選取的背景圖已刪除，請重新選擇。'],
      ['line_rich_menu_media_asset_digest_conflict', '選取的背景圖內容已變更，請重新選擇。'],
      ['line_rich_menu_media_asset_version_conflict', '選取的背景圖版本已變更，請重新選擇。'],
      ['line_rich_menu_media_asset_size_conflict', '選取的背景圖尺寸不符合目前選單，請重新選擇。'],
    ] as const;

    for (const [code, message] of cases) {
      globalThis.fetch = vi.fn().mockResolvedValue(response({
        detail: {
          error: {
            category: 'validation', code, message: 'raw backend validation detail',
            field_errors: [], domain_blockers: [], retryable: false,
            correlation_id: 'line-rich-menu-draft-test', current_version: null,
          },
        },
      }, 422));
      await expect(lineRichMenuDraftClient.preview(PREVIEW_REQUEST)).rejects.toMatchObject({
        code: 'line_configuration_query_request_invalid', status: 422, retryable: false, message,
      });
    }
  });

  it('成功 envelope 的 missing、extra 或 null 欄位一律 contract mismatch', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...QUERY_ENVELOPE,
      data: { ...QUERY_DATA, unexpected: true },
    }));
    await expect(lineRichMenuDraftClient.query()).rejects.toBeInstanceOf(LineConfigurationQueryContractError);

    globalThis.fetch = vi.fn().mockResolvedValue(response({
      success: true,
      message: '預覽成功',
      data: { ...previewEnvelope().data, preview_fingerprint: null },
      error: null,
    }));
    await expect(lineRichMenuDraftClient.preview(PREVIEW_REQUEST)).rejects.toBeInstanceOf(
      LineConfigurationQueryContractError
    );

    globalThis.fetch = vi.fn().mockResolvedValue(response({
      ...applyEnvelope(),
      data: { ...applyEnvelope().data, receipt: { ...applyEnvelope().data.receipt, unexpected: true } },
    }));
    await expect(lineRichMenuDraftClient.apply(APPLY_REQUEST)).rejects.toBeInstanceOf(
      LineConfigurationQueryContractError
    );
  });

  it('publication lock 缺失、未知狀態、revision mismatch 或 business reason 漂移時 fail closed', async () => {
    const invalidLocks = [
      [],
      [{ ...QUERY_DATA.publication_locks[0], state: 'unknown' }],
      [{ ...QUERY_DATA.publication_locks[0], configuration_revision: 3 }],
      [{ ...QUERY_DATA.publication_locks[0], state: 'processing', readonly_reason: null }],
    ];

    for (const publicationLocks of invalidLocks) {
      globalThis.fetch = vi.fn().mockResolvedValue(response({
        ...QUERY_ENVELOPE,
        data: { ...QUERY_DATA, publication_locks: publicationLocks },
      }));
      await expect(lineRichMenuDraftClient.query()).rejects.toBeInstanceOf(
        LineConfigurationQueryContractError
      );
    }
  });
});
