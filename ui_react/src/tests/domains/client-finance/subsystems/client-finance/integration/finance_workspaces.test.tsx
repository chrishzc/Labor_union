/** Agreed workspace composition, separate totals, exact case detail and recovery. */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FinancePage } from '../../../../../../pages/FinancePage';
import { ordersQueryClient } from '../../../../../../api/orders/order_query_client';
import { clientFinanceHistoryClient } from '../../../../../../api/client_finance/client_finance_history_client';
import { cashRequirementsQueryClient } from '../../../../../../api/accounts_payable/cash_requirements_query_client';
import { clientSubsidyReturnQueryClient } from '../../../../../../api/client_finance/client_subsidy_return_query_client';
import { orderGovernmentSubsidyProjectionClient } from '../../../../../../api/orders/order_government_subsidy_projection_client';
import { subsidyAdvanceSettlementClient as recovery } from '../../../../../../api/client_finance/subsidy_advance_settlement_client';
import { ApiNetworkError } from '../../../../../../api/shared/typed_errors';
import { staffDirectoryClient } from '../../../../../../api/staff_directory/staff_directory_client';
import { staffPayablesQueryClient } from '../../../../../../api/staff_payables/staff_payables_query_client';

const caseNo = 'TEST-001';
const advance = { advance_id: 10, case_no: caseNo, client_name: '測試客戶', advanced_on: '2026-03-15', advance_amount_ntd: 12000,
  government_received_ntd: 12000, received_on: '2026-04-01', recovered_amount_ntd: 0, status: 'ready' as const, review_reason: null };
const government = { case_no: caseNo, substatus_code: 'paid' as const, identity_status: '一般市民', source: { owner: 'Government Subsidy', identity: 'batch:1', version: 5 },
  occurred_at: null, service_end_date: '2026-01-20', claim_quarter: 1, claim_application_year: 2026, claim_application_month: 4, claim_submitted_at: null,
  blockers: [], warnings: [], available_read_actions: [], claim_batch_id: 1, claim_item_count: 1, claimed_hours: 40, unit_price_ntd: 300,
  requested_amount_ntd: 12000, approved_amount_ntd: 12000, net_allocated_ntd: 12000, service_end_confirmed: true, estimated_subsidy_amount_ntd: 12000, estimate_unavailable_reason: null, confirmed_approved_amount_ntd: 12000, outstanding_amount_ntd: 0, overpayment_identity: null, overpayment_remaining_ntd: null };
