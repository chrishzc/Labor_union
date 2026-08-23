/**
 * File: reports_entry_cross_owner_cutover.test.tsx
 * Description: 驗證 #reports 的季度／年度GET、weekly與匯出停用及跨owner邊界。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import type { SubsidyReportPreview } from '../api/reports/subsidy_report_query_schemas';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';

const QUARTERLY_ENDPOINT = '/api/v1/finance-reports/subsidy-reconciliation/quarterly';
const ANNUAL_ENDPOINT = '/api/v1/finance-reports/subsidy-reconciliation/annual';
const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';

type FetchRecord = {
  path: string;
  method: string;
  search: string;
};

type FetchStubOptions = {
  reportResponse?: (kind: 'quarterly' | 'annual', year: number, quarter: number | null, call: number) => Response;
};

function requestUrl(input: string | URL | Request): URL {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(raw, 'http://admin.test');
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function reportEnvelope(
  kind: 'quarterly' | 'annual',
  year: number,
  quarter: number | null,
  data: SubsidyReportPreview = SUBSIDY_REPORT_RESPONSE.data,
): unknown {
  return {
    success: true,
    message: '成功取得補助報表',
    data: {
      ...data,
      period_kind: kind,
      application_year: year,
      quarter,
    },
    error: null,
  };
}

function systemStatusEnvelope(): unknown {
  return {
    success: true,
    message: '成功取得系統效能快照',
    data: {
      started_at: '2026-08-20T01:02:03Z',
      request_count: 17,
      average_response_time_ms: 24.5,
      p50_response_time_upper_bound_ms: 20,
      p95_response_time_upper_bound_ms: 50,
      maximum_response_time_ms: 180,
    },
    error: null,
  };
}

function typedUnavailableResponse(): unknown {
  return {
    detail: {
      error: {
        category: 'unavailable',
        code: 'SUBSIDY_REPORT_UNAVAILABLE',
        message: '補助報表服務暫時無法使用',
        field_errors: [],
        domain_blockers: [],
        retryable: true,
        correlation_id: 'reports-entry-cross-owner-cutover',
        current_version: null,
      },
    },
  };
}

function emptyReportData(): SubsidyReportPreview {
  return {
    ...SUBSIDY_REPORT_RESPONSE.data,
    total_row_count: 0,
    total_amount_ntd: 0,
    partitions: SUBSIDY_REPORT_RESPONSE.data.partitions.map((partition) => ({
      ...partition,
      row_count: 0,
      total_amount_ntd: 0,
      rows: [],
    })),
  };
}

function installFetchStub(options: FetchStubOptions = {}): FetchRecord[] {
  const requests: FetchRecord[] = [];
  let reportCalls = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = requestUrl(input);
    const path = url.pathname;
    requests.push({
      path,
      method: String(init?.method ?? 'GET').toUpperCase(),
      search: url.search,
    });

    if (path === SYSTEM_STATUS_ENDPOINT) return jsonResponse(systemStatusEnvelope());
    if (path !== QUARTERLY_ENDPOINT && path !== ANNUAL_ENDPOINT) {
      throw new Error(`Unexpected API path: ${path}`);
    }

    reportCalls += 1;
    const kind = path === QUARTERLY_ENDPOINT ? 'quarterly' : 'annual';
    const year = Number(url.searchParams.get('application_year'));
    const quarterValue = url.searchParams.get('quarter');
    const quarter = quarterValue === null ? null : Number(quarterValue);
    return options.reportResponse?.(kind, year, quarter, reportCalls)
      ?? jsonResponse(reportEnvelope(kind, year, quarter));
  });
  return requests;
}

let authNonce = 0;

function authenticate(): void {
  authNonce += 1;
  sessionClient.setSession(`reports-entry-cross-owner-token-${authNonce}`, {
    id: 7,
    username: 'reports-entry-admin',
    display_name: 'Reports 入口驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setReportsHash(): void {
  act(() => window.history.replaceState(null, '', '#reports'));
}

function countPath(requests: readonly FetchRecord[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

describe('Reports #reports cross-owner entry static subgate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setReportsHash();
  });

  afterEach(() => {
    cleanup();
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#'));
    vi.restoreAllMocks();
  });

  it('actual StrictMode #reports 僅呈現季度／年度報表且不混入其他 owner 頁面', async () => {
    authenticate();
    const requests = installFetchStub();

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument());
    expect(window.location.hash).toBe('#reports');
    expect(screen.getByText('📊 工會補助核銷報表')).toBeInTheDocument();
    expect(screen.queryByText('🩺 系統狀態')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="system-status.page"]')).toBeNull();

    const initialQuarterlyCount = countPath(requests, QUARTERLY_ENDPOINT);
    expect(screen.getByText(/補助總額/)).toBeInTheDocument();
    expect(screen.getAllByText(/NT\$ 12,000/).length).toBeGreaterThan(0);
    expect(screen.getByText(/A\*+/)).toBeInTheDocument();
    expect(screen.getByText('此類別目前沒有資料。')).toBeInTheDocument();
    expect(document.querySelector('[data-control-id="reports.export.full-workbook"]')).toBeNull();
    expect(document.querySelector('[data-control-id="reports.export.quarterly-xlsx"]')).toBeEnabled();

    fireEvent.change(screen.getByLabelText('檢視'), { target: { value: 'annual' } });
    await waitFor(() => expect(screen.getByText(/2026 年度/)).toBeInTheDocument());
    expect(countPath(requests, ANNUAL_ENDPOINT)).toBe(1);
    expect(document.querySelector('[data-control-id="reports.export.annual-xlsx"]')).toBeEnabled();
    expect(screen.queryByText(/未開放|後端尚未提供/)).not.toBeInTheDocument();

    // TEST_DATA_INCOMPLETE：fixture只有一筆去敏季度列；不把它當成完整production coverage。
    expect(initialQuarterlyCount).toBe(1);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
    expect(requests.every((request) => [
      QUARTERLY_ENDPOINT,
      ANNUAL_ENDPOINT,
      SYSTEM_STATUS_ENDPOINT,
    ].includes(request.path))).toBe(true);
  });

  it('empty report 維持明確空狀態，不以fixture補成假資料', async () => {
    authenticate();
    const emptyRequests = installFetchStub({
      reportResponse: (kind, year, quarter) => jsonResponse(reportEnvelope(kind, year, quarter, emptyReportData())),
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('此期間沒有補助核銷資料。')).toBeInTheDocument());
    expect(screen.queryByText('CASE-RPT-001')).not.toBeInTheDocument();
    expect(countPath(emptyRequests, QUARTERLY_ENDPOINT)).toBe(1);
    expect(emptyRequests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('typed unavailable fail closed；人工retry最多只增加一次同scope GET', async () => {
    authenticate();
    let retryRequested = false;
    const unavailableRequests = installFetchStub({
      reportResponse: (kind, year, quarter) => retryRequested
        ? jsonResponse(reportEnvelope(kind, year, quarter))
        : jsonResponse(typedUnavailableResponse(), 503),
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('補助報表服務暫時無法使用'));
    expect(countPath(unavailableRequests, QUARTERLY_ENDPOINT)).toBe(1);
    retryRequested = true;
    fireEvent.click(screen.getByRole('button', { name: '重新載入' }));
    await waitFor(() => expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument());
    expect(countPath(unavailableRequests, QUARTERLY_ENDPOINT)).toBe(2);
    expect(unavailableRequests.every((request) => request.method === 'GET')).toBe(true);
  });
});
