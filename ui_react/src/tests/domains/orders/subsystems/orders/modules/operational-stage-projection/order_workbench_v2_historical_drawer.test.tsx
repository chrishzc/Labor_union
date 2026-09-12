import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HistoricalOrderAdoptionEvidenceSchema } from '../../../../../../../api/orders/historical_adoption_evidence_schemas';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS, type CoreStageCode } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import { OrderWorkbenchV2Drawer } from '../../../../../../../components/OrderWorkbenchV2Drawer';

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
}));

vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core },
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  ordersQueryClient: {
    getOrderDetail: mocks.detail,
    getOrderTerms: mocks.terms,
    getAssignmentPlan: mocks.assignment,
  },
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
    label: code === 'confirmed_service_dates' ? '正式服務日期確認' : code,
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

describe('historical Drawer immutable evidence boundary', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
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

  it('future source period 與 evidence-only staff 保留在來源區，formal owner/assignment 不被覆寫', async () => {
    render(<OrderWorkbenchV2Drawer caseNo="CASE-FUTURE" branchType="historical" onClose={vi.fn()} />);
    const dialog = screen.getByRole('region', { name: '案件 CASE-FUTURE' });
    const ownerHeading = await within(dialog).findByRole('heading', { name: '歷史案件目前進度' });
    const ownerSection = ownerHeading.closest('section');
    if (!(ownerSection instanceof HTMLElement)) throw new Error('找不到目前正式 owner progression 區');
    expect(within(ownerSection).getByText(/正式服務日期確認/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: '訂單與服務資料' }));
    const evidenceRegion = within(dialog).getByRole('heading', { name: '歷史服務資料' }).closest('section')!;
    expect(within(dialog).getByText('尚未正式安排月嫂。')).toBeInTheDocument();
    expect(within(dialog).getByText('尚未確認')).toBeInTheDocument();

    expect(within(evidenceRegion).getByText(/2026-09-03 → 2026-09-22/)).toBeInTheDocument();
    expect(within(evidenceRegion).getByText(/陳月嫂/)).toBeInTheDocument();
    expect(within(evidenceRegion).queryByText(/陳\*嫂/)).not.toBeInTheDocument();
    expect(within(evidenceRegion).getByText(/不代表目前已確認的服務安排/)).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const intake = screen.getByRole('region', { name: '訂單缺件' });
    expect(await within(intake).findByText('目前不可完成補件')).toBeInTheDocument();
    expect(within(intake).queryByRole('button', { name: '確認完成進件補齊' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '案件 CASE-FUTURE' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '案件處理' }));
    fireEvent.click(restart);
    await screen.findByText(/已重啟正常流程並回讀確認為「訂單成立」/);
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
    fireEvent.click(screen.getByRole('button', { name: '訂單與服務資料' }));
    const evidence = screen.getByRole('heading', { name: '歷史服務資料' }).closest('section')!;
    expect(await within(evidence).findByText(`歷史帳務資料暫時無法取得：${blocker}`)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '案件 CASE-FUTURE' })).toBeInTheDocument();
    expect(screen.queryByText(/historical_order_not_found/)).not.toBeInTheDocument();
    expect(mocks.accounting).toHaveBeenCalledWith('CASE-FUTURE');
  });

  it('mounts the existing replacement workflow only after the explicit business entry is selected', async () => {
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
    fireEvent.click(screen.getByRole('button', { name: '案件異動' }));
    const entry = await screen.findByRole('button', { name: '服務前更換月嫂' });
    await waitFor(() => expect(entry).toBeEnabled());
    expect(screen.queryByRole('option', { name: '候選月嫂尚未定案' })).not.toBeInTheDocument();
    fireEvent.click(entry);
    const replacementEntry = await screen.findByRole('button', { name: '換人' });
    fireEvent.click(replacementEntry);
    expect(await screen.findByRole('option', { name: '候選月嫂尚未定案' })).toHaveValue('R-01');
  });
});
