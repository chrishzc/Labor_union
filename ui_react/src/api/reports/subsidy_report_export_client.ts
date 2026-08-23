/**
 * File: subsidy_report_export_client.ts
 * Description: 下載既有季度／年度補助核銷 XLSX，驗證認證、媒體型別與非空內容。
 */
import { sessionClient } from '../auth/session_client';

export type SubsidyReportExportQuery =
  | { kind: 'quarterly'; applicationYear: number; quarter: number }
  | { kind: 'annual'; applicationYear: number };

export interface SubsidyReportExportArtifact {
  blob: Blob;
  filename: string;
}

function filenameFromHeader(value: string | null, fallback: string): string {
  const match = value?.match(/filename="?([^";]+)"?/i);
  const candidate = match?.[1]?.trim();
  return candidate && candidate.toLowerCase().endsWith('.xlsx') ? candidate : fallback;
}

export const subsidyReportExportClient = {
  async download(query: SubsidyReportExportQuery, signal?: AbortSignal): Promise<SubsidyReportExportArtifact> {
    const token = sessionClient.getToken();
    if (!token) throw new Error('請先登入後再匯出補助報表。');
    const path = `/api/v1/finance-reports/subsidy-reconciliation/${query.kind}/export`;
    const params = new URLSearchParams({ application_year: String(query.applicationYear) });
    if (query.kind === 'quarterly') params.set('quarter', String(query.quarter));
    const response = await fetch(`${path}?${params}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });
    if (!response.ok) throw new Error(`補助報表匯出失敗（HTTP ${response.status}）。`);
    const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
    if (!contentType.includes('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')) {
      throw new Error('補助報表匯出回應不是 XLSX。');
    }
    const blob = await response.blob();
    if (blob.size === 0) throw new Error('補助報表匯出檔案為空。');
    const fallback = query.kind === 'quarterly'
      ? `subsidy-reconciliation-${query.applicationYear}-Q${query.quarter}.xlsx`
      : `subsidy-reconciliation-${query.applicationYear}.xlsx`;
    return { blob, filename: filenameFromHeader(response.headers.get('content-disposition'), fallback) };
  },
};
