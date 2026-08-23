/**
 * File: data_import_entry_cutover.test.tsx
 * Description: 驗證資料匯入entry的GET預算、局部查詢重試、四類active控制與真實receipt呈現。
 */
import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { SYSTEM_STATUS_ENDPOINT } from '../api/system/system_status_client';
import { sessionClient } from '../api/auth/session_client';
import { detailedHcmResult } from './fixtures/hcm_import_result_fixtures';

vi.mock('../pages/AnomaliesPage', () => ({
  AnomaliesPage: () => null,
}));

const HCM_RESULTS_ENDPOINT = '/api/v1/case-import/hcm/workbooks/results';
const ACTIVE_PREVIEW_CONTROL_IDS = [
  'imports.hcm-current.preview',
  'imports.client-beclass.preview',
  'imports.staff-historical.preview',
  'imports.historic-orders.preview',
] as const;

const ACTIVE_APPLY_CONTROL_IDS = [
  'imports.hcm-current.apply',
  'imports.client-beclass.apply',
  'imports.staff-historical.apply',
  'imports.historic-orders.apply',
] as const;

type FetchRecord = {
  path: string;
  method: string;
};

type FetchMode = 'empty' | 'ready' | 'unavailable';

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

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function hcmEnvelope(items: unknown[]): unknown {
  return {
    success: true,
    message: '成功取得 HCM 匯入結果',
    data: { items, next_cursor: null },
    error: null,
  };
}

function legacyHcmResult(): typeof detailedHcmResult {
  return {
    ...detailedHcmResult,
    receipt_id: 9,
    source_content_digest: 'b'.repeat(64),
    row_outcomes_available: false,
    legacy_summary_only: true,
    row_outcomes: [],
  };
}

function typedUnavailableResponse(): unknown {
  return {
    detail: {
      error: {
        category: 'unavailable',
        code: 'HCM_RESULT_QUERY_UNAVAILABLE',
        message: 'HCM 匯入結果查詢暫時無法使用',
        field_errors: [],
        domain_blockers: [],
        retryable: true,
        correlation_id: 'hcm-result-entry-test',
        current_version: null,
      },
    },
  };
}

function installFetchStub(mode: FetchMode): FetchRecord[] {
  const requests: FetchRecord[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(String(input), 'http://admin.test');
    const method = String(init?.method ?? 'GET').toUpperCase();
    requests.push({ path: url.pathname, method });

    if (url.pathname === SYSTEM_STATUS_ENDPOINT) {
      return jsonResponse(PERFORMANCE_RESPONSE);
    }
    if (url.pathname === HCM_RESULTS_ENDPOINT) {
      if (mode === 'empty') return jsonResponse(hcmEnvelope([]));
      if (mode === 'unavailable') return jsonResponse(typedUnavailableResponse(), 503);
      return jsonResponse(hcmEnvelope([detailedHcmResult, legacyHcmResult()]));
    }
    throw new Error(`Unexpected API path: ${url.pathname}`);
  });
  return requests;
}

