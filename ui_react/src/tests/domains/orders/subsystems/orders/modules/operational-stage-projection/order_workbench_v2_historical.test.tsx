import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
} from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import type { OrderCoreStageProjectionQueryParams } from '../../../../../../../api/orders/order_core_stage_projection_client';
import { OrderWorkbenchV2Page } from '../../../../../../../pages/OrderWorkbenchV2Page';

const mocks = vi.hoisted(() => ({
  core: vi.fn(),
  summaries: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.core },
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({
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

describe('待辦看板依目前狀態整合歷史訂單', () => {
  beforeEach(() => {
    mocks.core.mockReset();
    mocks.summaries.mockReset();
    mocks.summaries.mockResolvedValue({ items: [], next_cursor: null, etag: 'd'.repeat(64) });
    mocks.core.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => {
      if (params.workbench_scope === 'completed') return page([
        historical('CASE-C', '歷史訂單－服務完成'), historical('CASE-D', '歷史訂單－帳務完成'),
      ]);
      if (params.workbench_scope === 'cancelled') return page([]);
      const result = page([historical('CASE-FUTURE', '歷史訂單－未服務')]);
      return { ...result, stage_counts: { ...counts(), confirmed_service_dates: 1 },
        substatus_counts: params.stage ? Object.fromEntries(substatusCodesForStage(params.stage).map((code) => [code, 1])) : {} };
    });
  });

  it('歷史未服務留在進行中，正式 owner stage 可篩選；完成與取消不顯示13階段', async () => {
    render(<OrderWorkbenchV2Page />);
    expect(await screen.findByText('CASE-FUTURE')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '歷史訂單' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /9 日期確認 1/ }));
    await waitFor(() => expect(mocks.core).toHaveBeenLastCalledWith(
      expect.objectContaining({ workbench_scope: 'in_progress', stage: 'confirmed_service_dates' }), expect.any(Object),
    ));
    expect(await screen.findByText('CASE-FUTURE')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '完成訂單' }));
    expect(await screen.findByText('CASE-C')).toBeInTheDocument();
    expect(screen.getByText('CASE-D')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '13 個核心訂單階段' })).not.toBeInTheDocument();
    expect(mocks.core).toHaveBeenLastCalledWith(expect.objectContaining({ workbench_scope: 'completed', stage: undefined, substatus_code: undefined }), expect.any(Object));
    fireEvent.click(screen.getByRole('button', { name: '取消訂單' }));
    await waitFor(() => expect(mocks.core).toHaveBeenLastCalledWith(expect.objectContaining({ workbench_scope: 'cancelled', stage: undefined }), expect.any(Object)));
    expect(screen.queryByRole('region', { name: '13 個核心訂單階段' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '進行中訂單' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '全部進行中' })).toHaveAttribute('aria-pressed', 'true'));
  });

  it('拒絕伺服器把洽談中案件回傳到完成清單，避免錯誤分類冒充成功', async () => {
    mocks.core.mockImplementation(async (params: OrderCoreStageProjectionQueryParams) => page(
      params.workbench_scope === 'completed'
        ? [{ ...historical('CASE-WRONG', '洽談中'), branch_type: 'normal' }] : [],
    ));
    render(<OrderWorkbenchV2Page />);
    fireEvent.click(screen.getByRole('button', { name: '完成訂單' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('不符合所選分類');
    expect(screen.queryByText('CASE-WRONG')).not.toBeInTheDocument();
  });

  it('接續分頁失敗時不把部分結果顯示成完整清單', async () => {
    mocks.core.mockResolvedValueOnce({ ...page([historical('CASE-A', '歷史訂單－未服務')]), next_cursor: 'CASE-A' })
      .mockRejectedValueOnce(new Error('第二頁查詢失敗'));
    render(<OrderWorkbenchV2Page />);
    expect(await screen.findByRole('alert')).toHaveTextContent('第二頁查詢失敗');
    expect(screen.queryByText('CASE-A')).not.toBeInTheDocument();
  });

  it('完整讀取接續分頁後才呈現全部案件', async () => {
    mocks.core.mockResolvedValueOnce({ ...page([historical('CASE-A', '歷史訂單－未服務')]), next_cursor: 'CASE-A' })
      .mockResolvedValueOnce(page([historical('CASE-B', '歷史訂單－服務中')]));
    render(<OrderWorkbenchV2Page />);
    expect(await screen.findByText('CASE-B')).toBeInTheDocument();
    expect(screen.getByText('CASE-A')).toBeInTheDocument();
    expect(mocks.core).toHaveBeenLastCalledWith(expect.objectContaining({ after_case_no: 'CASE-A', workbench_scope: 'in_progress' }), expect.any(Object));
  });
});
