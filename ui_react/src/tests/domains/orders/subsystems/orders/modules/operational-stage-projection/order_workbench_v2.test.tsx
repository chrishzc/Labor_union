import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  CoreStageProjectionSchema,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageBranchType,
  type CoreStageCode,
  type CoreStageStatus,
  type CoreStageSubstatusCode,
} from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../../../../../../../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../../../../../../../pages/OrderWorkbenchV2Page';
import { hcmResubmissionClient } from '../../../../../../../api/case_import/hcm_resubmission_client';
import { caseStatisticsQueryClient } from '../../../../../../../api/reports/weekly_operations_report_query_client';
import { WorkbenchCaseStatistics } from '../../../../../../../components/WorkbenchCaseStatistics';
import type { CaseStatisticsData } from '../../../../../../../api/reports/weekly_operations_report_schemas';

function statisticsResult(year: number, quarter: number | null, month: number | null): CaseStatisticsData {
  const startMonth = month ?? (quarter ? (quarter - 1) * 3 + 1 : 1);
  const endMonth = month ?? (quarter ? quarter * 3 : 12);
  const count = month ?? quarter ?? 12;
  return {
    year, quarter, month,
    start_date: `${year}-${String(startMonth).padStart(2, '0')}-01`,
    end_date: `${year}-${String(endMonth).padStart(2, '0')}-${new Date(year, endMonth, 0).getDate()}`,
    timezone: 'Asia/Taipei', available_years: [2026, 2025, 2024], annual_application_count: 12,
    generated_at: '2026-10-13T12:00:00+08:00',
    summary: {
      application_count: count, general_eligible_count: count, general_ineligible_count: 0,
      subsidized_eligible_count: 0, subsidized_ineligible_count: 0,
      order_status_counts: { '待補件': count, '洽談中': 0, '訂單成立': 0, '服務中': 0, '訂單完成': 0, '訂單取消': 0 },
      unclassified_qualification_count: 0, other_status_count: 0,
    },
  };
}

const clientMocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: clientMocks.getCoreStageTimelines,
  },
}));

vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: clientMocks.loadSummaries,
  ordersQueryClient: { getOrderSummaries: vi.fn() },
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

function coreStage(
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
    source: { owner: `source-${code}`, identity: `${code}:${caseNo}`, version: 1 },
    occurred_at: null,
    blockers,
    warnings,
    available_read_actions: [],
    availability_reason: status === 'unavailable' ? `${code}_missing` : null,
  };
}

function timeline(
  caseNo: string,
  currentCode: CoreStageCode | null,
  currentStatus: CoreStageStatus = 'in_progress',
  options: {
    lifecycle?: string;
    branch?: CoreStageBranchType;
    blockers?: readonly { code: string; message: string }[];
    warnings?: readonly { code: string; message: string }[];
  } = {},
) {
  const lifecycle = options.lifecycle ?? '服務中';
  const branch = options.branch ?? 'normal';
  const stages = CORE_STAGE_CODES.map((code) => coreStage(
    code,
    code === currentCode ? currentStatus : 'completed',
    caseNo,
    code === currentCode ? options.blockers : [],
    code === currentCode ? options.warnings : [],
  ));
  return {
    case_no: caseNo,
    base_revision: 1,
    lifecycle_status: lifecycle,
    branch_type: branch,
    current_core_stage_code: currentCode,
    current_core_stage_ordinal: currentCode === null ? null : CORE_STAGE_CODES.indexOf(currentCode) + 1,
    core_stages: stages,
    source_projection_digest: 'a'.repeat(64),
  };
}

function stageCounts(overrides: Partial<Record<CoreStageCode, number>> = {}) {
  return Object.fromEntries(
    CORE_STAGE_CODES.map((code) => [code, overrides[code] ?? 0]),
  );
}

function substatusCounts(
  stage: CoreStageCode | undefined,
  overrides: Partial<Record<CoreStageSubstatusCode, number>> = {},
) {
  if (stage === undefined) return {};
  return Object.fromEntries(
    substatusCodesForStage(stage).map((code) => [code, overrides[code] ?? 0]),
  );
}

