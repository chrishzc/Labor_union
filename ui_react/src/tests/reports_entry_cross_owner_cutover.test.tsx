/**
 * File: reports_entry_cross_owner_cutover.test.tsx
 * Description: 驗證 #reports 的營運週報三分頁、季度／年度 regression 與跨 owner GET 邊界。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import { weeklyReportWeekEnd } from '../api/reports/weekly_operations_report_query_client';
import type { SubsidyReportPreview } from '../api/reports/subsidy_report_query_schemas';
import { SUBSIDY_REPORT_RESPONSE } from './fixtures/reports/subsidy_report_query_contract_fixtures';
import { WEEKLY_OPERATIONS_REPORT } from './fixtures/reports/weekly_operations_report_contract_fixtures';

const QUARTERLY_ENDPOINT = '/api/v1/finance-reports/subsidy-reconciliation/quarterly';
const ANNUAL_ENDPOINT = '/api/v1/finance-reports/subsidy-reconciliation/annual';
const WEEKLY_ENDPOINT = '/api/v1/operations-reports/weekly';
const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';

type FetchRecord = {
  path: string;
  method: string;
  search: string;
};

type FetchStubOptions = {
  reportResponse?: (kind: 'quarterly' | 'annual', year: number, quarter: number | null, call: number) => Response;
  weeklyResponse?: (weekStart: string, call: number) => Response;
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

function weeklyEnvelope(weekStart: string, data = WEEKLY_OPERATIONS_REPORT): unknown {
  const weekEnd = weeklyReportWeekEnd(weekStart);
  return {
    success: true,
    message: '成功取得營運週報',
    data: {
      ...data,
      period: { ...data.period, week_start: weekStart, week_end: weekEnd, week_label: `${weekStart}～${weekEnd}` },
      service_rows: data.service_rows.map((row) => ({ ...row, week_start: weekStart, week_end: weekEnd })),
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

function emptyWeeklyData() {
  return {
    ...WEEKLY_OPERATIONS_REPORT,
    summary: {
      ...WEEKLY_OPERATIONS_REPORT.summary,
      application_count: 0,
      general_eligible_count: 0,
      subsidized_eligible_count: 0,
      rejection_unpartitioned_count: 0,
      order_established_count: 0,
      incomplete_count: 0,
    },
    case_rows: [],
    service_rows: [],
    subsidy_partitions: WEEKLY_OPERATIONS_REPORT.subsidy_partitions.map((partition) => ({
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
    if (path === WEEKLY_ENDPOINT) {
      reportCalls += 1;
      const weekStart = url.searchParams.get('week_start') ?? '';
      return options.weeklyResponse?.(weekStart, reportCalls) ?? jsonResponse(weeklyEnvelope(weekStart));
    }
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

  it('actual StrictMode #reports 呈現週報三分頁並保留補助報表，不混入其他 owner', async () => {
    authenticate();
    const requests = installFetchStub();

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('CASE-WEEK-001')).toBeInTheDocument());
    expect(window.location.hash).toBe('#reports');
    expect(screen.getByText('📊 工會營運與補助報表')).toBeInTheDocument();
    expect(screen.queryByText('🩺 系統狀態')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="system-status.page"]')).toBeNull();

    expect(countPath(requests, WEEKLY_ENDPOINT)).toBe(1);
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(document.querySelector('[data-control-id="reports.export.full-workbook"]')).toBeEnabled();
    fireEvent.click(screen.getByRole('tab', { name: '補助案件統計表' }));
    expect(screen.getAllByText(/NT\$ 12,000/).length).toBeGreaterThan(0);
    expect(screen.getByText(/A\*+/)).toBeInTheDocument();
    expect(screen.getByText('此類別目前沒有資料。')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('報表範圍'), { target: { value: 'quarterly' } });
    await waitFor(() => expect(screen.getByText('CASE-RPT-001')).toBeInTheDocument());
    expect(document.querySelector('[data-control-id="reports.export.quarterly-xlsx"]')).toBeEnabled();

    fireEvent.change(screen.getByLabelText('報表範圍'), { target: { value: 'annual' } });
    await waitFor(() => expect(screen.getByText(/2026 年度/)).toBeInTheDocument());
    expect(countPath(requests, ANNUAL_ENDPOINT)).toBe(1);
    expect(document.querySelector('[data-control-id="reports.export.annual-xlsx"]')).toBeEnabled();
    expect(screen.queryByText(/未開放|後端尚未提供/)).not.toBeInTheDocument();

    expect(countPath(requests, QUARTERLY_ENDPOINT)).toBe(1);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
    expect(requests.every((request) => [
      QUARTERLY_ENDPOINT,
      ANNUAL_ENDPOINT,
      WEEKLY_ENDPOINT,
      SYSTEM_STATUS_ENDPOINT,
    ].includes(request.path))).toBe(true);
  });

  it('empty report 維持明確空狀態，不以fixture補成假資料', async () => {
    authenticate();
    const emptyRequests = installFetchStub({
      weeklyResponse: (weekStart) => jsonResponse(weeklyEnvelope(weekStart, emptyWeeklyData())),
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('此期間沒有可列入報表的資料。')).toBeInTheDocument());
    expect(screen.queryByText('CASE-WEEK-001')).not.toBeInTheDocument();
    expect(countPath(emptyRequests, WEEKLY_ENDPOINT)).toBe(1);
    expect(emptyRequests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('typed unavailable fail closed；人工retry最多只增加一次同scope GET', async () => {
    authenticate();
    let retryRequested = false;
    const unavailableRequests = installFetchStub({
      weeklyResponse: (weekStart) => retryRequested
        ? jsonResponse(weeklyEnvelope(weekStart))
        : jsonResponse(typedUnavailableResponse(), 503),
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('補助報表服務暫時無法使用'));
    expect(countPath(unavailableRequests, WEEKLY_ENDPOINT)).toBe(1);
    retryRequested = true;
    fireEvent.click(screen.getByRole('button', { name: '重試' }));
    await waitFor(() => expect(screen.getByText('CASE-WEEK-001')).toBeInTheDocument());
    expect(countPath(unavailableRequests, WEEKLY_ENDPOINT)).toBe(2);
    expect(unavailableRequests.every((request) => request.method === 'GET')).toBe(true);
  });
});
