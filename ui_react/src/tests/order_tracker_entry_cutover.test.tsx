/**
 * File: order_tracker_entry_cutover.test.tsx
 * Description: 驗證 Order Tracker entry 的 StrictMode GET 預算、七階段與唯讀 Drawer 查詢。
 */
import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { sessionClient } from '../api/auth/session_client';
import {
  realisticOrderSummaryPage,
} from './fixtures/orders_real_data_fixtures';
import type { OrderSummaryPage } from '../api/orders/order_query_schemas';

const SUMMARY_ENDPOINT = '/api/v1/orders/summaries';
const STAGE_PROJECTION_ENDPOINT = '/api/orders/operational-timelines';
const SYSTEM_STATUS_ENDPOINT = '/api/v1/system/status/performance-snapshot';
const CARD_PROJECTION_ENDPOINT = '/api/v1/orders/ORD-2026-0801/card-projection';
const NOTIFICATION_TIMELINE_ENDPOINT = '/api/v1/line/notification-rules/timeline/ORD-2026-0801';

const STAGE_CODES = [
  'intake_terms',
  'matching_willingness',
  'client_review',
  'contract_deposit',
  'date_confirmation',
  'active_service',
  'settlement_payout',
] as const;

type FetchRecord = {
  path: string;
  method: string;
  signal?: AbortSignal;
};

type FetchStubOptions = {
  summaryBody?: unknown;
  summaryStatus?: number;
  stageBody?: unknown;
  stageStatus?: number;
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

function stageProjectionEnvelope(summaryPage: OrderSummaryPage): unknown {
  const items = summaryPage.items.map((summary, itemIndex) => {
    const currentStageCode = STAGE_CODES[itemIndex % STAGE_CODES.length];
    const stages = STAGE_CODES.map((code, stageIndex) => {
      const isCurrent = code === currentStageCode;
      return {
        ordinal: stageIndex + 1,
        code,
        label: `測試階段 ${stageIndex + 1}`,
        owner: 'test fixture',
        status: isCurrent ? 'in_progress' : 'unavailable',
        source: {
          owner: 'test fixture',
          identity: `test:${summary.case_no}:${code}`,
          version: 1,
        },
        occurred_at: null,
        blockers: [],
        warnings: [],
        available_actions: [],
        availability_reason: isCurrent ? null : 'test_data_unavailable',
        settlement: code === 'settlement_payout'
          ? ['service_completion', 'client_settlement', 'staff_payout'].map((settlementCode) => ({
            code: settlementCode,
            status: 'unavailable',
            source: {
              owner: 'test fixture',
              identity: `test:${summary.case_no}:${settlementCode}`,
              version: 1,
            },
            occurred_at: null,
            availability_reason: 'test_data_unavailable',
          }))
          : [],
      };
    });
    const sopSteps = Array.from({ length: 11 }, (_, stepIndex) => ({
      ordinal: stepIndex + 1,
      code: `test_step_${stepIndex + 1}`,
      label: `測試步驟 ${stepIndex + 1}`,
      owner: 'test fixture',
      status: 'unavailable',
      occurred_at: null,
      blockers: [],
      warnings: [],
      available_actions: [],
      availability_reason: 'test_data_unavailable',
    }));
    return {
      case_no: summary.case_no,
      base_revision: 1,
      current_stage_code: currentStageCode,
      stages,
      sop_steps: sopSteps,
      projection_digest: 'd'.repeat(64),
    };
  });
  const stageCounts = STAGE_CODES.reduce<Record<string, number>>((counts, code) => {
    counts[code] = items.filter((item) => item.current_stage_code === code).length;
    return counts;
  }, {});
  return {
    success: true,
    message: '成功取得訂單七階段投影',
    data: {
      items,
      stage_counts: stageCounts,
      next_cursor: null,
      etag: 'e'.repeat(64),
    },
    error: null,
  };
}

function cardProjectionEnvelope(): unknown {
  const field = (owner: string, identity: string, value: unknown) => ({
    value,
    owner,
    source_identity: identity,
    source_version: '1',
    availability: 'available',
    availability_reason: null,
  });
  return {
    success: true,
    message: '成功取得案件卡片',
    data: {
      case_no: 'ORD-2026-0801',
      contact_phone: field('Clients', 'client:ORD-2026-0801', '0900000000'),
      contact_address: field('Clients', 'client:ORD-2026-0801', '測試地址'),
      requires_cooking: field('Orders', 'terms:ORD-2026-0801', true),
      floor_fee_ntd: field('Orders', 'terms:ORD-2026-0801', 0),
      deposit_amount_ntd: field('Orders', 'deposit:ORD-2026-0801', 10000),
      deposit_settlement_state: field('Orders', 'deposit:ORD-2026-0801', 'settled'),
      deposit_settled_on: field('Orders', 'deposit:ORD-2026-0801', '2026-08-10'),
      actual_start_date: field('Scheduling', 'schedule:ORD-2026-0801', '2026-08-16'),
      actual_end_date: field('Scheduling', 'schedule:ORD-2026-0801', '2026-09-14'),
      assignment_segments: field('Scheduling', 'assignments:ORD-2026-0801', []),
    },
    error: null,
  };
}

function notificationTimelineEnvelope(): unknown {
  return {
    success: true,
    message: '成功取得 LINE 通知歷程',
    data: { case_no: 'ORD-2026-0801', records: [] },
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
        correlation_id: 'order-tracker-entry-cutover',
        current_version: null,
      },
    },
  };
}

