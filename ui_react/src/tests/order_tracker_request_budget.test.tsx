/**
 * File: order_tracker_request_budget.test.tsx
 * Description: 驗證 Tracker 摘要請求預算、明確重載、Abort／stale 與 Drawer 唯讀查詢。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { OrderSummaryPage } from '../api/orders/order_query_schemas';
import {
  getGovernmentSubsidyProjections,
  getTerminalAggregates,
  orderStageProjectionClient,
} from '../api/orders/order_stage_projection_client';
import type { GovernmentSubsidyProjectionPage } from '../api/orders/order_stage_projection_schemas';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { lineNotificationTimelineClient } from '../api/line/notification_timeline_client';
import { OrderTrackerPage } from '../pages/OrderTrackerPage';
import { realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

function governmentEnvelope(caseNo: string): unknown {
  return {
    success: true,
    message: '成功取得政府補助投影',
    data: {
      items: [{
        case_no: caseNo,
        substatus_code: 'pending_review',
        identity_status: null,
        source: { owner: 'Orders', identity: `subsidy:${caseNo}`, version: 3 },
        occurred_at: null,
        blockers: [{ code: 'review_required', message: '補助資格待人工覆核。' }],
        warnings: [],
        available_read_actions: [],
        claim_batch_id: null,
        claim_item_count: 0,
        claimed_hours: 0,
        unit_price_ntd: null,
        requested_amount_ntd: 0,
        approved_amount_ntd: 0,
        net_allocated_ntd: 0,
        overpayment_identity: null,
        overpayment_remaining_ntd: null,
      }],
      substatus_counts: {
        claim_lineage_missing: 0,
        draft: 0,
        submitted: 0,
        approved: 0,
        partially_paid: 0,
        paid: 0,
        pending_review: 1,
        offset_reserved: 0,
        offset_applied: 0,
        return_payable: 0,
        partially_returned: 0,
        returned: 0,
      },
      next_cursor: null,
      etag: 'a'.repeat(64),
    },
    error: null,
  };
}

function terminalEnvelope(caseNo: string): unknown {
  return {
    success: true,
    message: '成功取得結案彙總',
    data: {
      items: [{
        case_no: caseNo,
        applicable: true,
        fully_closed: false,
        components: Array.from({ length: 14 }, (_, index) => ({
          code: `terminal_component_${index + 1}`,
          owner: 'Client Finance',
          completed: index === 0,
          reason: index === 0 ? null : '尚未形成正式根事實',
        })),
      }],
      next_cursor: null,
    },
    error: null,
  };
}

describe('OrderTrackerPage request budget', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockRejectedValue(new Error('stage query fixture'));
    vi.spyOn(orderStageProjectionClient, 'getGovernmentSubsidyProjections').mockRejectedValue(new Error('government subsidy query fixture'));
    vi.spyOn(orderStageProjectionClient, 'getTerminalAggregates').mockRejectedValue(new Error('terminal aggregate query fixture'));
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockRejectedValue(new Error('card query fixture'));
    vi.spyOn(lineNotificationTimelineClient, 'query').mockResolvedValue({ case_no: 'ORD-2026-0801', records: [] });
  });

  it('uses one initial GET in StrictMode and local interactions add no request', async () => {
    const query = vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    render(<StrictMode><OrderTrackerPage /></StrictMode>);

    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    expect(query).toHaveBeenCalledTimes(1);
    const stageNav = document.querySelector(
      '[data-control-id="order-tracker.stage-nav.intake_terms"]'
    );
    expect(stageNav).not.toBeNull();
    fireEvent.click(stageNav as HTMLButtonElement);
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));
    fireEvent.click(screen.getByRole('tab', { name: /LINE 通知紀錄與發送狀態/ }));
    await waitFor(() => expect(screen.getByText('目前沒有 LINE 通知紀錄。')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /手動重發/ })).not.toBeInTheDocument();
    expect(query).toHaveBeenCalledTimes(1);
  });

  it('decodes the complete government and terminal server envelopes', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url, 'http://admin.test').pathname;
      const body = path === '/api/orders/government-subsidy-projections'
        ? governmentEnvelope('ORD-2026-0801')
        : terminalEnvelope('ORD-2026-0801');
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      const subsidy = await getGovernmentSubsidyProjections({ page_size: 200 });
      const terminal = await getTerminalAggregates({ page_size: 200 });
      expect(subsidy.items[0].substatus_code).toBe('pending_review');
      expect(subsidy.substatus_counts.pending_review).toBe(1);
      expect(terminal.items[0].fully_closed).toBe(false);
      expect(terminal.items[0].components).toHaveLength(14);
      expect(fetchMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it('uses server subsidy IDs and all-scope summaries when a subsidy filter is active', async () => {
    const summaryQuery = vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage),
    );
    vi.mocked(orderStageProjectionClient.getGovernmentSubsidyProjections).mockResolvedValue(
      (governmentEnvelope('ORD-2026-0802') as { data: GovernmentSubsidyProjectionPage }).data,
    );

    render(<OrderTrackerPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.change(screen.getByRole('combobox', { name: '補助狀態' }), {
      target: { value: 'pending_review' },
    });

    await waitFor(() => expect(summaryQuery).toHaveBeenLastCalledWith(
      { page_size: 200, lifecycle_scope: 'all' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(orderStageProjectionClient.getGovernmentSubsidyProjections).toHaveBeenLastCalledWith(
      { page_size: 200, substatus_code: 'pending_review' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    fireEvent.change(screen.getByRole('combobox', { name: '補助狀態' }), {
      target: { value: '__all__' },
    });
    await waitFor(() => expect(orderStageProjectionClient.getGovernmentSubsidyProjections).toHaveBeenLastCalledWith(
      { page_size: 200 },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it('aborts the prior generation on explicit reload and discards a stale response', async () => {
    let resolveFirst: ((page: OrderSummaryPage) => void) | undefined;
    let firstSignal: AbortSignal | undefined;
    const freshPage: OrderSummaryPage = {
      items: [realisticOrderSummaryPage.items[1]],
      next_cursor: null,
      etag: 'c'.repeat(64),
    };
    const query = vi.spyOn(ordersQueryClient, 'getOrderSummaries')
      .mockImplementationOnce((_params, options) => new Promise((resolve) => {
        firstSignal = options?.signal;
        resolveFirst = resolve;
      }))
      .mockResolvedValueOnce(freshPage);

    render(<OrderTrackerPage />);
    await waitFor(() => expect(query).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '重新載入摘要' }));

    await waitFor(() => expect(screen.getByText('ORD-2026-0802')).toBeInTheDocument());
    expect(firstSignal?.aborted).toBe(true);
    resolveFirst?.(realisticOrderSummaryPage);
    await Promise.resolve();
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('presents a query failure and each explicit retry costs one request', async () => {
    const query = vi.spyOn(ordersQueryClient, 'getOrderSummaries')
      .mockRejectedValueOnce(new Error('typed orders failure'))
      .mockResolvedValueOnce(realisticOrderSummaryPage);
    render(<OrderTrackerPage />);

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('typed orders failure'));
    expect(document.body.textContent).not.toContain('訂單清單載入未完成，請稍後重新載入摘要。');
    expect(query).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '重新載入摘要' }));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    expect(query).toHaveBeenCalledTimes(2);
  });
});
