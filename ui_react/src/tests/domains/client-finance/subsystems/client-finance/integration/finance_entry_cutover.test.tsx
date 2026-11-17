/**
 * File: finance_entry_cutover.test.tsx
 * Description: 驗證 Finance entry 的 StrictMode GET 預算、四組查詢、正常匯入門檻與無假 mutation 入口。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../../../../../App';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { FINANCE_BATCH_RESPONSE, FINANCE_MANIFEST_RESPONSE } from '../../../../../fixtures/finance/finance_query_contract_fixtures';
import { CORE_STAGE_CODES } from '../../../../../../api/orders/order_core_stage_projection_schemas';

const ORDERS_SUMMARY_ENDPOINT = '/api/v1/orders/summaries';
const CLIENT_RECEIPT_ENDPOINT = '/api/v1/orders/CASE-FIN-001/client-finance/receipt-reconciliation';
const CORE_STAGE_ENDPOINT = '/api/orders/core-stage-timelines';
const BANK_TRANSACTIONS_ENDPOINT = '/api/v1/finance-import/bank-transactions';
const IMPORT_HISTORY_ENDPOINT = '/api/v1/finance-import/import-history';
const FINANCE_BATCHES_ENDPOINT = '/api/v1/finance-import/batches';
const FINANCE_MANIFEST_ENDPOINT = '/api/v1/finance-import/batches/BATCH-FIN-021/manifest';
const FINANCE_REVIEW_ENDPOINT = '/api/v1/finance-import/batches/BATCH-FIN-021/review-rows';
const FINANCE_REPROCESS_ENDPOINT = '/api/v1/finance-import/batches/BATCH-FIN-021/reprocess-runs';
const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';

type RequestRecord = {
  path: string;
  method: string;
};

type FetchStubOptions = {
  emptyCases?: boolean;
  noPublicBatchIdentity?: boolean;
  stageUnavailable?: boolean;
};

const REVIEW_RESPONSE = {
  success: true,
  message: 'ok',
  error: null,
  data: {
    batch_identity: 'BATCH-FIN-021',
    source_reviews: [],
    next_after_source_review_id: null,
    items: [{
      row_id: 301,
      row_identity: 'ROW-FIN-301',
      transaction_date: '2026-08-01',
      direction: 'credit',
      amount_ntd: 5000,
      classification_type: 'client_receipt',
      disposition: 'pending',
      reconciliation_status: 'unmatched',
      source_sheet: 'Sheet1',
      source_row: 2,
      occurrence_count: 1,
      available_actions: [],
      created_at: '2026-08-17T00:00:00+08:00',
    }],
    next_after_row_id: null,
  },
};

const REPROCESS_RESPONSE = {
  success: true,
  message: 'ok',
  error: null,
  data: {
    items: [{
      run_id: 401,
      batch_identity: 'BATCH-FIN-021',
      classifier_version: 'v1',
      plan_fingerprint: 'c'.repeat(64),
      selected_count: 1,
      changed_count: 0,
      dispatch_count: 0,
      reconciled_count: 0,
      pending_count: 1,
      status: 'pending',
      created_at: '2026-08-17T00:00:00+08:00',
      completed_at: '2026-08-17T00:00:00+08:00',
    }],
    next_before_run_id: null,
  },
};

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function systemStatusResponse(): unknown {
  return {
    success: true,
    message: 'ok',
    error: null,
    data: {
      started_at: '2026-08-20T01:02:03Z',
      request_count: 1,
      average_response_time_ms: 1,
      p50_response_time_upper_bound_ms: 1,
      p95_response_time_upper_bound_ms: 1,
      maximum_response_time_ms: 1,
    },
  };
}

function ordersSummaryResponse(emptyCases: boolean): unknown {
  return {
    success: true,
    message: 'ok',
    error: null,
    data: {
      items: emptyCases ? [] : [{
        case_no: 'CASE-FIN-001',
        client_name: '去敏客戶',
        order_status: '服務中',
        staff_name: null,
        identity_status: null,
        start_date: null,
        end_date: null,
        actual_start_date: null,
        actual_end_date: null,
        service_days: null,
        total_employer_self_pay_payable: null,
      }],
      next_cursor: null,
      etag: 'a'.repeat(64),
    },
  };
}

function typedUnavailableResponse(): unknown {
  return {
    detail: {
      error: {
        category: 'unavailable',
        code: 'CLIENT_RECEIPT_UNAVAILABLE',
        message: 'HTTP 503 correlation_id=finance-secret-detail',
        field_errors: [],
        domain_blockers: [],
        retryable: true,
        correlation_id: 'finance-entry-cutover',
        current_version: null,
      },
    },
  };
}

function installFetchStub(options: FetchStubOptions = {}): RequestRecord[] {
  const requests: RequestRecord[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(raw, 'http://admin.test');
    const path = url.pathname;
    requests.push({ path, method: String(init?.method ?? 'GET').toUpperCase() });

    if (path === SYSTEM_STATUS_ENDPOINT) return response(systemStatusResponse());
    if (path === ORDERS_SUMMARY_ENDPOINT) return response(ordersSummaryResponse(Boolean(options.emptyCases)));
    if (path === CORE_STAGE_ENDPOINT) return options.stageUnavailable ? response(typedUnavailableResponse(), 503) : response({
      success: true,
      message: 'ok',
      error: null,
      data: {
        items: [],
        stage_counts: Object.fromEntries(CORE_STAGE_CODES.map(code => [code, 0])),
        substatus_counts: {},
        historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 },
        next_cursor: null,
        etag: 'b'.repeat(64),
      },
    });
    if (path === BANK_TRANSACTIONS_ENDPOINT) return response({
      success: true, message: 'ok', error: null,
      data: { items: [], pending_count: 0, next_before_row_id: null },
    });
    if (path === IMPORT_HISTORY_ENDPOINT) return response({
      success: true, message: 'ok', error: null,
      data: { items: [], next_before: null },
    });
    if (path === FINANCE_BATCHES_ENDPOINT) {
      if (!options.noPublicBatchIdentity) return response(FINANCE_BATCH_RESPONSE);
      return response({
        ...FINANCE_BATCH_RESPONSE,
        data: [{ ...FINANCE_BATCH_RESPONSE.data[0], batch_identity: null }],
      });
    }
    if (path === FINANCE_MANIFEST_ENDPOINT) return response(FINANCE_MANIFEST_RESPONSE);
    if (path === FINANCE_REVIEW_ENDPOINT) return response(REVIEW_RESPONSE);
    if (path === FINANCE_REPROCESS_ENDPOINT) return response(REPROCESS_RESPONSE);
    throw new Error(`Unexpected API path: ${path}`);
  });
  return requests;
}

function authenticate(): void {
  sessionClient.setSession('finance-entry-cutover-token', {
    id: 7,
    username: 'finance-entry-admin',
    display_name: '財務入口驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setFinanceHash(): void {
  act(() => window.history.replaceState(null, '', '#finance'));
}

function countPath(requests: readonly RequestRecord[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

describe('Finance #finance entry static subgate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setFinanceHash();
  });

  afterEach(() => {
    cleanup();
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#'));
    vi.restoreAllMocks();
  });

  it('uses the current four workspaces and keeps bank import guarded before file selection', async () => {
    authenticate();
    const requests = installFetchStub({ emptyCases: true });
    render(<StrictMode><App /></StrictMode>);

    await screen.findByText('目前沒有符合條件的進行中案件。');
    expect(window.location.hash).toBe('#finance');
    expect(screen.getByRole('heading', { name: '帳務中心' })).toBeInTheDocument();
    expect(within(screen.getByRole('navigation', { name: '帳務工作區' })).getAllByRole('button').map(button => button.textContent)).toEqual(['案件帳務', '銀行對帳', '政府補助清單', '每月帳務']);
    expect(countPath(requests, ORDERS_SUMMARY_ENDPOINT)).toBeGreaterThanOrEqual(1);
    expect(countPath(requests, CORE_STAGE_ENDPOINT)).toBeGreaterThanOrEqual(1);
    expect(countPath(requests, '/api/v1/client-payments')).toBe(0);
    expect(countPath(requests, CLIENT_RECEIPT_ENDPOINT)).toBe(0);
    expect(countPath(requests, BANK_TRANSACTIONS_ENDPOINT)).toBe(0);

    fireEvent.click(screen.getByRole('button', { name: '銀行對帳' }));
    await screen.findByText('目前沒有符合條件的銀行交易資料。');
    expect(countPath(requests, BANK_TRANSACTIONS_ENDPOINT)).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole('button', { name: '匯入永豐對帳單' }));
    expect(screen.getByRole('button', { name: '匯入銀行交易明細' })).toBeDisabled();
    expect(document.querySelector('[data-control-id="finance.finance-import.preview"]')).toBeNull();
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeNull();
    expect(requests.every(request => request.method === 'GET')).toBe(true);
  });

  it('opens import history separately without reading historical batch identities', async () => {
    authenticate();
    const requests = installFetchStub({ noPublicBatchIdentity: true });
    render(<StrictMode><App /></StrictMode>);

    fireEvent.click(await screen.findByRole('button', { name: '銀行對帳' }));
    await screen.findByText('目前沒有符合條件的銀行交易資料。');
    expect(screen.getByRole('button', { name: '匯入紀錄' })).toBeVisible();
    expect(countPath(requests, IMPORT_HISTORY_ENDPOINT)).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: '匯入紀錄' }));
    expect(await screen.findByText('目前沒有匯入紀錄。')).toBeVisible();
    expect(countPath(requests, IMPORT_HISTORY_ENDPOINT)).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('無public identity')).not.toBeInTheDocument();
    expect(countPath(requests, FINANCE_BATCHES_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_MANIFEST_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_REVIEW_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_REPROCESS_ENDPOINT)).toBe(0);
    expect(requests.every(request => request.method === 'GET')).toBe(true);
  });

  it('distinguishes an empty active list from typed unavailability of the stage source', async () => {
    authenticate();
    const emptyRequests = installFetchStub({ emptyCases: true });
    render(<StrictMode><App /></StrictMode>);

    expect(await screen.findByText('目前沒有符合條件的進行中案件。')).toBeVisible();
    expect(screen.queryByText('CASE-FIN-001')).not.toBeInTheDocument();
    expect(countPath(emptyRequests, CLIENT_RECEIPT_ENDPOINT)).toBe(0);
    expect(emptyRequests.every(request => request.method === 'GET')).toBe(true);

    cleanup();
    authenticate();
    const unavailableRequests = installFetchStub({ stageUnavailable: true });
    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('案件帳務或營運階段暫時無法取得，請重新查詢。'));
    expect(screen.queryByText(/HTTP 503|correlation_id|finance-secret-detail/)).not.toBeInTheDocument();
    expect(screen.queryByText('目前沒有符合條件的進行中案件。')).not.toBeInTheDocument();
    expect(screen.queryByText('CASE-FIN-001')).not.toBeInTheDocument();
    expect(countPath(unavailableRequests, CORE_STAGE_ENDPOINT)).toBeGreaterThanOrEqual(1);
    expect(unavailableRequests.every(request => request.method === 'GET')).toBe(true);
  });
});
