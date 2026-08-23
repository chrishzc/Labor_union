/**
 * File: weekly_operations_report_client.test.ts
 * Description: 驗證營運週報 GET、週一起日、strict 解碼、aggregate、PII 與完整 XLSX 匯出邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { weeklyOperationsReportExportClient } from '../api/reports/weekly_operations_report_export_client';
import { weeklyOperationsReportQueryClient } from '../api/reports/weekly_operations_report_query_client';
import {
  WEEKLY_OPERATIONS_REPORT,
  WEEKLY_OPERATIONS_RESPONSE,
} from './fixtures/reports/weekly_operations_report_contract_fixtures';

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } });
}

describe('weekly operations report clients', () => {
  beforeEach(() => {
    sessionClient.setSession('weekly-report-token', {
      id: 9,
      username: 'weekly-reports',
      display_name: '週報驗證員',
      role: 'admin',
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('以 fresh bearer 執行單一週報 GET 並接受 strict 三分頁 view', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(WEEKLY_OPERATIONS_RESPONSE));
    const report = await weeklyOperationsReportQueryClient.query('2026-08-17');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/operations-reports/weekly?week_start=2026-08-17');
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('GET');
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer weekly-report-token');
    expect(report.case_rows).toHaveLength(2);
    expect(report.service_rows[0]?.weekly_hours).toBe(40);
  });

  it('非週一起日於 network 前 fail closed', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    await expect(weeklyOperationsReportQueryClient.query('2026-08-18')).rejects.toThrow('星期一');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('拒絕 aggregate 漂移、未遮罩姓名與 unknown 欄位', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({
        ...WEEKLY_OPERATIONS_RESPONSE,
        data: { ...WEEKLY_OPERATIONS_REPORT, summary: { ...WEEKLY_OPERATIONS_REPORT.summary, application_count: 99 } },
      }))
      .mockResolvedValueOnce(jsonResponse({
        ...WEEKLY_OPERATIONS_RESPONSE,
        data: {
          ...WEEKLY_OPERATIONS_REPORT,
          case_rows: [{ ...WEEKLY_OPERATIONS_REPORT.case_rows[0], applicant_name_masked: '王小明' }, WEEKLY_OPERATIONS_REPORT.case_rows[1]],
        },
      }))
      .mockResolvedValueOnce(jsonResponse({
        ...WEEKLY_OPERATIONS_RESPONSE,
        data: { ...WEEKLY_OPERATIONS_REPORT, browser_calculated_value: 1 },
      }));

    await expect(weeklyOperationsReportQueryClient.query('2026-08-17')).rejects.toThrow('aggregate');
    await expect(weeklyOperationsReportQueryClient.query('2026-08-17')).rejects.toThrow('未遮罩');
    await expect(weeklyOperationsReportQueryClient.query('2026-08-17')).rejects.toThrow('結構異常');
  });

  it('下載同一週界的完整 XLSX 並保留後端檔名', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(new Uint8Array([80, 75, 3, 4]), {
      status: 200,
      headers: {
        'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'content-disposition': 'attachment; filename="weekly-2026-08-17-2026-08-23.xlsx"',
      },
    }));
    const artifact = await weeklyOperationsReportExportClient.download('2026-08-17');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/operations-reports/weekly/export?week_start=2026-08-17');
    expect(artifact.filename).toBe('weekly-2026-08-17-2026-08-23.xlsx');
    expect(artifact.blob.size).toBeGreaterThan(0);
  });
});
