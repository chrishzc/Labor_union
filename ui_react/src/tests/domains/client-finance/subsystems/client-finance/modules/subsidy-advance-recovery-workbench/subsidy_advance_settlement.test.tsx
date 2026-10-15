/** ADVREC human confirmation, authoritative readback and unknown outcomes. */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SubsidyAdvanceSettlementPanel } from '../../../../../../../components/SubsidyAdvanceSettlementPanel';
import { subsidyAdvanceSettlementClient as client, type AdvanceSettlementRow } from '../../../../../../../api/client_finance/subsidy_advance_settlement_client';
import { ApiHttpError, ApiNetworkError } from '../../../../../../../api/shared/typed_errors';

vi.mock('../../../../../../../api/client_finance/subsidy_advance_settlement_client', () => ({
  subsidyAdvanceSettlementClient: { queryAll: vi.fn(), preview: vi.fn(), apply: vi.fn() },
}));

const row: AdvanceSettlementRow = {
  advance_id: 10, case_no: 'TEST-001', client_name: '測試客戶', advanced_on: '2026-03-15',
  advance_amount_ntd: 12000, government_received_ntd: 12000, received_on: '2026-04-01',
  recovered_amount_ntd: 0, status: 'ready', review_reason: null,
};
const preview = { row, account_version: 3, batch_version: 5, preview_fingerprint: 'a'.repeat(64) };
const recovered = { ...row, recovered_amount_ntd: 12000, status: 'recovered' as const };

beforeEach(() => {
  vi.mocked(client.queryAll).mockReset().mockResolvedValue([row]);
  vi.mocked(client.preview).mockReset().mockResolvedValue(preview);
  vi.mocked(client.apply).mockReset().mockResolvedValue({ advance_id: 10, case_no: row.case_no, recovered_amount_ntd: 12000, account_version: 4 });
});

async function confirmPreview() {
  fireEvent.click(await screen.findByRole('button', { name: '預覽 TEST-001 銷帳' }));
  const apply = await screen.findByRole('button', { name: '確認銷帳' });
  expect(apply).toBeDisabled();
  fireEvent.change(screen.getByLabelText('核對說明'), { target: { value: '已核對政府撥款與原墊款證據' } });
  fireEvent.click(screen.getByLabelText('我已核對原墊款與政府入款，確認建立回收銷帳。'));
  return apply;
}

describe('subsidy advance settlement page', () => {
  it('confirms once and declares success only after fresh recovered readback', async () => {
    vi.mocked(client.queryAll).mockResolvedValueOnce([row]).mockResolvedValue([recovered]);
    render(<SubsidyAdvanceSettlementPanel onOpenImport={vi.fn()} />);
    fireEvent.click(await confirmPreview());
    await screen.findByText(/TEST-001 已銷帳 NT\$ 12,000，已重新查詢確認/);
    expect(client.apply).toHaveBeenCalledTimes(1);
    expect(client.apply).toHaveBeenCalledWith(10, {
      expected_account_version: 3, expected_batch_version: 5, preview_fingerprint: 'a'.repeat(64),
      reason: '已核對政府撥款與原墊款證據',
    }, expect.stringMatching(/^advance-settlement:/), expect.any(AbortSignal));
    expect(screen.queryByRole('button', { name: '確認銷帳' })).not.toBeInTheDocument();
  });

  it('keeps an unconfirmed result blocked and reuses the exact command after readback', async () => {
    vi.mocked(client.apply).mockRejectedValueOnce(new ApiNetworkError('network'));
    render(<SubsidyAdvanceSettlementPanel onOpenImport={vi.fn()} />);
    fireEvent.click(await confirmPreview());
    const check = await screen.findByRole('button', { name: '重新查詢銷帳結果' });
    expect(screen.getByRole('button', { name: '確認銷帳' })).toBeDisabled();
    expect(screen.getByLabelText('核對說明')).toBeDisabled();
    fireEvent.click(check);
    await screen.findByText(/仍未銷帳，可安全重試原操作/);
    vi.mocked(client.queryAll).mockResolvedValue([recovered]);
    fireEvent.click(screen.getByRole('button', { name: '確認銷帳' }));
    await screen.findByText(/已重新查詢確認/);
    const calls = vi.mocked(client.apply).mock.calls;
    expect(calls[0].slice(0, 3)).toEqual(calls[1].slice(0, 3));
  });

  it('does not treat a successful HTTP receipt as settled without matching readback', async () => {
    vi.mocked(client.queryAll).mockResolvedValueOnce([row]).mockResolvedValue([{ ...row, status: 'review_required', review_reason: 'amount_mismatch' }]);
    render(<SubsidyAdvanceSettlementPanel onOpenImport={vi.fn()} />);
    fireEvent.click(await confirmPreview());
    await screen.findByText(/尚無法確認本次銷帳結果/);
    expect(screen.getByRole('button', { name: '確認銷帳' })).toBeDisabled();
    expect(screen.queryByText(/已銷帳 NT\$/)).not.toBeInTheDocument();
  });

  it('invalidates a stale preview and reloads without applying another command', async () => {
    vi.mocked(client.apply).mockRejectedValue(new ApiHttpError(409, 'stale_preview', 'stale'));
    render(<SubsidyAdvanceSettlementPanel onOpenImport={vi.fn()} />);
    fireEvent.click(await confirmPreview());
    await waitFor(() => expect(client.queryAll).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('button', { name: '確認銷帳' })).not.toBeInTheDocument();
    expect(client.apply).toHaveBeenCalledTimes(1);
  });

  it('shows review reasons and never offers settlement for waiting or mismatched records', async () => {
    vi.mocked(client.queryAll).mockResolvedValue([
      { ...row, status: 'review_required', review_reason: 'amount_mismatch' },
      { ...row, advance_id: 11, case_no: 'TEST-002', status: 'waiting_receipt', government_received_ntd: 0 },
    ]);
    render(<SubsidyAdvanceSettlementPanel onOpenImport={vi.fn()} />);
    await screen.findByText('政府核准、入款或原墊款金額不一致。');
    expect(screen.queryByRole('button', { name: /預覽 .* 銷帳/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('銷帳狀態'), { target: { value: 'waiting_receipt' } });
    expect(screen.queryByText('TEST-001')).not.toBeInTheDocument();
    expect(screen.getByText('TEST-002')).toBeInTheDocument();
  });
});
