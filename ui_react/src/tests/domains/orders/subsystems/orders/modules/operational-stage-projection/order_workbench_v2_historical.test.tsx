import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CORE_STAGE_CODES,
  SUBSTATUS_BY_STAGE_STATUS,
  substatusCodesForStage,
  type CoreStageProjection,
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

function stages(caseNo: string): CoreStageProjection[] {
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
      const result = page([historical('CASE-FUTURE', '歷史訂單－未服務')]);
      return { ...result, stage_counts: { ...counts(), confirmed_service_dates: 1 },
        substatus_counts: params.stage ? Object.fromEntries(substatusCodesForStage(params.stage).map((code) => [code, 1])) : {} };
    });
  });

  it('歷史未服務留在進行中，正式 owner stage 可篩選；看板不提供完成與取消分類', async () => {
    render(<OrderWorkbenchV2Page />);
    expect(await screen.findByText('CASE-FUTURE')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '歷史訂單' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /9 待服務 1/ }));
    await waitFor(() => expect(mocks.core).toHaveBeenLastCalledWith(
      expect.objectContaining({ workbench_scope: 'in_progress', stage: 'confirmed_service_dates' }), expect.any(Object),
    ));
    expect(await screen.findByText('CASE-FUTURE')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '完成訂單' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消訂單' })).not.toBeInTheDocument();
    expect(screen.getByRole('region', { name: '13 個核心訂單階段' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '全部進行中' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '全部進行中' })).toHaveAttribute('aria-pressed', 'true'));
  });

  it('第 9 步顯示待排班的歷史配對與日期確認狀態，並優先顯示有效推薦方案', async () => {
    const pending = historical('CASE-UNSCHEDULED', '歷史訂單－未服務');
    const confirmed = historical('CASE-CONFIRMED', '歷史訂單－未服務');
    pending.core_stages = pending.core_stages.map((stage) => stage.code === 'confirmed_service_dates'
      ? {
          ...stage,
          status: 'unavailable',
          substatus_code: 'date_confirmation_unavailable',
          source: { ...stage.source, identity: null, version: null },
          availability_reason: 'confirmed_service_date_lineage_missing',
        }
      : stage);
    mocks.core.mockResolvedValue(page([confirmed, pending]));
    const summary = {
      client_name: '測試客戶',
      order_status: '歷史訂單－未服務',
      start_date: '2026-12-01',
      end_date: '2026-12-20',
      actual_start_date: null,
      actual_end_date: null,
      identity_status: null,
      service_days: 20,
      total_employer_self_pay_payable: null,
      staff_name: '歷史配對月嫂',
      staff_display_label: 'E001 歷史配對月嫂',
      scheduled_staff_display_label: null,
    };
    mocks.summaries.mockResolvedValue({
      items: [
        { ...summary, case_no: pending.case_no, recommended_staff_display_label: null },
        { ...summary, case_no: confirmed.case_no, recommended_staff_display_label: 'E002 目前方案月嫂' },
      ],
      next_cursor: null,
      etag: 'd'.repeat(64),
    });

    render(<OrderWorkbenchV2Page />);
    const pendingRow = within(await screen.findByRole('row', { name: /CASE-UNSCHEDULED/ }));
    const confirmedRow = within(await screen.findByRole('row', { name: /CASE-CONFIRMED/ }));
    await pendingRow.findByText('測試客戶');
    expect.soft(pendingRow.queryByText('E001 歷史配對月嫂')).toBeInTheDocument();
    expect.soft(pendingRow.queryByText('日期未確認')).toBeInTheDocument();
    expect(confirmedRow.getByText('E002 目前方案月嫂')).toBeInTheDocument();
    expect(confirmedRow.getByText('日期已確認')).toBeInTheDocument();
    expect(confirmedRow.queryByText('E001 歷史配對月嫂')).not.toBeInTheDocument();
  });

  it('拒絕伺服器把歷史已完成案件回傳到進行中清單，避免錯誤分類冒充成功', async () => {
    mocks.core.mockResolvedValue(page([historical('CASE-WRONG', '歷史訂單－服務完成')]));
    render(<OrderWorkbenchV2Page />);
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
