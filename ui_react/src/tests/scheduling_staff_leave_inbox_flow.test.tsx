/**
 * File: scheduling_staff_leave_inbox_flow.test.tsx
 * Description: 驗證請假待辦受理、取消、完成回讀與一般畫面的業務化狀態文案。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import {
  staffLeaveInboxClient,
  type LeaveInboxItem,
} from '../api/scheduling/staff_leave_inbox_client';
import { ApiDecodeError } from '../api/shared/typed_errors';
import { transport } from '../api/shared/transport';
import { leaveSubstitutionClient } from '../api/scheduling/leave_substitution_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffAssignmentOptionsClient } from '../api/scheduling/staff_assignment_options_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { leaveSubstitutionFlowStore } from '../adapters/scheduling/leave_substitution_flow_store';
import { SchedulingPage } from '../pages/SchedulingPage';
import {
  LEAVE_APPLY_REQUEST,
  LEAVE_ASSIGNMENTS,
  LEAVE_CASE_NO,
  LEAVE_OBSERVED_ASSIGNMENTS,
  LEAVE_PREVIEW,
  LEAVE_PREVIEW_REQUEST,
  LEAVE_RECEIPT,
} from './fixtures/scheduling/leave_substitution_contract_fixtures';

vi.mock('../api/orders/load_all_core_stage_timelines', () => ({
  loadAllCoreStageTimelines: vi.fn().mockResolvedValue({ items: [] }),
}));

const PENDING_ITEM: LeaveInboxItem = {
  id: 77,
  staff_id: 11,
  staff_name: '去敏月嫂甲',
  leave_start_date: '2026-08-03',
  leave_end_date: '2026-08-03',
  request_reason: '個人事務',
  request_status: 'pending',
  aggregate_version: 4,
};

const RESOLVED_ITEM: LeaveInboxItem = {
  ...PENDING_ITEM,
  request_status: 'resolved',
  aggregate_version: 5,
};

function serviceCase(caseNo: string, orderStatus = '服務中') {
  return {
    case_no: caseNo, client_name: '去敏客戶甲', order_status: orderStatus,
    staff_name: '去敏月嫂甲', identity_status: 'verified',
    start_date: '2026-08-01', end_date: '2026-08-31',
    actual_start_date: '2026-08-01', actual_end_date: null,
    service_days: 20, total_employer_self_pay_payable: 10000,
  };
}

function seedQueryReady(): void {
  leaveSubstitutionFlowStore.setQueryReady(LEAVE_CASE_NO, LEAVE_ASSIGNMENTS);
}

function seedObservedReceipt(): void {
  seedQueryReady();
  leaveSubstitutionFlowStore.setDraft(LEAVE_CASE_NO, LEAVE_PREVIEW_REQUEST);
  leaveSubstitutionFlowStore.setPreviewReady(LEAVE_CASE_NO, LEAVE_PREVIEW);
  leaveSubstitutionFlowStore.setApplyPending(LEAVE_CASE_NO, LEAVE_APPLY_REQUEST);
  leaveSubstitutionFlowStore.setReceiptReceived(LEAVE_CASE_NO, LEAVE_RECEIPT);
  leaveSubstitutionFlowStore.setObserved(LEAVE_CASE_NO, LEAVE_OBSERVED_ASSIGNMENTS);
}

function renderLeaveWorkspace(): void {
  window.location.hash = `#scheduling?tab=leave_sub&case_no=${LEAVE_CASE_NO}`;
  render(<SchedulingPage />);
}

describe('Scheduling staff leave inbox flow', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    sessionClient.clearSession();
    leaveSubstitutionFlowStore.clearAll();
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({
      items: [serviceCase(LEAVE_CASE_NO)],
      next_cursor: null, etag: 'a'.repeat(64),
    });
    vi.spyOn(leaveSubstitutionClient, 'listAssignments').mockResolvedValue([...LEAVE_ASSIGNMENTS]);
    vi.spyOn(staffAssignmentOptionsClient, 'getStaffAssignmentOptions').mockResolvedValue([]);
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '去敏月嫂甲', phone: null, education: null },
        { id: 12, name: '去敏月嫂乙', phone: null, education: null },
      ],
      next_cursor: null,
    });
    vi.spyOn(staffLeaveInboxClient, 'list').mockResolvedValue([]);
  });

  it('下拉只列出服務中且有正式服務日的案件，選取後仍重新查詢正式指派', async () => {
    vi.mocked(ordersQueryClient.getOrderSummaries).mockResolvedValue({
      items: [
        serviceCase(LEAVE_CASE_NO), serviceCase('CASE-READY'), serviceCase('CASE-NO-ASSIGNMENT'), serviceCase('CASE-NO-DAY'),
        serviceCase('CASE-PLANNED', '已排定'), serviceCase('CASE-COMPLETED', '已結束'),
      ],
      next_cursor: null, etag: 'a'.repeat(64),
    });
    vi.mocked(leaveSubstitutionClient.listAssignments).mockImplementation(async (caseNo) => (
      caseNo === 'CASE-NO-ASSIGNMENT' ? [] : caseNo === 'CASE-NO-DAY'
        ? LEAVE_ASSIGNMENTS.map((item) => ({ ...item, official_schedules: [] }))
        : [...LEAVE_ASSIGNMENTS]
    ));
    renderLeaveWorkspace();
    const select = screen.getByRole('combobox', { name: '請假代班訂單編號' });
    expect(select).toBeDisabled();
    expect(screen.queryByRole('textbox', { name: '請假代班訂單編號' })).not.toBeInTheDocument();
    await waitFor(() => expect(select).toBeEnabled());
    expect([...((select as HTMLSelectElement).options)].map((option) => option.value)).toEqual(['', LEAVE_CASE_NO, 'CASE-READY']);
    expect(leaveSubstitutionClient.listAssignments).not.toHaveBeenCalledWith('CASE-PLANNED', expect.anything());
    expect(leaveSubstitutionClient.listAssignments).not.toHaveBeenCalledWith('CASE-COMPLETED', expect.anything());
    fireEvent.change(select, { target: { value: 'CASE-READY' } });
    await waitFor(() => expect(select).toHaveValue('CASE-READY'));
    fireEvent.click(screen.getByRole('button', { name: '🔍 重新整理指派' }));
    await screen.findByRole('combobox', { name: '正式服務日' });
    expect(leaveSubstitutionClient.listAssignments).toHaveBeenLastCalledWith('CASE-READY', undefined);
  });

  it('取得跨頁的服務中案件，不受目前日曆載入人員範圍限制', async () => {
    vi.mocked(staffDirectoryClient.queryPage).mockResolvedValue({ items: [], next_cursor: null });
    vi.mocked(ordersQueryClient.getOrderSummaries).mockImplementation(async (params) => ({
      items: [serviceCase(params?.after_case_no ? 'CASE-Z' : 'CASE-A')],
      next_cursor: params?.after_case_no ? null : 'CASE-A', etag: 'a'.repeat(64),
    }));
    renderLeaveWorkspace();
    const select = screen.getByRole('combobox', { name: '請假代班訂單編號' });
    await waitFor(() => expect(select).toBeEnabled());
    expect([...((select as HTMLSelectElement).options)].map((option) => option.value)).toEqual(['', 'CASE-A', 'CASE-Z']);
    expect(ordersQueryClient.getOrderSummaries).toHaveBeenCalledWith(
      { page_size: 200, lifecycle_scope: 'unfinished', after_case_no: 'CASE-A' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it('網址中的未合格案件不能預選或啟用指派查詢', async () => {
    window.location.hash = '#scheduling?tab=leave_sub&case_no=CASE-NOT-SERVING';
    render(<SchedulingPage />);
    const select = screen.getByRole('combobox', { name: '請假代班訂單編號' });
    await waitFor(() => expect(select).toBeEnabled());
    expect(select).toHaveValue('');
    expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).toBeDisabled();
    expect(screen.queryByText(/案件 #CASE-NOT-SERVING 正式排班資料/)).not.toBeInTheDocument();
  });

  it('正式排班查詢失敗時不提供未驗證選項，重新載入可恢復', async () => {
    vi.mocked(leaveSubstitutionClient.listAssignments).mockRejectedValue(new Error('query unavailable'));
    renderLeaveWorkspace();
    const select = screen.getByRole('combobox', { name: '請假代班訂單編號' });
    expect(await screen.findByRole('alert')).toHaveTextContent('服務中案件載入失敗');
    expect(select).toBeDisabled();
    expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).toBeDisabled();
    vi.mocked(leaveSubstitutionClient.listAssignments).mockResolvedValue([...LEAVE_ASSIGNMENTS]);
    fireEvent.click(screen.getByRole('button', { name: '重新載入案件' }));
    await waitFor(() => expect(select).toBeEnabled());
    expect(select).toHaveValue(LEAVE_CASE_NO);
  });

  it('沒有正式排班時顯示空清單提示並停用指派查詢', async () => {
    vi.mocked(leaveSubstitutionClient.listAssignments).mockResolvedValue([]);
    renderLeaveWorkspace();
    expect(await screen.findByText('目前沒有服務中且已有正式排班的案件。')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: '請假代班訂單編號' })).toHaveValue('');
    expect(document.querySelector('[data-control-id="scheduling.leave.query"]')).toBeDisabled();
  });

  it('保留受理後的最新狀態供代班檢查使用，且不顯示內部版本或宣稱已通知', async () => {
    seedQueryReady();
    let accepted = false;
    vi.spyOn(staffLeaveInboxClient, 'list').mockImplementation(async (status) => (
      status === 'pending' && !accepted ? [PENDING_ITEM] : []
    ));
    vi.spyOn(staffLeaveInboxClient, 'review').mockImplementation(async (_item, action) => {
      expect(action).toBe('accept');
      accepted = true;
      return { request_id: 77, status: 'accepted_for_processing', version: 5, actor: 'admin' };
    });

    renderLeaveWorkspace();
    fireEvent.click(await screen.findByRole('button', { name: '📋 受理並調度代班' }));

    expect(await screen.findByText(/已受理.*請假待辦/)).toHaveTextContent('尚未完成正式排班，也尚未建立 LINE 通知工作');
    expect(screen.getByText(/目前已連動 LINE 請假待辦/)).not.toHaveTextContent('版本');
    expect(document.body.textContent).not.toContain('請假待辦 #77');
    expect(screen.queryByText(/已通知月嫂/)).not.toBeInTheDocument();
  });

  it('人工指定補班日期會原樣送入既有 Preview', async () => {
    seedQueryReady();
    vi.spyOn(staffLeaveInboxClient, 'list').mockResolvedValue([]);
    const preview = vi.spyOn(leaveSubstitutionClient, 'preview').mockResolvedValue({
      ...LEAVE_PREVIEW,
      outcomes: LEAVE_PREVIEW.outcomes.map((outcome) => ({
        ...outcome,
        resulting_service_date: '2026-08-11',
      })),
    });

    renderLeaveWorkspace();
    fireEvent.change(await screen.findByRole('combobox', { name: '請假代班處理方式' }), {
      target: { value: 'defer_following_assignments' },
    });
    fireEvent.change(screen.getByLabelText('指定補班日期'), {
      target: { value: '2026-08-11' },
    });
    fireEvent.click(await screen.findByRole('button', { name: '🔍 檢查代班影響' }));

    await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
    expect(preview.mock.calls[0]?.[1].items[0]).toMatchObject({
      original_schedule_id: 301,
      work_date: '2026-08-03',
      resolution_type: 'defer_following_assignments',
      replacement_work_date: '2026-08-11',
      substitute_staff_id: null,
      is_double_pay: false,
    });
    expect(await screen.findByText('2026-08-11')).toBeInTheDocument();
  });

  it('提供管理員取消 pending 待辦的原因與 typed receipt', async () => {
    seedQueryReady();
    let cancelled = false;
    vi.spyOn(staffLeaveInboxClient, 'list').mockImplementation(async (status) => (
      status === 'pending' && !cancelled ? [PENDING_ITEM] : []
    ));
    const review = vi.spyOn(staffLeaveInboxClient, 'review').mockImplementation(async (_item, action, reason) => {
      expect(action).toBe('cancel');
      expect(reason).toBe('電話確認撤回請假');
      cancelled = true;
      return { request_id: 77, status: 'cancelled', version: 5, actor: 'admin' };
    });

    renderLeaveWorkspace();
    fireEvent.change(await screen.findByPlaceholderText('退回／取消原因說明…'), { target: { value: '電話確認撤回請假' } });
    fireEvent.click(screen.getByRole('button', { name: '取消待辦' }));

    await waitFor(() => expect(review).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/已取消.*請假待辦/)).toHaveTextContent('待辦狀態已更新');
    expect(screen.queryByText(/已通知月嫂/)).not.toBeInTheDocument();
  });

  it('terminal 待辦維持唯讀並顯示明確業務原因', async () => {
    seedQueryReady();
    vi.spyOn(staffLeaveInboxClient, 'list').mockResolvedValue([RESOLVED_ITEM]);

    renderLeaveWorkspace();

    expect(await screen.findByText('此待辦已結束，僅供回讀。')).toBeInTheDocument();
    expect(screen.getAllByText('已完成代班').length).toBeGreaterThan(0);
    expect(screen.queryByText('resolved')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '📋 受理並調度代班' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '取消待辦' })).not.toBeInTheDocument();
  });

  it('代班完成後重查已結束待辦，以業務文案顯示一致結果與通知僅為排隊中', async () => {
    seedObservedReceipt();
    const list = vi.spyOn(staffLeaveInboxClient, 'list').mockImplementation(async (status) => (
      status === 'resolved' ? [RESOLVED_ITEM] : []
    ));

    renderLeaveWorkspace();

    expect(await screen.findByText(/已確認關聯的請假待辦完成/)).toHaveTextContent('與最新調度結果一致');
    expect(screen.getByText(/LINE 通知/)).toHaveTextContent('已排入發送，尚未確認送達');
    expect(screen.queryByText(LEAVE_RECEIPT.batch_key)).not.toBeInTheDocument();
    expect(screen.queryByText(/Scheduling v|expected v|resolved v|canonical receipt/)).not.toBeInTheDocument();
    expect(list).toHaveBeenCalledWith('resolved', 100);
  });

  it('拒絕 identity、狀態或版本不符合 request 的 review receipt', async () => {
    sessionClient.setSession('leave-inbox-token', {
      id: 1,
      username: 'admin',
      display_name: 'Admin',
      role: 'admin',
    });
    vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: 'ok',
      data: { request_id: 78, status: 'accepted_for_processing', version: 4, actor: 'admin' },
      error: null,
    });

    await expect(staffLeaveInboxClient.review(PENDING_ITEM, 'accept', '受理')).rejects.toBeInstanceOf(ApiDecodeError);
  });
});
