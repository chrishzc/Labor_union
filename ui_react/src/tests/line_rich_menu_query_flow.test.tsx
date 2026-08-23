/**
 * File: line_rich_menu_query_flow.test.tsx
 * Description: 驗證 Rich Menu 設定與發布紀錄來自 query client，且未授權 provider action 不進入畫面。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from './fixtures/line_configuration_query_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

function dependencies(): { customer: CustomerServiceQueryClient; identity: LineIdentityQueryClient; configuration: LineConfigurationQueryClient } {
  return {
    customer: { getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE), listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE), getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE) },
    identity: { listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE), getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE) },
    configuration: { getNotificationRules: vi.fn().mockResolvedValue(LINE_NOTIFICATION_RULES_CATALOG_FIXTURE), getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE), listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE), getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE) },
  };
}

afterEach(() => vi.restoreAllMocks());

describe('LINE Rich Menu query-only 接線', () => {
  it('顯示真實 menu label 與 publication，且不暴露 provider action', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const { customer, identity, configuration } = dependencies();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} />);
    fireEvent.click(screen.getByRole('button', { name: /2\. 多角色 Rich Menu/ }));

    await waitFor(() => expect(screen.getByText('案件進度')).toBeInTheDocument());
    expect(screen.getByText('目前載入最多 100 筆。')).toBeInTheDocument();
    expect(screen.getByText('已發布')).toBeInTheDocument();
    expect(screen.queryByText('case_progress')).not.toBeInTheDocument();
    expect(screen.queryByText(/https?:\/\//)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /發布至 LINE|上傳圖片|刪除選單/ })).not.toBeInTheDocument();
    expect(configuration.getRichMenuConfiguration).toHaveBeenCalledTimes(1);
    expect(configuration.listRichMenuPublications).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '查看' }));
    await waitFor(() => expect(configuration.getRichMenuPublication).toHaveBeenCalledWith(
      19,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(screen.queryByRole('button', { name: '重新發布' })).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
