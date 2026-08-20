/**
 * File: order_tracker_request_budget.test.tsx
 * Description: 驗證 Tracker 初始單一GET、明確重載、Abort／stale防護及所有本地操作零額外請求。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import type { OrderSummaryPage } from '../api/orders/order_query_schemas';
import { OrderTrackerPage } from '../pages/OrderTrackerPage';
import { realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';

describe('OrderTrackerPage request budget', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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
    fireEvent.click(screen.getByRole('button', { name: '手動重發（未開放）' }));
    expect(query).toHaveBeenCalledTimes(1);
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
    expect(query).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '重新載入摘要' }));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    expect(query).toHaveBeenCalledTimes(2);
  });
});
