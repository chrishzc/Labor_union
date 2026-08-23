/**
 * File: orders_preview_action_race_guards.test.tsx
 * Description: 驗證Orders Preview POST在close／selection change後中止且不污染flow store。
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { OrdersPage } from '../pages/OrdersPage';
import {
  realisticActualStart,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
} from './fixtures/orders_real_data_fixtures';
import {
  realisticOrderReopenPreviewView,
  realisticServiceDatePreviewView,
  realisticServiceDateQueryView,
} from './fixtures/orders/order_mutation_contract_fixtures';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

const OPERABLE_CASE_NO = 'ORD-2026-0802';

function operableOrderCard(): HTMLElement {
  const card = screen.getByText(OPERABLE_CASE_NO).closest<HTMLElement>('.order-card');
  if (!card) throw new Error(`找不到 ${OPERABLE_CASE_NO} 訂單卡片。`);
  return card;
}

describe('Orders Preview action race guards', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue(realisticOrderDetail);
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue(realisticOrderCalendarDetail);
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue({ ...realisticActualStart, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue({ ...realisticServiceDateQueryView, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersMutationClient, 'previewServiceDates').mockResolvedValue({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
    vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValue({ ...realisticOrderReopenPreviewView, case_no: OPERABLE_CASE_NO });
  });

  afterEach(() => {
    cleanup();
    orderMutationFlowStore.clearAll();
    vi.restoreAllMocks();
  });

  async function openServiceDates(): Promise<void> {
    render(<OrdersPage />);
    await screen.findByText(OPERABLE_CASE_NO);
    fireEvent.click(within(operableOrderCard()).getByRole('button', { name: /確認服務日期/ }));
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledTimes(1));
    await screen.findByRole('button', { name: '預覽正式服務日期' });
  }

  it('aborts Service Dates Preview on drawer close and discards the late response', async () => {
    const pending = deferred<typeof realisticServiceDatePreviewView>();
    vi.mocked(ordersMutationClient.previewServiceDates).mockReturnValueOnce(pending.promise);
    await openServiceDates();

    fireEvent.click(screen.getByRole('button', { name: '預覽正式服務日期' }));
    await waitFor(() => expect(ordersMutationClient.previewServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewServiceDates).mock.calls[0]?.[2]?.signal;
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    const draft = orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO);
    expect(draft?.previewView).toBeNull();
    expect(draft?.status).not.toBe('preview_ready');
  });

  it('aborts Service Dates Preview when the selected dates change', async () => {
    const pending = deferred<typeof realisticServiceDatePreviewView>();
    vi.mocked(ordersMutationClient.previewServiceDates).mockReturnValueOnce(pending.promise);
    await openServiceDates();

    fireEvent.click(screen.getByRole('button', { name: '預覽正式服務日期' }));
    await waitFor(() => expect(ordersMutationClient.previewServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewServiceDates).mock.calls[0]?.[2]?.signal;
    fireEvent.click(screen.getAllByRole('button', { name: realisticServiceDateQueryView.selectable_dates[0] })[0]);
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    expect(orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO)?.status).toBe('draft_changed');
  });

  it('keeps Service Dates Preview alive when suggested dates equal the current selection', async () => {
    const pending = deferred<typeof realisticServiceDatePreviewView>();
    vi.mocked(ordersMutationClient.previewServiceDates).mockReturnValueOnce(pending.promise);
    await openServiceDates();

    fireEvent.click(screen.getByRole('button', { name: '預覽正式服務日期' }));
    await waitFor(() => expect(ordersMutationClient.previewServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewServiceDates).mock.calls[0]?.[2]?.signal;
    fireEvent.click(screen.getByRole('button', { name: '帶入建議日期' }));
    expect(signal?.aborted).toBe(false);

    await act(async () => {
      pending.resolve({ ...realisticServiceDatePreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    expect(orderMutationFlowStore.getServiceDatesDraft(OPERABLE_CASE_NO)?.status).toBe('preview_ready');
  });

  it('aborts Controlled Reopen Preview on modal close and keeps the draft closed', async () => {
    const pending = deferred<typeof realisticOrderReopenPreviewView>();
    vi.mocked(ordersMutationClient.previewReopen).mockReturnValueOnce(pending.promise);
    render(<OrdersPage />);
    await screen.findByText(OPERABLE_CASE_NO);

    fireEvent.click(within(operableOrderCard()).getByRole('button', { name: /重啟訂單/ }));
    await waitFor(() => expect(ordersMutationClient.previewReopen).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.previewReopen).mock.calls[0]?.[1]?.signal;
    fireEvent.click(screen.getByRole('button', { name: '關閉' }));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      pending.resolve({ ...realisticOrderReopenPreviewView, case_no: OPERABLE_CASE_NO });
      await Promise.resolve();
    });
    const draft = orderMutationFlowStore.getReopenDraft(OPERABLE_CASE_NO);
    expect(draft?.status).toBe('closed');
    expect(draft?.previewView).toBeNull();
  });
});
