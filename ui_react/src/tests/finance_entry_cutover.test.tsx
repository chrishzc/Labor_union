/**
 * File: finance_entry_cutover.test.tsx
 * Description: 驗證 Finance entry 的 StrictMode GET 預算、四組查詢、正常匯入門檻與無假 mutation 入口。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import {
  ACCOUNTS_PAYABLE_RESPONSE,
  FINANCE_BATCH_RESPONSE,
  FINANCE_MANIFEST_RESPONSE,
  RECEIPT_RESPONSE,
  STAFF_PAYABLES_RESPONSE,
} from './fixtures/finance/finance_query_contract_fixtures';

const ORDERS_SUMMARY_ENDPOINT = '/api/v1/orders/summaries';
const CLIENT_RECEIPT_ENDPOINT = '/api/v1/orders/CASE-FIN-001/client-finance/receipt-reconciliation';
const STAFF_DIRECTORY_ENDPOINT = '/api/v1/staff/summaries';
const STAFF_PAYABLE_ENDPOINT = '/api/v1/staff-payables/11';
const ACCOUNTS_PAYABLE_ENDPOINT = '/api/v1/finance-reports/accounts-payable';
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
  receiptStatus?: number;
};

const REVIEW_RESPONSE = {
  success: true,
  message: 'ok',
  error: null,
  data: {
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

function staffDirectoryResponse(): unknown {
  return {
    success: true,
    message: 'ok',
    error: null,
    data: {
      items: [{ id: 11, name: '去敏人員', phone: null }],
      next_cursor: null,
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
    if (path === CLIENT_RECEIPT_ENDPOINT) {
      return options.receiptStatus === 503
        ? response(typedUnavailableResponse(), 503)
        : response(RECEIPT_RESPONSE);
    }
    if (path === STAFF_DIRECTORY_ENDPOINT) return response(staffDirectoryResponse());
    if (path === STAFF_PAYABLE_ENDPOINT) return response(STAFF_PAYABLES_RESPONSE);
    if (path === ACCOUNTS_PAYABLE_ENDPOINT) return response(ACCOUNTS_PAYABLE_RESPONSE);
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

  it('actual StrictMode 四個 workspace 維持 active-tab selector/detail exact GET budget，匯入流程在未選檔前保持 guarded', async () => {
    authenticate();
    const requests = installFetchStub();
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('OBL-C-1')).toBeInTheDocument());
    expect(window.location.hash).toBe('#finance');
    expect(screen.getByText('💰 財務查詢與對帳工作台')).toBeInTheDocument();
    expect(countPath(requests, ORDERS_SUMMARY_ENDPOINT)).toBe(1);
    expect(countPath(requests, CLIENT_RECEIPT_ENDPOINT)).toBe(1);
    expect(document.querySelector('[data-control-id="finance.client-receipt.settle"]')).toBeNull();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.refund.approve"]')).toBeNull();
    expect(document.querySelector('[data-control-id="finance.subsidy.advance"]')).toBeNull();
    expect(document.querySelector('[data-control-id="finance.accounts-payable.export-xlsx"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '月嫂應付款' }));
    await waitFor(() => expect(screen.getByText('OBL-S-1')).toBeInTheDocument());
    expect(countPath(requests, STAFF_DIRECTORY_ENDPOINT)).toBe(1);
    expect(countPath(requests, STAFF_PAYABLE_ENDPOINT)).toBe(1);
    expect(document.querySelector('[data-control-id="finance.staff-payable.mark-paid"]')).toBeNull();
    expect(document.querySelector('[data-control-id="finance.staff-payable.adjustment"]')).toBeNull();
    expect(screen.queryByText(/未開放/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '應付帳款' }));
    await waitFor(() => expect(screen.getByText(/\*{8}9012/)).toBeInTheDocument());
    expect(countPath(requests, ACCOUNTS_PAYABLE_ENDPOINT)).toBe(1);
    expect(screen.queryByText('123456789012')).not.toBeInTheDocument();
    expect(document.querySelector('[data-control-id="finance.accounts-payable.export-xlsx"]')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    expect(screen.getByText('上傳檔案 → 預覽 → 匯入完成')).toBeInTheDocument();
    expect(countPath(requests, FINANCE_BATCHES_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_MANIFEST_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_REVIEW_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_REPROCESS_ENDPOINT)).toBe(0);
    expect(document.querySelector('[data-control-id="finance.finance-import.upload"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="finance.finance-import.reprocess"]')).toBeNull();
    expect(document.querySelector('[data-control-id="finance.finance-import.preview"]')).toBeDisabled();
    expect(document.querySelector('[data-control-id="finance.finance-import.apply"]')).toBeNull();
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('正常 Finance Import 不查詢或顯示歷史批次 identity', async () => {
    authenticate();
    const requests = installFetchStub({ noPublicBatchIdentity: true });
    render(<StrictMode><App /></StrictMode>);

    fireEvent.click(screen.getByRole('button', { name: '銀行流水匯入' }));
    expect(screen.getByText('上傳檔案 → 預覽 → 匯入完成')).toBeInTheDocument();
    expect(screen.queryByText('無public identity')).not.toBeInTheDocument();
    expect(countPath(requests, FINANCE_BATCHES_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_MANIFEST_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_REVIEW_ENDPOINT)).toBe(0);
    expect(countPath(requests, FINANCE_REPROCESS_ENDPOINT)).toBe(0);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('empty 與 typed unavailable 不轉成 fake success 或資料列', async () => {
    authenticate();
    const emptyRequests = installFetchStub({ emptyCases: true });
    render(<StrictMode><App /></StrictMode>);

    await waitFor(() => expect(screen.getByText('目前沒有可顯示的收款資料。')).toBeInTheDocument());
    expect(screen.queryByText('OBL-C-1')).not.toBeInTheDocument();
    expect(countPath(emptyRequests, ORDERS_SUMMARY_ENDPOINT)).toBe(1);
    expect(countPath(emptyRequests, CLIENT_RECEIPT_ENDPOINT)).toBe(0);
    expect(emptyRequests.every((request) => request.method === 'GET')).toBe(true);

    cleanup();
    authenticate();
    const unavailableRequests = installFetchStub({ receiptStatus: 503 });
    render(<StrictMode><App /></StrictMode>);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('服務暫時無法使用，請稍後再試。'));
    expect(screen.queryByText(/HTTP 503|correlation_id|finance-secret-detail/)).not.toBeInTheDocument();
    expect(screen.queryByText('OBL-C-1')).not.toBeInTheDocument();
    expect(screen.queryByText(/已成功|已結清|付款成功/)).not.toBeInTheDocument();
    expect(countPath(unavailableRequests, CLIENT_RECEIPT_ENDPOINT)).toBe(1);
    expect(unavailableRequests.every((request) => request.method === 'GET')).toBe(true);
  });
});
