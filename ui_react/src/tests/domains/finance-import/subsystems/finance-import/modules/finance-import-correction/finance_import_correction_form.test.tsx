import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { FinanceImportCorrectionForm } from '../../../../../../../components/FinanceImportCorrectionForm';
import { financeImportCorrectionClient as corrections, financeRefundBlockerMessage } from '../../../../../../../api/finance_import/finance_import_correction_client';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { ordersQueryClient } from '../../../../../../../api/orders/order_query_client';
import { clientSettlementRemediationClient } from '../../../../../../../api/client_finance/client_settlement_remediation_client';
import { subsidyPeriodClient } from '../../../../../../../api/government_subsidy/period_reconciliation_client';

vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderSummaries: vi.fn() } }));
vi.mock('../../../../../../../api/client_finance/client_receipt_query_client', () => ({ clientReceiptQueryClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/client_finance/client_settlement_remediation_client', () => ({ clientSettlementRemediationClient: { query: vi.fn() } }));
vi.mock('../../../../../../../api/finance_import/finance_import_correction_client', async importOriginal => ({
  ...await importOriginal<typeof import('../../../../../../../api/finance_import/finance_import_correction_client')>(),
  financeImportCorrectionClient: { preview: vi.fn(), apply: vi.fn(), queryOutcome: vi.fn() },
}));
vi.mock('../../../../../../../api/government_subsidy/period_reconciliation_client', () => ({ subsidyPeriodClient: { query: vi.fn(), difference: vi.fn() } }));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({ items: [{ case_no: 'CASE-1', client_name: '測試客戶一' }, { case_no: 'CASE-2', client_name: '測試客戶二' }], next_cursor: null } as never);
  vi.mocked(clientReceiptQueryClient.query).mockResolvedValue({ case_no: 'CASE-1', obligations: [{ obligation_identity: 'obligation:1', payment_stage: 'deposit', amount_due_ntd: 100 }] } as never);
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', batch_identity: 'batch:1', classification_type: 'client_receipt', bank_amount_ntd: 100, allocations: [{ obligation_identity: 'obligation:1', amount_ntd: 100 }] }, preview_fingerprint: 'a'.repeat(64) } as never);
  vi.mocked(corrections.apply).mockResolvedValue({ job_id: 'job:1' } as never);
  vi.mocked(corrections.queryOutcome).mockResolvedValue({ status: 'succeeded', receipt: null } as never);
  vi.mocked(subsidyPeriodClient.query).mockResolvedValue({
    period: { unit: 'quarter', year: 2026, index: 1 },
    version: 1,
    label: '115年第1季',
    lines: [
      { case_no: 'CASE-1', service_end_date: '2026-03-31', amount_ntd: 5000, unavailable_reason: null },
    ],
    total_ntd: 5000,
    coverage: [],
    blocked_cases: [],
    recorded_lines: [],
    changed_cases: [],
    can_reconcile: true,
  } as never);
  vi.mocked(subsidyPeriodClient.difference).mockResolvedValue({
    period: { unit: 'quarter', year: 2026, index: 1 },
    version: 2,
    label: '115年第1季',
    lines: [
      { case_no: 'CASE-1', service_end_date: '2026-03-31', amount_ntd: 5000, unavailable_reason: null },
    ],
    total_ntd: 5000,
    coverage: [
      { receipt_id: 1, period: { unit: 'quarter', year: 2026, index: 1 }, amount_ntd: 5000, recovered_advance_ntd: 0, label: '115年第1季', settled: true },
    ],
    blocked_cases: [],
    recorded_lines: [
      { case_no: 'CASE-1', service_end_date: '2026-03-31', amount_ntd: 5000, unavailable_reason: null },
    ],
    changed_cases: [],
    can_reconcile: false,
  } as never);
});

async function preview() {
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="bank sheet row 1" staff={[]} />);
  await screen.findByRole('option', { name: 'CASE-1｜測試客戶一' });
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-1' } });
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('更正原因（選填）'), { target: { value: '核對原始收款' } });
  fireEvent.click(screen.getByText('預覽核銷'));
}

it('previews before confirmation and requires a matching terminal receipt before declaring completion', async () => {
  await preview();
  expect(await screen.findByText(/本次核銷 NT\$/)).toHaveTextContent('100');
  expect(corrections.apply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '確認核銷' }));
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
  expect(screen.getByRole('button', { name: '預覽核銷' })).toBeEnabled();
  fireEvent.change(screen.getByLabelText('案件編號'), { target: { value: 'CASE-2' } });
  expect(screen.getByRole('button', { name: '預覽核銷' })).toBeDisabled();
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
  expect(screen.getByRole('button', { name: '預覽核銷' })).toBeDisabled();
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

