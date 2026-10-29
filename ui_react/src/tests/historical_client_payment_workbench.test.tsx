import { UnsavedChangesProvider, useUnsavedNavigation } from '../components/UnsavedChanges';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HistoricalClientPaymentWorkbench } from '../components/HistoricalClientPaymentWorkbench';
import { historicalClientPaymentClient } from '../api/client_finance/historical_client_payment_client';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';

function LeaveAction({ onLeave }: { onLeave: () => void }) { const { requestLeave } = useUnsavedNavigation(); return <button onClick={() => requestLeave(onLeave)}>離開付款頁</button>; }

const obligation = {
  obligation_identity: 'client-obligation:1', case_no: 'CASE-1', obligation_type: 'deposit',
  direction: 'receivable_from_client' as const, amount_due_ntd: 12000, projection_version: 4, status: 'open' as const,
};

describe('Historical client payment transport contract', () => {
  const query = { case_no: 'CASE-1', account_version: 4, adoption_receipt_id: null,
    adopted: false, normal_bank_candidate_identities: [], obligations: [obligation] };
  afterEach(() => vi.restoreAllMocks());

  it('keeps explicit nullable adoption facts without inventing owner data', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('historical-test');
    vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'Success', data: query });
    expect(await historicalClientPaymentClient.query('CASE-1')).toEqual(query);
  });

  it.each([
    { success: true, message: 'Success' },
    { success: true, message: 'Success', data: null },
    { success: true, message: 'Success', data: { ...query, account_version: undefined } },
    { success: true, message: 'Success', data: { ...query, unexpected: true } },
    { success: false, message: 'Rejected', data: query },
  ])('rejects unusable query envelopes', async (raw) => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('historical-test');
    vi.spyOn(transport, 'get').mockResolvedValue(raw);
    await expect(historicalClientPaymentClient.query('CASE-1')).rejects.toMatchObject({ code: 'HISTORICAL_CLIENT_SCHEMA_MISMATCH' });
  });
});

describe('HistoricalClientPaymentWorkbench', () => {
  afterEach(() => vi.restoreAllMocks());

  it('runs owner Query, automatic Preview/Apply and fresh readback without an Anomalies mutation', async () => {
    sessionClient.setSession('historical-client-payment-test', {
      id: 1, username: 'operator', display_name: 'Operator', role: 'admin',
    });
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

    const left = vi.fn();
    render(<UnsavedChangesProvider><LeaveAction onLeave={left} /><HistoricalClientPaymentWorkbench caseNo="CASE-1" /></UnsavedChangesProvider>);
    fireEvent.click(await screen.findByLabelText(/client-obligation:1/));
    fireEvent.change(screen.getByLabelText('原因（選填）'), { target: { value: '核對歷史付款' } });
    fireEvent.click(screen.getByRole('button', { name: '離開付款頁' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存變更並離開' }));

    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/已重新讀取付款結果：客戶款項已結清/)).toBeInTheDocument();
    await waitFor(() => expect(left).toHaveBeenCalledTimes(1));
  });
});
