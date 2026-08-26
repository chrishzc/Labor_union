/**
 * File: data_browser_entry_cutover.test.tsx
 * Description: 驗證 Data Browser entry 的 StrictMode GET 預算、去敏空狀態與唯讀控制邊界。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import { VALID_DATA_BROWSER_PAGE } from './fixtures/data_browser/data_browser_query_contract_fixtures';

const DATA_BROWSER_PREFIX = '/api/v1/admin/data-browser/sources/';
const ORDERS_ENDPOINT = `${DATA_BROWSER_PREFIX}orders`;
const CLIENTS_ENDPOINT = `${DATA_BROWSER_PREFIX}clients`;

interface RecordedRequest {
  path: string;
  method: string;
  query: URLSearchParams;
}

type DataBrowserMode = 'pages' | 'empty' | 'unavailable';

function envelope(data: object): Response {
  return new Response(JSON.stringify({
    success: true,
    message: '成功取得去敏資料來源',
    data,
    error: null,
  }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function pageFor(sourceId: 'orders' | 'clients', query: URLSearchParams): object {
  const after = query.get('after');
  const isNextPage = after !== null;
  const rowIdentity = sourceId === 'orders'
    ? (isNextPage ? '115000002' : '115000001')
    : (isNextPage ? 'client-0002' : 'client-0001');
  const title = sourceId === 'orders'
    ? `訂單 ${rowIdentity}`
    : `客戶 ${rowIdentity}`;
  const baseItem = VALID_DATA_BROWSER_PAGE.items[0];
  return {
    source_id: sourceId,
    items: [{
      ...baseItem,
      source_id: sourceId,
      row_identity: rowIdentity,
      display_title: title,
      detail_cells: baseItem.detail_cells.map((cell) => ({
        ...cell,
        field_id: sourceId === 'orders' ? cell.field_id : `client_${cell.field_id}`,
      })),
      summary_cells: baseItem.summary_cells.map((cell) => ({
        ...cell,
        field_id: sourceId === 'orders' ? cell.field_id : `client_${cell.field_id}`,
      })),
    }],
    next_cursor: isNextPage ? null : `cursor-${sourceId}-1`,
  };
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

function installFetchStub(mode: DataBrowserMode = 'pages'): RecordedRequest[] {
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

    if (url.pathname.startsWith(DATA_BROWSER_PREFIX)) {
      if (mode === 'empty') {
        return envelope({ source_id: 'orders', items: [], next_cursor: null });
      }
      if (mode === 'unavailable') {
        return new Response(JSON.stringify({ detail: 'Data Browser unavailable' }), {
          status: 503,
          headers: { 'content-type': 'application/json' },
        });
      }
      const sourceId = url.pathname.endsWith('/clients') ? 'clients' : 'orders';
      return envelope(pageFor(sourceId, url.searchParams));
    }

    throw new Error(`unexpected GET ${url.pathname}`);
  });
  return requests;
}

function count(requests: RecordedRequest[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

describe('Data Browser Phase5 entry candidate', () => {
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

  it('actual StrictMode 初始 Data Browser query 必須只有一個 GET', async () => {
    authenticate();
    const requests = installFetchStub();
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    expect(window.location.hash).toBe('#data-browser');
    expect(screen.getByTitle('資料中心')).toHaveClass('active');
    expect(count(requests, ORDERS_ENDPOINT)).toBe(1);
    expect(count(requests, SYSTEM_STATUS_ENDPOINT)).toBe(1);
  });

  it('source/search/next 各只增加一個 GET，Drawer/copy 不增加請求且不暴露假更正操作', async () => {
    authenticate();
    const requests = installFetchStub();
    vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined);
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('訂單 115000001')).toBeInTheDocument());
    const initialOrders = count(requests, ORDERS_ENDPOINT);
    const initialClients = count(requests, CLIENTS_ENDPOINT);

    fireEvent.click(screen.getByRole('button', { name: /客戶歷史檔案/ }));
    await waitFor(() => expect(screen.getByText('客戶 client-0001')).toBeInTheDocument());
    expect(count(requests, ORDERS_ENDPOINT)).toBe(initialOrders);
    expect(count(requests, CLIENTS_ENDPOINT)).toBe(initialClients + 1);

    fireEvent.change(screen.getByPlaceholderText(/搜尋案件編號/), { target: { value: '台北市' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢' }));
    await waitFor(() => expect(count(requests, CLIENTS_ENDPOINT)).toBe(initialClients + 2));
    expect(requests.at(-1)?.query.get('query')).toBe('台北市');

    fireEvent.click(screen.getByRole('button', { name: '載入下一頁' }));
    await waitFor(() => expect(count(requests, CLIENTS_ENDPOINT)).toBe(initialClients + 3));
    expect(requests.at(-1)?.query.get('after')).toBe('cursor-clients-1');

    fireEvent.click(screen.getAllByRole('button', { name: /檢視去敏詳情/ })[0]);
    const beforeDrawerActions = requests.length;
    expect(screen.getByText(/去敏資料詳情/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '複製去敏資料' }));
    await waitFor(() => expect(screen.getByText('已複製去敏資料')).toBeInTheDocument());
    expect(requests.length).toBe(beforeDrawerActions);

    expect(screen.getByText(/此頁只提供去敏資料查詢/)).toBeInTheDocument();
    for (const controlId of [
      'data-browser.patch',
      'data-browser.source-correction.preview',
      'data-browser.source-correction.apply',
    ]) {
      const control = document.querySelector(`[data-control-id="${controlId}"]`);
      expect(control).not.toBeInTheDocument();
    }
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
    expect(screen.queryByText(/RAW JSON|更正成功|套用成功/)).not.toBeInTheDocument();
  });

  it('typed empty 與 unavailable 只呈現真實狀態，不製造資料列或成功提示', async () => {
    authenticate();
    installFetchStub('empty');
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('此來源目前沒有符合條件的去敏資料。')).toBeInTheDocument());
    expect(screen.queryByText(/訂單 115000001|已成功載入/)).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id^="data-browser.row."]')).toBeNull();

    cleanupEntry();
    authenticate();
    installFetchStub('unavailable');
    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText(/載入失敗/)).toBeInTheDocument());
    expect(screen.queryByText('此來源目前沒有符合條件的去敏資料。')).not.toBeInTheDocument();
    expect(screen.queryByText(/訂單 115000001|已成功載入/)).not.toBeInTheDocument();
  });
});

function cleanupEntry(): void {
  cleanup();
  act(() => window.history.replaceState(null, '', '#data-browser'));
  vi.restoreAllMocks();
}
