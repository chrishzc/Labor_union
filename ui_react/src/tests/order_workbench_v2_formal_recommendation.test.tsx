import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';
import { ApiHttpError } from '../api/shared/typed_errors';
import type { FormalPlanContactState } from '../api/scheduling/matching_plan_communication_client';

const mocks = vi.hoisted(() => ({
  query: vi.fn(), createSingleCaregiverPlan: vi.fn(), queryContactState: vi.fn(),
  recordCustomerDecision: vi.fn(), queryPlan: vi.fn(), getDetail: vi.fn(),
  sendCustomerProfiles: vi.fn(), recordFormalPlanWillingness: vi.fn(),
}));
vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { query: mocks.query } }));
vi.mock('../api/scheduling/matching_candidate_workflow_client', () => ({ matchingCandidateWorkflowClient: { createSingleCaregiverPlan: mocks.createSingleCaregiverPlan } }));
vi.mock('../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: {
  queryContactState: mocks.queryContactState, recordCustomerDecision: mocks.recordCustomerDecision,
  sendCustomerProfiles: mocks.sendCustomerProfiles, recordFormalPlanWillingness: mocks.recordFormalPlanWillingness,
} }));
vi.mock('../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.queryPlan } }));
vi.mock('../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.getDetail } }));

const CASE = 'CASE-RECOMMEND';
function pool() {
  return { pool_id: 9, case_no: CASE, candidates: [
    { id: 17, staff_id: 8892, staff_name: '月嫂甲', status: 'active', willingness: 'willing' },
    { id: 18, staff_id: 8893, staff_name: '月嫂乙', status: 'active', willingness: 'unwilling' },
    { id: 19, staff_id: 8894, staff_name: '月嫂丙', status: 'withdrawn', willingness: 'willing' },
  ].map((candidate) => ({ ...candidate, service_start_date: '2026-09-01', service_end_date: '2026-09-05',
    created_at: '2026-09-03T00:00:00Z', reason: null, information: { '1': null, '2': null } })) };
}
function contactState(): FormalPlanContactState {
  return { plan: { id: 51, case_no: CASE, communication_version: 4, status: 'proposed', is_active: 1 },
    segments: [{ segment_id: 71, willingness: 'willing' }], all_willing: true,
    customer_decision: 'pending', customer_profiles_status: 'manually_confirmed', customer_profiles_manual_confirmation: null };
}
function plan() {
  return { plan_id: 51, case_no: CASE, version: 1, status: 'proposed', result: 'created',
    segments: [{ segment_order: 1, staff_id: 8892, assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-05' }] };
}
let exists: boolean;
let contact: FormalPlanContactState;
let activeLockId: number | null;
function activePlan() {
  return { planId: 51, status: contact.plan.status, activeLockId, communicationVersion: contact.plan.communication_version,
    segments: contact.segments.map((segment, index) => ({ segmentId: segment.segment_id, sequence: index + 1,
      staffId: 8892 + index, assignedStartDate: '2026-09-01', assignedEndDate: '2026-09-05' })) };
}
async function loadCandidates() {
  fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
  await screen.findByText('月嫂甲 · 月嫂 #8892');
}
async function createFormalPlan() {
  await loadCandidates();
  const button = screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await screen.findByText('正式媒合方案已建立：#51 · created');
}
async function openExisting(onObserved = vi.fn()) {
  exists = true;
  render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={onObserved} />);
  await screen.findByText('目前正式媒合方案：#51');
  return onObserved;
}

describe('待辦看板 Beta 正式方案建立與既有方案續辦', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    exists = false; contact = contactState(); activeLockId = null;
    mocks.query.mockResolvedValue(pool());
    mocks.getDetail.mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
    mocks.queryPlan.mockImplementation(async () => {
      if (!exists) throw new ApiHttpError(404, 'not_found', 'no active plan');
      return activePlan();
    });
    mocks.queryContactState.mockImplementation(async () => structuredClone(contact));
    mocks.createSingleCaregiverPlan.mockImplementation(async () => { exists = true; return plan(); });
    mocks.recordCustomerDecision.mockImplementation(async (_caseNo, _planId, _version, decision) => {
      contact = { ...contact, customer_decision: decision, plan: { ...contact.plan,
        communication_version: 5, status: decision === 'accepted' ? 'accepted' : 'proposed' } };
      return { event_id: 91, communication_version: 5, source: 'manual', willingness: null, customer_decision: decision };
    });
    mocks.sendCustomerProfiles.mockImplementation(async () => {
      contact = { ...contact, customer_profiles_status: 'pending', plan: { ...contact.plan, communication_version: 5 } };
      return { intent_id: 81, line_delivery_task_id: null, delivery_status: 'pending', notification_kind: 'customer_profiles' };
    });
  });

  it('只让 active 且 willing 候選建立既有正式方案，並以 active-plan 與 contact-state 回讀', async () => {
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await loadCandidates();
    expect(screen.getAllByText(/不可建立方案/)).toHaveLength(2);
    expect(screen.queryByRole('button', { name: '以 月嫂乙 建立正式媒合方案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '以 月嫂丙 建立正式媒合方案' })).not.toBeInTheDocument();
    const create = screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' });
    await waitFor(() => expect(create).toBeEnabled());
    fireEvent.click(create);
    await screen.findByText('正式媒合方案已建立：#51 · created');
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledWith(CASE, { staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' });
    expect(mocks.queryContactState).toHaveBeenCalledWith(CASE, 51);
    expect(screen.getByText('manually_confirmed')).toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledTimes(1);
  });

  it.each(['accepted', 'declined'] as const)('以目前 communication version 記錄客戶 %s，之後正式回讀及通知父頁', async (decision) => {
    const onObserved = vi.fn();
    render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={onObserved} />);
    await createFormalPlan();
    onObserved.mockClear();
    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), { target: { value: '電話核對正式推薦。' } });
    fireEvent.click(screen.getByRole('button', { name: decision === 'accepted' ? '記錄方案 51 客戶接受' : '記錄方案 51 客戶拒絕' }));
    await screen.findByText(`目前決定：${decision}`);
    expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(CASE, 51, 4, decision, '電話核對正式推薦。');
    expect(mocks.queryContactState).toHaveBeenCalledTimes(3);
    expect(onObserved).toHaveBeenCalledTimes(1);
    if (decision === 'declined') expect(screen.getByText('客戶拒絕正式推薦')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '記錄方案 51 客戶接受' })).not.toBeInTheDocument();
  });

  it('沒有既有方案且候選 query 不可用時，不建立方案或記錄決策', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
    await screen.findByText('candidate pool unavailable');
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(mocks.queryContactState).not.toHaveBeenCalled();
    expect(mocks.recordCustomerDecision).not.toHaveBeenCalled();
  });

  it('重新開頁直接續辦既有方案並發送履歷，不建立替代方案或冒充 LINE 送達', async () => {
    contact.customer_profiles_status = null;
    const onObserved = await openExisting();
    fireEvent.change(screen.getByLabelText('方案 51 履歷傳送備註'), { target: { value: '請核對兩份正式履歷。' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送月嫂履歷給客戶' }));
    await screen.findByText('履歷發送工作已建立：#81（pending）；尚不代表 LINE 已送達。');
    expect(mocks.sendCustomerProfiles).toHaveBeenCalledWith(CASE, 51, 4, '請核對兩份正式履歷。');
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '寄送月嫂履歷給客戶' })).not.toBeInTheDocument();
  });

  it('既有方案不依賴候選池成功，候選池失敗仍可讀取正式方案', async () => {
    await openExisting();
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
    await screen.findByText('candidate pool unavailable');
    expect(screen.getByText('目前正式媒合方案：#51')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '記錄方案 51 客戶接受' })).toBeInTheDocument();
  });

  it.each(['accepted', 'locked'] as const)('既有 %s 方案不可重新建立或發送履歷', async (state) => {
    if (state === 'accepted') { contact.customer_decision = 'accepted'; contact.plan.status = 'accepted'; }
    else activeLockId = 88;
    await openExisting();
    await loadCandidates();
    expect(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '寄送月嫂履歷給客戶' })).not.toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
  });

  it('active-plan 403 不當成沒有方案，不容許新建', async () => {
    mocks.queryPlan.mockRejectedValue(new ApiHttpError(403, 'forbidden', '無讀取權限'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await screen.findByText('目前正式方案不可用：無讀取權限');
    await loadCandidates();
    expect(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' })).toBeDisabled();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
  });

  it('送出前版本已變更時停止，不用新版本偷換使用者已確認的方案', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    fireEvent.change(screen.getByLabelText('方案 51 履歷傳送備註'), { target: { value: '核對履歷' } });
    contact.plan.communication_version = 6;
    fireEvent.click(screen.getByRole('button', { name: '寄送月嫂履歷給客戶' }));
    await screen.findByText('正式方案版本已變更，請重新讀取後確認。');
    expect(mocks.sendCustomerProfiles).not.toHaveBeenCalled();
  });

  it('active plan 在送出前換案時停止，不對其他方案發送', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    mocks.queryPlan.mockResolvedValue({ ...activePlan(), planId: 52 });
    fireEvent.change(screen.getByLabelText('方案 51 履歷傳送備註'), { target: { value: '核對履歷' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送月嫂履歷給客戶' }));
    await screen.findByText('目前有效方案已變更，請重新載入；不對其他方案執行操作。');
    expect(mocks.sendCustomerProfiles).not.toHaveBeenCalled();
  });

  it('receipt 回來但 owner 未觀察到發送時不報成功或通知父頁，也不重送', async () => {
    contact.customer_profiles_status = null;
    mocks.sendCustomerProfiles.mockResolvedValue({ intent_id: 81, delivery_status: 'pending' });
    const onObserved = await openExisting();
    fireEvent.change(screen.getByLabelText('方案 51 履歷傳送備註'), { target: { value: '核對履歷' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送月嫂履歷給客戶' }));
    await screen.findByText('操作後正式方案回讀尚未確認預期結果，請重新讀取；不重送操作。');
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.sendCustomerProfiles).toHaveBeenCalledTimes(1);
  });

  it('多段方案逐段補登意願，保留同一 plan 並以更新後 version 續辦', async () => {
    contact = { ...contact, all_willing: false, segments: [{ segment_id: 71, willingness: 'willing' }, { segment_id: 72, willingness: 'pending' }] };
    mocks.recordFormalPlanWillingness.mockImplementation(async () => {
      contact = { ...contact, all_willing: true, plan: { ...contact.plan, communication_version: 5 },
        segments: contact.segments.map((segment) => ({ ...segment, willingness: 'willing' })) };
    });
    const onObserved = await openExisting();
    expect(screen.getByRole('button', { name: '記錄方案 51 客戶接受' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), { target: { value: '第二段月嫂電話確認。' } });
    fireEvent.click(screen.getByRole('button', { name: '確認分段 72 月嫂願意承接' }));
    await screen.findByText('正式方案月嫂意願已回讀確認。');
    expect(mocks.recordFormalPlanWillingness).toHaveBeenCalledWith(CASE, 51, 72, 4, '第二段月嫂電話確認。');
    expect(screen.getByRole('button', { name: '記錄方案 51 客戶接受' })).toBeEnabled();
    expect(onObserved).toHaveBeenCalledTimes(1);
  });
});
