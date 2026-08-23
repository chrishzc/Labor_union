/**
 * File: orders_no_fake_mutation.test.ts
 * Description: 驗證 Orders 只呈現 typed 可操作流程，且不保留假 mutation 控制。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { orderCancellationClient } from '../api/orders/order_cancellation_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
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
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

const operableSummaryPage = {
  ...realisticOrderSummaryPage,
  items: realisticOrderSummaryPage.items.map((item, index) => index === 0 ? { ...item, order_status: '洽談中' } : item),
};

describe('OrdersPage zero fake mutation', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(window, 'alert').mockImplementation(() => undefined);
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue(operableSummaryPage);
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
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(operableSummaryPage),
    );
    const field = <T = null>(owner: string, value: T = null as T) => ({
      value, owner, source_identity: `fixture:${owner}`, source_version: '1',
      availability: value === null ? 'unavailable' as const : 'available' as const,
      availability_reason: value === null ? 'fixture_missing' : null,
    });
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockImplementation(async (caseNo) => ({
      case_no: caseNo, contact_phone: field('Client'), contact_address: field('Client'),
      requires_cooking: field('Orders'), floor_fee_ntd: field('Orders'),
      deposit_amount_ntd: field('Finance'), deposit_settlement_state: field('Finance'),
      deposit_settled_on: field('Finance'), actual_start_date: field('Orders'),
      actual_end_date: field('Orders'), assignment_segments: field('Scheduling', []),
    }));
    vi.spyOn(contractSigningClient, 'query').mockResolvedValue({
      case_no: 'ORD-2026-0801', staff_segments: [], commitment_id: null,
      client_document_sent: false, client_signed_received: false, contract_identity: null, documents: [],
    });
    vi.spyOn(orderCancellationClient, 'query').mockResolvedValue({
      case_no: 'ORD-2026-0801', lifecycle_status: '訂單成立', actual_start_date: null,
      contracted_service_days: 30, service_hours_per_day: 8, service_started: false,
      service_data_locked: false, order_version: 0, scheduling_version: 0,
      scheduling_generation: 0, client_finance_version: 0, payroll_version: 0,
      confirmed_service_days: [], caregiver_options: [],
    });
    vi.spyOn(orderCancellationClient, 'preview').mockResolvedValue({
      cancellation_date: '2026-08-23', actual_end_date: null, confirmed_service_days: [],
      official_service_day_count: 0, official_service_hours: 0, order_version: 0,
      scheduling_version: 0, scheduling_generation: 0, client_finance_version: 0,
      payroll_version: 0, scheduling: {}, client_finance_impact: {}, payroll_impact: {},
      lifecycle_impact: {}, preview_fingerprint: 'a'.repeat(64),
    });
  });

  it('removes fake new-order control and enables typed stage filters', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    expect(screen.queryByRole('button', { name: /新建訂單/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /進件與補件/ })).toBeEnabled();
    expect(window.alert).not.toHaveBeenCalled();
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it('removes fake date-side manual mutations', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /確認服務日期/ })[0]));
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledOnce());
    expect(screen.queryByRole('button', { name: /轉入正式服務履約/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /電話補登客戶確認/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /電話補登月嫂確認/ })).not.toBeInTheDocument();
  });

  it('removes fake matching side effects while assignment query remains available', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    await screen.findByText('正式執行排班（非候選推薦）');
    expect(screen.queryByRole('button', { name: /加入月嫂至意願池/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /重設配對池/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /傳送已勾選月嫂履歷給客戶/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /產生並建立等待訂金鎖/ })).not.toBeInTheDocument();
    expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledOnce();
  });

  it('offers cancellation Query and Preview without exposing Apply', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /取消試算/ })[0]));
    await screen.findByText('取消前根事實');
    fireEvent.click(screen.getByRole('button', { name: '產生取消預覽' }));
    await screen.findByText('取消影響預覽（零寫入）');
    expect(screen.queryByRole('button', { name: /確認執行取消/ })).not.toBeInTheDocument();
    expect(orderCancellationClient.preview).toHaveBeenCalledOnce();
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