beforeEach(() => {
  vi.restoreAllMocks(); window.location.hash = '#finance';
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement) { this.setAttribute('open', ''); });
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (this: HTMLDialogElement) { this.removeAttribute('open'); });
  vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({ items: [{ case_no: caseNo, client_name: '測試客戶', order_status: '訂單完成', staff_name: null, identity_status: '一般市民', start_date: null, end_date: null, actual_start_date: null, actual_end_date: null, service_days: 5, total_employer_self_pay_payable: 20000 }], next_cursor: null, etag: 'a'.repeat(64) });
  vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({ case_no: caseNo, client_id: 1, staff_id: null, client_name: '測試客戶', staff_name: null, order_status: '訂單完成', identity_status: '一般市民', cancel_reason: null, line_group_id: null, contract_identity: null, actual_start_date: null, actual_end_date: null, deposit_date: null, start_date: null, end_date: null, service_days: 5, service_hours_per_day: 8, deposit_service_days: null, floor_fee: 0, custom_rest_dates: null });
  vi.spyOn(clientFinanceHistoryClient, 'queryAll').mockResolvedValue([{ case_no: caseNo, account_version: '3', open_receivable_amount_ntd: 0, open_payable_amount_ntd: 0, obligation_count: 1, ledger_entry_count: 1, receipt_entry_count: 0 }]);
  vi.spyOn(clientFinanceHistoryClient, 'query').mockResolvedValue({ case_no: caseNo, account_version: '3', obligations: [], ledger_entries: [{ entry_id: 10, entry_type: 'subsidy_advance', amount_ntd: 12000, occurred_on: '2026-03-15', reconciliation_reference: 'test', reversal_of_entry_id: null, created_at: '2026-03-15T00:00:00', allocations: [] }] });
  vi.spyOn(clientSubsidyReturnQueryClient, 'queryAll').mockResolvedValue({ rows: [], next_cursor: null });
  vi.spyOn(orderGovernmentSubsidyProjectionClient, 'queryAll').mockResolvedValue([government]);
  vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([
    { row_id: 'formal', case_no: caseNo, recipient_name: '測試客戶', payment_type: 'client_subsidy_return', certainty: 'confirmed', source: 'client_refund', source_amount_ntd: 12000, unpaid_amount_ntd: 12000, payment_date: '2026-10-15', date_is_estimate: false, pending_reasons: [] },
    { row_id: 'estimate', case_no: 'TEST-002', recipient_name: '預估客戶', payment_type: 'client_subsidy_return', certainty: 'estimated', source: 'subsidy_estimate', source_amount_ntd: 9000, unpaid_amount_ntd: 9000, payment_date: null, date_is_estimate: false, pending_reasons: ['服務尚未完成'] },
  ]);
  vi.spyOn(recovery, 'queryAll').mockResolvedValue([advance, { ...advance, advance_id: 11, case_no: 'TEST-001-OTHER', client_name: '其他案件客戶' }]);
  vi.spyOn(recovery, 'preview').mockResolvedValue({ row: advance, account_version: 3, batch_version: 5, preview_fingerprint: 'a'.repeat(64) });
  vi.spyOn(recovery, 'apply').mockResolvedValue({ advance_id: 10, case_no: caseNo, recovered_amount_ntd: 12000, account_version: 4 });
});
afterEach(() => { cleanup(); window.location.hash = ''; vi.restoreAllMocks(); });

