/**
 * File: line_identity_revocation_flow.test.tsx
 * Description: 驗證 LINE 身分解除 Preview／Apply／重查，不把申請受理冒充解除完成。
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CustomerServiceClient } from '../api/customer_service/customer_service_client';
import type { LineIdentityClient } from '../api/line_identity/line_identity_client';
import { LineManagementPage } from '../pages/LineManagementPage';
import { CUSTOMER_SERVICE_DETAIL_FIXTURE, CUSTOMER_SERVICE_PAGE_FIXTURE, CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE, CUSTOMER_SERVICE_SUMMARY_FIXTURE } from './fixtures/customer_service/customer_service_contract_fixtures';
import { BINDING_PAGE_FIXTURE, BOUND_IDENTITY_FIXTURE, REVOCATION_PREVIEW_FIXTURE, REVOCATION_REQUEST_FIXTURE } from './fixtures/line_identity/line_identity_contract_fixtures';

afterEach(() => vi.restoreAllMocks());

describe('LINE 身分解除狀態機', () => {
  it('reason 必填，申請後重查 revocation_pending 且不顯示已解除', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const customer: CustomerServiceClient = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
      previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE),
      applyResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const pendingBinding = { ...BOUND_IDENTITY_FIXTURE, status: 'revocation_pending' as const, version: 8, revocation_request_id: 901, revocation_status: 'pending_menu_reset' as const };
    const identity: LineIdentityClient = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn().mockResolvedValueOnce(BOUND_IDENTITY_FIXTURE).mockResolvedValue(pendingBinding),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    };
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));
    await screen.findByText('U123••••cdef');
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    const reason = await screen.findByRole('textbox');
    expect(screen.getByRole('button', { name: '預覽解除' })).toBeDisabled();
    fireEvent.change(reason, { target: { value: ' 客戶確認解除 ' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽解除' }));
    await screen.findByText('預設 Rich Menu：已發布');
    fireEvent.click(screen.getByRole('button', { name: '提交解除申請' }));

    await screen.findByText(/解除申請已受理/);
    expect(screen.getByText(/重新查詢狀態：「解除處理中」/)).toBeInTheDocument();
    expect(screen.queryByText(/重新查詢狀態：「已解除」/)).not.toBeInTheDocument();
    expect(identity.applyRevocation).toHaveBeenCalledWith(BOUND_IDENTITY_FIXTURE.line_user_id, expect.objectContaining({ expected_version: 7, reason: '客戶確認解除', idempotency_key: expect.any(String), correlation_id: expect.any(String) }));
    expect(identity.getBinding).toHaveBeenCalledTimes(2);
    expect(document.body.textContent).not.toContain(BOUND_IDENTITY_FIXTURE.line_user_id);
    expect(document.body.textContent).not.toContain(REVOCATION_REQUEST_FIXTURE.provider_menu_id);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('Apply 已受理但重查失敗時不得退回可再次 Apply，只能重試觀察', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('unexpected network')));
    const customer: CustomerServiceClient = {
      getSummary: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_SUMMARY_FIXTURE),
      listTickets: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_PAGE_FIXTURE),
      getTicketDetail: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
      previewResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_RESOLVE_PREVIEW_FIXTURE),
      applyResolve: vi.fn().mockResolvedValue(CUSTOMER_SERVICE_DETAIL_FIXTURE),
    };
    const pendingBinding = { ...BOUND_IDENTITY_FIXTURE, status: 'revocation_pending' as const, version: 8, revocation_request_id: 901, revocation_status: 'pending_menu_reset' as const };
    const identity: LineIdentityClient = {
      listBindings: vi.fn().mockResolvedValue(BINDING_PAGE_FIXTURE),
      getBinding: vi.fn()
        .mockResolvedValueOnce(BOUND_IDENTITY_FIXTURE)
        .mockRejectedValueOnce(new Error('temporary read failure'))
        .mockResolvedValueOnce(pendingBinding),
      previewRevocation: vi.fn().mockResolvedValue(REVOCATION_PREVIEW_FIXTURE),
      applyRevocation: vi.fn().mockResolvedValue(REVOCATION_REQUEST_FIXTURE),
    };
    render(<LineManagementPage customerService={customer} lineIdentity={identity} />);
    fireEvent.click(screen.getByRole('button', { name: /3\. LINE 身分綁定/ }));
    await screen.findByText('U123••••cdef');
    fireEvent.click(screen.getByRole('button', { name: '查看明細' }));
    fireEvent.change(await screen.findByRole('textbox'), { target: { value: '客戶確認解除' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽解除' }));
    await screen.findByText('預設 Rich Menu：已發布');
    fireEvent.click(screen.getByRole('button', { name: '提交解除申請' }));

    await screen.findByText(/解除申請已受理，但最新狀態尚未確認/);
    expect(screen.queryByRole('button', { name: '提交解除申請' })).not.toBeInTheDocument();
    const retryObservation = screen.getByRole('button', { name: '重新查詢解除狀態' });
    fireEvent.click(retryObservation);

    await screen.findByText(/重新查詢狀態：「解除處理中」/);
    expect(identity.applyRevocation).toHaveBeenCalledTimes(1);
    expect(identity.getBinding).toHaveBeenCalledTimes(3);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
