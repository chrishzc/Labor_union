/** 驗證年度置頂、星期一歸月、月小計置底，以及 server totals 不被前端重新推算。 */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { weeklyOperationsReportQueryClient } from '../api/reports/weekly_operations_report_query_client';
import { WeeklyOperationsReportSchema } from '../api/reports/weekly_operations_report_schemas';
import { ReportsPage } from '../pages/ReportsPage';
import { WEEKLY_OPERATIONS_REPORT } from './fixtures/reports/weekly_operations_report_contract_fixtures';

function statusCounts(count: number) {
  return Object.fromEntries(Object.keys(WEEKLY_OPERATIONS_REPORT.annual_totals[0].order_status_counts)
    .map((status) => [status, status === '服務中' ? count : 0]));
}

function crossMonthReport() {
  const report = structuredClone(WEEKLY_OPERATIONS_REPORT);
  report.period = {
    start_date: '2026-08-31', end_date: '2026-09-13',
    timezone: 'Asia/Taipei', period_label: '2026-08-31～2026-09-13',
  };
  report.case_rows = ['2026-08-31', '2026-09-01', '2026-09-07'].map((day, index) => ({
    ...report.case_rows[0],
    case_no: `CASE-MONTH-${index + 1}`,
    applicant_name: `測試案件${index + 1}`,
    application_date: day,
    week_start_date: index < 2 ? '2026-08-31' : '2026-09-07',
    week_end_date: index < 2 ? '2026-09-06' : '2026-09-13',
    week_label: index < 2 ? '2026-08-31 ~ 2026-09-06' : '2026-09-07 ~ 2026-09-13',
  }));
  report.summary = {
    ...report.summary,
    application_count: 3, general_eligible_count: 3,
    rejection_unpartitioned_count: 0, order_established_count: 3, incomplete_count: 0,
  };
  report.weekly_metrics = [
    { week_start_date: '2026-08-31', week_end_date: '2026-09-06', promotion_count: 12, inquiry_count: 34, updated_at: null },
    { week_start_date: '2026-09-07', week_end_date: '2026-09-13', promotion_count: 5, inquiry_count: 0, updated_at: null },
  ];
  report.monthly_subtotals = [
    { ...report.summary, year: 2026, month: 8, start_date: '2026-08-31', end_date: '2026-09-06',
      application_count: 2, general_eligible_count: 2, order_established_count: 2,
      promotion_count: 12, inquiry_count: 34, review_rejected_count: 0, order_status_counts: statusCounts(2) },
    { ...report.summary, year: 2026, month: 9, start_date: '2026-09-07', end_date: '2026-09-13',
      application_count: 1, general_eligible_count: 1, order_established_count: 1,
      promotion_count: 5, inquiry_count: 0, review_rejected_count: 0, order_status_counts: statusCounts(1) },
  ];
  report.annual_totals = [{
    ...report.summary, year: 2026, month: null, start_date: '2026-01-05', end_date: '2026-09-13',
    application_count: 10, general_eligible_count: 10, order_established_count: 10,
    promotion_count: 77, inquiry_count: 99, review_rejected_count: 0, order_status_counts: statusCounts(10),
  }];
  return report;
}

async function renderReport(report = crossMonthReport()) {
  vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue(report);
  render(<ReportsPage />);
  return screen.findByRole('table', { name: '週報案件受理總表' });
}

