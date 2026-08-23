/**
 * File: line_customer_service_resolve_flow.test.tsx
 * Description: 驗證客服工單 query/detail、遮罩資料與未開放結案控制項不觸發 Preview／Apply。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
  CUSTOMER_SERVICE_TICKET_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

function setup(): {
  customer: CustomerServiceQueryClient;
  previewResolve: ReturnType<typeof vi.fn>;
  applyResolve: ReturnType<typeof vi.fn>;
} {
  const previewResolve = vi.fn();
  const applyResolve = vi.fn();
  const customer: CustomerServiceClient = {
    getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
    listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
    getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    previewResolve,
    applyResolve,
  };
  const identity: LineIdentityQueryClient = {
    listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
    getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
  };
  render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
  return { customer, previewResolve, applyResolve };
}

afterEach(() => vi.restoreAllMocks());

describe('客服工單 query-only slice', () => {
  it('可讀取客服 detail，且結案 Preview／Apply 控制項原生鎖定', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, previewResolve, applyResolve } = setup();
    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('客服結案 mutation 未開放');
    expect(screen.getByText(CUSTOMER_SERVICE_TICKET_FIXTURE.line_user_id_masked)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '預覽結案（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '確認結案（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重試結案（未開放）' })).toBeDisabled();
    expect(customer.getTicketDetail).toHaveBeenCalledTimes(1);
    expect(previewResolve).not.toHaveBeenCalled();
    expect(applyResolve).not.toHaveBeenCalled();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('detail 查詢失敗時只提供查詢重試，不恢復結案 mutation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const previewResolve = vi.fn();
    const applyResolve = vi.fn();
    const getTicketDetail = vi.fn()
      .mockRejectedValueOnce(new Error('temporary read failure'))
      .mockResolvedValueOnce(CUSTOMER_SERVICE_DETAIL_FIXTURE);
    const customerCandidate = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail,
      previewResolve,
      applyResolve,
    };
    const customer: CustomerServiceQueryClient = customerCandidate;
    const identity: LineIdentityQueryClient = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
    };
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('客服工單明細載入失敗');
    fireEvent.click(screen.getByRole('button', { name: '重試查詢' }));
    await screen.findByText('客服結案 mutation 未開放');
    expect(getTicketDetail).toHaveBeenCalledTimes(2);
    expect(previewResolve).not.toHaveBeenCalled();
    expect(applyResolve).not.toHaveBeenCalled();
  });
});