function corePage(
  items: unknown[],
  options: {
    selectedStage?: CoreStageCode;
    stageCounts?: Partial<Record<CoreStageCode, number>>;
    substatusCounts?: Partial<Record<CoreStageSubstatusCode, number>>;
    nextCursor?: string | null;
  } = {},
) {
  return {
    items,
    stage_counts: stageCounts(options.stageCounts),
    substatus_counts: substatusCounts(options.selectedStage, options.substatusCounts),
    next_cursor: options.nextCursor ?? null,
    etag: 'b'.repeat(64),
  };
}

function orderSummary(
  caseNo: string,
  clientName: string,
  staffName: string | null,
  startDate: string,
  endDate: string,
) {
  return {
    case_no: caseNo,
    client_name: clientName,
    order_status: '服務中',
    staff_name: staffName,
    identity_status: '一般市民',
    start_date: startDate,
    end_date: endDate,
    actual_start_date: null,
    actual_end_date: null,
    service_days: 20,
    total_employer_self_pay_payable: 12000,
  };
}

function summaryPage(items: unknown[]) {
  return { items, next_cursor: null, etag: 'c'.repeat(64) };
}

function cardFor(caseNo: string): HTMLElement {
  const card = screen.getByText(caseNo).closest('article');
  if (!(card instanceof HTMLElement)) throw new Error(`找不到 ${caseNo} 案件卡`);
  return card;
}

function formalServicePage(substatus?: CoreStageSubstatusCode) {
  const planned = ['CASE-PLAN-1', 'CASE-PLAN-2', 'CASE-PLAN-3'].map((caseNo) =>
    timeline(caseNo, 'formal_service', 'not_started'));
  const active = ['CASE-ACTIVE-1', 'CASE-ACTIVE-2', 'CASE-ACTIVE-3', 'CASE-ACTIVE-4'].map((caseNo) =>
    timeline(caseNo, 'formal_service', 'in_progress'));
  const all = [...active, ...planned];
  const items = substatus === 'waiting_to_start'
    ? planned
    : substatus === 'service_in_progress'
      ? active
      : all;
  return corePage(items, {
    selectedStage: 'formal_service',
    stageCounts: { formal_service: 7, intake_validation: 2 },
    substatusCounts: { waiting_to_start: 3, service_in_progress: 4 },
  });
}

