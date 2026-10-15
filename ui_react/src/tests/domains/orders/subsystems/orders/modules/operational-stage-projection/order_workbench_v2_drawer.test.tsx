import { OrderWorkbenchV2Drawer } from '../../../../../../../components/OrderWorkbenchV2Drawer';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageBranchType,
  type CoreStageCode,
  type CoreStageStatus,
} from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../../../../../../../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../../../../../../../pages/OrderWorkbenchV2Page';
import { adaptOrderSummaryPage } from '../../../../../../../adapters/orders/order_summary_adapter';
import { OrderConflictError } from '../../../../../../../api/orders/order_query_errors';

vi.mock('../../../../../../../components/OrderServiceDatesPanel', () => ({ OrderServiceDatesPanel: () => <p>服務日期工作區</p> }));
vi.mock('../../../../../../../components/OrderAssignmentPlanPanel', () => ({ OrderAssignmentPlanPanel: () => <p>排班工作區</p> }));
vi.mock('../../../../../../../components/OrderMultiCaregiverPlanPanel', () => ({
  OrderMultiCaregiverPlanPanel: ({ filters, onObserved }: { filters: Record<string, boolean>; onObserved?: () => void }) => <section aria-label="正式分段工作區">
    <p>分段下廚篩選：{String(filters.cooking)}</p>
    <button type="button" onClick={onObserved}>模擬分段方案正式回讀成功</button>
  </section>,
}));

const clientMocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
  getOrderDetail: vi.fn(),
  getFormManagementContext: vi.fn(),
  getOrderTerms: vi.fn(),
  getAssignmentPlan: vi.fn(),
  historicalQuery: vi.fn(),
  historicalPreview: vi.fn(),
  historicalApply: vi.fn(),
}));

vi.mock('../../../../../../../components/OrderIntakeRepairPanel', () => ({
  OrderIntakeRepairPanel: ({ caseNo, orderStatus, summaryHref, onChanged }: { caseNo: string; orderStatus: string; summaryHref: string; onChanged?: () => void }) => (
    <section aria-label="正式補件入口">{caseNo}：{orderStatus}
      <a href={summaryHref}>前往補齊案件資料 →</a>
      <button type="button" onClick={onChanged}>模擬補件回讀</button>
    </section>
  ),
}));

vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: clientMocks.getCoreStageTimelines,
  },
}));

vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: clientMocks.loadSummaries,
  ordersQueryClient: {
    getOrderSummaries: vi.fn(),
    getOrderDetail: clientMocks.getOrderDetail,
    getFormManagementContext: clientMocks.getFormManagementContext,
    getOrderTerms: clientMocks.getOrderTerms,
    getAssignmentPlan: clientMocks.getAssignmentPlan,
  },
}));

