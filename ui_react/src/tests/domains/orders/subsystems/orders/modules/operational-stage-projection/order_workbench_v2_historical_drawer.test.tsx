import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ComponentProps } from 'react';
import { FinancePage } from '../../../../../../../pages/FinancePage';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { historicalCompletionClient } from '../../../../../../../api/orders/historical_completion_client';
import { HistoricalCompletionSchema } from '../../../../../../../api/orders/historical_completion_schemas';
import { clientReceiptQueryClient } from '../../../../../../../api/client_finance/client_receipt_query_client';
import { accountsPayableQueryClient } from '../../../../../../../api/accounts_payable/accounts_payable_query_client';
import { RECEIPT_RESPONSE } from '../../../../../../fixtures/finance/finance_query_contract_fixtures';
import { HistoricalOrderAdoptionEvidenceSchema } from '../../../../../../../api/orders/historical_adoption_evidence_schemas';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS, type CoreStageCode } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import { OrderWorkbenchV2Drawer } from '../../../../../../../components/OrderWorkbenchV2Drawer';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({
  core: vi.fn(),
  detail: vi.fn(),
  terms: vi.fn(),
  assignment: vi.fn(),
  evidence: vi.fn(),
  baseline: vi.fn(),
  accounting: vi.fn(),
  intakeCompletion: vi.fn(),
  intakeApply: vi.fn(),
  restartQuery: vi.fn(),
  restartPreview: vi.fn(),
  restartApply: vi.fn(),
  serviceDatesRender: vi.fn(),
  actualStartRender: vi.fn(),
  matchingPlan: vi.fn(),
  matchingContact: vi.fn(),
  matchingPreview: vi.fn(),
  candidatePool: vi.fn(),
  summaries: vi.fn(),
  getStart: vi.fn(), getCalendar: vi.fn(), previewStart: vi.fn(), applyStart: vi.fn(),
  getDates: vi.fn(), calculate: vi.fn(), previewDates: vi.fn(), applyDates: vi.fn(),
}));
const dateWorkspace = vi.hoisted(() => ({ live: false }));

vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core },
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: mocks.summaries,
  ordersQueryClient: {
    getOrderDetail: mocks.detail,
    getOrderTerms: mocks.terms,
    getAssignmentPlan: mocks.assignment,
    getOrderSummaries: vi.fn(),
    getActualStart: mocks.getStart,
    getOrderCalendarDetail: mocks.getCalendar,
  },
}));
vi.mock('../../../../../../../api/orders/order_actual_start_client', () => ({ orderActualStartClient: { preview: mocks.previewStart, apply: mocks.applyStart } }));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({ ordersMutationClient: { getServiceDates: mocks.getDates, previewServiceDates: mocks.previewDates, applyServiceDates: mocks.applyDates } }));
vi.mock('../../../../../../../api/scheduling/schedule_precision_client', () => ({ schedulePrecisionClient: { calculate: mocks.calculate } }));
vi.mock('../../../../../../../api/client_finance/deposit_skip_client', () => ({ depositSkipClient: {
  query: vi.fn(async (caseNo: string) => ({ case_no: caseNo, deposit_required_ntd: 0, deposit_net_received_ntd: 0, unpaid_progression_allowed: false, blockers: ['deposit_skip.deposit_obligation_required'] })),
  preview: vi.fn(), apply: vi.fn(),
} }));
vi.mock('../../../../../../../api/scheduling/service_arrangement_status_client', () => ({ serviceArrangementStatusClient: {
  completion: vi.fn(async (caseNo: string) => ({ case_no: caseNo, current_status: '訂單成立', completion_instant: null, state: 'awaiting_schedule', blockers: [] })),
} }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({
  waitingDepositLockClient: { queryPlan: mocks.matchingPlan },
}));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({
  matchingPlanCommunicationClient: { queryContactState: mocks.matchingContact, previewCustomerConfirmation: mocks.matchingPreview },
}));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: { query: mocks.candidatePool },
}));
vi.mock('../../../../../../../api/orders/historical_adoption_evidence_client', () => ({
  historicalAdoptionEvidenceClient: { queryByCase: mocks.evidence },
}));
vi.mock('../../../../../../../api/orders/historical_operational_baseline_client', () => ({
  historicalOperationalBaselineClient: { queryByCase: mocks.baseline },
}));
vi.mock('../../../../../../../api/orders/historical_service_accounting_client', () => ({
  historicalServiceAccountingClient: {
    query: mocks.accounting,
    queryPrecisionRestart: mocks.restartQuery,
    previewPrecisionRestart: mocks.restartPreview,
    applyPrecisionRestart: mocks.restartApply,
  },
}));
vi.mock('../../../../../../../components/OrderServiceDatesPanel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../../../../components/OrderServiceDatesPanel')>();
  return { OrderServiceDatesPanel: (props: ComponentProps<typeof actual.OrderServiceDatesPanel>) => {
    mocks.serviceDatesRender(props);
    return dateWorkspace.live ? <div aria-label="服務日期精算工作區"><actual.OrderServiceDatesPanel {...props} /></div> : <div aria-label="服務日期精算工作區">服務日期精算已開啟</div>;
  } };
});
vi.mock('../../../../../../../components/OrderActualStartPanel', () => ({
  OrderActualStartPanel: (props: { onObserved?: (operation: 'date_only' | 'reschedule') => void; onOpenServiceDates?: () => void }) => {
    mocks.actualStartRender(props);
    return <>
      <button type="button" onClick={props.onOpenServiceDates}>模擬尚未建立排班</button>
      <button type="button" onClick={() => props.onObserved?.('date_only')}>模擬實際開始日正式回讀成功</button>
    </>;
  },
}));
vi.mock('../../../../../../../api/orders/order_intake_completion_client', async () => {
  const actual = await vi.importActual<typeof import('../../../../../../../api/orders/order_intake_completion_client')>(
    '../../../../../../../api/orders/order_intake_completion_client',
  );
  return {
    ...actual,
    orderIntakeCompletionClient: {
      ...actual.orderIntakeCompletionClient,
      previewCompletion: mocks.intakeCompletion,
      applyCompletion: mocks.intakeApply,
    },
  };
});

