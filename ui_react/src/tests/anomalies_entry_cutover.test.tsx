/**
 * File: anomalies_entry_cutover.test.tsx
 * Description: 驗證 #anomalies 已認證查詢候選的 GET 預算、typed 資料與變更鎖定。
 */
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import {
  VALID_ANOMALIES_QUERY_RESPONSE,
  VALID_EMPTY_IMPORT_WARNING_TASKS_RESPONSE,
  VALID_IMPORT_WARNING_REFERRAL_VIEW,
  VALID_IMPORT_WARNING_TASKS_RESPONSE,
} from './fixtures/anomalies/anomaly_query_contract_fixtures';
import { VALID_ANOMALY_DETAIL_VIEW } from './fixtures/anomalies/anomaly_detail_contract_fixtures';

const ANOMALY_LIST_ENDPOINT = '/api/v1/anomalies';
const WARNING_LIST_ENDPOINT = '/api/v1/import-warning-tracking/tasks';

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
          options.anomalyResponse ?? VALID_ANOMALIES_QUERY_RESPONSE,
          options.anomalyStatus ?? 200
        );
      }
      if (path.startsWith(`${ANOMALY_LIST_ENDPOINT}/`)) {
        return jsonResponse({
          success: true,
          message: '成功取得異常詳情',
          data: VALID_ANOMALY_DETAIL_VIEW,
          error: null,
        });
      }
      if (path === WARNING_LIST_ENDPOINT) {
        return jsonResponse(
          options.warningResponse ?? VALID_IMPORT_WARNING_TASKS_RESPONSE,
          options.warningStatus ?? 200
        );
      }
      if (path.endsWith('/referral')) {
        return jsonResponse({
          success: true,
          message: '成功取得匯入警示導向',
          data: VALID_IMPORT_WARNING_REFERRAL_VIEW,
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
  const listRequests = requests.filter(({ path }) =>
    path === ANOMALY_LIST_ENDPOINT || path === WARNING_LIST_ENDPOINT
  );
  expect(listRequests).toHaveLength(2);
  expect(listRequests.map(({ path }) => path).sort()).toEqual(
    [ANOMALY_LIST_ENDPOINT, WARNING_LIST_ENDPOINT].sort()
  );
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

  it('authenticated #anomalies renders typed server data with exactly two initial list GETs', async () => {
    authenticate();
    const { requests } = installFetchStub();

    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
      expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument();
    });

    expect(window.location.hash).toBe('#anomalies');
    expect(screen.getByText('🔴 嚴重阻擋')).toBeInTheDocument();
    expect(screen.getAllByText('異常偵測項目').length).toBeGreaterThan(0);
    expect(screen.queryByText(/目前 typed view 未納入/)).not.toBeInTheDocument();
    expect(screen.queryByText('已成功載入異常')).not.toBeInTheDocument();
    expectInitialListBudget(requests);
    expectOnlyGet(requests);
  });

  it('empty and unavailable typed responses stay explicit and never become fake success', async () => {
    authenticate();
    const { requests } = installFetchStub({
      anomalyResponse: typedUnavailableResponse(),
      warningResponse: VALID_EMPTY_IMPORT_WARNING_TASKS_RESPONSE,
      anomalyStatus: 503,
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/載入異常資料失敗：異常查詢暫時無法使用/)).toBeInTheDocument();
      expect(screen.getByText('目前無待追蹤之匯入警示任務。')).toBeInTheDocument();
    });

    expect(screen.queryByText('SCHEDULE-001')).not.toBeInTheDocument();
    expect(screen.queryByText('已成功載入異常')).not.toBeInTheDocument();
    expectInitialListBudget(requests);
    expectOnlyGet(requests);
  });

  it('keeps generic claim and resolve disabled; lazy detail/referral remain GET-only', async () => {
    authenticate();
    const { requests } = installFetchStub();

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('SCHEDULE-001')).toBeInTheDocument();
      expect(screen.getByText('HCM-FIELD-001')).toBeInTheDocument();
    });
    expectInitialListBudget(requests);
    expect(requests.some(({ path }) => path.endsWith('/referral'))).toBe(false);
    expect(requests.some(({ path }) => path.startsWith(`${ANOMALY_LIST_ENDPOINT}/`))).toBe(false);

    const claimButton = screen.getAllByRole('button', { name: /🔵 認領此案/ })[0];
    expect(claimButton).toBeDisabled();
    fireEvent.click(claimButton);
    expect(screen.queryByText('認領成功')).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getAllByRole('button', { name: /排查處置抽屜 ➔/ })[0]);
    });
    await waitFor(() => {
      expect(screen.getByText(/後端異常詳情/)).toBeInTheDocument();
      expect(screen.getByText(/claim ·/)).toBeInTheDocument();
      expect(screen.getByText(/v2 → v3/)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /確認排除異常/ })).toBeDisabled();
    expect(document.querySelector('[data-surface-id="anomalies.finance-correction"]')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /確認排除異常/ }));
    expect(screen.queryByText('排除成功')).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '關閉' }));
      fireEvent.click(screen.getAllByRole('button', { name: '查看警示詳情' })[0]);
    });
    await waitFor(() => {
      expect(screen.getByText('owner_preview_apply')).toBeInTheDocument();
    });

    const transitionButton = screen.getByRole('button', { name: '請依上方轉介流程處理來源資料' });
    expect(transitionButton).toBeDisabled();
    fireEvent.click(transitionButton);
    expect(screen.queryByText('狀態變更成功')).not.toBeInTheDocument();

    const detailRequests = requests.filter(({ path }) => path.startsWith(`${ANOMALY_LIST_ENDPOINT}/`));
    const referralRequests = requests.filter(({ path }) => path.endsWith('/referral'));
    expect(detailRequests).toHaveLength(1);
    expect(referralRequests).toHaveLength(1);
    expectOnlyGet(requests);
  });
});
