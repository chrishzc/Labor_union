import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinanceImportCorrectionForm } from '../../../../../../../components/FinanceImportCorrectionForm';
import { financeImportCorrectionClient as corrections } from '../../../../../../../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';

vi.mock('../../../../../../../api/client_finance/client_receipt_query_client', () => ({ clientReceiptQueryClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/finance_import/finance_import_correction_client', () => ({ financeImportCorrectionClient: { preview: vi.fn(), apply: vi.fn(), queryOutcome: vi.fn() } }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ case_no: 'CASE-1', obligations: [{ obligation_identity: 'obligation:1', payment_stage: 'deposit', amount_due_ntd: 100 }] } as never);
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', classification_type: 'client_receipt', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:1', amount_ntd: 100 }] }, preview_fingerprint: 'a'.repeat(64) } as never);
  vi.mocked(corrections.apply).mockResolvedValue({ job_id: 'job:1' } as never);
});

async function preview() {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-1' } });
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('更正原因'), { target: { value: '核對原始收款' } });
  fireEvent.click(screen.getByText('預覽更正'));
}

it('requires explicit confirmation and a matching terminal receipt before declaring completion', async () => {
  await preview();
  expect(await screen.findByText(/本次核銷 NT\$/)).toHaveTextContent('100');
  expect(corrections.apply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText('確認更正並核銷'));
  expect(await screen.findByText(/尚未完成核銷/)).toBeInTheDocument();
  vi.mocked(corrections.queryOutcome).mockResolvedValue({ status: 'succeeded', receipt: { row_identity: 'row:1', preview_fingerprint: 'a'.repeat(64) } } as never);
  fireEvent.click(screen.getByText('重新查詢更正結果'));
  expect(await screen.findByText('帳務更正完成，已確認核銷收據。')).toBeInTheDocument();
  expect(corrections.apply).toHaveBeenCalledTimes(1);
});

it('invalidates preview when the target changes', async () => {
  await preview();
  await screen.findByText('確認更正並核銷');
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-2' } });
  expect(screen.queryByText('確認更正並核銷')).not.toBeInTheDocument();
  expect(corrections.apply).not.toHaveBeenCalled();
});

it('rejects unselected allocations and does not offer Apply', async () => {
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', classification_type: 'client_receipt', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'other:2', amount_ntd: 100 }] } } as never);
  await preview();
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('未選取的款項'));
  expect(screen.queryByText('確認更正並核銷')).not.toBeInTheDocument();
});
