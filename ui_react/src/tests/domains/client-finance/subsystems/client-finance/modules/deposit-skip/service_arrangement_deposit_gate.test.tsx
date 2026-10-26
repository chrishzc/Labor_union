import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { depositSkipClient } from '../../../../../../../api/client_finance/deposit_skip_client';
import { ServiceArrangementDepositGate } from '../../../../../../../components/ServiceArrangementDepositGate';

afterEach(() => vi.restoreAllMocks());
const locked = { case_no: 'CASE-001', expected_account_version: 3, resulting_account_version: 4, deposit_required_ntd: 12000, deposit_net_received_ntd: 0, unpaid_progression_allowed: false, mutates: true, blockers: [], preview_fingerprint: 'a'.repeat(64) };

it('one click reads fresh eligibility, applies and verifies the unpaid gate without a reason form', async () => {
  vi.spyOn(depositSkipClient, 'query').mockResolvedValueOnce({ ...locked, account_version: 3 }).mockResolvedValue({ ...locked, account_version: 4, unpaid_progression_allowed: true });
  vi.spyOn(depositSkipClient, 'preview').mockResolvedValue(locked);
  const apply = vi.spyOn(depositSkipClient, 'apply').mockResolvedValue({ case_no: 'CASE-001', account_version: 4, unpaid_progression_allowed: true, replayed: false });
  const committed = vi.fn();
  render(<ServiceArrangementDepositGate caseNo="CASE-001" onCommitted={committed} />);
  fireEvent.click(await screen.findByRole('button', { name: '未付款人工放行' }));
  await screen.findByText('已解除・未付款人工放行');
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(apply).toHaveBeenCalledWith('CASE-001', locked, '', expect.stringMatching(/^deposit-skip-CASE-001-/));
  expect(screen.getByText(/已核銷 NT\$ 0/)).toBeInTheDocument();
  expect(committed).toHaveBeenCalledOnce();
});

it('recovers an unknown result with the same immutable command and only reports success after readback', async () => {
  vi.spyOn(depositSkipClient, 'query').mockResolvedValueOnce({ ...locked, account_version: 3 }).mockResolvedValue({ ...locked, account_version: 4, unpaid_progression_allowed: true });
  vi.spyOn(depositSkipClient, 'preview').mockResolvedValue(locked);
  const apply = vi.spyOn(depositSkipClient, 'apply').mockRejectedValueOnce(new Error('network lost after apply')).mockResolvedValue({ case_no: 'CASE-001', account_version: 4, unpaid_progression_allowed: true, replayed: true });
  const committed = vi.fn();
  const guarded = vi.fn();
  render(<ServiceArrangementDepositGate caseNo="CASE-001" onCommitted={committed} onBusyChange={guarded} />);
  fireEvent.click(await screen.findByRole('button', { name: '未付款人工放行' }));
  const recover = await screen.findByRole('button', { name: '確認原放行處理結果' });
  expect(committed).not.toHaveBeenCalled();
  expect(guarded).toHaveBeenLastCalledWith(true);
  fireEvent.click(recover);
  await waitFor(() => expect(committed).toHaveBeenCalledOnce());
  expect(apply.mock.calls[0]).toEqual(apply.mock.calls[1]);
  expect(guarded).toHaveBeenLastCalledWith(false);
});
