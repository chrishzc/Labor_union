/**
 * File: reports_query_page.test.tsx
 * Description: 驗證 ReportsPage 週報三分頁、季度／年度 regression、XLSX 與 stale 狀態清除。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { subsidyReportExportClient } from '../api/reports/subsidy_report_export_client';
import { weeklyOperationsReportExportClient } from '../api/reports/weekly_operations_report_export_client';
import { weeklyOperationsReportQueryClient } from '../api/reports/weekly_operations_report_query_client';
import { ReportsPage } from '../pages/ReportsPage';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';
import { WEEKLY_OPERATIONS_REPORT } from './fixtures/reports/weekly_operations_report_contract_fixtures';
describe('ReportsPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(subsidyReportQueryClient, 'query').mockImplementation(async (query) => ({ ...SUBSIDY_REPORT_RESPONSE.data, period_kind: query.kind, application_year: query.applicationYear, quarter: query.kind === 'quarterly' ? query.quarter : null }));
    vi.spyOn(subsidyReportExportClient, 'download').mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'report.xlsx' });
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockImplementation(async (startDate, endDate) => ({
      ...WEEKLY_OPERATIONS_REPORT,
      period: { ...WEEKLY_OPERATIONS_REPORT.period, start_date: startDate, end_date: endDate, period_label: `${startDate}～${endDate}` },
      service_rows: WEEKLY_OPERATIONS_REPORT.service_rows.map((row) => ({ ...row, period_start_date: startDate, period_end_date: endDate })),
    }));
    vi.spyOn(weeklyOperationsReportExportClient, 'download').mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'weekly.xlsx' });
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });
  it('顯示週報三分頁、null 待補正與完整 XLSX，並保留季度／年度補助', async () => {
    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    expect(screen.getByRole('region', { name: '營運與補助報表查詢工作區' })).toBeInTheDocument();
    expect(screen.getAllByText('未登錄／待補正').length).toBeGreaterThan(1);
    expect(screen.getAllByRole('tab')).toHaveLength(3);

    fireEvent.click(screen.getByRole('tab', { name: '補助案件統計表' }));
    expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument();
    expect(screen.getAllByText('NT$ 12,000').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^\d{4}-\d{2}-\d{2}～\d{4}-\d{2}-\d{2}$/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/年初至本週/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: '每週服務中與工時' }));
    expect(screen.getByText('陳**')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '下載營運報表 XLSX' }));
    await waitFor(() => expect(weeklyOperationsReportExportClient.download).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('XLSX 已產生並開始下載。')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('報表範圍'), { target: { value: 'quarterly' } });
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(1));
    expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument();
    const quarterlyExport = document.querySelector('[data-control-id="reports.export.quarterly-xlsx"]') as HTMLButtonElement;
    fireEvent.click(quarterlyExport);
    await waitFor(() => expect(subsidyReportExportClient.download).toHaveBeenCalledWith(expect.objectContaining({ kind: 'quarterly' }), expect.any(AbortSignal)));

    fireEvent.change(screen.getByLabelText('報表範圍'), { target: { value: 'annual' } });
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(2));
    expect(document.querySelector('[data-control-id="reports.export.annual-xlsx"]')).toBeEnabled();
    expect(screen.queryByText(/未開放|後端尚未提供/)).not.toBeInTheDocument();
  });

  it('日期範圍與 reload 變更會清除 stale export success', async () => {
    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');
    fireEvent.click(screen.getByRole('button', { name: '下載營運報表 XLSX' }));
    await screen.findByText('XLSX 已產生並開始下載。');

    const startInput = screen.getByLabelText('起日');
    expect(startInput).toHaveAttribute('type', 'date');
    fireEvent.change(startInput, { target: { value: '2026-08-13' } });
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    await waitFor(() => expect(weeklyOperationsReportQueryClient.query).toHaveBeenLastCalledWith(
      '2026-08-13',
      expect.any(String),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));

    fireEvent.click(screen.getByRole('button', { name: '下載營運報表 XLSX' }));
    await screen.findByText('XLSX 已產生並開始下載。');
    fireEvent.click(screen.getByRole('button', { name: '重新載入' }));
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    await waitFor(() => expect(weeklyOperationsReportQueryClient.query).toHaveBeenCalledTimes(3));
  });

  it('手動日期範圍變更後保留選定期間', async () => {
    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');

    const startInput = screen.getByLabelText('起日') as HTMLInputElement;
    const endInput = screen.getByLabelText('迄日') as HTMLInputElement;
    fireEvent.change(startInput, { target: { value: '2026-08-20' } });
    fireEvent.change(endInput, { target: { value: '2026-08-31' } });

    await waitFor(() => expect(weeklyOperationsReportQueryClient.query).toHaveBeenLastCalledWith(
      '2026-08-20',
      '2026-08-31',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(startInput.value).toBe('2026-08-20');
    expect(endInput.value).toBe('2026-08-31');
  });

  it('scope 變更後忽略舊週報 export completion', async () => {
    let resolveExport!: (artifact: { blob: Blob; filename: string }) => void;
    vi.mocked(weeklyOperationsReportExportClient.download).mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    render(<ReportsPage />);
    await screen.findByText('CASE-WEEK-001');

    fireEvent.click(screen.getByRole('button', { name: '下載營運報表 XLSX' }));
    expect(screen.getByRole('button', { name: '正在產生 XLSX…' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('報表範圍'), { target: { value: 'annual' } });

    await act(async () => {
      resolveExport({ blob: new Blob(['old-xlsx']), filename: 'old-report.xlsx' });
    });
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
  });
});
