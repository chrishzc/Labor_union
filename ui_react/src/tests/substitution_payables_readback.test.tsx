/**
 * File: substitution_payables_readback.test.tsx
 * Description: 驗證代班完成後只讀取本案 Staff Payables，且失敗重試不會重送代班變更。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffLeaveInboxClient } from '../api/scheduling/staff_leave_inbox_client';
import { staffAssignmentOptionsClient } from '../api/scheduling/staff_assignment_options_client';
import { staffPayablesQueryClient } from '../api/staff_payables/staff_payables_query_client';
import type { StaffPayablesQuery } from '../api/staff_payables/staff_payables_query_schemas';
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

function payable(staffId: number, caseNo = LEAVE_CASE_NO): StaffPayablesQuery {
  return {
    staff_id: staffId,
    staff_payables_version: 7,
    obligations: [{
      obligation_identity: `payable:${staffId}:${caseNo}`,
      case_no: caseNo,
      amount_due_ntd: staffId === 11 ? 3200 : 4800,
      due_date: '2026-08-31',
      net_paid_ntd: 0,
      balance_ntd: staffId === 11 ? 3200 : 4800,
      payout_status: 'payable',
    }],
    events: [],
  };
}

function seedObservedReceipt(): void {
  leaveSubstitutionFlowStore.setQueryReady(LEAVE_CASE_NO, LEAVE_ASSIGNMENTS);
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

describe('Scheduling substitution Staff Payables readback', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    leaveSubstitutionFlowStore.clearAll();
    vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({
      items: [
        { id: 11, name: '月嫂甲', phone: null },
        { id: 12, name: '月嫂乙', phone: null },
      ],
      next_cursor: null,
    });
    vi.spyOn(staffLeaveInboxClient, 'list').mockResolvedValue([]);
    vi.spyOn(ordersQueryClient, 'getOrderSummaries').mockResolvedValue({
      items: [],
      next_cursor: null,
      etag: 'a'.repeat(64),
    });
    vi.spyOn(staffAssignmentOptionsClient, 'getStaffAssignmentOptions').mockResolvedValue([]);
  });

  it('回讀原人員與代班人員的本案未結義務，不顯示其他案件或內部版本', async () => {
    seedObservedReceipt();
    const query = vi.spyOn(staffPayablesQueryClient, 'query').mockImplementation(async (staffId) => ({
      ...payable(staffId),
      obligations: [
        ...payable(staffId).obligations,
        ...payable(staffId, 'CASE-OTHER').obligations,
      ],
    }));

    renderLeaveWorkspace();

    const readback = await screen.findByRole('region', { name: '代班薪資與應付款回讀' });
    await waitFor(() => expect(query).toHaveBeenCalledTimes(2));
    expect(query).toHaveBeenCalledWith(11);
    expect(query).toHaveBeenCalledWith(12);
    await waitFor(() => expect(readback).toHaveTextContent('月嫂甲'));
    expect(readback).toHaveTextContent('月嫂乙');
    expect(readback).toHaveTextContent('NT$ 3,200');
    expect(readback).toHaveTextContent('NT$ 4,800');
    expect(readback).toHaveTextContent('待付款');
    expect(readback).not.toHaveTextContent('CASE-OTHER');
    expect(readback).not.toHaveTextContent('版本');
    expect(readback).toHaveTextContent('不會發動付款、匯出或再次套用代班');
  });

  it('回讀失敗後只重查 Staff Payables，不重送代班或請假待辦 mutation', async () => {
    seedObservedReceipt();
    const query = vi.spyOn(staffPayablesQueryClient, 'query')
      .mockRejectedValueOnce(new Error('temporary'))
      .mockRejectedValueOnce(new Error('temporary'))
      .mockImplementation(async (staffId) => payable(staffId));
    const review = vi.spyOn(staffLeaveInboxClient, 'review');

    renderLeaveWorkspace();

    expect(await screen.findByRole('alert')).toHaveTextContent('代班變更已完成');
    fireEvent.click(screen.getByRole('button', { name: '重新查詢薪資與應付款' }));

    await waitFor(() => expect(query).toHaveBeenCalledTimes(4));
    expect(await screen.findByText(/應付 NT\$ 3,200/)).toBeInTheDocument();
    expect(review).not.toHaveBeenCalled();
    expect(screen.getByText('🎉 代班變更已完成')).toBeInTheDocument();
  });
});