function authenticate(): void {
  sessionClient.setSession('data-import-entry-token', {
    id: 1,
    username: 'data-import-entry-admin',
    display_name: '資料匯入驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setDataImportHash(): void {
  window.history.replaceState(null, '', '#data-import');
}

function hcmRequests(requests: readonly FetchRecord[]): FetchRecord[] {
  return requests.filter(({ path }) => path === HCM_RESULTS_ENDPOINT);
}

function expectOnlyGet(requests: readonly FetchRecord[]): void {
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every(({ method }) => method === 'GET')).toBe(true);
}

describe('Data Import HCM Result Review entry cutover candidate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setDataImportHash();
  });

  afterEach(() => {
    sessionClient.clearSession();
    window.history.replaceState(null, '', '#');
    vi.restoreAllMocks();
  });

  it('actual StrictMode initial load uses one HCM GET and refresh adds one GET', async () => {
    authenticate();
    const requests = installFetchStub('ready');

    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('Receipt #8')).toBeInTheDocument());
    expect(window.location.hash).toBe('#data-import');
    expect(hcmRequests(requests)).toHaveLength(1);
    expect(hcmRequests(requests)[0]?.method).toBe('GET');

    fireEvent.click(screen.getByRole('button', { name: '重新整理結果' }));
    await waitFor(() => expect(hcmRequests(requests)).toHaveLength(2));
    expectOnlyGet(requests);
  });

  it('renders inserted, warning, problem, exact replay and legacy unavailable without fake success', async () => {
    authenticate();
    const requests = installFetchStub('ready');

    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('Receipt #8')).toBeInTheDocument());
    expect(screen.getByText('Receipt #9')).toBeInTheDocument();
    expect(screen.getByText('本次新增訂單')).toBeInTheDocument();
    expect(screen.getByText('115000001')).toBeInTheDocument();
    expect(screen.getAllByText('115000002').length).toBeGreaterThan(0);
    expect(screen.getByText(/^欄位：行動電話$/)).toBeInTheDocument();
    expect(screen.getByText(/^代碼：hcm_field_invalid:行動電話$/)).toBeInTheDocument();
    expect(screen.getByText('115000003')).toBeInTheDocument();
    expect(screen.getByText('Exact Replay')).toBeInTheDocument();
    expect(screen.getByText(/歷史摘要 receipt；本批次統計如上/)).toBeInTheDocument();
    expect(screen.queryByText('本批次沒有新增訂單。')).not.toBeInTheDocument();
    expect(hcmRequests(requests)).toHaveLength(1);
    expectOnlyGet(requests);
  });

  it('referral changes only the local hash and adds no HTTP request', async () => {
    authenticate();
    const requests = installFetchStub('ready');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText('Receipt #8')).toBeInTheDocument());
    const beforeReferral = requests.length;

    fireEvent.click(screen.getByRole('button', { name: '前往異常與匯入警示中心' }));
    expect(window.location.hash).toBe('#anomalies');
    expect(requests).toHaveLength(beforeReferral);
    expect(hcmRequests(requests)).toHaveLength(1);
    expectOnlyGet(requests);
  });

  it('empty and typed unavailable states never fabricate a receipt', async () => {
    authenticate();
    const emptyRequests = installFetchStub('empty');
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText(/目前沒有可查詢的 HCM 匯入receipt/)).toBeInTheDocument());
    expect(screen.queryByText(/Receipt #/)).not.toBeInTheDocument();
    expect(hcmRequests(emptyRequests)).toHaveLength(1);
    expectOnlyGet(emptyRequests);

    sessionClient.clearSession();
    window.history.replaceState(null, '', '#data-import');
    vi.restoreAllMocks();
    document.body.innerHTML = '';
    authenticate();
    const unavailableRequests = installFetchStub('unavailable');
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(document.querySelector('[data-surface-id="imports.hcm-results.error"]')).toHaveTextContent(/HCM 匯入結果目前無法取得/));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重試結果查詢' })).toBeInTheDocument();
    expect(screen.queryByText(/Receipt #/)).not.toBeInTheDocument();
    expect(hcmRequests(unavailableRequests)).toHaveLength(1);
    expectOnlyGet(unavailableRequests);
  });

  it('exposes four active Preview controls and explains why Preview or Apply cannot run yet', async () => {
    authenticate();
    const requests = installFetchStub('empty');

    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByText(/目前沒有可查詢的 HCM 匯入receipt/)).toBeInTheDocument());

    expect(document.querySelector('[data-control-id="imports.hcm-current.open-preview"]')).toBeInTheDocument();
    for (const controlId of ACTIVE_PREVIEW_CONTROL_IDS) {
      const control = document.querySelector(`[data-control-id="${controlId}"]`);
      expect(control, controlId).toBeInTheDocument();
      expect(control, controlId).toBeDisabled();
    }
    for (const controlId of ACTIVE_APPLY_CONTROL_IDS) {
      expect(document.querySelector(`[data-control-id="${controlId}"]`), controlId).toBeNull();
    }
    expect(screen.getAllByText('Preview 暫不可用：請先選擇 .xlsx 工作簿。')).toHaveLength(4);
    expect(screen.getAllByText('Apply 下一步：成功完成 Preview 後顯示確認與套用按鈕。')).toHaveLength(4);
    expect(document.querySelector('[data-control-id="imports.hcm-historical.preview"]')).toBeNull();
    expect(document.querySelector('[data-control-id="imports.bank-statements.preview"]')).toBeNull();
    expectOnlyGet(requests);
  });
});
