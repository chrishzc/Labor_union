import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import type { FormalPlanContactState } from '../../../../../../../api/scheduling/matching_plan_communication_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { OrderWorkbenchV2Drawer } from '../../../../../../../components/OrderWorkbenchV2Drawer';
import { CORE_STAGE_CODES, SUBSTATUS_BY_STAGE_STATUS } from '../../../../../../../api/orders/order_core_stage_projection_schemas';

const mocks = vi.hoisted(() => ({
  query: vi.fn(), createSingleCaregiverPlan: vi.fn(), queryMatchingPlanReceipt: vi.fn(), queryContactState: vi.fn(),
  recordCustomerDecision: vi.fn(), queryPlan: vi.fn(), getDetail: vi.fn(), getAssignmentPlan: vi.fn(),
  sendCustomerConfirmation: vi.fn(), previewCustomerConfirmation: vi.fn(), recordFormalPlanWillingness: vi.fn(),
  coreTimelines: vi.fn(), getTerms: vi.fn(), replacementQuery: vi.fn(), replacementPreview: vi.fn(), replacementApply: vi.fn(),
}));
vi.mock('../../../../../../../api/orders/order_core_stage_projection_client', () => ({ orderCoreStageProjectionClient: { getCoreStageTimelines: mocks.coreTimelines } }));
vi.mock('../../../../../../../components/OrderServiceDatesPanel', () => ({ OrderServiceDatesPanel: () => <p>服務日期工作區</p> }));
vi.mock('../../../../../../../components/OrderAssignmentPlanPanel', () => ({ OrderAssignmentPlanPanel: () => <p>排班工作區</p> }));
vi.mock('../../../../../../../components/ContractExternalSigningActions', () => ({ ContractExternalSigningActions: () => <p>契約工作區</p> }));
vi.mock('../../../../../../../api/orders/service_before_replacement_client', async importOriginal => ({
  ...await importOriginal<typeof import('../../../../../../../api/orders/service_before_replacement_client')>(),
  serviceBeforeReplacementClient: { query: mocks.replacementQuery, preview: mocks.replacementPreview, apply: mocks.replacementApply },
}));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { query: mocks.query } }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', async importOriginal => ({
  ...await importOriginal<typeof import('../../../../../../../api/scheduling/matching_candidate_workflow_client')>(), matchingCandidateWorkflowClient: {
  createSingleCaregiverPlan: mocks.createSingleCaregiverPlan, queryMatchingPlanReceipt: mocks.queryMatchingPlanReceipt,
} }));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: {
  queryContactState: mocks.queryContactState, recordCustomerDecision: mocks.recordCustomerDecision,
  sendCustomerConfirmation: mocks.sendCustomerConfirmation, previewCustomerConfirmation: mocks.previewCustomerConfirmation,
  recordFormalPlanWillingness: mocks.recordFormalPlanWillingness,
} }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.queryPlan } }));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getOrderDetail: mocks.getDetail, getAssignmentPlan: mocks.getAssignmentPlan, getOrderTerms: mocks.getTerms } }));

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
  await screen.findByRole('heading', { name: '選定推薦月嫂' });
}
async function loadCandidates() {
  await openCandidatePicker();
  await screen.findByText('未設定 月嫂甲');
}
async function openSending() {
  const send = await screen.findByRole('button', { name: '寄送確認資訊給客戶' });
  await waitFor(() => expect(send).toBeEnabled());
  if (!screen.queryByRole('button', { name: '確認寄送' })) fireEvent.click(send);
}
async function openManual() {
  if (!screen.queryByLabelText('方案 51 客戶決策依據')) fireEvent.click(await screen.findByRole('button', { name: '手動記錄客戶決定' }));
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
  await screen.findByRole('heading', { name: /^推薦方案/ });
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
    mocks.getAssignmentPlan.mockResolvedValue({ service_started: false, assignments: [] });
    mocks.queryPlan.mockImplementation(async () => {
      if (!exists) throw new ApiHttpError(404, 'not_found', 'no active plan');
      return activePlan();
    });
    mocks.queryContactState.mockImplementation(async () => structuredClone(contact));
    mocks.previewCustomerConfirmation.mockImplementation(async (_caseNo, _planId, expectedVersion) => ({
      case_no: CASE, plan_id: 51, expected_version: expectedVersion,
      order_information_1_ready: true, order_information_2_ready: true,
      weekly_service_ready: true, weekly_service_row_count: 1,
      order_information_1: [{ segment_id: 71, staff_id: 8892, staff_name: '月嫂甲', text: '訂單資訊－1\n總薪資：預估 48000 元' }],
      order_information_2: [{ segment_id: 71, staff_id: 8892, staff_name: '月嫂甲', text: '訂單資訊－2\n飲食習慣：清淡' }],
      weekly_service_rows: [{ serial_number: 1, staff_name: '月嫂甲', week_start_date: '2026-09-01', week_end_date: '2026-09-07', service_hours_per_day: 8, weekly_work_days: 5, weekly_hours: 40 }],
      caregiver_resumes: [{ staff_id: 8892, staff_name: '月嫂甲', ready: true, filename: 'resume-A.pdf', version: 3, blocker: null }],
      blockers: [], send_allowed: true,
    }));
    mocks.createSingleCaregiverPlan.mockImplementation(async (command) => { exists = true; return plan(command); });
    mocks.recordCustomerDecision.mockImplementation(async (_caseNo, _planId, _version, decision) => {
      contact = { ...contact, customer_decision: decision, plan: { ...contact.plan,
        communication_version: 5, status: decision === 'accepted' ? 'accepted' : 'proposed' } };
      return { event_id: 91, case_no: CASE, plan_id: 51, segment_id: null, event_key: 'test-decision-key', communication_version: 5, source: 'admin', willingness: null, customer_decision: decision };
    });
    mocks.recordFormalPlanWillingness.mockImplementation(async (caseNo, planId, segmentId, version, reason, eventKey, actor, willingness) => {
      const segments = contact.segments.map(segment => segment.segment_id === segmentId ? { ...segment, willingness } : segment);
      contact = { ...contact, segments, all_willing: segments.every(segment => segment.willingness === 'willing'),
        plan: { ...contact.plan, communication_version: version + 1 } };
      return { event_id: 92, case_no: caseNo, plan_id: planId, segment_id: segmentId, event_key: eventKey,
        communication_version: version + 1, source: 'admin', willingness, customer_decision: null, reason, actor };
    });
    mocks.sendCustomerConfirmation.mockImplementation(async (_caseNo, _planId, version) => {
      contact = { ...contact, customer_profiles_status: 'pending', plan: { ...contact.plan, communication_version: version + 1 } };
      return { intent_id: 81, line_delivery_task_id: null, delivery_status: 'pending', notification_kind: 'customer_profiles' };
    });
  });

  it.each([409, 422])('建立方案明確拒絕 %s 時顯示原因並保留修正入口，不鎖成結果未明', async status => {
    mocks.createSingleCaregiverPlan.mockRejectedValue(new ApiHttpError(status, 'matching_candidate_no_longer_available', '候選月嫂或檔期已變更，請重新選擇。'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} onOpenCandidates={vi.fn()} />);
    await loadCandidates();
    fireEvent.click(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('候選月嫂或檔期已變更，請重新選擇。');
    expect(screen.getByRole('button', { name: '返回尋找人選' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: '確認建立結果' })).not.toBeInTheDocument();
    expect(orderMutationFlowStore.getFormalPlanCreation(CASE, 'single')).toBeUndefined();
  });

  it('原建立結果未明且收據查詢遭拒時，保留原操作並就地顯示原因', async () => {
    mocks.createSingleCaregiverPlan.mockRejectedValue(new Error('網路中斷，建立結果待核對。'));
    mocks.queryMatchingPlanReceipt.mockRejectedValue(new ApiHttpError(403, 'forbidden', '目前無權查詢原操作結果。'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await loadCandidates();
    fireEvent.click(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' }));
    const confirm = await screen.findByRole('button', { name: '確認建立結果' });
    expect(screen.getByText('原因：網路中斷，建立結果待核對。')).toBeVisible();
    const original = orderMutationFlowStore.getFormalPlanCreation(CASE, 'single')!.command;
    fireEvent.click(confirm);
    expect(await screen.findByText('原因：目前無權查詢原操作結果。')).toBeVisible();
    expect(orderMutationFlowStore.getFormalPlanCreation(CASE, 'single')).toMatchObject({ status: 'outcome_unknown', command: original });
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledTimes(1);
  });

  it('確認原命令未保存後重試遭明確拒絕，解除鎖定並顯示修正原因', async () => {
    mocks.createSingleCaregiverPlan.mockRejectedValueOnce(new Error('網路中斷'))
      .mockRejectedValueOnce(new ApiHttpError(409, 'matching_candidate_no_longer_available', '檔期已變更，請返回尋找人選。'));
    mocks.queryMatchingPlanReceipt.mockRejectedValue(new ApiHttpError(404, 'not_found', '原命令未保存'));
    render(<OrderFormalRecommendationPanel caseNo={CASE} onOpenCandidates={vi.fn()} />);
    await loadCandidates();
    fireEvent.click(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' }));
    fireEvent.click(await screen.findByRole('button', { name: '確認建立結果' }));
    expect(await screen.findByText('檔期已變更，請返回尋找人選。')).toBeVisible();
    expect(screen.getByRole('button', { name: '返回尋找人選' })).toBeEnabled();
    expect(orderMutationFlowStore.getFormalPlanCreation(CASE, 'single')).toBeUndefined();
    expect(mocks.createSingleCaregiverPlan.mock.calls[0][0]).toEqual(mocks.createSingleCaregiverPlan.mock.calls[1][0]);
  });

  it('不再顯示獨立的國定假日雙方協調入口', async () => {
    await openExisting();
    expect(screen.queryByText('國定假日上班雙方協調')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '檢查國定假日上班協議' })).not.toBeInTheDocument();
  });

  it('只让 active 且 willing 候選建立既有正式方案，並以 active-plan 與 contact-state 回讀', async () => {
    render(<OrderFormalRecommendationPanel caseNo={CASE} />);
    await loadCandidates();
    expect(screen.queryByText('月嫂乙')).not.toBeInTheDocument();
    expect(screen.queryByText('月嫂丙')).not.toBeInTheDocument();
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
    await openManual();
    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), { target: { value: '電話核對正式推薦。' } });
    fireEvent.click(screen.getByRole('button', { name: decision === 'accepted' ? '記錄方案 51 客戶接受' : '記錄方案 51 客戶拒絕' }));
    await waitFor(() => expect(screen.getAllByText(decision === 'accepted' ? '客戶已接受' : '客戶已拒絕').length).toBeGreaterThan(0));
    expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(
      CASE, 51, 4, decision, '電話核對正式推薦。', expect.stringMatching(/^orders-formal-manual-customer-decision-51-/), 'operator-1',
    );
    expect(mocks.queryContactState).toHaveBeenCalledTimes(3);
    expect(onObserved).toHaveBeenCalledTimes(1);
    if (decision === 'declined') expect(screen.getByText('客戶未接受本次推薦')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '記錄方案 51 客戶接受' })).not.toBeInTheDocument();
  });

  it('電話已談妥時不要求先寄送客戶確認資訊，仍可用既有人工入口記錄接受', async () => {
    contact.customer_profiles_status = null;
    await openExisting();

    await openManual();
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
    await screen.findByText('candidate pool unavailable');
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(mocks.queryContactState).not.toHaveBeenCalled();
    expect(mocks.recordCustomerDecision).not.toHaveBeenCalled();
  });

  it('重新開頁直接續辦既有方案並發送確認資訊，不建立替代方案或冒充 LINE 送達', async () => {
    contact.customer_profiles_status = null;
    const onObserved = await openExisting();
    await screen.findByRole('button', { name: '寄送確認資訊給客戶' });
    await openSending();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '請核對完整確認資訊。' } });
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('確認資訊發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');
    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledWith(
      CASE, 51, 4, '請核對完整確認資訊。', expect.stringMatching(/^orders-customer-confirmation-51-/),
    );
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
  });

  it('既有方案不重複載入候選池，仍可查看推薦及記錄客戶決定', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    await openExisting();
    expect(mocks.query).not.toHaveBeenCalled();
    await openManual();
    expect(screen.getByRole('button', { name: '記錄方案 51 客戶接受' })).toBeInTheDocument();
  });

  it.each(['accepted', 'locked'] as const)('既有 %s 方案不可重新建立或發送確認資訊', async (state) => {
    if (state === 'accepted') { contact.customer_decision = 'accepted'; contact.plan.status = 'accepted'; }
    else activeLockId = 88;
    await openExisting();
    expect(screen.queryByRole('button', { name: '以 月嫂甲 建立正式媒合方案' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '更換月嫂' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
  });

  it.each([null, 88])('已接受推薦以自動保留狀態取代手動上鎖，lock=%s', async lockId => {
    contact.customer_decision = 'accepted';
    activeLockId = lockId;
    await openExisting();
    expect(await screen.findByText(lockId === null ? '等待服務日期確認' : '推薦已確認・檔期已自動保留')).toBeVisible();
    expect(screen.queryByRole('button', { name: '確認保留檔期' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '檢查檔期' })).not.toBeInTheDocument();
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
    await openSending();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對履歷' } });
    contact.plan.communication_version = 6;
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('正式方案版本已變更，請重新讀取後確認。');
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });

  it('active plan 在送出前換案時停止，不對其他方案發送', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    mocks.queryPlan.mockResolvedValue({ ...activePlan(), planId: 52 });
    await openSending();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對履歷' } });
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('目前有效方案已變更，請重新載入；不對其他方案執行操作。');
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });

  it('receipt 回來但 owner 未觀察到發送時不報成功或通知父頁，也不重送', async () => {
    contact.customer_profiles_status = null;
    mocks.sendCustomerConfirmation.mockResolvedValue({ intent_id: 81, delivery_status: 'pending' });
    const onObserved = await openExisting();
    await openSending();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對履歷' } });
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('操作後正式方案回讀尚未確認預期結果，請重新讀取；不重送操作。');
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledTimes(1);
  });

  it('寄送結果不確定後由人員重試時沿用同一操作識別', async () => {
    contact.customer_profiles_status = null;
    mocks.sendCustomerConfirmation.mockRejectedValueOnce(new Error('連線中斷，結果尚未確認。'));
    await openExisting();
    await screen.findByRole('button', { name: '寄送確認資訊給客戶' });
    await openSending();
    fireEvent.change(screen.getByLabelText('方案 51 確認資訊備註'), { target: { value: '核對完整確認資訊' } });

    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('連線中斷，結果尚未確認。');
    fireEvent.click(screen.getByRole('button', { name: '再試一次' }));
    await screen.findByRole('button', { name: '寄送確認資訊給客戶' });
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('確認資訊發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');

    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledTimes(2);
    expect(mocks.sendCustomerConfirmation.mock.calls[1][4]).toBe(
      mocks.sendCustomerConfirmation.mock.calls[0][4],
    );
  });

  it('多段已同意人選不要求再次正式同意，未同意者則導回詢問而不冒充同意', async () => {
    contact = { ...contact, all_willing: false, segments: [{ segment_id: 71, willingness: 'willing' }, { segment_id: 72, willingness: 'pending' }] };
    await openExisting();
    expect(screen.getByText('仍有月嫂尚未同意本次服務')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /確認月嫂.*願意承接/ })).not.toBeInTheDocument();
    expect(mocks.recordFormalPlanWillingness).not.toHaveBeenCalled();
  });
  it('通知不承接後要求換人，不用舊客戶接受繼續保留檔期', async () => {
    contact = { ...contact, all_willing: false, customer_decision: 'accepted', segments: [{ segment_id: 71, willingness: 'unwilling' }] };
    await openExisting();
    expect(screen.getByText('推薦月嫂已通知不承接')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /預覽方案.*等待訂金鎖/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '更換月嫂' })).toBeEnabled();
  });

  it.each(['unwilling', 'pending'] as const)('正式方案 %s 改為願意並回讀後，可用新版本寄送客戶 LINE 確認資訊', async (prior) => {
    contact = { ...contact, all_willing: false, customer_profiles_status: null,
      segments: [{ segment_id: 71, willingness: 'willing' }, { segment_id: 72, willingness: prior }] };
    await openExisting();
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '手動修改月嫂意願' })[1]!);
    const save = screen.getByRole('button', { name: '儲存意願變更' });
    expect(save).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: '願意承接' }));
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('修改原因（必填）'), { target: { value: '電話確認月嫂改為願意承接本段服務。' } });
    fireEvent.click(save);
    await screen.findByText('月嫂意願變更已儲存並完成回讀。');
    expect(mocks.recordFormalPlanWillingness).toHaveBeenCalledWith(
      CASE, 51, 72, 4, '電話確認月嫂改為願意承接本段服務。',
      expect.stringMatching(/^orders-formal-manual-willingness-51-72-/), 'operator-1', 'willing',
    );
    expect(mocks.previewCustomerConfirmation).toHaveBeenCalledWith(CASE, 51, 5, expect.anything());
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText('確認資訊發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');
    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledWith(
      CASE, 51, 5, '請查收正式推薦月嫂的完整確認資訊。', expect.stringMatching(/^orders-customer-confirmation-51-/),
    );
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
  });

  it('仍可把正式願意改成不承接，並阻擋客戶確認資訊寄送', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    fireEvent.click(screen.getByRole('button', { name: '手動修改月嫂意願' }));
    fireEvent.change(screen.getByLabelText('修改原因（必填）'), { target: { value: '月嫂來電通知無法承接。' } });
    expect(screen.getByRole('button', { name: '儲存意願變更' })).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: '不承接' }));
    fireEvent.click(screen.getByRole('button', { name: '儲存意願變更' }));
    await screen.findByText('月嫂意願變更已儲存並完成回讀。');
    expect(mocks.recordFormalPlanWillingness).toHaveBeenCalledWith(
      CASE, 51, 71, 4, '月嫂來電通知無法承接。', expect.any(String), 'operator-1', 'unwilling',
    );
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });

  it('願意更正收到回條但正式回讀未確認時，保留操作並阻擋寄送直到重新回讀成功', async () => {
    contact = { ...contact, all_willing: false, customer_profiles_status: null, segments: [{ segment_id: 71, willingness: 'unwilling' }] };
    mocks.recordFormalPlanWillingness.mockResolvedValue({ event_id: 92, communication_version: 5 });
    await openExisting();
    fireEvent.click(screen.getByRole('button', { name: '手動修改月嫂意願' }));
    fireEvent.click(screen.getByRole('radio', { name: '願意承接' }));
    fireEvent.change(screen.getByLabelText('修改原因（必填）'), { target: { value: '月嫂確認可承接。' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存意願變更' }));
    await screen.findAllByText('正式人工回覆已收到收據，但目前方案回讀尚未確認相同版本與結果；只能重新讀取。');
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
    contact = { ...contact, all_willing: true, segments: [{ segment_id: 71, willingness: 'willing' }],
      plan: { ...contact.plan, communication_version: 5 } };
    fireEvent.click(screen.getByRole('button', { name: '只重新讀取正式人工回覆結果' }));
    await screen.findByText('月嫂意願變更已儲存並完成回讀。');
    await waitFor(() => expect(screen.getByRole('button', { name: '寄送確認資訊給客戶' })).toBeEnabled());
    expect(mocks.recordFormalPlanWillingness).toHaveBeenCalledTimes(1);
  });

  it.each([
    { service_started: false, assignments: [{ assignment_id: 1 }] },
    { service_started: true, assignments: [] },
  ])('已有指派或服務事實時，不以意願更正旁路人員異動：%j', async (assignment) => {
    contact = { ...contact, all_willing: false, customer_profiles_status: null, segments: [{ segment_id: 71, willingness: 'unwilling' }] };
    mocks.getAssignmentPlan.mockResolvedValue(assignment);
    await openExisting();
    fireEvent.click(screen.getByRole('button', { name: '手動修改月嫂意願' }));
    fireEvent.click(screen.getByRole('radio', { name: '願意承接' }));
    fireEvent.change(screen.getByLabelText('修改原因（必填）'), { target: { value: '月嫂確認可承接。' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存意願變更' }));
    await screen.findByText('本案已有正式指派，請由換人或請假代班記錄人員異動。');
    expect(mocks.recordFormalPlanWillingness).not.toHaveBeenCalled();
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });

  it.each(['none', 'network', 'old-active'] as const)('LINE 拒接回讀使看板退回，R-04 後選新人並重新取得客戶接受（交接回讀：%s）', async (readbackCase) => {
    let phase: 'accepted' | 'withdrawn' | 'replacement' | 'new_proposed' | 'new_accepted' = 'accepted';
    let newPlan = false;
    let pendingReadbackFailure = false;
    contact = { ...contactState(), customer_decision: 'accepted', plan: { ...contactState().plan, status: 'accepted' } };
    const originalAcceptance = structuredClone(contact);
    const oldAssignment = { assignment_id: 301, staff_id: 8892, sequence: 1, assigned_start_date: '2026-09-01', assigned_end_date: '2026-09-05', official_service_dates: [] };
    mocks.getAssignmentPlan.mockImplementation(async () => ({ case_no: CASE, service_started: false,
      assignments: ['accepted', 'withdrawn'].includes(phase) ? [oldAssignment] : [] }));
    mocks.getTerms.mockResolvedValue({});
    mocks.getDetail.mockResolvedValue({ case_no: CASE, client_name: '合成測試客戶', order_status: '訂單成立', service_days: 5, service_hours_per_day: 8 });
    mocks.query.mockImplementation(async () => ({ ...pool(), candidates: pool().candidates.map(candidate => ({ ...candidate,
      status: candidate.id === 17 && newPlan === false && !['accepted', 'withdrawn'].includes(phase) ? 'withdrawn' : candidate.status,
      willingness: candidate.id === 18 ? 'willing' : candidate.willingness })) }));
    mocks.queryPlan.mockImplementation(async () => {
      if (phase === 'replacement' && pendingReadbackFailure) {
        pendingReadbackFailure = false;
        if (readbackCase === 'old-active') return activePlan();
        throw new Error('換人後回讀暫時失敗');
      }
      if (phase === 'replacement') throw new ApiHttpError(404, 'not_found', '原推薦已退役');
      return newPlan ? { planId: 52, status: 'proposed', activeLockId: null, planVersion: 1,
        segments: [{ segmentId: 72, sequence: 1, staffId: 8893, assignedStartDate: '2026-09-01', assignedEndDate: '2026-09-05' }] } : activePlan();
    });
    mocks.coreTimelines.mockImplementation(async () => {
      const code = phase === 'accepted' ? 'formal_service' : phase === 'replacement' ? 'matching_pool'
        : phase === 'new_accepted' ? 'external_signing_dispatch' : 'formal_recommendation';
      return { items: [{ case_no: CASE, branch_type: 'normal', lifecycle_status: '訂單成立',
        current_core_stage_code: code, current_core_stage_ordinal: CORE_STAGE_CODES.indexOf(code) + 1,
        core_stages: CORE_STAGE_CODES.map((item, index) => {
          const status = item === code ? phase === 'withdrawn' ? 'blocked' : 'in_progress' : 'completed';
          return { ordinal: index + 1, code: item, label: item === 'formal_recommendation' ? '推薦月嫂給客戶確認' : item,
            status, substatus_code: SUBSTATUS_BY_STAGE_STATUS[item][status], source: { owner: 'Scheduling', identity: item, version: 5 },
            blockers: item === code && phase === 'withdrawn' ? [{ code: 'recommendation_caregiver_unwilling', message: '推薦月嫂已通知不承接，請更換月嫂並重新取得客戶確認。' }] : [], warnings: [] };
        }) }] };
    });
    const ready = { case_no: CASE, scenario: 'R-04', outcome: 'ready', actual_service_day_count: 0, actual_service_dates: [],
      actual_service_proof: { case_no: CASE, service_dates: [], source_identity: 'official:301', source_version: 1, fingerprint: 'a'.repeat(64) },
      prior_generation_identity: 'generation:1', prior_event_identity: 'event:1', prior_aggregate_identity: 'aggregate:1',
      generation_version: 1, event_version: 1, aggregate_version: 1, impacted_roots: [], retained_roots: [],
      root_delta: { retained: [], superseded: [], created: [] }, candidate_pool_reuse_proof: null, successor_round: null,
      resume_step: 'step_2', blockers: [] };
    mocks.replacementQuery.mockResolvedValue(ready);
    mocks.replacementPreview.mockImplementation(async (_case, request) => ({ ...ready, reason: request.reason, evidence: [],
      expected_generation_version: 1, expected_event_version: 1, expected_aggregate_version: 1, preview_fingerprint: 'a'.repeat(64) }));
    mocks.replacementApply.mockImplementation(async () => {
      phase = 'replacement';
      pendingReadbackFailure = readbackCase !== 'none';
      return { status: 'applied', receipt: { case_no: CASE, replacement_generation_identity: 'generation:2' },
        readback: { case_no: CASE, generation_identity: 'generation:2', resume_step: 'step_2', candidate_count: 0, complete: true } };
    });
    mocks.createSingleCaregiverPlan.mockImplementation(async command => {
      expect(phase).toBe('replacement');
      expect(command.segments[0].staff_id).toBe(8893);
      newPlan = true; phase = 'new_proposed';
      contact = { ...contactState(), plan: { ...contactState().plan, id: 52, communication_version: 0 },
        segments: [{ segment_id: 72, staff_id: 8893, staff_name: '月嫂乙', willingness: 'willing' }],
        customer_decision: 'pending', customer_profiles_status: null };
      return { ...plan(command), plan_id: 52 };
    });
    const originalPreview = mocks.previewCustomerConfirmation.getMockImplementation()!;
    mocks.previewCustomerConfirmation.mockImplementation(async (...args) => ({ ...await originalPreview(...args), plan_id: contact.plan.id }));
    mocks.recordCustomerDecision.mockImplementation(async (caseNo, planId, version, decision, reason, eventKey) => {
      expect(planId).toBe(52); expect(contact.customer_decision).toBe('pending');
      contact = { ...contact, customer_decision: decision, plan: { ...contact.plan, communication_version: version + 1 } };
      phase = 'new_accepted';
      return { event_id: 101, case_no: caseNo, plan_id: planId, communication_version: version + 1,
        segment_id: null, event_key: eventKey, source: 'admin', willingness: null, customer_decision: decision, reason };
    });
    const view = render(<OrderWorkbenchV2Drawer key="before-line" caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    expect(await screen.findByText('排班工作區')).toBeVisible();
    // The separate owner integration test exercises the real LINE callback; this is its fresh API readback.
    contact = { ...contact, all_willing: false, segments: [{ segment_id: 71, staff_id: 8892, staff_name: '月嫂甲', willingness: 'unwilling' }],
      plan: { ...contact.plan, communication_version: 5 } };
    phase = 'withdrawn';
    view.rerender(<OrderWorkbenchV2Drawer key="after-line" caseNo={CASE} branchType="normal" onClose={vi.fn()} />);
    expect(await screen.findByText('推薦月嫂已通知不承接')).toBeVisible();
    expect(screen.getByRole('button', { name: /推薦月嫂給客戶確認.*需要處理/ })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('button', { name: '寄送確認資訊給客戶' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '更換月嫂' }));
    fireEvent.click(await screen.findByRole('button', { name: '換人' }));
    await screen.findByText('可以辦理更換');
    fireEvent.change(screen.getByLabelText('換人原因'), { target: { value: '月嫂透過 LINE 通知不接案' } });
    fireEvent.click(screen.getByRole('button', { name: '預覽換人影響' }));
    await screen.findByText('預覽完成，尚未寫入');
    fireEvent.click(screen.getByLabelText('我已確認換人原因及影響'));
    fireEvent.click(screen.getByRole('button', { name: '確認更換' }));
    await waitFor(() => expect(mocks.replacementApply).toHaveBeenCalledTimes(1));
    if (readbackCase !== 'none') {
      await screen.findByText(readbackCase === 'network' ? '換人後回讀暫時失敗' : '換人已登記，但原推薦仍為有效方案；請重新讀取，不重送換人。');
      expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('button', { name: '重新讀取換人後的推薦進度' }));
    }
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /尋找月嫂與詢問意願.*可辦理/ })).toHaveAttribute('aria-current', 'page');
      expect(screen.getByRole('button', { name: /推薦月嫂給客戶確認/ })).toBeEnabled();
    });
    fireEvent.click(await screen.findByRole('button', { name: /推薦月嫂給客戶確認/ }));
    const select = await screen.findByRole('button', { name: '以 月嫂乙 建立正式媒合方案' });
    await waitFor(() => expect(select).toBeEnabled());
    fireEvent.click(select);
    await screen.findByText('正式媒合方案已建立：#52');
    expect(contact.customer_decision).toBe('pending');
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await screen.findByText(/確認資訊發送工作已建立/);
    expect(mocks.sendCustomerConfirmation).toHaveBeenCalledWith(CASE, 52, 0, expect.any(String), expect.any(String));
    await openManual();
    fireEvent.change(screen.getByLabelText('方案 52 客戶決策依據'), { target: { value: '客戶收到新推薦後電話確認接受月嫂乙' } });
    fireEvent.click(screen.getByRole('button', { name: '記錄方案 52 客戶接受' }));
    await waitFor(() => expect(contact.customer_decision).toBe('accepted'));
    expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(CASE, 52, 1, 'accepted', expect.any(String), expect.any(String), 'operator-1');
    expect(originalAcceptance.customer_decision).toBe('accepted');
    expect(originalAcceptance.plan.id).toBe(51);
    expect(mocks.replacementApply).toHaveBeenCalledTimes(1);
  });

  it('共用內容在唯讀抽屜查看，客戶人工回覆及換人入口不重複展開', async () => {
    contact.customer_profiles_status = null;
    await openExisting();
    const view = await screen.findByRole('button', { name: '查看服務條件與費用' });
    await waitFor(() => expect(view).toBeEnabled());
    expect(screen.queryByLabelText('方案 51 客戶決策依據')).not.toBeInTheDocument();
    fireEvent.click(view);
    expect(await screen.findByRole('dialog', { name: '客戶確認資訊' })).toBeInTheDocument();
    expect(screen.getByText(/總薪資：預估 48000 元/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '每週服務說明' }));
    expect(screen.getByRole('table')).toHaveTextContent('40 小時');
    expect(screen.queryByText('其他處理')).not.toBeInTheDocument();
    expect(screen.queryByText('更換推薦人選')).not.toBeInTheDocument();
  });

  it('缺月嫂履歷時顯示人工傳送提醒但仍允許寄送確認資訊', async () => {
    contact.customer_profiles_status = null;
    mocks.previewCustomerConfirmation.mockResolvedValue({
      case_no: CASE, plan_id: 51, expected_version: 4,
      order_information_1_ready: true, order_information_2_ready: true,
      weekly_service_ready: true, weekly_service_row_count: 1,
      order_information_1: [{ segment_id: 71, staff_id: 8892, staff_name: '月嫂甲', text: '訂單資訊－1' }],
      order_information_2: [{ segment_id: 71, staff_id: 8892, staff_name: '月嫂甲', text: '訂單資訊－2' }],
      weekly_service_rows: [{ serial_number: 1, staff_name: '月嫂甲', week_start_date: '2026-09-01', week_end_date: '2026-09-07', service_hours_per_day: 8, weekly_work_days: 5, weekly_hours: 40 }],
      caregiver_resumes: [{
        staff_id: 8892, staff_name: '月嫂甲', ready: false, filename: null, version: null,
        blocker: '月嫂 月嫂甲 未附履歷；確認資訊仍可寄送，請由公會人員另行透過 LINE 傳送履歷。',
      }],
      blockers: [],
      send_allowed: true,
    });

    await openExisting();

    expect(await screen.findByText(/履歷 PDF 未附/)).toBeInTheDocument();
    const send = screen.getByRole('button', { name: '寄送確認資訊給客戶' });
    expect(send).toBeEnabled();
    await openSending();
    fireEvent.click(screen.getByRole('button', { name: '確認寄送' }));
    await waitFor(() => expect(mocks.sendCustomerConfirmation).toHaveBeenCalled());
  });
});
