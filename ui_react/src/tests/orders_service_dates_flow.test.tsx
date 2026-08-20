/**
 * File: orders_service_dates_flow.test.tsx
 * Description: 驗證 OrdersPage 服務日期確認工作流 (Query -> Select -> Preview -> Apply -> Receipt -> Re-query) 完整元件整合測試。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { OrdersPage } from '../pages/OrdersPage';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import {
  realisticServiceDateQueryView,
  realisticServiceDatePreviewView,
  realisticServiceDateReceiptView,
} from './fixtures/orders/order_mutation_contract_fixtures';
import {
  OrderMutationConflictError,
  ApiTimeoutError,
} from '../api/orders/order_mutation_errors';
import { realisticOrderDetail } from './fixtures/orders_real_data_fixtures';

describe('Confirmed Service Dates Component Flow Suite', () => {
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
          order_status: '確認實際服務日期',
          staff_name: '林月嬌',
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

    vi.spyOn(ordersQueryClient, 'getActualStart').mockReset().mockResolvedValue({
      case_no: 'ORD-2026-0801',
      planned_start_date: '2026-09-01',
      current_actual_start_date: null,
      service_data_locked: false,
      order_version: 1,
      scheduling_version: 1,
      scheduling_generation: 1,
      client_finance_version: 1,
      payroll_version: 1,
    });

    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockReset().mockResolvedValue({
      case_no: 'ORD-2026-0801',
      service_mode: '週休2日',
    });

    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockReset().mockResolvedValue(
      realisticOrderDetail
    );

    vi.spyOn(ordersMutationClient, 'getServiceDates').mockReset().mockResolvedValue(
      realisticServiceDateQueryView
    );
  });

  afterEach(() => {
    expect(globalThis.fetch).not.toHaveBeenCalled();
    globalThis.fetch = originalFetch;
  });

  it('1. 雙哨兵 (Sentinel) 驗證：不同伺服器回傳值驅動相異 DOM 渲染（非 hardcode）', async () => {
    // Sentinel A
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      case_no: 'ORD-2026-0801',
      contracted_service_days: 3,
      current_dates: ['2026-09-01'],
      current_version: 1,
    });

    const { unmount } = render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));

    await waitFor(() => {
      const metaRow = document.querySelector('.service-dates-meta-row')!;
      expect(metaRow).not.toBeNull();
      expect(metaRow).toHaveTextContent('合約服務天數：3 天');
      expect(metaRow).toHaveTextContent('目前確認版本：v1');
      expect(metaRow).toHaveTextContent('已確認日期：2026-09-01');
    });

    unmount();
    orderMutationFlowStore.clearAll();

    // Sentinel B (different case, days, version)
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({
      ...realisticServiceDateQueryView,
      case_no: 'ORD-2026-0801',
      contracted_service_days: 5,
      current_dates: ['2026-09-10', '2026-09-11'],
      current_version: 2,
    });

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));

    await waitFor(() => {
      const metaRow = document.querySelector('.service-dates-meta-row')!;
      expect(metaRow).not.toBeNull();
      expect(metaRow).toHaveTextContent('合約服務天數：5 天');
      expect(metaRow).toHaveTextContent('目前確認版本：v2');
      expect(metaRow).toHaveTextContent('已確認日期：2026-09-10, 2026-09-11');
    });
  });

  it('2. 完整服務日期變更流程：查詢 -> 選取 -> 預覽 -> 填寫原因 -> 套用 -> 重新查詢觀察', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates')
      .mockResolvedValueOnce(realisticServiceDateQueryView)
      .mockResolvedValueOnce({
        ...realisticServiceDateQueryView,
        current_version: 1,
        current_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      });

    const previewSpy = vi
      .spyOn(ordersMutationClient, 'previewServiceDates')
      .mockResolvedValue(realisticServiceDatePreviewView);

    const applySpy = vi
      .spyOn(ordersMutationClient, 'applyServiceDates')
      .mockResolvedValue(realisticServiceDateReceiptView);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));

    await waitFor(() => {
      expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument();
    });

    // 點擊帶入建議日期
    const suggestedBtn = screen.getByRole('button', { name: /帶入建議日期/ });
    fireEvent.click(suggestedBtn);

    // 預覽按鈕應為可點擊
    const previewBtn = document.querySelector(
      '[data-control-id="orders.date.service-date-preview"]'
    ) as HTMLButtonElement;
    expect(previewBtn).not.toBeDisabled();

    // 點擊預覽
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument();
      expect(screen.getByText(/第 1 週/)).toBeInTheDocument();
    });
    expect(previewSpy).toHaveBeenCalledTimes(1);

    // 填寫原因
    const reasonInput = document.querySelector('.mutation-reason-input') as HTMLTextAreaElement;
    fireEvent.change(reasonInput, { target: { value: '客戶確認服務日期無誤' } });

    // 點擊確認套用
    const applyBtn = document.querySelector(
      '[data-control-id="orders.date.service-date-apply"]'
    ) as HTMLButtonElement;
    expect(applyBtn).not.toBeDisabled();

    fireEvent.click(applyBtn);

    await waitFor(() => {
      expect(screen.getByText(/服務日期已確認成功/)).toBeInTheDocument();
    });

    expect(applySpy).toHaveBeenCalledTimes(1);
    const applyCallArgs = applySpy.mock.calls[0];
    expect(applyCallArgs[0]).toBe('ORD-2026-0801');
    expect(applyCallArgs[1].reason).toBe('客戶確認服務日期無誤');
    expect(applyCallArgs[2].idempotencyKey).toBeTruthy();
  });

  it('3. 草稿失效機制：產生預覽後若使用者更改日期，舊預覽立即失效且無法直接 Apply', async () => {
    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
      realisticServiceDatePreviewView
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /帶入建議日期/ }));
    const previewBtn = document.querySelector(
      '[data-control-id="orders.date.service-date-preview"]'
    ) as HTMLButtonElement;
    fireEvent.click(previewBtn);

    await waitFor(() => {
      expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument();
    });

    // 使用者取消勾選其中一天
    const chip = screen.getByRole('button', { name: '2026-09-01' });
    fireEvent.click(chip);

    // 預覽結果卡片與 Apply 按鈕應消失或不可見
    expect(screen.queryByText(/服務週次精算預覽/)).toBeNull();
    expect(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')
    ).toBeNull();
  });

  it('4. 409 Conflict Stale 處理：伺服器版本衝突時顯示過期提示並要求重新查詢', async () => {
    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
      realisticServiceDatePreviewView
    );
    vi.spyOn(ordersMutationClient, 'applyServiceDates').mockRejectedValue(
      new OrderMutationConflictError({
        code: 'service_date_confirmation_stale_version',
        message: '排程版本已過期，請重新查詢',
        status: 409,
      })
    );

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /帶入建議日期/ }));
    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-preview"]')!
    );

    await waitFor(() => expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument());

    const reasonInput = document.querySelector('.mutation-reason-input') as HTMLTextAreaElement;
    fireEvent.change(reasonInput, { target: { value: '原因說明' } });

    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')!
    );

    await waitFor(() => {
      expect(screen.getByText(/排程版本已過期，請重新查詢/)).toBeInTheDocument();
    });
  });

  it('5. Outcome Unknown 恢復：逾時時進入 outcome_unknown 並允許原 Key 原 Payload 重試', async () => {
    vi.spyOn(ordersMutationClient, 'getServiceDates')
      .mockResolvedValueOnce(realisticServiceDateQueryView)
      .mockResolvedValueOnce({
        ...realisticServiceDateQueryView,
        current_version: 1,
        current_dates: ['2026-09-01', '2026-09-02', '2026-09-03'],
      });

    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue(
      realisticServiceDatePreviewView
    );

    const applySpy = vi
      .spyOn(ordersMutationClient, 'applyServiceDates')
      .mockRejectedValueOnce(new ApiTimeoutError(5000))
      .mockResolvedValueOnce(realisticServiceDateReceiptView);

    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /帶入建議日期/ }));
    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-preview"]')!
    );

    await waitFor(() => expect(screen.getByText(/服務週次精算預覽/)).toBeInTheDocument());

    const reasonInput = document.querySelector('.mutation-reason-input') as HTMLTextAreaElement;
    fireEvent.change(reasonInput, { target: { value: '原因說明' } });

    fireEvent.click(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')!
    );

    // 出現 outcome_unknown 提示
    await waitFor(() => {
      expect(screen.getByText(/服務日期確認回應逾時或未明/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /重試提交/ })).toBeInTheDocument();
    });

    expect(reasonInput).toBeDisabled();
    expect(
      document.querySelector('[data-control-id="orders.date.service-date-apply"]')
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: '2026-09-01' })).toBeDisabled();

    const firstKey = applySpy.mock.calls[0][2].idempotencyKey;

    // 點擊重試
    fireEvent.click(screen.getByRole('button', { name: /重試提交/ }));

    await waitFor(() => {
      expect(screen.getByText(/服務日期已確認成功/)).toBeInTheDocument();
    });

    expect(applySpy).toHaveBeenCalledTimes(2);
    const secondKey = applySpy.mock.calls[1][2].idempotencyKey;
    expect(secondKey).toBe(firstKey);
  });

  it('6. 抽屜關閉後重開：Draft 與 Idempotency Key 保留在記憶體 Store 中不遺失', async () => {
    render(React.createElement(OrdersPage));
    await waitFor(() => expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument());

    // 開啟抽屜並選取日期
    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /帶入建議日期/ }));
    const draftBefore = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
    const keyBefore = draftBefore?.idempotencyKey;

    // 關閉抽屜
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));

    // 再次開啟抽屜
    fireEvent.click(screen.getByRole('button', { name: /📅 確認服務日期/ }));
    await waitFor(() => expect(screen.getByText(/正式服務日期確認/)).toBeInTheDocument());

    const draftAfter = orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801');
    expect(draftAfter?.selectedDates).toEqual(['2026-09-01', '2026-09-02', '2026-09-03']);
    expect(draftAfter?.idempotencyKey).toBe(keyBefore);
  });
});
