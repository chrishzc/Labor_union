import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderMultiCaregiverPlanPanel } from '../components/OrderMultiCaregiverPlanPanel';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { MatchingAvailability, MatchingPlanSegmentInput } from '../api/scheduling/matching_candidate_workflow_client';

const mocks = vi.hoisted(() => ({ search: vi.fn(), create: vi.fn(), queryPlan: vi.fn(), detail: vi.fn() }));
vi.mock('../api/scheduling/matching_candidate_workflow_client', () => ({ matchingCandidateWorkflowClient: { searchSegmentedCaregivers: mocks.search, createMatchingPlan: mocks.create } }));
vi.mock('../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.queryPlan } }));
vi.mock('../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.detail } }));
const CASE = 'CASE-MULTI-BETA';
const filters = { region: true, cooking: false, preferred_service_days: true, daily_service_hours: true };
let created: MatchingPlanSegmentInput[] | null;
function availability(count: number): MatchingAvailability {
  return { case_no: CASE, planned_start_date: '2026-09-01', planned_end_date: '2026-09-20', feasibility: 'complete',
    complete_combinations: [Array.from({ length: count }, (_, index) => ({ segment_index: index, staff_id: 100 + index,
      start_date: `2026-09-${String(index * 5 + 1).padStart(2, '0')}`, end_date: `2026-09-${String(index * 5 + 5).padStart(2, '0')}` }))],
    segment_candidates: [], candidate_options: [], conflicts: [] };
}
function observed() {
  return { planId: 51, status: 'proposed', activeLockId: null, communicationVersion: 1,
    segments: (created ?? []).map((segment, index) => ({ segmentId: 71 + index, sequence: index + 1,
      staffId: segment.staff_id, assignedStartDate: segment.start_date, assignedEndDate: segment.end_date })) };
}
async function search(count = 2) {
  fireEvent.change(screen.getByLabelText('多月嫂服務分段數'), { target: { value: String(count) } });
  fireEvent.click(screen.getByRole('button', { name: '查詢多月嫂完整組合' }));
  return screen.findByRole('button', { name: `以完整組合 1 建立正式 ${count} 段方案` });
}

describe('Beta server-owned 多月嫂分段方案', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    created = null;
    mocks.search.mockImplementation(async (_caseNo, count) => availability(count));
    mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
    mocks.queryPlan.mockImplementation(async () => {
      if (created === null) throw new ApiHttpError(404, 'not_found', 'no plan');
      return observed();
    });
    mocks.create.mockImplementation(async (_caseNo, segments: MatchingPlanSegmentInput[]) => {
      created = segments;
      return { plan_id: 51, case_no: CASE, version: 1, status: 'proposed', result: 'created',
        segments: segments.map((segment, index) => ({ segment_order: index + 1, staff_id: segment.staff_id,
          assigned_start_date: segment.start_date, assigned_end_date: segment.end_date })) };
    });
  });

  it.each([2, 3, 4])('%i 段只傳送 server 完整組合，沿用四項 filter 並回讀每段 identity/日期', async (count) => {
    const onObserved = vi.fn();
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    const create = await search(count);
    expect(mocks.search).toHaveBeenCalledWith(CASE, count, [], filters);
    fireEvent.click(create);
    await screen.findByText(new RegExp(`正式 ${count} 段多月嫂方案 #51 已建立並完成回讀`));
    expect(mocks.create).toHaveBeenCalledWith(CASE, availability(count).complete_combinations[0]!.map((segment) => ({
      staff_id: segment.staff_id, start_date: segment.start_date, end_date: segment.end_date,
    })));
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.queryPlan).toHaveBeenCalledTimes(2);
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(create).toBeDisabled();
  });

  it('partial 查詢不從 segment_candidates 拼湊可建立方案', async () => {
    mocks.search.mockResolvedValue({ ...availability(2), feasibility: 'partial', complete_combinations: [],
      segment_candidates: availability(2).complete_combinations[0], conflicts: [{ segment_index: 1, staff_id: 101, work_date: '2026-09-07', reason_code: 'occupied' }] });
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    fireEvent.click(screen.getByRole('button', { name: '查詢多月嫂完整組合' }));
    await screen.findByText('後端未回傳可建立的 2 段完整組合。');
    expect(screen.queryByRole('button', { name: /建立正式/ })).not.toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it.each(['accepted', 'locked', 'completed', 'forbidden'])('%s 的正式 gate 不可繞過', async (gate) => {
    if (gate === 'accepted') mocks.queryPlan.mockResolvedValue({ ...observed(), status: 'accepted' });
    if (gate === 'locked') mocks.queryPlan.mockResolvedValue({ ...observed(), activeLockId: 88 });
    if (gate === 'completed') mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單完成' });
    if (gate === 'forbidden') mocks.queryPlan.mockRejectedValue(new ApiHttpError(403, 'forbidden', '無讀取權限'));
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    fireEvent.click(await search());
    await screen.findByRole('alert');
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('建立後 active-plan 分段不一致不報完成或重送', async () => {
    mocks.queryPlan.mockRejectedValueOnce(new ApiHttpError(404, 'not_found', 'no plan'))
      .mockResolvedValue({ ...observed(), segments: [] });
    const onObserved = vi.fn();
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    fireEvent.click(await search());
    await screen.findByRole('alert');
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: /以完整組合/ })).toBeDisabled();
  });

  it('篩選變更會清除舊組合，必須重新查詢', async () => {
    const view = render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await search();
    view.rerender(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={{ ...filters, cooking: true }} />);
    await waitFor(() => expect(screen.queryByRole('button', { name: /以完整組合/ })).not.toBeInTheDocument());
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('切換案件後舊查詢晚回來不能成為新案件的可操作組合', async () => {
    let resolve!: (data: MatchingAvailability) => void;
    mocks.search.mockImplementationOnce(() => new Promise<MatchingAvailability>((done) => { resolve = done; }));
    const view = render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    fireEvent.click(screen.getByRole('button', { name: '查詢多月嫂完整組合' }));
    view.rerender(<OrderMultiCaregiverPlanPanel caseNo="CASE-OTHER" filters={filters} />);
    await act(async () => { resolve(availability(2)); });
    expect(screen.queryByRole('button', { name: /以完整組合/ })).not.toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });
});
