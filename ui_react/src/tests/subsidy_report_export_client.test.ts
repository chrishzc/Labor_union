/**
 * File: subsidy_report_export_client.test.ts
 * Description: 驗證補助季度／年度 XLSX export 的 path、認證、媒體型別與檔名。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { subsidyReportExportClient } from '../api/reports/subsidy_report_export_client';

describe('subsidyReportExportClient', () => {
  beforeEach(() => {
    sessionClient.setSession('report-export-token', { id: 1, username: 'tester', display_name: '測試', role: 'operator', linked_line_user_id: null, capabilities: [], is_root: false, access_control_version: 1 });
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('下載季度 XLSX 並保留後端檔名', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([80, 75, 3, 4]), { status: 200, headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'content-disposition': 'attachment; filename="quarter.xlsx"' } }));
    globalThis.fetch = fetchMock;
    const artifact = await subsidyReportExportClient.download({ kind: 'quarterly', applicationYear: 2026, quarter: 3 });
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/finance-reports/subsidy-reconciliation/quarterly/export?application_year=2026&quarter=3');
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer report-export-token');
    expect(artifact.filename).toBe('quarter.xlsx');
    expect(artifact.blob.size).toBeGreaterThan(0);
  });

  it('拒絕非 XLSX 回應', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }));
    await expect(subsidyReportExportClient.download({ kind: 'annual', applicationYear: 2026 })).rejects.toThrow('不是 XLSX');
  });
});
