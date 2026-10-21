import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderMultiCaregiverPlanPanel } from '../../../../../../../components/OrderMultiCaregiverPlanPanel';
import { ApiHttpError, ApiNetworkError } from '../../../../../../../api/shared/typed_errors';
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
function availability(): MatchingAvailability {
  return { case_no: CASE, planned_start_date: '2026-09-01', planned_end_date: '2026-09-20', feasibility: 'partial',
    complete_combinations: [], segment_candidates: [], candidate_options: [100, 101, 102, 103].map((staffId) => ({
      segment_index: 0, staff_id: staffId, staff_name: `月嫂 ${staffId}`,
      coverage_day_count: 1, available_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-01' }],
      case_period_start: '2026-09-01', case_period_end: '2026-09-20', required_service_dates: ['2026-09-01'],
      supported_service_dates: ['2026-09-01'], supported_ranges: [{ start_date: '2026-09-01', end_date: '2026-09-01', service_day_count: 1 }],
      supported_day_count: 1, required_day_count: 1, full_case_coverage: false,
      selected_segment_start: '2026-09-01', selected_segment_end: '2026-09-01', full_selected_segment_coverage: true,
      uncovered_segment_dates: [], source_scheduling_version: 1, filter_results: {},
    })), conflicts: [] };
}
function segments(count = 2): MatchingPlanSegmentInput[] {
  return Array.from({ length: count }, (_, index) => ({ staff_id: 100 + index,
    start_date: `2026-09-${String(Math.floor(index * 20 / count) + 1).padStart(2, '0')}`,
    end_date: `2026-09-${String(Math.floor((index + 1) * 20 / count)).padStart(2, '0')}` }));
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
function fillDates(count = 2) {
  segments(count).forEach((segment, index) => {
    fireEvent.change(screen.getByLabelText(`第 ${index + 1} 段服務開始日`), { target: { value: segment.start_date } });
    fireEvent.change(screen.getByLabelText(`第 ${index + 1} 段服務結束日`), { target: { value: segment.end_date } });
  });
}
async function fillForm(count = 2) {
  await selectStaff(count);
  fillDates(count);
  return screen.getByRole('button', { name: `儲存 ${count} 段服務安排` });
}

describe('人工指定多月嫂服務日期', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
    created = null;
    mocks.search.mockResolvedValue(availability());
    mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
    mocks.queryPlan.mockImplementation(async () => {
      if (created === null) throw new ApiHttpError(404, 'not_found', 'no plan');
      return observed();
    });
    mocks.create.mockImplementation(async (command) => planReceipt(command));
  });

  it('本案下廚需求未填寫時提示補件位置並維持零寫入', async () => {
    mocks.search.mockRejectedValue(new ApiHttpError(409, 'matching_preference_source_not_ready', '媒合查詢失敗'));
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={{ ...filters, cooking: true }} />);
    await screen.findByText(/本案尚未填寫「下廚需求」/);
    expect(screen.getByText(/客戶名冊補齊本案下廚需求/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存 2 段服務安排' })).toBeDisabled();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it.each([2, 3, 4])('%i 段一次儲存人工指定人選與日期，並核對正式回讀', async (count) => {
    const onObserved = vi.fn();
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    const save = await fillForm(count);
    expect(mocks.create).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /完整組合/ })).not.toBeInTheDocument();
    fireEvent.click(save);
    await screen.findByText(new RegExp(`正式 ${count} 段多月嫂方案 #51 已建立並完成回讀`));
    expect(mocks.search).toHaveBeenCalledTimes(1);
    expect(mocks.search).toHaveBeenCalledWith(CASE, 1, [], filters, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ caseNo: CASE, actor: 'operator-1', segments: segments(count),
      asOf: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), key: expect.stringMatching(/^orders-multi-plan-/) }));
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.queryPlan).toHaveBeenCalledTimes(2);
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(save).toBeDisabled();
  });

  it('日期未填完、起訖顛倒或人選重複不能儲存', async () => {
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await selectStaff();
    const save = screen.getByRole('button', { name: '儲存 2 段服務安排' });
    expect(save).toBeDisabled();
    fillDates();
    expect(save).toBeEnabled();
    fireEvent.change(screen.getByLabelText('第 1 段服務開始日'), { target: { value: '2026-09-12' } });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('第 1 段服務開始日'), { target: { value: '' } });
    expect(save).toBeDisabled();
    fillDates();
    expect(screen.getByLabelText('第 2 段月嫂').querySelector('option[value="100"]')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('第 2 段月嫂'), { target: { value: '100' } });
    expect(save).toBeDisabled();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it.each(['accepted', 'locked', 'completed', 'forbidden'])('%s 的正式 gate 不可繞過', async (gate) => {
    if (gate === 'accepted') mocks.queryPlan.mockResolvedValue({ ...observed(), status: 'accepted' });
    if (gate === 'locked') mocks.queryPlan.mockResolvedValue({ ...observed(), activeLockId: 88 });
    if (gate === 'completed') mocks.detail.mockResolvedValue({ case_no: CASE, order_status: '訂單完成' });
    if (gate === 'forbidden') mocks.queryPlan.mockRejectedValue(new ApiHttpError(403, 'forbidden', '無讀取權限'));
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    fireEvent.click(await fillForm());
    await screen.findByRole('alert');
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it.each(['日期未完整銜接', '服務日期重疊', '檔期已被占用'])('後端拒絕 %s 後保留輸入，修改日期後可重新儲存', async (reason) => {
    mocks.create.mockRejectedValueOnce(new ApiHttpError(409, 'matching_plan_availability_conflict', reason));
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    const save = await fillForm();
    fireEvent.click(save);
    expect(await screen.findByRole('alert')).toHaveTextContent(reason);
    expect(screen.queryByRole('button', { name: '確認建立結果' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('第 1 段服務結束日')).toHaveValue('2026-09-10');
    expect(save).toBeEnabled();
    fireEvent.change(screen.getByLabelText('第 1 段服務結束日'), { target: { value: '2026-09-09' } });
    fireEvent.change(screen.getByLabelText('第 2 段服務開始日'), { target: { value: '2026-09-10' } });
    fireEvent.click(save);
    await screen.findByText(/正式 2 段多月嫂方案 #51 已建立並完成回讀/);
    expect(mocks.create.mock.calls[1]![0].segments).toEqual([
      { staff_id: 100, start_date: '2026-09-01', end_date: '2026-09-09' },
      { staff_id: 101, start_date: '2026-09-10', end_date: '2026-09-20' },
    ]);
  });

  it('建立後同一人選但日期回讀不一致不報完成，只能重讀', async () => {
    mocks.queryPlan.mockRejectedValueOnce(new ApiHttpError(404, 'not_found', 'no plan')).mockImplementation(async () => {
      const result = observed();
      result.segments[0]!.assignedEndDate = '2026-09-09';
      return result;
    });
    const onObserved = vi.fn();
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    fireEvent.click(await fillForm());
    await screen.findByText(/多月嫂方案建立收據與正式分段回讀不一致/);
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: '儲存 2 段服務安排' })).toBeDisabled();
    expect(screen.getByLabelText('第 1 段服務結束日')).toBeDisabled();
    mocks.queryPlan.mockImplementation(async () => observed());
    fireEvent.click(screen.getByRole('button', { name: '重新讀取' }));
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(mocks.create).toHaveBeenCalledTimes(1);
  });

  it.each([true, false])('儲存結果未明時保留原日期與操作識別，receipt 存在=%s', async (receiptExists) => {
    mocks.create.mockRejectedValueOnce(new ApiNetworkError());
    const onObserved = vi.fn();
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    fireEvent.click(await fillForm());
    await screen.findByRole('button', { name: '確認建立結果' });
    const command = mocks.create.mock.calls[0]![0];
    if (receiptExists) mocks.queryReceipt.mockResolvedValue(planReceipt(command));
    else mocks.queryReceipt.mockRejectedValue(new ApiHttpError(404, 'not_found', 'no receipt'));
    expect(screen.getByLabelText('第 1 段服務結束日')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '確認建立結果' }));
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(mocks.queryReceipt).toHaveBeenCalledWith(command);
    expect(mocks.create).toHaveBeenCalledTimes(receiptExists ? 1 : 2);
    if (!receiptExists) expect(mocks.create.mock.calls[1]![0]).toEqual(command);
  });

  it('篩選變更清除人選、保留本案輸入日期，重新選人後才可儲存', async () => {
    const view = render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    await fillForm();
    view.rerender(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={{ ...filters, cooking: true }} />);
    await waitFor(() => expect(screen.getByLabelText('第 1 段月嫂')).toHaveValue('0'));
    expect(screen.getByLabelText('第 1 段服務結束日')).toHaveValue('2026-09-10');
    expect(screen.getByRole('button', { name: '儲存 2 段服務安排' })).toBeDisabled();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it('對調先後人選時保留指定日期，不產生系統替代組合', async () => {
    render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} />);
    const save = await fillForm();
    fireEvent.change(screen.getByLabelText('第 1 段月嫂'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('第 2 段月嫂'), { target: { value: '100' } });
    fireEvent.change(screen.getByLabelText('第 1 段月嫂'), { target: { value: '101' } });
    fireEvent.click(save);
    await screen.findByText(/正式 2 段多月嫂方案 #51 已建立並完成回讀/);
    expect(mocks.create.mock.calls[0]![0].segments).toEqual([
      { staff_id: 101, start_date: '2026-09-01', end_date: '2026-09-10' },
      { staff_id: 100, start_date: '2026-09-11', end_date: '2026-09-20' },
    ]);
  });

  it('等待案件回讀時切換案件，舊輸入與晚回應不能寫入新案件', async () => {
    let resolve!: (data: { case_no: string; order_status: string }) => void;
    mocks.detail.mockImplementation(() => new Promise((done) => { resolve = done; }));
    const onObserved = vi.fn();
    const view = render(<OrderMultiCaregiverPlanPanel caseNo={CASE} filters={filters} onObserved={onObserved} />);
    fireEvent.click(await fillForm());
    expect(screen.getByLabelText('第 1 段服務開始日')).toBeDisabled();
    mocks.search.mockResolvedValue({ ...availability(), case_no: 'CASE-OTHER' });
    view.rerender(<OrderMultiCaregiverPlanPanel caseNo="CASE-OTHER" filters={filters} onObserved={onObserved} />);
    await act(async () => { resolve({ case_no: CASE, order_status: '訂單成立' }); });
    expect(screen.getByLabelText('第 1 段服務開始日')).toHaveValue('');
    expect(screen.getByLabelText('第 1 段月嫂')).toHaveValue('0');
    expect(mocks.create).not.toHaveBeenCalled();
    expect(onObserved).not.toHaveBeenCalled();
  });
});