async function openDetail() {
  fireEvent.click(await screen.findByRole('button', { name: '案件補助明細' }));
  const drawer = await screen.findByRole('dialog');
  await within(drawer).findByRole('button', { name: '預覽 TEST-001 銷帳' });
  return drawer;
}
describe('three finance workspaces', () => {
  it('filters received clients by actual receipts, retaining partially collected cases and excluding other ledger-only cases', async () => {
    const base = { case_no: 'PARTIAL', account_version: '3', open_receivable_amount_ntd: 5000, open_payable_amount_ntd: 0, obligation_count: 1, ledger_entry_count: 2, receipt_entry_count: 1 };
    vi.mocked(clientFinanceHistoryClient.queryAll).mockResolvedValue([
      base,
      { ...base, case_no: 'PAID', open_receivable_amount_ntd: 0 },
      ...['REFUND', 'ADJUSTMENT', 'REVERSAL', 'SUBSIDY_RETURN', 'SUBSIDY_ADVANCE'].map(case_no => ({ ...base, case_no, receipt_entry_count: 0 })),
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
  it('groups subsidy cases by confirmed service end and keeps estimates separate from approved receivables', async () => {
    const pending = { ...government, substatus_code: 'claim_lineage_missing' as const, claim_item_count: 0, claim_batch_id: null,
      service_end_confirmed: false, approved_amount_ntd: 0, confirmed_approved_amount_ntd: null, outstanding_amount_ntd: null, net_allocated_ntd: 0 };
    vi.mocked(orderGovernmentSubsidyProjectionClient.queryAll).mockResolvedValue([
      pending,
      { ...government, case_no: 'TEST-APPROVED', substatus_code: 'partially_paid', approved_amount_ntd: 2000, confirmed_approved_amount_ntd: 2000, outstanding_amount_ntd: 1500, net_allocated_ntd: 500, estimated_subsidy_amount_ntd: 2400 },
      { ...pending, case_no: 'TEST-UNKNOWN', service_end_confirmed: true, estimated_subsidy_amount_ntd: null, estimate_unavailable_reason: 'rate_snapshot_missing' },
    ]);
    render(<FinancePage />);
    fireEvent.change(screen.getByLabelText('收款來源'), { target: { value: 'government' } });
    const table = await screen.findByRole('table');
    await within(table).findByText('TEST-APPROVED');
    expect(screen.queryByRole('option', { name: '待收款' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: '待確認服務結束' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '已確認服務結束' })).toBeInTheDocument();
    expect(within(table).queryByText('NT$ 0')).not.toBeInTheDocument();
    expect(within(table).getByText('NT$ 1,500')).toBeInTheDocument();
    expect(within(table).getByText('補助單價待確認')).toBeInTheDocument();
    expect(document.querySelector('.finance-inline-summary')).toHaveTextContent('預估補助小計 NT$ 14,400');
    expect(document.querySelector('.finance-inline-summary')).toHaveTextContent('已核准待收小計 NT$ 1,500');
    fireEvent.change(screen.getByLabelText('狀態'), { target: { value: 'service_pending' } });
    expect(within(table).getByText(caseNo)).toBeInTheDocument();
    expect(within(table).queryByText('TEST-APPROVED')).not.toBeInTheDocument();
    expect(document.querySelector('.finance-inline-summary')).toHaveTextContent('已核准待收小計 待確認');
    fireEvent.click(within(table).getByRole('button', { name: '案件補助明細' }));
    const drawer = await screen.findByRole('dialog');
    const section = (await within(drawer).findByRole('heading', { name: '政府補助' })).closest('section')!;
    await waitFor(() => expect(section).toHaveTextContent('尚無正式請款資料'));
    expect(section).not.toHaveTextContent('NT$ 0');
    expect(section).toHaveTextContent('預估補助金額NT$ 12,000');
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
    const base = { row_id: 'service', case_no: 'SERVICE', recipient_name: '服務待結束客戶', payment_type: 'client_subsidy_return' as const, certainty: 'estimated' as const, source: 'subsidy_estimate' as const, source_amount_ntd: 9000, unpaid_amount_ntd: 9000, payment_date: null, date_is_estimate: false, pending_reasons: ['服務尚未完成'] };
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([
      base,
      { ...base, row_id: 'other', case_no: 'OTHER', recipient_name: '收款待確認客戶', pending_reasons: ['客戶服務費尚未收齊'] },
      { ...base, row_id: 'formal', case_no: 'FORMAL', recipient_name: '正式退款客戶', certainty: 'confirmed', source: 'client_refund', pending_reasons: ['退款付款日尚未確定'] },
    ]);
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    await screen.findByText('服務待結束客戶');
    expect(within(screen.getByLabelText('付款狀態')).getAllByRole('option').map(option => option.textContent)).toEqual(['全部', '確認待付', '待確認服務結束']);
    expect(within(screen.getByText('收款待確認客戶').closest('tr')!).getByText('待確認', { selector: '.finance-badge' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'service_pending' } });
    expect(screen.getByText('服務待結束客戶')).toBeInTheDocument();
    expect(screen.queryByText('收款待確認客戶')).not.toBeInTheDocument();
    expect(screen.queryByText('正式退款客戶')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'confirmed' } });
    expect(screen.getByText('正式退款客戶')).toBeInTheDocument();
    expect(screen.queryByText('服務待結束客戶')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('付款狀態'), { target: { value: 'all' } });
    expect(screen.getByText('收款待確認客戶')).toBeInTheDocument();
  });
  it('opens one exact-case drawer from receipts and payments without duplicate subsidiary lists', async () => {
    render(<FinancePage />); let drawer = await openDetail();
    expect(within(drawer).getByText('工會代墊補助 NT$ 12,000')).toBeInTheDocument();
    expect(within(drawer).queryByText('其他案件客戶')).not.toBeInTheDocument();
    expect(within(drawer).queryByRole('heading', { name: '代墊補助款銷帳清冊' })).not.toBeInTheDocument();
    fireEvent.click(within(drawer).getByRole('button', { name: '關閉案件補助明細' }));
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    const row = (await screen.findByText('測試客戶')).closest('tr')!;
    fireEvent.click(within(row).getByRole('button', { name: '案件補助明細' })); drawer = await screen.findByRole('dialog');
    expect(await within(drawer).findByRole('button', { name: '預覽 TEST-001 銷帳' })).toBeInTheDocument();
    expect(clientSubsidyReturnQueryClient.queryAll).toHaveBeenLastCalledWith(expect.objectContaining({ caseNo, signal: expect.any(AbortSignal) }));
  });
  it('opens the staff identified by the payable instead of the first directory record', async () => {
    vi.mocked(cashRequirementsQueryClient.queryAll).mockResolvedValue([{ row_id: 'staff:22', case_no: caseNo, recipient_name: '第二位人員', payment_type: 'staff_payable', certainty: 'confirmed', source: 'staff_obligation', source_amount_ntd: 42000, unpaid_amount_ntd: 42000, payment_date: '2026-10-15', date_is_estimate: false, pending_reasons: [], staff_id: 22 }]);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [{ id: 11, name: '第一位人員', phone: null, education: null }, { id: 22, name: '第二位人員', phone: null, education: null }], next_cursor: null });
    vi.spyOn(staffPayablesQueryClient, 'query').mockResolvedValue({ staff_id: 22, staff_payables_version: 1, obligations: [], events: [] });
    render(<FinancePage />);
    fireEvent.click(screen.getByRole('button', { name: '付款' }));
    fireEvent.click(await screen.findByRole('button', { name: '人員付款明細' }));
    await waitFor(() => expect(staffPayablesQueryClient.query).toHaveBeenCalledWith(22, expect.objectContaining({ signal: expect.any(AbortSignal) })));
    expect(screen.getByLabelText('服務人員')).toHaveValue('22');
  });
  it('keeps service quarter separate from the following application year', async () => {
    vi.mocked(orderGovernmentSubsidyProjectionClient.queryAll).mockResolvedValue([{ ...government, service_end_date: '2026-12-31', claim_quarter: 4, claim_application_year: 2027, claim_application_month: 1 }]);
    render(<FinancePage />);
    fireEvent.change(screen.getByLabelText('收款來源'), { target: { value: 'government' } });
    await waitFor(() => expect(screen.getAllByText('2026 年第 4 季').length).toBeGreaterThan(0));
    expect(screen.queryByText('2027 年第 4 季')).not.toBeInTheDocument();
    const drawer = await openDetail();
    expect(await within(drawer).findByText('2027-01')).toBeInTheDocument();
    expect(within(drawer).getByText('2026 年第 4 季')).toBeInTheDocument();
  });
  it('keeps the shared drawer open on uncertain recovery, then refreshes the real readback', async () => {
    vi.mocked(recovery.apply).mockRejectedValueOnce(new ApiNetworkError('lost reply'));
    render(<FinancePage />); const drawer = await openDetail(); const detail = within(drawer);
    fireEvent.click(detail.getByRole('button', { name: '預覽 TEST-001 銷帳' }));
    fireEvent.change(await detail.findByLabelText('核對說明'), { target: { value: '核對原墊款與政府入款' } });
    fireEvent.click(detail.getByLabelText('我已核對原墊款與政府入款，確認建立回收銷帳。'));
    fireEvent.click(detail.getByRole('button', { name: '確認銷帳' }));
    await detail.findByRole('button', { name: '重新查詢銷帳結果' });
    expect(detail.getByRole('button', { name: '關閉案件補助明細' })).toBeDisabled();
    vi.mocked(recovery.queryAll).mockResolvedValue([{ ...advance, status: 'recovered', recovered_amount_ntd: 12000 }]);
    fireEvent.click(detail.getByRole('button', { name: '重新查詢銷帳結果' }));
    await detail.findByText(/已銷帳 NT\$ 12,000，已重新查詢確認/);
    await waitFor(() => expect(detail.getByRole('button', { name: '關閉案件補助明細' })).toBeEnabled());
    expect(recovery.apply).toHaveBeenCalledTimes(1);
    expect(clientFinanceHistoryClient.queryAll).toHaveBeenCalledTimes(2);
  });
});
