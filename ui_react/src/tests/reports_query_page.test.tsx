/**
 * File: reports_query_page.test.tsx
 * Description: 驗證 ReportsPage 季度／年度 GET、XLSX export 與跨期間狀態清除。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { subsidyReportQueryClient } from '../api/reports/subsidy_report_query_client';
import { subsidyReportExportClient } from '../api/reports/subsidy_report_export_client';
import { ReportsPage } from '../pages/ReportsPage';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';
describe('ReportsPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(subsidyReportQueryClient, 'query').mockImplementation(async (query) => ({ ...SUBSIDY_REPORT_RESPONSE.data, period_kind: query.kind, application_year: query.applicationYear, quarter: query.kind === 'quarterly' ? query.quarter : null }));
    vi.spyOn(subsidyReportExportClient, 'download').mockResolvedValue({ blob: new Blob(['xlsx']), filename: 'report.xlsx' });
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
  });
  it('renders server report, switches view and downloads the selected XLSX', async () => {
    render(<ReportsPage />);
    await waitFor(() => expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument());
    expect(document.querySelectorAll('main')).toHaveLength(0);
    expect(screen.getByRole('region', { name: '補助報表查詢工作區' })).toBeInTheDocument();
    expect(screen.getAllByText('NT$ 12,000').length).toBeGreaterThan(0);
    expect(screen.getByText(/A\*+/)).toBeInTheDocument();
    expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(1);
    const quarterlyExport = document.querySelector('[data-control-id="reports.export.quarterly-xlsx"]') as HTMLButtonElement;
    expect(quarterlyExport).toBeEnabled();
    fireEvent.click(quarterlyExport);
    await waitFor(() => expect(subsidyReportExportClient.download).toHaveBeenCalledWith(expect.objectContaining({ kind: 'quarterly' })));
    expect(await screen.findByText('XLSX 已產生並開始下載。')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('檢視'), { target: { value: 'annual' } });
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(2));
    const annualExport = document.querySelector('[data-control-id="reports.export.annual-xlsx"]') as HTMLButtonElement;
    expect(annualExport).toBeEnabled();
    fireEvent.click(annualExport);
    await waitFor(() => expect(subsidyReportExportClient.download).toHaveBeenCalledWith(expect.objectContaining({ kind: 'annual' })));
    expect(screen.queryByText(/未開放|後端尚未提供/)).not.toBeInTheDocument();
  });
  it('clears stale export success before year, quarter and reload changes', async () => {
    render(<ReportsPage />);
    await screen.findByText('CASE-RPT-001');

    const exportButton = screen.getByRole('button', { name: '匯出 XLSX' });
    fireEvent.click(exportButton);
    await screen.findByText('XLSX 已產生並開始下載。');
    fireEvent.change(screen.getByLabelText('年度'), { target: { value: '2027' } });
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole('button', { name: '匯出 XLSX' }));
    await screen.findByText('XLSX 已產生並開始下載。');
    fireEvent.change(screen.getByLabelText('季度'), { target: { value: '2' } });
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(3));

    fireEvent.click(screen.getByRole('button', { name: '匯出 XLSX' }));
    await screen.findByText('XLSX 已產生並開始下載。');
    fireEvent.click(screen.getByRole('button', { name: '重新載入' }));
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    await waitFor(() => expect(subsidyReportQueryClient.query).toHaveBeenCalledTimes(4));
  });
  it('ignores an old export completion after the report scope changes', async () => {
    let resolveExport!: (artifact: { blob: Blob; filename: string }) => void;
    vi.mocked(subsidyReportExportClient.download).mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    render(<ReportsPage />);
    await screen.findByText('CASE-RPT-001');

    fireEvent.click(screen.getByRole('button', { name: '匯出 XLSX' }));
    expect(screen.getByRole('button', { name: '正在產生 XLSX…' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('檢視'), { target: { value: 'annual' } });

    await act(async () => {
      resolveExport({ blob: new Blob(['old-xlsx']), filename: 'old-report.xlsx' });
    });
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
  });
});
