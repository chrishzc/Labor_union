import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  type CoreStageCode,
} from '../api/orders/order_core_stage_projection_schemas';
import { OrderWorkbenchV2Drawer } from '../components/OrderWorkbenchV2Drawer';

const mocks = vi.hoisted(() => ({
  getCoreStageTimelines: vi.fn(),
  getOrderDetail: vi.fn(),
  getOrderTerms: vi.fn(),
  getAssignmentPlan: vi.fn(),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: {
    getCoreStageTimelines: mocks.getCoreStageTimelines,
  },
}));

vi.mock('../api/orders/order_query_client', () => ({
  ordersQueryClient: {
    getOrderDetail: mocks.getOrderDetail,
    getOrderTerms: mocks.getOrderTerms,
    getAssignmentPlan: mocks.getAssignmentPlan,
  },
}));

vi.mock('../components/OrderAutomaticCompletionStatus', () => ({
  OrderAutomaticCompletionStatus: ({ caseNo, onObserved }: { caseNo: string; onObserved: () => void }) => <section aria-label="自動完工狀態"><p>預計服務完成時間・{caseNo}</p><p>尚未到服務完成時間</p><button type="button" onClick={onObserved}>test-owner-background-readback</button></section>,
}));
vi.mock('../components/ServiceArrangementDepositGate', () => ({ ServiceArrangementDepositGate: () => <p>訂金鎖狀態</p> }));
vi.mock('../components/ContractExternalSigningActions', () => ({
  ContractExternalSigningActions: ({ onCommitted, onOpenServiceDates }: { onCommitted: () => void; onOpenServiceDates: () => void }) => <section><button type="button" onClick={onCommitted}>test-signing-completed</button><button type="button" onClick={onOpenServiceDates}>前往確認服務日期與排班 →</button></section>,
}));
vi.mock('../components/OrderServiceDatesPanel', () => ({
  OrderServiceDatesPanel: () => <p>服務日期工作區</p>,
}));
vi.mock('../components/OrderAssignmentPlanPanel', () => ({
  OrderAssignmentPlanPanel: () => <p>正式排班工作區</p>,
}));
vi.mock('../components/OrderActualStartPanel', () => ({
  OrderActualStartPanel: () => <section aria-label="已開啟開始日調整">開始日調整表單</section>,
}));

function timeline(caseNo: string, currentCode: CoreStageCode) {
  return {
    case_no: caseNo,
    base_revision: 1,
    lifecycle_status: '服務中',
    branch_type: 'normal',
    current_core_stage_code: currentCode,
    current_core_stage_ordinal: CORE_STAGE_CODES.indexOf(currentCode) + 1,
    historical_current_owner_stage_code: null,
    historical_current_owner_stage_ordinal: null,
    core_stages: CORE_STAGE_CODES.map((code, index) => {
      const status = code === currentCode ? 'in_progress' as const : index < CORE_STAGE_CODES.indexOf(currentCode) ? 'completed' as const : 'not_started' as const;
      return {
        ordinal: index + 1,
        code,
        label: code,
        owner: `owner-${code}`,
        status,
        substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][status],
        source: { owner: `owner-${code}`, identity: `${caseNo}:${code}`, version: 1 },
        occurred_at: null as string | null,
        blockers: [],
        warnings: [],
        available_read_actions: [],
        availability_reason: null,
      };
    }),
    source_projection_digest: 'd'.repeat(64),
  };
}

function detail(caseNo: string, orderStatus: string) {
  return {
    case_no: caseNo,
    client_id: 88,
    staff_id: 42,
    client_name: '測試客戶',
    staff_name: '測試月嫂',
    order_status: orderStatus,
    identity_status: '一般市民',
    cancel_reason: null,
    line_group_id: null,
    contract_identity: 'contract-142',
    actual_start_date: '2026-09-01',
    actual_end_date: null,
    deposit_date: null,
    start_date: '2026-09-01',
    end_date: '2026-09-20',
    service_days: 20,
    service_hours_per_day: 9,
    deposit_service_days: null,
    floor_fee: 0,
    custom_rest_dates: null,
  };
}

const terms = {
  case_no: 'CASE-142',
  order_version: 4,
  scheduling_version: 5,
  scheduling_generation: 1,
  client_finance_version: 2,
  payroll_version: 2,
  service_data_locked: true,
  terms: {
    planned_start_date: '2026-09-01',
    service_days: 20,
    service_hours_per_day: 9,
    requires_cooking: false,
    floor_fee_ntd: 0,
    service_time: { start_time: '09:00:00', end_time: '18:00:00', end_day_offset: 0 },
  },
};

const assignment = {
  case_no: 'CASE-142',
  order_version: 4,
  scheduling_version: 5,
  scheduling_generation: 1,
  client_finance_version: 2,
  payroll_version: 2,
  contracted_service_days: 20,
  service_hours_per_day: 9,
  service_started: true,
  assignments: [],
};

