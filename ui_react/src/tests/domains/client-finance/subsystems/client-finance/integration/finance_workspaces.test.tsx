import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FinancePage } from '../../../../../../pages/FinancePage';
import { monthlyAccountingClient, type AccountingRange, type MonthlyAccountingReport } from '../../../../../../api/finance_import/monthly_accounting_client';
import { financeAccountingClient, type CaseAccounting } from '../../../../../../api/finance_import/finance_accounting_client';
import { financeImportQueryClient } from '../../../../../../api/finance_import/finance_import_query_client';
import type { FinanceBankTransaction } from '../../../../../../api/finance_import/finance_import_query_schemas';
import { cashRequirementsQueryClient } from '../../../../../../api/accounts_payable/cash_requirements_query_client';
import { staffPayoutRemediationClient } from '../../../../../../api/staff_payables/staff_payout_remediation_client';
import { subsidyPeriodClient, type SubsidyPeriod } from '../../../../../../api/government_subsidy/period_reconciliation_client';
import { subsidyAdvanceSettlementClient } from '../../../../../../api/client_finance/subsidy_advance_settlement_client';
import { weeklyOperationsReportQueryClient } from '../../../../../../api/reports/weekly_operations_report_query_client';
import { transport } from '../../../../../../api/shared/transport';
import { WEEKLY_OPERATIONS_REPORT } from '../../../../../fixtures/reports/weekly_operations_report_contract_fixtures';

const caseNo = 'CASE-RPT-001';
const now = new Date();
const month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
const date = `${month}-15`;
type MonthRow = MonthlyAccountingReport['rows'][number];
type Item = MonthRow['items'][number];
type Bank = MonthRow['bank_facts'][number];

function item(case_no: string, direction: Item['direction'], expected_ntd: number, actual_ntd: number, remaining_ntd: number, noncash_ntd = 0) {
  return {
    case_no, direction, expected_ntd, actual_ntd, remaining_ntd, noncash_ntd,
    identity: `${case_no}:${direction}`, client_name: case_no, party: case_no,
    due_date: date, label: direction === 'payable' ? '月嫂薪資' : '第一期',
  } satisfies Item;
}

function bank(case_no: string, cash_flow: NonNullable<Bank['cash_flow']>, amount_ntd: number) {
  return {
    identity: `bank:${case_no}`, occurred_on: date, direction: ['C', 'G'].includes(cash_flow) ? 'in' : 'out',
    cases: [case_no], bank: cash_flow === 'G' ? 'taishin' : 'sinopac', cash_flow, amount_ntd,
  } satisfies Bank;
}

function report(range: AccountingRange, items: ReturnType<typeof item>[] = [], bank_facts: ReturnType<typeof bank>[] = [], undated_item_count = 0): MonthlyAccountingReport {
  const sum = (direction: Item['direction'], field: 'expected_ntd' | 'actual_ntd' | 'remaining_ntd' | 'noncash_ntd') =>
    items.filter(row => row.direction === direction).reduce((total, row) => total + row[field], 0);
  const cash = (direction: Bank['direction']) => bank_facts.filter(row => row.direction === direction).reduce((total, row) => total + row.amount_ntd, 0);
  return {
    ...range, as_of: date, excluded_cases: [], undated_item_count,
    rows: [{
      month: range.start_month, items, bank_facts,
      expected_in_ntd: sum('receivable', 'expected_ntd'), received_ntd: sum('receivable', 'actual_ntd'),
      remaining_in_ntd: sum('receivable', 'remaining_ntd'), other_in_ntd: sum('receivable', 'noncash_ntd'),
      expected_out_ntd: sum('payable', 'expected_ntd'), paid_ntd: sum('payable', 'actual_ntd'),
      remaining_out_ntd: sum('payable', 'remaining_ntd'), other_out_ntd: sum('payable', 'noncash_ntd'),
      cash_in_ntd: cash('in'), cash_out_ntd: cash('out'),
    }],
  };
}

function detail(case_no: string, overrides: Partial<CaseAccounting> = {}): CaseAccounting {
  return {
    case_no, client_name: case_no, receivable_ntd: null, received_ntd: null, payable_ntd: null, paid_ntd: null,
    pending_warning_count: 0, client_items: [], staff_items: [], transactions: [], warnings: [], ...overrides,
  };
}