function installFetchStub(options: FetchStubOptions = {}): FetchRecord[] {
  const requests: FetchRecord[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const path = requestPath(input);
    requests.push({
      path,
      method: String(init?.method ?? 'GET').toUpperCase(),
      signal: init?.signal ?? undefined,
    });

    if (path === SYSTEM_STATUS_ENDPOINT) {
      return jsonResponse(systemStatusEnvelope());
    }
    if (path === STAGE_PROJECTION_ENDPOINT) {
      return jsonResponse(
        options.stageBody ?? stageProjectionEnvelope(realisticOrderSummaryPage),
        options.stageStatus ?? 200,
      );
    }
    if (path === SUMMARY_ENDPOINT) {
      return jsonResponse(
        options.summaryBody ?? summaryEnvelope(realisticOrderSummaryPage),
        options.summaryStatus ?? 200,
      );
    }
    if (path === CARD_PROJECTION_ENDPOINT) return jsonResponse(cardProjectionEnvelope());
    if (path === NOTIFICATION_TIMELINE_ENDPOINT) return jsonResponse(notificationTimelineEnvelope());
    throw new Error(`Unexpected API path: ${path}`);
  });
  return requests;
}

function authenticate(): void {
  sessionClient.setSession('order-tracker-entry-cutover-token', {
    id: 7,
    username: 'order-tracker-entry-admin',
    display_name: '訂單看板驗證管理員',
    role: 'system_admin',
    capabilities: ['system.administration'],
    is_root: true,
    access_control_version: 1,
  });
}

function setTrackerHash(): void {
  act(() => {
    window.history.replaceState(null, '', '#order-tracker');
  });
}

function countPath(requests: readonly FetchRecord[], path: string): number {
  return requests.filter((request) => request.path === path).length;
}

