import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderMultiCaregiverPlanPanel } from '../../../../../../../components/OrderMultiCaregiverPlanPanel';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import type { MatchingAvailability, MatchingPlanSegmentInput } from '../../../../../../../api/scheduling/matching_candidate_workflow_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const mocks = vi.hoisted(() => ({ search: vi.fn(), create: vi.fn(), queryReceipt: vi.fn(), queryPlan: vi.fn(), detail: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', () => ({ matchingCandidateWorkflowClient: {
  searchSegmentedCaregivers: mocks.search, createMatchingPlan: mocks.create, queryMatchingPlanReceipt: mocks.queryReceipt,
} }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.queryPlan } }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.detail } }));
const CASE = 'CASE-MULTI-BETA';
const filters = { region: true, cooking: false, preferred_service_days: true, daily_service_hours: true };
let created: MatchingPlanSegmentInput[] | null;
function availability(count: number): MatchingAvailability {
  return { case_no: CASE, planned_start_date: '2026-09-01', planned_end_date: '2026-09-20', feasibility: count === 1 ? 'partial' : 'complete',
    complete_combinations: count === 1 ? [] : [Array.from({ length: count }, (_, index) => ({ segment_index: index, staff_id: 100 + index,
      start_date: `2026-09-${String(index * 5 + 1).padStart(2, '0')}`, end_date: `2026-09-${String(index * 5 + 5).padStart(2, '0')}` }))],
    segment_candidates: [], candidate_options: count === 1 ? [100, 101, 102, 103].map((staffId) => ({
      segment_index: 0, staff_id: staffId, staff_name: `月嫂 ${staffId}`,
      coverage_day_count: 1, available_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-01' }],
      case_period_start: '2026-09-01', case_period_end: '2026-09-20', required_service_dates: ['2026-09-01'],
      supported_service_dates: ['2026-09-01'], supported_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-01', service_day_count: 1 }],
      supported_day_count: 1, required_day_count: 1, full_case_coverage: true,
      selected_segment_start: '2026-09-01', selected_segment_end: '2026-09-01', full_selected_segment_coverage: true,
      uncovered_segment_dates: [], source_scheduling_version: 1, filter_results: {},
    })) : [], conflicts: [] };
}
function observed() {
  return { planId: 51, status: 'proposed', activeLockId: null, planVersion: 1,
    segments: (created ?? []).map((segment, index) => ({ segmentId: 71 + index, sequence: index + 1,
      staffId: segment.staff_id, assignedStartDate: segment.start_date, assignedEndDate: segment.end_date })) };
}
function planReceipt(command: { caseNo: string; actor: string; asOf: string; key: string; segments: MatchingPlanSegmentInput[] }) {
  created = command.segments;
  return { plan_id: 51, case_no: command.caseNo, version: 1, status: 'proposed' as const, result: 'created' as const,
    actor: command.actor, as_of: command.asOf, event_key: command.key, command_fingerprint: 'a'.repeat(64), replayed: false,
    segments: command.segments.map((segment, index) => ({ segment_order: index + 1, staff_id: segment.staff_id,
      assigned_start_date: segment.start_date, assigned_end_date: segment.end_date })) };
}
async function selectStaff(count = 2) {
  fireEvent.change(screen.getByLabelText('多月嫂服務分段數'), { target: { value: String(count) } });
  await waitFor(() => expect(screen.getByLabelText('第 1 段月嫂').querySelector('option[value="100"]')).not.toBeNull());
  for (let index = 0; index < count; index += 1) {
    fireEvent.change(screen.getByLabelText(`第 ${index + 1} 段月嫂`), { target: { value: String(100 + index) } });
  }
}

async function search(count = 2) {
  await selectStaff(count);
  fireEvent.click(screen.getByRole('button', { name: `查詢這 ${count} 位月嫂的完整組合` }));
  return screen.findByRole('button', { name: `以完整組合 1 建立正式 ${count} 段方案` });
}