it('shows refund type, scheduled date and amount before manually selecting multiple refunds', async () => {
  vi.mocked(clientSettlementRemediationClient.query).mockResolvedValue({case_no:'CASE-1',refund_obligations:[
    {obligation_identity:'refund:1',obligation_type:'refund',due_date:'2026-10-15',amount_due_ntd:6000},
    {obligation_identity:'refund:2',obligation_type:'adjustment',due_date:null,amount_due_ntd:6000},
  ]} as never);
  vi.mocked(corrections.preview).mockResolvedValue({candidate:{row_identity:'row:1',batch_identity:'batch:1',classification_type:'client_refund',
    bank_amount_ntd:11900,allocations:[{obligation_identity:'refund:1',amount_ntd:6000},{obligation_identity:'refund:2',amount_ntd:6000}],
    refund_summary:{transfer_fee_ntd:100,remaining_ntd:0}},preview_fingerprint:'a'.repeat(64)} as never);
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="synthetic refund row" staff={[]} initialKind="client_refund" initialCaseNo="CASE-1" />);
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox',{name:/待退 NT\$ 6,000.*一般退款.*預計退款日 2026-10-15/}));
  fireEvent.click(screen.getByRole('checkbox',{name:/退款調整.*預計退款日 未設定/}));
  fireEvent.click(screen.getByRole('button',{name:'預覽核銷'}));
  expect(await screen.findByLabelText('客戶退款核銷預覽')).toHaveTextContent('NT$ 11,900');
  expect(corrections.preview).toHaveBeenCalledWith(expect.objectContaining({target_obligation_identities:['refund:1','refund:2'],allow_partial_refund_recovery:false}));
});

it.each(['client_refund_recipient_account_ambiguous', 'client_refund_recipient_account_mismatch', 'client_refund_source_account_missing', 'due_date_missing', 'bank_transaction_date_missing', 'bank_currency_not_twd', 'subsidy_advance_not_due', 'client_subsidy_memo_case_mismatch', 'client_subsidy_memo_staff_matched', 'refund_requires_exact_settlement', 'allocation_exceeds_obligation'])(
  'shows the actual failed refund reason instead of a generic refresh message: %s', async code => {
    const kind = code.startsWith('subsidy_') || code.startsWith('client_subsidy_') ? 'client_subsidy_return' : 'client_refund';
    vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', batch_identity: 'batch:1',
      classification_type: kind, bank_amount_ntd: 100, allocations: [{ obligation_identity: 'refund:1', amount_ntd: 100 }] },
      preview_fingerprint: 'a'.repeat(64) } as never);
    vi.mocked(corrections.queryOutcome).mockResolvedValue({ job_id: 'job:1', status: 'failed', receipt: null, failure_code: code } as never);
    const onPosted = vi.fn();
    render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="synthetic bank row" staff={[]} initialKind={kind}
      initialCaseNo="CASE-1" lockedObligations={[{ id: 'refund:1', label: '合成退款' }]} onPosted={onPosted} />);
    fireEvent.click(await screen.findByRole('button', { name: '預覽核銷' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認核銷' }));
    expect(await screen.findByText(financeRefundBlockerMessage(code, kind))).toBeInTheDocument();
    expect(onPosted).not.toHaveBeenCalled();
    expect(screen.queryByText('更正未完成，請重新查詢帳務資料。')).not.toBeInTheDocument();
  },
);

it.each((['client_refund', 'client_subsidy_return'] as const).flatMap(kind => [0, 30, 100].map(fee => ({kind, fee}))))('shows owner $kind cash, fee $fee and remaining balance without switching to partial mode', async ({kind, fee}) => {
  vi.mocked(corrections.preview).mockResolvedValue({ candidate: { row_identity: 'row:1', batch_identity: 'batch:1', classification_type: kind,
    bank_amount_ntd: 12000-fee, allocations: [{ obligation_identity: 'refund:1', amount_ntd: 12000 }],
    refund_summary: { transfer_fee_ntd: fee, remaining_ntd: 0 } }, preview_fingerprint: 'a'.repeat(64) } as never);
  vi.mocked(corrections.queryOutcome).mockResolvedValue({ status: 'succeeded', receipt: {
    row_identity: 'row:1', batch_identity: 'batch:1', preview_fingerprint: 'a'.repeat(64),
  } } as never);
  vi.mocked(clientSettlementRemediationClient.query).mockResolvedValue({ case_no: 'CASE-1', refund_obligations: [], subsidy_return_obligations: [] } as never);
  const posted = vi.fn();
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="synthetic bank row" staff={[]} initialKind={kind}
    initialCaseNo="CASE-1" lockedObligations={[{ id: 'refund:1', label: '合成退款' }]} onPosted={posted} />);
  expect(screen.getByLabelText('退款核銷方式')).toHaveValue('exact');
  if (kind === 'client_subsidy_return') expect(screen.getByRole('option', {name: '退款超出，另列待追回款'})).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '預覽核銷' }));
  const summary = await screen.findByLabelText(kind === 'client_refund' ? '客戶退款核銷預覽' : '客戶補助退款核銷預覽');
  expect(within(summary).getByText('銀行實付').nextElementSibling).toHaveTextContent(`NT$ ${(12000-fee).toLocaleString()}`);
  expect(within(summary).getByText('匯款手續費').nextElementSibling).toHaveTextContent(`NT$ ${fee}`);
  expect(within(summary).getByText('本次核銷').nextElementSibling).toHaveTextContent('NT$ 12,000');
  expect(within(summary).getByText('核銷後待退餘額（本次選取款項）').nextElementSibling).toHaveTextContent('NT$ 0');
  expect(corrections.preview).toHaveBeenCalledWith(expect.objectContaining({ allow_partial_refund_recovery: false }));
  fireEvent.click(screen.getByRole('button', { name: '確認核銷' }));
  await waitFor(() => expect(posted).toHaveBeenCalledOnce());
});

