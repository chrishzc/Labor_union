/**
 * File: orders_query_request_lifecycle.test.tsx
 * Description: 驗證Orders summary與drawer查詢在close／unmount後中止且不寫回過期結果。
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { OrdersPage } from '../pages/OrdersPage';
import {
  realisticActualStart,
  realisticAssignmentPlan,
  realisticContractCompletion,
  realisticOrderCalendarDetail,
  realisticOrderDetail,
  realisticOrderSummaryPage,
  realisticOrderTerms,
} from './fixtures/orders_real_data_fixtures';
import { realisticServiceDateQueryView } from './fixtures/orders/order_mutation_contract_fixtures';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

describe('Orders query request lifecycle', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue(realisticOrderDetail);
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue(realisticOrderCalendarDetail);
    vi.spyOn(ordersQueryClient, 'getOrderTerms').mockResolvedValue(realisticOrderTerms);
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue(realisticActualStart);
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockResolvedValue(realisticContractCompletion);
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue(realisticAssignmentPlan);
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);
  });

  afterEach(() => {
    cleanup();
    orderMutationFlowStore.clearAll();
    vi.restoreAllMocks();
  });

  it('starts one StrictMode summary request and aborts it on unmount', async () => {
    const pending = deferred<typeof realisticOrderSummaryPage>();
    vi.mocked(ordersQueryClient.getOrderSummaries).mockReturnValueOnce(pending.promise);
    render(<StrictMode><OrdersPage /></StrictMode>);
    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersQueryClient.getOrderSummaries).mock.calls[0]?.[1]?.signal;

    cleanup();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      pending.resolve(realisticOrderSummaryPage);
      await Promise.resolve();
    });
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
  });

  it('aborts matching drawer GETs when the drawer closes and discards late results', async () => {
    const detail = deferred<typeof realisticOrderDetail>();
    const assignment = deferred<typeof realisticAssignmentPlan>();
    vi.mocked(ordersQueryClient.getOrderDetail).mockReturnValueOnce(detail.promise);
    vi.mocked(ordersQueryClient.getAssignmentPlan).mockReturnValueOnce(assignment.promise);
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');

    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    await waitFor(() => expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledTimes(1));
    const detailSignal = vi.mocked(ordersQueryClient.getOrderDetail).mock.calls[0]?.[1]?.signal;
    const assignmentSignal = vi.mocked(ordersQueryClient.getAssignmentPlan).mock.calls[0]?.[1]?.signal;
    fireEvent.click(screen.getByRole('button', { name: '關閉工作台' }));

    expect(detailSignal?.aborted).toBe(true);
    expect(assignmentSignal?.aborted).toBe(true);
    await act(async () => {
      detail.resolve(realisticOrderDetail);
      assignment.resolve(realisticAssignmentPlan);
      await Promise.resolve();
    });
    expect(screen.queryByText('正式執行排班（非候選推薦）')).not.toBeInTheDocument();
  });

  it('aborts Service Dates GET without converting cancellation into a typed business error', async () => {
    const serviceDates = deferred<typeof realisticServiceDateQueryView>();
    vi.mocked(ordersMutationClient.getServiceDates).mockReturnValueOnce(serviceDates.promise);
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');

    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    const calendarTab = await screen.findByRole('button', { name: /實質服務日曆/ });
    fireEvent.click(calendarTab);
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(ordersMutationClient.getServiceDates).mock.calls[0]?.[1]?.signal;
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      serviceDates.reject(new Error('aborted transport'));
      await Promise.resolve();
    });
    expect(orderMutationFlowStore.getServiceDatesDraft('ORD-2026-0801')?.status).not.toBe('typed_error');
  });
});
