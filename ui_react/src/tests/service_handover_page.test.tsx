import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ServiceHandoverPage } from '../pages/ServiceHandoverPage';
import { UnsavedChangesProvider } from '../components/UnsavedChanges';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { leaveSubstitutionClient } from '../api/scheduling/leave_substitution_client';
import { leaveSubstitutionFlowStore } from '../adapters/scheduling/leave_substitution_flow_store';
import { parseServiceHandoverLink, serviceHandoverHref } from '../adapters/scheduling/service_handover_navigation';
import { LeaveSubstitutionNetworkError } from '../api/scheduling/leave_substitution_errors';
import type { AssignmentPlan, OrderDetail } from '../api/orders/order_query_schemas';
import type { LeaveSubstitutionAssignment, LeaveSubstitutionPreview } from '../api/scheduling/leave_substitution_schemas';
import { LEAVE_CASE_NO, LEAVE_PREVIEW, LEAVE_RECEIPT } from './fixtures/scheduling/leave_substitution_contract_fixtures';

const dates = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-24'];
const original: LeaveSubstitutionAssignment[] = [{ assignment_id: 31, staff_id: 11,
  assigned_start_date: dates[0], assigned_end_date: dates[5],
  official_schedules: dates.map((work_date, index) => ({ schedule_id: 301 + index, work_date, is_double_pay: index === 3 })) }];
const observed: LeaveSubstitutionAssignment[] = [
  { assignment_id: 32, staff_id: 11, assigned_start_date: dates[0], assigned_end_date: dates[1],
    official_schedules: dates.slice(0, 2).map((work_date, index) => ({ schedule_id: 401 + index, work_date, is_double_pay: false })) },
  { assignment_id: 33, staff_id: 12, assigned_start_date: dates[2], assigned_end_date: dates[5],
    official_schedules: dates.slice(2).map((work_date, index) => ({ schedule_id: 403 + index, work_date, is_double_pay: index === 1 })) },
];
const preview: LeaveSubstitutionPreview = { ...LEAVE_PREVIEW, linked_request: null,
  assignments: observed.map((assignment, index) => ({ candidate_key: `a${index + 1}`, staff_id: assignment.staff_id,
    sequence: index + 1, assigned_start_date: assignment.assigned_start_date, assigned_end_date: assignment.assigned_end_date,
    official_service_dates: assignment.official_schedules.map(day => day.work_date), actual_hours: assignment.official_schedules.length * 8,
    lineage_source_assignment_ids: [31] })),
  outcomes: dates.slice(2).map((day, index) => ({ item_index: index, original_schedule_id: 303 + index,
    original_assignment_id: 31, original_staff_id: 11, original_work_date: day, resolution_type: 'substitute',
    leave_occupancy_date: day, resulting_service_date: day, resulting_staff_id: 12,
    resulting_assignment_key: 'a2', is_double_pay: index === 1 })),
  accounting: { staff: [
    { staff_id: 11, before: { salary_ntd: 16800, floor_fee_ntd: 1000, adjustment_ntd: 100, total_ntd: 17900 },
      after: { salary_ntd: 4800, floor_fee_ntd: 333, adjustment_ntd: 100, total_ntd: 5233 },
      paid_net_ntd: 8000, payable_after_ntd: 0, recovery_increase_ntd: 2767, recovery_after_ntd: 2767, payment_due_date: '2026-11-30' },
    { staff_id: 12, before: { salary_ntd: 0, floor_fee_ntd: 0, adjustment_ntd: 0, total_ntd: 0 },
      after: { salary_ntd: 12000, floor_fee_ntd: 667, adjustment_ntd: 0, total_ntd: 12667 },
      paid_net_ntd: 0, payable_after_ntd: 12667, recovery_increase_ntd: 0, recovery_after_ntd: 0, payment_due_date: '2026-11-30' },
  ], client: { before_ntd: 22000, after_ntd: 22000, difference_ntd: 0, settled_ntd: 5000 } },
};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-21T02:00:00Z'));
  leaveSubstitutionFlowStore.clearAll();
  window.location.hash = serviceHandoverHref(LEAVE_CASE_NO, 31);
  vi.spyOn(ordersQueryClient, 'getOrderDetail').mockResolvedValue({ case_no: LEAVE_CASE_NO, client_name: '範例客戶',
    service_days: 6, service_hours_per_day: 8 } as OrderDetail);
  vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue({ case_no: LEAVE_CASE_NO, service_started: true } as AssignmentPlan);
  vi.spyOn(staffDirectoryClient, 'queryPage').mockResolvedValue({ items: [
    { id: 11, name: '原月嫂', union_no: '001', phone: null, education: null },
    { id: 12, name: '接任月嫂', union_no: '002', phone: null, education: null },
  ], next_cursor: null });
  vi.spyOn(leaveSubstitutionClient, 'listAssignments').mockResolvedValueOnce(original).mockResolvedValue(observed);
  vi.spyOn(leaveSubstitutionClient, 'preview').mockResolvedValue(preview);
  vi.spyOn(leaveSubstitutionClient, 'apply').mockResolvedValue({ ...LEAVE_RECEIPT, linked_request: null });
});

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); leaveSubstitutionFlowStore.clearAll(); });

