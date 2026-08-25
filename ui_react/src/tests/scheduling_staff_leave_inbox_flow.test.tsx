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
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '去敏月嫂甲', phone: null },
        { id: 12, name: '去敏月嫂乙', phone: null },
      ],
      next_cursor: null,
    });
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
    expect(screen.getByText(/LINE 通知工作/)).toHaveTextContent('已排入可靠發送佇列，尚未證明送達');
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
