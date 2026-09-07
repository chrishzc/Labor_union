import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageBranchType,
  type CoreStageCode,
  type CoreStageStatus,
  type CoreStageSubstatusCode,
} from '../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const clientMocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: clientMocks.getCoreStageTimelines,
  },
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: clientMocks.loadSummaries,
  ordersQueryClient: { getOrderSummaries: vi.fn() },
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
  const all = [...planned, ...active];
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
  beforeEach(() => {
    clientMocks.getCoreStageTimelines.mockReset();
    clientMocks.loadSummaries.mockReset();
    clientMocks.loadSummaries.mockResolvedValue(summaryPage([]));
  });

  it('直接呈現 server stage/substatus counts，且第 10 階兩個子狀態可獨立查詢', async () => {
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
        selectedStage: 'intake_validation',
        stageCounts: { intake_validation: 2, formal_service: 7 },
        substatusCounts: { intake_pending: 2 },
      });
    });

    render(<OrderWorkbenchV2Page />);

    await waitFor(() => expect(screen.getByRole('button', { name: /10 排班\/服務 7/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /10 排班\/服務 7/ }));

    await waitFor(() => expect(screen.getByRole('button', { name: /待開工 3/ })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /服務進行中 4/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /服務阻塞 0/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /服務期間已完成 0/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /排班資料不可用 0/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /全部 7/ })).toBeInTheDocument();

    await waitFor(() => {
      expect(within(cardFor('CASE-ACTIVE-1')).getByText('王小明')).toBeInTheDocument();
      expect(within(cardFor('CASE-ACTIVE-1')).getByText('陳月嫂')).toBeInTheDocument();
      expect(within(cardFor('CASE-PLAN-1')).getByText('尚未正式指派')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /待開工 3/ }));
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({
        branch_type: 'normal',
        stage: 'formal_service',
        substatus_code: 'waiting_to_start',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.getByText('CASE-PLAN-1')).toBeInTheDocument());
    expect(screen.queryByText('CASE-ACTIVE-1')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /服務進行中 4/ }));
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({
        branch_type: 'normal',
        stage: 'formal_service',
        substatus_code: 'service_in_progress',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.getByText('CASE-ACTIVE-1')).toBeInTheDocument());
    expect(screen.queryByText('CASE-PLAN-1')).not.toBeInTheDocument();
  });

  it('搜尋、阻塞、提醒與 normal/historical/cancelled 都傳入正式 query', async () => {
    clientMocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      if (params.branch_type === 'historical') {
        return corePage([
          timeline('CASE-HISTORY', null, 'completed', {
            lifecycle: '歷史訂單－服務完成',
            branch: 'historical',
          }),
        ]);
      }
      if (params.branch_type === 'cancelled') {
        return corePage([
          timeline('CASE-CANCELLED', null, 'completed', {
            lifecycle: '訂單取消',
            branch: 'cancelled',
          }),
        ]);
      }
      return corePage([
        timeline('CASE-NORMAL', 'intake_validation', 'blocked', {
          blockers: [{ code: 'intake_blocked', message: '缺少必要資料' }],
          warnings: [{ code: 'intake_warning', message: '請確認聯絡資訊' }],
        }),
      ], {
        selectedStage: 'intake_validation',
        stageCounts: { intake_validation: 1 },
        substatusCounts: { intake_blocked: 1 },
      });
    });

    render(<OrderWorkbenchV2Page />);
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenCalledWith(
      expect.objectContaining({ branch_type: 'normal', stage: 'intake_validation' }),
      expect.any(Object),
    ));

    fireEvent.change(screen.getByRole('textbox', { name: '搜尋案件編號' }), {
      target: { value: 'CASE-SEARCH' },
    });
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({ case_no_search: 'CASE-SEARCH' }),
      expect.any(Object),
    ));

    fireEvent.click(screen.getByRole('checkbox', { name: '只看阻塞' }));
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({ blocker_only: true }),
      expect.any(Object),
    ));

    fireEvent.click(screen.getByRole('checkbox', { name: '只看提醒' }));
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({ blocker_only: true, warning_only: true }),
      expect.any(Object),
    ));

    fireEvent.click(screen.getByRole('button', { name: '歷史訂單' }));
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({
        branch_type: 'historical',
        stage: undefined,
        substatus_code: undefined,
      }),
      expect.any(Object),
    ));
    await waitFor(() => expect(screen.getByText('CASE-HISTORY')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: '取消訂單' }));
    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({
        branch_type: 'cancelled',
        stage: undefined,
        substatus_code: undefined,
      }),
      expect.any(Object),
    ));
    await waitFor(() => expect(screen.getByText('CASE-CANCELLED')).toBeInTheDocument());
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