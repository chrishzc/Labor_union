/**
 * File: line_rules_query_flow.test.tsx
 * Description: 驗證通知規則只在頁籤啟用時查詢，並同時呈現真實 catalog 與 typed mutation 維護區。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../../../../../../api/customer_service/customer_service_client';
import type { LineConfigurationQueryClient } from '../../../../../../api/line_configuration/line_configuration_query_client';
import type { LineNotificationRulesCatalog } from '../../../../../../api/line_configuration/line_configuration_query_schemas';
import type { LineIdentityClient } from '../../../../../../api/line_identity/line_identity_client';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from '../../../../../fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from '../../../../../fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from '../../../../../fixtures/line_configuration_query_fixtures';

function dependencies(rules: LineNotificationRulesCatalog = LINE_NOTIFICATION_RULES_CATALOG_FIXTURE): {
  customer: CustomerServiceClient;
  identity: Pick<LineIdentityClient, 'listBindings' | 'getBinding' | 'previewRevocation' | 'applyRevocation'>;
  configuration: LineConfigurationQueryClient;
} {
  return {
    customer: { getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE), listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE), getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE), previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE), applyResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE) },
    identity: { listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE), getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE), previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE), applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE) },
    configuration: { getNotificationRules: vi.fn().mockResolvedValue(rules), getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE), listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE), getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE) },
  };
}

const onboardingClient = {
  get: vi.fn().mockResolvedValue({ template_id: 'customer_onboarding_welcome', content: '測試歡迎內容', revision: 1, variables: [], sample_preview: '測試歡迎內容' }),
  preview: vi.fn(), update: vi.fn(),
};

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionClient.clearSession(); });

describe('LINE 通知規則 query 與 mutation 接線', () => {
  it('只在頁籤啟用時查一次，通知內容與發送設定沿用同一真實規則', async () => {
    sessionClient.setSession('synthetic-line-rules-session', { id: 7, username: 'line-rules-test', display_name: '測試管理員', role: 'admin' });
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      expect(String(input)).toBe('/api/v1/line/notification-rules/deposit_notice/message-template');
      expect(options?.method).toBe('GET');
      expect(options?.body).toBeUndefined();
      return new Response(JSON.stringify({ success: true, data: {
        rule_id: 'deposit_notice', template_id: 'deposit_notice', name: '訂金確認',
        content: '訂金確認通知', revision: 1, variables: [], sample_preview: '訂金確認通知',
      } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
    vi.stubGlobal('fetch', fetchSpy);
    const { customer, identity, configuration } = dependencies();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} onboardingClient={onboardingClient} />);
    expect(configuration.getNotificationRules).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '通知與發送' }));
    await screen.findByRole('button', { name: '編輯訂金確認內容' });
    expect(configuration.getNotificationRules).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('FLOW-04')).not.toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(fetchSpy.mock.calls.filter(([input]) => String(input) === '/api/v1/line/notification-rules/deposit_notice/message-template')).toHaveLength(1);
    expect(fetchSpy.mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: '編輯訂金確認內容' }));
    fireEvent.click(screen.getByText('發送設定'));
    fireEvent.click(screen.getByRole('button', { name: '修改發送設定' }));
    expect(screen.getByRole('region', { name: 'LINE 通知規則維護' })).toBeInTheDocument();
    expect(screen.getByLabelText('收件者')).toHaveValue('client');
    expect(screen.getByLabelText('排程方式')).toHaveValue('immediate');
    fireEvent.click(screen.getByRole('button', { name: '返回內容' }));
    fireEvent.click(screen.getByRole('button', { name: '取消' }));

    fireEvent.click(screen.getByRole('button', { name: '編輯訂金確認內容' }));
    expect(screen.getAllByText('訂金確認').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByText('發送設定'));
    fireEvent.click(screen.getByRole('button', { name: '修改發送設定' }));
    expect(screen.queryByText('系統唯一規則識別碼：deposit_notice')).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'LINE 通知規則維護' })).toBeInTheDocument();
    expect(screen.getByLabelText('收件者')).toHaveValue('client');
    expect(screen.queryByRole('button', { name: /儲存並發布|手動重播/ })).not.toBeInTheDocument();
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect(fetchSpy.mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);
  });

  it('revision 0 的空 definition 顯示真實空狀態而不是 mock 規則', async () => {
    const empty = { revision: 0, definition: {} } as const;
    const { customer, identity, configuration } = dependencies(empty);
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} onboardingClient={onboardingClient} />);
    fireEvent.click(screen.getByRole('button', { name: '通知與發送' }));
    expect(await screen.findByRole('button', { name: '編輯新好友歡迎訊息內容' })).toBeInTheDocument();
    // An empty rules definition retains the welcome entry, without inventing notification rules.
    expect(document.querySelectorAll('[data-notification-id]')).toHaveLength(1);
    expect(document.querySelector('[data-notification-id="welcome"]')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '編輯訂金確認內容' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Current revision|revision：0/i)).not.toBeInTheDocument();
    expect(screen.queryByText('FLOW-13')).not.toBeInTheDocument();
  });
});
