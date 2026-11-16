/**
 * File: line_rules_query_flow.test.tsx
 * Description: 驗證通知工作台載入通知規則、顯示文案與提交唯讀手機預覽的接線。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { LineConfigurationQueryClient } from '../../../../../../api/line_configuration/line_configuration_query_client';
import type { LineNotificationRulesCatalog } from '../../../../../../api/line_configuration/line_configuration_query_schemas';
import type { LineIdentityClient } from '../../../../../../api/line_identity/line_identity_client';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from '../../../../../fixtures/line_configuration_query_fixtures';

function dependencies(rules: LineNotificationRulesCatalog = LINE_NOTIFICATION_RULES_CATALOG_FIXTURE): {
  identity: Pick<LineIdentityClient, 'listBindings' | 'getBinding' | 'previewRevocation' | 'applyRevocation'>;
  configuration: LineConfigurationQueryClient;
} {
  return {
    identity: { listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE), getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE), previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE), applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE) },
    configuration: { getNotificationRules: vi.fn().mockResolvedValue(rules), getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE), listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE), getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE) },
  };
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionClient.clearSession(); window.history.replaceState(null, '', window.location.pathname); });

function response(data: unknown): Response {
  return new Response(JSON.stringify({ success: true, data }), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('LINE 通知工作台接線', () => {
  it('進入工作台只查一次規則，以已載入規則的文案產生手機預覽', async () => {
    sessionClient.setSession('synthetic-line-rules-session', { id: 7, username: 'line-rules-test', display_name: '測試管理員', role: 'admin' });
    const catalogPath = '/api/v1/line/message-previews/catalog';
    const templatePath = '/api/v1/line/notification-rules/deposit_notice/message-template';
    const previewPath = '/api/v1/line/message-previews/preview';
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      switch (String(input)) {
        case catalogPath:
          return response([{ id: 'deposit_notice', template_id: 'deposit_message', name: '訂金確認', format: 'text', requires_case: false, requires_staff: false, builtin: false, allows_draft: true }]);
        case templatePath:
          return response({ rule_id: 'deposit_notice', template_id: 'deposit_message', name: '訂金確認',
            content: '訂金確認通知', revision: 1, variables: [], sample_preview: '訂金確認通知' });
        case previewPath:
          return response({ status: 'ready', format: 'text', text: '訂金確認通知', note: '', bubbles: [], facts: [] });
        default:
          throw new Error(`Unexpected request ${options?.method} ${String(input)}`);
      }
    });
    vi.stubGlobal('fetch', fetchSpy);
    const { identity, configuration } = dependencies();
    render(<LineManagementPage scope="notifications" lineIdentity={identity} lineConfiguration={configuration} />);
    const flow = within(screen.getByRole('region', { name: 'LINE 流程圖' }));
    fireEvent.click(await flow.findByRole('button', { name: '其他通知' }));
    fireEvent.click(flow.getByRole('button', { name: '未歸入流程' }));
    fireEvent.click(flow.getByRole('button', { name: '編輯訂金確認內容' }));
    expect(screen.queryByRole('button', { name: '編輯新好友歡迎訊息內容' })).not.toBeInTheDocument();
    expect(configuration.getNotificationRules).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('FLOW-04')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('訂金確認通知');
    expect(screen.queryByRole('button', { name: '發送設定' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '公版預覽資料' })).not.toBeInTheDocument();
    expect(screen.queryByText('系統唯一規則識別碼：deposit_notice')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /儲存並發布|手動重播/ })).not.toBeInTheDocument();
    const phone = within(screen.getByRole('complementary', { name: 'LINE 對話預覽' }));
    expect(await phone.findByText('訂金確認通知')).toBeVisible();
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    expect(fetchSpy).toHaveBeenCalledWith(catalogPath, expect.objectContaining({ method: 'GET' }));
    expect(fetchSpy).toHaveBeenCalledWith(templatePath, expect.objectContaining({ method: 'GET' }));
    const preview = fetchSpy.mock.calls.find(([input]) => String(input) === previewPath)?.[1];
    expect(preview?.method).toBe('POST');
    expect(JSON.parse(String(preview?.body))).toEqual({ id: 'deposit_notice', data_source: 'sample', content: '訂金確認通知' });
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    fireEvent.click(flow.getByRole('button', { name: '編輯訂金確認內容' }));
    expect(screen.getByRole('textbox', { name: '通知內容' })).toHaveValue('訂金確認通知');
    expect(configuration.getNotificationRules).toHaveBeenCalledTimes(1);
  });

  it('revision 0 的空 definition 顯示真實空狀態而不是 mock 規則或歡迎詞', async () => {
    const empty = { revision: 0, definition: {} } as const;
    const { identity, configuration } = dependencies(empty);
    const fetchSpy = vi.fn().mockResolvedValue(response([]));
    vi.stubGlobal('fetch', fetchSpy);
    render(<LineManagementPage scope="notifications" lineIdentity={identity} lineConfiguration={configuration} />);
    await waitFor(() => expect(screen.queryByText('正在載入通知內容…')).not.toBeInTheDocument());
    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/line/message-previews/catalog', expect.objectContaining({ method: 'GET' }));
    expect(document.querySelectorAll('[data-notification-id]')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: '編輯新好友歡迎訊息內容' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '編輯訂金確認內容' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Current revision|revision：0/i)).not.toBeInTheDocument();
    expect(screen.queryByText('FLOW-13')).not.toBeInTheDocument();
  });
});
