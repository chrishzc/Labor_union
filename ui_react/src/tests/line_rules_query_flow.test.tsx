/**
 * File: line_rules_query_flow.test.tsx
 * Description: 驗證通知規則只在頁籤啟用時查詢，並同時呈現真實 catalog 與 typed mutation 維護區。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineNotificationRulesCatalog } from '../api/line_configuration/line_configuration_query_schemas';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from './fixtures/line_configuration_query_fixtures';

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

afterEach(() => vi.restoreAllMocks());

describe('LINE 通知規則 query 與 mutation 接線', () => {
  it('只在頁籤啟用時查一次並以真實規則開啟查詢 Drawer', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const { customer, identity, configuration } = dependencies();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} />);
    expect(configuration.getNotificationRules).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /4\. 通知規則/ }));
    await waitFor(() => expect(screen.getAllByText('deposit_notice').length).toBeGreaterThan(0));
    expect(configuration.getNotificationRules).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('FLOW-04')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /deposit_notice/ }));
    expect(screen.getAllByText('訂金確認').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: /儲存並發布|手動重播/ })).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('revision 0 的空 definition 顯示真實空狀態而不是 mock 規則', async () => {
    const empty = { revision: 0, definition: {} } as const;
    const { customer, identity, configuration } = dependencies(empty);
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} />);
    fireEvent.click(screen.getByRole('button', { name: /4\. 通知規則/ }));
    await screen.findByText('目前尚未設定通知規則');
    expect(screen.getAllByText(/Current revision：0/).length).toBeGreaterThan(0);
    expect(screen.queryByText('FLOW-13')).not.toBeInTheDocument();
  });
});
