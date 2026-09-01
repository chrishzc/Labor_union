/**
 * File: substitution_payables_readback.test.tsx
 * Description: 驗證代班完成後只讀取本案 Staff Payables，且失敗重試不會重送代班變更。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffLeaveInboxClient } from '../api/scheduling/staff_leave_inbox_client';
import { staffAssignmentOptionsClient } from '../api/scheduling/staff_assignment_options_client';
import { substitutionPayablesLineageClient, type SubstitutionPayablesLineage } from '../api/scheduling/substitution_payables_lineage_client';
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

function lineage(): SubstitutionPayablesLineage {
  return {
    case_no: LEAVE_CASE_NO,
    batch_key: LEAVE_RECEIPT.batch_key,
    scheduling_receipt_id: 901,
    scheduling_version: LEAVE_RECEIPT.scheduling_version,
    scheduling_generation: LEAVE_RECEIPT.scheduling_generation,
    expected_payroll_version: LEAVE_RECEIPT.payroll_version - 1,
    resulting_payroll_version: LEAVE_RECEIPT.payroll_version,
    items: [
      {
        item_index: 0,
        outcome_event_id: 701,
        original_assignment_id: 101,
        original_schedule_id: 1001,
        original_staff_id: 11,
        original_work_date: '2026-08-10',
        resolution_type: 'substitute',
        resulting_assignment_id: 201,
        resulting_staff_id: 12,
        resulting_service_date: '2026-08-10',
        payroll_event_id: 801,
        payroll_event_expected_version: LEAVE_RECEIPT.payroll_version - 1,
        payroll_event_resulting_version: LEAVE_RECEIPT.payroll_version,
        payroll_fingerprint: 'a'.repeat(64),
        payables_evidence: {
          obligation_identity: 'obligation:substitute:201',
          assignment_id: 201,
          staff_id: 12,
          amount_due_ntd: 4800,
          due_date: '2026-08-31',
          obligation_status: 'open',
          obligation_payroll_version: LEAVE_RECEIPT.payroll_version,
          obligation_event_id: 801,
          projection_status: 'payable',
          projection_amount_ntd: 4800,
          projection_net_paid_ntd: 0,
          projection_balance_ntd: 4800,
          projection_version: 7,
          projection_event_id: 901,
          blockers: [],
        },
        lineage_subject: 'substitution:batch:outcome:701',
        blockers: [],
      },
      {
        item_index: 1,
        outcome_event_id: 702,
        original_assignment_id: 101,
        original_schedule_id: 1002,
        original_staff_id: 11,
        original_work_date: '2026-08-11',
        resolution_type: 'defer_following_assignments',
        resulting_assignment_id: 202,
        resulting_staff_id: 11,
        resulting_service_date: '2026-08-11',
        payroll_event_id: 802,
        payroll_event_expected_version: LEAVE_RECEIPT.payroll_version - 1,
        payroll_event_resulting_version: LEAVE_RECEIPT.payroll_version,
        payroll_fingerprint: 'b'.repeat(64),
        payables_evidence: {
          obligation_identity: 'obligation:original:202',
          assignment_id: 202,
          staff_id: 11,
          amount_due_ntd: 3200,
          due_date: '2026-08-31',
          obligation_status: 'open',
          obligation_payroll_version: LEAVE_RECEIPT.payroll_version,
          obligation_event_id: 802,
          projection_status: 'payable',
          projection_amount_ntd: 3200,
          projection_net_paid_ntd: 0,
          projection_balance_ntd: 3200,
          projection_version: 7,
          projection_event_id: 902,
          blockers: [],
        },
        lineage_subject: 'substitution:batch:outcome:702',
        blockers: [],
      },
    ],
    authoritative_complete: true,
    blockers: [],
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
    vi.spyOn(substitutionPayablesLineageClient, 'query').mockResolvedValue(lineage());
  });

  it('回讀原人員與代班人員的本案未結義務，不顯示其他案件或內部版本', async () => {
    seedObservedReceipt();
    const query = vi.spyOn(substitutionPayablesLineageClient, 'query').mockResolvedValue(lineage());

    renderLeaveWorkspace();

    const readback = await screen.findByRole('region', { name: '代班薪資與應付款回讀' });
    await waitFor(() => expect(query).toHaveBeenCalledWith(LEAVE_CASE_NO, LEAVE_RECEIPT.batch_key));
    await waitFor(() => expect(readback).toHaveTextContent('月嫂甲'));
    expect(readback).toHaveTextContent('月嫂乙');
    expect(readback).toHaveTextContent('NT$ 3,200');
    expect(readback).toHaveTextContent('NT$ 4,800');
    expect(readback).toHaveTextContent('待付款');
    expect(readback).toHaveTextContent('版本化血緣');
    expect(readback).toHaveTextContent(`Scheduling v${LEAVE_RECEIPT.scheduling_version} → Payroll v${LEAVE_RECEIPT.payroll_version}`);
    expect(readback).toHaveTextContent('不會發動付款、匯出或再次套用代班');
  });

  it('回讀失敗後只重查 Staff Payables，不重送代班或請假待辦 mutation', async () => {
    seedObservedReceipt();
    const query = vi.spyOn(substitutionPayablesLineageClient, 'query')
      .mockRejectedValueOnce(new Error('temporary'))
      .mockResolvedValue(lineage());
    const review = vi.spyOn(staffLeaveInboxClient, 'review');

    renderLeaveWorkspace();

    expect(await screen.findByRole('alert')).toHaveTextContent('代班變更已完成');
    fireEvent.click(screen.getByRole('button', { name: '重新查詢薪資與應付款' }));

    await waitFor(() => expect(query).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/應付 NT\$ 3,200/)).toBeInTheDocument();
    expect(review).not.toHaveBeenCalled();
    expect(screen.getByText('🎉 代班變更已完成')).toBeInTheDocument();
  });
});
