/**
 * File: staff_entry_cutover.test.tsx
 * Description: 驗證 #staff StrictMode 查詢預算、資格分片與無永久假控制項。
 */
import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import {
  STAFF_RESPONSE_ONE,
} from './fixtures/staff/staff_directory_contract_fixtures';
import {
  STAFF_LIFECYCLE_QUERY_RESPONSE,
} from './fixtures/staff/staff_lifecycle_contract_fixtures';
import {
  STAFF_PREFERENCE_DEFINITIONS_RESPONSE,
  STAFF_PREFERENCE_PROFILE_RESPONSE,
} from './fixtures/staff/staff_preferences_contract_fixtures';
import {
  STAFF_AVAILABILITY_QUERY_RESPONSE,
} from './fixtures/staff/staff_availability_contract_fixtures';
import { STAFF_QUALIFICATION_RESPONSE } from './fixtures/staff/staff_qualification_contract_fixtures';

const STAFF_SUMMARY_ENDPOINT = '/api/v1/staff/summaries';
const STAFF_LIFECYCLE_ENDPOINT = '/api/v1/staff/11/lifecycle';
const STAFF_QUALIFICATION_ENDPOINT = '/api/v1/staff/11/qualification-master';
const PREFERENCE_DEFINITIONS_ENDPOINT = '/api/v1/scheduling/staff-matching-preferences/definitions';
const PREFERENCE_PROFILE_ENDPOINT = '/api/v1/scheduling/staff-matching-preferences/staff/11';
const AVAILABILITY_ENDPOINT = '/api/v1/scheduling/staff/11/availability-blocks';

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

type FetchRecord = {
  path: string;
  method: string;
};