const governmentRow: FinanceBankTransaction = {
  row_id: 9, row_identity: 'finance-import-row:9', transaction_date: date, bank: 'taishin', direction: 'incoming',
  amount_ntd: 12000, classification_type: 'government_subsidy', status: 'pending', disposition: 'business_pending',
  reference: 'G-9', counterparty_name: '新竹市政府', cases: [], review_reason: null, available_actions: [],
};

function periodView(period: SubsidyPeriod) {
  return {
    period, version: 1, label: `${period.year} · ${period.unit} · ${period.index}`, lines: [],
    total_ntd: 12000, coverage: [], recorded_lines: [], changed_cases: [], blocked_cases: [], can_reconcile: true,
  };
}

beforeEach(() => {
  // Every external request in this suite is either replaced by a typed owner fixture or rejected locally.
  for (const method of ['get', 'post', 'put', 'patch', 'delete'] as const) {
    vi.spyOn(transport, method).mockRejectedValue(new Error('No network in finance workbench tests'));
  }
  vi.spyOn(monthlyAccountingClient, 'query').mockImplementation(async range => report(range));
  vi.spyOn(financeAccountingClient, 'query').mockImplementation(async case_no => detail(case_no));
  vi.spyOn(financeImportQueryClient, 'listBankTransactions').mockResolvedValue({ items: [governmentRow], pending_count: 1, next_before_row_id: null });
  vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue(WEEKLY_OPERATIONS_REPORT);
  vi.spyOn(subsidyPeriodClient, 'query').mockImplementation(async period => periodView(period));
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, '', window.location.pathname);
  vi.restoreAllMocks();
});

function openFinance(tab = 'monthly') {
  window.history.replaceState(null, '', `#finance?tab=${tab}`);
  return render(<FinancePage />);
}

async function monthDetails() {
  fireEvent.click(await screen.findByRole('button', { name: '展開明細' }));
  return within(await screen.findByRole('region', { name: /明細/ }));
}

async function openCase(scope: ReturnType<typeof within>, selected: string, label = selected) {
  fireEvent.click(await scope.findByRole('button', { name: label }));
  return within(await screen.findByRole('dialog', { name: `案件帳務 · ${selected}` }));
}

async function openGovernment() {
  openFinance('bank');
  fireEvent.click(await screen.findByRole('button', { name: '核對交易 G-9' }));
  return within(await screen.findByRole('dialog', { name: '政府整期核對' }));
}

function changeCategory(category: AccountingRange['category']) {
  fireEvent.change(screen.getByLabelText('案件類別'), { target: { value: category } });
  fireEvent.click(screen.getByRole('button', { name: '查詢' }));
}

