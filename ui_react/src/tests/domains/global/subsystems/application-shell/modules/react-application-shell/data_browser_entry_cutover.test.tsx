/**
 * File: data_browser_entry_cutover.test.tsx
 * Description: 驗證舊 Data Browser 深連結導向現行客戶名冊，不再載入六來源頁面或舊寫入控制。
 */
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../../../../../../App';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import type { ClientRegistryPage } from '../../../../../../../api/client_registry/client_registry_schemas';
import { SYSTEM_STATUS_ENDPOINT } from '../../../../../../../api/system/system_status_client';

const CLIENT_REGISTRY_ENDPOINT = '/api/v1/admin/registries/clients';
const DATA_BROWSER_PREFIX = '/api/v1/admin/data-browser';
const REGISTRY_PAGE: ClientRegistryPage = {
  items: [{
    client_id: 1,
    case_no: 'CASE-001',
    name: '測試客戶',
    phone: null,
    city: null,
    baby_info: null,
    service_days: 26,
    requires_cooking: false,
    planned_start_date: null,
    order_status: '待處理',
  }],
  next_cursor: null,
};

interface RecordedRequest {
  path: string;
  method: string;
  query: URLSearchParams;
}

type RegistryMode = 'rows' | 'empty' | 'unavailable';

function envelope(data: object): Response {
  return new Response(JSON.stringify({
    success: true,
    message: '成功取得查詢結果',
    data,
    error: null,
  }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function authenticate(): void {
  sessionClient.setSession('data-browser-entry-token', {
    id: 1,
    username: 'data-browser-admin',
    display_name: '資料瀏覽驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 2,
  });
}

function installFetchStub(mode: RegistryMode = 'rows'): RecordedRequest[] {
  const requests: RecordedRequest[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost');
    const method = init?.method ?? 'GET';
    requests.push({ path: url.pathname, method, query: url.searchParams });

    if (url.pathname === SYSTEM_STATUS_ENDPOINT) {
      return envelope({
        started_at: '2026-08-20T01:02:03Z',
        request_count: 1,
        average_response_time_ms: 1,
        p50_response_time_upper_bound_ms: 1,
        p95_response_time_upper_bound_ms: 1,
        maximum_response_time_ms: 1,
      });
    }

    if (url.pathname === CLIENT_REGISTRY_ENDPOINT) {
      if (mode === 'empty') {
        return envelope({ items: [], next_cursor: null });
      }
      if (mode === 'unavailable') {
        return new Response(JSON.stringify({ detail: 'Client registry unavailable' }), {
          status: 503,
          headers: { 'content-type': 'application/json' },
        });
      }
      if (url.searchParams.get('query') === 'CASE-002') {
        return envelope({
          items: [{ ...REGISTRY_PAGE.items[0], case_no: 'CASE-002', name: '篩選測試客戶' }],
          next_cursor: null,
        });
      }
      return envelope(REGISTRY_PAGE);
    }

    throw new Error(`unexpected ${method} ${url.pathname}`);
  });
  return requests;
}

describe('Retired Data Browser entry redirects to the client registry', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#data-browser'));
  });

  afterEach(() => {
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#'));
    vi.restoreAllMocks();
  });

  it.each(['#data-browser', '#databrowser'])('%s 在 StrictMode 導向名冊而非六來源頁面', async (hash) => {
    act(() => window.history.replaceState(null, '', hash));
    authenticate();
    const requests = installFetchStub();
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('CASE-001')).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: '客戶名冊', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '客戶清單' })).toHaveAttribute('aria-selected', 'true');
    expect(requests.some((request) => request.path === CLIENT_REGISTRY_ENDPOINT)).toBe(true);
    expect(requests.some((request) => request.path.startsWith(DATA_BROWSER_PREFIX))).toBe(false);
    expect(document.querySelector('[data-control-id^="data-browser."]')).toBeNull();
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('名冊搜尋使用正式 Query，依 server 回應顯示結果而不呼叫舊入口或 mutation', async () => {
    authenticate();
    const requests = installFetchStub();
    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('CASE-001')).toBeInTheDocument());

    fireEvent.change(screen.getByRole('textbox', { name: '搜尋客戶名冊清單' }), {
      target: { value: ' CASE-002 ' },
    });
    fireEvent.click(screen.getByRole('button', { name: '套用篩選' }));

    await waitFor(() => expect(screen.getByText('CASE-002')).toBeInTheDocument());
    expect(screen.getByText('篩選測試客戶')).toBeInTheDocument();
    expect(screen.queryByText('CASE-001')).not.toBeInTheDocument();
    expect(requests.some((request) => request.path === CLIENT_REGISTRY_ENDPOINT
      && request.query.get('query') === 'CASE-002')).toBe(true);
    expect(requests.some((request) => request.path.startsWith(DATA_BROWSER_PREFIX))).toBe(false);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
    expect(document.querySelector('[data-control-id^="data-browser."]')).toBeNull();
  });

  it('空名冊只顯示空狀態，不製造資料列或恢復舊頁面', async () => {
    authenticate();
    const requests = installFetchStub('empty');
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('目前沒有可顯示的案件。')).toBeInTheDocument());
    expect(screen.queryByText('CASE-001')).not.toBeInTheDocument();
    expect(requests.some((request) => request.path.startsWith(DATA_BROWSER_PREFIX))).toBe(false);
  });

  it('名冊 Query 失敗顯示錯誤，不冒充空名冊或成功載入', async () => {
    authenticate();
    const requests = installFetchStub('unavailable');
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    expect(screen.getByRole('alert')).not.toBeEmptyDOMElement();
    expect(screen.queryByText('目前沒有可顯示的案件。')).not.toBeInTheDocument();
    expect(screen.queryByText('CASE-001')).not.toBeInTheDocument();
    expect(requests.some((request) => request.path.startsWith(DATA_BROWSER_PREFIX))).toBe(false);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });
});
