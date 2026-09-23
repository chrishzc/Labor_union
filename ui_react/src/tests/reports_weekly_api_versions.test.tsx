/** 舊 API 仍可閱讀，未提供的統計不能當零；新版回應恢復完整統計與匯出。 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { weeklyOperationsReportQueryClient } from '../api/reports/weekly_operations_report_query_client';
import { weeklyOperationsReportExportClient } from '../api/reports/weekly_operations_report_export_client';
import { WeeklyOperationsReportV3Schema } from '../api/reports/weekly_operations_report_schemas';
import { WeeklyOperationsReportError } from '../api/reports/weekly_operations_report_errors';
import { adaptWeeklyOperationsReport } from '../adapters/reports/weekly_operations_report_adapter';
import { ReportsPage } from '../pages/ReportsPage';
import { WEEKLY_OPERATIONS_REPORT } from './fixtures/reports/weekly_operations_report_contract_fixtures';

function legacyReport() {
  const data: Record<string, unknown> = { ...WEEKLY_OPERATIONS_REPORT, schema_version: 'operations-report.v3' };
  delete data.annual_totals;
  delete data.monthly_subtotals;
  return WeeklyOperationsReportV3Schema.parse(data);
}

describe('週報混合 API 版本畫面', () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(cleanup);

  it('v3 保留週次、案件及 metrics，明示統計不可用，不把缺值變成零或空小計', async () => {
    const legacy = legacyReport();
    const view = adaptWeeklyOperationsReport(legacy);
    expect(view.totalsAvailable).toBe(false);
    expect(view.annualTotals).toBeNull();
    expect(view.monthlySubtotals).toBeNull();
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue(legacy);
    const exportSpy = vi.spyOn(weeklyOperationsReportExportClient, 'download');
    render(<ReportsPage />);
    const table = await screen.findByRole('table', { name: '週報案件受理總表' });
    expect(screen.getByText(/週報 API 尚未更新至新版統計/)).toBeInTheDocument();
    expect(within(table).getByText('CASE-WEEK-001')).toBeInTheDocument();
    expect(within(table).getByRole('row', { name: '週次 2026-08-17' })).toBeInTheDocument();
    expect(within(table).queryByRole('row', { name: '115年度累計' })).not.toBeInTheDocument();
    expect(within(table).queryByRole('row', { name: '115年8月小計' })).not.toBeInTheDocument();
    const download = screen.getByRole('button', { name: '下載營運報表 XLSX' });
    expect(download).toBeDisabled();
    fireEvent.click(download);
    expect(exportSpy).not.toHaveBeenCalled();
  });

  it('後端更新後 reload 即恢復統計與下載，不沿用先前的不可用狀態', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query')
      .mockResolvedValueOnce(legacyReport())
      .mockResolvedValueOnce(WEEKLY_OPERATIONS_REPORT);
    render(<ReportsPage />);
    await screen.findByText(/週報 API 尚未更新至新版統計/);
    fireEvent.click(screen.getByRole('button', { name: '重新載入' }));
    await screen.findByRole('row', { name: '115年度累計' });
    expect(screen.queryByText(/週報 API 尚未更新至新版統計/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '下載營運報表 XLSX' })).toBeEnabled();
  });

  it('查詢為新版、匯出卻命中舊 API 時顯示版本原因，不顯示下載成功', async () => {
    vi.spyOn(weeklyOperationsReportQueryClient, 'query').mockResolvedValue(WEEKLY_OPERATIONS_REPORT);
    const message = '週報匯出 API 尚未提供新版統計，請待後端更新後重新載入；未下載舊格式檔案。';
    vi.spyOn(weeklyOperationsReportExportClient, 'download').mockRejectedValue(
      new WeeklyOperationsReportError('WEEKLY_REPORT_EXPORT_VERSION_MISMATCH', message),
    );
    render(<ReportsPage />);
    await screen.findByRole('row', { name: '115年度累計' });
    fireEvent.click(screen.getByRole('button', { name: '下載營運報表 XLSX' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(message));
    expect(screen.queryByText('XLSX 已產生並開始下載。')).not.toBeInTheDocument();
  });
});
