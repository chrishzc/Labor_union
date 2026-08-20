/**
 * File: line_rich_menu_query_flow.test.tsx
 * Description: 驗證 Rich Menu 設定與 loaded-scope 發布歷史來自 query client，且敏感 action 不進 DOM。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineConfigurationQueryClient } from '../api/line_configuration/line_configuration_query_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';
import { LINE_NOTIFICATION_RULES_CATALOG_FIXTURE, LINE_RICH_MENU_CONFIGURATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_FIXTURE, LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE } from './fixtures/line_configuration_query_fixtures';

function dependencies(): { customer: CustomerServiceClient; identity: LineIdentityClient; configuration: LineConfigurationQueryClient } {
  return {
    customer: { getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE), listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE), getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE), previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE), applyResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE) },
    identity: { listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE), getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE), previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE), applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE) },
    configuration: { getNotificationRules: vi.fn().mockResolvedValue(LINE_NOTIFICATION_RULES_CATALOG_FIXTURE), getRichMenuConfiguration: vi.fn().mockResolvedValue(LINE_RICH_MENU_CONFIGURATION_FIXTURE), listRichMenuPublications: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_PAGE_FIXTURE), getRichMenuPublication: vi.fn().mockResolvedValue(LINE_RICH_MENU_PUBLICATION_FIXTURE) },
  };
}

afterEach(() => vi.restoreAllMocks());

describe('LINE Rich Menu query-only 接線', () => {
  it('顯示真實 menu label 與 loaded-scope publication，且不 render action payload', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new Error('unexpected network'));
    vi.stubGlobal('fetch', fetchSpy);
    const { customer, identity, configuration } = dependencies();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} lineConfiguration={configuration} />);
    fireEvent.click(screen.getByRole('button', { name: /2\. 多角色 Rich Menu/ }));

    await waitFor(() => expect(screen.getByText('案件進度')).toBeInTheDocument());
    expect(screen.getAllByText(/最多 100 筆/)).toHaveLength(2);
    expect(screen.getByText('已發布')).toBeInTheDocument();
    expect(screen.queryByText('case_progress')).not.toBeInTheDocument();
    expect(screen.queryByText(/https?:\/\//)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /發布至 LINE/ })).toBeDisabled();
    expect(configuration.getRichMenuConfiguration).toHaveBeenCalledTimes(1);
    expect(configuration.listRichMenuPublications).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '查看' }));
    await waitFor(() => expect(configuration.getRichMenuPublication).toHaveBeenCalledWith(19));
    expect(screen.getByRole('button', { name: '重新發布' })).toBeDisabled();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
