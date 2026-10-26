/** Agreed workspace composition, separate totals, exact case detail and recovery. */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FinancePage } from '../../../../../../pages/FinancePage';
import { ordersQueryClient } from '../../../../../../api/orders/order_query_client';
import { clientFinanceHistoryClient } from '../../../../../../api/client_finance/client_finance_history_client';
import { cashRequirementsQueryClient } from '../../../../../../api/accounts_payable/cash_requirements_query_client';
import { clientSubsidyReturnQueryClient } from '../../../../../../api/client_finance/client_subsidy_return_query_client';
import { subsidyPeriodClient,type SubsidyPeriod } from '../../../../../../api/government_subsidy/period_reconciliation_client';
import { subsidyAdvanceSettlementClient as recovery } from '../../../../../../api/client_finance/subsidy_advance_settlement_client';
import { ApiNetworkError } from '../../../../../../api/shared/typed_errors';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffPayablesQueryClient } from '../../../../../../api/staff_payables/staff_payables_query_client';

const caseNo = 'TEST-001';
const advance = { advance_id: 10, case_no: caseNo, client_name: '測試客戶', advanced_on: '2026-03-15', advance_amount_ntd: 12000,
  government_received_ntd: 12000, received_on: '2026-04-01', recovered_amount_ntd: 0, status: 'ready' as const, review_reason: null };
const caseCoverage={case_no:caseNo,service_end_date:'2026-01-20',amount_ntd:12000,coverage:[{receipt_id:9,label:'2026 年 第 1 季',amount_ntd:36000,recorded_case_amount_ntd:12000,recorded_service_end_date:'2026-01-20',recovered_advance_ntd:12000}]};
const periodView=(period:SubsidyPeriod)=>({period,version:1,label:`${period.year} 年 第 ${period.index} 季`,lines:[{case_no:caseNo,service_end_date:'2026-01-20',amount_ntd:12000,unavailable_reason:null}],total_ntd:12000,coverage:[],recorded_lines:[],changed_cases:[],blocked_cases:[],can_reconcile:true});
beforeEach(() => {
  vi.restoreAllMocks(); window.location.hash = '#finance';
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement) { this.setAttribute('open', ''); });
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (this: HTMLDialogElement) { this.removeAttribute('open'); });
  vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: caseNo, client_name: '測試客戶', order_status: '訂單完成', staff_name: null, identity_status: '一般市民', start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: 5, total_employer_self_pay_payable: 20000 }], next_cursor: null, etag: 'a'.repeat(64) });
  vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({ case_no: caseNo, client_id: 1, staff_id: null, client_name: '測試客戶', staff_name: null, order_status: '訂單完成', identity_status: '一般市民', cancel_reason: null, line_group_id: null, contract_identity: null, actual_start_date: null, actual_end_date: null, deposit_date: null, start_date: null, end_date: null, service_days: 5, service_hours_per_day: 8, deposit_service_days: null, floor_fee: 0, custom_rest_dates: null });
  vi.spyOn(clientFinanceHistoryClient, 'queryAll').mockResolvedValue([{ case_no: caseNo, account_version: '3', open_receivable_amount_ntd: 0, open_payable_amount_ntd: 0, obligation_count: 1, ledger_entry_count: 1, receipt_entry_count: 0, receipt_status: 'settled' as const }]);
  vi.spyOn(clientFinanceHistoryClient, 'query').mockResolvedValue({ case_no: caseNo, account_version: '3', obligations: [], ledger_entries: [{ entry_id: 10, entry_type: 'subsidy_advance', amount_ntd: 12000, occurred_on: '2026-03-15', reconciliation_reference: 'test', reversal_of_entry_id: null, created_at: '2026-03-15T00:00:00', allocations: [] }] });
  vi.spyOn(clientSubsidyReturnQueryClient, 'queryAll').mockResolvedValue({ rows: [], next_cursor: null });
  vi.spyOn(subsidyPeriodClient,'query').mockImplementation(async period=>periodView(period));
  vi.spyOn(subsidyPeriodClient,'bankRows').mockResolvedValue([]);
  vi.spyOn(subsidyPeriodClient,'caseCoverage').mockResolvedValue(caseCoverage);
  vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([
    { row_id: 'formal', case_no: caseNo, recipient_name: '測試客戶', payment_type: 'client_subsidy_return', certainty: 'confirmed', source: 'client_refund', payment_status: 'pending' as const, source_amount_ntd: 12000, unpaid_amount_ntd: 12000, payment_date: '2026-10-15', date_is_estimate: false, pending_reasons: [] },
    { row_id: 'estimate', case_no: 'TEST-002', recipient_name: '預估客戶', payment_type: 'client_subsidy_return', certainty: 'estimated', source: 'subsidy_estimate', payment_status: 'pending' as const, source_amount_ntd: 9000, unpaid_amount_ntd: 9000, payment_date: null, date_is_estimate: false, pending_reasons: ['服務尚未完成'] },
  ]);
  vi.spyOn(recovery, 'queryAll').mockResolvedValue([advance, { ...advance, advance_id: 11, case_no: 'TEST-001-OTHER', client_name: '其他案件客戶' }]);
  vi.spyOn(recovery, 'preview').mockResolvedValue({ row: advance, account_version: 3, batch_version: 5, preview_fingerprint: 'a'.repeat(64) });
  vi.spyOn(recovery, 'apply').mockResolvedValue({ advance_id: 10, case_no: caseNo, recovered_amount_ntd: 12000, account_version: 4 });
});
afterEach(() => { cleanup(); window.location.hash = ''; vi.restoreAllMocks(); });

