import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinanceImportCorrectionForm } from '../../../../../../../components/FinanceImportCorrectionForm';
import { financeImportCorrectionClient as corrections } from '../../../../../../../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { clientSettlementRemediationClient } from '../../../../../../../api/client_finance/client_settlement_remediation_client';

vi.mock('../../../../../../../api/client_finance/client_receipt_query_client', () => ({ clientReceiptQueryClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/client_finance/client_settlement_remediation_client', () => ({ clientSettlementRemediationClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/finance_import/finance_import_correction_client', () => ({ financeImportCorrectionClient: { preview: vi.fn(), apply: vi.fn(), queryOutcome: vi.fn() } }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ case_no: 'CASE-1', obligations: [{ obligation_identity: 'obligation:1', payment_stage: 'deposit', amount_due_ntd: 100 }] } as never);
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', batch_identity: 'batch:1', classification_type: 'client_receipt', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:1', amount_ntd: 100 }] }, preview_fingerprint: 'a'.repeat(64) } as never);
  vi.mocked(corrections.apply).mockResolvedValue({ job_id: 'job:1' } as never);
});

async function preview() {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-1' } });
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('更正原因（選填）'), { target: { value: '核對原始收款' } });
  fireEvent.click(screen.getByText('儲存更正並核銷'));
}

it('uses one click and requires a matching terminal receipt before declaring completion', async () => {
  await preview();
  expect(await screen.findByText(/本次核銷 NT\$/)).toHaveTextContent('100');
  await waitFor(() => expect(corrections.apply).toHaveBeenCalledOnce());
  expect(await screen.findByText(/尚未完成核銷/)).toBeInTheDocument();
  vi.mocked(corrections.queryOutcome).mockResolvedValue({ status: 'succeeded', receipt: { row_identity: 'row:1', batch_identity: 'batch:1', preview_fingerprint: 'a'.repeat(64) } } as never);
  fireEvent.click(screen.getByText('重新查詢更正結果'));
  expect(await screen.findByText('帳務更正完成，已確認核銷收據。')).toBeInTheDocument();
  expect(corrections.apply).toHaveBeenCalledTimes(1);
});

it('clears old selections when the target changes before saving', async () => {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-1' } });
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  expect(screen.getByRole('button', { name: '儲存更正並核銷' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-2' } });
  expect(screen.getByRole('button', { name: '儲存更正並核銷' })).toBeDisabled();
  expect(corrections.apply).not.toHaveBeenCalled();
});

it('rejects unselected allocations and does not offer Apply', async () => {
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', classification_type: 'client_receipt', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'other:2', amount_ntd: 100 }] } } as never);
  await preview();
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('未選取的款項'));
  expect(corrections.apply).not.toHaveBeenCalled();
});

it('offers a partial customer refund from the original bank row, including not-yet-due refunds', async () => {
  vi.mocked(clientSettlementRemediationClient.query).mockResolvedValueOnce({
    case_no: 'CASE-1', refund_obligations: [{ obligation_identity: 'refund:1', amount_due_ntd: 3000 }],
  } as never).mockResolvedValue({case_no: 'CASE-1', refund_obligations: [{obligation_identity: 'refund:1', amount_due_ntd: 1800}]} as never);
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: {
    row_identity: 'row:1', batch_identity: 'batch:1', classification_type: 'client_refund',
    bank_amount_ntd: 1200, allocations: [{ obligation_identity: 'refund:1', amount_ntd: 1200 }],
  }, preview_fingerprint: 'a'.repeat(64) } as never);
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} initialKind="client_refund" />);
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-1' } });
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('退款核銷方式'), { target: { value: 'partial' } });
  fireEvent.click(screen.getByText('儲存更正並核銷'));
  await waitFor(() => expect(corrections.apply).toHaveBeenCalledOnce());
  expect(clientSettlementRemediationClient.query).toHaveBeenCalledWith('CASE-1', { includeNotDue: true });
  expect(corrections.preview).toHaveBeenCalledWith(expect.objectContaining({
    classification_type: 'client_refund', target_obligation_identities: ['refund:1'],
    allow_partial_refund_recovery: true, allow_refund_overage_recovery: false,
  }));
  expect(await screen.findByText(/尚未完成核銷/)).toBeInTheDocument();
  vi.mocked(corrections.queryOutcome).mockResolvedValue({status: 'succeeded', receipt: {
    row_identity: 'row:1', batch_identity: 'batch:1', preview_fingerprint: 'a'.repeat(64),
  }} as never);
  fireEvent.click(screen.getByText('重新查詢更正結果'));
  expect(await screen.findByText('退款核銷完成；已更新剩餘待退款，後續清冊只列餘額。')).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /待退 NT\$ 1,800/ })).toBeInTheDocument();
  expect(corrections.apply).toHaveBeenCalledOnce();
});
