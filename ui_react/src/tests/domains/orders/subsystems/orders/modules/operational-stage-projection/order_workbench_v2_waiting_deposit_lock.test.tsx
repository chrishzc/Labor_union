/** Current service-start handoff and retained waiting-lock client guards; success still requires canonical assignment readback. */
import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';
import { MatchingScheduleAndAssignmentActions } from '../../../../../../../components/MatchingScheduleAndAssignmentActions';
import { serviceStartClient, type ServiceStartView } from '../../../../../../../api/scheduling/service_start_client';
import { serviceArrangementStatusClient } from '../../../../../../../api/scheduling/service_arrangement_status_client';
import { assignmentPlanMutationClient } from '../../../../../../../api/scheduling/assignment_plan_mutation_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import type { MatchingScheduleState } from '../../../../../../../api/scheduling/matching_schedule_confirmation_client';

const mocks = vi.hoisted(() => ({ queryPlan: vi.fn(), queryContactState: vi.fn(), confirmationPreview: vi.fn(), preview: vi.fn(), apply: vi.fn(),
  querySchedule: vi.fn(), send: vi.fn(), prepare: vi.fn(), confirm: vi.fn(), assignment: vi.fn() }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: {
  queryPlan: mocks.queryPlan, preview: mocks.preview, apply: mocks.apply,
} }));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: { queryContactState: mocks.queryContactState, previewCustomerConfirmation: mocks.confirmationPreview } }));
vi.mock('../../../../../../../api/scheduling/matching_schedule_confirmation_client', () => ({ matchingScheduleConfirmationClient: {
  query: mocks.querySchedule, prepareManual: mocks.prepare, send: mocks.send, confirmRecipient: mocks.confirm,
} }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getAssignmentPlan: mocks.assignment } }));
const CASE = 'CASE-DEPOSIT-LOCK';
const dates = ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-05'];
let lockId: number | null;
let accepted: boolean;
function startTodo(): ServiceStartView {
  return { request_id: 8, case_no: CASE, staff_id: 8891, staff_name: '原月嫂', segment_id: 71,
    order_version: 2, version: 4, status: 'substitute_required', requested_start_date: dates[0],
    selected_staff_id: 8892, selected_staff_name: '接任月嫂', willingness: 'willing', invitation_status: 'sent', joined: true,
    proposed_start_date: dates[0], proposed_end_date: dates[4], result: null,
    workflow_kind: 'service_start', leave_dates: [], conflict_message: null, handover_dates: [] };
}
function completedTodo(): ServiceStartView {
  return { ...startTodo(), status: 'applied', version: 5, result: {
    actual_start_date: dates[0], actual_end_date: dates[4], order_version: 3,
    first_payment_due_date: dates[0], group_record_queued: true,
    assignments: [{ staff_id: 8892, staff_name: '接任月嫂', service_dates: dates }],
  } };
}
async function saveDates() {
  fireEvent.click(await screen.findByRole('button', { name: '儲存並更新排班' }));
}
function activePlan() {
  return { planId: 51, status: accepted ? 'accepted' : 'proposed', activeLockId: lockId, planVersion: 1,
    segments: [{ segmentId: 71, sequence: 1, staffId: 8892, assignedStartDate: dates[0], assignedEndDate: dates[4] }] };
}
function contactState() {
  return { plan: { id: 51, case_no: CASE, communication_version: 5, status: accepted ? 'accepted' : 'proposed', is_active: 1 },
    segments: [{ segment_id: 71, willingness: 'willing' }], all_willing: true,
    customer_decision: accepted ? 'accepted' : 'pending', customer_profiles_status: 'manually_confirmed', customer_profiles_manual_confirmation: null };
}
function schedule(): MatchingScheduleState {
  const weeks = [{ week_number: 1, period_start: dates[0], period_end: dates[4], service_dates: dates, service_day_count: 5 }];
  return { case_no: CASE, plan_id: 51, confirmed_service_date_version: 3, snapshot_id: 31, snapshot_status: 'manual_ready', gate_passed: true,
    outdated_schedule_preview: null,
    schedule_preview: { week_grouping_policy: 'calendar_week_sunday_to_saturday_v1', total_service_days: 5, total_weeks: 1, weeks,
      recipient_schedules: [{ audience_type: 'customer', segment_id: null, total_service_days: 5, total_weeks: 1, weeks },
        { audience_type: 'caregiver', segment_id: 71, total_service_days: 5, total_weeks: 1, weeks }] },
    recipients: [{ recipient_snapshot_id: 41, audience_type: 'customer', segment_id: null, delivery_status: 'pending', confirmation_status: 'manually_confirmed', confirmation_source: 'admin', confirmation_reason: '電話已確認', confirmation_occurred_at_utc: '2026-08-31T00:00:00Z' },
      { recipient_snapshot_id: 42, audience_type: 'caregiver', segment_id: 71, delivery_status: 'pending', confirmation_status: 'manually_confirmed', confirmation_source: 'admin', confirmation_reason: '電話已確認', confirmation_occurred_at_utc: '2026-08-31T00:00:00Z' }] };
}
function CurrentFlow({ onObserved }: { onObserved: () => void }) {
  const [datesOpen, setDatesOpen] = useState(false);
  const [observed, setObserved] = useState(false);
  const [revision, setRevision] = useState(0);
  return <>
    <OrderFormalRecommendationPanel caseNo={CASE} revision={revision} assignmentExists={observed} onObserved={onObserved} onOpenServiceDates={() => setDatesOpen(true)} />
    {datesOpen && <MatchingScheduleAndAssignmentActions caseNo={CASE} planId={51} planSegments={activePlan().segments}
      waitingLockAcquired={lockId !== null} assignmentExists={observed} onOpenDates={() => setDatesOpen(false)}
      onAssignmentCompleted={async () => { await onObserved(); setObserved(true); setRevision(value => value + 1); }} />}
  </>;
}
async function open(onObserved = vi.fn()) {
  render(<CurrentFlow onObserved={onObserved} />);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(accepted ? '客戶已接受' : '確認資訊已送達'));
  return onObserved;
}
async function openDates() { await act(async () => { fireEvent.click(screen.getByRole('button', { name: '前往確認服務日期' })); }); }
function expectNoUiMutation() {
  expect(mocks.preview).not.toHaveBeenCalled();
  expect(mocks.apply).not.toHaveBeenCalled();
  expect(mocks.prepare).not.toHaveBeenCalled();
  expect(mocks.send).not.toHaveBeenCalled();
  expect(mocks.confirm).not.toHaveBeenCalled();
  expect(assignmentPlanMutationClient.preview).not.toHaveBeenCalled();
  expect(assignmentPlanMutationClient.apply).not.toHaveBeenCalled();
}

