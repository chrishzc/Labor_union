import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { depositSkipClient } from '../../../../../../../api/client_finance/deposit_skip_client';
import { ClientDepositSkipActions } from '../../../../../../../components/ClientDepositSkipActions';

vi.mock('../../../../../../../api/client_finance/deposit_skip_client', () => ({
  depositSkipClient: { preview: vi.fn(), apply: vi.fn() },
}));

const preview = {
  case_no: 'CASE-001',
  expected_account_version: 3,
  resulting_account_version: 4,
  deposit_required_ntd: 12000,
  deposit_net_received_ntd: 0,
  unpaid_progression_allowed: true,
  mutates: true,
  blockers: [],
  preview_fingerprint: 'a'.repeat(64),
};

describe('ClientDepositSkipActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(depositSkipClient.preview).mockResolvedValue(preview);
    vi.mocked(depositSkipClient.apply).mockResolvedValue({
      case_no: 'CASE-001', account_version: 4, unpaid_progression_allowed: true, replayed: false,
    });
  });

  it.each(['', '公會突發狀況測試'])('saves the audited skip in one click with optional reason %j', async (reason) => {
    const onCommitted = vi.fn();
    render(<ClientDepositSkipActions caseNo="CASE-001" onCommitted={onCommitted} />);
    fireEvent.change(screen.getByLabelText('放行原因（選填）'), { target: { value: reason } });
    expect(depositSkipClient.apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '儲存未付訂金放行' }));
    await waitFor(() => expect(depositSkipClient.apply).toHaveBeenCalledWith('CASE-001', preview, reason, expect.stringMatching(/^deposit-skip-CASE-001-/)));
    expect(depositSkipClient.preview).toHaveBeenCalledOnce();
    expect(onCommitted).toHaveBeenCalledOnce();
    expect(screen.getByRole('status')).toHaveTextContent('訂金仍維持未付');
  });

  it('shows the backend eligibility blocker and never offers apply', async () => {
    vi.mocked(depositSkipClient.preview).mockResolvedValue({
      ...preview,
      mutates: false,
      resulting_account_version: 3,
      blockers: ['deposit_skip.general_citizen_required'],
    });
    render(<ClientDepositSkipActions caseNo="CASE-001" />);
    fireEvent.change(screen.getByLabelText('放行原因（選填）'), { target: { value: '測試' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存未付訂金放行' }));

    await screen.findByText('僅一般市民可由此入口人工跳過訂金。');
    expect(screen.queryByRole('button', { name: '確認未付仍放行' })).not.toBeInTheDocument();
  });
});
