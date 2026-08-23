/**
 * File: line_identity_revocation_flow.test.tsx
 * Description: 驗證 LINE 身分 query/detail、遮罩資料與未開放解除控制項不觸發 Preview／Apply。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, FIXTURE_LINE_USER_ID } from './fixtures/line_identity/line_identity_contract_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding'>;

afterEach(() => vi.restoreAllMocks());

describe('LINE 身分 query-only slice', () => {
  it('可讀取遮罩 binding detail，且解除 Preview／Apply 控制項原生鎖定', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const customer: CustomerServiceQueryClient = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const previewRevocation = vi.fn();
    const applyRevocation = vi.fn();
    const identityCandidate = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValue(BOUND_IDENTITY_FIXTURE),
      previewRevocation,
      applyRevocation,
    };
    const identity: LineIdentityQueryClient = identityCandidate;
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));
    await screen.findByText('U123••••cdef');
    expect(screen.queryByText(FIXTURE_LINE_USER_ID)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('身分解除 mutation 未開放');
    expect(screen.getByRole('button', { name: '預覽解除（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '提交解除（未開放）' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '觀察解除（未開放）' })).toBeDisabled();
    expect(identityCandidate.getBinding).toHaveBeenCalledTimes(1);
    expect(previewRevocation).not.toHaveBeenCalled();
    expect(applyRevocation).not.toHaveBeenCalled();
    expect(document.body.textContent).not.toContain(FIXTURE_LINE_USER_ID);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('detail 查詢失敗時只提供查詢重試，不恢復解除 mutation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const customer: CustomerServiceQueryClient = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const previewRevocation = vi.fn();
    const applyRevocation = vi.fn();
    const getBinding = vi.fn()
      .mockRejectedValueOnce(new Error('temporary read failure'))
      .mockResolvedValueOnce(BOUND_IDENTITY_FIXTURE);
    const identityCandidate = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding,
      previewRevocation,
      applyRevocation,
    };
    const identity: LineIdentityQueryClient = identityCandidate;
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));
    await screen.findByText('U123••••cdef');
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    await screen.findByText('LINE 身分明細載入失敗');
    fireEvent.click(screen.getByRole('button', { name: '重試查詢' }));
    await screen.findByText('身分解除 mutation 未開放');
    expect(getBinding).toHaveBeenCalledTimes(2);
    expect(previewRevocation).not.toHaveBeenCalled();
    expect(applyRevocation).not.toHaveBeenCalled();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
