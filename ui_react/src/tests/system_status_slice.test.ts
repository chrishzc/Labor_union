/**
 * @file system_status_slice.test.ts
 * @description 驗證系統效能遙測狀態垂直切片，包含後端合約測試與 MasterLayout 指示器狀態對應。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import {
  fetchPerformanceSnapshot,
  SYSTEM_STATUS_ENDPOINT,
} from '../api/system/system_status_client';
import { MasterLayout } from '../components/MasterLayout';
import { sessionClient } from '../api/auth/session_client';

function authenticate(): void {
  sessionClient.setSession('system-status-slice-token', {
    id: 1,
    username: 'system-status-admin',
    display_name: '系統狀態管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

describe('System Status Vertical Slice & MasterLayout Indicator', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    authenticate();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    sessionClient.clearSession();
  });

  it('fetchPerformanceSnapshot 應符合後端 PerformanceSnapshot 合約規範', async () => {
    const rawBackendEnvelope = {
      success: true,
      message: 'Success',
      data: {
        started_at: '2026-08-09T00:00:00Z',
        request_count: 15,
        average_response_time_ms: 24.5,
        p50_response_time_upper_bound_ms: 20,
        p95_response_time_upper_bound_ms: 50,
        maximum_response_time_ms: 180.0,
      },
      error: null,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => rawBackendEnvelope,
    });

    const snapshot = await fetchPerformanceSnapshot();

    expect(globalThis.fetch).toHaveBeenCalledWith(
      SYSTEM_STATUS_ENDPOINT,
      expect.objectContaining({ method: 'GET' })
    );

    expect(snapshot.started_at).toBe('2026-08-09T00:00:00Z');
    expect(snapshot.request_count).toBe(15);
    expect(snapshot.average_response_time_ms).toBe(24.5);
    expect(snapshot.p95_response_time_upper_bound_ms).toBe(50);
  });

  it('在正常低延遲狀態下，MasterLayout 應顯示綠色狀態指示與延遲數值', async () => {
    const rawBackendEnvelope = {
      success: true,
      message: 'Success',
      data: {
        started_at: '2026-08-09T00:00:00Z',
        request_count: 50,
        average_response_time_ms: 18.0,
        p50_response_time_upper_bound_ms: 20,
        p95_response_time_upper_bound_ms: 45,
        maximum_response_time_ms: 120.0,
      },
      error: null,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => rawBackendEnvelope,
    });

    render(
      React.createElement(
        MasterLayout,
        {
          currentSection: 'operations',
          currentPage: 'order-tracker',
          onSelectSection: () => {},
          onSelectPage: () => {},
          onLogout: () => {},
        },
        React.createElement('div', null, 'Workspace Content')
      )
    );

    await waitFor(() => {
      const indicator = screen.getByTestId('system-status-indicator');
      expect(indicator).toBeInTheDocument();
      expect(indicator).toHaveTextContent(/系統在線.*18ms/);
    });
  });

  it('在冷啟動且尚無請求流量時 (request_count: 0)，應安全呈現系統在線而不崩潰', async () => {
    const coldStartEnvelope = {
      success: true,
      message: 'Success',
      data: {
        started_at: '2026-08-09T00:00:00Z',
        request_count: 0,
        average_response_time_ms: null,
        p50_response_time_upper_bound_ms: null,
        p95_response_time_upper_bound_ms: null,
        maximum_response_time_ms: null,
      },
      error: null,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => coldStartEnvelope,
    });

    render(
      React.createElement(
        MasterLayout,
        {
          currentSection: 'operations',
          currentPage: 'order-tracker',
          onSelectSection: () => {},
          onSelectPage: () => {},
          onLogout: () => {},
        },
        React.createElement('div', null, 'Cold Start Content')
      )
    );

    await waitFor(() => {
      const indicator = screen.getByTestId('system-status-indicator');
      expect(indicator).toBeInTheDocument();
      expect(indicator).toHaveTextContent(/系統在線/);
    });
  });

  it('在系統高延遲時 (p95 >= 2000ms)，應切換為 degraded 警示標記', async () => {
    const highLatencyEnvelope = {
      success: true,
      message: 'Success',
      data: {
        started_at: '2026-08-09T00:00:00Z',
        request_count: 100,
        average_response_time_ms: 1200.0,
        p50_response_time_upper_bound_ms: 500,
        p95_response_time_upper_bound_ms: 2500,
        maximum_response_time_ms: 4000.0,
      },
      error: null,
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: async () => highLatencyEnvelope,
    });

    render(
      React.createElement(
        MasterLayout,
        {
          currentSection: 'operations',
          currentPage: 'order-tracker',
          onSelectSection: () => {},
          onSelectPage: () => {},
          onLogout: () => {},
        },
        React.createElement('div', null, 'Degraded Content')
      )
    );

    await waitFor(() => {
      const indicator = screen.getByTestId('system-status-indicator');
      expect(indicator).toHaveTextContent(/延遲偏高/);
    });
  });

  it('當後端網路異常或斷線時，應降級呈現系統離線而不導致頁面崩潰', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    render(
      React.createElement(
        MasterLayout,
        {
          currentSection: 'operations',
          currentPage: 'order-tracker',
          onSelectSection: () => {},
          onSelectPage: () => {},
          onLogout: () => {},
        },
        React.createElement('div', null, 'Offline Content')
      )
    );

    await waitFor(() => {
      const indicator = screen.getByTestId('system-status-indicator');
      expect(indicator).toBeInTheDocument();
      expect(indicator).toHaveTextContent('系統離線');
    });
  });
});
