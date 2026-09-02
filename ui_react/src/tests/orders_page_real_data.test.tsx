/**
 * File: orders_page_real_data.test.tsx
 * Description: 驗證 OrdersPage successor 契約 surface、active-plan 查詢的 fail-closed、404 與合法空狀態。
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';
import { sessionClient } from '../api/auth/session_client';
import { ordersMutationClient } from '../api/orders/order_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { contractSigningClient } from '../api/orders/contract_signing_client';
import { orderCardProjectionClient } from '../api/orders/order_card_projection_client';
import type { OrdersCardProjection } from '../api/orders/order_card_projection_schemas';
import { orderCancellationClient } from '../api/orders/order_cancellation_client';
import { orderStageProjectionClient } from '../api/orders/order_stage_projection_client';
import { orderTermsMutationClient } from '../api/orders/order_terms_mutation_client';
import { orderActualStartClient } from '../api/orders/order_actual_start_client';
import { OrderConflictError, OrderValidationError } from '../api/orders/order_query_errors';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import {
  matchingCandidateWorkflowClient,
  type MatchingAvailability,
} from '../api/scheduling/matching_candidate_workflow_client';
import { waitingDepositLockClient } from '../api/scheduling/waiting_deposit_lock_client';
import { transport } from '../api/shared/transport';
import { ApiDecodeError, ApiHttpError, ApiNetworkError } from '../api/shared/typed_errors';
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
import {
  realisticOrderReopenPreviewView,
  realisticServiceDateQueryView,
} from './fixtures/orders/order_mutation_contract_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

vi.mock('../components/ContractExternalSigningActions', () => ({
  ContractExternalSigningActions: ({ caseNo }: { caseNo: string }) => (
    <section aria-label="外部平台簽約與最終 PDF">successor contract surface：{caseNo}</section>
  ),
}));

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

const cancellationQuery = {
  case_no: 'ORD-2026-0801', lifecycle_status: '訂單成立', actual_start_date: null,
  contracted_service_days: 30, service_hours_per_day: 8, service_started: false,
  historical_mid_service_confirmation_available: false,
  service_data_locked: false, order_version: 0, scheduling_version: 0,
  scheduling_generation: 0, client_finance_version: 0, payroll_version: 0,
  confirmed_service_days: [], caregiver_options: [],
};

function useOperableSummary(): void {
  vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue(operableSummaryPage);
  vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(
    buildOrdersStageProjectionFixture(operableSummaryPage),
  );
}

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
    vi.spyOn(candidateContactPoolClient, 'query').mockImplementation(async (caseNo) => ({
      pool_id: null,
      case_no: caseNo,
      candidates: [],
    }));
    vi.spyOn(waitingDepositLockClient, 'queryPlan').mockRejectedValue(
      new ApiHttpError(404, 'HTTP_404', 'active matching plan not found'),
    );
    vi.spyOn(contractSigningClient, 'query').mockResolvedValue({
      case_no: 'ORD-2026-0801',
      staff_segments: [{ segment_id: 1, staff_id: 101, sent: true, signed_received: true }],
      commitment_id: 1,
      client_document_sent: true,
      client_signed_received: true,
      contract_identity: 'CONTRACT-1',
      documents: [],
    });
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage),
    );
    vi.spyOn(orderCardProjectionClient, 'getCardProjection').mockImplementation(async (caseNo) => unavailableCardProjection(caseNo));
    vi.spyOn(orderCancellationClient, 'query').mockResolvedValue(cancellationQuery);
    vi.spyOn(orderCancellationClient, 'preview').mockResolvedValue({
      cancellation_date: '2026-08-23', actual_start_date: null, actual_end_date: null, confirmed_service_days: [],
      official_service_day_count: 0, official_service_hours: 0, order_version: 0,
      scheduling_version: 0, scheduling_generation: 0, client_finance_version: 0,
      payroll_version: 0,
      scheduling: { case_no: 'ORD-2026-0801', generation_number: 1, expected_aggregate_version: 0, resulting_aggregate_version: 1, cancelled_assignment_ids: [], assignments: [], buffers: [] },
      client_finance_impact: { case_no: 'ORD-2026-0801', expected_account_version: 0, resulting_account_version: 1, stage_plans: [], actions: [], settlement: { deposit_settled: false, all_formal_obligations_settled: false, fingerprint: 'b'.repeat(64) }, blockers: [], fingerprint: 'c'.repeat(64) },
      payroll_impact: { case_no: 'ORD-2026-0801', expected_payroll_version: 0, resulting_payroll_version: 1, payroll: { assignments: [], earned_floor_fee: { amount: 0 }, total_payable: { amount: 0 }, fingerprint: 'd'.repeat(64) }, carried_rate_snapshots: [], actions: [], special_pay_events: [], blockers: [], fingerprint: 'e'.repeat(64) },
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
    vi.spyOn(orderTermsMutationClient, 'preview').mockResolvedValue({
      before: realisticOrderTerms.terms,
      after: realisticOrderTerms.terms,
      order_version: realisticOrderTerms.order_version,
      scheduling_version: realisticOrderTerms.scheduling_version,
      scheduling_generation: realisticOrderTerms.scheduling_generation,
      client_finance_version: realisticOrderTerms.client_finance_version,
      payroll_version: realisticOrderTerms.payroll_version,
      scheduling: {},
      client_finance_impact: {},
      payroll_impact: {},
      lifecycle_impact: {},
      preview_fingerprint: 'b'.repeat(64),
    });
    vi.spyOn(orderActualStartClient, 'preview').mockResolvedValue({
      before_actual_start_date: null,
      after_actual_start_date: '2026-09-01',
      actual_end_date: '2026-09-30',
      order_version: 1,
      scheduling_version: 2,
      scheduling_generation: 3,
      client_finance_version: 4,
      payroll_version: 5,
      actual_start: { official_service_dates: ['2026-09-01', '2026-09-02'] },
      scheduling: { assignments: [{ candidate_key: 'fixture-assignment' }] },
      preview_fingerprint: 'c'.repeat(64),
    } as never);
    vi.spyOn(ordersMutationClient, 'getServiceDates').mockResolvedValue(realisticServiceDateQueryView);
    vi.spyOn(ordersMutationClient, 'previewReopen').mockResolvedValue(realisticOrderReopenPreviewView);
  });

  it('renders raw server statuses and filters with the server seven-stage projection', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    expect(screen.getAllByText('伺服器狀態：待補件').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /全部 \(7\)/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /1\. 進件與補件 \(1\)/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: /6\. 正式服務中 \(6\)/ })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /1\. 進件與補件 \(1\)/ }));
    expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument();
    expect(screen.queryByText('ORD-2026-0802')).not.toBeInTheDocument();
    expect(screen.queryByText(/未納入目前摘要／typed view/)).not.toBeInTheDocument();
    expect(screen.getAllByText(/雇主自付應付額/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/合約總額：/)).not.toBeInTheDocument();
  });

  it('keeps summary orders usable when stage projection includes a stage-only historical case', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue({
      ...stagePage,
      items: [
        ...stagePage.items,
        { ...stagePage.items[0], case_no: 'LEGACY-STAGE-ONLY' },
      ],
    });

    render(<OrdersPage />);

    await screen.findByText('ORD-2026-0801');
    expect(screen.getByText('ORD-2026-0802')).toBeInTheDocument();
    expect(screen.queryByText(/訂單階段資料載入失敗/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /1\. 進件與補件/ })).toBeEnabled();
  });

  it('automatically continues to terminal, deduplicates summaries and removes the manual next-page gate', async () => {
    const firstPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[0]],
      next_cursor: realisticOrderSummaryPage.items[0].case_no,
    };
    const secondPage = {
      ...realisticOrderSummaryPage,
      items: [realisticOrderSummaryPage.items[1]],
      next_cursor: null,
    };
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);
    vi.mocked(orderStageProjectionClient.getOperationalTimelines)
      .mockResolvedValueOnce({ ...buildOrdersStageProjectionFixture(firstPage), next_cursor: firstPage.next_cursor })
      .mockResolvedValueOnce(buildOrdersStageProjectionFixture(secondPage));

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await screen.findByText('ORD-2026-0802');
    expect(screen.getAllByText('ORD-2026-0801')).toHaveLength(1);
    expect(screen.getByRole('button', { name: /1\. 進件與補件 \(2\)/ })).toBeEnabled();
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenNthCalledWith(
      2,
      { page_size: 200, lifecycle_scope: 'unfinished', after_case_no: 'ORD-2026-0801' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenNthCalledWith(
      1,
      { page_size: 200, lifecycle_scope: 'unfinished' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(orderStageProjectionClient.getOperationalTimelines).toHaveBeenNthCalledWith(
      1,
      { page_size: 200, lifecycle_scope: 'unfinished' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(orderStageProjectionClient.getOperationalTimelines).toHaveBeenNthCalledWith(
      2,
      { page_size: 200, lifecycle_scope: 'unfinished', after_case_no: 'ORD-2026-0801' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('button', { name: '載入下一頁' })).not.toBeInTheDocument();
  });

  it('fails closed with retry when summary continuation cursor does not advance', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries)
      .mockResolvedValueOnce({ ...realisticOrderSummaryPage, items: [realisticOrderSummaryPage.items[0]], next_cursor: realisticOrderSummaryPage.items[0].case_no })
      .mockResolvedValueOnce({ ...realisticOrderSummaryPage, items: [realisticOrderSummaryPage.items[0]], next_cursor: realisticOrderSummaryPage.items[0].case_no });
    render(<OrdersPage />);
    await waitFor(() => expect(screen.getByText(/載入訂單資料失敗/)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: '重試' })).toBeInTheDocument();
  });

  it('filters cancelled orders from the terminal projection instead of a business stage', async () => {
    const stagePage = buildOrdersStageProjectionFixture(realisticOrderSummaryPage);
    stagePage.items[0].current_stage_code = null;
    stagePage.items[0].current_sop_step = null;
    stagePage.items[0].terminal_state = 'cancelled';
    stagePage.stage_counts.intake_terms = 0;
    vi.mocked(orderStageProjectionClient.getOperationalTimelines).mockResolvedValue(stagePage);

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');

    const cancelledFilter = screen.getByRole('button', { name: /已取消 \(1\)/ });
    fireEvent.click(cancelledFilter);
    expect(screen.getByText('ORD-2026-0801')).toBeInTheDocument();
    expect(screen.queryByText('ORD-2026-0802')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /2\. 媒合與徵詢意願 \(0\)/ })).toBeEnabled();
  });

  it('searches all lifecycle states and clears the old stage filter', async () => {
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: /1\. 進件與補件 \(1\)/ }));
    expect(screen.queryByText('ORD-2026-0802')).not.toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox', { name: '搜尋案件' }), {
      target: { value: 'ORD-2026-0802' },
    });

    await waitFor(() => expect(
      screen.getByRole('button', { name: /1\. 進件與補件/ }),
    ).toBeDisabled());

    await waitFor(() => expect(ordersQueryClient.getOrderSummaries).toHaveBeenLastCalledWith(
      { page_size: 200, lifecycle_scope: 'all', query_text: 'ORD-2026-0802' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    expect(await screen.findByText('ORD-2026-0802')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /全部 \(7\)/ })).toHaveClass('active');
    expect(screen.getByRole('button', { name: /1\. 進件與補件/ })).toBeDisabled();
  });

  it('reloads cancellation facts when the shared workbench switches to another order', async () => {
    const firstQuery = { ...cancellationQuery, lifecycle_status: '訂單取消' as const };
    const secondQuery = { ...cancellationQuery, case_no: 'ORD-2026-0802', lifecycle_status: '洽談中' as const };
    vi.mocked(orderCancellationClient.query).mockImplementation(async (caseNo) => (
      caseNo === 'ORD-2026-0801' ? firstQuery : secondQuery
    ));

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    expect(await screen.findByText('🚫 不可再次取消')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }));

    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[1]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));

    await waitFor(() => expect(orderCancellationClient.query).toHaveBeenLastCalledWith(
      'ORD-2026-0802',
      expect.any(AbortSignal),
    ));
    expect(screen.getByText('🟢 允許取消試算')).toBeInTheDocument();
    expect(screen.queryByText('🚫 不可再次取消')).not.toBeInTheDocument();
    expect(screen.getByText('洽談中')).toBeInTheDocument();
  });

  it('deduplicates the StrictMode initial summary load to one transport request', async () => {
    vi.restoreAllMocks();
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('strict-mode-token');
    vi.spyOn(orderStageProjectionClient, 'getOperationalTimelines').mockResolvedValue(
      buildOrdersStageProjectionFixture(realisticOrderSummaryPage),
    );
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

  it('queries typed detail, terms, candidate pool, and assignment plan once for the matching Drawer', async () => {
    useOperableSummary();
    vi.mocked(ordersQueryClient.getFormManagementContext).mockResolvedValueOnce({
      case_no: 'ORD-2026-0801',
      service_time: '08:30-17:30',
      service_type: '到府服務',
      delivery_type: '自然產',
      residence_type: '公寓',
      city: '台北市',
      identity_status: 'regular',
    });
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    await screen.findByText('正式執行排班（非候選推薦）');
    expect(ordersQueryClient.getOrderDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getOrderTerms).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getFormManagementContext).toHaveBeenCalledTimes(1);
    expect(candidateContactPoolClient.query).toHaveBeenCalledTimes(1);
    expect(waitingDepositLockClient.queryPlan).toHaveBeenCalledTimes(1);
    expect(screen.getByText('無進行中方案')).toBeInTheDocument();
    expect(screen.getByText('服務縣市：台北市')).toBeInTheDocument();
    expect(screen.getByText('服務類型：到府服務')).toBeInTheDocument();
    expect(screen.getByText('每日服務時段：08:30-17:30')).toBeInTheDocument();
    expect(screen.getByText('生產方式：自然產')).toBeInTheDocument();
    expect(screen.getByText('住宅類型：公寓')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.matching.active-plan-query-error"]')).toBeNull();
    expect(screen.queryByText(/後端.*提供|未開放|未納入/)).not.toBeInTheDocument();
  });

  it('keeps missing client context fields explicit without exposing source metadata', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    await screen.findByText('正式執行排班（非候選推薦）');

    expect(screen.getByText('服務縣市：尚未登錄')).toBeInTheDocument();
    expect(screen.getByText('服務類型：尚未登錄')).toBeInTheDocument();
    expect(screen.getByText('每日服務時段：尚未登錄')).toBeInTheDocument();
    expect(screen.queryByText(/query_no|survey_details|fingerprint|source_identity/i)).not.toBeInTheDocument();
  });

  it('completes the sanctioned candidate workflow through real UI controls and typed readbacks', async () => {
    useOperableSummary();
    const availability: MatchingAvailability = {
      case_no: 'ORD-2026-0801',
      planned_start_date: '2026-08-01',
      planned_end_date: '2026-08-30',
      feasibility: 'complete',
      complete_combinations: [[{ segment_index: 0, staff_id: 8892, start_date: '2026-08-01', end_date: '2026-08-30' }]],
      segment_candidates: [{ segment_index: 0, staff_id: 8892, start_date: '2026-08-01', end_date: '2026-08-30' }],
      candidate_options: [{
        segment_index: 0,
        staff_id: 8892,
        staff_name: '測試可接月嫂',
        coverage_day_count: 30,
        available_ranges: [{ start_date: '2026-08-01', end_date: '2026-08-30' }],
        case_period_start: '2026-08-01',
        case_period_end: '2026-08-30',
        required_service_dates: ['2026-08-01'],
        supported_service_dates: ['2026-08-01'],
        supported_ranges: [{ start_date: '2026-08-01', end_date: '2026-08-30', service_day_count: 1 }],
        supported_day_count: 1,
        required_day_count: 1,
        full_case_coverage: true,
        selected_segment_start: '2026-08-01',
        selected_segment_end: '2026-08-30',
        full_selected_segment_coverage: true,
        uncovered_segment_dates: [],
        source_scheduling_version: 4,
        filter_results: {
          region: true,
          cooking: true,
          preferred_service_days: true,
          daily_service_hours: true,
        },
      }],
      conflicts: [],
    };
    let poolCandidates: Array<{
      id: number; staff_id: number; service_start_date: string; service_end_date: string;
      status: 'active'; created_at: string; staff_name: string;
      willingness: 'pending' | 'willing'; reason: string | null;
      information: { '1': null; '2': null };
    }> = [];
    let activePlan = false;
    vi.mocked(candidateContactPoolClient.query).mockImplementation(async (caseNo) => ({
      pool_id: poolCandidates.length ? 8 : null,
      case_no: caseNo,
      candidates: poolCandidates,
    }));
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSingleCaregiver').mockResolvedValue(availability);
    vi.spyOn(candidateContactPoolClient, 'addCandidates').mockImplementation(async () => {
      poolCandidates = [{
        id: 17, staff_id: 8892, service_start_date: '2026-08-01', service_end_date: '2026-08-30',
        status: 'active', created_at: '2026-08-23T10:00:00', staff_name: '測試可接月嫂',
        willingness: 'pending', reason: null, information: { '1': null, '2': null },
      }];
      return { pool_id: 8, candidate_ids: [17], status: 'recorded' };
    });
    vi.spyOn(candidateContactPoolClient, 'sendInformation').mockResolvedValue({
      status: 'queued', event_id: 31, line_task_id: 52,
    });
    vi.spyOn(candidateContactPoolClient, 'recordWillingness').mockImplementation(async () => {
      poolCandidates = poolCandidates.map((candidate) => ({ ...candidate, willingness: 'willing' }));
      return { status: 'recorded', event_id: 32 };
    });
    vi.spyOn(matchingCandidateWorkflowClient, 'createSingleCaregiverPlan').mockImplementation(async () => {
      activePlan = true;
      return {
        plan_id: 51, case_no: 'ORD-2026-0801', version: 1, status: 'proposed', result: 'created',
        segments: [{ segment_order: 1, staff_id: 8892, assigned_start_date: '2026-08-01', assigned_end_date: '2026-08-30' }],
      };
    });
    vi.mocked(waitingDepositLockClient.queryPlan).mockImplementation(async () => {
      if (!activePlan) throw new ApiHttpError(404, 'HTTP_404', 'active matching plan not found');
      return { planId: 51, status: 'proposed', activeLockId: null };
    });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);

    fireEvent.click(await screen.findByRole('button', { name: /重新查詢符合條件月嫂/ }));
    expect(await screen.findByText(/測試可接月嫂/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /測試可接月嫂/ }));
    fireEvent.click(screen.getByRole('button', { name: /加入候選聯繫池/ }));
    await screen.findByText(/已回讀確認 1 位月嫂加入候選聯繫池/);

    fireEvent.click(screen.getByRole('button', { name: /重新寄送資訊-1/ }));
    await screen.findByText(/訂單資訊-1 已排入發送；尚未代表 LINE 已送達/);
    fireEvent.click(screen.getByRole('button', { name: '更新候選意願' }));
    await screen.findByText(/意願為願意/);

    const formalPlanButton = screen.getByRole('button', { name: '建立正式單月嫂配對方案' });
    expect(formalPlanButton).toBeEnabled();
    fireEvent.click(formalPlanButton);
    await screen.findByText('正式單月嫂方案已建立並完成回讀。');
    expect(matchingCandidateWorkflowClient.searchSingleCaregiver).toHaveBeenCalledOnce();
    expect(candidateContactPoolClient.addCandidates).toHaveBeenCalledOnce();
    expect(candidateContactPoolClient.query).toHaveBeenCalledTimes(7);
    expect(matchingCandidateWorkflowClient.createSingleCaregiverPlan).toHaveBeenCalledOnce();
  });

  it('disables formal-plan creation when the current plan already has a waiting-deposit lock', async () => {
    useOperableSummary();
    const createFormalPlanSpy = vi.spyOn(matchingCandidateWorkflowClient, 'createSingleCaregiverPlan');
    vi.mocked(candidateContactPoolClient.query).mockResolvedValue({
      pool_id: 8,
      case_no: 'ORD-2026-0801',
      candidates: [{
        id: 17, staff_id: 8892, service_start_date: '2026-08-01', service_end_date: '2026-08-30',
        status: 'active', created_at: '2026-08-23T10:00:00', staff_name: '測試可接月嫂',
        willingness: 'willing', reason: null, information: { '1': null, '2': null },
      }],
    });
    vi.mocked(waitingDepositLockClient.queryPlan).mockResolvedValue({
      planId: 51,
      status: 'accepted',
      activeLockId: 91,
    });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);

    const formalPlanButton = await screen.findByRole('button', { name: '建立正式單月嫂配對方案' });
    expect(formalPlanButton).toBeDisabled();
    expect(formalPlanButton).toHaveAttribute('title', '目前方案已取得等待訂金鎖，不能重新建立媒合方案。');
    expect(screen.getByRole('button', { name: /重新寄送資訊-1/ })).toBeDisabled();
    expect(screen.getByText('目前方案已取得等待訂金鎖；候選聯繫紀錄已鎖定，請依定金與簽約流程繼續。')).toBeInTheDocument();
    fireEvent.click(formalPlanButton);
    expect(createFormalPlanSpy).not.toHaveBeenCalled();
  });

  it('maps an unready matching preference source to the Client BeClass corrective action', async () => {
    useOperableSummary();
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSingleCaregiver').mockRejectedValue(
      new ApiHttpError(
        409,
        'matching_preference_source_not_ready',
        '月嫂分段檔期查詢未通過',
      ),
    );
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /重新查詢符合條件月嫂/ }));

    expect(await screen.findByText(
      '下廚料理需求尚未就緒；請先從資料匯入中心匯入並唯一配對 Client BeClass，再重新查詢月嫂。',
    )).toHaveAttribute('role', 'alert');
    expect(screen.queryByText(/最新完整承接候選（0 位）/)).not.toBeInTheDocument();
    expect(screen.queryByText(/目前沒有月嫂能完整承接/)).not.toBeInTheDocument();
  });

  it('requires exact service dates before a matching query can treat days as formal coverage', async () => {
    useOperableSummary();
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSingleCaregiver').mockRejectedValue(
      new ApiHttpError(
        409,
        'official_service_dates_incomplete',
        '月嫂分段檔期查詢未通過。',
      ),
    );
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /重新查詢符合條件月嫂/ }));

    expect(await screen.findByText(
      '尚未確認精確服務日期；請先完成日期精算與休假調整，再重新查詢月嫂。',
    )).toHaveAttribute('role', 'alert');
    expect(screen.queryByText(/最新完整承接候選（0 位）/)).not.toBeInTheDocument();
  });

  it('explains that a settled order cannot restart negotiation availability search', async () => {
    useOperableSummary();
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSingleCaregiver').mockRejectedValue(
      new ApiHttpError(
        409,
        'caregiver_availability_stage_conflict',
        '月嫂分段檔期查詢未通過。',
      ),
    );
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /重新查詢符合條件月嫂/ }));

    expect(await screen.findByText(
      '此案已不在洽談階段，不能重新查詢候選月嫂；請依既有正式方案、定金與簽約流程繼續。',
    )).toHaveAttribute('role', 'alert');
    expect(screen.queryByText(/最新完整承接候選（0 位）/)).not.toBeInTheDocument();
  });

  it('uses available card projection facts in the matching demand summary', async () => {
    useOperableSummary();
    const projection = unavailableCardProjection('ORD-2026-0801');
    projection.contact_address = {
      ...projection.contact_address,
      value: '臺中市西區測試路 1 號',
      availability: 'available',
      availability_reason: null,
    };
    projection.deposit_amount_ntd = {
      ...projection.deposit_amount_ntd,
      value: 12_000,
      availability: 'available',
      availability_reason: null,
    };
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValueOnce(projection);
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);

    expect(await screen.findByText('📍 臺中市西區測試路 1 號')).toBeInTheDocument();
    expect(screen.getByText('💰 定金：NT$ 12,000')).toBeInTheDocument();
  });

  it('keeps historical Client Finance gaps explicit while preserving valid matching projections', async () => {
    useOperableSummary();
    vi.mocked(ordersQueryClient.getOrderTerms).mockRejectedValueOnce(
      new OrderConflictError(
        'Orders Terms request was rejected.',
        null,
        [],
        'client_finance_bootstrap_required',
      ),
    );
    vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValueOnce(
      new OrderValidationError(
        'Assignment Plan request was rejected.',
        [],
        'client_finance_bootstrap_required',
      ),
    );
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);

    expect(await screen.findByText('歷史資料待補正')).toBeInTheDocument();
    expect(screen.getByText(/完整正式排班 projection 待補正/)).toBeInTheDocument();
    expect(screen.getByText(/資料待補正（下廚料理條款）/)).toBeInTheDocument();
    expect(screen.queryByText('尚未確認料理需求')).not.toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.matching.query-error"]')).toBeNull();
  });

  it.each([
    ['detail identity', () => vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValueOnce({ ...realisticOrderDetail, case_no: 'OTHER' })],
    ['assignment identity', () => vi.mocked(ordersQueryClient.getAssignmentPlan).mockResolvedValueOnce({ ...realisticAssignmentPlan, case_no: 'OTHER' })],
    ['candidate query', () => vi.mocked(candidateContactPoolClient.query).mockRejectedValueOnce(new Error('candidate failed'))],
  ])('fails matching closed for %s drift without rendering legal empty states', async (_source, breakSource) => {
    useOperableSummary();
    breakSource();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);

    expect(await screen.findByText('正式排班資料暫時無法取得，請關閉後重試。')).toBeInTheDocument();
    expect(screen.queryByText('目前尚無候選聯繫紀錄。')).not.toBeInTheDocument();
    expect(screen.queryByText('目前尚無正式執行排班分段')).not.toBeInTheDocument();
    expect(screen.queryByText('尚未確認料理需求')).not.toBeInTheDocument();
  });

  it.each([
    ['network', () => new ApiNetworkError('network failed')],
    ['5xx', () => new ApiHttpError(503, 'HTTP_503', 'service unavailable', true)],
    ['schema', () => new ApiDecodeError('schema failed')],
    ['other', () => new Error('unexpected failure')],
  ])('keeps a non-404 active-plan %s failure separate from assignment-plan state', async (_kind, makeError) => {
    useOperableSummary();
    vi.mocked(waitingDepositLockClient.queryPlan).mockRejectedValueOnce(makeError());
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));

    expect(await screen.findByText('進行中媒合方案與等待訂金鎖資料載入失敗，請關閉後重試。')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.matching.active-plan-query-error"]')).toHaveAttribute('role', 'alert');
    expect(screen.queryByText('無進行中方案')).not.toBeInTheDocument();
    expect(screen.queryByText('目前沒有可建立鎖定的進行中媒合方案')).not.toBeInTheDocument();
    expect(screen.getByText('正式執行排班（非候選推薦）')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.matching.query-error"]')).toBeNull();
  });

  it('shows an assignment-plan typed failure instead of misreporting an empty schedule', async () => {
    useOperableSummary();
    vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValueOnce(
      new Error('Assignment Plan request was rejected.'),
    );
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    expect(await screen.findByText('正式排班資料載入失敗，請關閉後重試。')).toBeInTheDocument();
    expect(screen.queryByText('目前沒有伺服器回傳的正式執行排班段')).not.toBeInTheDocument();
  });

  it('uses the signing GET and renders real staff/client signed status', async () => {
    useOperableSummary();
    const projection = unavailableCardProjection('ORD-2026-0801');
    projection.contact_address = {
      ...projection.contact_address,
      value: '臺中市西區測試路 1 號',
      availability: 'available',
      availability_reason: null,
    };
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValueOnce(projection);
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]));
    await screen.findByText('✅ 全部分段已簽回');
    expect(ordersQueryClient.getOrderDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getOrderTerms).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getContractCompletion).toHaveBeenCalledTimes(1);
    expect(contractSigningClient.query).toHaveBeenCalledTimes(1);
    expect(screen.getByText('✅ 客戶契約已簽回')).toBeInTheDocument();
    expect(screen.getByText('⏳ 待核銷')).toBeInTheDocument();
    const locationFact = screen.getByText('產婦與地點').closest('.matching-fact-item');
    if (!locationFact) throw new Error('找不到 unified contract Drawer 的產婦與地點區域。');
    expect(locationFact).toHaveTextContent('臺中市西區測試路 1 號');
    expect(locationFact).not.toHaveTextContent('地址待確認');
  });

  it('mounts the successor contract workflow without exposing the legacy external URL surface', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    expect(await screen.findByRole('region', { name: '外部平台簽約與最終 PDF' })).toHaveTextContent(
      'successor contract surface：ORD-2026-0801',
    );
    expect(screen.queryByLabelText('受控 HTTPS 文件下載網址')).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '契約寄送與簽回文件操作' })).not.toBeInTheDocument();
  });

  it('shows missing service-time and cooking roots as pending instead of inventing defaults', async () => {
    useOperableSummary();
    vi.mocked(ordersQueryClient.getOrderTerms).mockResolvedValueOnce({
      ...realisticOrderTerms,
      terms: {
        ...realisticOrderTerms.terms,
        service_hours_per_day: 9,
        requires_cooking: null,
        service_time: { start_time: null, end_time: null, end_day_offset: null },
      },
    });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    const serviceFact = await screen.findByText('每日時段與料理');
    expect(serviceFact.closest('.matching-fact-item')).toHaveTextContent('資料待補正（服務時段三欄）');
    expect(serviceFact.closest('.matching-fact-item')).toHaveTextContent('尚未登錄（下廚料理條款）');
    expect(screen.queryByText(/09:00.*17:00/)).not.toBeInTheDocument();
  });

  it.each([
    ['terms', () => vi.mocked(ordersQueryClient.getOrderTerms).mockRejectedValueOnce(new Error('terms failed'))],
    ['completion', () => vi.mocked(ordersQueryClient.getContractCompletion).mockRejectedValueOnce(new Error('completion failed'))],
    ['detail', () => vi.mocked(ordersQueryClient.getOrderDetail).mockRejectedValueOnce(new Error('detail failed'))],
    ['signing', () => vi.mocked(contractSigningClient.query).mockRejectedValueOnce(new Error('signing failed'))],
  ])('fails the contract Drawer closed when the required %s query fails', async (_source, failQuery) => {
    useOperableSummary();
    failQuery();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    expect(await screen.findByText('契約與條款資料載入失敗，請關閉後重試。')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.contract.query-error"]')).toHaveAttribute('role', 'alert');
    expect(screen.queryByText('尚無月嫂契約分段')).not.toBeInTheDocument();
    expect(screen.queryByText('尚未寄送客戶契約')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '檢查訂單條款變更' })).not.toBeInTheDocument();
  });

  it('routes missing historical Client Finance roots to correction isolation without a fake query failure', async () => {
    useOperableSummary();
    vi.mocked(ordersQueryClient.getOrderTerms).mockRejectedValueOnce(
      new ApiHttpError(409, 'client_finance_bootstrap_required', 'Orders Terms request was rejected.'),
    );
    vi.mocked(ordersQueryClient.getContractCompletion).mockRejectedValueOnce(
      new ApiHttpError(422, 'client_finance_bootstrap_required', '契約完成請求未通過驗證。'),
    );
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    expect(await screen.findByText('歷史資料待補正')).toBeInTheDocument();
    expect(screen.getByText(/缺少客戶帳務的契約與定金資料/)).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.contract.historical-correction"]')).toHaveAttribute('role', 'status');
    expect(document.querySelector('[data-surface-id="orders.contract.query-error"]')).toBeNull();
    expect(screen.queryByRole('button', { name: '檢查訂單條款變更' })).not.toBeInTheDocument();
  });

  it.each([
    ['terms', () => vi.mocked(ordersQueryClient.getOrderTerms).mockResolvedValueOnce({ ...realisticOrderTerms, case_no: 'OTHER' })],
    ['completion', () => vi.mocked(ordersQueryClient.getContractCompletion).mockResolvedValueOnce({ ...realisticContractCompletion, case_no: 'OTHER' })],
    ['detail', () => vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValueOnce({ ...realisticOrderDetail, case_no: 'OTHER' })],
    ['signing', () => vi.mocked(contractSigningClient.query).mockResolvedValueOnce({
      case_no: 'OTHER', staff_segments: [], commitment_id: null,
      client_document_sent: false, client_signed_received: false,
      contract_identity: null, documents: [],
    })],
  ])('fails the contract Drawer closed when the required %s identity drifts', async (_source, driftQuery) => {
    useOperableSummary();
    driftQuery();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    expect(await screen.findByText('契約與條款資料載入失敗，請關閉後重試。')).toBeInTheDocument();
    expect(screen.queryByText('尚無月嫂契約分段')).not.toBeInTheDocument();
    expect(screen.queryByText('尚未寄送客戶契約')).not.toBeInTheDocument();
  });

  it('preserves legitimate empty signing facts after all required queries succeed', async () => {
    useOperableSummary();
    vi.mocked(contractSigningClient.query).mockResolvedValueOnce({
      case_no: 'ORD-2026-0801', staff_segments: [], commitment_id: null,
      client_document_sent: false, client_signed_received: false,
      contract_identity: null, documents: [],
    });
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    expect(await screen.findByText('尚無月嫂契約分段')).toBeInTheDocument();
    expect(screen.getByText('尚未寄送客戶契約')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.contract.query-error"]')).toBeNull();
  });

  it('keeps an unavailable assignment projection distinct from a legitimate empty assignment list', async () => {
    useOperableSummary();
    const projection = unavailableCardProjection('ORD-2026-0801');
    projection.assignment_segments = {
      ...projection.assignment_segments,
      value: null,
      availability: 'unavailable',
      availability_reason: 'formal_assignment_lineage_missing',
    };
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValueOnce(projection);
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    const surface = await waitFor(() => document.querySelector('[data-surface-id="orders.card-projection"]'));
    expect(surface).toHaveTextContent('資料待補正（正式指派分段）');
    expect(surface).not.toHaveTextContent('目前尚無正式指派分段。');
  });

  it('keeps one operational assignment summary and places identifiers and provenance in collapsed technical details', async () => {
    useOperableSummary();
    const projection = unavailableCardProjection('ORD-2026-0801');
    const field = <T,>(owner: string, value: T) => ({
      value,
      owner,
      source_identity: `fixture:assignment:${owner}`,
      source_version: '7',
      availability: 'available' as const,
      availability_reason: null,
    });
    projection.assignment_segments = field('Scheduling', [{
      assignment_id: field('Scheduling', 501),
      staff_id: field('Staff', 101),
      staff_name: field('Staff', '王小美'),
      sequence: field('Scheduling', 1),
      assigned_start_date: field('Scheduling', '2026-08-01'),
      assigned_end_date: field('Scheduling', '2026-08-30'),
      status: field('Scheduling', 'active'),
    }]);
    vi.mocked(orderCardProjectionClient.getCardProjection).mockResolvedValueOnce(projection);

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);

    const surface = await waitFor(() => document.querySelector('[data-surface-id="orders.card-projection"]'));
    if (!surface) throw new Error('找不到案件投影。');
    expect(surface).toHaveTextContent('服務人員：王小美');
    expect(surface).toHaveTextContent('正式服務期間：2026-08-01 ～ 2026-08-30');
    expect(surface).toHaveTextContent('指派狀態：正式服務中');
    expect(surface.querySelectorAll('.card-projection-segment-row')).toHaveLength(3);

    const technicalDetails = surface.querySelector('.card-projection-technical-details');
    expect(technicalDetails).not.toHaveAttribute('open');
    expect(technicalDetails).toHaveTextContent('assignment_id：501');
    expect(technicalDetails).toHaveTextContent('staff_id：101');
    expect(technicalDetails).toHaveTextContent('sequence：1');
    expect(technicalDetails).toHaveTextContent('資料來源：Scheduling；版本：7');
  });

  it('creates a zero-write terms Preview from editable typed fields', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    await screen.findByDisplayValue('2026-09-01');
    fireEvent.click(screen.getByRole('button', { name: /檢查訂單條款變更/ }));
    await screen.findByText(/條款變更前後/);
    expect(screen.getByText('變更原因（稽核必填）')).toBeInTheDocument();
    expect(orderTermsMutationClient.preview).toHaveBeenCalledWith(
      'ORD-2026-0801',
      expect.objectContaining({
        proposed_terms: expect.objectContaining({
          service_days: 30,
          service_hours_per_day: 9,
          requires_cooking: true,
        }),
      }),
    );
    expect(screen.getByRole('button', { name: /確認套用訂單條款/ })).toBeDisabled();
  });

  it('queries and previews cancellation effects while gating Apply behind reason and confirmation', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByText(/實際開始日：尚未開始/);
    expect(screen.queryByRole('button', { name: '新增實際服務日' })).not.toBeInTheDocument();
    expect(orderCancellationClient.query).toHaveBeenCalledWith('ORD-2026-0801', expect.any(AbortSignal));
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));
    await screen.findByText(/取消影響預覽/);
    expect(orderCancellationClient.preview).toHaveBeenCalledWith('ORD-2026-0801', [], expect.any(AbortSignal));
    expect(screen.getByText(/客戶帳務：0 筆調整/)).toBeInTheDocument();
    expect(screen.getByText(/服務人員薪資：0 筆調整/)).toBeInTheDocument();
    expect(screen.getByText(/客戶帳務：0 筆調整/).closest('.cancellation-calc-box')?.querySelector('details')).not.toHaveAttribute('open');
    expect(screen.getByRole('button', { name: /確認執行取消/ })).toBeDisabled();
    expect(document.body.textContent).not.toContain('preview_fingerprint');
    expect(document.body.textContent).not.toContain('NT$ 18,000');
    expect(ordersQueryClient.getAssignmentPlan).not.toHaveBeenCalled();
  });

  it('blocks a second cancellation when the fresh lifecycle query is already cancelled', async () => {
    useOperableSummary();
    vi.mocked(orderCancellationClient.query).mockResolvedValueOnce({
      ...cancellationQuery,
      lifecycle_status: '訂單取消',
    });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));

    expect(await screen.findByText('此案件已取消，不可再次取消；如需處理請改走受控重開。')).toBeInTheDocument();
    expect(screen.getByText('🚫 不可再次取消')).toBeInTheDocument();
    expect(screen.queryByText('🟠 歷史服務事實可補登')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /預覽取消與退款試算/ })).toBeDisabled();
    expect(orderCancellationClient.preview).not.toHaveBeenCalled();
  });

  it('allows historical mid-service remediation only when the server flag is true', async () => {
    useOperableSummary();
    vi.mocked(orderCancellationClient.query).mockResolvedValueOnce({
      ...cancellationQuery,
      lifecycle_status: '訂單取消',
      service_started: false,
      historical_mid_service_confirmation_available: true,
      confirmed_service_days: [],
      caregiver_options: [{ staff_id: 101, display_name: '歷史月嫂（已離職）' }],
    });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));

    expect(await screen.findByText('🟠 歷史服務事實可補登')).toBeInTheDocument();
    expect(screen.queryByText('此案件已取消，不可再次取消；如需處理請改走受控重開。')).not.toBeInTheDocument();
    const addServiceDayButton = screen.getByRole('button', { name: '新增實際服務日' });
    fireEvent.click(addServiceDayButton);
    fireEvent.click(addServiceDayButton);
    const dateInputs = document.querySelectorAll<HTMLInputElement>('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: '2026-08-01' } });
    fireEvent.change(dateInputs[1], { target: { value: '2026-08-02' } });
    const caregiverSelects = screen.getAllByRole('combobox');
    expect(caregiverSelects).toHaveLength(2);
    fireEvent.change(caregiverSelects[0], { target: { value: '101' } });
    fireEvent.change(caregiverSelects[1], { target: { value: '101' } });
    fireEvent.change(screen.getByLabelText('第 1 日人工原因'), { target: { value: '歷史服務日一' } });
    fireEvent.change(screen.getByLabelText('第 2 日人工原因'), { target: { value: '歷史服務日二' } });
    const previewButton = screen.getByRole('button', { name: /預覽取消與退款試算/ });
    expect(previewButton).not.toBeDisabled();
    fireEvent.click(previewButton);
    await screen.findByText(/取消影響預覽/);
    expect(orderCancellationClient.preview).toHaveBeenCalledWith(
      'ORD-2026-0801',
      [
        { service_date: '2026-08-01', staff_id: 101, reason: '歷史服務日一' },
        { service_date: '2026-08-02', staff_id: 101, reason: '歷史服務日二' },
      ],
      expect.any(AbortSignal),
    );
    fireEvent.change(screen.getByLabelText('人工取消原因'), { target: { value: '補登歷史服務事實' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對本次取消日期/ }));
    expect(screen.getByRole('button', { name: /確認執行取消/ })).not.toBeDisabled();
  });

  it('shows the backend cancellation preview blocker instead of a generic failure', async () => {
    useOperableSummary();
    vi.mocked(orderCancellationClient.preview).mockRejectedValueOnce(
      new ApiHttpError(
        409,
        'cancellation_actual_service_facts_required',
        '服務已開始時，請先確認至少一日實際服務資料。',
      ),
    );

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByText(/實際開始日：尚未開始/);
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));

    expect(
      await screen.findByText('服務已開始時，請先確認至少一日實際服務資料。'),
    ).toBeInTheDocument();
  });

  it('locks the cancellation drawer while Apply is unresolved and rejects case switching', async () => {
    useOperableSummary();
    let resolveApply: ((value: Awaited<ReturnType<typeof orderCancellationClient.apply>>) => void) | undefined;
    const pendingApply = new Promise<Awaited<ReturnType<typeof orderCancellationClient.apply>>>((resolve) => {
      resolveApply = resolve;
    });
    vi.mocked(orderCancellationClient.apply).mockReturnValueOnce(pendingApply);

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByText(/實際開始日：尚未開始/);
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));
    await screen.findByText(/取消影響預覽/);
    fireEvent.change(screen.getByLabelText('人工取消原因'), { target: { value: '客戶電話確認取消' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對本次取消日期/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認執行取消/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /正在套用取消/ })).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Close drawer' })).toBeDisabled();

    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[1]);
    expect(screen.getByRole('button', { name: /正在套用取消/ })).toBeInTheDocument();

    resolveApply?.({
      case_no: 'ORD-2026-0801', order_version: 1, scheduling_version: 1,
      scheduling_generation: 1, client_finance_version: 1, payroll_version: 1,
      lifecycle_status: '訂單取消', actual_end_date: null,
      official_service_day_count: 0, official_service_hours: 0,
      cancelled_assignment_ids: [], created_assignment_keys: [],
      preview_fingerprint: 'a'.repeat(64),
    });
    await screen.findByText(/訂單取消已完成/);
  });

  it('retries an unknown cancellation outcome with the original payload and idempotency key', async () => {
    useOperableSummary();
    vi.spyOn(orderCancellationClient, 'receipt').mockRejectedValueOnce(
      new ApiHttpError(404, 'order_cancellation_receipt_not_found', 'receipt not found'),
    );
    vi.mocked(orderCancellationClient.apply)
      .mockRejectedValueOnce(new Error('network timeout'))
      .mockResolvedValueOnce({
        case_no: 'ORD-2026-0801', order_version: 1, scheduling_version: 1,
        scheduling_generation: 1, client_finance_version: 1, payroll_version: 1,
        lifecycle_status: '訂單取消', actual_end_date: null,
        official_service_day_count: 0, official_service_hours: 0,
        cancelled_assignment_ids: [], created_assignment_keys: [],
        preview_fingerprint: 'a'.repeat(64),
      });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByText(/實際開始日：尚未開始/);
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));
    await screen.findByText(/取消影響預覽/);
    fireEvent.change(screen.getByLabelText('人工取消原因'), { target: { value: '客戶電話確認取消' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對本次取消日期/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認執行取消/ }));
    const unknownResult = await screen.findByText(/取消結果未明/);
    expect(unknownResult).not.toHaveTextContent(/receipt|Idempotency|Apply/i);
    const firstCall = vi.mocked(orderCancellationClient.apply).mock.calls[0];
    fireEvent.click(screen.getByRole('button', { name: /以相同內容重新確認取消/ }));
    await screen.findByText(/訂單取消已完成/);
    const secondCall = vi.mocked(orderCancellationClient.apply).mock.calls[1];
    expect(secondCall?.[2].idempotencyKey).toBe(firstCall?.[2].idempotencyKey);
    expect(secondCall?.[1]).toEqual(firstCall?.[1]);
  });

  it('reconciles an unknown cancellation outcome by receipt before owner card and stage readback', async () => {
    useOperableSummary();
    vi.mocked(orderCancellationClient.apply).mockRejectedValueOnce(new Error('network timeout'));
    vi.spyOn(orderCancellationClient, 'receipt').mockResolvedValueOnce({
      case_no: 'ORD-2026-0801', order_version: 1, scheduling_version: 1,
      scheduling_generation: 1, client_finance_version: 1, payroll_version: 1,
      lifecycle_status: '訂單取消', actual_end_date: null,
      official_service_day_count: 0, official_service_hours: 0,
      cancelled_assignment_ids: [], created_assignment_keys: [],
      preview_fingerprint: 'a'.repeat(64),
    });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByText(/實際開始日：尚未開始/);
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));
    await screen.findByText(/取消影響預覽/);
    fireEvent.change(screen.getByLabelText('人工取消原因'), { target: { value: '客戶電話確認取消' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對本次取消日期/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認執行取消/ }));
    await screen.findByText(/取消結果未明/);

    const apply = vi.mocked(orderCancellationClient.apply);
    const firstApply = apply.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: /以相同內容重新確認取消/ }));
    await screen.findByText(/訂單取消已完成/);
    expect(orderCancellationClient.receipt).toHaveBeenCalledWith(
      'ORD-2026-0801',
      expect.any(String),
      expect.any(AbortSignal),
    );
    expect(apply).toHaveBeenCalledTimes(firstApply);
    expect(orderCancellationClient.query).toHaveBeenCalledWith('ORD-2026-0801');
    expect(vi.mocked(orderCardProjectionClient.getCardProjection).mock.calls.length).toBeGreaterThan(1);
    expect(vi.mocked(orderStageProjectionClient.getOperationalTimelines).mock.calls.length).toBeGreaterThan(1);
  });

  it('keeps an unknown cancellation outcome unresolved without POST when receipt lookup fails', async () => {
    useOperableSummary();
    vi.mocked(orderCancellationClient.apply).mockRejectedValueOnce(new Error('network timeout'));
    vi.spyOn(orderCancellationClient, 'receipt').mockRejectedValueOnce(
      new ApiHttpError(500, 'receipt_lookup_failed', 'receipt lookup failed'),
    );

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByText(/實際開始日：尚未開始/);
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));
    await screen.findByText(/取消影響預覽/);
    fireEvent.change(screen.getByLabelText('人工取消原因'), { target: { value: '客戶電話確認取消' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /我已核對本次取消日期/ }));
    fireEvent.click(screen.getByRole('button', { name: /確認執行取消/ }));
    await screen.findByText(/取消結果未明/);
    const applyCalls = vi.mocked(orderCancellationClient.apply).mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: /以相同內容重新確認取消/ }));
    const unresolvedResult = await screen.findByText(/尚無法確認原操作結果/);
    expect(unresolvedResult).not.toHaveTextContent(/receipt|Idempotency|Apply/i);
    expect(vi.mocked(orderCancellationClient.apply)).toHaveBeenCalledTimes(applyCalls);
    expect(screen.queryByText(/訂單取消已完成/)).not.toBeInTheDocument();
  });

  it('edits an in-service day and caregiver with a required change reason before Preview', async () => {
    useOperableSummary();
    vi.mocked(orderCancellationClient.query).mockResolvedValueOnce({
      ...cancellationQuery,
      actual_start_date: '2026-08-01',
      service_started: true,
      confirmed_service_days: [{ service_date: '2026-08-20', staff_id: 101, reason: null }],
      caregiver_options: [{ staff_id: 101, display_name: '原月嫂' }, { staff_id: 202, display_name: '替代月嫂' }],
    });
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: /訂單取消、退款與受控重開/ }));
    await screen.findByDisplayValue('2026-08-20');
    fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: '202' } });
    fireEvent.change(screen.getByRole('textbox', { name: '第 1 日人工原因' }), { target: { value: '實際照護人員更換' } });
    fireEvent.click(screen.getByRole('button', { name: /預覽取消與退款試算/ }));
    await screen.findByText(/取消影響預覽/);
    expect(orderCancellationClient.preview).toHaveBeenCalledWith(
      'ORD-2026-0801',
      [{ service_date: '2026-08-20', staff_id: 202, reason: '實際照護人員更換' }],
      expect.any(AbortSignal),
    );
  });

  it('loads the two owned date workflows without unrelated detail projections', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    await act(async () => fireEvent.click(screen.getByRole('button', { name: /實質服務日曆/ })));
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledOnce());
    expect(ordersQueryClient.getOrderCalendarDetail).toHaveBeenCalledOnce();
    expect(ordersQueryClient.getActualStart).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('最新根事實版本')).not.toBeInTheDocument();
  });

  it('exposes an editable actual-start Preview while Apply remains reason-gated', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    await act(async () => fireEvent.click(screen.getByRole('button', { name: /實質服務日曆/ })));
    await screen.findByDisplayValue('2026-09-01');
    fireEvent.click(screen.getByRole('button', { name: '預覽實際開工日變更' }));
    await screen.findByText('實際開工日影響已確認');
    expect(screen.getByText('套用原因（稽核必填）')).toBeInTheDocument();
    expect(orderActualStartClient.preview).toHaveBeenCalledWith(
      'ORD-2026-0801',
      { new_actual_start_date: '2026-09-01' },
    );
    expect(screen.getByRole('button', { name: '確認套用實際開工日' })).toBeDisabled();
  });

  it('creates a server-validated multi-caregiver plan from the fallback control', async () => {
    useOperableSummary();
    const availability: MatchingAvailability = {
      case_no: 'ORD-2026-0801', planned_start_date: '2026-08-01', planned_end_date: '2026-08-30',
      feasibility: 'complete',
      complete_combinations: [[
        { segment_index: 0, staff_id: 8892, start_date: '2026-08-01', end_date: '2026-08-15' },
        { segment_index: 1, staff_id: 8893, start_date: '2026-08-16', end_date: '2026-08-30' },
      ]],
      segment_candidates: [], candidate_options: [], conflicts: [],
    };
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSingleCaregiver').mockResolvedValue({
      ...availability,
      complete_combinations: [],
      candidate_options: [],
    });
    vi.spyOn(matchingCandidateWorkflowClient, 'searchSegmentedCaregivers').mockResolvedValue(availability);
    vi.spyOn(matchingCandidateWorkflowClient, 'createMatchingPlan').mockResolvedValue({
      plan_id: 52, case_no: 'ORD-2026-0801', version: 1, status: 'proposed', result: 'created',
      segments: [
        { segment_order: 1, staff_id: 8892, assigned_start_date: '2026-08-01', assigned_end_date: '2026-08-15' },
        { segment_order: 2, staff_id: 8893, assigned_start_date: '2026-08-16', assigned_end_date: '2026-08-30' },
      ],
    });
    vi.mocked(waitingDepositLockClient.queryPlan)
      .mockRejectedValueOnce(new ApiHttpError(404, 'HTTP_404', 'active matching plan not found'))
      .mockResolvedValue({ planId: 52, status: 'proposed', activeLockId: null });

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]);
    fireEvent.click(await screen.findByRole('button', { name: '🔍 重新查詢符合條件月嫂' }));
    fireEvent.click(await screen.findByRole('button', { name: '查詢多月嫂連續分段備案' }));
    await screen.findByText('備案 1');
    fireEvent.click(screen.getByRole('button', { name: '建立此 2 段正式多月嫂方案' }));

    await screen.findByText('正式 2 段多月嫂方案已建立並完成回讀。');
    expect(matchingCandidateWorkflowClient.searchSegmentedCaregivers).toHaveBeenCalledWith(
      'ORD-2026-0801',
      2,
      [],
      { region: true, cooking: true, preferred_service_days: true, daily_service_hours: true },
    );
    expect(matchingCandidateWorkflowClient.createMatchingPlan).toHaveBeenCalledWith('ORD-2026-0801', [
      { staff_id: 8892, start_date: '2026-08-01', end_date: '2026-08-15' },
      { staff_id: 8893, start_date: '2026-08-16', end_date: '2026-08-30' },
    ]);
  });
});