vi.mock('../../../../../../../api/orders/historical_service_accounting_client', () => ({
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
  external_signing_dispatch: '建立契約並送交外部簽署平台',
  deposit_settlement: '客戶定金核銷',
  external_signing_completion: '雙方外部簽署完成',
  confirmed_service_dates: '服務日期確認',
  formal_service: '排班與服務履約',
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
    start_date: '2026-10-01',
    end_date: '2026-10-20',
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

describe('待辦看板 唯讀工作 Drawer', () => {
  beforeEach(() => {
    Object.values(clientMocks).forEach((mock) => mock.mockReset());
    clientMocks.loadSummaries.mockResolvedValue(summaryPage());
    clientMocks.getFormManagementContext.mockImplementation(async (caseNo: string) => ({
      case_no: caseNo, service_time: '舊來源時間', service_type: '連續服務', city: '測試縣市',
      delivery_type: null, residence_type: null, identity_status: '一般市民',
    }));
  });

  it('provides a multi-caregiver entry in candidate inquiry and forwards matching filters', async () => {
    const caseNo = 'CASE-MULTI-ENTRY';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'matching_pool', { lifecycle: '洽談中' })]));
    setOwnerFacts(caseNo);
    render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);
    const entry = await screen.findByRole('button', { name: '多月嫂分段' });
    expect(screen.queryByRole('region', { name: '正式分段工作區' })).not.toBeInTheDocument();
    fireEvent.click(entry);
    expect(entry).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('region', { name: '正式分段工作區' })).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText('分段下廚篩選：true')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: '下廚料理' }));
    expect(screen.getByText('分段下廚篩選：false')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '候選月嫂' }));
    expect(screen.getByRole('button', { name: '候選月嫂' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('hands off to customer-confirmation preparation only after the segmented plan was read back', async () => {
    const caseNo = 'CASE-MULTI-HANDOFF';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'matching_pool', { lifecycle: '洽談中' })]));
    setOwnerFacts(caseNo);
    render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '多月嫂分段' }));
    expect(screen.getByRole('heading', { name: '尋找月嫂與詢問意願' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '模擬分段方案正式回讀成功' }));
    expect(await screen.findByRole('heading', { name: '推薦月嫂給客戶確認' })).toBeInTheDocument();
    expect(screen.queryByText('多月嫂接續方案')).not.toBeInTheDocument();
  });

  it('上方集中資料編輯入口，進件摘要導向名冊且不重複表單', async () => {
    const caseNo = 'CASE-STEP-CONTEXT';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'intake_validation')]));
    setOwnerFacts(caseNo);
    const view = render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('region', { name: '正式補件入口' });
    const header = view.container.querySelector('.order-case-header') as HTMLElement;
    const body = view.container.querySelector('.order-case-task-body') as HTMLElement;
    const records = within(header).getByRole('button', { name: '查看相關資料與通知紀錄' });
    expect(within(header).getByRole('link', { name: '編輯客戶與訂單資料 →' })).toHaveAttribute('href', `#clients?case=${caseNo}&from=workbench`);
    expect(clientMocks.getFormManagementContext).not.toHaveBeenCalled();
    expect(within(body).queryByText('確認基本服務需求；待補資料與可先辦事項分開處理。')).not.toBeInTheDocument();
    expect(within(body).queryByRole('region', { name: '本步驟相關資料' })).not.toBeInTheDocument();
    expect(within(body).queryByRole('link', { name: '編輯客戶與訂單資料 →' })).not.toBeInTheDocument();
    fireEvent.click(records);
    expect(await within(header).findByText('測試縣市')).toBeInTheDocument();
    expect(clientMocks.getFormManagementContext).toHaveBeenCalledWith(caseNo, { signal: expect.any(AbortSignal) });
    fireEvent.click(within(header).getByRole('button', { name: '收起相關資料與通知紀錄' }));
    expect(within(header).queryByRole('heading', { name: '客戶服務資料' })).not.toBeInTheDocument();
    expect(within(body).getByRole('region', { name: '正式補件入口' })).toBeVisible();
  });

  it('回讀後依正式進度接續目前待辦，原摘要保持掛載', async () => {
    const caseNo = 'CASE-INTAKE-ADVANCE';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'intake_validation', { lifecycle: '待補件' })]));
    setOwnerFacts(caseNo);
    render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);
    const intake = await screen.findByRole('region', { name: '正式補件入口' });
    expect(within(intake).getByRole('link')).toHaveAttribute('href', `#clients?case=${caseNo}&field=intake&from=workbench`);
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'matching_pool', { lifecycle: '洽談中' })]));
    fireEvent.click(within(intake).getByRole('button', { name: '模擬補件回讀' }));
    await waitFor(() => expect(screen.getByRole('button', { name: /尋找月嫂與詢問意願/ })).toHaveAttribute('aria-current', 'page'));
    expect(intake).toBeInTheDocument();
    expect(intake).not.toBeVisible();
    expect(screen.getByRole('heading', { name: '尋找月嫂與詢問意願', level: 2 })).toBeInTheDocument();
  });

  it('重新查詢不拉走使用者手動查閱的工作，可返回目前待辦', async () => {
    const caseNo = 'CASE-MANUAL-GROUP';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'intake_validation', { lifecycle: '洽談中' })]));
    clientMocks.getOrderTerms.mockRejectedValue(new Error('服務条件尚未齊備'));
    clientMocks.getOrderDetail.mockResolvedValue(detail(caseNo, '測試客戶'));
    clientMocks.getAssignmentPlan.mockResolvedValue(assignment(caseNo, 42));
    render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('region', { name: '正式補件入口' });
    fireEvent.click(screen.getByRole('button', { name: /辦理契約與簽署/ }));
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'matching_pool', { lifecycle: '洽談中' })]));
    fireEvent.click(screen.getByRole('button', { name: '模擬補件回讀', hidden: true }));
    await waitFor(() => expect(screen.getByText('洽談中')).toBeInTheDocument());
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: /辦理契約與簽署/ })).toHaveAttribute('aria-current', 'page');
    fireEvent.click(screen.getByRole('button', { name: '回到目前待辦' }));
    await waitFor(() => expect(screen.getByRole('button', { name: /尋找月嫂與詢問意願/ })).toHaveAttribute('aria-current', 'page'));
  });

  it('顯示未填每日時數的正式查詢阻塞，不以空白條件或進度推進掩蓋缺件', async () => {
    const caseNo = 'CASE-MISSING-HOURS';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'intake_validation', {
      lifecycle: '洽談中', blockers: [{ code: 'orders_terms_missing', message: '缺少欄位：服務時間。' }],
    })]));
    clientMocks.getOrderTerms.mockRejectedValue(new OrderConflictError('Orders Terms request was rejected.', null, [], 'order_terms_service_hours_per_day_required'));
    clientMocks.getOrderDetail.mockRejectedValue(new Error('detail_unavailable'));
    clientMocks.getAssignmentPlan.mockResolvedValue(assignment(caseNo, 42));
    render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);
    expect(await screen.findByRole('region', { name: '正式補件入口' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /確認客戶與服務需求/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByText('缺少欄位：服務時間。')).toBeInTheDocument();
  });

  it('訂金待辦進入服務安排，不再顯示重複收款步驟或舊放行表單', async () => {
    const caseNo = 'CASE-DEPOSIT-OVERRIDE';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([
      timeline(caseNo, 'deposit_settlement', { lifecycle: '洽談中' }),
    ]));
    setOwnerFacts(caseNo);

    render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" onClose={vi.fn()} />);

    await screen.findByRole('heading', { name: '確認服務日期與排班' });
    expect(screen.getByRole('region', { name: '訂金鎖狀態' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '一般市民訂金未付人工放行' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /客戶收款與月嫂結算/ })).not.toBeInTheDocument();
  });

  it.each(['Enter', ' '])('案件卡可用 %s 開啟案件處理', async (key) => {
    const caseNo = 'CASE-CARD-KEYBOARD';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([
      timeline(caseNo, 'intake_validation', { lifecycle: '洽談中' }),
    ]));
    setOwnerFacts(caseNo);
    render(<OrderWorkbenchV2Page />);
    const card = await screen.findByRole('button', { name: `開啟案件 ${caseNo} 案件處理` });
    expect(card).toHaveAttribute('tabindex', '0');
    expect(card).toHaveAttribute('aria-disabled', 'false');
    card.focus();
    fireEvent.keyDown(card, { key });
    const work = await screen.findByRole('region', { name: `案件 ${caseNo}` });
    expect(within(work).getByRole('heading', { name: '案件處理', level: 1 })).toBeInTheDocument();
  });

  it('資料未補齊使 detail 不可用時仍依正式 intake projection 開啟補件入口', async () => {
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([
      timeline('CASE-INCOMPLETE', 'intake_validation', { lifecycle: '待補件' }),
    ]));
    clientMocks.getOrderDetail.mockRejectedValue(new Error('order_detail_projection_invalid'));
    clientMocks.getOrderTerms.mockRejectedValue(new Error('terms_unavailable'));
    clientMocks.getAssignmentPlan.mockRejectedValue(new Error('assignment_unavailable'));
    render(<OrderWorkbenchV2Drawer caseNo="CASE-INCOMPLETE" branchType="normal" onClose={() => {}} />);
    expect(await screen.findByRole('region', { name: '正式補件入口' })).toHaveTextContent('CASE-INCOMPLETE：待補件');
    expect(screen.queryByText('客戶與訂單資料暫時無法取得。')).not.toBeInTheDocument();
    expect(screen.queryByText('服務條件尚未就緒')).not.toBeInTheDocument();
  });

  it('由名冊返回時以正式查詢開啟相同案件的最新待辦，關閉後清除深連結', async () => {
    const caseNo = 'CASE-REGISTRY-RETURN';
    window.location.hash = `#order-workbench-v2?case=${caseNo}`;
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([timeline(caseNo, 'matching_pool', { lifecycle: '洽談中' })]));
    setOwnerFacts(caseNo);
    render(<OrderWorkbenchV2Page />);
    const work = await screen.findByRole('region', { name: `案件 ${caseNo}` });
    await within(work).findByRole('heading', { name: '尋找月嫂與詢問意願', level: 2 });
    expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledWith({ lifecycle_scope: 'all', case_no_search: caseNo, page_size: 20 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    fireEvent.click(within(work).getByRole('button', { name: '← 返回待辦看板' }));
    await waitFor(() => expect(window.location.hash).toBe('#order-workbench-v2'));
    window.location.hash = '';
  });

  it('keeps known name and dates from the matching case summary when incomplete terms prevent detail reads', async () => {
    const caseNo = 'CASE-INCOMPLETE';
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([
      timeline(caseNo, 'intake_validation', { lifecycle: '待補件' }),
    ]));
    clientMocks.getOrderDetail.mockRejectedValue(new Error('order_detail_projection_invalid'));
    clientMocks.getOrderTerms.mockRejectedValue(new Error('terms_unavailable'));
    clientMocks.getAssignmentPlan.mockRejectedValue(new Error('assignment_unavailable'));
    const summary = adaptOrderSummaryPage({ items: [{
      case_no: caseNo, client_name: '已登錄客戶', order_status: '待補件',
      staff_name: null, identity_status: null, start_date: '2026-11-01', end_date: null,
      actual_start_date: null, actual_end_date: null, service_days: null,
      total_employer_self_pay_payable: null,
    }], next_cursor: null, etag: 'f'.repeat(64) }).items[0]!;
    const { container, rerender } = render(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" summary={summary} onClose={() => {}} />);
    await screen.findByRole('region', { name: '正式補件入口' });
    const header = container.querySelector('.order-case-context')!;
    expect(header).toHaveTextContent('已登錄客戶');
    expect(header).toHaveTextContent('2026-11-01');
    expect(header).toHaveTextContent('待補服務天數');
    expect(header).not.toHaveTextContent('讀取失敗');
    rerender(<OrderWorkbenchV2Drawer caseNo={caseNo} branchType="normal" summary={{ ...summary, id: 'ANOTHER-CASE' }} onClose={() => {}} />);
    expect(header).not.toHaveTextContent('已登錄客戶');
    expect(header).toHaveTextContent('讀取失敗');
  });

  it('由案件卡開啟／關閉，並只用正式 GET owner facts 與 core-stage projection 呈現案件、服務、派案、13 階、notice 與 lineage', async () => {
    const row = timeline('CASE-DRAWER', 'intake_validation', {
      currentStatus: 'blocked',
      blockers: [{ code: 'service_blocked', message: '排班尚未完成' }],
      warnings: [{ code: 'service_warning', message: '確認服務開始資訊' }],
    });
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => (
      params.case_no_search === 'CASE-DRAWER'
        ? page([row])
        : page([row], params.stage)
    ));
    setOwnerFacts('CASE-DRAWER');

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(screen.getByText('CASE-DRAWER')).toBeInTheDocument());

    fireEvent.click(within(cardFor('CASE-DRAWER')).getByText('CASE-DRAWER'));
    const dialog = await screen.findByRole('region', { name: '案件 CASE-DRAWER' });

    await waitFor(() => expect(within(dialog).getAllByText('林小芳').length).toBeGreaterThan(0));
    const caseContext = dialog.querySelector('.order-case-context');
    expect(caseContext).toHaveTextContent('約定服務開始日2026-10-01');
    expect(caseContext).toHaveTextContent('實際開始2026-10-03');
    fireEvent.click(within(dialog).getByRole('button', { name: /確認服務日期與排班/ }));
    expect(within(dialog).getAllByText('2026-10-01').length).toBeGreaterThan(0);
    expect(caseContext).toHaveTextContent('20 日');
    expect(within(dialog).getAllByText('2026-10-03').length).toBeGreaterThan(0);
    expect(caseContext).toHaveTextContent('1 段正式指派');
    expect(within(dialog).getByText('服務日期工作區')).toBeVisible();
    expect(within(dialog).queryByText(/lineage_source_assignment_ids/)).not.toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: /確認客戶與服務需求/ }));
    fireEvent.click(within(dialog).getByText('查看十三階段紀錄'));
    expect(dialog.querySelectorAll('.order-case-progress li')).toHaveLength(13);
    expect(within(dialog).queryByText(/source_projection_digest/)).not.toBeInTheDocument();

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

    fireEvent.click(within(dialog).getByRole('button', { name: '← 返回待辦看板' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: '案件 CASE-DRAWER' })).not.toBeInTheDocument());
  });

  it('歷史支線把歷史配對明確隔離在「歷史來源證據」，不冒充目前正式派案或服務期間', async () => {
    const normal = timeline('CASE-NORMAL', 'intake_validation');
    const historical = timeline('CASE-HISTORY', null, {
      branch: 'historical',
      lifecycle: '歷史訂單－服務完成',
    });
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      if (params.case_no_search === 'CASE-HISTORY') return page([historical]);
      if (params.workbench_scope === 'completed') return page([historical]);
      return page([normal], params.stage);
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

    render(<OrderWorkbenchV2Drawer caseNo="CASE-HISTORY" branchType="historical" workbenchScope="completed" onClose={vi.fn()} />);

    const dialog = await screen.findByRole('region', { name: '案件 CASE-HISTORY' });
    expect(within(dialog).queryByRole('heading', { name: '13 階段正式進度' })).not.toBeInTheDocument();
    expect(within(dialog).queryByTestId('drawer-core-stage')).not.toBeInTheDocument();
    await within(dialog).findByRole('heading', { name: '服務完工' });
    const assignmentSection = dialog.querySelector('.order-case-context')! as HTMLElement;
    await waitFor(() => expect(assignmentSection).toHaveTextContent('1 段正式指派'));
    const historicalRegion = within(dialog).getByRole('heading', { name: '歷史服務資料' }).closest('section')!;
    await waitFor(() => expect(within(historicalRegion).getByText(/歷史月嫂/)).toBeInTheDocument());
    expect(within(assignmentSection).queryByText(/歷史月嫂/)).not.toBeInTheDocument();
    expect(within(historicalRegion).getByText(/不代表目前已確認的服務安排/)).toBeInTheDocument();
    expect(within(historicalRegion).queryByText('excel:legacy-orders:row-17')).not.toBeInTheDocument();
    expect(clientMocks.historicalQuery).toHaveBeenCalledWith('CASE-HISTORY');
    expect(clientMocks.historicalPreview).not.toHaveBeenCalled();
    expect(clientMocks.historicalApply).not.toHaveBeenCalled();
  });

  it.each([
    ['completed', 'normal', '訂單完成'],
    ['cancelled', 'cancelled', '訂單取消'],
  ] as const)('%s 案件抽屜不顯示13步驟', async (scope, branch, lifecycle) => {
    const row = timeline('CASE-TERMINAL', null, { branch, lifecycle });
    clientMocks.getCoreStageTimelines.mockResolvedValue(page([row]));
    setOwnerFacts('CASE-TERMINAL', '測試客戶', 99);
    render(<OrderWorkbenchV2Drawer caseNo="CASE-TERMINAL" branchType={branch} workbenchScope={scope} onClose={vi.fn()} />);
    const dialog = await screen.findByRole('region', { name: '案件 CASE-TERMINAL' });
    expect(within(dialog).queryByRole('heading', { name: '13 階段正式進度' })).not.toBeInTheDocument();
    await waitFor(() => expect(within(dialog).getByRole('heading', { name: scope === 'completed' ? '服務完工' : '案件處理紀錄' })).toBeInTheDocument());
    expect(within(dialog).queryByTestId('drawer-core-stage')).not.toBeInTheDocument();
  });

  it('typed query 失敗時只在對應區顯示明確錯誤，仍保留正式 core-stage；Escape 關閉後晚到 response 不會重開 Drawer', async () => {
    const row = timeline('CASE-STRICT', 'intake_validation');
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => (
      params.case_no_search === 'CASE-STRICT'
        ? page([row])
        : page([row], params.stage)
    ));
    clientMocks.getOrderDetail.mockResolvedValue({
      ...detail('CASE-STRICT', '嚴格解碼客戶'),
      start_date: '1999-01-01',
    });
    clientMocks.getOrderTerms.mockRejectedValue(new Error('strict decode: invalid OrderTerms payload'));
    let resolveAssignment!: (value: ReturnType<typeof assignment>) => void;
    clientMocks.getAssignmentPlan.mockReturnValue(new Promise((resolve) => {
      resolveAssignment = resolve;
    }));

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(screen.getByText('CASE-STRICT')).toBeInTheDocument());
    fireEvent.click(cardFor('CASE-STRICT'));

    const dialog = await screen.findByRole('region', { name: '案件 CASE-STRICT' });
    const caseContext = dialog.querySelector('.order-case-context');
    expect(caseContext).toHaveTextContent('約定服務開始日1999-01-01');
    expect(caseContext).toHaveTextContent('服務量20 日 · 每日 9 小時');
    expect(await within(dialog).findByRole('region', { name: '正式補件入口' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /確認客戶與服務需求/ })).toHaveAttribute('aria-current', 'page');
    expect(within(dialog).queryByRole('button', { name: '案件異動' })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: '訂單與服務資料' })).not.toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: '← 返回待辦看板' }));
    await waitFor(() => expect(screen.queryByRole('region', { name: '案件 CASE-STRICT' })).not.toBeInTheDocument());
    resolveAssignment(assignment('CASE-STRICT', 66));
    await Promise.resolve();
    await Promise.resolve();
    expect(screen.queryByRole('region', { name: '案件 CASE-STRICT' })).not.toBeInTheDocument();
  });
});
