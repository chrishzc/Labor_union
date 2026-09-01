/**
 * File: challenger_g5_adversarial_suite.test.tsx
 * Description: 對 OrdersPage 競態、壞契約、request budget 與 unavailable 行為做對抗驗證。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { orderCancellationClient } from '../api/orders/order_cancellation_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
import { ApiHttpError } from '../api/shared/typed_errors';
import { OrdersPage } from '../pages/OrdersPage';
import type { OrdersCardProjection } from '../api/orders/order_card_projection_schemas';
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
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

function unavailableCardProjection(caseNo: string): OrdersCardProjection {
  const field = <T,>(owner: string, value: T | null = null) => ({
    value,
    owner,
    source_identity: `fixture:${caseNo}:${owner}`,
    source_version: '1',
    availability: value === null ? 'unavailable' as const : 'available' as const,
    availability_reason: value === null ? 'fixture_root_fact_missing' : null,
  });
  return {
    case_no: caseNo,
    contact_phone: field<string>('Client'),
    contact_address: field<string>('Client'),
    requires_cooking: field<boolean>('Orders'),
    floor_fee_ntd: field<number>('Orders'),
    deposit_amount_ntd: field<number>('Client Finance'),
    deposit_settlement_state: field<'unsettled' | 'settled'>('Client Finance'),
    deposit_settled_on: field<string>('Client Finance'),
    actual_start_date: field<string>('Orders'),
    actual_end_date: field<string>('Orders'),
    assignment_segments: field<[]>( 'Scheduling', []),
  };
}

const operableSummaryPage = {
  ...realisticOrderSummaryPage,
  items: realisticOrderSummaryPage.items.map((item, index) => index === 0 ? { ...item, order_status: '洽談中' } : item),
};

function orderCard(caseNo: string): HTMLElement {
  const card = screen.getByText(caseNo).closest<HTMLElement>('.order-card');
  if (!card) throw new Error(`找不到 ${caseNo} 訂單卡片。`);
  return card;
}

describe('G5 OrdersPage adversarial suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(operableSummaryPage);
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
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockImplementation(async (caseNo) => ({
      ...realisticContractCompletion,
      case_no: caseNo,
    }));
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue(realisticAssignmentPlan);
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);
    vi.spyOn(candidateContactPoolClient, 'query').mockImplementation(async (caseNo) => ({
      pool_id: null,
      case_no: caseNo,
      candidates: [],
    }));
    vi.spyOn(contractSigningClient, 'query').mockImplementation(async (caseNo) => ({
      case_no: caseNo,
      staff_segments: [{ segment_id: 1, staff_id: 101, sent: true, signed_received: true }],
      commitment_id: 1,
      client_document_sent: true,
      client_signed_received: true,
      contract_identity: `CONTRACT-${caseNo}`,
      documents: [],
    }));
    vi.spyOn(waitingDepositLockClient, 'queryPlan').mockRejectedValue(
      new ApiHttpError(404, 'HTTP_404', 'active matching plan not found'),
    );
    vi.spyOn(orderCancellationClient, 'query').mockImplementation(async (caseNo) => ({
      case_no: caseNo,
      lifecycle_status: '訂單成立',
      actual_start_date: null,
      contracted_service_days: 30,
      service_hours_per_day: 8,
      service_started: false,
      historical_mid_service_confirmation_available: false,
      service_data_locked: false,
      order_version: 0,
      scheduling_version: 0,
      scheduling_generation: 0,
      client_finance_version: 0,
      payroll_version: 0,
      confirmed_service_days: [],
      caregiver_options: [],
    }));
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(operableSummaryPage)
    );
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockImplementation(async (caseNo) => unavailableCardProjection(caseNo));
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
    await act(async () => {
      fireEvent.click(within(orderCard('ORD-2026-0801')).getByRole('button', { name: /媒合與正式排班/ }));
    });
    await act(async () => {
      fireEvent.click(within(orderCard('ORD-2026-0802')).getByRole('button', { name: /媒合與正式排班/ }));
    });
    await act(async () => {
      second.resolve({
        ...realisticAssignmentPlan,
        case_no: 'ORD-2026-0802',
        assignments: [{ ...realisticAssignmentPlan.assignments[0], staff_id: 222 }],
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    const staff222Elements = await screen.findAllByText(/Staff #222/);
    expect(staff222Elements.length).toBeGreaterThanOrEqual(1);
    await act(async () => {
      first.resolve({
        ...realisticAssignmentPlan,
        case_no: 'ORD-2026-0801',
        assignments: [{ ...realisticAssignmentPlan.assignments[0], staff_id: 111 }],
      });
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => Promise.resolve());
    expect(screen.queryAllByText(/Staff #111/)).toHaveLength(0);
    expect(screen.getAllByText(/Staff #222/).length).toBeGreaterThanOrEqual(1);
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
    await act(async () => {
      fireEvent.click(within(orderCard('ORD-2026-0801')).getByRole('button', { name: /條款與契約/ }));
    });
    await act(async () => {
      fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    });
    await waitFor(() => expect(orderCancellationClient.query).toHaveBeenCalledOnce());
    expect(screen.queryByText(/全額退還/)).not.toBeInTheDocument();
    expect(screen.queryByText(/已勾選推薦此履歷/)).not.toBeInTheDocument();
    expect(screen.queryByText(/後端.*提供|未開放|未納入/)).not.toBeInTheDocument();
  });
});
