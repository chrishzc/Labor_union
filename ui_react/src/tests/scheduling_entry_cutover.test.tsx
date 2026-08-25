/**
 * File: scheduling_entry_cutover.test.tsx
 * Description: 驗證 Scheduling 月份軸、獨立資格查詢、GET 預算與受控操作門檻。
 */
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import { sessionClient } from '../api/auth/session_client';
import {
  STAFF_EMPTY_RESPONSE,
  STAFF_RESPONSE_ONE,
} from './fixtures/staff/staff_directory_contract_fixtures';

const STAFF_SUMMARY_ENDPOINT = '/api/v1/staff/summaries';
const CALENDAR_ENDPOINT_PREFIX = '/api/v1/scheduling/staff/';
const ELIGIBILITY_ENDPOINT = '/api/v1/scheduling/eligibility-collisions';
type FetchRecord = {
  path: string;
  method: string;
  query: URLSearchParams;
  signal?: AbortSignal;
};

type FetchMode = 'ready' | 'empty' | 'terms_incomplete' | 'unavailable' | 'retry';

const PERFORMANCE_RESPONSE = {
  success: true,
  message: '成功取得系統效能快照',
  data: {
    started_at: '2026-08-20T01:02:03Z',
    request_count: 1,
    average_response_time_ms: 1,
    p50_response_time_upper_bound_ms: 1,
    p95_response_time_upper_bound_ms: 1,
    maximum_response_time_ms: 1,
  },
  error: null,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function addDays(value: string, amount: number): string {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function datesInRange(start: string, end: string): string[] {
  const dates: string[] = [];
  let current = start;
  while (current <= end) {
    dates.push(current);
    current = addDays(current, 1);
  }
  return dates;
}

function typedErrorResponse(
  code: string,
  message: string,
  status: number,
  category: 'domain_blocked' | 'unavailable'
): Response {
  return jsonResponse({
    detail: {
      error: {
        category,
        code,
        message,
        field_errors: [],
        domain_blockers: [],
        retryable: status >= 500,
        correlation_id: `scheduling-entry-${code}`,
        current_version: null,
      },
    },
  }, status);
}

function projectionResponse(
  staffId: number,
  rangeStart: string,
  rangeEnd: string,
  mode: 'ready' | 'empty'
): unknown {
  if (mode === 'empty') {
    const days = datesInRange(rangeStart, rangeEnd).map((calendarDate) => ({
      calendar_date: calendarDate,
      available: true,
      entries: [],
    }));
    return {
      success: true,
      message: '成功取得目前排班投影',
      data: {
        staff_id: staffId,
        range_start: rangeStart,
        range_end: rangeEnd,
        evaluated_at: '2026-08-21T09:00:00+08:00',
        assignments: [],
        days,
        case_versions: [],
        projection_token: 'b'.repeat(64),
      },
      error: null,
    };
  }

  const dates = datesInRange(rangeStart, rangeEnd);
  const firstDate = dates[0];
  const secondDate = dates[1] ?? firstDate;
  const caseNo = `CASE-SCH-${String(staffId).padStart(3, '0')}`;
  const assignment = {
    assignment_id: staffId + 20,
    case_no: caseNo,
    generation_id: staffId + 30,
    scheduling_version: 3,
    staff_id: staffId,
    status: 'active' as const,
    assigned_start_date: firstDate,
    assigned_end_date: secondDate,
    first_service_at: `${firstDate}T09:00:00+08:00`,
    completion_at: `${secondDate}T18:00:00+08:00`,
    official_service_day_count: 1,
    actual_hours: 8,
  };
  const days = dates.map((calendarDate, index) => {
    if (index === 0) {
      return {
        calendar_date: calendarDate,
        available: false,
        entries: [{
          occupancy_kind: 'official_workday' as const,
          case_no: caseNo,
          assignment_id: assignment.assignment_id,
          assignment_status: 'active' as const,
          lock_id: null,
          segment_id: null,
          availability_block_id: null,
          unavailability_kind: null,
          unavailability_reason: null,
        }],
      };
    }
    if (index === 1) {
      return {
        calendar_date: calendarDate,
        available: false,
        entries: [{
          occupancy_kind: 'assignment_rest' as const,
          case_no: caseNo,
          assignment_id: assignment.assignment_id,
          assignment_status: 'active' as const,
          lock_id: null,
          segment_id: null,
          availability_block_id: null,
          unavailability_kind: null,
          unavailability_reason: null,
        }],
      };
    }
    return { calendar_date: calendarDate, available: true, entries: [] };
  });

  return {
    success: true,
    message: '成功取得目前排班投影',
    data: {
      staff_id: staffId,
      range_start: rangeStart,
      range_end: rangeEnd,
      evaluated_at: '2026-08-21T09:00:00+08:00',
      assignments: [assignment],
      days,
      case_versions: [{ case_no: caseNo, scheduling_version: 3 }],
      projection_token: 'a'.repeat(64),
    },
    error: null,
  };
}

function eligibilityResponse(url: URL): Response {
  const caseNo = url.searchParams.get('case_no') ?? 'CASE-SCH-011';
  const staffId = Number(url.searchParams.get('staff_id') ?? '11');
  const asOf = url.searchParams.get('as_of') ?? '2026-08-21';
  return jsonResponse({
    success: true,
    message: '成功取得資格與檔期衝突投影',
    data: {
      case_no: caseNo,
      case_status: '洽談中',
      as_of: asOf,
      evaluated_at: '2026-08-21T09:00:00+08:00',
      scheduling_version: 3,
      staff: [{
        staff_id: staffId,
        eligibility: 'partial',
        availability: 'unknown',
        qualification_checks: [],
        collisions: [],
        coverage: {
          start_date: null,
          end_date: null,
          required_day_count: null,
          available_day_count: null,
          missing_dates: [],
          review_dates: [],
          status: 'unavailable',
        },
        partial_data: ['service_time_terms_incomplete'],
      }],
      partial_data: ['service_time_terms_incomplete'],
    },
    error: null,
  });
}

function installFetchStub(mode: FetchMode): FetchRecord[] {
  const requests: FetchRecord[] = [];
  let calendarCalls = 0;
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://admin.test');
    const method = String(init?.method ?? 'GET').toUpperCase();
    requests.push({ path: url.pathname, method, query: url.searchParams, signal: init?.signal ?? undefined });

    if (url.pathname === SYSTEM_STATUS_ENDPOINT) {
      return jsonResponse(PERFORMANCE_RESPONSE);
    }
    if (url.pathname === STAFF_SUMMARY_ENDPOINT) {
      return jsonResponse(STAFF_RESPONSE_ONE);
    }
    if (url.pathname === ELIGIBILITY_ENDPOINT) {
      return eligibilityResponse(url);
    }
    if (url.pathname.startsWith(CALENDAR_ENDPOINT_PREFIX)) {
      calendarCalls += 1;
      const match = url.pathname.match(/\/staff\/(\d+)\/current-calendar$/);
      const staffId = Number(match?.[1]);
      const rangeStart = url.searchParams.get('range_start') ?? '';
      const rangeEnd = url.searchParams.get('range_end') ?? '';
      if (mode === 'terms_incomplete') {
        return typedErrorResponse(
          'service_time_terms_incomplete',
          '每日服務時段條款不完整，需補正。',
          422,
          'domain_blocked'
        );
      }
      if (mode === 'unavailable' || (mode === 'retry' && calendarCalls === 1)) {
        return typedErrorResponse(
          'SCHEDULING_UNAVAILABLE',
          '目前排班投影暫時無法取得。',
          503,
          'unavailable'
        );
      }
      return jsonResponse(
        projectionResponse(staffId, rangeStart, rangeEnd, mode === 'empty' ? 'empty' : 'ready')
      );
    }
    throw new Error(`Unexpected API path: ${url.pathname}`);
  });
  return requests;
}

