/**
 * File: weekly_operations_report_export_client.ts
 * Description: 下載營運報表三工作表 XLSX，驗證期間、認證、媒體型別與非空內容。
 */
import { sessionClient } from '../auth/session_client';
import { WeeklyOperationsReportError } from './weekly_operations_report_errors';
import { validateOperationsReportDateRange } from './weekly_operations_report_query_client';

export interface WeeklyOperationsReportExportArtifact {
  blob: Blob;
  filename: string;
}

function filenameFromHeader(value: string | null, fallback: string): string {
  const match = value?.match(/filename="?([^";]+)"?/i);
  const candidate = match?.[1]?.trim();
  return candidate && candidate.toLowerCase().endsWith('.xlsx') ? candidate : fallback;
}

export const weeklyOperationsReportExportClient = {
  async download(startDate: string, endDate: string, signal?: AbortSignal): Promise<WeeklyOperationsReportExportArtifact> {
    validateOperationsReportDateRange(startDate, endDate);
    const token = sessionClient.getToken();
    if (!token) throw new WeeklyOperationsReportError('WEEKLY_REPORT_UNAUTHENTICATED', '請先登入後再匯出週報。', false, 401);
    const response = await fetch(`/api/v1/operations-reports/weekly/export?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });
    if (!response.ok) {
      throw new WeeklyOperationsReportError(
        `HTTP_${response.status}`,
        `營運週報匯出失敗（HTTP ${response.status}）。`,
        response.status >= 500,
        response.status,
      );
    }
    const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
    if (!contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
      throw new WeeklyOperationsReportError('WEEKLY_REPORT_EXPORT_MEDIA_TYPE', '營運週報匯出回應不是 XLSX。');
    }
    const blob = await response.blob();
    if (blob.size === 0) throw new WeeklyOperationsReportError('WEEKLY_REPORT_EXPORT_EMPTY', '營運週報匯出檔案為空。');
    const fallback = `operations-report-${startDate}-${endDate}.xlsx`;
    return { blob, filename: filenameFromHeader(response.headers.get('content-disposition'), fallback) };
  },
};