describe('Beta server-owned 多月嫂分段方案', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
    created = null;
    mocks.search.mockImplementation(async (_caseNo, count) => availability(count));
    mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
    mocks.queryPlan.mockImplementation(async () => {
      if (created === null) throw new ApiHttpError(404, 'not_found', 'no plan');
      return observed();
    });
    mocks.create.mockImplementation(async (command) => planReceipt(command));
  });

  it.each([2, 3, 4])('%i 段只傳送 server 完整組合，沿用四項 filter 並回讀每段 identity/日期', async (count) => {
    const onObserved = vi.fn();
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    const create = await search(count);
    expect(mocks.search).toHaveBeenCalledWith(CASE, count, Array.from({ length: count }, (_, index) => ({ staff_id: 100 + index })), filters,
      expect.objectContaining({ signal: expect.any(AbortSignal) }));
    fireEvent.click(create);
    await screen.findByText(new RegExp(`正式 ${count} 段多月嫂方案 #51 已建立並完成回讀`));
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({
      caseNo: CASE, actor: 'operator-1', segments: availability(count).complete_combinations[0]!.map((segment) => ({
        staff_id: segment.staff_id, start_date: segment.start_date, end_date: segment.end_date,
      })), asOf: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), key: expect.stringMatching(/^orders-multi-plan-/),
    }));
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.queryPlan).toHaveBeenCalledTimes(2);
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(create).toBeDisabled();
  });

  it('partial 查詢不從 segment_candidates 拼湊可建立方案', async () => {
    mocks.search.mockImplementation(async (_caseNo, count) => count === 1 ? availability(1) : { ...availability(2), feasibility: 'partial', complete_combinations: [],
      segment_candidates: availability(2).complete_combinations[0], conflicts: [{ segment_index: 1, staff_id: 101, work_date: '2026-09-07', reason_code: 'occupied' }] });
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await selectStaff();
    fireEvent.click(screen.getByRole('button', { name: '查詢這 2 位月嫂的完整組合' }));
    await screen.findByText('這 2 位月嫂目前沒有可完整銜接的方案，請調整人選、順序或媒合條件後再查詢。');
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
    await screen.findByText(/多月嫂方案建立收據與正式分段回讀不一致/);
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

  it('必須依序選不同月嫂；換人後舊組合不可建立', async () => {
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    const searchButton = screen.getByRole('button', { name: '查詢這 2 位月嫂的完整組合' });
    await waitFor(() => expect(screen.getByLabelText('第 1 段月嫂').querySelector('option[value="100"]')).not.toBeNull());
    expect(searchButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText('第 1 段月嫂'), { target: { value: '100' } });
    expect(screen.getByLabelText('第 2 段月嫂').querySelector('option[value="100"]')).toBeDisabled();
    expect(searchButton).toBeDisabled();
    fireEvent.change(screen.getByLabelText('第 2 段月嫂'), { target: { value: '101' } });
    expect(searchButton).toBeEnabled();
    fireEvent.click(searchButton);
    await screen.findByRole('button', { name: '以完整組合 1 建立正式 2 段方案' });
    fireEvent.change(screen.getByLabelText('第 1 段月嫂'), { target: { value: '102' } });
    expect(screen.queryByRole('button', { name: /以完整組合/ })).not.toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('先後人選對調時，查詢草稿保留使用者選定的順序', async () => {
    mocks.search.mockImplementation(async (_caseNo, count) => count === 1 ? availability(1) : {
      ...availability(2), complete_combinations: [[
        { segment_index: 0, staff_id: 101, start_date: '2026-09-01', end_date: '2026-09-10' },
        { segment_index: 1, staff_id: 100, start_date: '2026-09-11', end_date: '2026-09-20' },
      ]],
    });
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await waitFor(() => expect(screen.getByLabelText('第 1 段月嫂').querySelector('option[value="101"]')).not.toBeNull());
    fireEvent.change(screen.getByLabelText('第 1 段月嫂'), { target: { value: '101' } });
    fireEvent.change(screen.getByLabelText('第 2 段月嫂'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: '查詢這 2 位月嫂的完整組合' }));
    await screen.findByRole('button', { name: '以完整組合 1 建立正式 2 段方案' });
    expect(mocks.search).toHaveBeenCalledWith(CASE, 2, [{ staff_id: 101 }, { staff_id: 100 }], filters,
      expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('伺服器回傳不符指定人選的組合不顯示為可建立方案', async () => {
    mocks.search.mockImplementation(async (_caseNo, count) => count === 1 ? availability(1) : {
      ...availability(2), complete_combinations: [[
        { segment_index: 0, staff_id: 103, start_date: '2026-09-01', end_date: '2026-09-10' },
        { segment_index: 1, staff_id: 101, start_date: '2026-09-11', end_date: '2026-09-20' },
      ]],
    });
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await selectStaff();
    fireEvent.click(screen.getByRole('button', { name: '查詢這 2 位月嫂的完整組合' }));
    await screen.findByText('這 2 位月嫂目前沒有可完整銜接的方案，請調整人選、順序或媒合條件後再查詢。');
    expect(screen.queryByRole('button', { name: /以完整組合/ })).not.toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('切換案件後舊查詢晚回來不能成為新案件的可操作組合', async () => {
    let resolve!: (data: MatchingAvailability) => void;
    mocks.search.mockImplementation((_caseNo, count) => count === 1
      ? Promise.resolve(availability(1))
      : new Promise<MatchingAvailability>((done) => { resolve = done; }));
    const view = render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await selectStaff();
    fireEvent.click(screen.getByRole('button', { name: '查詢這 2 位月嫂的完整組合' }));
    view.rerender(<OrderMultiCaregiverPlanPanel caseNo="CASE-OTHER" filters={filters} />);
    await act(async () => { resolve(availability(2)); });
    expect(screen.queryByRole('button', { name: /以完整組合/ })).not.toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();
  });
});