async function openDetail() {
  fireEvent.click(await screen.findByRole('button', { name: '案件補助明細' }));
  const drawer = await screen.findByRole('dialog');
  await within(drawer).findByText(/整期核銷涵蓋/);
  return drawer;
}
describe('three finance workspaces', () => {
  it('distinguishes a missing canonical payable from an unpaid or zero balance', async () => {
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([{
      row_id: 'missing', case_no: 'HISTORICAL-MISSING', recipient_name: '帳務未建月嫂', staff_id: 9,
      payment_type: 'staff_payable', certainty: 'estimated', source: 'missing_payroll', payment_status: 'pending',
      source_amount_ntd: null, unpaid_amount_ntd: null, payment_date: null, date_is_estimate: false,
      pending_reasons: ['尚未建立月嫂應付帳務'],
    }]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    const row = (await screen.findByText('未設定 帳務未建月嫂')).closest('tr')!;
    expect(within(row).getByText('服務與薪資資料待確認')).toBeInTheDocument();
    expect(within(row).queryByText('NT$ 0')).not.toBeInTheDocument();
    expect(within(row).queryByText('確認待付')).not.toBeInTheDocument();
  });
  it('shows owner payment status after requery without mixing paid rows into outstanding totals', async () => {
    const base = { row_id: 'paid', case_no: 'HISTORICAL', recipient_name: '歷史月嫂', payment_type: 'staff_payable' as const,
      certainty: 'confirmed' as const, source: 'staff_obligation' as const, source_amount_ntd: 24000, unpaid_amount_ntd: 0,
      payment_date: null, date_is_estimate: false, pending_reasons: [], staff_id: 9, payment_status: 'paid' as const };
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([
      base, { ...base, row_id: 'partial', recipient_name: '部分付款月嫂', unpaid_amount_ntd: 5000, payment_status: 'partially_paid' },
      { ...base, row_id: 'settled', recipient_name: '結清月嫂', payment_status: 'settled' },
    ]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    const paid = (await screen.findByText('未設定 歷史月嫂')).closest('tr')!;
    expect(within(paid).getByText('已付款')).toBeInTheDocument();
    expect(within(paid).getByText('NT$ 0')).toBeInTheDocument();
    expect(screen.getByLabelText('付款摘要')).toHaveTextContent('確認待付 NT$ 5,000');
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'paid' } });
    expect(screen.queryByText('未設定 部分付款月嫂')).not.toBeInTheDocument();
    expect(screen.queryByText('未設定 結清月嫂')).not.toBeInTheDocument();
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([{ ...base, unpaid_amount_ntd: 24000, payment_status: 'pending' }]);
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await waitFor(() => expect(screen.queryByText('未設定 歷史月嫂')).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'all' } });
    expect(await screen.findByText('未設定 歷史月嫂')).toBeInTheDocument();
    expect(within(screen.getByText('未設定 歷史月嫂').closest('tr')!).getByText('確認待付')).toBeInTheDocument();
  });

  it('keeps an overpaid caregiver at zero payable with the owner recovery hint visible', async () => {
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([{
      row_id: 'handover-paid', case_no: 'HANDOVER', recipient_name: '原月嫂', staff_id: 9,
      payment_type: 'staff_payable', certainty: 'confirmed', source: 'staff_obligation',
      source_amount_ntd: 16800, unpaid_amount_ntd: 0, payment_status: 'paid',
      payment_date: '2026-11-15', date_is_estimate: false,
      pending_reasons: ['已有超付款，請至人員帳務處理追償'],
    }]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    const row = (await screen.findByText('未設定 原月嫂')).closest('tr')!;
    expect(within(row).getByText('已付款')).toBeInTheDocument();
    expect(within(row).getByText('NT$ 0')).toBeInTheDocument();
    expect(within(row).getByText('已有超付款，請至人員帳務處理追償')).toBeInTheDocument();
    expect(screen.getByLabelText('付款摘要')).toHaveTextContent('確認待付 NT$ 0');
  });

  it('shows historical receipt status from the owner even without canonical receipt entries', async () => {
    vi.mocked(clientFinanceHistoryClient.queryAll).mockResolvedValue([
      { case_no: 'HISTORICAL-PAID', account_version: '4', open_receivable_amount_ntd: 0, open_payable_amount_ntd: 0,
        obligation_count: 1, ledger_entry_count: 0, receipt_entry_count: 0, receipt_status: 'received' },
    ]);
    render(<FinancePage />);
    const row = (await screen.findByText('HISTORICAL-PAID')).closest('tr')!;
    expect(within(row).getByText('已收款')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('狀態'), { target: { value: 'history' } });
    expect(screen.getByText('HISTORICAL-PAID')).toBeInTheDocument();
  });

  it('filters received clients by actual receipts, retaining partially collected cases and excluding other ledger-only cases', async () => {
    const base = { case_no: 'PARTIAL', account_version: '3', open_receivable_amount_ntd: 5000, open_payable_amount_ntd: 0, obligation_count: 1, ledger_entry_count: 2, receipt_entry_count: 1, receipt_status: 'partially_received' as const };
    vi.mocked(clientFinanceHistoryClient.queryAll).mockResolvedValue([
      base,
      { ...base, case_no: 'PAID', open_receivable_amount_ntd: 0, receipt_status: 'received' },
      ...['REFUND', 'ADJUSTMENT', 'REVERSAL', 'SUBSIDY_RETURN', 'SUBSIDY_ADVANCE'].map(case_no => ({ ...base, case_no, receipt_entry_count: 0, receipt_status: 'unpaid' as const })),
    ]);
    render(<FinancePage />);
    await screen.findByText('PARTIAL');
    expect(screen.queryByRole('option', { name: '含入帳紀錄' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('狀態'), { target: { value: 'history' } });
    const table = screen.getByRole('table');
    expect(within(table).getByText('PARTIAL')).toBeInTheDocument();
    expect(within(table).getByText('PAID')).toBeInTheDocument();
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    for (const case_no of ['REFUND', 'ADJUSTMENT', 'REVERSAL', 'SUBSIDY_RETURN', 'SUBSIDY_ADVANCE', caseNo]) expect(within(table).queryByText(case_no)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('狀態'), { target: { value: 'unpaid' } });
    expect(within(table).getByText('PARTIAL')).toBeInTheDocument();
    expect(within(table).queryByText('PAID')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('狀態'), { target: { value: 'all' } });
    expect(within(table).getByText('REFUND')).toBeInTheDocument();
    expect(clientFinanceHistoryClient.query).not.toHaveBeenCalled();
    expect(clientFinanceHistoryClient.queryAll).toHaveBeenCalledTimes(1);
  });
  it('uses the same period query for month quarter and year without application stages',async()=>{
    render(<FinancePage/>);fireEvent.change(screen.getByLabelText('收款來源'),{target:{value:'government'}});
    await screen.findByRole('heading',{name:'政府補助整期核銷'});
    await screen.findByRole('button',{name:caseNo});
    expect(screen.queryByText('核准金額')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('彙總單位'),{target:{value:'month'}});
    await waitFor(()=>expect(subsidyPeriodClient.query).toHaveBeenLastCalledWith(expect.objectContaining({unit:'month'}),expect.any(AbortSignal)));
    fireEvent.change(screen.getByLabelText('彙總單位'),{target:{value:'year'}});
    await waitFor(()=>expect(subsidyPeriodClient.query).toHaveBeenLastCalledWith(expect.objectContaining({unit:'year',index:1}),expect.any(AbortSignal)));
  });
  it('has exactly three entries and separates confirmed money, estimates and unknown dates', async () => {
    render(<FinancePage />);
    expect(within(screen.getByRole('navigation', { name: '帳務工作區' })).getAllByRole('button').map(button => button.textContent)).toEqual(['收款', '付款', '銀行對帳']);
    await screen.findByRole('button', { name: '收款明細' });
    expect(cashRequirementsQueryClient.queryAll).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    const summary = await screen.findByLabelText('付款摘要');
    expect(summary).toHaveTextContent('確認待付 NT$ 12,000'); expect(summary).toHaveTextContent('預估 NT$ 9,000'); expect(summary).not.toHaveTextContent('21,000');
    fireEvent.change(screen.getByLabelText('付款月份'), { target: { value: '2026-11' } });
    expect(screen.getByText('預估客戶')).toBeInTheDocument(); expect(screen.queryByText('測試客戶')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'confirmed' } });
    expect(screen.queryByText('預估客戶')).not.toBeInTheDocument(); expect(summary).toHaveTextContent('確認待付 NT$ 0');
    expect(cashRequirementsQueryClient.queryAll).toHaveBeenCalledTimes(1);
  });
  it('distinguishes confirmed payables from pending service completion without relabelling other estimates', async () => {
    const base = { row_id: 'service', case_no: 'SERVICE', recipient_name: '服務待結束客戶', payment_type: 'client_subsidy_return' as const, certainty: 'estimated' as const, source: 'subsidy_estimate' as const, payment_status: 'pending' as const, source_amount_ntd: 9000, unpaid_amount_ntd: 9000, payment_date: null, date_is_estimate: false, pending_reasons: ['服務尚未完成'] };
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([
      base,
      { ...base, row_id: 'other', case_no: 'OTHER', recipient_name: '收款待確認客戶', pending_reasons: ['客戶服務費尚未收齊'] },
      { ...base, row_id: 'formal', case_no: 'FORMAL', recipient_name: '正式退款客戶', certainty: 'confirmed', source: 'client_refund', pending_reasons: ['退款付款日尚未確定'] },
    ]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    await screen.findByText('服務待結束客戶');
    expect(within(screen.getByLabelText('付款狀態')).getAllByRole('option').map(option => option.textContent)).toEqual(['全部', '確認待付', '計算資料待確認', '部分付款', '已付款', '已結清']);
    expect(within(screen.getByText('收款待確認客戶').closest('tr')!).getByText('計算資料待確認', { selector: '.finance-badge' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'data_pending' } });
    expect(screen.getByText('服務待結束客戶')).toBeInTheDocument();
    expect(screen.getByText('收款待確認客戶')).toBeInTheDocument();
    expect(screen.queryByText('正式退款客戶')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'confirmed' } });
    expect(screen.getByText('正式退款客戶')).toBeInTheDocument();
    expect(screen.queryByText('服務待結束客戶')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'all' } });
    expect(screen.getByText('收款待確認客戶')).toBeInTheDocument();
  });
  it('opens the same exact-case coverage and refund drawer from receipts and payments',async()=>{
    render(<FinancePage/>);let drawer=await openDetail();
    expect(within(drawer).getByText('工會代墊補助 NT$ 12,000')).toBeInTheDocument();
    expect(within(drawer).queryByText('其他案件客戶')).not.toBeInTheDocument();
    expect(within(drawer).queryByRole('button',{name:/銷帳/})).not.toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole('button',{name:'關閉案件補助明細'}));
    fireEvent.click(screen.getByRole('button',{name:'付款'}));
    const row=(await screen.findByText('測試客戶')).closest('tr')!;
    fireEvent.click(within(row).getByRole('button',{name:'案件補助明細'}));drawer=await screen.findByRole('dialog');
    await within(drawer).findByText(/整期核銷涵蓋/);
    expect(subsidyPeriodClient.caseCoverage).toHaveBeenLastCalledWith(caseNo,expect.any(AbortSignal));
    expect(recovery.apply).not.toHaveBeenCalled();
  });
  it('opens the staff identified by the payable instead of the first directory record', async () => {
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([{ row_id: 'staff:22', case_no: caseNo, recipient_name: '第二位人員', payment_type: 'staff_payable', certainty: 'confirmed', source: 'staff_obligation', payment_status: 'pending' as const, source_amount_ntd: 42000, unpaid_amount_ntd: 42000, payment_date: '2026-10-15', date_is_estimate: false, pending_reasons: [], staff_id: 22 }]);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '第一位人員', phone: null, education: null }, { id: 22, name: '第二位人員', phone: null, education: null }], next_cursor: null });
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue({ staff_id: 22, staff_payables_version: 1, obligations: [], events: [] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    fireEvent.click(await screen.findByRole('button', { name: '人員付款明細' }));
    await waitFor(() => expect(staffPayablesQueryClient.query).toHaveBeenCalledWith(22, expect.objectContaining({ signal: expect.any(AbortSignal) })));
    expect(screen.getByLabelText('服務人員')).toHaveValue('22');
  });
  it('uses service period directly without an application-year operation',async()=>{
    render(<FinancePage/>);fireEvent.change(screen.getByLabelText('收款來源'),{target:{value:'government'}});
    await screen.findByText('本期補助總額',{exact:false});
    fireEvent.change(screen.getByLabelText('年度'),{target:{value:'2026'}});
    fireEvent.change(screen.getByLabelText('季度'),{target:{value:'4'}});
    await screen.findByText('2026 年 第 4 季');
    expect(screen.queryByText('預計申請年月')).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'送件'})).not.toBeInTheDocument();
  });
  it('allows retry of a coverage query without inventing zero or performing per-case recovery',async()=>{
    vi.mocked(subsidyPeriodClient.caseCoverage).mockRejectedValueOnce(new ApiNetworkError('lost reply'));
    render(<FinancePage/>);fireEvent.click(await screen.findByRole('button',{name:'案件補助明細'}));
    const drawer=await screen.findByRole('dialog');const detail=within(drawer);
    await detail.findByText('補助資料待確認。');
    expect(detail.queryByText('NT$ 0')).not.toBeInTheDocument();
    fireEvent.click(detail.getByRole('button',{name:'重新查詢'}));
    await detail.findByText(/整期核銷涵蓋/);
    expect(subsidyPeriodClient.caseCoverage).toHaveBeenCalledTimes(2);
    expect(recovery.apply).not.toHaveBeenCalled();
  });

});
