/**
 * File: orders_no_fake_mutation.test.ts
 * Description: 驗證 Orders 非 Phase 2B controls 維持原生鎖定且不觸發假成功。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import React from 'react';
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

describe('OrdersPage zero fake mutation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
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

  it('keeps new-order and unsupported stage filters native-disabled', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    expect(screen.getByRole('button', { name: /新建訂單/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /進件與補件/ })).toBeDisabled();
    expect(window.alert).not.toHaveBeenCalled();
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it('keeps date-side manual edits and lifecycle transition disabled', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /確認服務日期/ })[0]));
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledOnce());
    expect(screen.getByLabelText(/實際服務開始日/)).toBeDisabled();
    expect(screen.getByLabelText(/排休與請假摘要/)).toBeDisabled();
    expect(screen.getByRole('button', { name: /轉入正式服務履約/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /電話補登客戶確認/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /電話補登月嫂確認/ })).toBeDisabled();
  });

  it('keeps matching side effects disabled while assignment query remains available', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    await screen.findByText('正式執行排班（非候選推薦）');
    expect(screen.getByRole('button', { name: /加入月嫂至意願池/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /重設配對池/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /傳送已勾選月嫂履歷給客戶/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: /產生並建立等待訂金鎖/ })).toBeDisabled();
  });

  it('keeps cancellation Apply disabled and presents no calculated success', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /取消試算/ })[0]));
    expect(screen.getByRole('button', { name: /確認執行取消/ })).toBeDisabled();
    expect(screen.getByText(/應退款金額/)).toBeInTheDocument();
    expect(screen.queryByText(/全額退還/)).not.toBeInTheDocument();
    expect(window.alert).not.toHaveBeenCalled();
  });

  it('removes the compatibility stage mapper after OrderTracker migration', () => {
    const source = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');
    const summary = source('src/adapters/orders/order_summary_adapter.ts');
    const tracker = source('src/adapters/orders/order_tracker_adapter.ts');
    const page = source('src/pages/OrdersPage.tsx');
    const detail = source('src/adapters/orders/order_detail_adapter.ts');
    expect(summary).not.toContain('mapOrderStatusToWorkflowStage');
    expect(tracker).not.toContain('mapOrderStatusToWorkflowStage');
    expect(page).not.toContain('mapOrderStatusToWorkflowStage');
    expect(detail).not.toContain('mapOrderStatusToWorkflowStage');
  });
});
