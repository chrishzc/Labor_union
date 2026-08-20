/**
 * File: orders_page_real_data.test.tsx
 * Description: 驗證 OrdersPage 真實 query、request budget、unavailable slots 與四 Drawer。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { sessionClient } from '../api/auth/session_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { transport } from '../api/shared/transport';
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

describe('OrdersPage query real-data slice', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(realisticOrderSummaryPage);
    vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue(realisticOrderDetail);
    vi.spyOn(ordersQueryClient, 'getOrderCalendarDetail').mockResolvedValue(realisticOrderCalendarDetail);
    vi.spyOn(ordersQueryClient, 'getOrderTerms').mockResolvedValue(realisticOrderTerms);
    vi.spyOn(ordersQueryClient, 'getFormManagementContext').mockResolvedValue({
      case_no: 'ORD-2026-0801',
      service_time: null,
      service_type: null,
      delivery_type: null,
      residence_type: null,
      city: null,
      identity_status: null,
    });
    vi.spyOn(ordersQueryClient, 'getActualStart').mockResolvedValue(realisticActualStart);
    vi.spyOn(ordersQueryClient, 'getContractCompletion').mockResolvedValue(realisticContractCompletion);
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue(realisticAssignmentPlan);
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);
  });

  it('renders raw server statuses and disables unsupported seven-stage filters', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    expect(screen.getAllByText('伺服器狀態：待補件').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /全部 \(7\)/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /1\. 進件與補件 \(—\)/ })).toBeDisabled();
    expect(screen.getAllByText(/後端尚未提供 typed projection/).length).toBeGreaterThan(0);
  });

  it('deduplicates the StrictMode initial summary load to one transport request', async () => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('strict-mode-token');
    const get = vi.spyOn(transport, 'get').mockResolvedValue({
      success: true,
      message: 'Success',
      data: realisticOrderSummaryPage,
      error: null,
    });
    render(<StrictMode><OrdersPage /></StrictMode>);
    await screen.findByText('ORD-2026-0801');
    expect(get).toHaveBeenCalledOnce();
    expect(get.mock.calls[0][0]).toBe('/api/v1/orders/summaries');
  });

  it('uses only detail and assignment-plan once for the matching Drawer', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    await screen.findByText('正式執行排班（非候選推薦）');
    expect(ordersQueryClient.getOrderDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText(/候選聯繫池與正式推薦/).length).toBeGreaterThan(0);
  });

  it('uses detail, terms, and completion once while signing slots stay unavailable', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]));
    await screen.findByText(/月嫂契約簽回狀態/);
    expect(ordersQueryClient.getOrderDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getOrderTerms).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getContractCompletion).toHaveBeenCalledTimes(1);
    expect(screen.getByText('⏳ 待核銷')).toBeInTheDocument();
  });

  it('opens the cancellation slot with zero query and no calculated refund', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /取消試算/ })[0]));
    expect(screen.getByText(/取消與退款規則/)).toBeInTheDocument();
    expect(screen.getByText(/應退款金額/)).toBeInTheDocument();
    expect(ordersQueryClient.getOrderDetail).not.toHaveBeenCalled();
    expect(ordersQueryClient.getAssignmentPlan).not.toHaveBeenCalled();
  });

  it('keeps the Phase 2B date flow and budgets three Orders GETs', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /確認服務日期/ })[0]));
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledOnce());
    expect(ordersQueryClient.getOrderDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getOrderCalendarDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getActualStart).toHaveBeenCalledTimes(1);
    expect(screen.getAllByText(/服務後緩衝期間/).length).toBeGreaterThan(0);
  });
});
