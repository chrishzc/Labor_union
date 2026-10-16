/** Retired Anomalies page: no navigation, render branch or issue requests. */
import type { ReactNode } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { MasterLayout, NAV_ITEMS, PAGE_SECTION_MAP } from '../components/MasterLayout';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';

vi.mock('../pages/OrderWorkbenchV2Page', () => ({
  OrderWorkbenchV2Page: () => <h1>待辦看板內容</h1>,
}));
vi.mock('../components/StaffIdentityProvider', () => ({
  StaffIdentityProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const PERFORMANCE = {
  success: true, message: '查詢成功', error: null,
  data: { started_at: '2026-10-16T01:00:00Z', request_count: 1, average_response_time_ms: 12,
    p50_response_time_upper_bound_ms: 15, p95_response_time_upper_bound_ms: 20, maximum_response_time_ms: 20 },
};

beforeEach(() => {
  sessionClient.clearSession();
  window.history.replaceState(null, '', '#anomalies');
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const path = String(input).split('?')[0];
    if (path !== SYSTEM_STATUS_ENDPOINT) throw new Error(`Unexpected request: ${path}`);
    return new Response(JSON.stringify(PERFORMANCE), { status: 200, headers: { 'content-type': 'application/json' } });
  });
});
afterEach(() => {
  sessionClient.clearSession();
  window.history.replaceState(null, '', '#');
  vi.restoreAllMocks();
});

describe('Anomalies page retirement', () => {
  it('removes the audit entry and its dedicated notification shortcut', async () => {
    sessionClient.setSession('retired-nav-test-session', { id: 7, username: 'retired-nav-test',
      display_name: '測試管理員', role: 'system_admin', capabilities: ['system.administration'], is_root: true, access_control_version: 1 });
    render(<MasterLayout currentSection="audit" currentPage="account-management"
      onSelectSection={vi.fn()} onSelectPage={vi.fn()} onLogout={vi.fn()}>系統頁面</MasterLayout>);
    expect(NAV_ITEMS.some(item => String(item.id) === 'anomalies')).toBe(false);
    expect(Object.hasOwn(PAGE_SECTION_MAP, 'anomalies')).toBe(false);
    expect(screen.queryByRole('button', { name: /異常審核|查看待處理異常/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /帳號權限/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /儲存空間管理/ })).toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
  });

  it.each(['#anomalies', '#/anomalies'])('uses the existing default workbench for retired hash %s without querying anomalies', async (hash) => {
    window.history.replaceState(null, '', hash);
    sessionClient.setSession('retired-page-test-session', { id: 7, username: 'retired-page-test',
      display_name: '測試管理員', role: 'system_admin', capabilities: ['system.administration'], is_root: true, access_control_version: 1 });
    render(<App />);
    expect(await screen.findByRole('heading', { name: '待辦看板內容' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '異常審核' })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    const paths = vi.mocked(fetch).mock.calls.map(([input]) => String(input));
    expect(paths.every(path => path.split('?')[0] === SYSTEM_STATUS_ENDPOINT)).toBe(true);
  });
});
