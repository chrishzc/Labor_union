/** Waiting-deposit lock guards and navigation to the case's service-date work area. */
import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';
import { serviceStartClient } from '../../../../../../../api/scheduling/service_start_client';
import { serviceArrangementStatusClient } from '../../../../../../../api/scheduling/service_arrangement_status_client';
import { assignmentPlanMutationClient } from '../../../../../../../api/scheduling/assignment_plan_mutation_client';
import { transport } from '../../../../../../../api/shared/transport';
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
  return <>
    <OrderFormalRecommendationPanel caseNo={CASE} assignmentExists={false} onObserved={onObserved} onOpenServiceDates={() => setDatesOpen(true)} />
    {datesOpen && <section aria-label="案件服務安排" />}
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
    vi.spyOn(serviceStartClient, 'todos');
    vi.spyOn(serviceStartClient, 'options').mockResolvedValue({ items: [] });
    vi.spyOn(serviceStartClient, 'command');
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

  it('客戶已接受時可前往本案服務安排，舊代班、手動鎖與班表 mutation 皆無呼叫', async () => {
    const onObserved = await open();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    await openDates();
    expect(screen.getByRole('region', { name: '案件服務安排' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '儲存班表' })).not.toBeInTheDocument();
    expect(serviceStartClient.todos).not.toHaveBeenCalled();
    expect(serviceStartClient.command).not.toHaveBeenCalled();
    expect(onObserved).not.toHaveBeenCalled();
    expectNoUiMutation();
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
});
