/**
 * File: orders_page_real_data.test.tsx
 * Description: 驗證 OrdersPage 契約與 active-plan 查詢的 fail-closed、404 與合法空狀態。
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
import { realisticServiceDateQueryView } from './fixtures/orders/order_mutation_contract_fixtures';
import { buildOrdersStageProjectionFixture } from './fixtures/orders_stage_projection_fixtures';

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
      cancellation_date: '2026-08-23', actual_end_date: null, confirmed_service_days: [],
      official_service_day_count: 0, official_service_hours: 0, order_version: 0,
      scheduling_version: 0, scheduling_generation: 0, client_finance_version: 0,
      payroll_version: 0, scheduling: {}, client_finance_impact: {}, payroll_impact: {},
      lifecycle_impact: {}, preview_fingerprint: 'a'.repeat(64),
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

  it('continues from next_cursor and appends the next page without duplicating summaries', async () => {
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
      .mockResolvedValueOnce(buildOrdersStageProjectionFixture(firstPage))
      .mockResolvedValueOnce(buildOrdersStageProjectionFixture(secondPage));

    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getByRole('button', { name: '載入下一頁' }));

    await screen.findByText('ORD-2026-0802');
    expect(screen.getAllByText('ORD-2026-0801')).toHaveLength(1);
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenNthCalledWith(
      2,
      { after_case_no: 'ORD-2026-0801' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.queryByRole('button', { name: '載入下一頁' })).not.toBeInTheDocument();
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
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /媒合與正式排班/ })[0]));
    await screen.findByText('正式執行排班（非候選推薦）');
    expect(ordersQueryClient.getOrderDetail).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledTimes(1);
    expect(ordersQueryClient.getOrderTerms).toHaveBeenCalledTimes(1);
    expect(candidateContactPoolClient.query).toHaveBeenCalledTimes(1);
    expect(waitingDepositLockClient.queryPlan).toHaveBeenCalledTimes(1);
    expect(screen.getByText('無進行中方案')).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.matching.active-plan-query-error"]')).toBeNull();
    expect(screen.queryByText(/後端.*提供|未開放|未納入/)).not.toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: '預覽訂單條款變更' })).not.toBeInTheDocument();
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
    expect(screen.getByText(/缺少 Client Finance 契約與定金根事實/)).toBeInTheDocument();
    expect(document.querySelector('[data-surface-id="orders.contract.historical-correction"]')).toHaveAttribute('role', 'status');
    expect(document.querySelector('[data-surface-id="orders.contract.query-error"]')).toBeNull();
    expect(screen.queryByRole('button', { name: '預覽訂單條款變更' })).not.toBeInTheDocument();
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

  it('creates a zero-write terms Preview from editable typed fields', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /條款與契約/ })[0]);
    await screen.findByDisplayValue('2026-09-01');
    fireEvent.click(screen.getByRole('button', { name: '預覽訂單條款變更' }));
    await screen.findByText('Preview 已產生');
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
    expect(screen.getByRole('button', { name: '確認套用訂單條款' })).toBeDisabled();
  });

  it('queries and previews cancellation effects without exposing Apply', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /取消試算/ })[0]));
    await screen.findByText('取消前根事實');
    expect(orderCancellationClient.query).toHaveBeenCalledWith('ORD-2026-0801', expect.any(AbortSignal));
    fireEvent.click(screen.getByRole('button', { name: '產生取消預覽' }));
    await screen.findByText('取消影響預覽（零寫入）');
    expect(orderCancellationClient.preview).toHaveBeenCalledWith('ORD-2026-0801', [], expect.any(AbortSignal));
    expect(screen.queryByRole('button', { name: /確認執行取消/ })).not.toBeInTheDocument();
    expect(ordersQueryClient.getOrderDetail).not.toHaveBeenCalled();
    expect(ordersQueryClient.getAssignmentPlan).not.toHaveBeenCalled();
  });

  it('loads the two owned date workflows without unrelated detail projections', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    await act(async () => fireEvent.click(screen.getAllByRole('button', { name: /確認服務日期/ })[0]));
    await waitFor(() => expect(ordersMutationClient.getServiceDates).toHaveBeenCalledOnce());
    expect(ordersQueryClient.getOrderDetail).not.toHaveBeenCalled();
    expect(ordersQueryClient.getOrderCalendarDetail).not.toHaveBeenCalled();
    expect(ordersQueryClient.getActualStart).toHaveBeenCalledTimes(1);
    expect(screen.getByText('最新根事實版本')).toBeInTheDocument();
  });

  it('exposes an editable actual-start Preview while Apply remains reason-gated', async () => {
    useOperableSummary();
    render(<OrdersPage />);
    await screen.findByText('ORD-2026-0801');
    fireEvent.click(screen.getAllByRole('button', { name: /確認服務日期/ })[0]);
    await screen.findByDisplayValue('2026-09-01');
    fireEvent.click(screen.getByRole('button', { name: '預覽實際開工日變更' }));
    await screen.findByText('實際開工日 Preview 已產生');
    expect(orderActualStartClient.preview).toHaveBeenCalledWith(
      'ORD-2026-0801',
      { new_actual_start_date: '2026-09-01' },
    );
    expect(screen.getByRole('button', { name: '確認套用實際開工日' })).toBeDisabled();
  });
});