it('offers subsidy partial settlement explicitly and shows the owner remaining balance', async () => {
  vi.mocked(clientSettlementRemediationClient.query).mockResolvedValue({case_no:'CASE-1',subsidy_return_obligations:[{obligation_identity:'subsidy:1',amount_due_ntd:2000}]} as never);
  vi.mocked(corrections.queryOutcome).mockResolvedValue({status:'succeeded',receipt:{row_identity:'row:1',batch_identity:'batch:1',preview_fingerprint:'a'.repeat(64)}} as never);
  vi.mocked(corrections.preview).mockResolvedValue({candidate:{row_identity:'row:1',batch_identity:'batch:1',
    classification_type:'client_subsidy_return',bank_amount_ntd:10000,allocations:[{obligation_identity:'subsidy:1',amount_ntd:10000}],
    refund_summary:{transfer_fee_ntd:0,remaining_ntd:2000}},preview_fingerprint:'a'.repeat(64)} as never);
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="合成補助出款" staff={[]} initialKind="client_subsidy_return"
    initialCaseNo="CASE-1" lockedObligations={[{id:'subsidy:1',label:'補助待退12,000元'}]} />);
  expect(screen.getByLabelText('退款核銷方式')).toHaveValue('exact');
  fireEvent.change(screen.getByLabelText('退款核銷方式'),{target:{value:'partial'}});
  fireEvent.click(screen.getByRole('button',{name:'預覽核銷'}));
  const summary=await screen.findByLabelText('客戶補助退款核銷預覽');
  expect(within(summary).getByText('銀行實付').nextElementSibling).toHaveTextContent('NT$ 10,000');
  expect(within(summary).getByText('匯款手續費').nextElementSibling).toHaveTextContent('NT$ 0');
  expect(within(summary).getByText('核銷後待退餘額（本次選取款項）').nextElementSibling).toHaveTextContent('NT$ 2,000');
  expect(corrections.preview).toHaveBeenCalledWith(expect.objectContaining({classification_type:'client_subsidy_return',
    allow_partial_refund_recovery:true,allow_refund_overage_recovery:false}));
  fireEvent.click(screen.getByRole('button',{name:'確認核銷'}));
  expect(await screen.findByText('退款核銷完成；已更新剩餘待退款，後續清冊只列餘額。')).toBeInTheDocument();
  expect(clientSettlementRemediationClient.query).toHaveBeenCalledWith('CASE-1',{includeNotDue:true});
  expect(screen.getByLabelText(/待退 NT\$ 2,000/)).toBeInTheDocument();
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
  fireEvent.click(screen.getByText('預覽核銷'));
  fireEvent.click(await screen.findByRole('button', { name: '確認核銷' }));
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

it.each(['client_refund','client_subsidy_return'] as const)('requires an explicit %s overage choice to delegate excess refund cash to recovery', async kind => {
  vi.mocked(clientSettlementRemediationClient.query)
    .mockResolvedValueOnce({case_no:'CASE-1', refund_obligations:kind==='client_refund'?[{obligation_identity:'refund:1',amount_due_ntd:1000}]:[],subsidy_return_obligations:kind==='client_subsidy_return'?[{obligation_identity:'refund:1',amount_due_ntd:1000}]:[]} as never)
    .mockResolvedValue({case_no:'CASE-1', refund_obligations:[],subsidy_return_obligations:[]} as never);
  vi.mocked(corrections.preview).mockResolvedValue({candidate:{
    row_identity:'row:1', batch_identity:'batch:1', classification_type:kind,
    bank_amount_ntd:1200, allocations:[{obligation_identity:'refund:1',amount_ntd:1000}],
    allow_refund_overage_recovery:true,
    refund_summary:{transfer_fee_ntd:0,remaining_ntd:0},
  }, preview_fingerprint:'a'.repeat(64)} as never);
  vi.mocked(corrections.queryOutcome).mockResolvedValue({status:'succeeded',receipt:{
    row_identity:'row:1',batch_identity:'batch:1',preview_fingerprint:'a'.repeat(64),
  }} as never);
  render(<FinanceImportCorrectionForm rowIdentity="row:1" sourceLabel="synthetic bank row" staff={[]} initialKind={kind} />);
  await screen.findByRole('option',{name:'CASE-1｜測試客戶一'});
  fireEvent.change(screen.getByLabelText('案件編號'),{target:{value:'CASE-1'}});
  fireEvent.click(screen.getByText('查詢待核銷款項'));
  fireEvent.click(await screen.findByRole('checkbox'));
  expect(screen.getByLabelText('退款核銷方式')).toHaveValue('exact');
  expect(corrections.preview).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('退款核銷方式'),{target:{value:'overage'}});
  fireEvent.click(screen.getByText('預覽核銷'));
  if(kind==='client_subsidy_return')expect((await screen.findByText('超退待追回')).nextElementSibling).toHaveTextContent('NT$ 200');
  fireEvent.click(await screen.findByRole('button', { name: '確認核銷' }));
  await screen.findByText('退款核銷完成；超退金額已另列待追回款，請至案件帳務查看。');
  expect(corrections.preview).toHaveBeenCalledWith(expect.objectContaining({
    classification_type:kind,target_obligation_identities:['refund:1'],
    allow_refund_overage_recovery:true,allow_partial_refund_recovery:false,
  }));
  expect(corrections.apply).toHaveBeenCalledOnce();
});

