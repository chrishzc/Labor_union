import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { OrderWorkbenchV2Drawer } from '../../../../../../../components/OrderWorkbenchV2Drawer';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS } from '../../../../../../../api/orders/order_core_stage_projection_schemas';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';

const calls = vi.hoisted(() => ({ core: vi.fn(), detail: vi.fn(), terms: vi.fn(), assignment: vi.fn(),
  start: vi.fn(), matching: vi.fn(), queryDates: vi.fn(), previewDates: vi.fn(), applyDates: vi.fn(),
  previewArrangement: vi.fn(), applyArrangement: vi.fn() }));
vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({
  orderCoreStageProjectionClient: { getCoreStageTimelines: calls.core },
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: {
  getOrderDetail: calls.detail, getOrderTerms: calls.terms, getAssignmentPlan: calls.assignment,
  getActualStart: calls.start,
} }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({
  waitingDepositLockClient: { queryPlan: calls.matching },
}));
vi.mock('../../../../../../../api/orders/order_mutation_client', () => ({ ordersMutationClient: {
  getServiceDates: calls.queryDates, previewServiceDates: calls.previewDates, applyServiceDates: calls.applyDates,
  previewHistoricalArrangement: calls.previewArrangement, applyHistoricalArrangement: calls.applyArrangement,
} }));
// Unrelated work groups may remain mounted while the service facts are loading.
vi.mock('../../../../../../../components/OrderIntakeRepairPanel', () => ({ OrderIntakeRepairPanel: () => null }));
vi.mock('../../../../../../../components/OrderTermsMutationPanel', () => ({ OrderTermsMutationPanel: () => null }));

const CASE = 'HIST-ARRANGEMENT-WORKBENCH';
const dates = ['2026-09-14', '2026-09-15', '2026-09-16'];
let confirmedVersion: number;
let schedulingVersion: number;
const query = () => ({ case_no: CASE, order_version: 3, scheduling_version: schedulingVersion,
  contracted_service_days: 3, suggested_dates: [], selectable_dates: dates, current_version: confirmedVersion,
  current_dates: dates, bound_staff: [{ staff_id: 12, staff_name: '既定月嫂' }], arrangement_pending: schedulingVersion === 1 });
const assignment = () => ({ case_no: CASE, order_version: 3, scheduling_version: schedulingVersion,
  scheduling_generation: schedulingVersion, client_finance_version: 1, payroll_version: 1,
  contracted_service_days: 3, service_hours_per_day: 4, service_started: false,
  assignments: schedulingVersion === 1 ? [] : [{ assignment_id: 101, candidate_key: null, staff_id: 12, sequence: 1,
    assigned_start_date: dates[0], assigned_end_date: dates[2], official_service_dates: dates,
    actual_hours: null, lineage_source_assignment_ids: [] }] });

beforeEach(() => {
  Object.values(calls).forEach((call) => call.mockReset());
  orderMutationFlowStore.clearAll(); confirmedVersion = 2; schedulingVersion = 1;
  calls.core.mockImplementation(async () => ({ items: [{ case_no: CASE, lifecycle_status: '訂單成立', branch_type: 'normal',
    current_core_stage_code: 'formal_service', current_core_stage_ordinal: 10,
    historical_current_owner_stage_code: null, historical_current_owner_stage_ordinal: null,
    core_stages: CORE_STAGE_CODES.map((code, i) => ({ ordinal: i + 1, code, label: code, owner: 'test',
      status: code === 'formal_service' ? 'in_progress' : 'completed',
      substatus_code: SUBSTATUS_BY_STAGE_STATUS[code][code === 'formal_service' ? 'in_progress' : 'completed'],
      source: { owner: 'test', identity: CASE, version: 1 }, occurred_at: null, blockers: [], warnings: [],
      available_read_actions: [], availability_reason: null })) }] }));
  calls.detail.mockResolvedValue({ case_no: CASE, client_id: 88, client_name: '測試客戶', staff_name: null,
    order_status: '訂單成立', actual_start_date: dates[0], start_date: '2026-09-21', service_days: 3, service_hours_per_day: 4 });
  calls.terms.mockResolvedValue({ case_no: CASE, terms: { planned_start_date: '2026-09-21', service_days: 3,
    service_hours_per_day: 4, service_time: { start_time: '08:30:00', end_time: '12:30:00', end_day_offset: 0 } } });
  calls.assignment.mockImplementation(async () => assignment());
  calls.start.mockImplementation(async () => ({ case_no: CASE, current_actual_start_date: dates[0], planned_start_date: '2026-09-21',
    service_data_locked: false, order_version: 3, scheduling_version: schedulingVersion,
    scheduling_generation: schedulingVersion, has_formal_assignments: schedulingVersion > 1 }));
  calls.matching.mockRejectedValue(new ApiHttpError(404, 'resource_not_found', '無媒合方案'));
  calls.queryDates.mockImplementation(async () => query());
  calls.previewDates.mockImplementation(async () => ({ case_no: CASE, order_version: 3, scheduling_version: 1,
    current_version: confirmedVersion, service_dates: dates, weeks: [], preview_fingerprint: 'a'.repeat(64) }));
  calls.applyDates.mockImplementation(async () => {
    confirmedVersion += 1;
    return { case_no: CASE, confirmed_version: confirmedVersion, order_version: 3, scheduling_version: 1,
      service_dates: dates, preview_fingerprint: 'a'.repeat(64) };
  });
  calls.previewArrangement.mockImplementation(async () => ({ case_no: CASE, order_version: 3, scheduling_version: 1,
    confirmed_version: confirmedVersion, segments: [{ staff_id: 12, assigned_start_date: dates[0], assigned_end_date: dates[2],
      service_dates: dates }], preview_fingerprint: 'b'.repeat(64) }));
  calls.applyArrangement.mockImplementation(async () => {
    schedulingVersion = 2;
    return { case_no: CASE, scheduling_version: 2, generation_number: 2, assignment_ids: [101], preview_fingerprint: 'b'.repeat(64) };
  });
});

