/**
 * File: orders_entry_cutover.test.tsx
 * Description: 驗證 #orders 的 StrictMode GET 預算、typed Drawer 與失敗邊界。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import type { OrderSummaryPage } from '../api/orders/order_query_schemas';
import {
  realisticAssignmentPlan,
  realisticContractCompletion,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
} from './fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

const SUMMARY_ENDPOINT = '/api/v1/orders/summaries';
const STAGE_PROJECTION_ENDPOINT = '/api/orders/operational-timelines';
const ORDER_DETAIL_ENDPOINT = '/api/v1/orders/ORD-2026-0801';
const CALENDAR_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/calendar-detail`;
const TERMS_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/terms`;
const COMPLETION_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/contract-completion`;
const ASSIGNMENT_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/assignment-plan`;
const CANDIDATE_POOL_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/candidate-contact-pool`;
const ACTIVE_PLAN_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/matching-plans/active`;
const CARD_PROJECTION_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/card-projection`;
const CONTRACT_SIGNING_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/contract-signing`;
const CANCELLATION_QUERY_ENDPOINT = `${ORDER_DETAIL_ENDPOINT}/cancellation`;
const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';

type FetchRecord = {
  path: string;
  method: string;
};

type FetchStubOptions = {
  summaryBody?: unknown;
  summaryStatus?: number;
  stageBody?: unknown;
};

const operableSummaryPage: OrderSummaryPage = {
  ...realisticOrderSummaryPage,
  items: realisticOrderSummaryPage.items.map((item, index) => index === 0 ? { ...item, order_status: '洽談中' } : item),
};

function requestPath(input: string | URL | Request): string {
  const raw = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
  return new URL(raw, 'http://admin.test').pathname;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function summaryEnvelope(page: OrderSummaryPage): unknown {
  return {
    success: true,
    message: '成功取得訂單摘要',
    data: page,
    error: null,
  };
}

function systemStatusEnvelope(): unknown {
  return {
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
}

function typedUnavailableResponse(): unknown {
  return {
    detail: {
      error: {
        category: 'unavailable',
        code: 'ORDERS_QUERY_UNAVAILABLE',
        message: '訂單摘要服務暫時無法使用',
        field_errors: [],
        domain_blockers: [],
        retryable: true,
        correlation_id: 'orders-entry-cutover',
        current_version: null,
      },
    },
  };
}

function orderEnvelope(data: unknown): unknown {
  return { success: true, message: '成功取得 Orders query', data, error: null };
}

function cardProjectionEnvelope(): unknown {
  const field = (owner: string, sourceIdentity: string) => ({
    value: null,
    owner,
    source_identity: sourceIdentity,
    source_version: null,
    availability: 'unavailable',
    availability_reason: 'test_root_fact_missing',
  });
  return orderEnvelope({
    case_no: 'ORD-2026-0801',
    contact_phone: field('Clients', 'client:ORD-2026-0801'),
    contact_address: field('Clients', 'client:ORD-2026-0801'),
    requires_cooking: field('Orders Terms', 'terms:ORD-2026-0801'),
    floor_fee_ntd: field('Orders Terms', 'terms:ORD-2026-0801'),
    deposit_amount_ntd: field('Client Finance', 'deposit:ORD-2026-0801'),
    deposit_settlement_state: field('Client Finance', 'deposit:ORD-2026-0801'),
    deposit_settled_on: field('Client Finance', 'deposit:ORD-2026-0801'),
    actual_start_date: field('Orders', 'actual-dates:ORD-2026-0801'),
    actual_end_date: field('Orders', 'actual-dates:ORD-2026-0801'),
    assignment_segments: field('Scheduling', 'assignments:ORD-2026-0801'),
  });
}

function installFetchStub(options: FetchStubOptions = {}): FetchRecord[] {
  const requests: FetchRecord[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = requestPath(input);
    requests.push({
      path,
      method: String(init?.method ?? 'GET').toUpperCase(),
    });

    if (path === SYSTEM_STATUS_ENDPOINT) return jsonResponse(systemStatusEnvelope());
    if (path === SUMMARY_ENDPOINT) {
      return jsonResponse(
        options.summaryBody ?? summaryEnvelope(operableSummaryPage),
        options.summaryStatus ?? 200,
      );
    }
    if (path === STAGE_PROJECTION_ENDPOINT) {
      return jsonResponse(
        options.stageBody ?? orderEnvelope(buildOrdersStageProjectionFixture(operableSummaryPage)),
      );
    }
    if (path === ORDER_DETAIL_ENDPOINT) return jsonResponse(orderEnvelope(realisticOrderDetail));
    if (path === CALENDAR_ENDPOINT) return jsonResponse(orderEnvelope(realisticOrderCalendarDetail));
    if (path === TERMS_ENDPOINT) return jsonResponse(orderEnvelope(realisticOrderTerms));
    if (path === COMPLETION_ENDPOINT) return jsonResponse(orderEnvelope(realisticContractCompletion));
    if (path === ASSIGNMENT_ENDPOINT) return jsonResponse(orderEnvelope(realisticAssignmentPlan));
    if (path === CANDIDATE_POOL_ENDPOINT) return jsonResponse(orderEnvelope({
      pool_id: null,
      case_no: 'ORD-2026-0801',
      candidates: [],
    }));
    if (path === ACTIVE_PLAN_ENDPOINT) return jsonResponse(orderEnvelope({
      plan: { id: 19, case_no: 'ORD-2026-0801', status: 'proposed' },
      availability_lock: null,
    }));
    if (path === CARD_PROJECTION_ENDPOINT) return jsonResponse(cardProjectionEnvelope());
    if (path === CONTRACT_SIGNING_ENDPOINT) return jsonResponse(orderEnvelope({
      case_no: 'ORD-2026-0801', staff_segments: [], commitment_id: null,
      client_document_sent: false, client_signed_received: false, contract_identity: null, documents: [],
    }));
    if (path === CANCELLATION_QUERY_ENDPOINT) return jsonResponse(orderEnvelope({
      case_no: 'ORD-2026-0801', lifecycle_status: '訂單成立', actual_start_date: null,
      contracted_service_days: 30, service_hours_per_day: 8, service_started: false,
      service_data_locked: false, order_version: 0, scheduling_version: 0,
      scheduling_generation: 0, client_finance_version: 0, payroll_version: 0,
      confirmed_service_days: [], caregiver_options: [],
    }));
    throw new Error(`Unexpected API path: ${path}`);
  });
  return requests;
}

let authNonce = 0;

function authenticate(): void {
  authNonce += 1;
  sessionClient.setSession(`orders-entry-cutover-token-${authNonce}`, {
    id: 7,
    username: 'orders-entry-admin',
    display_name: 'Orders 入口驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setOrdersHash(): void {
  act(() => window.history.replaceState(null, '', '#orders'));
}

function countPath(requests: readonly FetchRecord[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

describe('Orders #orders entry static subgate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setOrdersHash();
  });

  afterEach(() => {
    cleanup();
    sessionClient.clearSession();
    act(() => window.history.replaceState(null, '', '#'));
    vi.restoreAllMocks();
  });

  it('actual StrictMode 初始摘要恰好一次 GET，三個 query drawer 維持 frozen budget 且全程 GET-only', async () => {
    authenticate();
    const requests = installFetchStub();

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    expect(window.location.hash).toBe('#orders');
    expect(screen.getByText('📦 訂單與客戶管理')).toBeInTheDocument();
    expect(screen.queryByText('📊 訂單進度儀表板')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id^="order-tracker."]')).toBeNull();
    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(1);
    expect(countPath(requests, STAGE_PROJECTION_ENDPOINT)).toBe(1);

    expect(screen.queryByRole('button', { name: /新建訂單/ })).not.toBeInTheDocument();
    for (const label of [
      '1. 進件與補件',
      '2. 媒合與徵詢意願',
      '3. 推薦客戶確認',
      '4. 雙邊簽約定金',
      '5. 確認事前服務日期',
      '6. 正式服務中',
      '7. 完工結案請款',
    ]) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeEnabled();
    }

    const initialQueryCounts = {
      detail: countPath(requests, ORDER_DETAIL_ENDPOINT),
      calendar: countPath(requests, CALENDAR_ENDPOINT),
      terms: countPath(requests, TERMS_ENDPOINT),
      completion: countPath(requests, COMPLETION_ENDPOINT),
      assignment: countPath(requests, ASSIGNMENT_ENDPOINT),
      candidatePool: countPath(requests, CANDIDATE_POOL_ENDPOINT),
      activePlan: countPath(requests, ACTIVE_PLAN_ENDPOINT),
      card: countPath(requests, CARD_PROJECTION_ENDPOINT),
      signing: countPath(requests, CONTRACT_SIGNING_ENDPOINT),
      cancellation: countPath(requests, CANCELLATION_QUERY_ENDPOINT),
    };

    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    await waitFor(() => expect(countPath(requests, CONTRACT_SIGNING_ENDPOINT) - initialQueryCounts.signing).toBe(1));
    expect(await screen.findByText('尚無月嫂契約分段')).toBeInTheDocument();
    expect(countPath(requests, ORDER_DETAIL_ENDPOINT) - initialQueryCounts.detail).toBe(1);
    expect(countPath(requests, TERMS_ENDPOINT) - initialQueryCounts.terms).toBe(1);
    expect(countPath(requests, COMPLETION_ENDPOINT) - initialQueryCounts.completion).toBe(1);
    expect(countPath(requests, CALENDAR_ENDPOINT) - initialQueryCounts.calendar).toBe(0);
    expect(countPath(requests, ASSIGNMENT_ENDPOINT) - initialQueryCounts.assignment).toBe(0);
    expect(countPath(requests, CANDIDATE_POOL_ENDPOINT) - initialQueryCounts.candidatePool).toBe(0);
    expect(countPath(requests, ACTIVE_PLAN_ENDPOINT) - initialQueryCounts.activePlan).toBe(0);
    expect(countPath(requests, CARD_PROJECTION_ENDPOINT) - initialQueryCounts.card).toBe(1);
    expect(countPath(requests, CONTRACT_SIGNING_ENDPOINT) - initialQueryCounts.signing).toBe(1);
    expect(screen.queryByText(/後端.*提供|未開放|未納入/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));

    const beforeMatchingTerms = countPath(requests, TERMS_ENDPOINT);
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    await waitFor(() => expect(screen.getByText('正式執行排班（非候選推薦）')).toBeInTheDocument());
    expect(countPath(requests, ORDER_DETAIL_ENDPOINT) - initialQueryCounts.detail).toBe(2);
    expect(countPath(requests, ASSIGNMENT_ENDPOINT) - initialQueryCounts.assignment).toBe(1);
    expect(countPath(requests, CANDIDATE_POOL_ENDPOINT) - initialQueryCounts.candidatePool).toBe(1);
    expect(countPath(requests, ACTIVE_PLAN_ENDPOINT) - initialQueryCounts.activePlan).toBe(1);
    expect(countPath(requests, TERMS_ENDPOINT) - beforeMatchingTerms).toBe(1);
    expect(countPath(requests, COMPLETION_ENDPOINT) - initialQueryCounts.completion).toBe(1);
    expect(countPath(requests, CARD_PROJECTION_ENDPOINT) - initialQueryCounts.card).toBe(2);
    expect(screen.queryByText(/後端.*提供|未開放|未納入/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));

    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    const cancelTabBtn = await screen.findByRole('button', { name: /訂單取消與退款試算/ });
    fireEvent.click(cancelTabBtn);
    await waitFor(() => expect(countPath(requests, CANCELLATION_QUERY_ENDPOINT) - initialQueryCounts.cancellation).toBe(1));

    // 驗證 5-Tab 導航按鈕完整存在
    expect(screen.getByRole('button', { name: /實質服務日曆/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /受控重開訂單/ })).toBeInTheDocument();
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('empty 與 typed unavailable 維持 fail closed，不產生假案件或成功狀態', async () => {
    authenticate();
    const emptyPage: OrderSummaryPage = { items: [], next_cursor: null, etag: 'b'.repeat(64) };
    const emptyRequests = installFetchStub({
      summaryBody: summaryEnvelope(emptyPage),
      stageBody: orderEnvelope(buildOrdersStageProjectionFixture(emptyPage)),
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('目前無符合條件的訂單')).toBeInTheDocument());
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(countPath(emptyRequests, SUMMARY_ENDPOINT)).toBe(1);
    expect(emptyRequests.every((request) => request.method === 'GET')).toBe(true);

    cleanup();
    authenticate();
    const unavailableRequests = installFetchStub({
      summaryBody: typedUnavailableResponse(),
      summaryStatus: 503,
    });
    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText(/載入訂單資料失敗：訂單摘要服務暫時無法使用/)).toBeInTheDocument());
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(screen.queryByText(/已成功載入|伺服器狀態：/)).not.toBeInTheDocument();
    expect(countPath(unavailableRequests, SUMMARY_ENDPOINT)).toBe(1);
    expect(unavailableRequests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('typed error retry 最多只增加一次 GET，成功結果不混入舊摘要或推導狀態', async () => {
    authenticate();
    const freshPage: OrderSummaryPage = {
      items: [realisticOrderSummaryPage.items[1]],
      next_cursor: null,
      etag: 'c'.repeat(64),
    };
    const requests: FetchRecord[] = [];
    let summaryCalls = 0;

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = requestPath(input);
      requests.push({ path, method: String(init?.method ?? 'GET').toUpperCase() });
      if (path === SYSTEM_STATUS_ENDPOINT) return jsonResponse(systemStatusEnvelope());
      if (path !== SUMMARY_ENDPOINT) throw new Error(`Unexpected API path: ${path}`);
      summaryCalls += 1;
      if (summaryCalls === 1) return jsonResponse(typedUnavailableResponse(), 503);
      return jsonResponse(summaryEnvelope(freshPage));
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText(/載入訂單資料失敗：訂單摘要服務暫時無法使用/)).toBeInTheDocument());
    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(1);
    fireEvent.click(screen.getByRole('button', { name: '重試' }));
    await waitFor(() => expect(screen.getByText('ORD-2026-0802')).toBeInTheDocument());
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(2);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });
});
