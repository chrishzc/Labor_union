import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderAssignmentPlanPanel } from '../../../../../../../components/OrderAssignmentPlanPanel';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const mocks = vi.hoisted(() => ({
  getAssignmentPlan: vi.fn(),
  queryPlan: vi.fn(),
  queryStaff: vi.fn(),
}));

vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  ordersQueryClient: {
    getAssignmentPlan: mocks.getAssignmentPlan,
  },
}));

vi.mock('../../../../../../../api/staff_directory/staff_directory_client', () => ({
  createStaffDirectoryClient: () => ({ queryPage: mocks.queryStaff }),
}));

vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({
  waitingDepositLockClient: { queryPlan: mocks.queryPlan },
}));

vi.mock('../../../../../../../components/MatchingScheduleAndAssignmentActions', () => ({
  MatchingScheduleAndAssignmentActions: ({ planId, officialServiceDates }: { planId: number; officialServiceDates: string[] }) => (
    <section aria-label="mock 日期表確認與排班">matching plan {planId}<p>{officialServiceDates.join('、')}</p></section>
  ),
}));

vi.mock('../../../../../../../components/ServiceBeforeReplacementActions', () => ({
  ServiceBeforeReplacementActions: ({
    caseNo,
    onCommitted,
    onSubstitutionReferral,
  }: {
    caseNo: string;
    onCommitted?: () => Promise<void> | void;
    onSubstitutionReferral?: () => Promise<void> | void;
  }) => (
    <section aria-label="mock 服務前換人 workflow">
      <span>replacement case {caseNo}</span>
      <button type="button" onClick={() => void onCommitted?.()}>模擬換人完成</button>
      <button type="button" onClick={() => void onSubstitutionReferral?.()}>模擬請假代班</button>
    </section>
  ),
}));

function assignmentPlan() {
  return {
    case_no: 'CASE-ASSIGNMENT-PLAN',
    order_version: 21,
    scheduling_version: 12,
    scheduling_generation: 3,
    client_finance_version: 8,
    payroll_version: 5,
    contracted_service_days: 4,
    service_hours_per_day: 8,
    service_started: false,
    assignments: [
      {
        assignment_id: 301,
        candidate_key: null,
        staff_id: 8891,
        sequence: 1,
        assigned_start_date: '2026-09-10',
        assigned_end_date: '2026-09-11',
        official_service_dates: ['2026-09-10', '2026-09-11'],
        actual_hours: null,
        lineage_source_assignment_ids: [],
      },
      {
        assignment_id: 302,
        candidate_key: null,
        staff_id: 8892,
        sequence: 2,
        assigned_start_date: '2026-09-12',
        assigned_end_date: '2026-09-13',
        official_service_dates: ['2026-09-12', '2026-09-13'],
        actual_hours: null,
        lineage_source_assignment_ids: [301],
      },
    ],
  };
}

describe('正式指派自動回讀與排班明細', () => {
  beforeEach(() => {
    mocks.getAssignmentPlan.mockReset();
    mocks.queryPlan.mockReset();
    mocks.queryStaff.mockReset();
    mocks.queryStaff.mockImplementation(async ({ staffId }: { staffId: number }) => ({
      items: [{ id: staffId, union_no: staffId === 8891 ? 'A010' : 'A002', name: '同名月嫂', phone: null, education: null }], next_cursor: null,
    }));
    mocks.queryPlan.mockResolvedValue({
      planId: 51, status: 'accepted', activeLockId: 61, planVersion: 4,
      segments: [{ segmentId: 71, sequence: 1, staffId: 8891, assignedStartDate: '2026-09-10', assignedEndDate: '2026-09-13' }],
    });
    window.location.hash = '';
  });

  it('無有效媒合方案時仍顯示正式指派回讀，而不是資源錯誤', async () => {
    mocks.getAssignmentPlan.mockResolvedValue(assignmentPlan());
    mocks.queryPlan.mockRejectedValue(new ApiHttpError(404, 'resource_not_found', '找不到要求的資源'));
    render(<OrderAssignmentPlanPanel caseNo="CASE-ASSIGNMENT-PLAN" />);
    fireEvent.click(await screen.findByText('查看目前月嫂與排班明細'));
    expect(await screen.findByText('2 段')).toBeInTheDocument();
    expect(screen.getByText(/尚無有效媒合方案/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByLabelText('mock 日期表確認與排班')).toHaveTextContent('matching plan 0');
    expect(screen.getByLabelText('mock 日期表確認與排班')).toHaveTextContent('2026-09-10、2026-09-11、2026-09-12、2026-09-13');
  });

  it('只使用既有 assignment-plan owner facts 顯示正式指派段與官方服務日', async () => {
    mocks.getAssignmentPlan.mockResolvedValue(assignmentPlan());

    render(<OrderAssignmentPlanPanel caseNo="CASE-ASSIGNMENT-PLAN" />);
    fireEvent.click(await screen.findByText('查看目前月嫂與排班明細'));

    await waitFor(() => expect(mocks.getAssignmentPlan).toHaveBeenCalledWith('CASE-ASSIGNMENT-PLAN'));
    expect(await screen.findByText('2 段')).toBeInTheDocument();
    expect(screen.queryByText('#12')).not.toBeInTheDocument();
    expect(screen.queryByText('#3')).not.toBeInTheDocument();
    expect(screen.getByText('4 天 × 8 小時')).toBeInTheDocument();

    const first = screen.getByLabelText('第 1 段正式指派');
    expect(await within(first).findByText('A010 同名月嫂')).toBeInTheDocument();
    expect(within(first).getByText('2026-09-10 ~ 2026-09-11')).toBeInTheDocument();
    expect(within(first).getByText('2 天')).toBeInTheDocument();

    const second = screen.getByLabelText('第 2 段正式指派');
    expect(await within(second).findByText('A002 同名月嫂')).toBeInTheDocument();
    expect(within(second).getByText('2026-09-12 ~ 2026-09-13')).toBeInTheDocument();
    expect(within(second).getByText('2 天')).toBeInTheDocument();
    expect(screen.queryByText(/待開工|服務進行中/)).not.toBeInTheDocument();
    expect(screen.getByLabelText('mock 日期表確認與排班')).toHaveTextContent('matching plan 51');
    expect(screen.getByLabelText('mock 日期表確認與排班')).toHaveTextContent('2026-09-10、2026-09-11、2026-09-12、2026-09-13');
    expect(mocks.queryStaff).toHaveBeenCalledWith({ staffId: 8891 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(mocks.queryStaff).toHaveBeenCalledWith({ staffId: 8892 }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('只有明確點擊服務前更換月嫂後才展開既有 workflow，完成後重新讀取正式指派', async () => {
    mocks.getAssignmentPlan.mockResolvedValue(assignmentPlan());

    render(<OrderAssignmentPlanPanel caseNo="CASE-ASSIGNMENT-PLAN" />);

    expect(screen.queryByLabelText('mock 服務前換人 workflow')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '服務前更換月嫂' }));

    expect(screen.getByLabelText('mock 服務前換人 workflow')).toBeInTheDocument();
    expect(screen.getByText('replacement case CASE-ASSIGNMENT-PLAN')).toBeInTheDocument();

    await waitFor(() => expect(mocks.getAssignmentPlan).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: '模擬換人完成' }));
    await waitFor(() => expect(mocks.getAssignmentPlan).toHaveBeenCalledTimes(2));

    fireEvent.click(screen.getByRole('button', { name: '模擬請假代班' }));
    expect(window.location.hash).toBe('#scheduling?tab=leave_sub&case_no=CASE-ASSIGNMENT-PLAN');
  });
});
