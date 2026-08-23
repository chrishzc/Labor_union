/**
 * File: system_status_entry_cutover.test.tsx
 * Description: 驗證系統狀態 entry 的 Hash、認證、單一 GET、typed 快照、失敗與重試。
 */
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { MasterLayout } from '../components/MasterLayout';
import {
  fetchPerformanceSnapshot,
  SYSTEM_STATUS_ENDPOINT,
} from '../api/system/system_status_client';
import { sessionClient } from '../api/auth/session_client';
import { SystemStatusPage } from '../pages/SystemStatusPage';

const snapshotEnvelope = (overrides: Record<string, unknown> = {}) => ({
  success: true,
  message: 'Success',
  data: {
    started_at: '2026-08-20T01:02:03Z',
    request_count: 17,
    average_response_time_ms: 24.5,
    p50_response_time_upper_bound_ms: 20,
    p95_response_time_upper_bound_ms: 50,
    maximum_response_time_ms: 180,
    ...overrides,
  },
  error: null,
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function authenticate(): void {
  sessionClient.setSession('system-status-candidate-token', {
    id: 1,
    username: 'system-status-admin',
    display_name: '系統狀態驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

describe('System Status entry cutover candidate contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    act(() => {
      window.history.replaceState(null, '', '#');
    });
  });

  afterEach(() => {
    sessionClient.clearSession();
    act(() => {
      window.history.replaceState(null, '', '#');
    });
    vi.restoreAllMocks();
  });

  it('未認證時阻擋 #system-status 並不發起工作區查詢', () => {
    act(() => {
      window.history.replaceState(null, '', '#system-status');
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    render(
      <StrictMode>
        <App />
      </StrictMode>
    );

    expect(screen.getByRole('heading', { name: '月子工會管理系統' })).toBeInTheDocument();
    expect(screen.queryByTestId('system-status.page')).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('認證後 Hash 才呈現專用 entry', async () => {
    act(() => {
      window.history.replaceState(null, '', '#system-status');
    });
    authenticate();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(snapshotEnvelope())
    );
    render(
      <StrictMode>
        <App />
      </StrictMode>
    );

    await waitFor(() => expect(screen.getByTestId('system-status.page')).toBeInTheDocument());
    expect(screen.getByTestId('system-status.page')).toHaveAttribute(
      'data-entry-identity',
      'ui-react:#system-status'
    );
    expect(window.location.hash).toBe('#system-status');
    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy).toHaveBeenCalledWith(
      SYSTEM_STATUS_ENDPOINT,
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('未登入 direct query 在 fetch 前以 typed error fail closed 且零網路請求', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    await expect(fetchPerformanceSnapshot()).rejects.toMatchObject({
      name: 'ApiHttpError',
      status: 401,
      code: 'SYSTEM_STATUS_UNAUTHENTICATED',
    });
    expect(fetchSpy).not.toHaveBeenCalled();

    render(<SystemStatusPage />);
    await waitFor(() => expect(screen.getByTestId('system-status.query.error')).toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('請先完成管理員登入後再查詢系統狀態。');
  });

  it('初次載入只發出一次 GET，且不因頁面載入產生其他 HTTP method', async () => {
    authenticate();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(snapshotEnvelope())
    );

    render(<SystemStatusPage />);

    await waitFor(() => expect(screen.getByTestId('system-status.query.success')).toBeInTheDocument());
    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy).toHaveBeenCalledWith(
      SYSTEM_STATUS_ENDPOINT,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer system-status-candidate-token',
        }),
      })
    );
    expect(fetchSpy.mock.calls.every(([, options]) => options?.method === 'GET')).toBe(true);
  });

  it('caller 不能以大小寫變形 Authorization 覆蓋目前 session token', async () => {
    authenticate();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(snapshotEnvelope())
    );

    await fetchPerformanceSnapshot({
      headers: {
        authorization: 'Bearer caller-controlled-token',
        'X-Candidate-Probe': 'preserved',
      },
      timeoutMs: 4321,
    });

    expect(fetchSpy).toHaveBeenCalledWith(
      SYSTEM_STATUS_ENDPOINT,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer system-status-candidate-token',
          'X-Candidate-Probe': 'preserved',
        }),
      })
    );
    const requestHeaders = fetchSpy.mock.calls[0]?.[1]?.headers as Record<string, string>;
    expect(requestHeaders).not.toHaveProperty('authorization');
  });

  it('custom options 不與預設 in-flight query 錯誤共用 request', async () => {
    authenticate();
    let resolveDefault!: (response: Response) => void;
    const defaultResponse = new Promise<Response>((resolve) => {
      resolveDefault = resolve;
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockReturnValueOnce(defaultResponse)
      .mockResolvedValueOnce(jsonResponse(snapshotEnvelope({ request_count: 9 })));

    const defaultQuery = fetchPerformanceSnapshot();
    const customQuery = fetchPerformanceSnapshot({ timeoutMs: 4321 });

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    resolveDefault(jsonResponse(snapshotEnvelope({ request_count: 8 })));

    await expect(defaultQuery).resolves.toMatchObject({ request_count: 8 });
    await expect(customQuery).resolves.toMatchObject({ request_count: 9 });
  });

  it('non-System page 的 Shell status query 在 StrictMode 下也只送一次 GET', async () => {
    authenticate();
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(snapshotEnvelope())
    );

    render(
      <StrictMode>
        <MasterLayout
          currentSection="operations"
          currentPage="order-tracker"
          onSelectSection={() => undefined}
          onSelectPage={() => undefined}
          onLogout={() => undefined}
        />
      </StrictMode>
    );

    await waitFor(() => expect(screen.getByTestId('system-status-indicator')).toHaveTextContent('系統在線'));
    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy).toHaveBeenCalledWith(
      SYSTEM_STATUS_ENDPOINT,
      expect.objectContaining({ method: 'GET' })
    );
  });

  it('成功畫面只呈現 typed server snapshot，不以本地狀態或 fallback 冒充成功', async () => {
    authenticate();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse(snapshotEnvelope({
        request_count: 0,
        average_response_time_ms: null,
        p50_response_time_upper_bound_ms: null,
        p95_response_time_upper_bound_ms: null,
        maximum_response_time_ms: null,
      }))
    );

    render(<SystemStatusPage />);

    await waitFor(() => expect(screen.getByTestId('system-status.query.success')).toBeInTheDocument());
    expect(screen.getByTestId('system-status.metric.started-at')).toHaveTextContent(
      '2026-08-20T01:02:03Z'
    );
    expect(screen.getByTestId('system-status.metric.request-count')).toHaveTextContent('0');
    expect(screen.getByTestId('system-status.metric.average-response-time')).toHaveTextContent('未提供');
    expect(screen.getByTestId('system-status.metric.p95-response-time')).toHaveTextContent('未提供');
    expect(screen.queryByText(/系統在線|服務正常/)).not.toBeInTheDocument();
  });

  it('錯誤時不顯示 optimistic success，明確重試後才接受第二次 server snapshot', async () => {
    authenticate();
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('system status unavailable'))
      .mockResolvedValueOnce(jsonResponse(snapshotEnvelope({ request_count: 3 })));

    render(<SystemStatusPage />);

    await waitFor(() => expect(screen.getByTestId('system-status.query.error')).toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('system status unavailable');
    expect(screen.queryByTestId('system-status.query.success')).not.toBeInTheDocument();
    expect(screen.queryByText(/系統在線|服務正常/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '重試查詢' }));

    await waitFor(() => expect(screen.getByTestId('system-status.query.success')).toBeInTheDocument());
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('system-status.metric.request-count')).toHaveTextContent('3');
  });
});
