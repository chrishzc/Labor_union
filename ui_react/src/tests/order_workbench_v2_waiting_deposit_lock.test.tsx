import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';

const mocks = vi.hoisted(() => ({ queryPlan: vi.fn(), queryContactState: vi.fn(), preview: vi.fn(), apply: vi.fn() }));
vi.mock('../api/scheduling/waiting_deposit_lock_client', () => ({ waitingDepositLockClient: {
  queryPlan: mocks.queryPlan, preview: mocks.preview, apply: mocks.apply,
} }));
vi.mock('../api/scheduling/matching_plan_communication_client', () => ({ matchingPlanCommunicationClient: { queryContactState: mocks.queryContactState } }));
const CASE = 'CASE-DEPOSIT-LOCK';
let lockId: number | null;
let accepted: boolean;
function activePlan() {
  return { planId: 51, status: accepted ? 'accepted' : 'proposed', activeLockId: lockId, communicationVersion: 5,
    segments: [{ segmentId: 71, sequence: 1, staffId: 8892, assignedStartDate: '2026-09-01', assignedEndDate: '2026-09-05' }] };
}
function contactState() {
  return { plan: { id: 51, case_no: CASE, communication_version: 5, status: accepted ? 'accepted' : 'proposed', is_active: 1 },
    segments: [{ segment_id: 71, willingness: 'willing' }], all_willing: true,
    customer_decision: accepted ? 'accepted' : 'pending', customer_profiles_status: 'manually_confirmed', customer_profiles_manual_confirmation: null };
}
function preview(allowed = true) {
  return { case_no: CASE, plan_id: 51, service_day_count: 5, buffer_day_count: 2, occupancy: [],
    conflicts: allowed ? [] : [{ staff_id: 8892, lock_date: '2026-09-04', source_type: 'active_lock', source_id: 99 }],
    apply_allowed: allowed, preview_fingerprint: 'a'.repeat(64) };
}
async function open(onObserved = vi.fn()) {
  render(<OrderFormalRecommendationPanel caseNo={CASE} onObserved={onObserved} />);
  await screen.findByText(`目前決定：${accepted ? 'accepted' : 'pending'}`);
  return onObserved;
}

describe('待辦看板 Beta 既有方案等待訂金鎖', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    lockId = null; accepted = true;
    mocks.queryPlan.mockImplementation(async () => activePlan());
    mocks.queryContactState.mockImplementation(async () => contactState());
    mocks.preview.mockResolvedValue(preview());
    mocks.apply.mockImplementation(async () => {
      lockId = 88;
      return { result: 'created', lock_id: 88, plan_id: 51, case_no: CASE, lock_rows: [] };
    });
  });

  it('accepted 既有方案先 Preview，再用該 fingerprint Apply 並回讀 lock', async () => {
    const onObserved = await open();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '預覽方案 51 等待訂金鎖' }));
    await screen.findByText('允許套用：是');
    expect(mocks.preview).toHaveBeenCalledWith(CASE, 51);
    const apply = screen.getByRole('button', { name: '套用方案 51 等待訂金鎖' });
    await waitFor(() => expect(apply).toBeEnabled());
    fireEvent.click(apply);
    await screen.findByText('等待訂金鎖已套用：Lock #88 · created');
    expect(mocks.apply).toHaveBeenCalledWith(CASE, 51, 'a'.repeat(64));
    expect(mocks.queryPlan).toHaveBeenCalledTimes(4);
    expect(onObserved).toHaveBeenCalledTimes(1);
    expect(screen.getByText('既有等待訂金鎖：#88')).toBeInTheDocument();
  });

  it('apply_allowed=false 顯示正式衝突且不能 Apply', async () => {
    mocks.preview.mockResolvedValue(preview(false));
    await open();
    fireEvent.click(screen.getByRole('button', { name: '預覽方案 51 等待訂金鎖' }));
    await screen.findByText('允許套用：否');
    expect(screen.getByText('衝突：月嫂 #8892 · 2026-09-04 · active_lock #99')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '套用方案 51 等待訂金鎖' })).toBeDisabled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('pending 方案仍可 Query，但不提供鎖 Preview 或 Apply', async () => {
    accepted = false;
    await open();
    expect(mocks.queryPlan).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '預覽方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(mocks.preview).not.toHaveBeenCalled();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('重新開頁已有鎖時呈現原 lock，不重新建立', async () => {
    lockId = 88;
    await open();
    expect(screen.getByText('既有等待訂金鎖：#88')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '預覽方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('Preview 的方案 identity 不一致時停止', async () => {
    mocks.preview.mockResolvedValue({ ...preview(), plan_id: 52 });
    await open();
    fireEvent.click(screen.getByRole('button', { name: '預覽方案 51 等待訂金鎖' }));
    await screen.findByText('等待訂金鎖 Preview identity 不一致，已停止套用。');
    expect(mocks.apply).not.toHaveBeenCalled();
  });

  it('Apply 後 lock 回讀不一致不報成功、不通知父頁或重試', async () => {
    mocks.apply.mockResolvedValue({ result: 'created', lock_id: 88, plan_id: 51, case_no: CASE, lock_rows: [] });
    const onObserved = await open();
    fireEvent.click(screen.getByRole('button', { name: '預覽方案 51 等待訂金鎖' }));
    await screen.findByText('允許套用：是');
    const apply = screen.getByRole('button', { name: '套用方案 51 等待訂金鎖' });
    await waitFor(() => expect(apply).toBeEnabled());
    fireEvent.click(apply);
    await screen.findByText('操作後正式方案回讀尚未確認預期結果，請重新讀取；不重送操作。');
    expect(onObserved).not.toHaveBeenCalled();
    expect(mocks.apply).toHaveBeenCalledTimes(1);
  });
});
