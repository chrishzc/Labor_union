/**
 * File: challenger_g5_adversarial_suite.test.tsx
 * Description: 對 OrdersPage 競態、壞契約、request budget 與 unavailable 行為做對抗驗證。
 */
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

describe('G5 OrdersPage adversarial suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue(realisticOrderDetail);
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue(realisticOrderCalendarDetail);
    vi.spyOn(ordersQueryClient, 'getOrderTerms').mockResolvedValue(realisticOrderTerms);
    vi.spyOn(ordersQueryClient, 'getFormManagementContext').mockResolvedValue({
      case_no: 'ORD-2026-0801', service_time: null, service_type: null,
      delivery_type: null, residence_type: null, city: null, identity_status: null,
    });
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue(realisticActualStart);
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockResolvedValue(realisticContractCompletion);
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue(realisticAssignmentPlan);
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);
  });

  it('discards a stale matching assignment response after fast case switching', async () => {
    const first = deferred<typeof realisticAssignmentPlan>();
    const second = deferred<typeof realisticAssignmentPlan>();
    vi.mocked(ordersQueryClient.getAssignmentPlan)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    vi.mocked(ordersQueryClient.getOrderDetail).mockImplementation(async (caseNo) => ({
      ...realisticOrderDetail,
      case_no: caseNo,
    }));
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    const buttons = screen.getAllByRole('button', { name: /媒合與正式排班/ });
    await act(async () => fireEvent.click(buttons[0]));
    await act(async () => fireEvent.click(buttons[1]));
    second.resolve({
      ...realisticAssignmentPlan,
      case_no: 'ORD-2026-0802',
      assignments: [{ ...realisticAssignmentPlan.assignments[0], staff_id: 222 }],
    });
    await screen.findByText(/Staff #222/);
    first.resolve({
      ...realisticAssignmentPlan,
      assignments: [{ ...realisticAssignmentPlan.assignments[0], staff_id: 111 }],
    });
    await act(async () => Promise.resolve());
    expect(screen.queryByText(/Staff #111/)).not.toBeInTheDocument();
    expect(screen.getByText(/Staff #222/)).toBeInTheDocument();
  });

  it('keeps one summary request on initial mount', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledOnce();
  });

  it('shows a contract failure instead of partial cards when decode rejects', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockRejectedValueOnce(
      new Error('回應信封結構驗證失敗: [data.items.0.case_no] Required')
    );
    render(<OrdersPage />);
    expect(await screen.findByText(/載入訂單資料失敗/)).toHaveTextContent('回應信封結構驗證失敗');
    expect(screen.queryByText('ORD-2026-0801')).not.toBeInTheDocument();
  });

  it('never renders inferred refund or recommendation success in unavailable slots', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /取消試算/ })[0]));
    expect(screen.queryByText(/全額退還/)).not.toBeInTheDocument();
    expect(screen.queryByText(/已勾選推薦此履歷/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/後端尚未提供 typed projection/).length).toBeGreaterThan(0);
  });
});
