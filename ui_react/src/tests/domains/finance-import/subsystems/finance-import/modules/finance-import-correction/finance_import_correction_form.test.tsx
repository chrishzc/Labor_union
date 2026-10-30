import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinanceImportCorrectionForm } from '../../../../../../../components/FinanceImportCorrectionForm';
import { financeImportCorrectionClient as corrections } from '../../../../../../../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { clientSettlementRemediationClient } from '../../../../../../../api/client_finance/client_settlement_remediation_client';

vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderSummaries: vi.fn() } }));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client', () => ({ clientReceiptQueryClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/client_finance/client_settlement_remediation_client', () => ({ clientSettlementRemediationClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/finance_import/finance_import_correction_client', () => ({ financeImportCorrectionClient: { preview: vi.fn(), apply: vi.fn(), queryOutcome: vi.fn() } }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({ items: [{ case_no: 'CASE-1', client_name: '測試客戶一' }, { case_no: 'CASE-2', client_name: '測試客戶二' }], next_cursor: null } as never);
  vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ case_no: 'CASE-1', obligations: [{ obligation_identity: 'obligation:1', payment_stage: 'deposit', amount_due_ntd: 100 }] } as never);
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', batch_identity: 'batch:1', classification_type: 'client_receipt', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:1', amount_ntd: 100 }] }, preview_fingerprint: 'a'.repeat(64) } as never);
  vi.mocked(corrections.apply).mockResolvedValue({ job_id: 'job:1' } as never);
  vi.mocked(corrections.queryOutcome).mockResolvedValue({ status: 'succeeded', receipt: null } as never);
});

async function preview() {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  await screen.findByRole('option', { name: 'CASE-1｜測試客戶一' });
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
  expect(await screen.findByText('更正收據尚未確認，不能判定完成。')).toBeInTheDocument();
  vi.mocked(corrections.queryOutcome).mockResolvedValue({ status: 'succeeded', receipt: { row_identity: 'row:1', batch_identity: 'batch:1', preview_fingerprint: 'a'.repeat(64) } } as never);
  fireEvent.click(screen.getByText('重新查詢更正結果'));
  expect(await screen.findByText('帳務更正完成，已確認核銷收據。')).toBeInTheDocument();
  expect(corrections.apply).toHaveBeenCalledTimes(1);
});

it('clears old selections when the target changes before saving', async () => {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  await screen.findByRole('option', { name: 'CASE-1｜測試客戶一' });
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-1' } });
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  expect(screen.getByRole('button', { name: '儲存更正並核銷' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-2' } });
  expect(screen.getByRole('button', { name: '儲存更正並核銷' })).toBeDisabled();
  expect(corrections.apply).not.toHaveBeenCalled();
});

it('searches partial case numbers and client names, pages results and only queries the selected exact case', async () => {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  await screen.findByRole('option', { name: 'CASE-1｜測試客戶一' });
  expect(screen.getByRole('button', { name: '查詢待核銷款項' })).toBeDisabled();
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce({ items: [{ case_no: 'CASE-2', client_name: '同名客戶' }], next_cursor: 'CASE-2' } as never);
  fireEvent.change(screen.getByLabelText('搜尋案件'), { target: { value: 'CASE-' } });
  await screen.findByRole('option', { name: 'CASE-2｜同名客戶' });
  expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith({ query_text: 'CASE-', page_size: 50 }, expect.anything());
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce({ items: [{ case_no: 'CASE-3', client_name: '同名客戶' }], next_cursor: null } as never);
  fireEvent.click(screen.getByRole('button', { name: '載入更多案件' }));
  await screen.findByRole('option', { name: 'CASE-3｜同名客戶' });
  expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith({ query_text: 'CASE-', page_size: 50, after_case_no: 'CASE-2' }, expect.anything());
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-3' } });
  fireEvent.click(screen.getByRole('button', { name: '查詢待核銷款項' }));
  await waitFor(() => expect(clientReceiptQueryClient.query).toHaveBeenCalledWith('CASE-3'));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('搜尋案件'), { target: { value: '測試客戶' } });
  expect(screen.getByRole('button', { name: '儲存更正並核銷' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '查詢待核銷款項' })).toBeDisabled();
  await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith({ query_text: '測試客戶', page_size: 50 }, expect.anything()));
});

it('ignores late search results and distinguishes failure from an empty result', async () => {
  let resolve!: (value: never) => void;
  vi.mocked(ordersQueryClient.getOrderSummaries).mockReturnValueOnce(new Promise(done => { resolve = done; }));
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledOnce());
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValueOnce({ items: [], next_cursor: null } as never);
  fireEvent.change(screen.getByLabelText('搜尋案件'), { target: { value: '不存在' } });
  await screen.findByText('找不到符合的案件，請改用其他編號或客戶姓名搜尋。');
  await act(async () => resolve({ items: [{ case_no: 'OLD', client_name: '舊結果' }], next_cursor: null } as never));
  await waitFor(() => expect(screen.queryByRole('option', { name: 'OLD｜舊結果' })).not.toBeInTheDocument());
  vi.mocked(ordersQueryClient.getOrderSummaries).mockRejectedValueOnce(new Error('offline'));
  fireEvent.change(screen.getByLabelText('搜尋案件'), { target: { value: '重試' } });
  await screen.findByRole('alert');
  expect(screen.queryByText('找不到符合的案件，請改用其他編號或客戶姓名搜尋。')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '重新載入案件' }));
  await screen.findByRole('option', { name: 'CASE-1｜測試客戶一' });
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
  await screen.findByRole('option', { name: 'CASE-1｜測試客戶一' });
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
  expect(await screen.findByText('更正收據尚未確認，不能判定完成。')).toBeInTheDocument();
  vi.mocked(corrections.queryOutcome).mockResolvedValue({status: 'succeeded', receipt: {
    row_identity: 'row:1', batch_identity: 'batch:1', preview_fingerprint: 'a'.repeat(64),
  }} as never);
  fireEvent.click(screen.getByText('重新查詢更正結果'));
  expect(await screen.findByText('退款核銷完成；已更新剩餘待退款，後續清冊只列餘額。')).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: /待退 NT\$ 1,800/ })).toBeInTheDocument();
  expect(corrections.apply).toHaveBeenCalledOnce();
});
