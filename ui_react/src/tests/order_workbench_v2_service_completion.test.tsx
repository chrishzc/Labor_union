import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('../components/OrderServiceCompletionActions', () => ({
  OrderServiceCompletionActions: ({
    caseNo,
    orderStatus,
    onCompleted,
  }: {
    caseNo: string;
    orderStatus: string;
    onCompleted: () => void | Promise<void>;
  }) => (
    <button type="button" onClick={() => void onCompleted()}>
      completion:{caseNo}:{orderStatus}
    </button>
  ),
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
        occurred_at: null,
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
    mocks.getCoreStageTimelines.mockResolvedValue({ items: [timeline('CASE-142', 'service_completion')] });
    mocks.getOrderDetail
      .mockResolvedValueOnce(detail('CASE-142', '服務中'))
      .mockResolvedValue(detail('CASE-142', '訂單完成'));
    mocks.getOrderTerms.mockResolvedValue(terms);
    mocks.getAssignmentPlan.mockResolvedValue(assignment);
  });

  it('mounts the existing completion owner action and refreshes owner facts after completion', async () => {
    render(<OrderWorkbenchV2Drawer caseNo="CASE-142" branchType="normal" onClose={vi.fn()} />);

    const completion = await screen.findByRole('button', { name: 'completion:CASE-142:服務中' });
    expect(mocks.getOrderDetail).toHaveBeenCalledTimes(1);

    fireEvent.click(completion);

    await screen.findByRole('button', { name: 'completion:CASE-142:訂單完成' });
    await waitFor(() => expect(mocks.getOrderDetail).toHaveBeenCalledTimes(2));
    expect(mocks.getCoreStageTimelines).toHaveBeenCalledTimes(2);
    expect(mocks.getOrderTerms).toHaveBeenCalledTimes(2);
    expect(mocks.getAssignmentPlan).toHaveBeenCalledTimes(2);
  });
});
