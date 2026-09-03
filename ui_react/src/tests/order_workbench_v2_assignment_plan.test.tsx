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

describe('待辦看板 Beta 第 10 階正式指派與排班回讀', () => {
  beforeEach(() => {
    mocks.getAssignmentPlan.mockReset();
  });

  it('只使用既有 assignment-plan owner facts 顯示正式指派段與官方服務日', async () => {
    mocks.getAssignmentPlan.mockResolvedValue({
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
    });

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
});