describe('待辦看板目前自動等待訂金鎖及正式排班', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    orderMutationFlowStore.clearAll();
    sessionClient.setSession('synthetic-auto-arrangement-session', { id: 7, username: 'arrangement-test', display_name: '測試工會人員', role: 'admin' });
    sessionStorage.clear();
    lockId = null; accepted = true;
    vi.spyOn(serviceStartClient, 'todos').mockResolvedValue({ items: [startTodo()], total: 1, page: 1, page_size: 25 });
    vi.spyOn(serviceStartClient, 'options').mockResolvedValue({ items: [] });
    vi.spyOn(serviceStartClient, 'command').mockResolvedValue(completedTodo());
    vi.spyOn(assignmentPlanMutationClient, 'preview').mockRejectedValue(new Error('Unexpected UI assignment preview'));
    vi.spyOn(assignmentPlanMutationClient, 'apply').mockRejectedValue(new Error('Unexpected UI assignment apply'));
    mocks.queryPlan.mockImplementation(async () => activePlan());
    mocks.queryContactState.mockImplementation(async () => contactState());
    mocks.confirmationPreview.mockResolvedValue({ case_no: CASE, plan_id: 51, expected_version: 5,
      order_information_1_ready: true, order_information_2_ready: true, weekly_service_ready: true,
      weekly_service_row_count: 1, order_information_1: [], order_information_2: [], weekly_service_rows: [],
      caregiver_resumes: [], blockers: [], send_allowed: true });
    mocks.querySchedule.mockImplementation(async () => schedule());
    mocks.assignment.mockResolvedValue({ case_no: CASE, order_version: 3, scheduling_version: 2, scheduling_generation: 2,
      assignments: [{ staff_id: 8892, assigned_start_date: dates[0], assigned_end_date: dates[4], official_service_dates: dates }] });
    vi.spyOn(serviceArrangementStatusClient, 'arrangement').mockResolvedValue({ case_no: CASE, plan_id: 51, state: 'queued', blockers: [], job_id: 'automatic-job-51', assignment_count: 0 });
  });
  afterEach(() => { sessionClient.clearSession(); orderMutationFlowStore.clearAll(); vi.restoreAllMocks(); });

  it('accepted 方案只讀服務開始進度，正式 owner 回讀成立才通知父頁並回讀保留狀態', async () => {
    const onObserved = await open();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    await openDates();
    await screen.findByText(/已加入原案件群組/);
    expectNoUiMutation();
    expect(serviceStartClient.command).not.toHaveBeenCalled();
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.assignment).not.toHaveBeenCalled();
    lockId = 88;
    await saveDates();
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(mocks.assignment).toHaveBeenCalledWith(CASE, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    await waitFor(() => expect(mocks.queryPlan).toHaveBeenCalledTimes(2));
    expect(mocks.queryPlan).toHaveBeenLastCalledWith(CASE);
    expect(screen.getByRole('heading', { name: '已轉為正式班表' })).toBeInTheDocument();
    expect(serviceStartClient.command).toHaveBeenCalledTimes(1);
    expectNoUiMutation();
  });

  it('正式占用衝突保留雙方確認並阻擋自動處理，不提供手動繞過', async () => {
    vi.mocked(serviceStartClient.command).mockRejectedValue(new ApiHttpError(409, 'staff_occupancy_conflict', '月嫂檔期衝突，無法自動保留，請更換月嫂或調整服務日期。'));
    const onObserved = await open(); await openDates(); await saveDates();
    expect(await screen.findByText('月嫂檔期衝突，無法自動保留，請更換月嫂或調整服務日期。')).toBeInTheDocument();
    expect(screen.getByText(/願意代班/)).toBeInTheDocument();
    expect(screen.getByText(/已加入原案件群組/)).toBeInTheDocument();
    expect(screen.getByLabelText('實際服務開始日')).toBeEnabled();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(onObserved).not.toHaveBeenCalled(); expectNoUiMutation();
  });

  it('日期業務阻擋保留目前正式方案，不誤報推薦進度讀取失敗', async () => {
    vi.mocked(serviceStartClient.command).mockRejectedValue(new ApiHttpError(422, 'matching_schedule_confirmation_required_for_target_segments', '日期表與目前分段人選不同，請重新核對。'));
    await open(); await openDates(); await saveDates();
    expect(await screen.findByText('日期表與目前分段人選不同，請重新核對。')).toBeInTheDocument();
    expect(mocks.queryPlan).toHaveBeenCalledWith(CASE);
    expect(screen.getByRole('region', { name: `案件 ${CASE} 正式推薦媒合方案` })).toHaveTextContent('客戶已接受');
    expect(screen.queryByText('目前無法讀取推薦進度')).not.toBeInTheDocument(); expectNoUiMutation();
  });

  it('缺少服務日期時保留可執行的日期確認導引，查詢不建立檔期鎖', async () => {
    vi.mocked(serviceStartClient.todos).mockResolvedValue({ items: [{ ...startTodo(), proposed_start_date: null, requested_start_date: null }], total: 1, page: 1, page_size: 25 });
    const onObserved = await open();
    const navigation = screen.getByRole('button', { name: '前往確認服務日期' });
    expect(screen.getByText('配對及服務日期確認後，系統會自動保留月嫂檔期，不需另行操作。')).toBeInTheDocument();
    fireEvent.click(navigation);
    expect(await screen.findByRole('button', { name: '儲存並更新排班' })).toBeDisabled();
    expect(serviceStartClient.todos).toHaveBeenCalledWith(1, CASE);
    expect(serviceStartClient.command).not.toHaveBeenCalled();
    expect(onObserved).not.toHaveBeenCalled(); expectNoUiMutation();
  });

  it('pending 方案仍可 Query，但不提供鎖 Preview 或 Apply', async () => {
    accepted = false; await open();
    expect(mocks.queryPlan).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '預覽方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(serviceArrangementStatusClient.arrangement).not.toHaveBeenCalled(); expectNoUiMutation();
  });

  it('重新開頁已有鎖時呈現自動保留狀態，不重新建立', async () => {
    lockId = 88; await open();
    expect(screen.getByRole('heading', { name: '推薦已確認・檔期已自動保留' })).toBeInTheDocument();
    expect(mocks.queryPlan).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '預覽方案 51 等待訂金鎖' })).not.toBeInTheDocument(); expectNoUiMutation();
  });

  it.each([{ case_no: CASE, plan_id: 52 }, { case_no: 'OTHER-CASE', plan_id: 51 }])('自動狀態 case／plan identity 不一致時停止，不套用其他方案：%j', async identity => {
    vi.mocked(serviceArrangementStatusClient.arrangement).mockRestore();
    vi.spyOn(transport, 'get').mockResolvedValue({ success: true, message: 'ok', error: null, data: { ...identity, state: 'effective', blockers: [], job_id: 'unrelated-job', assignment_count: 1 } });
    const onObserved = await open();
    await expect(serviceArrangementStatusClient.arrangement(CASE, 51)).rejects.toThrow(identity.plan_id === 52 ? '自動排班狀態方案不一致。' : '服務安排狀態案件不一致。');
    expect(mocks.assignment).not.toHaveBeenCalled(); expect(onObserved).not.toHaveBeenCalled(); expectNoUiMutation();
  });

  it.each([{ case_no: CASE, assignments: [] }, { case_no: 'OTHER-CASE', assignments: [{ staff_id: 8892 }] }])('自動工作宣稱完成但 owner 回讀不一致，不報成功、不通知父頁或重送：%j', async readback => {
    mocks.assignment.mockResolvedValue(readback);
    const onObserved = await open(); await openDates(); await saveDates();
    expect(await screen.findByRole('alert')).toHaveTextContent('排班結果尚未完成正式回讀。');
    expect(onObserved).not.toHaveBeenCalled();
    expect(screen.queryByText('正式排班已完成')).not.toBeInTheDocument();
    expect(screen.queryByText('排班已完成並回讀一致。')).not.toBeInTheDocument();
    expect(screen.queryByText('排班已生效，月嫂預留檔期已轉為正式班表。')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '已轉為正式班表' })).not.toBeInTheDocument();
    expect(mocks.assignment).toHaveBeenCalledTimes(1);
    expect(serviceStartClient.command).toHaveBeenCalledTimes(1); expectNoUiMutation();
  });
});
