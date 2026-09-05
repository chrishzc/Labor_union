import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderAssignmentPlanPanel } from '../components/OrderAssignmentPlanPanel';

const mocks = vi.hoisted(() => ({
  getAssignmentPlan: vi.fn(),
}));

vi.mock('../api/orders/order_query_client', () => ({
  ordersQueryClient: {
    getAssignmentPlan: mocks.getAssignmentPlan,
  },
}));

vi.mock('../components/ServiceBeforeReplacementActions', () => ({
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

describe('待辦看板 Beta 第 10 階正式指派與排班回讀', () => {
  beforeEach(() => {
    mocks.getAssignmentPlan.mockReset();
    window.location.hash = '';
  });

  it('只使用既有 assignment-plan owner facts 顯示正式指派段與官方服務日', async () => {
    mocks.getAssignmentPlan.mockResolvedValue(assignmentPlan());

    render(<OrderAssignmentPlanPanel caseNo="CASE-ASSIGNMENT-PLAN" />);
    fireEvent.click(screen.getByRole('button', { name: '讀取正式指派與排班' }));

    await waitFor(() => expect(mocks.getAssignmentPlan).toHaveBeenCalledWith('CASE-ASSIGNMENT-PLAN'));
    expect(await screen.findByText('2 段')).toBeInTheDocument();
    expect(screen.getByText('#12')).toBeInTheDocument();
    expect(screen.getByText('#3')).toBeInTheDocument();
    expect(screen.getByText('4 天 × 8 小時')).toBeInTheDocument();

    const first = screen.getByLabelText('第 1 段正式指派');
    expect(within(first).getByText('#8891')).toBeInTheDocument();
    expect(within(first).getByText('2026-09-10 ~ 2026-09-11')).toBeInTheDocument();
    expect(within(first).getByText('2026-09-10、2026-09-11')).toBeInTheDocument();

    const second = screen.getByLabelText('第 2 段正式指派');
    expect(within(second).getByText('#8892')).toBeInTheDocument();
    expect(within(second).getByText('2026-09-12、2026-09-13')).toBeInTheDocument();
    expect(screen.queryByText(/待開工|服務進行中/)).not.toBeInTheDocument();
  });

  it('只有明確點擊服務前更換月嫂後才展開既有 workflow，完成後重新讀取正式指派', async () => {
    mocks.getAssignmentPlan.mockResolvedValue(assignmentPlan());

    render(<OrderAssignmentPlanPanel caseNo="CASE-ASSIGNMENT-PLAN" />);

    expect(screen.queryByLabelText('mock 服務前換人 workflow')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '服務前更換月嫂' }));

    expect(screen.getByLabelText('mock 服務前換人 workflow')).toBeInTheDocument();
    expect(screen.getByText('replacement case CASE-ASSIGNMENT-PLAN')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '模擬換人完成' }));
    await waitFor(() => expect(mocks.getAssignmentPlan).toHaveBeenCalledWith('CASE-ASSIGNMENT-PLAN'));

    fireEvent.click(screen.getByRole('button', { name: '模擬請假代班' }));
    expect(window.location.hash).toBe('#scheduling?tab=leave_sub&case_no=CASE-ASSIGNMENT-PLAN');
  });
});
