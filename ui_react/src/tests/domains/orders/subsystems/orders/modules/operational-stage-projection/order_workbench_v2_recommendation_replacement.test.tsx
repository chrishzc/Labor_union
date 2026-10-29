import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderRecommendationReplacementPanel } from '../../../../../../../components/OrderRecommendationReplacementPanel';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import type { FormalPlanContactState } from '../../../../../../../api/scheduling/matching_plan_communication_client';

const mocks = vi.hoisted(() => ({ assignment: vi.fn(), pool: vi.fn(), queryPlan: vi.fn(), contact: vi.fn(), previewRelease: vi.fn(), release: vi.fn(), cancel: vi.fn(), create: vi.fn(), receipt: vi.fn() }));
vi.mock('../../../../../../../api/staff_directory/staff_directory_client', async importOriginal => ({
  ...await importOriginal<typeof import('../../../../../../../api/staff_directory/staff_directory_client')>(),
  loadActiveStaffIds: vi.fn(async () => new Set([1, 2, 3])),
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({ ordersQueryClient: { getAssignmentPlan: mocks.assignment } }));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({ candidateContactPoolClient: { query: mocks.pool } }));
vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: { queryPlan: mocks.queryPlan, previewRelease: mocks.previewRelease, release: mocks.release } }));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: { queryContactState: mocks.contact, cancelRecommendation: mocks.cancel } }));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', () => ({ matchingCandidateWorkflowClient: { createSingleCaregiverPlan: mocks.create, createMatchingPlan: mocks.create, queryMatchingPlanReceipt: mocks.receipt } }));
const CASE = 'RECOMMEND-TEST';
const contact: FormalPlanContactState = { plan: { id: 51, case_no: CASE, status: 'proposed', communication_version: 4, is_active: 1 }, segments: [{ segment_id: 71, staff_id: 1, staff_name: '月嫂甲', willingness: 'willing' }], all_willing: true, customer_decision: 'accepted', customer_profiles_status: null, customer_profiles_manual_confirmation: null };
const plan = { planId: 51, status: 'proposed', activeLockId: null, planVersion: 1, segments: [{ segmentId: 71, sequence: 1, staffId: 1, assignedStartDate: '2026-11-16', assignedEndDate: '2026-11-20' }] };
let active: boolean;
let created: boolean;
const onObserved = vi.fn();
const onReplacementStarted = vi.fn();
function mount(lock = false, onOpenCandidates?: () => void) { return render(<OrderRecommendationReplacementPanel caseNo={CASE} plan={{ ...plan, activeLockId: lock ? 88 : null }} contact={contact} onObserved={onObserved} onReplacementStarted={onReplacementStarted} onOpenCandidates={onOpenCandidates} onClose={vi.fn()} onEditStateChange={vi.fn()} />); }
async function preview() {
  fireEvent.click(await screen.findByRole('radio', { name: /月嫂乙/ }));
  fireEvent.change(screen.getByLabelText('換人原因（選填）'), { target: { value: '客戶要求換人' } });
  fireEvent.click(screen.getByRole('button', { name: '儲存更換' }));
  expect(screen.queryByRole('checkbox', { name: '我已確認換人原因及影響' })).not.toBeInTheDocument();
}
describe('推薦頁更換人員沿用原正式操作及收據', () => {
  it('offers a working candidate repair entry when there is no willing successor', async () => {
    const onOpenCandidates = vi.fn();
    mocks.pool.mockResolvedValue({ case_no: CASE, candidates: [] });
    mount(false, onOpenCandidates);
    fireEvent.click(await screen.findByRole('button', { name: '前往尋找月嫂與詢問意願' }));
    expect(onOpenCandidates).toHaveBeenCalledOnce();
    expect(mocks.cancel).not.toHaveBeenCalled();
    expect(mocks.create).not.toHaveBeenCalled();
  });
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset());
    orderMutationFlowStore.clearAll(); onObserved.mockReset(); onReplacementStarted.mockReset(); active = true; created = false;
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator' } as never);
    mocks.assignment.mockResolvedValue({ case_no: CASE, service_started: false, assignments: [] });
    mocks.pool.mockResolvedValue({ case_no: CASE, candidates: [
      { id: 1, staff_id: 1, staff_name: '月嫂甲', status: 'active', willingness: 'willing' },
      { id: 2, staff_id: 2, staff_name: '月嫂乙', status: 'active', willingness: 'willing' },
      { id: 3, staff_id: 3, staff_name: '月嫂丙', status: 'active', willingness: 'unwilling' },
    ].map(row => ({ ...row, service_start_date: '2026-11-16', service_end_date: '2026-11-20' })) });
    mocks.queryPlan.mockImplementation(async () => {
      if (!active) throw new ApiHttpError(404, 'not_found', '無有效方案');
      return created ? { ...plan, planId: 52, segments: [{ ...plan.segments[0], staffId: 2 }] } : plan;
    });
    mocks.contact.mockResolvedValue(contact);
    mocks.cancel.mockImplementation(async () => { active = false; return { status: 'cancelled', event_id: 19 }; });
    mocks.receipt.mockRejectedValue(new ApiHttpError(404, 'not_found', '無原回條'));
    mocks.create.mockImplementation(async command => { active = true; created = true; return { plan_id: 52, case_no: CASE, version: 1, status: 'proposed', result: 'created', actor: command.actor, as_of: command.asOf, event_key: command.key, command_fingerprint: 'a'.repeat(64), replayed: false, segments: command.segments.map((segment: { staff_id: number; start_date: string; end_date: string }, index: number) => ({ segment_order: index + 1, staff_id: segment.staff_id, assigned_start_date: segment.start_date, assigned_end_date: segment.end_date })) }; });
  });
  it('只有願意的新月嫂可選，換人原因選填，未儲存不自動異動', async () => {
    mount();
    fireEvent.click(await screen.findByRole('radio', { name: /月嫂乙/ }));
    expect(screen.queryByRole('radio', { name: /月嫂丙/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('聯繫紀錄或更換依據')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '儲存更換' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('換人原因（選填）'), { target: { value: '   ' } });
    expect(screen.getByRole('button', { name: '儲存更換' })).toBeEnabled();
    expect(mocks.cancel).not.toHaveBeenCalled();
  });
  it('確定取消原方案後才建立新推薦，成功回讀原命令人員與日期後通知父頁', async () => {
    mount(); await preview();
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(mocks.cancel).toHaveBeenCalledTimes(1); expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ actor: 'operator', segments: [{ staff_id: 2, start_date: '2026-11-16', end_date: '2026-11-20' }] }));
    expect(orderMutationFlowStore.getRecommendationReplacement(CASE)).toBeUndefined();
  });
  it('取消結果未知時保留原操作與原因，使用相同 key 對帳後再接續', async () => {
    mocks.cancel.mockRejectedValueOnce(new Error('回應中斷'));
    mount(); await preview();
    const retry = await screen.findByRole('button', { name: '重新確認原換人操作' });
    expect(mocks.create).not.toHaveBeenCalled();
    const original = orderMutationFlowStore.getRecommendationReplacement(CASE)!.command;
    fireEvent.click(retry);
    await waitFor(() => expect(onObserved).toHaveBeenCalledOnce());
    expect(mocks.cancel.mock.calls[0]).toEqual(mocks.cancel.mock.calls[1]);
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ key: original.createKey, segments: original.segments }));
    expect(orderMutationFlowStore.getRecommendationReplacement(CASE)).toBeUndefined();
  });
  it('預覽後正式指派有變更時拒絕推薦取消，不旁路成一般重新推薦', async () => {
    mocks.assignment.mockResolvedValueOnce({ case_no: CASE, service_started: false, assignments: [] }).mockResolvedValue({ case_no: CASE, service_started: false, assignments: [{ id: 1 }] });
    mount(); await screen.findByRole('radio', { name: /月嫂乙/ });
    fireEvent.click(screen.getByRole('radio', { name: /月嫂乙/ }));
    fireEvent.change(screen.getByLabelText('換人原因（選填）'), { target: { value: '換人' } });
    fireEvent.click(screen.getByRole('button', { name: '儲存更換' }));
    await screen.findByText('本案已有正式指派，請重新查詢並接續正式換人或代班。');
    expect(mocks.cancel).not.toHaveBeenCalled(); expect(mocks.create).not.toHaveBeenCalled();
  });
  it('已有實際服務時只轉往代班，不能取消推薦或重寫已服務記錄', async () => {
    mocks.assignment.mockResolvedValue({ case_no: CASE, service_started: true, assignments: [{ id: 1 }] });
    mount();
    expect(await screen.findByRole('link', { name: '辦理臨時代班 →' })).toHaveAttribute('href', `#scheduling?tab=leave_sub&case_no=${CASE}`);
    expect(mocks.cancel).not.toHaveBeenCalled(); expect(mocks.create).not.toHaveBeenCalled();
  });
  it('原推薦已取消後重新開啟仍保留原命令，不重複取消即可接續建立', async () => {
    mocks.create.mockRejectedValueOnce(new Error('建立結果未明'));
    const first = mount(); await preview();
    await screen.findByRole('button', { name: '重新確認原換人操作' });
    const original = orderMutationFlowStore.getRecommendationReplacement(CASE)!.command;
    expect(original.originalPlan.planId).toBe(51);
    first.unmount(); mount();
    fireEvent.click(await screen.findByRole('button', { name: '重新確認原換人操作' }));
    await waitFor(() => expect(onObserved).toHaveBeenCalledTimes(1));
    expect(mocks.cancel).toHaveBeenCalledTimes(1);
    expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ key: original.createKey }));
  });
  it('新推薦確定遭檔期衝突拒絕後，查明無收據及有效方案才返回改選', async () => {
    mocks.create.mockRejectedValue(new ApiHttpError(409, 'matching_plan_staff_occupancy_conflict', '11/16 已由其他案件保留'));
    mount(); await preview();
    fireEvent.click(await screen.findByRole('button', { name: '返回改選月嫂' }));
    await waitFor(() => expect(onReplacementStarted).toHaveBeenCalledOnce());
    expect(orderMutationFlowStore.getRecommendationReplacement(CASE)).toBeUndefined();
    expect(mocks.receipt).toHaveBeenCalledTimes(2);
    expect(mocks.cancel).toHaveBeenCalledTimes(1); expect(mocks.create).toHaveBeenCalledTimes(1);
  });
  it('改選查核失敗時保留原操作，不能清掉尚待確認的結果', async () => {
    mocks.create.mockRejectedValue(new ApiHttpError(409, 'matching_plan_staff_occupancy_conflict', '檔期衝突'));
    mount(); await preview();
    const repair = await screen.findByRole('button', { name: '返回改選月嫂' });
    const original = orderMutationFlowStore.getRecommendationReplacement(CASE)!.command;
    mocks.receipt.mockRejectedValue(new Error('查詢中斷'));
    fireEvent.click(repair);
    await screen.findByText('查詢中斷');
    expect(onReplacementStarted).not.toHaveBeenCalled();
    expect(orderMutationFlowStore.getRecommendationReplacement(CASE)!.command).toEqual(original);
  });
  it('新推薦回應中斷時只允許以原操作查核，不提供改選入口', async () => {
    mocks.create.mockRejectedValue(new Error('回應中斷'));
    mount(); await preview();
    await screen.findByRole('button', { name: '重新確認原換人操作' });
    expect(screen.queryByRole('button', { name: '返回改選月嫂' })).not.toBeInTheDocument();
    expect(orderMutationFlowStore.getRecommendationReplacement(CASE)).toBeDefined();
  });
  it('已保留檔期沿用正式釋放預覽與回條，釋放失敗不取消原推薦', async () => {
    mocks.queryPlan.mockResolvedValue({ ...plan, activeLockId: 88 });
    mocks.previewRelease.mockResolvedValue({ apply_allowed: true, case_no: CASE, plan_id: 51, lock_id: 88, preview_fingerprint: 'a'.repeat(64) });
    mocks.release.mockRejectedValue(new ApiHttpError(409, 'conflict', '訂金狀態已變更'));
    mount(true); await preview();
    await screen.findByText('訂金狀態已變更');
    expect(mocks.release).toHaveBeenCalledWith(CASE, 51, 88, 'a'.repeat(64), '客戶要求換人', expect.any(String), 'operator');
    expect(mocks.cancel).not.toHaveBeenCalled(); expect(mocks.create).not.toHaveBeenCalled();
  });
});
