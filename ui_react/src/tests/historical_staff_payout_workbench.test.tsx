import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HistoricalStaffPayoutWorkbench } from '../components/HistoricalStaffPayoutWorkbench';
import { historicalStaffPayoutClient } from '../api/staff_payables/historical_staff_payout_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';

const obligation = {
  obligation_identity: 'staff-obligation:1', case_no: 'CASE-1', staff_id: 7, amount_due_ntd: 8000,
  payroll_version: 3, direction: 'payable_to_staff' as const, status: 'open' as const,
};

describe('Historical staff payout transport contract', () => {
  const query = { case_no: 'CASE-1', staff_id: 7, staff_payables_version: 3,
    adoption_receipt_id: null, adopted: false, normal_bank_candidate_identities: [], obligations: [obligation] };
  afterEach(() => vi.restoreAllMocks());

  it('keeps exact staff and case facts and explicit nullable adoption', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('historical-test');
    vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'Success', data: query });
    expect(await historicalStaffPayoutClient.query('CASE-1', 7)).toEqual(query);
  });

  it.each([
    { success: true, message: 'Success' },
    { success: true, message: 'Success', data: null },
    { success: true, message: 'Success', data: { ...query, staff_payables_version: undefined } },
    { success: true, message: 'Success', data: { ...query, unexpected: true } },
    { success: false, message: 'Rejected', data: query },
  ])('rejects unusable query envelopes', async (raw) => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('historical-test');
    vi.spyOn(transport, 'get').mockResolvedValue(raw);
    await expect(historicalStaffPayoutClient.query('CASE-1', 7)).rejects.toMatchObject({ code: 'HISTORICAL_STAFF_SCHEMA_MISMATCH' });
  });
});
describe('HistoricalStaffPayoutWorkbench', () => {
  beforeEach(() => sessionClient.setSession('historical-staff-payout', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 }));
  afterEach(() => { sessionClient.clearSession(); act(() => orderMutationFlowStore.clearAll()); vi.restoreAllMocks(); });

  it('keeps the exact staff and case through Query, Preview, Apply and fresh readback', async () => {
    vi.spyOn(historicalStaffPayoutClient, 'query').mockResolvedValue({
      case_no: 'CASE-1', staff_id: 7, staff_payables_version: 3, adoption_receipt_id: 9, adopted: true,
      normal_bank_candidate_identities: [], obligations: [obligation],
    });
    vi.spyOn(historicalStaffPayoutClient, 'preview').mockResolvedValue({
      case_no: 'CASE-1', staff_id: 7, staff_payables_version: 3, adoption_receipt_id: 9, obligations: [obligation],
      amount_snapshot_ntd: 8000, blockers: [], can_apply: true, preview_fingerprint: 'b'.repeat(64),
    });
    const apply = vi.spyOn(historicalStaffPayoutClient, 'apply').mockResolvedValue({
      event_identity: 'historical-staff-payout:event', case_no: 'CASE-1', staff_id: 7, obligation_identities: ['staff-obligation:1'],
      amount_snapshot_ntd: 8000, resulting_staff_payables_version: 4, preview_fingerprint: 'b'.repeat(64),
    });
    vi.spyOn(historicalStaffPayoutClient, 'readback').mockResolvedValue({
      case_no: 'CASE-1', staff_id: 7, staff_payables_version: 4, obligations: [{ ...obligation, status: 'settled' }],
      projections: [{ obligation_identity: 'staff-obligation:1', amount_snapshot_ntd: 8000, obligation_payroll_version: 3 }], owner_terminal: true,
    });

    render(<HistoricalStaffPayoutWorkbench caseNo="CASE-1" staffId={7} />);
    fireEvent.click(await screen.findByLabelText(/staff-obligation:1/));
    fireEvent.click(screen.getByRole('button', { name: '預覽歷史付款影響' }));
    expect(await screen.findByText(/金額快照：NT\$ 8,000/)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/我已核對案件、月嫂/));
    fireEvent.click(screen.getByRole('button', { name: '確認並提交' }));

    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/已重新讀取付款結果：本月嫂款項已結清/)).toBeInTheDocument();
  });
});