describe('current finance workspaces', () => {
  it('redirects the retired payment destination link to monthly accounting', async () => {
    openFinance('payment-destination');
    await screen.findByRole('heading', { name: '每月帳務狀況' });
    await waitFor(() => expect(monthlyAccountingClient.query).toHaveBeenCalled());
    expect(screen.queryByRole('heading', { name: '工會／代收付帳戶' })).not.toBeInTheDocument();
  });

  it('applies the same case category to receipt and payable rows and totals', async () => {
    const citizen = [item(caseNo, 'receivable', 100, 0, 100)];
    const nonCitizen = [item('115000099', 'receivable', 500, 0, 500), item('115000099', 'payable', 700, 0, 700)];
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range,
      range.category === 'all' ? [...citizen, ...nonCitizen] : range.category === 'non_citizen' ? nonCitizen : citizen));
    openFinance();
    changeCategory('subsidy');
    await screen.findByText('待收 NT$ 100');
    expect((await monthDetails()).getByRole('button', { name: caseNo })).toBeVisible();
    expect(screen.queryByRole('button', { name: '115000099' })).not.toBeInTheDocument();

    changeCategory('non_citizen');
    expect(await screen.findByText('待收 NT$ 500')).toBeVisible();
    expect(screen.getByText('待付 NT$ 700')).toBeVisible();
    expect((await monthDetails()).getAllByRole('button', { name: '115000099' })).toHaveLength(2);
    expect(screen.queryByRole('button', { name: caseNo })).not.toBeInTheDocument();

    changeCategory('all');
    expect(await screen.findByText('待收 NT$ 600')).toBeVisible();
    expect(screen.getByText('待付 NT$ 700')).toBeVisible();
    expect(monthlyAccountingClient.query).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'all' }), expect.any(AbortSignal));
  });

  it('keeps an absent staff obligation distinct from a real unpaid or zero balance', async () => {
    const missing = 'HISTORICAL-MISSING';
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range, [
      item(missing, 'receivable', 3000, 0, 3000), item('UNPAID', 'payable', 4000, 0, 4000), item('PAID', 'payable', 5000, 5000, 0),
    ]));
    openFinance();
    const table = await monthDetails();
    expect(table.getByRole('row', { name: /UNPAID/ })).toHaveTextContent('NT$ 4,000');
    expect(table.getByRole('row', { name: /PAID.*已付清/ })).toBeVisible();
    const drawer = await openCase(table, missing);
    expect(await drawer.findByText('本案目前無月嫂應付項目。')).toBeVisible();
    expect(drawer.queryByText('出款已結清')).not.toBeInTheDocument();
  });

  it('requeries owner payment progress and excludes closed balances from outstanding totals', async () => {
    let paid = 24000;
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range, [
      item('HISTORICAL', 'payable', 24000, paid, 24000 - paid),
      item('PARTIAL', 'payable', 24000, 19000, 5000),
      item('SETTLED', 'payable', 24000, 0, 0, 24000),
    ]));
    openFinance();
    expect(await screen.findByText('待付 NT$ 5,000')).toBeVisible();
    const table = await monthDetails();
    expect(within(table.getByRole('row', { name: /HISTORICAL/ })).getAllByRole('cell')[4]).toHaveTextContent('NT$ 24,000');
    expect(within(table.getByRole('row', { name: /SETTLED/ })).getAllByRole('cell')[5]).toHaveTextContent('NT$ 24,000');

    paid = 0;
    fireEvent.click(screen.getByRole('button', { name: '查詢' }));
    expect(await screen.findByText('待付 NT$ 29,000')).toBeVisible();
    expect((await monthDetails()).getByRole('row', { name: /HISTORICAL/ })).not.toHaveTextContent('已付清');
  });

  it('keeps an overpaid caregiver at zero payable and shows the discrepancy in the case drawer', async () => {
    const overpaid = item('HANDOVER', 'payable', 16800, 17500, 0);
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range, [overpaid]));
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail('HANDOVER', {
      staff_items: [{ ...overpaid, has_payment: true, version: '1' }],
    }));
    openFinance();
    expect(await screen.findByText('待付 NT$ 0')).toBeVisible();
    const drawer = await openCase(await monthDetails(), 'HANDOVER');
    expect(await drawer.findByText('超付款待核對')).toBeVisible();
    expect(drawer.getByText('已付 NT$ 17,500')).toBeVisible();
  });

  it('preserves a historically paid receipt without inventing a canonical bank receipt', async () => {
    const historical = item('HISTORICAL-PAID', 'receivable', 5000, 5000, 0);
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range, [historical]));
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail('HISTORICAL-PAID', {
      client_items: [{ ...historical, payment_stage: 'first', has_payment: true, version: '4' }],
    }));
    openFinance();
    const table = await monthDetails();
    expect(table.getByRole('row', { name: /HISTORICAL-PAID/ })).toHaveTextContent('已收齊');
    const drawer = await openCase(table, 'HISTORICAL-PAID');
    expect(await drawer.findByText('已繳齊')).toBeVisible();
    fireEvent.click(drawer.getAllByRole('button', { name: '關閉案件' })[0]);
    fireEvent.click(screen.getByRole('tab', { name: '已核銷收付款' }));
    expect(screen.getByText(/所選月份沒有資料/)).toBeVisible();
  });

  it('keeps partial and full actual receipts separate from refunds and non-cash ledger entries', async () => {
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range, [
      item('PARTIAL', 'receivable', 6000, 1000, 5000),
      item('PAID', 'receivable', 6000, 6000, 0),
      item('ADJUSTMENT', 'receivable', 4000, 0, 0, 4000),
    ], [bank('PARTIAL', 'C', 1000), bank('PAID', 'C', 6000), bank('REFUND', 'RS', 500), bank('SUBSIDY_RETURN', 'RT', 700)]));
    openFinance();
    expect((await monthDetails()).getByRole('row', { name: /PARTIAL/ })).toHaveTextContent('NT$ 5,000');
    fireEvent.click(screen.getByRole('tab', { name: '已核銷收付款' }));
    const table = await monthDetails();
    expect(within(table.getByRole('row', { name: /PARTIAL/ })).getAllByRole('cell')[4]).toHaveTextContent('NT$ 1,000');
    expect(within(table.getByRole('row', { name: /PAID/ })).getAllByRole('cell')[4]).toHaveTextContent('NT$ 6,000');
    for (const caseId of ['REFUND', 'SUBSIDY_RETURN']) {
      expect(within(table.getByRole('row', { name: new RegExp(caseId) })).getAllByRole('cell')[4]).toHaveTextContent('—');
    }
    expect(table.queryByRole('row', { name: /ADJUSTMENT|REVERSAL|SUBSIDY_ADVANCE/ })).not.toBeInTheDocument();
    expect(screen.getAllByText('NT$ 7,000').length).toBeGreaterThan(0);
  });

  it('queries month, quarter and year through the same government period owner', async () => {
    const drawer = await openGovernment();
    const unit = await drawer.findByLabelText('彙總單位');
    await waitFor(() => expect(subsidyPeriodClient.query).toHaveBeenLastCalledWith(expect.objectContaining({ unit: 'quarter' }), expect.any(AbortSignal)));
    for (const value of ['month', 'year']) {
      fireEvent.change(unit, { target: { value } });
      await waitFor(() => expect(subsidyPeriodClient.query).toHaveBeenLastCalledWith(expect.objectContaining({ unit: value, index: 1 }), expect.any(AbortSignal)));
    }
    expect(drawer.queryByText('核准金額')).not.toBeInTheDocument();
  });

  it('exposes current navigation and separates formal amounts from undated and estimated amounts', async () => {
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range,
      [item('FORMAL', 'payable', 12000, 0, 12000)], [], 1));
    const caseWorkspace = openFinance('case-accounting');
    const nav = within(screen.getByRole('navigation', { name: '帳務工作區' }));
    expect(nav.getAllByRole('button').map(button => button.textContent)).toEqual(['案件帳務', '銀行對帳', '政府補助清單', '每月帳務']);
    await screen.findByRole('region', { name: '進行中案件清單' });
    expect(monthlyAccountingClient.query).not.toHaveBeenCalled();
    caseWorkspace.unmount();

    openFinance('monthly');
    expect(await screen.findByText('待付 NT$ 12,000')).toBeVisible();
    expect(screen.getByText(/另有 1 筆未定到期日款項未分入月份/)).toBeVisible();
    expect(screen.queryByText(/NT\$ 21,000/)).not.toBeInTheDocument();
  });

  it('lists only formal due obligations and leaves service and collection estimates out of confirmed totals', async () => {
    const estimate = {
      row_id: 'service-estimate', case_no: 'SERVICE', recipient_name: '服務待結束客戶',
      payment_type: 'client_subsidy_return', certainty: 'estimated', source: 'subsidy_estimate',
      payment_status: 'pending', source_amount_ntd: 9000, unpaid_amount_ntd: 9000,
      payment_date: null, date_is_estimate: false, pending_reasons: ['服務尚未完成'],
    } as const;
    const forecast = vi.spyOn(cashRequirementsQueryClient, 'queryAll').mockResolvedValue([
      { ...estimate, pending_reasons: [...estimate.pending_reasons] },
      { ...estimate, row_id: 'collection-estimate', case_no: 'OTHER', recipient_name: '收款待確認客戶', pending_reasons: ['客戶服務費尚未收齊'] },
    ]);
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range,
      [item('FORMAL', 'payable', 9000, 0, 9000)]));
    openFinance();
    expect(await screen.findByText('待付 NT$ 9,000')).toBeVisible();
    const table = await monthDetails();
    expect(table.getByRole('button', { name: 'FORMAL' })).toBeVisible();
    expect(table.queryByRole('row', { name: /SERVICE|OTHER|服務待結束|收款待確認/ })).not.toBeInTheDocument();
    expect(forecast).not.toHaveBeenCalled();
  });

  it('opens the same exact-case subsidy and refund facts from the report and monthly payable', async () => {
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail(caseNo, {
      subsidy_ntd: 12000, bank_facts: [bank(caseNo, 'G', 12000)],
      client_items: [{ ...item(caseNo, 'payable', 8000, 0, 8000), label: '補助退款', version: '1', has_payment: false }],
    }));
    vi.mocked(monthlyAccountingClient.query).mockImplementation(async range => report(range, [item(caseNo, 'payable', 8000, 0, 8000)]));
    const recovery = vi.spyOn(subsidyAdvanceSettlementClient, 'apply');
    openFinance('government-list');
    const fromReport = await openCase(within(screen.getByRole('region', { name: '政府補助報表查詢工作區' })), caseNo, `開啟案件 ${caseNo}`);
    expect(await fromReport.findByText('實撥 NT$ 12,000')).toBeVisible();
    fireEvent.click(fromReport.getAllByRole('button', { name: '關閉案件' })[0]);
    fireEvent.click(screen.getByRole('button', { name: '每月帳務' }));
    const fromPayable = await openCase(await monthDetails(), caseNo);
    expect(await fromPayable.findByText('實撥 NT$ 12,000')).toBeVisible();
    expect(fromPayable.getByRole('columnheader', { name: '預計退款日' })).toBeVisible();
    expect(fromPayable.getByText('客戶退款待結：', { exact: false })).toHaveTextContent('NT$ 8,000');
    expect(vi.mocked(financeAccountingClient.query).mock.calls.map(([selected]) => selected)).toEqual([caseNo, caseNo]);
    expect(recovery).not.toHaveBeenCalled();
  });

  it('opens the staff owner identified by the matched bank payable', async () => {
    const payable = item(caseNo, 'payable', 42000, 0, 42000);
    vi.mocked(financeAccountingClient.query).mockResolvedValue(detail(caseNo, {
      staff_items: [{ ...payable, party: '第二位人員', has_payment: false, version: '1' }],
    }));
    vi.mocked(financeImportQueryClient.listBankTransactions).mockResolvedValue({
      items: [{
        ...governmentRow, bank: 'sinopac', direction: 'outgoing', classification_type: 'staff_payout',
        reference: 'P-9', cases: [caseNo], counterparty_name: '第二位人員',
        reconciliation_target: { case_no: caseNo, obligation_identities: [payable.identity], staff_id: 22 },
      }], pending_count: 1, next_before_row_id: null,
    });
    const query = vi.spyOn(staffPayoutRemediationClient, 'query').mockResolvedValue({
      staff_id: 22, staff_payables_version: 1, events: [],
      obligations: [{ obligation_identity: payable.identity, case_no: caseNo, due_date: date,
        amount_due_ntd: 42000, net_paid_ntd: 0, balance_ntd: 42000, payout_status: 'payable' }],
    });
    openFinance('bank');
    fireEvent.click(await screen.findByRole('button', { name: '核對交易 P-9' }));
    await waitFor(() => expect(query).toHaveBeenCalledWith(22, expect.anything()));
    expect(await screen.findByText(/餘額 NT\$ 42,000/)).toBeVisible();
    expect(query).not.toHaveBeenCalledWith(11, expect.anything());
  });

  it('uses the selected government service period without an application submission step', async () => {
    const drawer = await openGovernment();
    const year = await drawer.findByLabelText('年度');
    const selectedYear = now.getFullYear() - 1;
    fireEvent.change(year, { target: { value: String(selectedYear) } });
    fireEvent.change(drawer.getByLabelText('季度'), { target: { value: '4' } });
    expect(await drawer.findByText(`${selectedYear} · quarter · 4`)).toBeVisible();
    expect(subsidyPeriodClient.query).toHaveBeenLastCalledWith({ unit: 'quarter', year: selectedYear, index: 4 }, expect.any(AbortSignal));
    expect(drawer.queryByText('預計申請年月')).not.toBeInTheDocument();
    expect(drawer.queryByRole('button', { name: '送件' })).not.toBeInTheDocument();
  });

  it('retries the government period query without fabricating zero or performing recovery', async () => {
    vi.mocked(subsidyPeriodClient.query).mockRejectedValueOnce(new Error('lost reply')).mockImplementation(async period => ({
      ...periodView(period),
      coverage: [{ receipt_id: 9, period, label: '本期已入款', amount_ntd: 12000, recovered_advance_ntd: 12000 }],
    }));
    const difference = vi.spyOn(subsidyPeriodClient, 'difference');
    const recovery = vi.spyOn(subsidyAdvanceSettlementClient, 'apply');
    const drawer = await openGovernment();
    expect(await drawer.findByRole('alert')).toHaveTextContent('補助資料暫時無法取得');
    expect(drawer.queryByText('NT$ 0')).not.toBeInTheDocument();
    fireEvent.click(drawer.getByRole('button', { name: '重新整理補助' }));
    expect(await drawer.findByText(/首筆實收 NT\$ 12,000；代墊回收 NT\$ 12,000/)).toBeVisible();
    expect(subsidyPeriodClient.query).toHaveBeenCalledTimes(2);
    expect(difference).not.toHaveBeenCalled();
    expect(recovery).not.toHaveBeenCalled();
  });
});