describe('週報年度累計與月小計', () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(cleanup);

  it('年度在最上方，跨月整週只出現一次，各月小計在該月最後一組資料下方', async () => {
    const table = await renderReport();
    const order = [...table.querySelectorAll<HTMLTableRowElement>('tbody > tr')]
      .map((row) => row.getAttribute('aria-label') ?? row.cells[0].textContent);
    expect(order).toEqual([
      '115年度累計', '週次 2026-08-31', 'CASE-MONTH-1', 'CASE-MONTH-2',
      '115年8月小計', '週次 2026-09-07', 'CASE-MONTH-3', '115年9月小計',
    ]);
    const annual = within(table).getByRole('row', { name: '115年度累計' });
    expect(within(annual).getByText('平台案件申請數：10')).toBeInTheDocument();
    expect(within(annual).getByText('推廣次數：77')).toBeInTheDocument();
    const august = within(table).getByRole('row', { name: '115年8月小計' });
    expect(within(august).getByText('平台案件申請數：2')).toBeInTheDocument();
    expect(within(august).getByText('推廣次數：12')).toBeInTheDocument();
    expect(within(table).getAllByText('CASE-MONTH-2')).toHaveLength(1);
  });

  it('未完整登錄不顯示為零；已登錄的零保留', async () => {
    const report = crossMonthReport();
    report.weekly_metrics[0].promotion_count = null;
    report.monthly_subtotals[0].promotion_count = null;
    report.annual_totals[0].promotion_count = null;
    const table = await renderReport(report);
    const august = within(table).getByRole('row', { name: '115年8月小計' });
    const september = within(table).getByRole('row', { name: '115年9月小計' });
    expect(within(august).getByText('推廣次數：未完整登錄')).toBeInTheDocument();
    expect(within(september).getByText('詢問人次：0')).toBeInTheDocument();
    expect(within(table).getByRole('row', { name: '週次 2026-08-31' })).toHaveTextContent('推廣次數：未登錄／待補正');
  });

  it('案件為空仍保留每週數值及月小計', async () => {
    const report = crossMonthReport();
    report.case_rows = [];
    report.summary = { ...report.summary, application_count: 0, general_eligible_count: 0, order_established_count: 0 };
    report.monthly_subtotals = report.monthly_subtotals.map((total) => ({
      ...total, application_count: 0, general_eligible_count: 0, order_established_count: 0, order_status_counts: statusCounts(0),
    }));
    const table = await renderReport(report);
    expect(screen.getByText('此期間沒有案件受理資料。')).toBeInTheDocument();
    expect(within(table).getByRole('row', { name: '週次 2026-08-31' })).toBeInTheDocument();
    const subtotal = within(table).getByRole('row', { name: '115年8月小計' });
    expect(within(subtotal).getByText('平台案件申請數：0')).toBeInTheDocument();
    expect(within(subtotal).getByText('推廣次數：12')).toBeInTheDocument();
  });

  it('strict view 接受年度／月小計並拒絕缺少總計欄位', () => {
    const report = crossMonthReport();
    expect(WeeklyOperationsReportSchema.parse(report).annual_totals[0].application_count).toBe(10);
    const missingAnnual = { ...report, annual_totals: undefined };
    const missingMonth = { ...report, monthly_subtotals: undefined };
    expect(WeeklyOperationsReportSchema.safeParse(missingAnnual).success).toBe(false);
    expect(WeeklyOperationsReportSchema.safeParse(missingMonth).success).toBe(false);
  });

  it('顯示每種訂單狀態及缺值；使用 server 年度數值，不把服務中併入訂單成立', async () => {
    const report = crossMonthReport();
    const counts = report.annual_totals[0].order_status_counts;
    counts['待補件'] = 2;
    counts['訂單成立'] = 4;
    counts['歷史訂單－服務中'] = 3;
    counts['無訂單／狀態缺值'] = 1;
    report.annual_totals[0].application_count = Object.values(counts).reduce((sum, n) => sum + n, 0);
    const table = await renderReport(report);
    const annual = within(table).getByRole('row', { name: '115年度累計' });
    for (const [status, count] of Object.entries(counts)) {
      expect(within(annual).getByText(`${status}：${count}`)).toBeInTheDocument();
    }
    expect(within(annual).getByText('服務中：10')).toBeInTheDocument();
    expect(within(annual).getByText('訂單成立：4')).toBeInTheDocument();
    expect(within(annual).getByText('審核不符合（獨立）：0')).toBeInTheDocument();
  });

  it('strict status totals 拒絕缺值、負值或字串計數', () => {
    for (const invalid of [undefined, { 待補件: -1 }, { 待補件: '1' }]) {
      const report = crossMonthReport();
      const annual = { ...report.annual_totals[0], order_status_counts: invalid };
      expect(WeeklyOperationsReportSchema.safeParse({ ...report, annual_totals: [annual] }).success).toBe(false);
    }
  });

});
