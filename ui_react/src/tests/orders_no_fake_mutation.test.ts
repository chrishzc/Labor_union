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
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { matchingCandidateWorkflowClient } from '../api/scheduling/matching_candidate_workflow_client';
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
    vi.spyOn(candidateContactPoolClient, 'query').mockResolvedValue({
      pool_id: null,
      case_no: 'ORD-2026-0801',
      candidates: [],
    });
    vi.spyOn(candidateContactPoolClient, 'sendInformation').mockResolvedValue({
      status: 'queued', event_id: 91, line_task_id: 92,
    });
    vi.spyOn(waitingDepositLockClient, 'queryPlan').mockResolvedValue({
      planId: 19,
      status: 'proposed',
      activeLockId: null,
    });
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSingleCaregiver').mockResolvedValue({
      case_no: 'ORD-2026-0801',
      planned_start_date: '2026-09-01',
      planned_end_date: '2026-09-30',
      feasibility: 'complete',
      complete_combinations: [],
      segment_candidates: [],
      candidate_options: [],
      conflicts: [],
    });
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
      payroll_version: 0,
      scheduling: { case_no: 'ORD-2026-0801', generation_number: 1, expected_aggregate_version: 0, resulting_aggregate_version: 1, cancelled_assignment_ids: [], assignments: [], buffers: [] },
      client_finance_impact: { case_no: 'ORD-2026-0801', expected_account_version: 0, resulting_account_version: 1, stage_plans: [], actions: [], settlement: { deposit_settled: false, all_formal_obligations_settled: false, fingerprint: 'b'.repeat(64) }, blockers: [], fingerprint: 'c'.repeat(64) },
      payroll_impact: { case_no: 'ORD-2026-0801', expected_payroll_version: 0, resulting_payroll_version: 1, payroll: { assignments: [], earned_floor_fee: { amount: 0 }, total_payable: { amount: 0 }, fingerprint: 'd'.repeat(64) }, carried_rate_snapshots: [], actions: [], blockers: [], fingerprint: 'e'.repeat(64) },
      lifecycle_impact: { case_no: 'ORD-2026-0801', before_status: '訂單成立', after_status: '訂單取消', actual_end_date: null, cancellation_effective: true, fingerprint: 'f'.repeat(64) }, preview_fingerprint: 'a'.repeat(64),
    });
    vi.spyOn(orderCancellationClient, 'apply').mockResolvedValue({
      case_no: 'ORD-2026-0801', order_version: 1, scheduling_version: 1,
      scheduling_generation: 1, client_finance_version: 1, payroll_version: 1,
      lifecycle_status: '訂單取消', actual_end_date: null,
      official_service_day_count: 0, official_service_hours: 0,
      cancelled_assignment_ids: [], created_assignment_keys: [],
      preview_fingerprint: 'a'.repeat(64),
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
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]));
    await act(async () => fireEvent.click(await screen.findByRole('button', { name: /實質服務日曆/ })));
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
    expect(candidateContactPoolClient.query).toHaveBeenCalledOnce();
    expect(waitingDepositLockClient.queryPlan).toHaveBeenCalledOnce();
  });

  it('requeries matching facts, filters candidates, and queues information from real controls', async () => {
    vi.mocked(candidateContactPoolClient.query).mockResolvedValue({
      pool_id: 11,
      case_no: 'ORD-2026-0801',
      candidates: [{
        id: 17,
        staff_id: 8892,
        service_start_date: '2026-09-01',
        service_end_date: '2026-09-30',
        status: 'active',
        created_at: '2026-08-23T10:00:00',
        staff_name: '測試月嫂',
        willingness: 'willing',
        reason: null,
        information: { '1': null, '2': null },
      }],
    });
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    await screen.findByText('測試月嫂');

    fireEvent.click(screen.getByRole('button', { name: /無意願（0 位）/ }));
    expect(screen.getByText('目前篩選條件下沒有候選聯繫紀錄。')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /全部（1 位）/ }));
    fireEvent.click(screen.getByRole('button', { name: '🔄 重新寄送資訊-1' }));

    await screen.findByText('訂單資訊-1 已排入發送；尚未代表 LINE 已送達。');
    expect(document.body.textContent).not.toContain('發送任務 #92');
    expect(candidateContactPoolClient.sendInformation).toHaveBeenCalledWith('ORD-2026-0801', 17, 1);
    expect(screen.queryByText('✅ 100% 完整覆蓋無空檔')).not.toBeInTheDocument();
    expect(screen.queryByText('定金狀態：已核銷（檔期鎖定）')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '🔍 重新查詢符合條件月嫂' }));
    await waitFor(() => expect(matchingCandidateWorkflowClient.searchSingleCaregiver).toHaveBeenCalledOnce());
    expect(candidateContactPoolClient.query).toHaveBeenCalledTimes(2);
  });

  it('uses the typed cancellation Preview and confirmed Apply without fake amounts or alerts', async () => {
    render(React.createElement(OrdersPage));
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]));
    await act(async () => fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ })));
    await waitFor(() => expect(orderCancellationClient.query).toHaveBeenCalledOnce());
    await screen.findByText(/實際開始日：尚未開始/);
    const previewButton = screen.getByRole('button', { name: /預覽取消與退款試算/ });
    expect(previewButton).toBeEnabled();
    fireEvent.click(previewButton);
    await waitFor(() => expect(orderCancellationClient.preview).toHaveBeenCalledOnce());
    await screen.findByText(/取消影響預覽/);
    expect(document.body.textContent).not.toContain('NT$ 18,000');
    expect(document.body.textContent).not.toContain('Preview 指紋');

    const applyButton = screen.getByRole('button', { name: /確認執行取消/ });
    expect(applyButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText('人工取消原因'), { target: { value: '客戶電話確認取消' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對本次取消日期/ }));
    expect(applyButton).toBeEnabled();
    fireEvent.click(applyButton);

    await screen.findByText(/訂單取消已完成/);
    expect(screen.getByRole('status')).toHaveTextContent('Orders、Client Finance、Payroll 版本已回讀為 1／1／1');
    expect(orderCancellationClient.apply).toHaveBeenCalledWith(
      'ORD-2026-0801',
      expect.objectContaining({
        reason: '客戶電話確認取消',
        preview_fingerprint: 'a'.repeat(64),
        expected_order_version: 0,
        expected_scheduling_version: 0,
        expected_client_finance_version: 0,
        expected_payroll_version: 0,
      }),
      expect.objectContaining({ idempotencyKey: expect.stringContaining('orders-cancellation-ui-ORD-2026-0801-') }),
    );
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
