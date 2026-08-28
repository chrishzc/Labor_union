/**
 * File: client_over_refund_recovery_workbench.test.tsx
 * Description: 驗證 client recovery workbench 的分支、Preview invalidation 與 root predicate readback。
 */
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ClientOverRefundRecoveryWorkbench } from '../components/ClientOverRefundRecoveryWorkbench';
import type { ClientOverRefundRecoveryClient } from '../api/client_finance/client_over_refund_recovery_client';

const openQuery = { case_no: 'CASE-1', recovery_identity: 'recovery:1', remaining_amount_ntd: 500, status: 'open' as const, recovery_version: 3, account_version: 8, source_row_reference: 'bank:10', current_matchings: [] };
const matchedQuery = { ...openQuery, current_matchings: [{ matching_identity: 'match:1', matching_version: 1, incoming_row_reference: 'bank:10' }] };
const adjustmentPreview = { recovery_identity: 'recovery:1', account_version: 8, recovery_version: 3, adjustment_amount_ntd: 500, remaining_before_ntd: 500, remaining_after_ntd: 0, resulting_status: 'adjusted' as const, preview_fingerprint: 'a'.repeat(64) };

function client(overrides: Partial<ClientOverRefundRecoveryClient> = {}): ClientOverRefundRecoveryClient {
  return {
    query: vi.fn().mockResolvedValue(openQuery),
    previewMatching: vi.fn(), applyMatching: vi.fn(), previewCollection: vi.fn(), applyCollection: vi.fn(), previewAdjustment: vi.fn().mockResolvedValue(adjustmentPreview), applyAdjustment: vi.fn(),
    ...overrides,
  };
}

describe('ClientOverRefundRecoveryWorkbench', () => {
  it('keeps an open recovery visible and requires preview before Apply', async () => {
    const owner = client();
    render(<ClientOverRefundRecoveryWorkbench caseNo="CASE-1" recoveryIdentity="recovery:1" client={owner} />);
    await waitFor(() => expect(screen.getByText(/目前餘額：500/)).toBeInTheDocument());
    expect(screen.getByText(/配對不會解除異常/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '確認套用' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/canonical 入款流水 ID/), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '電話確認' } });
    fireEvent.change(screen.getByLabelText(/佐證 reference/), { target: { value: 'phone-log:1' } });
    expect(screen.getByRole('button', { name: '預覽處理影響' })).toBeEnabled();
  });

  it('only shows解除 after fresh owner readback satisfies remaining=0 and terminal status', async () => {
    const owner = client({
      query: vi.fn().mockResolvedValueOnce(openQuery).mockResolvedValueOnce({ ...openQuery, remaining_amount_ntd: 0, status: 'adjusted' as const }),
      applyAdjustment: vi.fn().mockResolvedValue({ recovery_identity: 'recovery:1', account_version: 9, recovery_version: 4, remaining_after_ntd: 0, resulting_status: 'adjusted' as const, evidence_reference: 'phone-log:1' }),
    });
    render(<ClientOverRefundRecoveryWorkbench caseNo="CASE-1" recoveryIdentity="recovery:1" client={owner} />);
    await waitFor(() => expect(screen.getByText(/目前餘額：500/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: '授權人工調整' }));
    fireEvent.change(screen.getByLabelText(/調整金額/), { target: { value: '500' } });
    fireEvent.change(screen.getByLabelText(/處理原因/), { target: { value: '電話確認後授權調整' } });
    fireEvent.change(screen.getByLabelText(/佐證 reference/), { target: { value: 'phone-log:1' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽處理影響' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '確認套用' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: '確認套用' }));
    await waitFor(() => expect(screen.getByText('客戶退款超額追償已解除')).toBeInTheDocument());
  });

  it('uses existing owner matching as the collection branch instead of offering a fake resolve', async () => {
    const owner = client({ query: vi.fn().mockResolvedValue(matchedQuery) });
    render(<ClientOverRefundRecoveryWorkbench caseNo="CASE-1" recoveryIdentity="recovery:1" client={owner} />);
    await waitFor(() => expect(screen.getByText(/目前餘額：500/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '核銷已配對入款' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /解除異常/ })).not.toBeInTheDocument();
  });
});
