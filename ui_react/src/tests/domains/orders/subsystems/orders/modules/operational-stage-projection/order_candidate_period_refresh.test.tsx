import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { OrderCandidateQueryPanel } from '../../../../../../../components/OrderCandidateQueryPanel';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const mocks = vi.hoisted(() => ({ search: vi.fn(), pool: vi.fn(), add: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', async (importOriginal) => ({ ...await importOriginal<typeof import('../../../../../../../api/scheduling/matching_candidate_workflow_client')>(), matchingCandidateWorkflowClient: { searchInquiryCandidates: mocks.search } }));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: { query: mocks.pool, addCandidates: mocks.add },
  createCandidateAddCommand: (caseNo: string, candidates: unknown[]) => ({ caseNo, candidates, actor: 'operator', eventKey: 'refresh-period' }),
}));

it('offers an explicit period update for an existing candidate and verifies the new period readback', async () => {
  orderMutationFlowStore.clearAll();
  const candidate = { id: 2, staff_id: 2, staff_name: '測試月嫂', status: 'active', willingness: 'willing', service_start_date: '2026-11-15', service_end_date: '2026-12-04' };
  const updated = { ...candidate, service_end_date: '2026-12-11', willingness: 'pending' };
  const pool = { case_no: 'TEST', pool_id: 1, candidates: [candidate] };
  mocks.pool.mockResolvedValueOnce(pool).mockResolvedValue({ ...pool, candidates: [updated] });
  mocks.add.mockResolvedValue({ pool_id: 1, candidate_ids: [2], status: 'recorded' });
  mocks.search.mockResolvedValue({ case_no: 'TEST', planned_start_date: '2026-11-15', planned_end_date: '2026-12-11', conflicts: [], candidate_options: [{ staff_id: 2, staff_name: candidate.staff_name, matching_conditions: { region: { status: 'pending', required_value: null, staff_values: [] }, preferred_service_days: { status: 'pending', required_value: null, staff_values: [] } }, segment_index: 0, case_period_start: '2026-11-15', case_period_end: '2026-12-11', selected_segment_start: '2026-11-15', selected_segment_end: '2026-12-11', full_case_coverage: true, supported_day_count: 27, required_day_count: 27 }] });
  render(<OrderCandidateQueryPanel caseNo="TEST" presentation="workbench" includeMultiCaregiver={false} />);
  await waitFor(() => expect(mocks.search).toHaveBeenCalled());
  const update = await screen.findByRole('button', { name: '更新詢問期間（測試月嫂）' });
  expect(screen.getByText(/更新後須重新記錄接案意願/)).toBeInTheDocument();
  fireEvent.click(update);
  await waitFor(() => expect(mocks.add).toHaveBeenCalledWith(expect.objectContaining({ candidates: [{ staff_id: 2, start_date: '2026-11-15', end_date: '2026-12-11' }] })));
  expect(await screen.findByRole('button', { name: '已加入候選池（測試月嫂）' })).toBeDisabled();
});

it('explains retained dates separately from buffer reminders without excluding a candidate', async () => {
  orderMutationFlowStore.clearAll();
  mocks.pool.mockReset().mockResolvedValue({ case_no: 'CONFLICT', pool_id: 1, candidates: [] });
  mocks.search.mockResolvedValue({ case_no: 'CONFLICT', planned_start_date: '2026-11-15', planned_end_date: '2026-12-05',
    conflicts: [
      { staff_id: 1, work_date: '2026-11-15', reason_code: 'active_lock' },
      { staff_id: 1, work_date: '2026-12-01', reason_code: 'buffer' },
    ], candidate_options: [{ segment_index: 0, staff_id: 1, staff_name: '衝突測試月嫂', matching_conditions: { region: { status: 'pending', required_value: null, staff_values: [] }, preferred_service_days: { status: 'pending', required_value: null, staff_values: [] } }, full_case_coverage: false,
      supported_day_count: 5, required_day_count: 21 }] });
  render(<OrderCandidateQueryPanel caseNo="CONFLICT" presentation="workbench" includeMultiCaregiver={false} />);
  await waitFor(() => expect(mocks.search).toHaveBeenCalled());
  await screen.findByText('未設定 衝突測試月嫂');
  fireEvent.click(screen.getByText('查看衝突日期與原因'));
  expect(screen.getByText('其他案件已保留檔期：2026-11-15')).toBeVisible();
  expect(screen.getByText('七天緩衝期（僅提醒，不阻擋）：2026-12-01')).toBeVisible();
  expect(screen.getByRole('button', { name: '加入候選池（衝突測試月嫂）' })).toBeEnabled();
});
