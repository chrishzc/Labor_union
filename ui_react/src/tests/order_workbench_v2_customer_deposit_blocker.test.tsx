import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageCode,
  type CoreStageStatus,
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

vi.mock('../components/OrderCandidateContactStatusPanel', () => ({
  OrderCandidateContactStatusPanel: () => null,
}));
vi.mock('../components/OrderCandidateQueryPanel', () => ({
  OrderCandidateQueryPanel: () => null,
}));
vi.mock('../components/OrderCaregiverContractPanel', () => ({
  OrderCaregiverContractPanel: () => null,
}));
vi.mock('../components/OrderFormalRecommendationPanel', () => ({
  OrderFormalRecommendationPanel: () => null,
}));
vi.mock('../components/OrderGovernmentSubsidyLane', () => ({
  OrderGovernmentSubsidyLane: () => null,
}));
vi.mock('../components/OrderTerminalAggregateLane', () => ({
  OrderTerminalAggregateLane: () => null,
}));
vi.mock('../components/OrderWorkbenchV2Drawer', () => ({
  OrderWorkbenchV2Drawer: () => null,
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
  blockers: readonly { code: string; message: string }[] = [],
) {
  return {
    ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
    code,
    label: STAGE_LABELS[code],
    owner: code === 'deposit_settlement' ? 'Client Finance' : `owner-${code}`,
    status,
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
    source: {
      owner: code === 'deposit_settlement' ? 'Client Finance' : `source-${code}`,
      identity: `${code}:CASE-DEPOSIT-OPEN`,
      version: 1,
    },
    occurred_at: null,
    blockers,
    warnings: [],
    available_read_actions: [],
    availability_reason: null,
  };
}

function stageCounts(depositCount: number) {
  return Object.fromEntries(
    CORE_STAGE_CODES.map((code) => [code, code === 'deposit_settlement' ? depositCount : 0]),
  );
}

function substatusCounts(selectedStage: CoreStageCode) {
  return Object.fromEntries(
    substatusCodesForStage(selectedStage).map((code) => [
      code,
      selectedStage === 'deposit_settlement' && code === 'deposit_blocked' ? 1 : 0,
    ]),
  );
}

function pageFor(selectedStage: CoreStageCode) {
  const isDeposit = selectedStage === 'deposit_settlement';
  return {
    items: isDeposit
      ? [{
          case_no: 'CASE-DEPOSIT-OPEN',
          base_revision: 7,
          lifecycle_status: '已成立',
          branch_type: 'normal',
          current_core_stage_code: 'deposit_settlement',
          current_core_stage_ordinal: 7,
          core_stages: CORE_STAGE_CODES.map((code) => stage(
            code,
            code === 'deposit_settlement' ? 'blocked' : 'completed',
            code === 'deposit_settlement'
              ? [{ code: 'deposit_not_settled', message: '仍有未結清訂金' }]
              : [],
          )),
          source_projection_digest: 'a'.repeat(64),
        }]
      : [],
    stage_counts: stageCounts(1),
    substatus_counts: substatusCounts(selectedStage),
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}

describe('待辦看板 Beta 客戶訂金 blocker', () => {
  beforeEach(() => {
    clientMocks.getCoreStageTimelines.mockReset();
    clientMocks.loadSummaries.mockReset();
    clientMocks.loadSummaries.mockResolvedValue({
      items: [],
      next_cursor: null,
      etag: 'c'.repeat(64),
    });
    clientMocks.getCoreStageTimelines.mockImplementation(
      async (params: OrderCoreStageProjectionQueryParams) => pageFor(params.stage ?? 'intake_validation'),
    );
  });

  it('第 7 階直接顯示 Client Finance 回傳的未結清訂金獨立阻礙', async () => {
    render(<OrderWorkbenchV2Page />);

    const depositStage = await screen.findByRole('button', { name: /7 定金 1/ });
    fireEvent.click(depositStage);

    await waitFor(() => expect(clientMocks.getCoreStageTimelines).toHaveBeenLastCalledWith(
      expect.objectContaining({
        branch_type: 'normal',
        stage: 'deposit_settlement',
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));

    expect(await screen.findByText('CASE-DEPOSIT-OPEN')).toBeInTheDocument();
    const blocker = screen.getByText('客戶定金核銷：仍有未結清訂金');
    expect(blocker).toBeInTheDocument();
    expect(blocker.closest('article')).toHaveTextContent('CASE-DEPOSIT-OPEN');
    expect(screen.getByText('阻塞')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /定金阻塞 1/ })).toBeInTheDocument();
  });
});
