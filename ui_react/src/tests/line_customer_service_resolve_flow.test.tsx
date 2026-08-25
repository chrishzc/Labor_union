/**
 * File: line_customer_service_resolve_flow.test.tsx
 * Description: 驗證客服工單 detail 到結案 Preview／Apply、重試與重新讀取流程。
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
  CUSTOMER_SERVICE_TICKET_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';

type CustomerServiceQueryClient = CustomerServiceClient;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

function setup(): {
  customer: CustomerServiceQueryClient;
  previewResolve: ReturnType<typeof vi.fn>;
  applyResolve: ReturnType<typeof vi.fn>;
} {
  const previewResolve = vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE);
  const applyResolve = vi.fn().mockResolvedValue({
    ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
    ticket: { ...CUSTOMER_SERVICE_TICKET_FIXTURE, status: 'resolved', version: 5 },
  });
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

describe('客服工單結案 successor', () => {
  it('可由 detail 執行結案 Preview／Apply 並顯示 canonical 結果', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const { customer, previewResolve, applyResolve } = setup();
    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('請協助確認資料更新方式');
    expect(screen.getByText(CUSTOMER_SERVICE_TICKET_FIXTURE.line_user_id_masked)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: '結案說明' }), { target: { value: '已由工會人員確認處理完成' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查結案影響' }));
    await screen.findByText('處理中 → 已結案');
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認結案內容與目前工單狀態' }));
    fireEvent.click(screen.getByRole('button', { name: '確認結案' }));
    await screen.findByText('結案已完成');
    expect(customer.getTicketDetail).toHaveBeenCalledTimes(1);
    expect(previewResolve).toHaveBeenCalledWith(31, expect.objectContaining({ status: 'resolved', expected_version: 4 }), expect.objectContaining({ correlationId: expect.any(String) }));
    expect(applyResolve).toHaveBeenCalledWith(31, expect.objectContaining({ preview_fingerprint: CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE.preview_fingerprint }), expect.objectContaining({ idempotencyKey: expect.any(String) }));
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('detail 查詢失敗後可重試並恢復結案 Preview', async () => {
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
    await screen.findByText('請協助確認資料更新方式');
    expect(screen.getByRole('button', { name: '檢查結案影響' })).toBeEnabled();
    expect(getTicketDetail).toHaveBeenCalledTimes(2);
    expect(previewResolve).not.toHaveBeenCalled();
    expect(applyResolve).not.toHaveBeenCalled();
  });
});
