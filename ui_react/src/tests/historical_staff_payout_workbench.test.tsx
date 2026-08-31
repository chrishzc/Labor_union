import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HistoricalStaffPayoutWorkbench } from '../components/HistoricalStaffPayoutWorkbench';
import { historicalStaffPayoutClient } from '../api/staff_payables/historical_staff_payout_client';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';

const obligation = {
  obligation_identity: 'staff-obligation:1', case_no: 'CASE-1', staff_id: 7, amount_due_ntd: 8000,
  payroll_version: 3, direction: 'payable_to_staff' as const, status: 'open' as const,
};

describe('HistoricalStaffPayoutWorkbench', () => {
  beforeEach(() => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('session-token');
    vi.stubGlobal('crypto', { randomUUID: () => '12345678-1234-4234-8234-123456789abc' });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('uses the exact Staff Payables Query, Preview, Apply and readback endpoints', async () => {
    const intent = {
      case_no: 'CASE-1', staff_id: 7, confirmation_kind: 'paid' as const,
      obligation_identities: ['staff-obligation:1'], payment_date: '2026-08-31',
      payment_date_unknown_reason: null, source_availability: 'missing' as const,
      evidence_reference: 'historical-payout:1',
    };
    const query = {
      case_no: 'CASE-1', staff_id: 7, staff_payables_version: 3, adoption_receipt_id: 9,
      adopted: true, normal_bank_candidate_identities: [], obligations: [obligation],
    };
    const preview = {
      case_no: 'CASE-1', staff_id: 7, staff_payables_version: 3, adoption_receipt_id: 9,
      obligations: [obligation], amount_snapshot_ntd: 8000, blockers: [], can_apply: true,
      preview_fingerprint: 'b'.repeat(64),
    };
    const receipt = {
      event_identity: 'historical-staff-payout:event', case_no: 'CASE-1', staff_id: 7,
      obligation_identities: ['staff-obligation:1'], amount_snapshot_ntd: 8000,
      resulting_staff_payables_version: 4, preview_fingerprint: 'b'.repeat(64),
    };
    const readback = {
      case_no: 'CASE-1', staff_id: 7, staff_payables_version: 4,
      obligations: [{ ...obligation, status: 'settled' as const }],
      projections: [{ obligation_identity: 'staff-obligation:1', amount_snapshot_ntd: 8000, obligation_payroll_version: 3 }],
      owner_terminal: true,
    };
    const get = vi.spyOn(transport, 'get')
      .mockResolvedValueOnce({ success: true, message: 'ok', data: query, error: null })
      .mockResolvedValueOnce({ success: true, message: 'ok', data: readback, error: null });
    const post = vi.spyOn(transport, 'post')
      .mockResolvedValueOnce({ success: true, message: 'ok', data: preview, error: null })
      .mockResolvedValueOnce({ success: true, message: 'ok', data: receipt, error: null });

    await historicalStaffPayoutClient.query('CASE-1', 7);
    await historicalStaffPayoutClient.preview(intent);
    await historicalStaffPayoutClient.apply(intent, preview, '人工核對歷史付款。', 'historical-staff-key');
    await historicalStaffPayoutClient.readback('CASE-1', 7);

    expect(get).toHaveBeenNthCalledWith(1, '/api/v1/staff-payables/historical-payouts/CASE-1/7', expect.objectContaining({ token: 'session-token' }));
    expect(post).toHaveBeenNthCalledWith(1, '/api/v1/staff-payables/historical-payouts/preview', intent, expect.objectContaining({ token: 'session-token' }));
    expect(post).toHaveBeenNthCalledWith(2, '/api/v1/staff-payables/historical-payouts/apply', expect.objectContaining({ expected_staff_payables_version: 3 }), expect.objectContaining({ token: 'session-token' }));
    expect(get).toHaveBeenNthCalledWith(2, '/api/v1/staff-payables/historical-payouts/CASE-1/7/readback', expect.objectContaining({ token: 'session-token' }));
  });

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
    expect(await screen.findByText(/Fresh readback：Staff Payables 已結清/)).toBeInTheDocument();
  });
});
