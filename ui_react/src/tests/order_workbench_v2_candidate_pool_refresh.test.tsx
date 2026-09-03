import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageCode,
} from '../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../api/orders/order_core_stage_projection_client';
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
});
