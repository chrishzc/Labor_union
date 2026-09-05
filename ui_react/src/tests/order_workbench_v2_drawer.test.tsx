import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageBranchType,
  type CoreStageCode,
  type CoreStageStatus,
} from '../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const clientMocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
  getOrderDetail: vi.fn(),
  getOrderTerms: vi.fn(),
  getAssignmentPlan: vi.fn(),
  historicalQuery: vi.fn(),
  historicalPreview: vi.fn(),
  historicalApply: vi.fn(),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: clientMocks.getCoreStageTimelines,
  },
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: clientMocks.loadSummaries,
  ordersQueryClient: {
    getOrderSummaries: vi.fn(),
    getOrderDetail: clientMocks.getOrderDetail,
    getOrderTerms: clientMocks.getOrderTerms,
    getAssignmentPlan: clientMocks.getAssignmentPlan,
  },
}));

vi.mock('../api/orders/historical_service_accounting_client', () => ({
  historicalServiceAccountingClient: {
    query: clientMocks.historicalQuery,
    preview: clientMocks.historicalPreview,
    apply: clientMocks.historicalApply,
  },
}));

const STAGE_LABELS: Readonly<Record<CoreStageCode, string>> = {
  intake_validation: '進件與資料完整性驗證',
  matching_pool: '建立候選月嫂池',
  caregiver_line_delivery: '詢問月嫂接案意願',
  caregiver_willingness_reply: '等待月嫂意願回覆',
  formal_recommendation: '推薦月嫂給客戶確認',
  caregiver_contract: '月嫂契約簽署',
  deposit_settlement: '客戶定金核銷',
  client_contract: '客戶契約簽署',
  confirmed_service_dates: '正式服務日期確認',
  formal_service: '正式排班與服務履約',
  service_completion: '完工／服務完成確認',
  client_settlement: '客戶端結算',
  staff_payout: '月嫂端結算',
};

