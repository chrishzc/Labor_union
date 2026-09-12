import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import type { FormalPlanContactState } from '../../../../../../../api/scheduling/matching_plan_communication_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const mocks = vi.hoisted(() => ({
  query: vi.fn(), createSingleCaregiverPlan: vi.fn(), queryMatchingPlanReceipt: vi.fn(), queryContactState: vi.fn(),
  recordCustomerDecision: vi.fn(), queryPlan: vi.fn(), getDetail: vi.fn(),
  sendCustomerConfirmation: vi.fn(), previewCustomerConfirmation: vi.fn(), recordFormalPlanWillingness: vi.fn(),
}));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { query: mocks.query } }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', () => ({ matchingCandidateWorkflowClient: {
  createSingleCaregiverPlan: mocks.createSingleCaregiverPlan, queryMatchingPlanReceipt: mocks.queryMatchingPlanReceipt,
} }));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: {
  queryContactState: mocks.queryContactState, recordCustomerDecision: mocks.recordCustomerDecision,
  sendCustomerConfirmation: mocks.sendCustomerConfirmation, previewCustomerConfirmation: mocks.previewCustomerConfirmation,
  recordFormalPlanWillingness: mocks.recordFormalPlanWillingness,
} }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.queryPlan } }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.getDetail } }));

const CASE = '115000285';
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
function plan(command?: { caseNo: string; actor: string; asOf: string; key: string; segments?: Array<{ staff_id: number; start_date: string; end_date: string }> }) {
  const segments = command?.segments ?? [{ staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }];
  return { plan_id: 51, case_no: command?.caseNo ?? CASE, version: 1, status: 'proposed', result: 'created',
    actor: command?.actor ?? 'operator-1', as_of: command?.asOf ?? '2026-09-12', event_key: command?.key ?? 'formal-plan-test-key',
    command_fingerprint: 'a'.repeat(64), replayed: false,
    segments: segments.map((segment, index) => ({
      segment_order: index + 1, staff_id: segment.staff_id,
      assigned_start_date: segment.start_date, assigned_end_date: segment.end_date,
    })) };
}
let exists: boolean;
let contact: FormalPlanContactState;
let activeLockId: number | null;
function activePlan() {
  return { planId: 51, status: contact.plan.status, activeLockId, planVersion: 1,
    segments: contact.segments.map((segment, index) => ({ segmentId: segment.segment_id, sequence: index + 1,
      staffId: 8892 + index, assignedStartDate: '2026-09-01', assignedEndDate: '2026-09-05' })) };
}
async function openCandidatePicker() {
  const summary = await screen.findByText(/^(選擇推薦月嫂|更換推薦人選)$/);
  const picker = summary.closest('details');
  if (picker && !picker.open) fireEvent.click(summary);
}
async function loadCandidates() {
  await openCandidatePicker();
  fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
  await screen.findByText('月嫂甲 · 月嫂 #8892');
}
async function createFormalPlan() {
  await loadCandidates();
  const button = screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await screen.findByText('正式媒合方案已建立：#51');
}
async function openExisting(onObserved = vi.fn()) {
  exists = true;
  render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={onObserved} />);
  await screen.findByText('目前正式媒合方案：#51');
  return onObserved;
}