describe('OrderWorkbenchV2Drawer service completion wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getCoreStageTimelines.mockResolvedValueOnce({ items: [timeline('CASE-142', 'service_completion')] })
      .mockResolvedValue({ items: [{ ...timeline('CASE-142', 'staff_payout'), lifecycle_status: '訂單完成' }] });
    mocks.getOrderDetail
      .mockResolvedValueOnce(detail('CASE-142', '服務中'))
      .mockResolvedValue(detail('CASE-142', '訂單完成'));
    mocks.getOrderTerms.mockResolvedValue(terms);
    mocks.getAssignmentPlan.mockResolvedValue(assignment);
  });

  it('shows automatic completion status without a manual completion action and refreshes on owner state changes', async () => {
    render(<OrderWorkbenchV2Drawer caseNo="CASE-142" branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('heading', { name: '客戶與月嫂確認排班' });
    expect(screen.queryByRole('button', { name: '辦理完工確認' })).not.toBeInTheDocument();
    expect(screen.getByText('預計服務完成時間・CASE-142')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '服務前更換月嫂 →' })).toBeInTheDocument();

    const completion = await screen.findByRole('button', { name: 'test-owner-background-readback' });
    expect(mocks.getOrderDetail).toHaveBeenCalledTimes(1);

    fireEvent.click(completion);

    await screen.findByRole('heading', { name: '服務完工' });
    expect(screen.getByRole('region', { name: '服務完工摘要' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /客戶收款與月嫂結算/ })).not.toBeInTheDocument();

    await waitFor(() => expect(mocks.getOrderDetail).toHaveBeenCalledTimes(2));
    expect(mocks.getCoreStageTimelines).toHaveBeenCalledTimes(2);
    expect(mocks.getOrderTerms).toHaveBeenCalledTimes(2);
    expect(mocks.getAssignmentPlan).toHaveBeenCalledTimes(2);
  });

  it('removes an open start-date rescheduling form when the background completion is read back', async () => {
    mocks.getAssignmentPlan.mockResolvedValue({ ...assignment, assignments: [{ assignment_id: 1, staff_id: 42, sequence: 1, assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-20', official_service_dates: [] }] });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-142" branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '更正開始日並重排' }));
    expect(await screen.findByRole('region', { name: '已開啟開始日調整' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'test-owner-background-readback' }));
    await screen.findByRole('region', { name: '服務完工摘要' });
    expect(screen.queryByRole('region', { name: '已開啟開始日調整' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '更正完工服務日期' })).toBeInTheDocument();
  });

  it('keeps an unpaid completed case on its completion screen and links to the same-case accounts', async () => {
    const completed = { ...timeline('CASE-142', 'client_settlement'), lifecycle_status: '訂單完成' };
    const service = completed.core_stages.find(stage => stage.code === 'service_completion')!;
    service.occurred_at = '2026-09-20T18:00:00+08:00';
    mocks.getCoreStageTimelines.mockReset().mockResolvedValue({ items: [completed] });
    mocks.getOrderDetail.mockReset().mockResolvedValue({ ...detail('CASE-142', '訂單完成'), actual_end_date: '2026-09-20' });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-142" branchType="normal" onClose={vi.fn()} />);
    const summary = await screen.findByRole('region', { name: '服務完工摘要' });
    expect(within(summary).getByText('2026-09-01 ～ 2026-09-20')).toBeInTheDocument();
    expect(within(summary).getByText('2026/09/20 18:00')).toBeInTheDocument();
    expect(within(summary).getByText('客戶款項')).toBeInTheDocument();
    expect(within(summary).getByText('月嫂款項')).toBeInTheDocument();
    expect(within(summary).getByText('客戶結算中')).toBeInTheDocument();
    expect(within(summary).getByText('待月嫂結算')).toBeInTheDocument();
    expect(within(summary).queryByText('客戶已結清')).not.toBeInTheDocument();
    expect(within(summary).getByRole('link', { name: '查看本案帳務 →' })).toHaveAttribute('href', '#finance?tab=client-receipts&case_no=CASE-142&from=workbench');
    expect(screen.getByRole('complementary', { name: '案件辦理事項' }).querySelectorAll('button')).toHaveLength(5);
    expect(screen.queryByText('特殊訂金處理')).not.toBeInTheDocument();
  });

  it.each(['deposit_settlement', 'client_settlement', 'staff_payout'] as const)('routes the %s current stage to the service workspace without restoring a sixth step', async stage => {
    mocks.getCoreStageTimelines.mockReset().mockResolvedValue({ items: [{ ...timeline('CASE-142', stage), lifecycle_status: '訂單成立' }] });
    render(<OrderWorkbenchV2Drawer caseNo="CASE-142" branchType="normal" onClose={vi.fn()} />);
    await screen.findByRole('navigation', { name: '服務安排步驟' });
    expect(screen.getByRole('heading', { name: '確認服務日期與排班' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /客戶收款與月嫂結算/ })).not.toBeInTheDocument();
  });

  it('keeps the completed contract screen instead of jumping to unpaid receipts, then opens the same-case service workspace', async () => {
    mocks.getCoreStageTimelines.mockReset().mockResolvedValueOnce({ items: [timeline('CASE-142', 'external_signing_completion')] })
      .mockResolvedValue({ items: [timeline('CASE-142', 'deposit_settlement')] });
    mocks.getOrderDetail.mockReset().mockResolvedValue(detail('CASE-142', '訂單成立'));
    render(<OrderWorkbenchV2Drawer caseNo="CASE-142" branchType="normal" onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: 'test-signing-completed' }));
    await waitFor(() => expect(mocks.getCoreStageTimelines).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('heading', { name: '辦理契約與簽署' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '前往確認服務日期與排班 →' }));
    expect(await screen.findByRole('heading', { name: '設定服務日期' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '服務安排步驟' })).toBeInTheDocument();
  });
});