function getUrl(input: string | URL | Request): URL {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(raw, 'http://admin.test');
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function authenticate(): void {
  sessionClient.setSession('staff-entry-cutover-token', {
    id: 7,
    username: 'staff-entry-cutover-admin',
    display_name: 'Staff entry 驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function installFetchStub(): FetchRecord[] {
  const requests: FetchRecord[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = getUrl(input);
    const method = String(init?.method ?? 'GET').toUpperCase();
    requests.push({ path: url.pathname, method });

    if (url.pathname === SYSTEM_STATUS_ENDPOINT) {
      return jsonResponse(PERFORMANCE_RESPONSE);
    }
    if (url.pathname === STAFF_SUMMARY_ENDPOINT) {
      return jsonResponse(STAFF_RESPONSE_ONE);
    }
    if (url.pathname === STAFF_LIFECYCLE_ENDPOINT) {
      return jsonResponse({
        ...STAFF_LIFECYCLE_QUERY_RESPONSE,
        data: { ...STAFF_LIFECYCLE_QUERY_RESPONSE.data, staff_id: 11 },
      });
    }
    if (url.pathname === STAFF_QUALIFICATION_ENDPOINT) {
      return jsonResponse(STAFF_QUALIFICATION_RESPONSE);
    }
    if (url.pathname === PREFERENCE_DEFINITIONS_ENDPOINT) {
      return jsonResponse(STAFF_PREFERENCE_DEFINITIONS_RESPONSE);
    }
    if (url.pathname === PREFERENCE_PROFILE_ENDPOINT) {
      return jsonResponse({
        ...STAFF_PREFERENCE_PROFILE_RESPONSE,
        data: { ...STAFF_PREFERENCE_PROFILE_RESPONSE.data, staff_id: 11 },
      });
    }
    if (url.pathname === AVAILABILITY_ENDPOINT) {
      return jsonResponse({
        ...STAFF_AVAILABILITY_QUERY_RESPONSE,
        data: STAFF_AVAILABILITY_QUERY_RESPONSE.data.map((block) => ({ ...block, staff_id: 11 })),
      });
    }
    return jsonResponse({ detail: 'Unexpected Staff entry request' }, 404);
  });
  return requests;
}

function countPath(requests: readonly FetchRecord[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

function expectOnlyGet(requests: readonly FetchRecord[]): void {
  expect(requests.every((request) => request.method === 'GET')).toBe(true);
}

describe('Staff #staff entry cutover candidate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    window.history.replaceState(null, '', '#staff');
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.history.replaceState(null, '', '#');
    vi.restoreAllMocks();
  });

  it('actual StrictMode 初始只發一個 Staff summaries GET，未選人員不查詢分片', async () => {
    authenticate();
    const requests = installFetchStub();

    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    expect(window.location.hash).toBe('#staff');
    expect(countPath(requests, STAFF_SUMMARY_ENDPOINT)).toBe(1);
    expect(requests.filter((request) => request.path !== SYSTEM_STATUS_ENDPOINT)).toHaveLength(1);
    expectOnlyGet(requests);
  });

  it('選擇服務人員時 Roster lifecycle 與 qualification 各一個 GET，且不發 mutation', async () => {
    authenticate();
    const requests = installFetchStub();

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    await waitFor(() => expect(countPath(requests, STAFF_LIFECYCLE_ENDPOINT)).toBe(1));
    await waitFor(() => expect(countPath(requests, STAFF_QUALIFICATION_ENDPOINT)).toBe(1));
    expect(countPath(requests, STAFF_LIFECYCLE_ENDPOINT)).toBeLessThanOrEqual(1);
    expect(countPath(requests, PREFERENCE_DEFINITIONS_ENDPOINT)).toBe(0);
    expect(countPath(requests, PREFERENCE_PROFILE_ENDPOINT)).toBe(0);
    expect(countPath(requests, AVAILABILITY_ENDPOINT)).toBe(0);
    expectOnlyGet(requests);
  });

  it('Preferences tab 對 definitions 與 profile 各發一個 GET', async () => {
    authenticate();
    const requests = installFetchStub();

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });

    await waitFor(() => expect(screen.getByDisplayValue('20–30')).toBeInTheDocument());
    expect(countPath(requests, PREFERENCE_DEFINITIONS_ENDPOINT)).toBe(1);
    expect(countPath(requests, PREFERENCE_PROFILE_ENDPOINT)).toBe(1);
    expect(countPath(requests, STAFF_LIFECYCLE_ENDPOINT)).toBe(0);
    expect(countPath(requests, AVAILABILITY_ENDPOINT)).toBe(0);
    expectOnlyGet(requests);
  });

  it('Availability 未輸入日期範圍時維持零 GET', async () => {
    authenticate();
    const requests = installFetchStub();

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    fireEvent.change(screen.getByLabelText('查詢服務人員'), { target: { value: '11' } });
    await waitFor(() => expect(screen.getByLabelText('查詢服務人員')).toHaveValue('11'));
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(countPath(requests, AVAILABILITY_ENDPOINT)).toBe(0);
    expect(requests.filter((request) => ![SYSTEM_STATUS_ENDPOINT, STAFF_SUMMARY_ENDPOINT].includes(request.path))).toHaveLength(0);
    expectOnlyGet(requests);
  });

  it('tab 與 Drawer 只查合法分片，且不呈現 master／notes／certification／bank 假操作', async () => {
    authenticate();
    const requests = installFetchStub();

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('去敏人員甲')).toBeInTheDocument());
    const initialRequestCount = requests.length;

    fireEvent.click(screen.getByRole('button', { name: /配對偏好/ }));
    expect(document.querySelector('[data-control-id="staff.preferences.cooking-skills"]')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /長假與暫停/ }));
    expect(document.querySelector('[data-control-id="staff.availability.end-pause"]')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /服務月嫂名冊/ }));
    expect(document.querySelector('[data-control-id="staff.master.create"]')).not.toBeInTheDocument();
    expect(requests).toHaveLength(initialRequestCount);

    fireEvent.click(screen.getAllByRole('button', { name: /檢視服務人員摘要/ })[0]);
    await waitFor(() => expect(screen.getByText('Lifecycle')).toBeInTheDocument());
    expect(countPath(requests, STAFF_LIFECYCLE_ENDPOINT)).toBe(1);
    expect(countPath(requests, STAFF_QUALIFICATION_ENDPOINT)).toBe(1);

    const disabledControlIds = [
      'staff.master.create',
      'staff.master.save',
      'staff.master.edit',
      'staff.master.attachment-upload',
      'staff.master.certificate-approve',
      'staff.master.bank-edit',
    ];
    for (const controlId of disabledControlIds) {
      expect(document.querySelector(`[data-control-id="${controlId}"]`)).not.toBeInTheDocument();
    }
    expect(screen.queryByText(/已成功|儲存成功|上傳成功/)).not.toBeInTheDocument();
    expectOnlyGet(requests);
  });
});
