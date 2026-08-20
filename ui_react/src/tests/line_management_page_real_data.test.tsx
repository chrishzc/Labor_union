/**
 * File: line_management_page_real_data.test.tsx
 * Description: 驗證 LINE 管理頁以 typed client 資料呈現六頁籤、客服 KPI 與遮罩身分清單。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';
import {
  BINDING_PAGE_FIXTURE,
  BOUND_IDENTITY_FIXTURE,
  REVOCATION_PREVIEW_FIXTURE,
  REVOCATION_REQUEST_FIXTURE,
} from './fixtures/line_identity/line_identity_contract_fixtures';

function clients(): { customer: CustomerServiceClient; identity: LineIdentityClient } {
  return {
    customer: {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
      previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE),
      applyResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    },
    identity: {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    },
  };
}

afterEach(() => vi.restoreAllMocks());

describe('LINE 管理頁真實資料呈現', () => {
  it('呈現六頁籤與客服 typed KPI／列表，不顯示 prototype 工單', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);

    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('後端尚未提供列表問題摘要')).toBeInTheDocument();
    expect(screen.queryByText('TKT-2026-001')).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /[1-6]\./ })).toHaveLength(6);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('切到身分頁才查詢清單，只呈現遮罩 LINE ID', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, identity } = clients();
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));

    await waitFor(() => expect(screen.getByText('U123••••cdef')).toBeInTheDocument());
    expect(screen.queryByText(BOUND_IDENTITY_FIXTURE.line_user_id)).not.toBeInTheDocument();
    expect(screen.queryByText(REVOCATION_PREVIEW_FIXTURE.provider_menu_id ?? '')).not.toBeInTheDocument();
    expect(identity.listBindings).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