function stage(
  code: CoreStageCode,
  status: CoreStageStatus,
  caseNo: string,
  blockers: readonly { code: string; message: string }[] = [],
  warnings: readonly { code: string; message: string }[] = [],
) {
  return {
    ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
    code,
    label: STAGE_LABELS[code],
    owner: `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: {
      owner: `source-${code}`,
      identity: `${code}:${caseNo}`,
      version: 7,
    },
    occurred_at: null,
    blockers,
    warnings,
    available_read_actions: [],
    availability_reason: null,
  };
}

function timeline(
  caseNo: string,
  currentCode: CoreStageCode | null,
  options: {
    branch?: CoreStageBranchType;
    lifecycle?: string;
    currentStatus?: CoreStageStatus;
    blockers?: readonly { code: string; message: string }[];
    warnings?: readonly { code: string; message: string }[];
  } = {},
) {
  const branch = options.branch ?? 'normal';
  const currentStatus = options.currentStatus ?? 'in_progress';
  return {
    case_no: caseNo,
    base_revision: 3,
    lifecycle_status: options.lifecycle ?? '服務中',
    branch_type: branch,
    current_core_stage_code: currentCode,
    current_core_stage_ordinal: currentCode === null ? null : CORE_STAGE_CODES.indexOf(currentCode) + 1,
    core_stages: CORE_STAGE_CODES.map((code) => stage(
      code,
      code === currentCode ? currentStatus : 'completed',
      caseNo,
      code === currentCode ? options.blockers : [],
      code === currentCode ? options.warnings : [],
    )),
    source_projection_digest: 'd'.repeat(64),
  };
}

function stageCounts(overrides: Partial<Record<CoreStageCode, number>> = {}) {
  return Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, overrides[code] ?? 0]));
}

function page(
  items: unknown[],
  selectedStage?: CoreStageCode,
) {
  return {
    items,
    stage_counts: stageCounts(selectedStage ? { [selectedStage]: items.length } : {}),
    substatus_counts: selectedStage
      ? Object.fromEntries(substatusCodesForStage(selectedStage).map((code) => [code, 0]))
      : {},
    next_cursor: null,
    etag: 'e'.repeat(64),
  };
}

function detail(caseNo: string, clientName: string, actualStart: string | null = '2026-10-03') {
  return {
    case_no: caseNo,
    client_id: 88,
    staff_id: null,
    client_name: clientName,
    staff_name: null,
    order_status: '服務中',
    identity_status: '一般市民',
    cancel_reason: null,
    line_group_id: null,
    contract_identity: 'contract-1',
    actual_start_date: actualStart,
    actual_end_date: null,
    deposit_date: null,
    start_date: '1999-01-01',
    end_date: '1999-01-20',
    service_days: 20,
    service_hours_per_day: 9,
    deposit_service_days: null,
    floor_fee: 0,
    custom_rest_dates: null,
  };
}

function terms(caseNo: string, plannedStart = '2026-10-01') {
  return {
    case_no: caseNo,
    order_version: 12,
    scheduling_version: 13,
    scheduling_generation: 2,
    client_finance_version: 5,
    payroll_version: 6,
    service_data_locked: false,
    terms: {
      planned_start_date: plannedStart,
      service_days: 20,
      service_hours_per_day: 9,
      requires_cooking: null,
      floor_fee_ntd: 0,
      service_time: { start_time: null, end_time: null, end_day_offset: null },
    },
  };
}

function assignment(caseNo: string, staffId = 42) {
  return {
    case_no: caseNo,
    order_version: 12,
    scheduling_version: 13,
    scheduling_generation: 2,
    client_finance_version: 5,
    payroll_version: 6,
    contracted_service_days: 20,
    service_hours_per_day: 9,
    service_started: true,
    assignments: [{
      assignment_id: 501,
      candidate_key: null,
      staff_id: staffId,
      sequence: 1,
      assigned_start_date: '2026-10-01',
      assigned_end_date: '2026-10-20',
      official_service_dates: ['2026-10-01', '2026-10-02'],
      actual_hours: null,
      lineage_source_assignment_ids: [301, 302],
    }],
  };
}

function summaryPage() {
  return { items: [], next_cursor: null, etag: 'f'.repeat(64) };
}

function cardFor(caseNo: string): HTMLElement {
  const card = screen.getByText(caseNo).closest('article');
  if (!(card instanceof HTMLElement)) throw new Error(`找不到 ${caseNo} 案件卡`);
  return card;
}

function setOwnerFacts(caseNo: string, clientName = '林小芳', staffId = 42) {
  clientMocks.getOrderDetail.mockResolvedValue(detail(caseNo, clientName));
  clientMocks.getOrderTerms.mockResolvedValue(terms(caseNo));
  clientMocks.getAssignmentPlan.mockResolvedValue(assignment(caseNo, staffId));
}

describe('待辦看板 Beta 唯讀工作 Drawer', () => {
  beforeEach(() => {
    Object.values(clientMocks).forEach((mock) => mock.mockReset());
    clientMocks.loadSummaries.mockResolvedValue(summaryPage());
  });

  it('由案件卡開啟／關閉，並只用正式 GET owner facts 與 core-stage projection 呈現案件、服務、派案、13 階、notice 與 lineage', async () => {
    const row = timeline('CASE-DRAWER', 'intake_validation', {
      currentStatus: 'blocked',
      blockers: [{ code: 'service_blocked', message: '正式排班尚未完成' }],
      warnings: [{ code: 'service_warning', message: '確認服務開始資訊' }],
    });
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => (
      params.case_no_search === 'CASE-DRAWER'
        ? page([row])
        : page([row], 'intake_validation')
    ));
    setOwnerFacts('CASE-DRAWER');

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(screen.getByText('CASE-DRAWER')).toBeInTheDocument());

    fireEvent.click(within(cardFor('CASE-DRAWER')).getByRole('button', { name: '開啟唯讀工作 Drawer' }));
    const dialog = await screen.findByRole('dialog', { name: '案件 CASE-DRAWER' });

    await waitFor(() => expect(within(dialog).getByText('林小芳')).toBeInTheDocument());
    expect(within(dialog).getByText('2026-10-01')).toBeInTheDocument();
    expect(within(dialog).getByText('20 日')).toBeInTheDocument();
    expect(within(dialog).getByText('2026-10-03')).toBeInTheDocument();
    expect(within(dialog).getByText('`actual_start_date` 僅代表實際開始，不作為完整服務區間。')).toBeInTheDocument();
    expect(within(dialog).getByText(/Segment 1 · 月嫂 #42/)).toBeInTheDocument();
    expect(within(dialog).getByText('lineage_source_assignment_ids：301, 302')).toBeInTheDocument();
    expect(within(dialog).getAllByTestId('drawer-core-stage')).toHaveLength(13);
    expect(within(dialog).getByText('正式排班尚未完成')).toBeInTheDocument();
    expect(within(dialog).getByText('確認服務開始資訊')).toBeInTheDocument();
    expect(within(dialog).getByText('identity：intake_validation:CASE-DRAWER')).toBeInTheDocument();
    expect(within(dialog).getByText(`source_projection_digest：${'d'.repeat(64)}`)).toBeInTheDocument();

    expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledWith(
      expect.objectContaining({
        lifecycle_scope: 'all',
        case_no_search: 'CASE-DRAWER',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    const drawerQuery = clientMocks.getCoreStageTimelines.mock.calls.find(
      ([params]) => params.case_no_search === 'CASE-DRAWER',
    );
    expect(drawerQuery?.[0]).not.toHaveProperty('branch_type');
    expect(clientMocks.getOrderDetail).toHaveBeenCalledWith('CASE-DRAWER', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(clientMocks.getOrderTerms).toHaveBeenCalledWith('CASE-DRAWER', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(clientMocks.getAssignmentPlan).toHaveBeenCalledWith('CASE-DRAWER', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(clientMocks.historicalQuery).not.toHaveBeenCalled();
    expect(clientMocks.historicalPreview).not.toHaveBeenCalled();
    expect(clientMocks.historicalApply).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: '關閉工作 Drawer' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('歷史支線把歷史配對明確隔離在「歷史來源證據」，不冒充目前正式派案或服務期間', async () => {
    const normal = timeline('CASE-NORMAL', 'intake_validation');
    const historical = timeline('CASE-HISTORY', null, {
      branch: 'historical',
      lifecycle: '歷史訂單－服務完成',
    });
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      if (params.case_no_search === 'CASE-HISTORY') return page([historical]);
      if (params.branch_type === 'historical') return page([historical]);
      return page([normal], 'intake_validation');
    });
    setOwnerFacts('CASE-HISTORY', '正式客戶', 99);
    clientMocks.historicalQuery.mockResolvedValue({
      case_no: 'CASE-HISTORY',
      lifecycle_status: '歷史訂單－服務完成',
      lifecycle_version: 1,
      adoption_receipt_id: 9,
      adoption_source_identity: 'excel:legacy-orders:row-17',
      historical_day_revision: 2,
      client_finance_version: 3,
      payroll_version: 4,
      contracted_service_days: 18,
      service_hours_per_day: 9,
      contractual_floor_fee_ntd: 0,
      client_identity_status: '一般市民',
      assignments: [{
        assignment_identity: 'legacy-pairing:77',
        staff_id: 77,
        staff_name: '歷史月嫂',
        policy_version: 'v1',
        policy_kind: 'citizen',
        hourly_rate_ntd: 200,
      }],
    });

    render(<OrderWorkbenchV2Page />);
    fireEvent.click(await screen.findByRole('button', { name: '歷史訂單' }));
    await waitFor(() => expect(screen.getByText('CASE-HISTORY')).toBeInTheDocument());
    fireEvent.click(within(cardFor('CASE-HISTORY')).getByRole('button', { name: '開啟唯讀工作 Drawer' }));

    const dialog = await screen.findByRole('dialog', { name: '案件 CASE-HISTORY' });
    const assignmentSection = within(dialog).getByRole('heading', { name: '目前正式派案／Assignment projection' }).closest('section');
    if (!(assignmentSection instanceof HTMLElement)) throw new Error('找不到正式派案區');
    const historicalRegion = within(dialog).getByRole('region', { name: '歷史來源證據' });

    await waitFor(() => expect(within(assignmentSection).getByText(/月嫂 #99/)).toBeInTheDocument());
    await waitFor(() => expect(within(historicalRegion).getByText(/歷史月嫂/)).toBeInTheDocument());
    expect(within(assignmentSection).queryByText(/歷史月嫂/)).not.toBeInTheDocument();
    expect(within(historicalRegion).getByText(/不代表目前正式服務期間或目前正式派案/)).toBeInTheDocument();
    expect(within(historicalRegion).getByText('excel:legacy-orders:row-17')).toBeInTheDocument();
    expect(within(historicalRegion).getByText(/歷史月嫂 \(#77, legacy-pairing:77\)/)).toBeInTheDocument();
    expect(clientMocks.historicalQuery).toHaveBeenCalledWith('CASE-HISTORY');
    expect(clientMocks.historicalPreview).not.toHaveBeenCalled();
    expect(clientMocks.historicalApply).not.toHaveBeenCalled();
  });

  it('typed query 失敗時只在對應區顯示明確錯誤，仍保留正式 core-stage；Escape 關閉後晚到 response 不會重開 Drawer', async () => {
    const row = timeline('CASE-STRICT', 'intake_validation');
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => (
      params.case_no_search === 'CASE-STRICT'
        ? page([row])
        : page([row], 'intake_validation')
    ));
    clientMocks.getOrderDetail.mockResolvedValue(detail('CASE-STRICT', '嚴格解碼客戶'));
    clientMocks.getOrderTerms.mockRejectedValue(new Error('strict decode: invalid OrderTerms payload'));
    let resolveAssignment!: (value: ReturnType<typeof assignment>) => void;
    clientMocks.getAssignmentPlan.mockReturnValue(new Promise((resolve) => {
      resolveAssignment = resolve;
    }));

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(screen.getByText('CASE-STRICT')).toBeInTheDocument());
    fireEvent.click(within(cardFor('CASE-STRICT')).getByRole('button', { name: '開啟唯讀工作 Drawer' }));

    const dialog = await screen.findByRole('dialog', { name: '案件 CASE-STRICT' });
    await waitFor(() => expect(within(dialog).getByText(/正式服務條款不可用：strict decode: invalid OrderTerms payload/)).toBeInTheDocument());
    expect(within(dialog).getAllByTestId('drawer-core-stage')).toHaveLength(13);
    expect(within(dialog).queryByText('1999-01-01')).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    resolveAssignment(assignment('CASE-STRICT', 66));
    await Promise.resolve();
    await Promise.resolve();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});