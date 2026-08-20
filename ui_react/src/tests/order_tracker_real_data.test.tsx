/**
 * File: order_tracker_real_data.test.tsx
 * Description: 驗證 Tracker 保留七階與雙Tab，並將真實摘要、SOP、LINE及結清缺口誠實呈現。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { OrderTrackerPage } from '../pages/OrderTrackerPage';
import { realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';

function surface(prefix: string): HTMLElement[] {
  return Array.from(document.querySelectorAll(`[data-surface-id^="${prefix}"]`));
}

describe('OrderTrackerPage query-only presentation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
  });

  it('renders seven unavailable stage slots and keeps summaries in a separate unclassified region', async () => {
    render(<OrderTrackerPage />);
    await waitFor(() => expect(screen.getByText('待後端階段投影')).toBeInTheDocument());

    expect(surface('order-tracker.stage-slot.')).toHaveLength(7);
    expect(surface('order-tracker.stage-count.')).toHaveLength(7);
    expect(surface('order-tracker.stage-unavailable.')).toHaveLength(7);
    expect(screen.getAllByText('後端尚未提供 typed stage projection')).toHaveLength(7);
    expect(screen.queryByText(/目前無案件停留於此階段/)).not.toBeInTheDocument();
    expect(screen.queryByText(/1 筆案件/)).not.toBeInTheDocument();
    expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument();
    expect(screen.getAllByText('原始訂單狀態（非七階段）')).toHaveLength(
      realisticOrderSummaryPage.items.length
    );
  });

  it('keeps eleven unavailable SOP labels, LINE unavailable and three settlement owners visible', async () => {
    render(<OrderTrackerPage />);
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /查看訂單 ORD-2026-0801/ }));

    expect(surface('order-tracker.sop.step.')).toHaveLength(11);
    expect(screen.getAllByText('後端尚未提供此步驟的 typed root-fact lineage')).toHaveLength(11);
    expect(screen.getAllByText('狀態 — 時間 —')).toHaveLength(11);
    expect(surface('order-tracker.settlement.')).toHaveLength(3);
    expect(screen.getByText('服務完成')).toBeInTheDocument();
    expect(screen.getByText('客戶款項結清')).toBeInTheDocument();
    expect(screen.getByText('月嫂薪資核銷')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /LINE 通知紀錄與發送狀態/ }));
    expect(screen.getByText('後端尚未提供此訂單的 case-scoped LINE timeline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '手動重發（未開放）' })).toBeDisabled();
    expect(screen.queryByText(/發送成功/)).not.toBeInTheDocument();
    expect(screen.queryByText(/2026-08-16/)).not.toBeInTheDocument();
  });

  it('shows an honest loaded-scope empty state without turning stage slots into zero counts', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [],
      next_cursor: null,
      etag: 'b'.repeat(64),
    });
    render(<OrderTrackerPage />);

    await waitFor(() => expect(screen.getByText(/目前 loaded scope 沒有訂單摘要/)).toBeInTheDocument());
    expect(surface('order-tracker.stage-count.')).toHaveLength(7);
    expect(screen.queryByText(/0 筆案件/)).not.toBeInTheDocument();
  });
});