function authenticate(): void {
  sessionClient.setSession('scheduling-entry-token', {
    id: 1,
    username: 'scheduling-entry-admin',
    display_name: '排班驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setSchedulingHash(): void {
  window.history.replaceState(null, '', '#scheduling');
}

function requestsAt(requests: readonly FetchRecord[], path: string): FetchRecord[] {
  return requests.filter((request) => request.path === path);
}

function calendarRequests(requests: readonly FetchRecord[]): FetchRecord[] {
  return requests.filter((request) => request.path.startsWith(CALENDAR_ENDPOINT_PREFIX));
}

function expectOnlyGet(requests: readonly FetchRecord[]): void {
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((request) => request.method === 'GET')).toBe(true);
}

describe('Scheduling #scheduling query entry cutover candidate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setSchedulingHash();
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.history.replaceState(null, '', '#');
    vi.restoreAllMocks();
  });

  it('initial load queries directory and every visible calendar; eligibility waits for an explicit case', async () => {
    authenticate();
    const requests = installFetchStub('ready');

    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => {
      expect(screen.getAllByText('CASE-SCH-011').length).toBeGreaterThan(0);
    });
    expect(window.location.hash).toBe('#scheduling');
    expect(requestsAt(requests, STAFF_SUMMARY_ENDPOINT)).toHaveLength(1);
    expect(calendarRequests(requests)).toHaveLength(2);
    expect(requestsAt(requests, ELIGIBILITY_ENDPOINT)).toHaveLength(0);
    expectOnlyGet(requests);
  });

  it('keeps a complete month axis when the selected calendar is domain-blocked', async () => {
    authenticate();
    const requests = installFetchStub('terms_incomplete');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('每日服務時段尚未完整'));

    const now = new Date();
    const expectedDays = new Date(Date.UTC(now.getFullYear(), now.getMonth() + 1, 0)).getUTCDate();
    expect(document.querySelectorAll('.gantt-day-header-col[data-date]')).toHaveLength(expectedDays);
    expect(calendarRequests(requests)).toHaveLength(2);
  });

  it('queries eligibility for an unassigned candidate from explicit case and staff controls', async () => {
    authenticate();
    const requests = installFetchStub('empty');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(calendarRequests(requests)).toHaveLength(2));

    fireEvent.change(screen.getByRole('textbox', { name: '資格查詢案件編號' }), {
      target: { value: 'CASE-INDEPENDENT-001' },
    });
    fireEvent.click(await screen.findByRole('button', { name: '檢查 服務人員摘要 #12 的資格與檔期' }));

    await waitFor(() => expect(requestsAt(requests, ELIGIBILITY_ENDPOINT)).toHaveLength(1));
    const request = requestsAt(requests, ELIGIBILITY_ENDPOINT)[0];
    expect(request?.query.get('case_no')).toBe('CASE-INDEPENDENT-001');
    expect(request?.query.get('staff_id')).toBe('12');
    await waitFor(() => expect(screen.getByText(/資料待補正：請至訂單管理/)).toBeInTheDocument());
    expect(document.body.textContent).not.toMatch(/測試資料不足|測試資料不完整|test_data_incomplete|unavailable/i);
  });

  it('檔期列已預載且切換月份會重載所有可見人員', async () => {
    authenticate();
    const requests = installFetchStub('ready');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-011').length).toBeGreaterThan(0));
    const initial = calendarRequests(requests).length;
    const initialRangeStart = calendarRequests(requests).at(-1)?.query.get('range_start');

    expect(calendarRequests(requests)).toHaveLength(initial);

    fireEvent.click(screen.getByRole('button', { name: /查看下個月/ }));
    await waitFor(() => expect(calendarRequests(requests)).toHaveLength(initial + 2));
    const monthReloads = calendarRequests(requests).slice(-2);
    expect(monthReloads.map((request) => request.path)).toEqual(expect.arrayContaining([
      expect.stringContaining('/staff/11/current-calendar'),
      expect.stringContaining('/staff/12/current-calendar'),
    ]));
    expect(monthReloads.every((request) => request.query.get('range_start') !== initialRangeStart)).toBe(true);

    fireEvent.change(screen.getByPlaceholderText('按月嫂姓名或編號...'), { target: { value: '不存在' } });
    fireEvent.click(screen.getByRole('button', { name: /🟡 待派單／防撞期/ }));
    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    fireEvent.click(screen.getByRole('button', { name: /服務人員排班甘特月曆/ }));
    expect(calendarRequests(requests)).toHaveLength(initial + 2);
    expectOnlyGet(requests);
  });

  it('explicit retry reloads only the failed row and preserves successful rows', async () => {
    authenticate();
    const requests = installFetchStub('retry');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(/1 位服務人員的排班資料載入失敗/));
    expect(calendarRequests(requests)).toHaveLength(2);

    fireEvent.click(screen.getByRole('button', { name: '重試月曆查詢' }));
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-011').length).toBeGreaterThan(0));
    expect(calendarRequests(requests)).toHaveLength(3);
    expect(calendarRequests(requests).filter((request) => request.path.includes('/staff/11/'))).toHaveLength(2);
    expect(calendarRequests(requests).filter((request) => request.path.includes('/staff/12/'))).toHaveLength(1);
    expectOnlyGet(requests);
  });

  it.each([
    ['empty', '本月無排班占用'],
    ['terms_incomplete', '每日服務時段尚未完整'],
    ['unavailable', '2 位服務人員的排班資料載入失敗'],
  ] as const)('keeps %s explicit and never fabricates occupancy', async (mode, expectedText) => {
    authenticate();
    const requests = installFetchStub(mode);

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getAllByText(new RegExp(expectedText)).length).toBeGreaterThan(0));
    expect(screen.queryByText('CASE-SCH-011')).not.toBeInTheDocument();
    expect(screen.queryByText('正式服務日', { selector: '.span-case-name' })).not.toBeInTheDocument();
    if (mode === 'unavailable') expect(document.body.textContent).not.toMatch(/unavailable/i);
    expect(requestsAt(requests, STAFF_SUMMARY_ENDPOINT)).toHaveLength(1);
    expect(calendarRequests(requests)).toHaveLength(2);
    expectOnlyGet(requests);
  });

  it('aborts an active directory request on unmount and ignores its late response', async () => {
    authenticate();
    const requests: FetchRecord[] = [];
    let resolveDirectory: ((response: Response) => void) | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
      const url = new URL(String(input), 'http://admin.test');
      const method = String(init?.method ?? 'GET').toUpperCase();
      requests.push({ path: url.pathname, method, query: url.searchParams, signal: init?.signal ?? undefined });
      if (url.pathname === SYSTEM_STATUS_ENDPOINT) return Promise.resolve(jsonResponse(PERFORMANCE_RESPONSE));
      if (url.pathname === STAFF_SUMMARY_ENDPOINT) {
        return new Promise<Response>((resolve) => { resolveDirectory = resolve; });
      }
      throw new Error(`Unexpected API path: ${url.pathname}`);
    });

    const rendered = render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(requestsAt(requests, STAFF_SUMMARY_ENDPOINT)).toHaveLength(1));
    const directoryRequest = requestsAt(requests, STAFF_SUMMARY_ENDPOINT)[0];
    expect(directoryRequest?.signal?.aborted).toBe(false);

    rendered.unmount();
    expect(directoryRequest?.signal?.aborted).toBe(true);
    await act(async () => {
      resolveDirectory?.(jsonResponse(STAFF_RESPONSE_ONE));
      await Promise.resolve();
    });

    expect(calendarRequests(requests)).toHaveLength(0);
    expect(document.querySelector('[data-surface-id="scheduling.page"]')).not.toBeInTheDocument();
    expectOnlyGet(requests);
  });

  it('將變更入口保持在明確的業務輸入與確認邊界內', async () => {
    authenticate();
    const requests = installFetchStub('ready');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getAllByText('CASE-SCH-011').length).toBeGreaterThan(0));
    const beforeControls = requests.length;

    expect(screen.getByRole('textbox', { name: '資格查詢案件編號' })).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.candidate-pool.add"]')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /服務中請假與代班/ }));
    expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.leave.preview"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.leave.apply"]')).not.toBeInTheDocument();
    expect(screen.getByText(/請先輸入訂單編號/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /國定假日政策/ }));
    expect(document.querySelector('[data-control-id="scheduling.holiday.query"]')).toBeEnabled();
    expect(document.querySelector('[data-control-id="scheduling.holiday.preview"]')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="scheduling.holiday.apply"]')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /新增國定假日/ })).toBeEnabled();
    expect(requests.length).toBeGreaterThanOrEqual(beforeControls);
    expectOnlyGet(requests);
  });

  it('empty Staff summary keeps the entry explicit without a selected calendar request', async () => {
    authenticate();
    const requests = installFetchStub('empty');
    vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
      const url = new URL(String(input), 'http://admin.test');
      const method = String(init?.method ?? 'GET').toUpperCase();
      requests.push({ path: url.pathname, method, query: url.searchParams, signal: init?.signal ?? undefined });
      if (url.pathname === SYSTEM_STATUS_ENDPOINT) return jsonResponse(PERFORMANCE_RESPONSE);
      if (url.pathname === STAFF_SUMMARY_ENDPOINT) return jsonResponse(STAFF_EMPTY_RESPONSE);
      throw new Error(`Unexpected API path: ${url.pathname}`);
    });

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('目前沒有可顯示的服務人員摘要。')).toBeInTheDocument());
    expect(requestsAt(requests, STAFF_SUMMARY_ENDPOINT)).toHaveLength(1);
    expect(calendarRequests(requests)).toHaveLength(0);
    expectOnlyGet(requests);
  });
});
