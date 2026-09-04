/**
 * File: reports_weekly_service_display.test.tsx
 * Description: 聚焦驗證營運報表服務工時的有資料、無資料與查詢失敗呈現。
 */
import { fireEvent, render, screen } from '@testing-library/react';
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
    fireEvent.click(screen.getByRole('tab', { name: '每周服務中說明' }));

    expect(screen.getByText('王**')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
  });

  it('營運報表有其他資料但沒有服務工時時明確顯示無資料', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue({
      ...WEEKLY_OPERATIONS_REPORT,
      service_rows: [],
      data_quality_issues: [],
    });

    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('tab', { name: '每周服務中說明' }));

    expect(screen.getByText('此期間服務工時無資料。')).toBeInTheDocument();
  });

  it('整個期間沒有可列入資料時明確顯示無資料', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue({
      ...WEEKLY_OPERATIONS_REPORT,
      case_rows: [],
      subsidy_partitions: [],
      service_rows: [],
      data_quality_issues: [],
    });

    render(<ReportsPage />);

    expect(await screen.findByText('此期間沒有可列入報表的資料。')).toBeInTheDocument();
  });

  it('營運報表查詢失敗時顯示錯誤而不是空白', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockRejectedValue(new Error('營運報表查詢失敗'));

    render(<ReportsPage />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('營運報表查詢失敗');
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument();
  });
});