async function arrange() {
  render(<UnsavedChangesProvider><ServiceHandoverPage /></UnsavedChangesProvider>);
  await screen.findByText('範例客戶');
  fireEvent.change(screen.getByLabelText(/^交接日期/), { target: { value: '2026-10-21' } });
  fireEvent.change(screen.getByLabelText(/^接任月嫂/), { target: { value: '12' } });
  await waitFor(() => expect(leaveSubstitutionClient.preview).toHaveBeenCalledOnce());
}

describe('服務中換人專用頁', () => {
  it('攜帶原案件及服務段，保留雙薪，只需一次儲存並返回同案', async () => {
    await arrange();
    expect(screen.getAllByText('NT$ 2,767')).toHaveLength(2);
    expect(screen.getByText('將建立獨立追償，不抵扣接任月嫂薪資。')).toBeInTheDocument();
    const save = screen.getByRole('button', { name: '儲存換人安排' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await screen.findByRole('heading', { name: '換人安排已儲存' });
    expect(leaveSubstitutionClient.apply).toHaveBeenCalledOnce();
    const request = vi.mocked(leaveSubstitutionClient.apply).mock.calls[0][1];
    expect(request).toMatchObject({ original_assignment_id: 31, handover_date: '2026-10-21', reason: '' });
    expect(request.items.map(item => item.work_date)).toEqual(dates.slice(2));
    expect(request.items[1].is_double_pay).toBe(true);
    expect(screen.getByRole('link', { name: '返回本案服務安排 →' })).toHaveAttribute('href', `#order-workbench-v2?case=${LEAVE_CASE_NO}&work=service`);
  });

  it('結果未明時鎖住草稿，以相同 payload 及 key 確認結果', async () => {
    vi.mocked(leaveSubstitutionClient.apply).mockRejectedValueOnce(new LeaveSubstitutionNetworkError('連線中斷'))
      .mockResolvedValue({ ...LEAVE_RECEIPT, linked_request: null });
    await arrange();
    const save = screen.getByRole('button', { name: '儲存換人安排' });
    await waitFor(() => expect(save).toBeEnabled()); fireEvent.click(save);
    const retry = await screen.findByRole('button', { name: '再次確認變更結果' });
    expect(screen.getByLabelText(/^交接日期/)).toBeDisabled();
    fireEvent.click(retry);
    await screen.findByRole('heading', { name: '換人安排已儲存' });
    const calls = vi.mocked(leaveSubstitutionClient.apply).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[1][1]).toEqual(calls[0][1]);
    expect(calls[1][2].idempotencyKey).toBe(calls[0][2].idempotencyKey);
  });

  it('帳務無法承接時顯示具體原因，禁止儲存', async () => {
    vi.mocked(leaveSubstitutionClient.preview).mockResolvedValue({ ...preview, accounting: null,
      apply_readiness: { status: 'blocked', blockers: ['handover_paid_adjustment_review_required'] } });
    await arrange();
    expect(await screen.findByText('原月嫂有已付款的獨立調整款，請先至本案帳務核對，再辦理換人。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存換人安排' })).toBeDisabled();
    expect(leaveSubstitutionClient.apply).not.toHaveBeenCalled();
  });

  it('正式回讀日期不符時保留收據，不再提交換人命令', async () => {
    vi.mocked(leaveSubstitutionClient.listAssignments).mockReset().mockResolvedValueOnce(original)
      .mockResolvedValueOnce([{ ...observed[1], official_schedules: observed[1].official_schedules.slice(1) }])
      .mockResolvedValue(observed);
    await arrange();
    const save = screen.getByRole('button', { name: '儲存換人安排' });
    await waitFor(() => expect(save).toBeEnabled()); fireEvent.click(save);
    fireEvent.click(await screen.findByRole('button', { name: '重新讀取已儲存安排' }));
    await screen.findByRole('heading', { name: '換人安排已儲存' });
    expect(leaveSubstitutionClient.apply).toHaveBeenCalledOnce();
  });

  it('導向會保留特殊案件字元，拒絕錯誤服務段', () => {
    expect(parseServiceHandoverLink(serviceHandoverHref('CASE & A+1', 31))).toEqual({ caseNo: 'CASE & A+1', assignmentId: 31 });
    expect(parseServiceHandoverLink('#scheduling?tab=handover&case_no=A&assignment_id=-1')).toBeNull();
    expect(parseServiceHandoverLink('#scheduling?tab=handover&case_no=A&case_no=B')).toBeNull();
  });

  it('原服務段已換代時仍可在同案選取最新服務段', async () => {
    window.location.hash = serviceHandoverHref(LEAVE_CASE_NO, 999);
    render(<UnsavedChangesProvider><ServiceHandoverPage /></UnsavedChangesProvider>);
    await screen.findByText('原服務指派已變更，請重新選擇這次要交接的服務段。');
    fireEvent.change(screen.getByLabelText('原月嫂服務段'), { target: { value: '31' } });
    fireEvent.change(screen.getByLabelText(/^交接日期/), { target: { value: '2026-10-21' } });
    fireEvent.change(screen.getByLabelText(/^接任月嫂/), { target: { value: '12' } });
    await waitFor(() => expect(screen.getByRole('button', { name: '儲存換人安排' })).toBeEnabled());
    expect(leaveSubstitutionClient.preview).toHaveBeenCalledWith(LEAVE_CASE_NO,
      expect.objectContaining({ original_assignment_id: 31 }), expect.anything());
  });
});