function stage(code: CoreStageCode, index: number) {
  const baseline = index < 8;
  const current = code === 'confirmed_service_dates';
  const status = baseline ? 'completed' : current ? 'in_progress' : 'not_started';
  return {
    ordinal: index + 1,
    code,
    label: code === 'confirmed_service_dates' ? '服務日期確認' : code,
    owner: baseline ? 'Historical Orders' : current ? 'Orders / Scheduling' : `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: {
      owner: baseline ? 'Historical Orders' : current ? 'Orders / Scheduling' : `source-${code}`,
      identity: baseline ? 'baseline:event:9' : `${code}:CASE-FUTURE`,
      version: 9,
    },
    occurred_at: null,
    blockers: [],
    warnings: baseline ? [{ code: 'historical_baseline_completed', message: '歷史訂單已略過此前置作業；未補造原流程 owner 事件。' }] : [],
    available_read_actions: current ? [{ action_id: 'orders.terms.query', method: 'GET', path: '/api/v1/orders/CASE-FUTURE/terms' }] : [],
    availability_reason: null,
  };
}

function timeline(lifecycleStatus = '歷史訂單－未服務') {
  return {
    case_no: 'CASE-FUTURE',
    base_revision: 12,
    lifecycle_status: lifecycleStatus,
    branch_type: 'historical',
    current_core_stage_code: null,
    current_core_stage_ordinal: null,
    historical_current_owner_stage_code: 'confirmed_service_dates',
    historical_current_owner_stage_ordinal: 9,
    core_stages: CORE_STAGE_CODES.map(stage),
    source_projection_digest: 'a'.repeat(64),
  };
}

function canonicalEvidence() {
  return {
    case_no: 'CASE-FUTURE',
    receipt_id: 77,
    receipt_identity: 'historical-order-adoption-receipt:77',
    evidence_owner: 'Historical Orders Adoption',
    source_identity: 'historical-orders:sheet:row:17',
    source_fingerprint: 'c'.repeat(64),
    preview_fingerprint: 'd'.repeat(64),
    historical_source_status: 'deposit_paid',
    operational_baseline_step: 9,
    source_start_date: '2026-09-03',
    source_end_date: '2026-09-22',
    source_period_availability: 'available',
    paired_staff: [{
      caregiver_ordinal: 1,
      staff_name: '陳月嫂',
      staff_id: 42,
      resolution: 'evidence_only',
      source_start_date: '2026-09-03',
      source_end_date: '2026-09-22',
      assignment_id: null,
    }],
    paired_staff_availability: 'available',
  };
}

function orderDetail(orderStatus = '歷史訂單－未服務') {
  return {
    case_no: 'CASE-FUTURE', client_id: 1, staff_id: null, client_name: '正式客戶', staff_name: null,
    order_status: orderStatus, identity_status: '一般市民', cancel_reason: null, line_group_id: null,
    contract_identity: null, actual_start_date: null, actual_end_date: null, deposit_date: null,
    start_date: '2026-09-03', end_date: '2026-09-22', service_days: 20, service_hours_per_day: 9,
    deposit_service_days: null, floor_fee: 0, custom_rest_dates: null,
  };
}

function useLiveDateWorkspace() {
  dateWorkspace.live = true;
  sessionClient.setSession('synthetic-historical-workspace', { id: 7, username: 'historical-test', display_name: '測試工會人員', role: 'admin' });
  let orderVersion = 12;
  let actualStart: string | null = null;
  const days = (start: string, count: number) => Array.from({ length: count }, (_, i) => new Date(Date.parse(`${start}T00:00:00Z`) + i * 86400000).toISOString().slice(0, 10));
  const terms = mocks.terms.getMockImplementation()!;
  mocks.terms.mockImplementation(async () => ({ ...await terms(), order_version: orderVersion }));
  const restart = mocks.restartApply.getMockImplementation()!;
  mocks.restartApply.mockImplementation(async (...args) => { const receipt = await restart(...args); orderVersion = receipt.order_version; return receipt; });
  mocks.getStart.mockImplementation(async () => ({ case_no: 'CASE-FUTURE', current_actual_start_date: actualStart, planned_start_date: '2026-09-03', service_data_locked: false,
    order_version: orderVersion, scheduling_version: 4, scheduling_generation: 2, client_finance_version: 2, payroll_version: 2, has_formal_assignments: false }));
  mocks.getCalendar.mockResolvedValue({ case_no: 'CASE-FUTURE', service_mode: '連續服務', original_service_type: '連續服務' });
  mocks.getDates.mockImplementation(async () => ({ case_no: 'CASE-FUTURE', order_version: orderVersion, scheduling_version: 4,
    contracted_service_days: 20, suggested_dates: [], selectable_dates: days(actualStart ?? '2026-09-03', 40), current_version: null,
    current_dates: [], bound_staff: [{ staff_id: 42, staff_name: '陳月嫂' }], arrangement_pending: true }));
  mocks.calculate.mockImplementation(async ({ actual_start_date }) => ({ actual_start_date, actual_end_date: days(actual_start_date, 20)[19], target_service_days: 20,
    total_calendar_days: 20, actual_work_days_count: 20, rest_days_count: 0, national_holidays_found: [], total_estimated_salary: null, weekly_stats: [],
    day_by_day: days(actual_start_date, 20).map((date, i) => ({ date, day_num: i + 1, is_work_day: true, is_rest_day: false, holiday_name: null })) }));
  mocks.previewStart.mockImplementation(async (_caseNo, { new_actual_start_date }) => ({ operation: 'date_only', case_no: 'CASE-FUTURE', before_actual_start_date: actualStart,
    after_actual_start_date: new_actual_start_date, order_version: orderVersion, scheduling_version: 4, scheduling_generation: 2,
    client_finance_version: 2, payroll_version: 2, preview_fingerprint: '2'.repeat(64) }));
  mocks.applyStart.mockImplementation(async (caseNo, payload) => {
    expect(caseNo).toBe('CASE-FUTURE');
    expect(payload.expected_order_version).toBe(orderVersion);
    expect(payload.preview_fingerprint).toBe('2'.repeat(64));
    actualStart = payload.new_actual_start_date; orderVersion++;
    mocks.detail.mockResolvedValue({ ...orderDetail('訂單成立'), actual_start_date: actualStart });
    return { operation: 'date_only', case_no: caseNo, actual_start_date: actualStart, order_version: orderVersion,
      scheduling_version: 4, scheduling_generation: 2, client_finance_version: 2, payroll_version: 2, preview_fingerprint: payload.preview_fingerprint, changed: true };
  });
}

describe('historical Drawer immutable evidence boundary', () => {
  it('從同案帳務頁 Query／Preview／Confirm／Apply，回到案件後回讀完成狀態並移除操作', async () => {
    let status = '歷史訂單－服務完成';
    mocks.core.mockImplementation(async () => ({ items: [timeline(status)] }));
    mocks.detail.mockImplementation(async () => orderDetail(status));
    mocks.summaries.mockImplementation(async () => ({ items: [{ case_no: 'CASE-FUTURE', client_name: '正式客戶', order_status: status,
      staff_name: null, identity_status: null, start_date: '2026-09-03', end_date: '2026-09-22', actual_start_date: null, actual_end_date: null,
      service_days: 20, total_employer_self_pay_payable: null }], next_cursor: null, etag: 'a'.repeat(64) }));
    vi.spyOn(clientReceiptQueryClient, 'query').mockResolvedValue({ ...RECEIPT_RESPONSE.data, case_no: 'CASE-FUTURE' });
    vi.spyOn(accountsPayableQueryClient, 'queryCase').mockResolvedValue({ case_no: 'CASE-FUTURE', target_payment_date: '2026-09-01', items: [] });
    const projection = HistoricalCompletionSchema.parse({ case_no: 'CASE-FUTURE', state: 'completed', step_11_status: 'completed', step_11_completed: true,
      historical_alerts_completed: true, active_alerts: [], owner_versions: [{ owner: 'orders', version: '12' }, { owner: 'client_finance', version: '2' }],
      owner_source_versions: [{ kind: 'staff_obligation', identity: 'obligation:17', version: '2' }], source_fingerprint: 'a'.repeat(64), projection_fingerprint: 'b'.repeat(64) });
    const query = vi.spyOn(historicalCompletionClient, 'query').mockResolvedValue(projection);
    const preview = { case_no: 'CASE-FUTURE', before_status: '歷史訂單－服務完成' as const, after_status: '歷史訂單－帳務完成' as const,
      expected_order_version: '12', resulting_order_version: '13', expected_client_finance_version: '2', expected_source_versions: projection.owner_source_versions,
      business_date: '2026-09-01', preview_fingerprint: 'c'.repeat(64) };
    const previewQuery = vi.spyOn(historicalCompletionClient, 'preview').mockResolvedValue(preview);
    const apply = vi.spyOn(historicalCompletionClient, 'apply').mockImplementation(async () => {
      status = '歷史訂單－帳務完成';
      return { case_no: 'CASE-FUTURE', lifecycle_event_id: 99, resulting_order_version: '13', after_status: '歷史訂單－帳務完成', replayed: false };
    });
    const onObserved = vi.fn();
    const view = render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} onObserved={onObserved} />);
    await screen.findByRole('heading', { name: '服務完工' });
    const entry = screen.getByRole('link', { name: '查看本案帳務 →' });
    expect(entry).toHaveAttribute('href', '#finance?tab=client-receipts&case_no=CASE-FUTURE&from=workbench');
    const readsBefore = mocks.core.mock.calls.length;
    act(() => window.history.replaceState(null, '', entry.getAttribute('href')!));
    view.rerender(<FinancePage />);
    fireEvent.click(await screen.findByRole('button', { name: '預覽並確認帳務完成' }));
    const confirm = await screen.findByRole('button', { name: '確認推進至帳務完成' });
    expect(confirm).toBeDisabled();
    expect(apply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: '我已確認客戶款項及所有月嫂款項均已結清' }));
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() => expect(mocks.summaries).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole('button', { name: '確認推進至帳務完成' })).not.toBeInTheDocument());
    expect(query).toHaveBeenCalledWith('CASE-FUTURE', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(previewQuery).toHaveBeenCalledWith('CASE-FUTURE');
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(preview, '確認歷史訂單客戶款項及月嫂款項皆已結清');
    expect(mocks.summaries.mock.invocationCallOrder.at(-1)).toBeGreaterThan(apply.mock.invocationCallOrder[0]!);
    const returnEntry = screen.getByRole('link', { name: '← 返回案件處理' });
    expect(returnEntry).toHaveAttribute('href', '#order-workbench-v2?case=CASE-FUTURE');
    act(() => window.history.replaceState(null, '', returnEntry.getAttribute('href')!));
    view.rerender(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} onObserved={onObserved} />);
    await screen.findByRole('heading', { name: '服務完工' });
    expect(mocks.core.mock.calls.length).toBeGreaterThan(readsBefore);
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.getAllByText(/歷史訂單－帳務完成/).length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: '確認推進至帳務完成' })).not.toBeInTheDocument();
  });

  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    dateWorkspace.live = false;
    orderMutationFlowStore.clearAll();
    mocks.matchingPlan.mockRejectedValue(new ApiHttpError(404, 'not_found', '尚無有效媒合方案'));
    mocks.core.mockResolvedValue({
      items: [timeline()],
      stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0])),
      substatus_counts: {},
      historical_lifecycle_counts: { unserved: 1, in_service: 0, service_completed: 0, accounting_completed: 0 },
      next_cursor: null,
      etag: 'b'.repeat(64),
    });
    mocks.detail.mockResolvedValue(orderDetail());
    mocks.terms.mockResolvedValue({
      case_no: 'CASE-FUTURE', order_version: 12, scheduling_version: 4, scheduling_generation: 1,
      client_finance_version: 2, payroll_version: 2, service_data_locked: false,
      terms: {
        planned_start_date: '2026-09-03', service_days: 20, service_hours_per_day: 9,
        requires_cooking: null, floor_fee_ntd: 0,
        service_time: { start_time: null, end_time: null, end_day_offset: null },
      },
    });
    mocks.assignment.mockResolvedValue({
      case_no: 'CASE-FUTURE', order_version: 12, scheduling_version: 4, scheduling_generation: 1,
      client_finance_version: 2, payroll_version: 2, contracted_service_days: 20, service_hours_per_day: 9,
      service_started: false, assignments: [],
    });
    mocks.evidence.mockResolvedValue(canonicalEvidence());
    mocks.baseline.mockResolvedValue({
      order_identity: 'order:CASE-FUTURE', case_no: 'CASE-FUTURE',
      historical_provenance: { source_event_identity: 'historical-source:17', source_version: 1 },
      current_orders_version: 12, baseline_binding_fingerprint: 'e'.repeat(64),
      current_baseline: {
        baseline_event_identity: 'baseline:event:9', selected_step: 9, resulting_orders_version: 12,
        resulting_owner_binding_fingerprint: 'f'.repeat(64),
        step_projection: Array.from({ length: 9 }, (_, index) => ({
          step: index + 1,
          state: index < 8 ? 'historical_baseline_completed' : 'in_progress',
        })),
      },
      allowed_steps: Array.from({ length: 11 }, (_, index) => index + 1),
      evidence_modes: ['retained', 'historical_evidence_unavailable_accepted'],
    });
    mocks.accounting.mockResolvedValue({
      case_no: 'CASE-FUTURE', lifecycle_status: '歷史訂單－未服務', lifecycle_version: 12,
      adoption_receipt_id: 77, adoption_source_identity: 'historical-orders:sheet:row:17',
      historical_day_revision: 0, client_finance_version: 2, payroll_version: 2,
      contracted_service_days: 20, service_hours_per_day: 9, contractual_floor_fee_ntd: 0,
      client_identity_status: '一般市民', assignments: [],
    });
    mocks.intakeCompletion.mockResolvedValue({
      case_no: 'CASE-FUTURE', missing_fields: ['client_name', 'start_date'],
      blockers: ['order_lifecycle_not_intake'], apply_allowed: false,
    });
    const restartQuery = {
      case_no: 'CASE-FUTURE', lifecycle_status: '歷史訂單－未服務',
      order_version: 12, scheduling_version: 4, client_finance_version: 2, payroll_version: 2,
      historical_day_revision: 0, confirmed_service_date_version: null,
      planned_start_date: '2026-09-03', actual_start_date: null, contracted_service_days: 20,
      assignments: [], blockers: [],
    };
    mocks.restartQuery.mockResolvedValue(restartQuery);
    mocks.restartPreview.mockResolvedValue({
      ...restartQuery, target_status: '訂單成立', actual_end_date: null, official_service_dates: [],
      client_finance_resulting_version: 2, payroll_resulting_version: 2, preview_fingerprint: '1'.repeat(64),
    });
    mocks.restartApply.mockImplementation(async () => {
      mocks.detail.mockResolvedValue(orderDetail('訂單成立'));
      mocks.core.mockResolvedValue({
        items: [{ ...timeline('訂單成立'), branch_type: 'normal' }],
        stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0])),
        substatus_counts: {},
        historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 },
        next_cursor: null,
        etag: 'c'.repeat(64),
      });
      return {
        case_no: 'CASE-FUTURE', lifecycle_status: '訂單成立', order_version: 13,
        scheduling_version: 5, scheduling_generation: 2, client_finance_version: 2,
        payroll_version: 2, historical_day_revision: 0, preview_fingerprint: '1'.repeat(64), replayed: false,
      };
    });
  });
  afterEach(() => { sessionClient.clearSession(); orderMutationFlowStore.clearAll(); window.history.replaceState(null, '', '#'); vi.restoreAllMocks(); });

  it('future source period 與 evidence-only staff 保留在來源區，formal owner/assignment 不被覆寫', async () => {
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    const dialog = screen.getByRole('region', { name: '案件 CASE-FUTURE' });
    const ownerHeading = await within(dialog).findByRole('heading', { name: '歷史案件目前進度' });
    const ownerSection = ownerHeading.closest('section');
    if (!(ownerSection instanceof HTMLElement)) throw new Error('找不到目前正式 owner progression 區');
    expect(within(ownerSection).getByText(/服務日期確認/)).toBeInTheDocument();
    const serviceEntry = within(dialog).getByRole('button', { name: /確認服務日期與排班/ });
    await waitFor(() => expect(serviceEntry).toBeEnabled());
    fireEvent.click(serviceEntry);
    const caseHeader = within(dialog).getByRole('heading', { name: '案件處理', level: 1 }).closest('header')!;
    expect(within(caseHeader).getByText('尚未正式指派')).toBeInTheDocument();
    const evidenceRegion = within(dialog).getByRole('heading', { name: '歷史服務資料' }).closest('section')!;
    expect(within(caseHeader).queryByText(/陳月嫂/)).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('region', { name: '案件 CASE-FUTURE 正式指派與排班回讀' })).not.toBeInTheDocument();
    expect(mocks.serviceDatesRender).not.toHaveBeenCalled();
    expect(within(dialog).getAllByText('尚未確認').length).toBeGreaterThan(0);

    expect(within(evidenceRegion).getByText(/2026-09-03 → 2026-09-22/)).toBeInTheDocument();
    expect(within(evidenceRegion).getByText(/陳月嫂/)).toBeInTheDocument();
    expect(within(evidenceRegion).queryByText(/陳\*嫂/)).not.toBeInTheDocument();
    expect(within(evidenceRegion).getByText(/不代表目前已確認的服務安排/)).toBeInTheDocument();
  });

  it('shows failed formal reads as unavailable while retaining the historical source period', async () => {
    mocks.detail.mockRejectedValue(new Error('order_detail_projection_invalid'));
    mocks.terms.mockRejectedValue(new Error('client_finance_bootstrap_required'));

    const view = render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    await screen.findByText('歷史匯入期間');
    const context = view.container.querySelector('.order-case-context');
    if (!(context instanceof HTMLElement)) throw new Error('找不到案件摘要區');

    expect(context).toHaveTextContent('2026-09-03 → 2026-09-22');
    expect(context).toHaveTextContent('讀取失敗');
    expect(context).not.toHaveTextContent('讀取中');
  });

  it('strict adoption evidence contract 接受 canonical staff_name 並拒絕舊 masked 欄位', () => {
    const canonical = canonicalEvidence();
    const parsed = HistoricalOrderAdoptionEvidenceSchema.parse(canonical);
    expect(parsed.paired_staff[0]?.staff_name).toBe('陳月嫂');

    const legacy = {
      ...canonical,
      paired_staff: [{
        ...canonical.paired_staff[0],
        staff_name: undefined,
        masked_staff_name: '陳*嫂',
      }],
    };
    expect(() => HistoricalOrderAdoptionEvidenceSchema.parse(legacy)).toThrow();
  });

  it.each(['歷史訂單－未服務', '歷史訂單－服務中'])('%s keeps the blocked intake drawer open and restarts through owner Query / Preview / Apply / readback', async (status) => {
    useLiveDateWorkspace();
    mocks.detail.mockResolvedValue(orderDetail(status));
    mocks.core.mockResolvedValue({
      items: [timeline(status)],
      stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0])),
      substatus_counts: {},
      historical_lifecycle_counts: { unserved: status === '歷史訂單－未服務' ? 1 : 0, in_service: status === '歷史訂單－服務中' ? 1 : 0, service_completed: 0, accounting_completed: 0 },
      next_cursor: null,
      etag: 'b'.repeat(64),
    });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    const restart = await screen.findByRole('button', { name: '前往重啟正常流程' });
    fireEvent.click(screen.getByRole('button', { name: /確認客戶與服務需求/ }));
    const intake = screen.getByRole('region', { name: '進件缺件摘要' });
    expect(await within(intake).findByText('order_lifecycle_not_intake')).toBeInTheDocument();
    expect(within(intake).getByRole('link', { name: '前往補齊案件資料 →' })).toHaveAttribute('href', '#clients?case=CASE-FUTURE&field=intake&from=workbench');
    expect(within(intake).queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '案件 CASE-FUTURE' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /確認服務日期與排班/ }));
    fireEvent.click(restart);
    await screen.findByText(/已重啟正常流程並正式回讀；已接續到服務日期精算/);
    expect(mocks.restartQuery).toHaveBeenCalledWith('CASE-FUTURE');
    expect(mocks.restartPreview).toHaveBeenCalledWith('CASE-FUTURE');
    expect(mocks.restartApply).toHaveBeenCalledTimes(1);
    expect(mocks.restartApply).toHaveBeenCalledWith(
      expect.objectContaining({ case_no: 'CASE-FUTURE', preview_fingerprint: '1'.repeat(64) }),
      expect.stringContaining('案件處理頁'),
    );
    expect(mocks.restartQuery.mock.invocationCallOrder[0]).toBeLessThan(mocks.restartPreview.mock.invocationCallOrder[0]!);
    expect(mocks.restartPreview.mock.invocationCallOrder[0]).toBeLessThan(mocks.restartApply.mock.invocationCallOrder[0]!);
    expect(mocks.detail.mock.invocationCallOrder.at(-1)).toBeGreaterThan(mocks.restartApply.mock.invocationCallOrder[0]!);
    await waitFor(() => expect(screen.queryByRole('button', { name: '前往重啟正常流程' })).not.toBeInTheDocument());
    expect(await screen.findByLabelText('服務日期精算工作區')).toBeInTheDocument();
    expect(mocks.serviceDatesRender).toHaveBeenLastCalledWith(
      expect.objectContaining({ calculationRevision: 1 }),
    );
    const startInput = await screen.findByLabelText('實際開始日');
    await waitFor(() => expect(startInput).toHaveValue('2026-09-03'));
    expect(mocks.applyStart).not.toHaveBeenCalled();
    expect(mocks.applyDates).not.toHaveBeenCalled();
    fireEvent.change(startInput, { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /確認排班/ }));
    expect(screen.queryByRole('button', { name: '預覽正式安排' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /設定服務日期/ }));
    expect(startInput).toHaveValue('');
    expect(await screen.findByLabelText('服務日期精算工作區')).toBeInTheDocument();
    await act(async () => { fireEvent.change(startInput, { target: { value: '2026-09-04' } }); });
    await waitFor(() => expect(screen.getByLabelText('此次選定服務日期摘要')).toHaveTextContent('20 / 20 天'));
    const saveStart = screen.getByRole('button', { name: '儲存實際開始日' });
    await waitFor(() => expect(saveStart).toBeEnabled());
    fireEvent.click(saveStart);
    await screen.findByText('實際開始日已儲存；服務日期尚未儲存。');
    expect(await screen.findByLabelText('服務日期精算工作區')).toBeInTheDocument();
    await waitFor(() => expect(mocks.serviceDatesRender).toHaveBeenLastCalledWith(expect.objectContaining({ calculationRevision: 1, projectionRevision: 2 })));
    expect(mocks.applyStart).toHaveBeenCalledTimes(1);
    expect(mocks.applyStart).toHaveBeenCalledWith('CASE-FUTURE', expect.objectContaining({ operation: 'date_only', new_actual_start_date: '2026-09-04', expected_order_version: 13, preview_fingerprint: '2'.repeat(64) }), expect.objectContaining({ idempotencyKey: expect.stringContaining('service-dates-start-') }));
    expect(mocks.getStart.mock.invocationCallOrder.at(-1)).toBeGreaterThan(mocks.applyStart.mock.invocationCallOrder[0]!);
    expect(mocks.detail.mock.invocationCallOrder.at(-1)).toBeGreaterThan(mocks.applyStart.mock.invocationCallOrder[0]!);
    expect(mocks.previewDates).not.toHaveBeenCalled();
    expect(mocks.applyDates).not.toHaveBeenCalled();
    expect(mocks.intakeApply).not.toHaveBeenCalled();
  });

  it.each(['歷史訂單－未服務', '歷史訂單－服務中'])('%s keeps the precision restart UI available without intake blockers', async (status) => {
    mocks.detail.mockResolvedValue(orderDetail(status));
    mocks.intakeCompletion.mockResolvedValue({
      case_no: 'CASE-FUTURE',
      order_status: status,
      order_version: 12,
      missing_fields: [],
      blockers: [],
      apply_allowed: false,
    });
    mocks.core.mockResolvedValue({
      items: [timeline(status)],
      stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0])),
      substatus_counts: {},
      historical_lifecycle_counts: { unserved: status === '歷史訂單－未服務' ? 1 : 0, in_service: status === '歷史訂單－服務中' ? 1 : 0, service_completed: 0, accounting_completed: 0 },
      next_cursor: null,
      etag: 'b'.repeat(64),
    });

    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);

    const restartRegion = await screen.findByRole('region', { name: '歷史訂單精算天數重啟' });
    expect(within(restartRegion).getByRole('heading', { name: '重啟精算天數' })).toBeInTheDocument();
    expect(within(restartRegion).getByRole('button', { name: '前往重啟正常流程' })).toBeEnabled();
  });

  it('stops before Preview and Apply when the restart owner returns blockers', async () => {
    mocks.restartQuery.mockResolvedValue({ blockers: ['historical_restart_not_available'] });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '前往重啟正常流程' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('historical_restart_not_available');
    expect(mocks.restartPreview).not.toHaveBeenCalled();
    expect(mocks.restartApply).not.toHaveBeenCalled();
  });

  it('does not claim success when owner readback has not observed the restart receipt', async () => {
    mocks.restartApply.mockResolvedValue({ lifecycle_status: '訂單成立', replayed: false });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '前往重啟正常流程' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('正式案件回讀尚未觀察到');
    expect(screen.queryByText(/已重啟正常流程並回讀確認/)).not.toBeInTheDocument();
  });

  it.each(['歷史訂單－服務完成', '歷史訂單－帳務完成'])('%s never exposes intake Apply or a restart rollback', async (status) => {
    mocks.detail.mockResolvedValue(orderDetail(status));
    mocks.core.mockResolvedValue({
      items: [timeline(status)],
      stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0])),
      substatus_counts: {},
      historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: status === '歷史訂單－服務完成' ? 1 : 0, accounting_completed: status === '歷史訂單－帳務完成' ? 1 : 0 },
      next_cursor: null,
      etag: 'b'.repeat(64),
    });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    await screen.findAllByText(status);
    expect(screen.queryByRole('button', { name: '前往重啟正常流程' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
    expect(mocks.restartQuery).not.toHaveBeenCalled();
    expect(mocks.restartApply).not.toHaveBeenCalled();
    expect(mocks.intakeApply).not.toHaveBeenCalled();
  });

  it.each(['historical_client_payment_terms_missing', 'historical_payroll_rate_policy_missing'])('shows the completed historical accounting owner blocker %s without hiding the case', async (blocker) => {
    mocks.detail.mockResolvedValue(orderDetail('歷史訂單－服務完成'));
    mocks.accounting.mockRejectedValue(new Error(blocker));
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /確認服務日期與排班/ }));
    const evidence = screen.getByRole('heading', { name: '歷史服務資料' }).closest('section')!;
    expect(await within(evidence).findByText(`歷史帳務資料暫時無法取得：${blocker}`)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '案件 CASE-FUTURE' })).toBeInTheDocument();
    expect(screen.queryByText(/historical_order_not_found/)).not.toBeInTheDocument();
    expect(mocks.accounting).toHaveBeenCalledWith('CASE-FUTURE');
  });

  it('mounts the existing replacement workflow only after the explicit business entry is selected', async () => {
    mocks.matchingPlan.mockResolvedValue({
      planId: 51, status: 'proposed', activeLockId: null, planVersion: 1,
      segments: [{ segmentId: 71, sequence: 1, staffId: 42, assignedStartDate: '2026-09-03', assignedEndDate: '2026-09-22' }],
    });
    mocks.matchingContact.mockResolvedValue({
      plan: { id: 51, case_no: 'CASE-FUTURE', status: 'proposed', communication_version: 4, is_active: 1 },
      segments: [{ segment_id: 71, staff_id: 42, staff_name: '陳月嫂', willingness: 'willing' }],
      all_willing: true, customer_decision: 'accepted', customer_profiles_status: null, customer_profiles_manual_confirmation: null,
    });
    mocks.matchingPreview.mockResolvedValue({
      case_no: 'CASE-FUTURE', plan_id: 51, expected_version: 4,
      order_information_1_ready: true, order_information_2_ready: true, weekly_service_ready: true,
      weekly_service_row_count: 1,
      order_information_1: [{ segment_id: 71, staff_id: 42, staff_name: '陳月嫂', text: '訂單資訊－1' }],
      order_information_2: [{ segment_id: 71, staff_id: 42, staff_name: '陳月嫂', text: '訂單資訊－2' }],
      weekly_service_rows: [{ serial_number: 1, staff_name: '陳月嫂', week_start_date: '2026-09-03', week_end_date: '2026-09-09', service_hours_per_day: 9, weekly_work_days: 5, weekly_hours: 45 }],
      caregiver_resumes: [{ staff_id: 42, staff_name: '陳月嫂', ready: true, filename: 'resume.pdf', version: 1, blocker: null }],
      blockers: [], send_allowed: true,
    });
    mocks.candidatePool.mockResolvedValue({
      case_no: 'CASE-FUTURE', candidates: [{
        id: 2, staff_id: 43, staff_name: '候選月嫂乙', status: 'active', willingness: 'willing',
        service_start_date: '2026-09-03', service_end_date: '2026-09-22',
      }],
    });
    mocks.detail.mockResolvedValue(orderDetail('訂單成立'));
    mocks.core.mockResolvedValue({
      items: [{
        ...timeline(), branch_type: 'normal', lifecycle_status: '訂單成立',
        current_core_stage_code: 'confirmed_service_dates', current_core_stage_ordinal: 9,
        historical_current_owner_stage_code: null, historical_current_owner_stage_ordinal: null,
        core_stages: CORE_STAGE_CODES.map((code, index) => ({
          ...stage(code, index), owner: `owner-${code}`, warnings: [],
          source: { owner: `owner-${code}`, identity: `${code}:CASE-FUTURE`, version: 12 },
        })),
      }],
      stage_counts: Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, code === 'confirmed_service_dates' ? 1 : 0])),
      substatus_counts: {}, next_cursor: null, etag: 'b'.repeat(64),
    });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /確認服務日期與排班/ }));
    const entry = await screen.findByRole('button', { name: '服務前更換月嫂 →' });
    await waitFor(() => expect(entry).toBeEnabled());
    expect(screen.queryByRole('region', { name: '更換月嫂' })).not.toBeInTheDocument();
    expect(mocks.candidatePool).not.toHaveBeenCalled();
    fireEvent.click(entry);
    expect(await screen.findByRole('radio', { name: /候選月嫂乙/ })).toHaveAttribute('value', '43');
    const replacementRegion = screen.getByRole('region', { name: '更換月嫂' });
    expect(within(replacementRegion).getByRole('button', { name: '檢查換人影響' })).toBeDisabled();
  });
});
