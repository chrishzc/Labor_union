/**
 * File: account_management_entry_cutover.test.tsx
 * Description: 驗證 Account entry 的 StrictMode GET 預算、lazy query、typed state 與原生 disabled 邊界。
 */
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { accountDirectoryClient } from '../api/access/account_directory_client';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import {
  ACCOUNT_DIRECTORY_FIXTURE,
  AUDIT_PAGE_FIXTURE,
} from './fixtures/access/account_query_contract_fixtures';
import { AUDIT_DETAIL_FIXTURE } from './fixtures/access/audit_query_contract_fixtures';

const ACCOUNTS_ENDPOINT = '/api/v1/admin/accounts';
const AUDIT_ENDPOINT = '/api/v1/admin/audits';
const AUDIT_DETAIL_ENDPOINT = '/api/v1/admin/audits/10';

interface RecordedRequest {
  path: string;
  method: string;
}

function response(data: unknown): Response {
  return new Response(JSON.stringify({ success: true, message: 'ok', data, error: null }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function authenticate(): void {
  sessionClient.setSession('account-entry-token', {
    id: 1,
    username: 'root-user',
    display_name: '根帳號',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 2,
  });
}

function installFetchStub(): RecordedRequest[] {
  const requests: RecordedRequest[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://localhost');
    const method = init?.method ?? 'GET';
    requests.push({ path: url.pathname, method });
    if (url.pathname === ACCOUNTS_ENDPOINT) return response(ACCOUNT_DIRECTORY_FIXTURE);
    if (url.pathname === AUDIT_ENDPOINT) return response(AUDIT_PAGE_FIXTURE);
    if (url.pathname === AUDIT_DETAIL_ENDPOINT) return response(AUDIT_DETAIL_FIXTURE);
    if (url.pathname === SYSTEM_STATUS_ENDPOINT) {
      return response({
        started_at: '2026-08-20T01:02:03Z',
        request_count: 1,
        average_response_time_ms: 1,
        p50_response_time_upper_bound_ms: 1,
        p95_response_time_upper_bound_ms: 1,
        maximum_response_time_ms: 1,
      });
    }
    throw new Error(`unexpected GET ${url.pathname}`);
  });
  return requests;
}

function count(requests: RecordedRequest[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

describe('Account Management Phase5 entry candidate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#account-management'));
  });

  afterEach(() => {
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#'));
    vi.restoreAllMocks();
  });

  it('actual StrictMode keeps account/audit GET budgets and exposes only account-owned tabs', async () => {
    authenticate();
    const requests = installFetchStub();
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(document.querySelector('.account-card-name')).toHaveTextContent('根帳號'));
    expect(window.location.hash).toBe('#account-management');
    expect(count(requests, ACCOUNTS_ENDPOINT)).toBe(1);
    expect(count(requests, AUDIT_ENDPOINT)).toBe(0);
    expect(requests.some((request) => request.path.startsWith('/api/v1/jobs/'))).toBe(false);

    for (const name of [
      /建立工作人員帳號/,
      /重設 MFA/,
      /強制登出/,
      /停權/,
    ]) {
      expect(screen.getAllByRole('button', { name })[0]).toBeDisabled();
    }

    fireEvent.click(screen.getByRole('tab', { name: /安全操作與登入稽核/ }));
    await waitFor(() => expect(screen.getByText('登入驗證')).toBeInTheDocument());
    expect(count(requests, AUDIT_ENDPOINT)).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: '查看' }));
    await waitFor(() => expect(screen.getByText('provided')).toBeInTheDocument());
    expect(count(requests, AUDIT_DETAIL_ENDPOINT)).toBe(1);

    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.queryByRole('tab', { name: /背景工作狀態/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('背景工作查詢碼')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="account.jobs.lookup"]')).toBeNull();
    expect(document.querySelector('[data-control-id="account.jobs.refresh"]')).toBeNull();
    expect(screen.getByText('管理工作人員帳號、登入驗證與安全稽核。')).toBeInTheDocument();
    expect(requests.some((request) => request.path.startsWith('/api/v1/jobs/'))).toBe(false);

    expect(requests.every((request) => request.method === 'GET')).toBe(true);
    expect(screen.queryByText(/建立成功|停權成功|重試成功|取消成功/)).not.toBeInTheDocument();
  });

  it('typed unavailable remains an error state and never becomes a fake account', async () => {
    authenticate();
    installFetchStub();
    vi.spyOn(accountDirectoryClient, 'query').mockRejectedValue(new Error('帳號中心暫時無法使用'));
    render(<App />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('帳號清冊暫時無法取得'));
    expect(document.querySelector('.account-card-name')).toBeNull();
    expect(screen.queryByText(/已成功載入帳號/)).not.toBeInTheDocument();
  });
});