it('supports government subsidy whole-period reconciliation via correction form', async () => {
  render(
    <FinanceImportCorrectionForm
      rowIdentity="finance-import-row:42"
      sourceLabel="bank sheet row 42"
      staff={[]}
      bankAmount={5000}
      initialKind="government_subsidy"
    />
  );
  await screen.findByText('115年第1季');
  expect(screen.getByText(/本期目前計算應收/)).toBeInTheDocument();
  expect(subsidyPeriodClient.query).toHaveBeenCalled();

  const confirmCheckbox = screen.getByRole('checkbox', { name: /我已確認整期期別、金額與處理方式無誤/ });
  fireEvent.click(confirmCheckbox);

  const reconcileBtn = screen.getByRole('button', { name: '確認核銷本期政府入款' });
  expect(reconcileBtn).toBeEnabled();
  fireEvent.click(reconcileBtn);

  await screen.findByText('政府補助整期入款核銷完成！已確認核銷收據。');
  expect(subsidyPeriodClient.difference).toHaveBeenCalledWith(expect.objectContaining({
    unit: 'quarter',
    year: expect.any(Number),
    index: expect.any(Number),
    action: 'initial_receipt',
    bank_row_id: 42,
    handling: 'exact',
  }));
});


it('preserves the over-refund operation for the locked bank row and its confirmed case obligation', async () => {
  render(<FinanceImportCorrectionForm rowIdentity="finance-import-row:42" sourceLabel="TX"
    staff={[]} initialKind="client_refund" initialCaseNo="CASE-1"
    lockedObligations={[{ id: 'refund:1', label: '本案退款' }]} />);

  expect(screen.getByRole('checkbox', { name: '本案退款' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: '本案退款' })).toBeDisabled();
  expect(screen.queryByLabelText('案件編號')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('退款核銷方式'), { target: { value: 'overage' } });
  fireEvent.click(screen.getByRole('button', { name: '預覽核銷' }));

  expect(corrections.preview).toHaveBeenCalledWith(expect.objectContaining({
    row_identity: 'finance-import-row:42', classification_type: 'client_refund',
    target_obligation_identities: ['refund:1'], allow_refund_overage_recovery: true,
  }));
  expect(corrections.apply).not.toHaveBeenCalled();
});
