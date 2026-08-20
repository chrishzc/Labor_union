/**
 * File: line_customer_service_resolve_flow.test.tsx
 * Description: 驗證客服結案 Preview／Apply／重查及 outcome unknown 相同識別鍵重試流程。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import { ApiTimeoutError } from '../api/customer_service/customer_service_errors';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import {
  CUSTOMER_SERVICE_DETAIL_FIXTURE,
  CUSTOMER_SERVICE_PAGE_FIXTURE,
  CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE,
  CUSTOMER_SERVICE_SUMMARY_FIXTURE,
} from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';

const resolvedDetail = {
  ...CUSTOMER_SERVICE_DETAIL_FIXTURE,
  ticket: { ...CUSTOMER_SERVICE_DETAIL_FIXTURE.ticket, status: 'resolved' as const, version: 5 },
};

function setup(applyResolve: CustomerServiceClient['applyResolve']) {
  const customer: CustomerServiceClient = {
    getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
    listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
    getTicketDetail: vi.fn().mockResolvedValueOnce(CUSTOMER_SERVICE_DETAIL_FIXTURE).mockResolvedValue(resolvedDetail),
    previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE),
    applyResolve,
  };
  const identity: LineIdentityClient = {
    listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
    getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
    previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
    applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
  };
  render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
  return customer;
}

afterEach(() => vi.restoreAllMocks());

describe('客服結案狀態機', () => {
  it('依序執行 detail、preview、apply、detail re-query 才顯示 observed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const customer = setup(vi.fn().mockResolvedValue(resolvedDetail));
    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('內部結案備註（可空）');
    fireEvent.change(screen.getByRole('textbox'), { target: { value: ' 已確認完成 ' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽結案' }));
    await screen.findByText('處理中 → 已結案');
    fireEvent.click(screen.getByRole('button', { name: '確認結案' }));

    await screen.findByText(/重新查詢完成：伺服器目前狀態為「已結案」/);
    expect(customer.previewResolve).toHaveBeenCalledWith(31, expect.objectContaining({ internal_note: '已確認完成', expected_version: 4 }), expect.objectContaining({ correlationId: expect.any(String) }));
    expect(customer.applyResolve).toHaveBeenCalledTimes(1);
    expect(customer.getTicketDetail).toHaveBeenCalledTimes(2);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('Apply 逾時保留抽屜並以完全相同 payload 與 key 重試', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const apply = vi.fn().mockRejectedValueOnce(new ApiTimeoutError(10_000)).mockResolvedValueOnce(resolvedDetail);
    const customer = setup(apply);
    await waitFor(() => expect(screen.getByText('#31')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('內部結案備註（可空）');
    fireEvent.click(screen.getByRole('button', { name: '預覽結案' }));
    await screen.findByText('處理中 → 已結案');
    fireEvent.click(screen.getByRole('button', { name: '確認結案' }));
    await screen.findByText(/套用結果未知/);
    expect(screen.getByRole('button', { name: '關閉' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /相同識別鍵重試/ }));
    await screen.findByText(/重新查詢完成/);

    expect(customer.applyResolve).toHaveBeenCalledTimes(2);
    expect(apply.mock.calls[1][1]).toEqual(apply.mock.calls[0][1]);
    expect(apply.mock.calls[1][2]).toEqual(apply.mock.calls[0][2]);
  });
});
