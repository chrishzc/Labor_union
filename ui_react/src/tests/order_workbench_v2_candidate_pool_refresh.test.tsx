import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageCode,
} from '../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../api/orders/order_core_stage_projection_client';
import type { OrderSummaryPage } from '../api/orders/order_query_schemas';
import { OrderWorkbenchV2Page } from '../pages/OrderWorkbenchV2Page';

const mocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  loadSummaries: vi.fn(),
}));

vi.mock('../components/OrderCandidateQueryPanel', () => ({
  OrderCandidateQueryPanel: ({
    caseNo,
    onPoolReadback,
  }: {
    caseNo: string;
    onPoolReadback?: () => void;
  }) => (
    <button type="button" onClick={onPoolReadback}>
      模擬 {caseNo} 候選池回讀完成
    </button>
  ),
}));

vi.mock('../components/OrderServiceDatesPanel', () => ({
  OrderServiceDatesPanel: ({ onObserved }: { onObserved?: () => void }) => (
    <button type="button" onClick={onObserved}>模擬服務日期回讀完成</button>
  ),
}));

vi.mock('../components/OrderWorkbenchV2Drawer', () => ({
  OrderWorkbenchV2Drawer: ({ onClose }: { onClose: () => void }) => (
    <button type="button" onClick={onClose}>關閉測試工作 Drawer</button>
  ),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: mocks.getCoreStageTimelines,
  },
}));

vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: mocks.loadSummaries,
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

