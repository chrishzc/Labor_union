/**
 * File: anomalies_entry_cutover.test.tsx
 * Description: 驗證 #anomalies 已認證查詢候選的 GET 預算、typed 資料與變更鎖定。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { MasterLayout } from '../components/MasterLayout';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';

const ANOMALY_LIST_ENDPOINT = '/api/v1/anomalies';
const WARNING_LIST_ENDPOINT = '/api/v1/import-warning-tracking/tasks';
const ISSUE_KEY = `ci_${'a'.repeat(64)}`;
const CURRENT_PAGE_RESPONSE = {
  success: true,
  message: '成功取得目前異常清單',
  data: {
    items: [{
      issue_key: ISSUE_KEY,
      definition_code: 'LINE-006',
      owner_domain: 'line',
      severity: 'warning',
      blocking: false,
      episode_started_at: '2026-08-30T01:00:00Z',
      last_verified_at: '2026-08-30T01:01:00Z',
    }],
    next_cursor: null,
  },
};
const CURRENT_DETAIL_RESPONSE = {
  success: true,
  message: '成功取得目前異常資訊',
  data: {
    issue_key: ISSUE_KEY,
    definition_code: 'LINE-006',
    owner_domain: 'line',
    owner_root_type: 'notification_failure',
    subject: { redaction_version: 'anomaly-safe.v1', definition_code: 'LINE-006', fields: [] },
    owner_snapshot_token: 'owner-v3',
    owner_version: 3,
    severity: 'warning',
    blocking: false,
    details_version: 1,
    details: { redaction_version: 'anomaly-safe.v1', definition_code: 'LINE-006', fields: [] },
    episode_started_at: '2026-08-30T01:00:00Z',
    last_verified_at: '2026-08-30T01:01:00Z',
    available_actions: [],
  },
};

const PERFORMANCE_RESPONSE = {
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

type FetchRecord = {
  path: string;
  method: string;
};

type FetchStubOptions = {
  anomalyResponse?: unknown;
  warningResponse?: unknown;
  anomalyStatus?: number;
  warningStatus?: number;
};

function getPath(input: string | URL | Request): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(raw, 'http://admin.test').pathname;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function typedUnavailableResponse(): unknown {
  return {
    detail: {
      error: {
        category: 'unavailable',
        code: 'ANOMALY_QUERY_UNAVAILABLE',
        message: '異常查詢暫時無法使用',
        field_errors: [],
        domain_blockers: [],
        retryable: true,
        correlation_id: 'anomaly-query-cutover-test',
        current_version: null,
      },
    },
  };
}

function installFetchStub(options: FetchStubOptions = {}): {
  requests: FetchRecord[];
} {
  const requests: FetchRecord[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(
    async (input: string | URL | Request, init?: RequestInit) => {
      const path = getPath(input);
      const method = String(init?.method ?? 'GET').toUpperCase();
      requests.push({ path, method });

      if (path === SYSTEM_STATUS_ENDPOINT) {
        return jsonResponse(PERFORMANCE_RESPONSE);
      }
      if (path === ANOMALY_LIST_ENDPOINT) {
        return jsonResponse(
          options.anomalyResponse ?? CURRENT_PAGE_RESPONSE,
          options.anomalyStatus ?? 200
        );
      }
      if (path.startsWith(`${ANOMALY_LIST_ENDPOINT}/`)) {
        return jsonResponse({
          success: true,
          message: '成功取得異常詳情',
          data: CURRENT_DETAIL_RESPONSE.data,
          error: null,
        });
      }
      if (path === WARNING_LIST_ENDPOINT) {
        return jsonResponse(
          options.warningResponse ?? { success: true, message: 'unused', data: [] },
          options.warningStatus ?? 200
        );
      }
      if (path.endsWith('/referral')) {
        return jsonResponse({
          success: true,
          message: '成功取得匯入警示導向',
          data: {},
          error: null,
        });
      }

      throw new Error(`Unexpected API path: ${path}`);
    }
  );

  return { requests };
}

function authenticate(): void {
  sessionClient.setSession('anomalies-cutover-test-token', {
    id: 7,
    username: 'anomalies-cutover-admin',
    display_name: '異常中心驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setAnomaliesHash(): void {
  window.history.replaceState(null, '', '#anomalies');
}

function expectOnlyGet(requests: readonly FetchRecord[]): void {
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((request) => request.method === 'GET')).toBe(true);
}

function expectInitialListBudget(requests: readonly FetchRecord[]): void {
  expect(requests.filter(({ path }) => path === ANOMALY_LIST_ENDPOINT)).toHaveLength(1);
  expect(requests.some(({ path }) => path === WARNING_LIST_ENDPOINT)).toBe(false);
}

describe('Anomalies #anomalies entry cutover query candidate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setAnomaliesHash();
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.history.replaceState(null, '', '#');
    vi.restoreAllMocks();
  });

  it('current audit navigation selects the anomalies route', () => {
    const onSelectPage = vi.fn();

    render(
      <MasterLayout
        currentSection="audit"
        currentPage="account-management"
        onSelectSection={vi.fn()}
        onSelectPage={onSelectPage}
        onLogout={vi.fn()}
      >
        <div>系統頁面</div>
      </MasterLayout>
    );

    fireEvent.click(screen.getByRole('button', { name: /異常審核/ }));

    expect(onSelectPage).toHaveBeenCalledTimes(1);
    expect(onSelectPage).toHaveBeenCalledWith('anomalies');
  });

  it('authenticated #anomalies renders only the current page contract', async () => {
    authenticate();
    const { requests } = installFetchStub();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('LINE-006')).toBeInTheDocument();
    });

    expect(window.location.hash).toBe('#anomalies');
    expect(screen.getByText('需要處理')).toBeInTheDocument();
    expect(screen.queryByText(/claimed|resolved|occurrence|timeline/i)).not.toBeInTheDocument();
    expectInitialListBudget(requests);
    expectOnlyGet(requests);
  });

  it('empty and unavailable typed responses stay explicit and never become fake success', async () => {
    authenticate();
    const { requests } = installFetchStub({
      anomalyResponse: typedUnavailableResponse(),
      anomalyStatus: 503,
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    expect(screen.queryByText('LINE-006')).not.toBeInTheDocument();
    expectInitialListBudget(requests);
    expectOnlyGet(requests);
  });

  it('keeps generic claim and resolve absent and reads current detail by issue key', async () => {
    authenticate();
    const { requests } = installFetchStub();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('LINE-006')).toBeInTheDocument();
    });
    expectInitialListBudget(requests);
    fireEvent.click(screen.getByRole('button', { name: /LINE-006/ }));
    await waitFor(() => {
      expect(screen.getByText(/系統不會用通用結案取代業務修正/)).toBeInTheDocument();
    });
    const detailRequests = requests.filter(({ path }) => path.startsWith(`${ANOMALY_LIST_ENDPOINT}/`));
    expect(detailRequests).toHaveLength(1);
    expect(detailRequests[0].path).toBe(`${ANOMALY_LIST_ENDPOINT}/${ISSUE_KEY}`);
    expectOnlyGet(requests);
  });
});
