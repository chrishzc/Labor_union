/**
 * File: line_identity_revocation_flow.test.tsx
 * Description: 驗證 LINE 身分 detail 到解除 Preview／Apply、遮罩與重試流程。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, FIXTURE_LINE_USER_ID, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';

type CustomerServiceQueryClient = Pick<CustomerServiceClient, 'getSummary' | 'listTickets' | 'getTicketDetail'>;
type LineIdentityQueryClient = Pick<LineIdentityClient, 'listBindings' | 'getBinding' | 'previewRevocation' | 'applyRevocation'>;

afterEach(() => vi.restoreAllMocks());

describe('LINE 身分解除 successor', () => {
  it('可由遮罩 binding detail 執行解除 Preview／Apply', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const customer: CustomerServiceQueryClient = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const previewRevocation = vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE);
    const applyRevocation = vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE);
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
    await screen.findByText('尚未申請解除');
    fireEvent.click(screen.getByRole('button', { name: '預覽解除' }));
    await screen.findByText('可提交解除');
    fireEvent.change(screen.getByRole('textbox', { name: '解除原因' }), { target: { value: '客戶已確認解除 LINE 身分綁定' } });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認解除對象與目前版本' }));
    fireEvent.click(screen.getByRole('button', { name: '提交解除' }));
    await screen.findByText('解除申請已受理');
    expect(identityCandidate.getBinding).toHaveBeenCalledTimes(1);
    expect(previewRevocation).toHaveBeenCalledWith(FIXTURE_LINE_USER_ID, expect.any(Object));
    expect(applyRevocation).toHaveBeenCalledWith(FIXTURE_LINE_USER_ID, expect.objectContaining({ expected_version: 7, reason: '客戶已確認解除 LINE 身分綁定' }), expect.any(Object));
    expect(document.body.textContent).not.toContain(FIXTURE_LINE_USER_ID);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('detail 查詢失敗後可重試並恢復解除 Preview', async () => {
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
    await screen.findByText('尚未申請解除');
    expect(screen.getByRole('button', { name: '預覽解除' })).toBeEnabled();
    expect(getBinding).toHaveBeenCalledTimes(2);
    expect(previewRevocation).not.toHaveBeenCalled();
    expect(applyRevocation).not.toHaveBeenCalled();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