function stage(code: CoreStageCode, currentCode: CoreStageCode) {
  const status = code === currentCode ? 'in_progress' : 'completed';
  return {
    ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
    code,
    label: STAGE_LABELS[code],
    owner: `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: { owner: `source-${code}`, identity: `${code}:CASE-READBACK`, version: 1 },
    occurred_at: null,
    blockers: [],
    warnings: [],
    available_read_actions: [],
    availability_reason: null,
  };
}

function timeline(currentCode: CoreStageCode) {
  return {
    case_no: 'CASE-READBACK',
    base_revision: 1,
    lifecycle_status: '媒合中',
    branch_type: 'normal',
    current_core_stage_code: currentCode,
    current_core_stage_ordinal: CORE_STAGE_CODES.indexOf(currentCode) + 1,
    core_stages: CORE_STAGE_CODES.map((code) => stage(code, currentCode)),
    source_projection_digest: 'a'.repeat(64),
  };
}

function page(selectedStage: CoreStageCode, items: unknown[]) {
  return {
    items,
    stage_counts: Object.fromEntries(
      CORE_STAGE_CODES.map((code) => [code, code === 'matching_pool' ? 1 : 0]),
    ),
    substatus_counts: Object.fromEntries(
      substatusCodesForStage(selectedStage).map((code) => [code, 0]),
    ),
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}

function summaries(updated = false): OrderSummaryPage {
  return {
    items: [{
      case_no: 'CASE-READBACK',
      client_name: updated ? '回讀後測試客戶' : '回讀前測試客戶',
      order_status: '訂單成立',
      staff_name: updated ? '回讀後測試月嫂' : null,
      identity_status: null,
      start_date: updated ? '2026-09-10' : '2026-09-01',
      end_date: updated ? '2026-09-30' : '2026-09-21',
      actual_start_date: null,
      actual_end_date: null,
      service_days: 20,
      total_employer_self_pay_payable: null,
    }],
    next_cursor: null,
    etag: (updated ? 'd' : 'c').repeat(64),
  };
}

describe('待辦看板 Beta 候選池回讀後刷新正式投影', () => {
  beforeEach(() => {
    mocks.getCoreStageTimelines.mockReset();
    mocks.loadSummaries.mockReset();
    mocks.loadSummaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'c'.repeat(64) });
    mocks.getCoreStageTimelines.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      const selectedStage = params.stage ?? 'intake_validation';
      return page(selectedStage, [timeline(selectedStage)]);
    });
  });

  it('候選池回讀完成 callback 會以目前第 2 階條件重新查詢正式十三階段投影', async () => {
    render(<OrderWorkbenchV2Page />);

    await waitFor(() => expect(screen.getByRole('button', { name: /2 候選池 1/ })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /2 候選池 1/ }));
    const refreshButton = await screen.findByRole('button', { name: '模擬 CASE-READBACK 候選池回讀完成' });
    const callsBeforeRefresh = mocks.getCoreStageTimelines.mock.calls.length;

    fireEvent.click(refreshButton);

    await waitFor(() => expect(mocks.getCoreStageTimelines.mock.calls.length).toBeGreaterThan(callsBeforeRefresh));
    expect(mocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({ branch_type: 'normal', stage: 'matching_pool' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('候選池回讀後同時重新查詢姓名、服務期間與指派摘要，不沿用首次載入資料', async () => {
    mocks.loadSummaries.mockResolvedValueOnce(summaries()).mockResolvedValue(summaries(true));
    render(<OrderWorkbenchV2Page />);
    await screen.findByText('回讀前測試客戶');
    const originalSignal = mocks.loadSummaries.mock.calls[0]![2].signal as AbortSignal;
    fireEvent.click(screen.getByRole('button', { name: /2 候選池 1/ }));
    fireEvent.click(await screen.findByRole('button', { name: '模擬 CASE-READBACK 候選池回讀完成' }));

    expect(await screen.findByText('回讀後測試客戶')).toBeInTheDocument();
    expect(screen.getByText('2026-09-10 ~ 2026-09-30')).toBeInTheDocument();
    expect(screen.getByText('回讀後測試月嫂')).toBeInTheDocument();
    expect(screen.queryByText('回讀前測試客戶')).not.toBeInTheDocument();
    expect(mocks.loadSummaries).toHaveBeenCalledTimes(2);
    expect(originalSignal.aborted).toBe(true);
    expect(mocks.loadSummaries).toHaveBeenLastCalledWith(
      expect.any(Function),
      { lifecycle_scope: 'all', page_size: 200 },
      { signal: expect.any(AbortSignal) },
    );
  });

  it('服務日期正式回讀完成後刷新清單上的服務期間', async () => {
    mocks.loadSummaries.mockResolvedValueOnce(summaries()).mockResolvedValue(summaries(true));
    render(<OrderWorkbenchV2Page />);
    await screen.findByText('回讀前測試客戶');
    fireEvent.click(screen.getByRole('button', { name: /^9 / }));
    fireEvent.click(await screen.findByRole('button', { name: '模擬服務日期回讀完成' }));

    expect(await screen.findByText('2026-09-10 ~ 2026-09-30')).toBeInTheDocument();
    expect(mocks.loadSummaries).toHaveBeenCalledTimes(2);
    expect(mocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({ stage: 'confirmed_service_dates' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('離開工作 Drawer 後回讀正式摘要與階段，不要求整頁重新載入', async () => {
    mocks.loadSummaries.mockResolvedValueOnce(summaries()).mockResolvedValue(summaries(true));
    render(<OrderWorkbenchV2Page />);
    await screen.findByText('回讀前測試客戶');
    fireEvent.click(screen.getByRole('button', { name: '開啟唯讀工作 Drawer' }));
    const before = mocks.getCoreStageTimelines.mock.calls.length;
    fireEvent.click(screen.getByRole('button', { name: '關閉測試工作 Drawer' }));

    expect(await screen.findByText('回讀後測試客戶')).toBeInTheDocument();
    expect(mocks.loadSummaries).toHaveBeenCalledTimes(2);
    expect(mocks.getCoreStageTimelines.mock.calls.length).toBeGreaterThan(before);
    expect(screen.queryByRole('button', { name: '關閉測試工作 Drawer' })).not.toBeInTheDocument();
  });

  it('舊摘要請求晚到時不覆蓋操作後回讀的新資料', async () => {
    let resolveInitial!: (value: OrderSummaryPage) => void;
    mocks.loadSummaries.mockImplementationOnce(() => new Promise<OrderSummaryPage>((resolve) => { resolveInitial = resolve; }));
    mocks.loadSummaries.mockResolvedValue(summaries(true));
    render(<OrderWorkbenchV2Page />);
    await screen.findByRole('button', { name: /2 候選池 1/ });
    const originalSignal = mocks.loadSummaries.mock.calls[0]![2].signal as AbortSignal;
    fireEvent.click(screen.getByRole('button', { name: /2 候選池 1/ }));
    fireEvent.click(await screen.findByRole('button', { name: '模擬 CASE-READBACK 候選池回讀完成' }));
    await screen.findByText('回讀後測試客戶');

    await act(async () => { resolveInitial(summaries()); });

    expect(originalSignal.aborted).toBe(true);
    expect(screen.getByText('回讀後測試客戶')).toBeInTheDocument();
    expect(screen.queryByText('回讀前測試客戶')).not.toBeInTheDocument();
  });
});
