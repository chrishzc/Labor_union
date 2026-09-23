/**
 * File: reports_weekly_service_display.test.tsx
 * Description: 聚焦驗證營運報表服務工時的有資料、無資料與查詢失敗呈現。
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { weeklyOperationsReportQueryClient } from '../api/reports/weekly_operations_report_query_client';
import { ReportsPage } from '../pages/ReportsPage';
import { WEEKLY_OPERATIONS_REPORT } from './fixtures/reports/weekly_operations_report_contract_fixtures';

describe('ReportsPage service-hours display', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('選到有服務紀錄的期間時顯示服務工時', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue(WEEKLY_OPERATIONS_REPORT);

    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('tab', { name: '每週服務中與工時' }));

    expect(screen.getByText('王**')).toBeInTheDocument();
    expect(screen.getByText('陳**')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('8-3')).toBeInTheDocument();
    expect(screen.getByText('2026/8/17')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      '週數', '序號', '市府案號', '雇主', '服務人員', '每週起始日',
      '每週結束日', '服務時數', '每週工作日數', '每週工時', '結案',
    ]);
    expect(screen.getByRole('columnheader', { name: '服務人員' })).toBeInTheDocument();
  });

  it('每日時數缺值時保留服務日數並顯示提醒', async () => {
    const first = WEEKLY_OPERATIONS_REPORT.service_rows[0];
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue({
      ...WEEKLY_OPERATIONS_REPORT,
      service_rows: [{
        ...first,
        service_hours_per_day: null,
        weekly_hours: null,
        data_quality_codes: ['service_hours_per_day_missing'],
      }],
    });

    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('tab', { name: '每週服務中與工時' }));

    expect(screen.getByRole('status')).toHaveTextContent('已保留可得明細');
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('陳**')).toBeInTheDocument();
  });

  it('營運報表有其他資料但沒有服務工時時明確顯示無資料', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue({
      ...WEEKLY_OPERATIONS_REPORT,
      service_rows: [],
      data_quality_issues: [],
    });

    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('tab', { name: '每週服務中與工時' }));

    expect(screen.getByText('此期間服務工時無資料。')).toBeInTheDocument();
  });

  it('跨月份仍以實際週界分組，並顯示月份週次標籤', async () => {
    const first = WEEKLY_OPERATIONS_REPORT.service_rows[0];
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue({
      ...WEEKLY_OPERATIONS_REPORT,
      service_rows: [
        first,
        { ...first, assignment_id: 702, case_no: 'CASE-WEEK-002' },
        {
          ...first,
          assignment_id: 703,
          case_no: 'CASE-WEEK-003',
          period_start_date: '2026-09-07',
          period_end_date: '2026-09-13',
        },
      ],
    });

    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('tab', { name: '每週服務中與工時' }));

    expect(screen.getByText('8-3')).toHaveAttribute('rowspan', '2');
    expect(screen.getByText('9-1')).toHaveAttribute('rowspan', '1');
    const tables = screen.getByRole('region', { name: '服務工時資料，可左右捲動' }).querySelectorAll('table');
    expect(tables).toHaveLength(2);
    expect(within(tables[0]).getAllByRole('row')).toHaveLength(3);
    expect(within(tables[1]).getAllByRole('row')).toHaveLength(2);
    expect(within(tables[0]).getAllByRole('cell', { name: '2026/8/17' })).toHaveLength(2);
    expect(within(tables[1]).getByRole('cell', { name: '2026/9/7' })).toBeInTheDocument();
    expect(within(within(tables[1]).getAllByRole('row')[1]).getByRole('cell', { name: '1' })).toBeInTheDocument();
  });

  it('請假代班後重新載入，依月嫂與週別顯示各自有效工作日', async () => {
    const first = WEEKLY_OPERATIONS_REPORT.service_rows[0];
    const originalReport = {
      ...WEEKLY_OPERATIONS_REPORT,
      service_rows: [
        { ...first, assignment_id: 701, staff_name: '原月嫂', weekly_work_days: 1, weekly_hours: 8 },
        { ...first, assignment_id: 702, staff_name: '代班月嫂', weekly_work_days: 1, weekly_hours: 8 },
      ],
    };
    const correctedReport = {
      ...originalReport,
      service_rows: [
        originalReport.service_rows[0],
        { ...originalReport.service_rows[1], period_start_date: '2026-08-24',
          period_end_date: '2026-08-30' },
      ],
    };
    const query = vi.spyOn(weeklyOperationsReportQueryClient, 'query')
      .mockResolvedValueOnce(originalReport).mockResolvedValueOnce(correctedReport);
    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('tab', { name: '每週服務中與工時' }));
    expect(screen.getAllByText('CASE-WEEK-001')).toHaveLength(2);
    expect(screen.getAllByText('2026/8/17')).toHaveLength(2);
    expect(screen.getByText('8-3')).toHaveAttribute('rowspan', '2');
    fireEvent.click(screen.getByRole('button', { name: '重新載入' }));
    await screen.findByText('2026/8/24');
    expect(screen.getByText('8-4')).toHaveAttribute('rowspan', '1');
    const tables = screen.getByRole('region', { name: '服務工時資料，可左右捲動' }).querySelectorAll('table');
    expect(tables).toHaveLength(2);
    expect(within(tables[0]).getByText('原月嫂')).toBeInTheDocument();
    expect(within(tables[1]).getByText('代班月嫂')).toBeInTheDocument();
    expect(within(tables[0]).getAllByRole('cell').at(-3)).toHaveTextContent('1');
    expect(within(tables[0]).getAllByRole('cell').at(-2)).toHaveTextContent('8');
    expect(within(tables[1]).getAllByRole('cell').at(-3)).toHaveTextContent('1');
    expect(within(tables[1]).getAllByRole('cell').at(-2)).toHaveTextContent('8');
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('整個期間沒有案件資料時仍顯示每週補登值並說明案件無資料', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue({
      ...WEEKLY_OPERATIONS_REPORT,
      case_rows: [],
      subsidy_partitions: [],
      service_rows: [],
      data_quality_issues: [],
    });

    render(<ReportsPage />);

    expect(await screen.findByText('此期間沒有案件受理資料。')).toBeInTheDocument();
    expect(screen.getAllByText('2026-08-17～2026-08-23')).not.toHaveLength(0);
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('營運報表查詢失敗時顯示錯誤而不是空白', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockRejectedValue(new Error('營運報表查詢失敗'));

    render(<ReportsPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('營運報表查詢失敗');
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument();
  });
});