describe('Order Tracker #order-tracker entry static subgate', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    setTrackerHash();
  });

  afterEach(() => {
    sessionClient.clearSession();
    act(() => {
      window.history.replaceState(null, '', '#');
    });
    vi.restoreAllMocks();
  });

  it('actual StrictMode 初始恰好一次 summaries 與 typed stage projection GET，互動維持 zero extra request', async () => {
    authenticate();
    const requests = installFetchStub();

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => {
      expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument();
      expect(screen.getAllByText('階段案件已載入')).toHaveLength(7);
    });
    expect(window.location.hash).toBe('#order-tracker');
    expect(screen.getByText('📊 訂單進度儀表板')).toBeInTheDocument();
    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(1);
    expect(countPath(requests, STAGE_PROJECTION_ENDPOINT)).toBe(1);
    expect(document.querySelectorAll('[data-surface-id^="order-tracker.stage-slot."]')).toHaveLength(7);
    expect(document.querySelectorAll('[data-surface-id^="order-tracker.stage-count."]')).toHaveLength(7);
    expect(screen.getAllByText('案件數 1')).toHaveLength(7);
    expect(screen.getAllByText('階段案件已載入')).toHaveLength(7);
    expect(screen.queryByText('訂單摘要')).not.toBeInTheDocument();
    expect(screen.queryByText(/目前無案件停留於此階段/)).not.toBeInTheDocument();

    const summaryCountBeforeInteractions = countPath(requests, SUMMARY_ENDPOINT);
    const stageCountBeforeInteractions = countPath(requests, STAGE_PROJECTION_ENDPOINT);
    for (const button of Array.from(
      document.querySelectorAll<HTMLButtonElement>('[data-control-id^="order-tracker.stage-nav."]'),
    )) {
      fireEvent.click(button);
    }

    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));
    expect(document.querySelectorAll('[data-surface-id^="order-tracker.sop.step."]')).toHaveLength(11);
    expect(screen.queryByText('狀態 —　時間 —')).not.toBeInTheDocument();
    expect(screen.getByText('七階段作業狀態')).toBeInTheDocument();
    expect(document.querySelectorAll('[data-surface-id^="order-tracker.settlement."]')).toHaveLength(3);

    fireEvent.click(screen.getByRole('tab', { name: /LINE 通知紀錄與發送狀態/ }));
    await waitFor(() => expect(screen.getByText('目前沒有 LINE 通知紀錄。')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /手動重發/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));

    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(summaryCountBeforeInteractions);
    expect(countPath(requests, STAGE_PROJECTION_ENDPOINT)).toBe(stageCountBeforeInteractions);
    expect(screen.queryByText(/發送成功|2026-08-16/)).not.toBeInTheDocument();
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('empty scope 與 typed unavailable 都維持明確狀態，不產生零計數或 fake success', async () => {
    authenticate();
    const emptyPage: OrderSummaryPage = {
      items: [],
      next_cursor: null,
      etag: 'b'.repeat(64),
    };
    const requests = installFetchStub({
      summaryBody: summaryEnvelope(emptyPage),
      stageBody: stageProjectionEnvelope(emptyPage),
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(screen.getByText('目前沒有訂單摘要。')).toBeInTheDocument());
    expect(document.querySelectorAll('[data-surface-id^="order-tracker.stage-count."]')).toHaveLength(7);
    expect(screen.getAllByText('0 筆案件')).toHaveLength(7);
    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(1);
    expect(countPath(requests, STAGE_PROJECTION_ENDPOINT)).toBe(1);
    expect(requests.every((request) => request.method === 'GET')).toBe(true);

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

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('訂單摘要服務暫時無法使用'));
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(screen.queryByText(/已成功載入|目前 loaded scope/)).not.toBeInTheDocument();
    expect(countPath(unavailableRequests, SUMMARY_ENDPOINT)).toBe(1);
    expect(countPath(unavailableRequests, STAGE_PROJECTION_ENDPOINT)).toBe(1);
    expect(unavailableRequests.every((request) => request.method === 'GET')).toBe(true);
  });

  it('重載時 abort 舊 generation，late stale response 不覆蓋最新 typed summary，且最多增加一次 GET', async () => {
    authenticate();
    const requests: FetchRecord[] = [];
    let summaryCalls = 0;
    let resolveFirst!: (response: Response) => void;
    let firstSignal: AbortSignal | undefined;
    const freshPage: OrderSummaryPage = {
      items: [realisticOrderSummaryPage.items[1]],
      next_cursor: null,
      etag: 'c'.repeat(64),
    };

    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const path = requestPath(input);
      requests.push({
        path,
        method: String(init?.method ?? 'GET').toUpperCase(),
        signal: init?.signal ?? undefined,
      });
      if (path === SYSTEM_STATUS_ENDPOINT) return jsonResponse(systemStatusEnvelope());
      if (path === STAGE_PROJECTION_ENDPOINT) {
        return jsonResponse(stageProjectionEnvelope(summaryCalls > 1 ? freshPage : realisticOrderSummaryPage));
      }
      if (path !== SUMMARY_ENDPOINT) throw new Error(`Unexpected API path: ${path}`);
      summaryCalls += 1;
      if (summaryCalls === 1) {
        firstSignal = init?.signal ?? undefined;
        return new Promise<Response>((resolve) => {
          resolveFirst = resolve;
        });
      }
      return jsonResponse(summaryEnvelope(freshPage));
    });

    render(
      <StrictMode>
        <App />
      </StrictMode>,
    );

    await waitFor(() => expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(1));
    fireEvent.click(screen.getByRole('button', { name: '重新載入摘要' }));

    await waitFor(() => expect(screen.getByText('ORD-2026-0802')).toBeInTheDocument());
    expect(firstSignal?.aborted).toBe(true);
    expect(countPath(requests, SUMMARY_ENDPOINT)).toBe(2);
    expect(countPath(requests, STAGE_PROJECTION_ENDPOINT)).toBe(2);

    resolveFirst(jsonResponse(summaryEnvelope(realisticOrderSummaryPage)));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(requests.every((request) => request.method === 'GET')).toBe(true);
  });
});
