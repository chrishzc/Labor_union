import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HistoricalClientPaymentWorkbench } from '../components/HistoricalClientPaymentWorkbench';
import { historicalClientPaymentClient } from '../api/client_finance/historical_client_payment_client';

const obligation = {
  obligation_identity: 'client-obligation:1', case_no: 'CASE-1', obligation_type: 'deposit',
  direction: 'receivable_from_client' as const, amount_due_ntd: 12000, projection_version: 4, status: 'open' as const,
};

describe('HistoricalClientPaymentWorkbench', () => {
  afterEach(() => vi.restoreAllMocks());

  it('runs owner Query, Preview, confirmed Apply and fresh readback without an Anomalies mutation', async () => {
    vi.spyOn(historicalClientPaymentClient, 'query').mockResolvedValue({
      case_no: 'CASE-1', account_version: 4, adoption_receipt_id: 9, adopted: true,
      normal_bank_candidate_identities: [], obligations: [obligation],
    });
    vi.spyOn(historicalClientPaymentClient, 'preview').mockResolvedValue({
      case_no: 'CASE-1', account_version: 4, adoption_receipt_id: 9, obligations: [obligation],
      amount_snapshot_ntd: 12000, blockers: [], can_apply: true, preview_fingerprint: 'a'.repeat(64),
    });
    const apply = vi.spyOn(historicalClientPaymentClient, 'apply').mockResolvedValue({
      event_identity: 'historical-client-payment:event', case_no: 'CASE-1', obligation_identities: ['client-obligation:1'],
      amount_snapshot_ntd: 12000, resulting_account_version: 5, preview_fingerprint: 'a'.repeat(64),
    });
    vi.spyOn(historicalClientPaymentClient, 'readback').mockResolvedValue({
      case_no: 'CASE-1', account_version: 5, obligations: [{ ...obligation, status: 'settled' }],
      projections: [{ obligation_identity: 'client-obligation:1', amount_snapshot_ntd: 12000, obligation_projection_version: 4 }], owner_terminal: true,
    });

    render(<HistoricalClientPaymentWorkbench caseNo="CASE-1" />);
    fireEvent.click(await screen.findByLabelText(/client-obligation:1/));
    fireEvent.click(screen.getByRole('button', { name: '預覽歷史付款影響' }));
    expect(await screen.findByText(/金額快照：NT\$ 12,000/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/我已核對方向/));
    fireEvent.click(screen.getByRole('button', { name: '確認並提交' }));

    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Fresh readback：Client Finance 已結清/)).toBeInTheDocument();
  });
});
