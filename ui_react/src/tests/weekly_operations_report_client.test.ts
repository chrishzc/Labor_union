/**
 * File: weekly_operations_report_client.test.ts
 * Description: 驗證營運週報 GET、週一起日、strict 解碼、aggregate、canonical PII 與完整 XLSX 匯出邊界。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { weeklyOperationsReportExportClient } from '../api/reports/weekly_operations_report_export_client';
import { weeklyReportMetricsClient } from '../api/reports/weekly_report_metrics_client';
import {
  weeklyOperationsReportQueryClient,
  validateOperationsReportDateRange,
} from '../api/reports/weekly_operations_report_query_client';
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
    const report = await weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/operations-reports/weekly?start_date=2026-08-20&end_date=2026-08-26&schema_version=operations-report.v4');
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('GET');
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).get('Authorization')).toBe('Bearer weekly-report-token');
    expect(report.case_rows).toHaveLength(2);
    expect(report.service_rows[0]?.weekly_hours).toBe(40);
  });

  it('無效日期範圍於 network 前 fail closed', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    await expect(weeklyOperationsReportQueryClient.query('2026-08-26', '2026-08-20')).rejects.toThrow('起日');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('接受跨月與跨年日期範圍', () => {
    expect(() => validateOperationsReportDateRange('2026-09-14', '2026-10-22')).not.toThrow();
    expect(() => validateOperationsReportDateRange('2026-12-31', '2027-01-02')).not.toThrow();
  });

  it('接受 canonical 原始姓名，仍拒絕 aggregate 漂移與 unknown 欄位', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({
        ...WEEKLY_OPERATIONS_RESPONSE,
        data: { ...WEEKLY_OPERATIONS_REPORT, summary: { ...WEEKLY_OPERATIONS_REPORT.summary, application_count: 99 } },
      }))
      .mockResolvedValueOnce(jsonResponse({
        ...WEEKLY_OPERATIONS_RESPONSE,
        data: {
          ...WEEKLY_OPERATIONS_REPORT,
          case_rows: [{ ...WEEKLY_OPERATIONS_REPORT.case_rows[0], applicant_name: '王小明' }, WEEKLY_OPERATIONS_REPORT.case_rows[1]],
          subsidy_partitions: WEEKLY_OPERATIONS_REPORT.subsidy_partitions.map((partition, index) => index === 0 ? {
            ...partition,
            rows: partition.rows.map((row, rowIndex) => rowIndex === 0 ? { ...row, address: '新竹市東區中央路281巷20-1號2樓' } : row),
          } : partition),
        },
      }))
      .mockResolvedValueOnce(jsonResponse({
        ...WEEKLY_OPERATIONS_RESPONSE,
        data: { ...WEEKLY_OPERATIONS_REPORT, browser_calculated_value: 1 },
      }));

    await expect(weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26')).rejects.toThrow('aggregate');
    await expect(weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26')).resolves.toBeDefined();
    await expect(weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26')).rejects.toThrow('結構異常');
  });

  it('下載同一週界的完整 XLSX 並保留後端檔名', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(new Uint8Array([80, 75, 3, 4]), {
      status: 200,
      headers: {
        'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'X-Operations-Report-Version': 'operations-report.v4',
        'content-disposition': 'attachment; filename="operations-report-2026-08-20-2026-08-26.xlsx"',
      },
    }));
    const artifact = await weeklyOperationsReportExportClient.download('2026-08-20', '2026-08-26');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/operations-reports/weekly/export?start_date=2026-08-20&end_date=2026-08-26');
    expect(artifact.filename).toBe('operations-report-2026-08-20-2026-08-26.xlsx');
    expect(artifact.blob.size).toBeGreaterThan(0);
  });

  it('查詢與儲存跨週的週指標，保留未登錄與實際零值差異', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({
        success: true,
        message: 'ok',
        data: WEEKLY_OPERATIONS_REPORT.weekly_metrics,
        error: null,
      }))
      .mockResolvedValueOnce(jsonResponse({
        success: true,
        message: 'ok',
        data: WEEKLY_OPERATIONS_REPORT.weekly_metrics[1],
        error: null,
      }));

    const metrics = await weeklyReportMetricsClient.list('2026-08-20', '2026-08-26');
    expect(metrics).toHaveLength(2);
    expect(metrics[1]?.promotion_count).toBeNull();
    expect(metrics[1]?.inquiry_count).toBe(0);

    await weeklyReportMetricsClient.save('2026-08-24', { promotion_count: null, inquiry_count: 0 });
    expect(fetchMock.mock.calls[1]?.[0]).toBe('/api/v1/operations-reports/weekly/metrics/2026-08-24');
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({ promotion_count: null, inquiry_count: 0 }));
  });
});

function legacyResponse() {
  const data: Record<string, unknown> = { ...WEEKLY_OPERATIONS_REPORT, schema_version: 'operations-report.v3' };
  delete data.annual_totals;
  delete data.monthly_subtotals;
  return { ...WEEKLY_OPERATIONS_RESPONSE, data };
}

describe('weekly report API version compatibility', () => {
  beforeEach(() => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('fixture-session');
  });
  afterEach(() => vi.restoreAllMocks());

  it('舊 API 回 v3 時保留原資料，不補統計、不重試或再打另一個 endpoint', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(legacyResponse()));
    const report = await weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26');
    expect(report.schema_version).toBe('operations-report.v3');
    expect(report.case_rows).toEqual(WEEKLY_OPERATIONS_REPORT.case_rows);
    expect(report).not.toHaveProperty('annual_totals');
    expect(report).not.toHaveProperty('monthly_subtotals');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each(['annual_totals', 'monthly_subtotals'])('v4 缺少 %s 仍拒絕，不偽裝成舊版', async (field) => {
    const data: Record<string, unknown> = { ...WEEKLY_OPERATIONS_REPORT };
    delete data[field];
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ...WEEKLY_OPERATIONS_RESPONSE, data }));
    await expect(weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26')).rejects.toThrow('結構異常');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('兩版仍拒絕混合欄位與未知版本', async () => {
    const legacy = legacyResponse();
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ ...legacy, data: { ...legacy.data, annual_totals: [] } }))
      .mockResolvedValueOnce(jsonResponse({ ...legacy, data: { ...legacy.data, schema_version: 'operations-report.v5' } }));
    await expect(weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26')).rejects.toThrow('結構異常');
    await expect(weeklyOperationsReportQueryClient.query('2026-08-20', '2026-08-26')).rejects.toThrow('結構異常');
  });

  it.each([null, 'operations-report.v3'])('匯出版本 %s 不得當作新版 XLSX', async (version) => {
    const headers: Record<string, string> = { 'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' };
    if (version !== null) headers['X-Operations-Report-Version'] = version;
    const response = new Response(new Uint8Array([80, 75, 3, 4]), { status: 200, headers });
    const readBlob = vi.spyOn(response, 'blob');
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(response);
    await expect(weeklyOperationsReportExportClient.download('2026-08-20', '2026-08-26')).rejects.toMatchObject({
      code: 'WEEKLY_REPORT_EXPORT_VERSION_MISMATCH', retryable: false,
    });
    expect(readBlob).not.toHaveBeenCalled();
  });
});