it('日期保存後聚焦下一步；正式排班沿用既定月嫂，明確確認才建立並刷新指派', async () => {
  const observed = vi.fn();
  render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} onObserved={observed} />);
  await screen.findByRole('button', { name: '前往正式排班' });
  expect(screen.queryByRole('button', { name: '預覽正式安排' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '確認服務日期' }));
  fireEvent.click(await screen.findByRole('button', { name: '完成服務日期確認' }));
  await screen.findByText('服務日期已確認並回讀版本 #3。');
  expect(screen.getByLabelText('服務日期確認後下一步')).toHaveFocus();
  expect(calls.applyArrangement).not.toHaveBeenCalled();
  expect(calls.previewArrangement).not.toHaveBeenCalled();

  await waitFor(() => expect(screen.getByRole('button', { name: '前往正式排班' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '前往正式排班' }));
  expect(screen.getByRole('button', { name: '正式排班' })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByLabelText('待建立正式安排摘要')).toHaveTextContent('既定月嫂');
  expect(screen.queryByText(/請至「推薦確認」確認人選/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '確認／更正實際開始日' })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '預覽正式安排' }));
  const apply = await screen.findByRole('button', { name: '建立正式安排' });
  await waitFor(() => expect(apply).toBeEnabled());
  expect(calls.applyArrangement).not.toHaveBeenCalled();
  fireEvent.click(apply);
  await screen.findByText('歷史案件正式安排已建立並回讀。');
  await screen.findByText('1 段');
  expect(calls.applyArrangement).toHaveBeenCalledWith(CASE, expect.objectContaining({
    expected_confirmed_version: 3, expected_scheduling_version: 1, segments: [{ staff_id: 12, service_dates: dates }],
  }), expect.anything());
  expect(within(screen.getByLabelText('第 1 段正式指派')).getByText(dates.join('、'))).toBeInTheDocument();
  expect(screen.queryByText(/請至「推薦確認」確認人選/)).not.toBeInTheDocument();
  expect(observed).toHaveBeenCalledTimes(2);
});

it('建立安排期間鎖定案件導覽；切回日期再返回仍保留原操作鍵供重試', async () => {
  let reject!: (error: Error) => void;
  calls.applyArrangement.mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
  const close = vi.fn();
  render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={close} />);
  fireEvent.click(await screen.findByRole('button', { name: '前往正式排班' }));
  fireEvent.click(screen.getByRole('button', { name: '預覽正式安排' }));
  const apply = await screen.findByRole('button', { name: '建立正式安排' });
  await waitFor(() => expect(apply).toBeEnabled());
  fireEvent.click(apply);
  await waitFor(() => expect(screen.getByRole('button', { name: '← 返回待辦看板' })).toBeDisabled());
  expect(screen.getByRole('button', { name: '確認日期' })).toBeDisabled();
  expect(close).not.toHaveBeenCalled();
  await act(async () => reject(new Error('網路中斷')));
  await screen.findByText('網路中斷');
  fireEvent.click(screen.getByRole('button', { name: '調整開始日與服務日期' }));
  expect(screen.getByLabelText('實際開始日')).toHaveValue(dates[0]);
  fireEvent.click(screen.getByRole('button', { name: '正式排班' }));
  fireEvent.click(screen.getByRole('button', { name: '以原操作確認結果' }));
  await screen.findByText('歷史案件正式安排已建立並回讀。');
  expect(calls.applyArrangement).toHaveBeenCalledTimes(2);
  expect(calls.applyArrangement.mock.calls[0][2].idempotencyKey).toBe(calls.applyArrangement.mock.calls[1][2].idempotencyKey);
});

it('開始日尚未確認時不能切到正式排班建立舊日期，返回後保留此次輸入', async () => {
  render(<OrderWorkbenchV2Drawer caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
  await screen.findByRole('button', { name: '前往正式排班' });
  fireEvent.change(screen.getByLabelText('實際開始日'), { target: { value: '' } });
  expect(screen.getByRole('button', { name: '前往正式排班' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '正式排班' }));
  expect(screen.getByText('開始日或服務日期尚未完成保存與回讀，請先回到「確認日期」接續確認。')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '預覽正式安排' })).not.toBeInTheDocument();
  expect(calls.applyArrangement).not.toHaveBeenCalled();
  expect(calls.previewArrangement).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '調整開始日與服務日期' }));
  expect(screen.getByLabelText('實際開始日')).toHaveValue('');
});
