/**
 * File: line_configuration_query_client.test.ts
 * Description: 驗證 LINE 設定四個 GET 白名單、fresh Session、Abort 與嚴格 fail-closed 解碼。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  LINE_CONFIGURATION_QUERY_TIMEOUT_MS,
  getLineNotificationRules,
  getLineRichMenuConfiguration,
  getLineRichMenuPublication,
  listLineRichMenuPublications,
} from '../api/line_configuration/line_configuration_query_client';
import {
  LineConfigurationQueryContractError,
  LineConfigurationQueryRequestError,
  LineConfigurationQueryUnauthenticatedError,
} from '../api/line_configuration/line_configuration_query_errors';
import {
  LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE,
  LINE_RICH_MENU_CONFIGURATION_ENVELOPE_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_ENVELOPE_FIXTURE,
  LINE_RICH_MENU_PUBLICATION_PAGE_ENVELOPE_FIXTURE,
} from './fixtures/line_configuration_query_fixtures';

function response(payload: object, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function setSession(token: string): void {
  sessionClient.setSession(token, {
    id: 52,
    username: 'line-configuration-test',
    display_name: 'LINE 設定測試',
    role: 'operator',
    linked_line_user_id: null,
    capabilities: [],
    is_root: false,
    access_control_version: 1,
  });
}

describe('LINE configuration query client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setSession('line-query-token-a');
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('只呼叫四個 GET 白名單，帶入 fresh bearer、Abort 與固定 request budget', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE))
      .mockResolvedValueOnce(response(LINE_RICH_MENU_CONFIGURATION_ENVELOPE_FIXTURE))
      .mockResolvedValueOnce(response(LINE_RICH_MENU_PUBLICATION_PAGE_ENVELOPE_FIXTURE))
      .mockResolvedValueOnce(response(LINE_RICH_MENU_PUBLICATION_ENVELOPE_FIXTURE));
    globalThis.fetch = fetchMock;
    const controller = new AbortController();

    await getLineNotificationRules({ signal: controller.signal, headers: { Authorization: 'Bearer caller', 'X-Test': 'yes' } });
    setSession('line-query-token-b');
    await getLineRichMenuConfiguration();
    await listLineRichMenuPublications();
    await getLineRichMenuPublication(19);

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      '/api/v1/line/notification-rules',
      '/api/v1/line/configurations/rich_menus',
      '/api/v1/line/rich-menus/publications?page=1&page_size=25',
      '/api/v1/line/rich-menus/publications/19',
    ]);
    for (const call of fetchMock.mock.calls) {
      expect(call[1]?.method).toBe('GET');
      expect(call[1]?.body).toBeUndefined();
      expect(call[1]?.signal).toBeInstanceOf(AbortSignal);
    }
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer line-query-token-a');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-Test')).toBe('yes');
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('Authorization')).toBe('Bearer line-query-token-b');
    expect(LINE_CONFIGURATION_QUERY_TIMEOUT_MS).toBe(10_000);
  });

  it('未登入或不合法 publication id 時在網路請求前 fail closed', async () => {
    sessionClient.clearSession();
    globalThis.fetch = vi.fn();
    await expect(getLineNotificationRules()).rejects.toBeInstanceOf(LineConfigurationQueryUnauthenticatedError);
    setSession('line-query-token-a');
    await expect(getLineRichMenuPublication(0)).rejects.toBeInstanceOf(LineConfigurationQueryRequestError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('發布紀錄接受明確頁碼，且不合法分頁參數在網路前 fail closed', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(response(LINE_RICH_MENU_PUBLICATION_PAGE_ENVELOPE_FIXTURE));
    await listLineRichMenuPublications({ page: 2, pageSize: 25 });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/api/v1/line/rich-menus/publications?page=2&page_size=25',
      expect.objectContaining({ method: 'GET' }),
    );
    vi.mocked(globalThis.fetch).mockClear();
    await expect(listLineRichMenuPublications({ page: 0 })).rejects.toBeInstanceOf(LineConfigurationQueryRequestError);
    await expect(listLineRichMenuPublications({ pageSize: 1.5 })).rejects.toBeInstanceOf(LineConfigurationQueryRequestError);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('schema drift、missing、extra、null 與未知 enum 一律 unavailable，不傳遞 raw payload', async () => {
    const invalid = [
      { ...LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE, data: { ...LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE.data, revision: null } },
      { ...LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE, data: { ...LINE_NOTIFICATION_RULES_ENVELOPE_FIXTURE.data, unexpected: true } },
      { ...LINE_RICH_MENU_CONFIGURATION_ENVELOPE_FIXTURE, data: { ...LINE_RICH_MENU_CONFIGURATION_ENVELOPE_FIXTURE.data, kind: 'other' } },
    ];
    globalThis.fetch = vi.fn().mockResolvedValue(response(invalid[0]));
    await expect(getLineNotificationRules()).rejects.toBeInstanceOf(LineConfigurationQueryContractError);
    for (const payload of invalid.slice(1)) {
      globalThis.fetch = vi.fn().mockResolvedValue(response(payload));
      await expect(getLineRichMenuConfiguration()).rejects.toBeInstanceOf(LineConfigurationQueryContractError);
    }
    globalThis.fetch = vi.fn().mockResolvedValue(response({ ...LINE_RICH_MENU_PUBLICATION_ENVELOPE_FIXTURE, data: { ...LINE_RICH_MENU_PUBLICATION_ENVELOPE_FIXTURE.data, status: 'provider_success' } }));
    await expect(getLineRichMenuPublication(19)).rejects.toBeInstanceOf(LineConfigurationQueryContractError);
  });

  it('unexpected fetch failure 不會被吞掉或轉成假成功', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('unexpected fetch'));
    await expect(getLineNotificationRules()).rejects.toMatchObject({
      code: 'line_configuration_query_network',
      retryable: true,
    });
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});