describe('待辦看板 Beta 正式方案建立與既有方案續辦', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
    exists = false; contact = contactState(); activeLockId = null;
    mocks.query.mockResolvedValue(pool());
    mocks.getDetail.mockResolvedValue({ case_no: CASE, order_status: '訂單成立' });
    mocks.queryPlan.mockImplementation(async () => {
      if (!exists) throw new ApiHttpError(404, 'not_found', 'no active plan');
      return activePlan();
    });
    mocks.queryContactState.mockImplementation(async () => structuredClone(contact));
    mocks.previewCustomerConfirmation.mockImplementation(async (_caseNo, _planId, expectedVersion) => ({
      case_no: CASE, plan_id: 51, expected_version: expectedVersion,
      order_information_1_ready: true, order_information_2_ready: true,
      weekly_service_ready: true, weekly_service_row_count: 1,
      caregiver_resumes: [{ staff_id: 8892, staff_name: '月嫂甲', ready: true, filename: 'resume-A.pdf', version: 3, blocker: null }],
      blockers: [], send_allowed: true,
    }));
    mocks.createSingleCaregiverPlan.mockImplementation(async (command) => { exists = true; return plan(command); });
    mocks.recordCustomerDecision.mockImplementation(async (_caseNo, _planId, _version, decision) => {
      contact = { ...contact, customer_decision: decision, plan: { ...contact.plan,
        communication_version: 5, status: decision === 'accepted' ? 'accepted' : 'proposed' } };
      return { event_id: 91, case_no: CASE, plan_id: 51, segment_id: null, event_key: 'test-decision-key', communication_version: 5, source: 'admin', willingness: null, customer_decision: decision };
    });
    mocks.sendCustomerConfirmation.mockImplementation(async () => {
      contact = { ...contact, customer_profiles_status: 'pending', plan: { ...contact.plan, communication_version: 5 } };
      return { intent_id: 81, line_delivery_task_id: null, delivery_status: 'pending', notification_kind: 'customer_profiles' };
    });
  });

  it('在目前 proposed 方案保留國定假日雙方協調入口', async () => {
    await openExisting();
    const more = screen.getByText('其他處理').closest('details');
    expect(more).not.toHaveAttribute('open');
    expect(screen.getByText('國定假日上班雙方協調')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查國定假日上班協議' })).toBeInTheDocument();
  });

  it('只让 active 且 willing 候選建立既有正式方案，並以 active-plan 與 contact-state 回讀', async () => {
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await loadCandidates();
    expect(screen.getAllByText('目前不可選擇')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: '以 月嫂乙 建立正式媒合方案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '以 月嫂丙 建立正式媒合方案' })).not.toBeInTheDocument();
    const create = screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' });
    await waitFor(() => expect(create).toBeEnabled());
    fireEvent.click(create);
    await screen.findByText('正式媒合方案已建立：#51');
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledWith(expect.objectContaining({
      caseNo: CASE, actor: 'operator-1', segments: [{ staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' }],
      asOf: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), key: expect.stringMatching(/^orders-single-plan-/),
    }));
    expect(mocks.queryContactState).toHaveBeenCalledWith(CASE, 51);
    expect(screen.getAllByText('確認資訊已送達').length).toBeGreaterThan(0);
    expect(screen.queryByText('manually_confirmed')).not.toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledTimes(1);
  });

  it('將 Stage 5 current willing candidate 的 server dates 原樣交給正式方案 client', async () => {
    const candidate = {
      ...pool().candidates[0],
      staff_id: 1,
      service_start_date: '2026-12-01',
      service_end_date: '2026-12-20',
    };
    mocks.query.mockResolvedValue({ pool_id: 9, case_no: CASE, candidates: [candidate] });

    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await openCandidatePicker();
    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
    const create = await screen.findByRole('button', { name: '以 月嫂甲 建立正式媒合方案' });
    await waitFor(() => expect(create).toBeEnabled());
    fireEvent.click(create);

    await waitFor(() => expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledWith(expect.objectContaining({
      caseNo: CASE,
      segments: [{ staff_id: 1, start_date: '2026-12-01', end_date: '2026-12-20' }],
    })));
  });

  it.each(['accepted', 'declined'] as const)('以目前 communication version 記錄客戶 %s，之後正式回讀及通知父頁', async (decision) => {
    const onObserved = vi.fn();
    render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={onObserved} />);
    await createFormalPlan();
    onObserved.mockClear();
    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), { target: { value: '電話核對正式推薦。' } });
    fireEvent.click(screen.getByRole('button', { name: decision === 'accepted' ? '記錄方案 51 客戶接受' : '記錄方案 51 客戶拒絕' }));
    await waitFor(() => expect(screen.getAllByText(decision === 'accepted' ? '客戶已接受' : '客戶已拒絕').length).toBeGreaterThan(0));
    expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(
      CASE, 51, 4, decision, '電話核對正式推薦。', expect.stringMatching(/^orders-formal-manual-customer-decision-51-/), 'operator-1',
    );
    expect(mocks.queryContactState).toHaveBeenCalledTimes(3);
    expect(onObserved).toHaveBeenCalledTimes(1);
    if (decision === 'declined') expect(screen.getByText('客戶拒絕正式推薦')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '記錄方案 51 客戶接受' })).not.toBeInTheDocument();
  });

  it('電話已談妥時不要求先寄送客戶確認資訊，仍可用既有人工入口記錄接受', async () => {
    contact.customer_profiles_status = null;
    await openExisting();

    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), {
      target: { value: '電話已確認客戶接受此人選。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄方案 51 客戶接受' }));

    await waitFor(() => expect(screen.getAllByText('客戶已接受').length).toBeGreaterThan(0));
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
    expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(
      CASE, 51, 4, 'accepted', '電話已確認客戶接受此人選。',
      expect.stringMatching(/^orders-formal-manual-customer-decision-51-/), 'operator-1',
    );
  });

  it('沒有既有方案且候選 query 不可用時，不建立方案或記錄決策', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await openCandidatePicker();
    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
    await screen.findByText('candidate pool unavailable');
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(mocks.queryContactState).not.toHaveBeenCalled();
    expect(mocks.recordCustomerDecision).not.toHaveBeenCalled();
  });

  it('重新開頁直接續辦既有方案並發送確認資訊，不建立替代方案或冒充 LINE 送達', async () => {
    contact.customer_profiles_status = null;
    const onObserved = await openExisting();
    await screen.findByText('四項確認資訊均已就緒，可以一次寄送。');
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '請核對完整確認資訊。' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送確認資訊給客戶' }));
    await screen.findByText('確認資訊發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');
    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledWith(
      CASE, 51, 4, '請核對完整確認資訊。', expect.stringMatching(/^orders-customer-confirmation-51-/),
    );
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
  });

  it('既有方案不依賴候選池成功，候選池失敗仍可讀取正式方案', async () => {
    await openExisting();
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    await openCandidatePicker();
    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
    await screen.findByText('candidate pool unavailable');
    expect(screen.getByText('目前正式媒合方案：#51')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '記錄方案 51 客戶接受' })).toBeInTheDocument();
  });

  it.each(['accepted', 'locked'] as const)('既有 %s 方案不可重新建立或發送確認資訊', async (state) => {
    if (state === 'accepted') { contact.customer_decision = 'accepted'; contact.plan.status = 'accepted'; }
    else activeLockId = 88;
    await openExisting();
    await loadCandidates();
    expect(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
  });

  it('active-plan 403 不當成沒有方案，不容許新建', async () => {
    mocks.queryPlan.mockRejectedValue(new ApiHttpError(403, 'forbidden', '無讀取權限'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await screen.findByText('目前無法讀取推薦進度');
    expect(screen.getByText('無讀取權限')).toBeInTheDocument();
    expect(screen.queryByText('選擇推薦月嫂')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '以 月嫂甲 建立正式媒合方案' })).not.toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
  });

  it('送出前版本已變更時停止，不用新版本偷換使用者已確認的方案', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對履歷' } });
    contact.plan.communication_version = 6;
    fireEvent.click(screen.getByRole('button', { name: '寄送確認資訊給客戶' }));
    await screen.findByText('正式方案版本已變更，請重新讀取後確認。');
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });

  it('active plan 在送出前換案時停止，不對其他方案發送', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    mocks.queryPlan.mockResolvedValue({ ...activePlan(), planId: 52 });
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對履歷' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送確認資訊給客戶' }));
    await screen.findByText('目前有效方案已變更，請重新載入；不對其他方案執行操作。');
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });

  it('receipt 回來但 owner 未觀察到發送時不報成功或通知父頁，也不重送', async () => {
    contact.customer_profiles_status = null;
    mocks.sendCustomerConfirmation.mockResolvedValue({ intent_id: 81, delivery_status: 'pending' });
    const onObserved = await openExisting();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對履歷' } });
    fireEvent.click(screen.getByRole('button', { name: '寄送確認資訊給客戶' }));
    await screen.findByText('操作後正式方案回讀尚未確認預期結果，請重新讀取；不重送操作。');
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledTimes(1);
  });

  it('寄送結果不確定後由人員重試時沿用同一操作識別', async () => {
    contact.customer_profiles_status = null;
    mocks.sendCustomerConfirmation.mockRejectedValueOnce(new Error('連線中斷，結果尚未確認。'));
    await openExisting();
    await screen.findByText('四項確認資訊均已就緒，可以一次寄送。');
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對完整確認資訊' } });

    const send = screen.getByRole('button', { name: '寄送確認資訊給客戶' });
    fireEvent.click(send);
    await screen.findByText('連線中斷，結果尚未確認。');
    fireEvent.click(screen.getByRole('button', { name: '再試一次' }));
    await screen.findByText('四項確認資訊均已就緒，可以一次寄送。');
    fireEvent.click(screen.getByRole('button', { name: '寄送確認資訊給客戶' }));
    await screen.findByText('確認資訊發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');

    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledTimes(2);
    expect(mocks.sendCustomerConfirmation.mock.calls[1][4]).toBe(
      mocks.sendCustomerConfirmation.mock.calls[0][4],
    );
  });

  it('多段方案逐段補登意願，保留同一 plan 並以更新後 version 續辦', async () => {
    contact = { ...contact, all_willing: false, segments: [{ segment_id: 71, willingness: 'willing' }, { segment_id: 72, willingness: 'pending' }] };
    mocks.recordFormalPlanWillingness.mockImplementation(async (_caseNo, _planId, segmentId, _version, _reason, eventKey) => {
      contact = { ...contact, all_willing: true, plan: { ...contact.plan, communication_version: 5 },
        segments: contact.segments.map((segment) => ({ ...segment, willingness: 'willing' })) };
      return {
        event_id: 92, case_no: CASE, plan_id: 51, segment_id: segmentId,
        event_key: eventKey, communication_version: 5, source: 'admin',
        willingness: 'willing', customer_decision: null,
      };
    });
    const onObserved = await openExisting();
    expect(screen.queryByRole('button', { name: '記錄方案 51 客戶接受' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('方案 51 月嫂意願確認依據'), { target: { value: '第二段月嫂電話確認。' } });
    fireEvent.click(screen.getByRole('button', { name: '確認月嫂 #8893 願意承接' }));
    await screen.findByText('正式方案月嫂意願已回讀確認。');
    expect(mocks.recordFormalPlanWillingness).toHaveBeenCalledWith(
      CASE, 51, 72, 4, '第二段月嫂電話確認。',
      expect.stringMatching(/^orders-formal-manual-willingness-51-72-/), 'operator-1',
    );
    expect(screen.getByRole('button', { name: '記錄方案 51 客戶接受' })).toBeDisabled();
    expect(screen.getByLabelText('方案 51 客戶決策依據')).toHaveValue('');
    expect(onObserved).toHaveBeenCalledTimes(1);
  });

  it('將正常續辦集中為單一主要動作，例外處理與更換人選預設收合', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    await waitFor(() => expect(screen.getByRole('button', { name: '寄送確認資訊給客戶' })).toBeEnabled());
    expect(screen.getByLabelText('方案 51 確認資訊備註')).toHaveValue('請查收正式推薦月嫂的完整確認資訊。');
    expect(screen.getByRole('list', { name: '本次確認資訊內容' })).toHaveTextContent('resume-A.pdf（版本 3）');
    expect(screen.getByText('其他處理').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByText('更換推薦人選').closest('details')).not.toHaveAttribute('open');
    expect(screen.queryByText(/^pending$/)).not.toBeInTheDocument();
  });

  it('缺任一月嫂履歷時直接顯示 blocker 並禁止寄送', async () => {
    contact.customer_profiles_status = null;
    mocks.previewCustomerConfirmation.mockResolvedValue({
      case_no: CASE, plan_id: 51, expected_version: 4,
      order_information_1_ready: true, order_information_2_ready: true,
      weekly_service_ready: true, weekly_service_row_count: 1,
      caregiver_resumes: [{
        staff_id: 8892, staff_name: '月嫂甲', ready: false, filename: null, version: null,
        blocker: '月嫂 月嫂甲 尚未上傳履歷 PDF，請先至人員管理完成履歷上傳。',
      }],
      blockers: ['月嫂 月嫂甲 尚未上傳履歷 PDF，請先至人員管理完成履歷上傳。'],
      send_allowed: false,
    });

    await openExisting();

    expect(await screen.findByText('月嫂 月嫂甲 尚未上傳履歷 PDF，請先至人員管理完成履歷上傳。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '寄送確認資訊給客戶' })).toBeDisabled();
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });
});