describe('待辦看板 Beta 正式十三階段 contract', () => {
  it('接受已完成但訂金未付的人工放行正式子狀態', () => {
    const stage = coreStage('deposit_settlement', 'completed', 'CASE-OVERRIDE');

    expect(CoreStageProjectionSchema.parse({
      ...stage,
      substatus_code: 'deposit_unpaid_override',
      warnings: [{ code: 'deposit_unpaid_override_active', message: '定金仍未付款，已由管理員人工放行。' }],
    }).substatus_code).toBe('deposit_unpaid_override');
    expect(substatusCodesForStage('deposit_settlement')).toContain('deposit_unpaid_override');
    expect(substatusCodesForStage('deposit_settlement')).toHaveLength(6);
    expect(substatusCodesForStage('confirmed_service_dates')).toEqual([
      'date_confirmation_pending',
      'date_confirmation_in_progress',
      'date_confirmation_blocked',
      'date_confirmed',
      'date_confirmation_unavailable',
    ]);
  });

  beforeEach(() => {
    vi.spyOn(caseStatisticsQueryClient, 'query').mockReset().mockImplementation(async (year, quarter, month) => statisticsResult(year, quarter, month));
    vi.spyOn(hcmResubmissionClient, 'current').mockReset().mockResolvedValue({ items: [], next_cursor: null });
    clientMocks.getCoreStageTimelines.mockReset();
    clientMocks.loadSummaries.mockReset();
    clientMocks.loadSummaries.mockResolvedValue(summaryPage([]));
  });

  it('從後續進件問題分頁顯示住宅型態驗證問題，保留其他案件的服務缺件提示', async () => {
    clientMocks.getCoreStageTimelines.mockResolvedValue(corePage([
      timeline('CASE-DATES', 'intake_validation', 'in_progress', {
        lifecycle: '待補件', blockers: [{ code: 'orders_terms_missing', message: '缺少欄位：服務開始日。' }],
      }),
      timeline('CASE-RESIDENCE', 'intake_validation', 'in_progress', { lifecycle: '待補件' }),
    ]));
    const current = vi.mocked(hcmResubmissionClient.current)
      .mockResolvedValueOnce({
        items: [{ source_id: 40, review_identity: 'unrelated', case_no: 'CASE-OTHER', fields: ['手機'], can_correct: true }],
        next_cursor: 40,
      })
      .mockResolvedValueOnce({
        items: [{ source_id: 30, review_identity: 'residence-review', case_no: 'CASE-RESIDENCE', fields: ['居住型態'], can_correct: true }],
        next_cursor: null,
      });

    render(<OrderWorkbenchV2Page />);

    await screen.findByText('居住型態');
    const residence = cardFor('CASE-RESIDENCE');
    expect(within(residence).getByText('進件欄位待修正')).toBeInTheDocument();
    expect(within(residence).queryByText('手機')).not.toBeInTheDocument();
    expect(within(cardFor('CASE-DATES')).getByText('缺少欄位：服務開始日。')).toBeInTheDocument();
    expect(within(cardFor('CASE-DATES')).queryByText('阻塞 · 進件與資料完整性驗證')).not.toBeInTheDocument();
    expect(within(cardFor('CASE-DATES')).queryByText('居住型態')).not.toBeInTheDocument();
    expect(current).toHaveBeenNthCalledWith(2, 40, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('進件問題續頁失敗時顯示讀取失敗，不以部分清單聲稱問題已完整取得', async () => {
    clientMocks.getCoreStageTimelines.mockResolvedValue(corePage([
      timeline('CASE-RESIDENCE', 'intake_validation', 'in_progress', { lifecycle: '待補件' }),
    ]));
    vi.mocked(hcmResubmissionClient.current)
      .mockResolvedValueOnce({
        items: [{ source_id: 40, review_identity: 'unrelated', case_no: 'CASE-OTHER', fields: ['手機'], can_correct: true }],
        next_cursor: 40,
      })
      .mockRejectedValueOnce(new Error('review page unavailable'));

    render(<OrderWorkbenchV2Page />);

    expect(await screen.findByText('原始進件欄位問題讀取失敗，請重新讀取案件。')).toBeInTheDocument();
    expect(within(cardFor('CASE-RESIDENCE')).queryByText('手機')).not.toBeInTheDocument();
  });

  it('案件卡只顯示目前階段通知，不提前顯示未來客戶結算阻塞', async () => {
    const current = timeline('CASE-CURRENT-NOTICE', 'confirmed_service_dates');
    const withFutureSettlementBlocker = {
      ...current,
      core_stages: current.core_stages.map((stage) => stage.code === 'client_settlement'
        ? {
            ...stage,
            status: 'blocked' as const,
            substatus_code: SUBSTATUS_BY_STAGE_STATUS.client_settlement.blocked,
            blockers: [{
              code: 'client_settlement_not_complete',
              message: 'Client Finance 子投影尚未完成。',
            }],
          }
        : stage),
    };
    clientMocks.getCoreStageTimelines.mockResolvedValue(corePage([
      withFutureSettlementBlocker,
    ], {
      stageCounts: { confirmed_service_dates: 1 },
    }));

    render(<OrderWorkbenchV2Page />);

    await screen.findByText('CASE-CURRENT-NOTICE');
    const card = cardFor('CASE-CURRENT-NOTICE');
    expect(within(card).getByText('服務日期確認')).toBeInTheDocument();
    expect(within(card).queryByText('Client Finance 子投影尚未完成。')).not.toBeInTheDocument();
    expect(within(card).queryByText(/阻塞 · 客戶端結算/)).not.toBeInTheDocument();
  });

  it('移除阻塞篩選，搜尋清除後保留所有案件與卡片阻塞原因', async () => {
    clientMocks.loadSummaries.mockResolvedValue(summaryPage([]));
    clientMocks.getCoreStageTimelines.mockResolvedValue(corePage([
      timeline('CASE-BLOCKED', 'matching_pool', 'blocked', { blockers: [{ code: 'needs_data', message: '資料待補' }] }),
      timeline('CASE-OPEN', 'matching_pool'),
    ], { stageCounts: { matching_pool: 2 } }));
    render(<OrderWorkbenchV2Page />);
    await screen.findByText('CASE-OPEN');
    const count = document.querySelector('.order-v2-result-count')!;
    fireEvent.change(screen.getByRole('textbox', { name: '搜尋案件編號或姓名' }), { target: { value: 'CASE-OPEN' } });
    expect(count).toHaveTextContent('顯示 1／ 2 筆');
    fireEvent.click(screen.getByRole('button', { name: '清除篩選' }));
    expect(screen.getByText('CASE-OPEN')).toBeInTheDocument();
    expect(count).toHaveTextContent('顯示 2／ 2 筆');
    expect(screen.getByText('CASE-BLOCKED')).toBeInTheDocument();
    expect(within(cardFor('CASE-BLOCKED')).getByText('資料待補')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /有阻塞/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '全部案件' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '開啟案件 CASE-OPEN 案件處理' })).toBe(cardFor('CASE-OPEN'));
    expect(within(cardFor('CASE-OPEN')).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('案件顯示方式')).not.toBeInTheDocument();
  });

  it('保留正式階段總數與案件摘要，不再提供已移除的小狀態篩選', async () => {
    clientMocks.loadSummaries.mockResolvedValue(summaryPage([
      orderSummary('CASE-PLAN-1', '林小芳', null, '2026-10-01', '2026-10-20'),
      orderSummary('CASE-ACTIVE-1', '王小明', '陳月嫂', '2026-09-01', '2026-09-20'),
    ]));
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      if (params.stage === 'formal_service') {
        return formalServicePage(params.substatus_code);
      }
      return corePage([
        timeline('CASE-INTAKE', 'intake_validation', 'not_started'),
      ], {
        selectedStage: params.stage,
        stageCounts: { intake_validation: 2, formal_service: 7 },
        substatusCounts: { intake_pending: 2 },
      });
    });

    render(<OrderWorkbenchV2Page />);
    expect(screen.queryByRole('checkbox', { name: '只看阻塞' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: '只看提醒' })).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByRole('button', { name: /10 排班\/服務 7/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /10 排班\/服務 7/ }));

    await screen.findByText('CASE-ACTIVE-1');
    expect(screen.queryByRole('button', { name: /待開工 3/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /服務進行中 4/ })).not.toBeInTheDocument();

    await waitFor(() => {
      expect(within(cardFor('CASE-ACTIVE-1')).getByText('王小明')).toBeInTheDocument();
      expect(within(cardFor('CASE-ACTIVE-1')).getByText('編號待確認 陳月嫂')).toBeInTheDocument();
      expect(within(cardFor('CASE-PLAN-1')).getByText('尚未正式指派')).toBeInTheDocument();
    });

    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({
        workbench_scope: 'in_progress',
        stage: 'formal_service',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.getByText('CASE-PLAN-1')).toBeInTheDocument());
    expect(screen.getByText('CASE-ACTIVE-1')).toBeInTheDocument();
    expect(clientMocks.getCoreStageTimelines.mock.calls.at(-1)![0]).not.toHaveProperty('substatus_code');
  });

  it('只查詢進行中案件，統計期間只查 Reporting、不改變待辦搜尋', async () => {
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      return corePage([
        timeline('CASE-NORMAL', 'intake_validation', 'blocked', {
          blockers: [{ code: 'intake_blocked', message: '缺少必要資料' }],
          warnings: [{ code: 'intake_warning', message: '請確認聯絡資訊' }],
        }),
      ], {
        selectedStage: params.stage,
        stageCounts: { intake_validation: 1 },
        substatusCounts: { intake_blocked: 1 },
      });
    });

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledWith(
      expect.objectContaining({ workbench_scope: 'in_progress', stage: undefined }),
      expect.any(Object),
    ));

    const searchInput = screen.getByRole('textbox', { name: '搜尋案件編號或姓名' });
    const callsBeforeSearch = clientMocks.getCoreStageTimelines.mock.calls.length;
    fireEvent.change(searchInput, {
      target: { value: 'CASE-SEARCH' },
    });
    await waitFor(() => expect(screen.getByText('目前沒有符合條件的案件。')).toBeInTheDocument());
    expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledTimes(callsBeforeSearch);

    fireEvent.change(searchInput, { target: { value: '' } });
    await waitFor(() => expect(screen.getByText('CASE-NORMAL')).toBeInTheDocument());

    expect(screen.queryByRole('button', { name: '完成訂單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消訂單' })).not.toBeInTheDocument();
    const statistics = screen.getByRole('region', { name: '案件受理統計' });
    expect(within(statistics).queryByText('UI 預覽・示意數據')).not.toBeInTheDocument();
    expect(statistics.querySelectorAll('dt')).toHaveLength(10);
    await waitFor(() => expect(statistics.querySelector('.workbench-statistics-total strong')!.textContent).toBe('12'));
    const initialTotal = statistics.querySelector('.workbench-statistics-total strong')!.textContent;
    fireEvent.change(within(statistics).getByLabelText('季度'), { target: { value: '2' } });
    expect(within(statistics).getByText('2026/04/01－2026/06/30')).toBeInTheDocument();
    await waitFor(() => expect(statistics.querySelector('.workbench-statistics-total strong')!.textContent).toBe('2'));
    expect(statistics.querySelector('.workbench-statistics-total strong')!.textContent).not.toBe(initialTotal);
    expect(statistics.querySelector('.workbench-statistics-annual strong')!.textContent).toBe('12');
    expect(within(statistics).getByLabelText('月份').querySelectorAll('option')).toHaveLength(4);
    fireEvent.change(within(statistics).getByLabelText('月份'), { target: { value: '5' } });
    expect(within(statistics).getByText('2026/05/01－2026/05/31')).toBeInTheDocument();
    fireEvent.change(within(statistics).getByLabelText('季度'), { target: { value: '4' } });
    expect(within(statistics).getByLabelText('月份')).toHaveValue('0');
    fireEvent.change(within(statistics).getByLabelText('年度'), { target: { value: '2025' } });
    expect(within(statistics).getByText('2025/10/01－2025/12/31')).toBeInTheDocument();
    await waitFor(() => expect(caseStatisticsQueryClient.query).toHaveBeenLastCalledWith(2025, 4, null, expect.any(Object)));
    expect(statistics.querySelectorAll('dt')).toHaveLength(10);
    expect(screen.getByText('CASE-NORMAL')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '13 個核心訂單階段' })).toBeInTheDocument();
    expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledTimes(callsBeforeSearch);
  });

  it('統計讀取失敗顯示缺值，可重試；看板重新整理會更新統計', async () => {
    clientMocks.getCoreStageTimelines.mockResolvedValue(corePage([]));
    vi.mocked(caseStatisticsQueryClient.query).mockRejectedValueOnce(new Error('unavailable'));
    render(<OrderWorkbenchV2Page />);
    const retry = await screen.findByRole('button', { name: '統計讀取失敗・重試' });
    const statistics = screen.getByRole('region', { name: '案件受理統計' });
    expect(statistics.querySelector('.workbench-statistics-total strong')).toHaveTextContent('—');
    expect(statistics.querySelectorAll('dt')).toHaveLength(10);
    fireEvent.click(retry);
    await waitFor(() => expect(statistics.querySelector('.workbench-statistics-total strong')).toHaveTextContent('12'));
    const beforeRefresh = vi.mocked(caseStatisticsQueryClient.query).mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '重新整理' }));
    await waitFor(() => expect(caseStatisticsQueryClient.query).toHaveBeenCalledTimes(beforeRefresh + 1));
  });

  it('快速切換統計月份時取消舊請求，晚到回應不覆蓋新數據', async () => {
    let resolveInitial!: (value: CaseStatisticsData) => void;
    vi.mocked(caseStatisticsQueryClient.query).mockReturnValueOnce(new Promise((resolve) => { resolveInitial = resolve; }));
    render(<WorkbenchCaseStatistics />);
    await waitFor(() => expect(caseStatisticsQueryClient.query).toHaveBeenCalledTimes(1));
    const signal = vi.mocked(caseStatisticsQueryClient.query).mock.calls[0][3]!.signal!;
    fireEvent.change(screen.getByLabelText('月份'), { target: { value: '5' } });
    const total = document.querySelector('.workbench-statistics-total strong')!;
    await waitFor(() => expect(total).toHaveTextContent('5'));
    expect(signal.aborted).toBe(true);
    resolveInitial(statisticsResult(2026, null, null));
    await waitFor(() => expect(total).toHaveTextContent('5'));
    expect(screen.getByText('2026/05/01－2026/05/31')).toBeInTheDocument();
  });

  it('未分類的不符合案件與週報同樣顯示未知，不將缺值顯示成零', async () => {
    const response = statisticsResult(2026, null, null);
    vi.mocked(caseStatisticsQueryClient.query).mockResolvedValue({ ...response, summary: {
      ...response.summary, general_eligible_count: 11, general_ineligible_count: null,
      subsidized_ineligible_count: null, unclassified_qualification_count: 1,
    } });
    render(<WorkbenchCaseStatistics />);
    await screen.findByText('部分資料待確認');
    const cells = document.querySelectorAll('.workbench-statistics-grid.qualifications dd');
    expect(cells[1]).toHaveTextContent('—');
    expect(cells[3]).toHaveTextContent('—');
    expect(document.querySelector('.workbench-statistics-total strong')).toHaveTextContent('12');
  });

  it('快速切換篩選時忽略已失效 request 的晚到 response', async () => {
    let resolveInitial!: (value: ReturnType<typeof corePage>) => void;
    const initialRequest = new Promise<ReturnType<typeof corePage>>((resolve) => {
      resolveInitial = resolve;
  });
    clientMocks.getCoreStageTimelines
      .mockReturnValueOnce(initialRequest)
      .mockResolvedValueOnce(corePage([
        timeline('CASE-FRESH', 'formal_service', 'in_progress'),
      ], {
        selectedStage: 'formal_service',
        stageCounts: { formal_service: 1 },
        substatusCounts: { service_in_progress: 1 },
      }));

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: /10 排班\/服務 0/ }));

    await waitFor(() => expect(screen.getByText('CASE-FRESH')).toBeInTheDocument());
    resolveInitial(corePage([
      timeline('CASE-STALE', 'intake_validation', 'not_started'),
    ], {
      selectedStage: 'intake_validation',
      stageCounts: { intake_validation: 1 },
      substatusCounts: { intake_pending: 1 },
    }));

    await Promise.resolve();
    await Promise.resolve();
    expect(screen.queryByText('CASE-STALE')).not.toBeInTheDocument();
    expect(screen.getByText('CASE-FRESH')).toBeInTheDocument();
  });

  it('正式API 無法使用時顯示明確錯誤，且不使用舊 projection fallback', async () => {
    clientMocks.getCoreStageTimelines.mockRejectedValue(
      new Error('503 core-stage source unavailable'),
    );

    render(<OrderWorkbenchV2Page />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('正式十三階段查詢失敗');
    expect(alert).toHaveTextContent('不會改用舊投影或前端推導');
    expect(alert).toHaveTextContent('503 core-stage source unavailable');
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
  });
});
