/**
 * File: challenger_g5_adversarial_suite.test.tsx
 * Description: 對 OrdersPage 競態、壞契約、request budget 與 unavailable 行為做對抗驗證。
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { orderCancellationClient } from '../api/orders/order_cancellation_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
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

function orderCard(caseNo: string): HTMLElement {
  const card = screen.getByText(caseNo).closest<HTMLElement>('.order-card');
  if (!card) throw new Error(`找不到 ${caseNo} 訂單卡片。`);
  return card;
}

describe('G5 OrdersPage adversarial suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue(realisticOrderDetail);
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue(realisticOrderCalendarDetail);
    vi.spyOn(ordersQueryClient, 'getOrderTerms').mockImplementation(async (caseNo) => ({
      ...realisticOrderTerms,
      case_no: caseNo,
    }));
    vi.spyOn(ordersQueryClient, 'getFormManagementContext').mockResolvedValue({
      case_no: 'ORD-2026-0801', service_time: null, service_type: null,
      delivery_type: null, residence_type: null, city: null, identity_status: null,
    });
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue(realisticActualStart);
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockResolvedValue(realisticContractCompletion);
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue(realisticAssignmentPlan);
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);
    vi.spyOn(candidateContactPoolClient, 'query').mockImplementation(async (caseNo) => ({
      pool_id: null,
      case_no: caseNo,
      candidates: [],
    }));
    vi.spyOn(waitingDepositLockClient, 'queryPlan').mockResolvedValue({
      planId: 701,
      status: 'proposed',
      activeLockId: null,
    });
    vi.spyOn(orderCancellationClient, 'query').mockImplementation(async (caseNo) => ({
      case_no: caseNo,
      lifecycle_status: '訂單成立',
      actual_start_date: null,
      contracted_service_days: 30,
      service_hours_per_day: 8,
      service_started: false,
      service_data_locked: false,
      order_version: 0,
      scheduling_version: 0,
      scheduling_generation: 0,
      client_finance_version: 0,
      payroll_version: 0,
      confirmed_service_days: [],
      caregiver_options: [],
    }));
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
    await act(async () => fireEvent.click(within(orderCard('ORD-2026-0802')).getByRole('button', { name: /媒合與正式排班/ })));
    await act(async () => fireEvent.click(within(orderCard('ORD-2026-0803')).getByRole('button', { name: /媒合與正式排班/ })));
    second.resolve({
      ...realisticAssignmentPlan,
      case_no: 'ORD-2026-0803',
      assignments: [{ ...realisticAssignmentPlan.assignments[0], staff_id: 222 }],
    });
    await screen.findByText(/Staff #222/);
    first.resolve({
      ...realisticAssignmentPlan,
      case_no: 'ORD-2026-0802',
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
    expect(await screen.findByText('取消前根事實')).toBeInTheDocument();
    expect(screen.queryByText(/全額退還/)).not.toBeInTheDocument();
    expect(screen.queryByText(/已勾選推薦此履歷/)).not.toBeInTheDocument();
    expect(screen.queryByText(/後端.*提供|未開放|未納入/)).not.toBeInTheDocument();
  });
});
