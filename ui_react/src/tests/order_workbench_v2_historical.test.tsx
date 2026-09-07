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
  core: vi.fn(),
  summaries: vi.fn(),
}));

vi.mock('../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core },
}));
vi.mock('../api/orders/order_query_client', () => ({
  loadAllOrderSummaries: mocks.summaries,
  ordersQueryClient: { getOrderSummaries: vi.fn() },
}));

function stages(caseNo: string) {
  return CORE_STAGE_CODES.map((code, index) => ({
    ordinal: index + 1,
    code,
    label: code,
    owner: `owner-${code}`,
    status: 'completed',
    substatus_code: SUBSTATUS_BY_STAGE_STATUS[code].completed,
    source: { owner: `source-${code}`, identity: `${code}:${caseNo}`, version: 1 },
    occurred_at: null,
    blockers: [],
    warnings: [],
    available_read_actions: [],
    availability_reason: null,
  }));
}

function historical(caseNo: string, lifecycle: string) {
  return {
    case_no: caseNo,
    base_revision: 9,
    lifecycle_status: lifecycle,
    branch_type: 'historical',
    current_core_stage_code: null,
    current_core_stage_ordinal: null,
    historical_current_owner_stage_code: 'confirmed_service_dates',
    historical_current_owner_stage_ordinal: 9,
    core_stages: stages(caseNo),
    source_projection_digest: 'a'.repeat(64),
  };
}

function counts() {
  return Object.fromEntries(CORE_STAGE_CODES.map((code) => [code, 0]));
}

function page(items: unknown[], lifecycleCounts = {
  unserved: 2,
  in_service: 3,
  service_completed: 4,
  accounting_completed: 5,
}) {
  return {
    items,
    stage_counts: counts(),
    substatus_counts: {},
    historical_lifecycle_counts: lifecycleCounts,
    next_cursor: null,
    etag: 'b'.repeat(64),
  };
}

function normalPage(selectedStage: CoreStageCode = 'intake_validation') {
  return {
    items: [],
    stage_counts: counts(),
    substatus_counts: Object.fromEntries(substatusCodesForStage(selectedStage).map((code) => [code, 0])),
    historical_lifecycle_counts: { unserved: 0, in_service: 0, service_completed: 0, accounting_completed: 0 },
    next_cursor: null,
    etag: 'c'.repeat(64),
  };
}

describe('待辦看板 Beta historical lifecycle branch', () => {
  beforeEach(() => {
    mocks.core.mockReset();
    mocks.summaries.mockReset();
    mocks.summaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'd'.repeat(64) });
    mocks.core.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      if (params.branch_type !== 'historical') return normalPage(params.stage ?? 'intake_validation');
      if (params.historical_lifecycle === 'unserved') {
        return page([historical('CASE-FUTURE', '歷史訂單－未服務')]);
      }
      return page([
        historical('CASE-U', '歷史訂單－未服務'),
        historical('CASE-I', '歷史訂單－服務中'),
      ]);
    });
  });

  it('四種 lifecycle 使用 server counts 並可獨立重查；future source date 不參與 lifecycle 判定', async () => {
    render(<OrderWorkbenchV2Page />);

    fireEvent.click(await screen.findByRole('button', { name: '歷史訂單' }));
    await waitFor(() => expect(screen.getByRole('button', { name: /未服務 2/ })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /服務中 3/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /服務完成 4/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /帳務完成 5/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /全部 14/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /未服務 2/ }));
    await waitFor(() => expect(mocks.core).toHaveBeenLastCalledWith(
      expect.objectContaining({
        branch_type: 'historical',
        historical_lifecycle: 'unserved',
        stage: undefined,
        substatus_code: undefined,
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => expect(screen.getByText('CASE-FUTURE')).toBeInTheDocument());
    expect(screen.getByText('Lifecycle：歷史訂單－未服務')).toBeInTheDocument();
  });
});
