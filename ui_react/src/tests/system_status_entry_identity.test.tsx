/**
 * File: system_status_entry_identity.test.tsx
 * Description: 驗證 System Status 專用 entry 的 authenticated typed snapshot 與 query 狀態。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
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
  sessionClient.setSession('system-status-identity-token', {
    id: 1,
    username: 'system-status-admin',
    display_name: '系統狀態管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

describe('SystemStatusPage identity amendment', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    authenticate();
  });

  afterEach(() => {
    sessionClient.clearSession();
    vi.restoreAllMocks();
  });

  it('exposes the dedicated identity and does not claim a status before the server snapshot arrives', async () => {
    let resolveFetch!: (response: Response) => void;
    const fetchPromise = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockReturnValue(fetchPromise);

    render(<SystemStatusPage />);

    expect(screen.getByTestId('system-status.page')).toHaveAttribute(
      'data-entry-identity',
      'ui-react:#system-status'
    );
    expect(screen.getByRole('status')).toHaveTextContent('正在讀取系統效能快照');
    expect(screen.queryByText(/系統在線|服務正常/)).not.toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith(
      SYSTEM_STATUS_ENDPOINT,
      expect.objectContaining({
        method: 'GET',
        headers: expect.objectContaining({
          Authorization: 'Bearer system-status-identity-token',
        }),
      })
    );

    resolveFetch(jsonResponse(snapshotEnvelope()));
    await waitFor(() => expect(screen.getByTestId('system-status.query.success')).toBeInTheDocument());
  });

  it('renders every displayed value from the typed server snapshot, including null metrics', async () => {
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
    expect(screen.getByTestId('system-status.metric.started-at')).toHaveTextContent('2026-08-20T01:02:03Z');
    expect(screen.getByTestId('system-status.metric.request-count')).toHaveTextContent('0');
    expect(screen.getByTestId('system-status.metric.average-response-time')).toHaveTextContent('未提供');
    expect(screen.getByTestId('system-status.metric.p95-response-time')).toHaveTextContent('未提供');
    expect(screen.queryByText(/系統在線|服務正常/)).not.toBeInTheDocument();
  });

  it('shows the typed transport error and retries through the same GET client path', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('connection refused'))
      .mockResolvedValueOnce(jsonResponse(snapshotEnvelope({ request_count: 3 })));

    render(<SystemStatusPage />);

    await waitFor(() => expect(screen.getByTestId('system-status.query.error')).toBeInTheDocument());
    expect(screen.getByRole('alert')).toHaveTextContent('connection refused');
    fireEvent.click(screen.getByRole('button', { name: '重新載入快照' }));

    await waitFor(() => expect(screen.getByTestId('system-status.query.success')).toBeInTheDocument());
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('system-status.metric.request-count')).toHaveTextContent('3');
  });
});
