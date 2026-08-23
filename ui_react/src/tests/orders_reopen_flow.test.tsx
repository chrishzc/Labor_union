/**
 * File: orders_reopen_flow.test.tsx
 * Description: 驗證 OrdersPage 受控重開工作流 (Click -> Preview -> Reason -> Apply -> Requery) 完整元件整合測試。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { OrdersPage } from '../pages/OrdersPage';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  realisticOrderReopenPreviewView,
  realisticOrderReopenReceiptView,
} from './fixtures/orders/order_mutation_contract_fixtures';
import { realisticOrderDetail, realisticOrderSummaryPage } from './fixtures/orders_real_data_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';
import {
  OrderMutationDomainBlockedError,
  ApiTimeoutError,
} from '../api/orders/order_mutation_errors';

describe('Controlled Order Reopen Component Flow Suite', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
    orderMutationFlowStore.clearAll();
    globalThis.fetch = vi.fn(async (input) => {
      throw new Error(`Unexpected network request: ${String(input)}`);
    }) as typeof fetch;

    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockReset().mockResolvedValue({
      items: [
        {
          case_no: 'ORD-2026-0801',
          client_name: '陳雅婷',
          order_status: '已取消',
          staff_name: null,
          identity_status: null,
          start_date: '2026-09-01',
          end_date: '2026-09-30',
          actual_start_date: null,
          actual_end_date: null,
          service_days: 30,
          total_employer_self_pay_payable: 90000,
        },
      ],
      next_cursor: null,
      etag: 'a'.repeat(64),
    });
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockReset().mockResolvedValue(
      realisticOrderDetail
    );
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage),
    );
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockRejectedValue(
      new Error('Card projection intentionally unavailable in reopen flow fixture'),
    );
  });

  afterEach(() => {
    expect(globalThis.fetch).not.toHaveBeenCalled();
    globalThis.fetch = originalFetch;
  });

  it('1. 雙哨兵 (Sentinel) 驗證：不同伺服器預覽資料驅動相異 DOM 渲染（非 hardcode）', async () => {
    // Sentinel A
    vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValueOnce({
      ...realisticOrderReopenPreviewView,
      case_no: 'ORD-2026-0801',
      after_status: '訂單成立',
      order_version: 7,
    });

    const { unmount } = render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    const reopenCardBtn = screen.getByRole('button', { name: /🔄 重啟訂單/ });
    fireEvent.click(reopenCardBtn);

    await waitFor(() => {
      const modal = document.querySelector('[data-surface-id="orders.modal.reopen"]')!;
      expect(modal).not.toBeNull();
      expect(modal).toHaveTextContent('訂單成立');
      expect(modal).toHaveTextContent('Order v7');
      expect(modal).toHaveTextContent('requires_fresh_scheduling_preview');
    });

    unmount();
    orderMutationFlowStore.clearAll();

    // Sentinel B
    vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValueOnce({
      ...realisticOrderReopenPreviewView,
      case_no: 'ORD-2026-0801',
      after_status: '服務中',
      order_version: 12,
    });

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /🔄 重啟訂單/ }));

    await waitFor(() => {
      const modal = document.querySelector('[data-surface-id="orders.modal.reopen"]')!;
      expect(modal).not.toBeNull();
      expect(modal).toHaveTextContent('服務中');
      expect(modal).toHaveTextContent('Order v12');
    });
  });

  it('2. 完整受控重開流程：點擊卡片重開 -> 取得預覽 -> 填寫原因 -> 套用重開 -> 刷新摘要清單', async () => {
    const previewSpy = vi
      .spyOn(ordersMutationClient, 'previewReopen')
      .mockResolvedValue(realisticOrderReopenPreviewView);

    const applySpy = vi
      .spyOn(ordersMutationClient, 'applyReopen')
      .mockResolvedValue(realisticOrderReopenReceiptView);

    const summarySpy = vi
      .spyOn(ordersQueryClient, 'getOrderSummaries')
      .mockResolvedValue({
        items: [
          {
            case_no: 'ORD-2026-0801',
            client_name: '陳雅婷',
            order_status: '進件與補件',
            staff_name: null,
            identity_status: null,
            start_date: '2026-09-01',
            end_date: '2026-09-30',
            actual_start_date: null,
            actual_end_date: null,
            service_days: 30,
            total_employer_self_pay_payable: 90000,
          },
        ],
        next_cursor: null,
        etag: 'a'.repeat(64),
      });

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    const reopenCardBtn = screen.getByRole('button', { name: /🔄 重啟訂單/ });
    fireEvent.click(reopenCardBtn);

    await waitFor(() => {
      expect(screen.getByText(/訂單受控重開 — ORD-2026-0801/)).toBeInTheDocument();
    });
    expect(previewSpy).toHaveBeenCalledTimes(1);

    // Apply 按鈕在原因填寫前應為 disabled
    const applyBtn = document.querySelector(
      '[data-control-id="orders.reopen.apply"]'
    ) as HTMLButtonElement;
    expect(applyBtn).toBeDisabled();

    // 填寫原因
    const reasonInput = document.querySelector(
      '[data-control-id="orders.reopen.reason"]'
    ) as HTMLTextAreaElement;
    fireEvent.change(reasonInput, { target: { value: '客戶來電確認恢復月嫂服務' } });

    expect(applyBtn).not.toBeDisabled();

    // 點擊確認重開
    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(screen.getByText(/訂單已成功重開/)).toBeInTheDocument();
    });

    expect(applySpy).toHaveBeenCalledTimes(1);
    expect(summarySpy).toHaveBeenCalledTimes(2); // 初始載入 + Apply 成功後 re-query
  });

  it('3. Domain Blocked 處理：訂單已有款項結清時，顯示伺服器領域阻擋訊息與 correlation id', async () => {
    vi.spyOn(ordersMutationClient, 'previewReopen').mockRejectedValue(
      new OrderMutationDomainBlockedError({
        code: 'order_reopen_financial_history_exists',
        message: '訂單已有款項結清紀錄，禁止直接重開',
        correlationId: 'corr-reopen-block-001',
        domainBlockers: ['order_reopen_financial_history_exists'],
        status: 409,
      })
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    const reopenCardBtn = screen.getByRole('button', { name: /🔄 重啟訂單/ });
    fireEvent.click(reopenCardBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/訂單已有款項結清紀錄，禁止直接重開/)
      ).toBeInTheDocument();
      expect(screen.getByText(/ID: corr-reopen-block-001/)).toBeInTheDocument();
      expect(screen.getByText(/order_reopen_financial_history_exists/)).toBeInTheDocument();
    });

    // 此時不應出現 Apply 按鈕
    expect(document.querySelector('[data-control-id="orders.reopen.apply"]')).toBeNull();
  });

  it('4. Outcome Unknown 恢復：重開 Apply 逾時進入 outcome_unknown 並允許重試', async () => {
    vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValue(
      realisticOrderReopenPreviewView
    );

    const applySpy = vi
      .spyOn(ordersMutationClient, 'applyReopen')
      .mockRejectedValueOnce(new ApiTimeoutError(5000))
      .mockResolvedValueOnce(realisticOrderReopenReceiptView);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /🔄 重啟訂單/ }));
    await waitFor(() =>
      expect(screen.getByText(/訂單受控重開 — ORD-2026-0801/)).toBeInTheDocument()
    );

    const reasonInput = document.querySelector(
      '[data-control-id="orders.reopen.reason"]'
    ) as HTMLTextAreaElement;
    fireEvent.change(reasonInput, { target: { value: '客戶恢復需求' } });

    const applyBtn = document.querySelector(
      '[data-control-id="orders.reopen.apply"]'
    ) as HTMLButtonElement;
    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(screen.getByText(/訂單重開回應逾時或未明/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /重試重開/ })).toBeInTheDocument();
    });

    expect(reasonInput).toBeDisabled();
    expect(applyBtn).toBeDisabled();

    const firstKey = applySpy.mock.calls[0][2].idempotencyKey;

    // 點擊重試
    fireEvent.click(screen.getByRole('button', { name: /重試重開/ }));

    await waitFor(() => {
      expect(screen.getByText(/訂單已成功重開/)).toBeInTheDocument();
    });

    expect(applySpy).toHaveBeenCalledTimes(2);
    const secondKey = applySpy.mock.calls[1][2].idempotencyKey;
    expect(secondKey).toBe(firstKey);
  });
});
