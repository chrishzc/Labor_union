import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';

const mocks = vi.hoisted(() => ({
  queryPool: vi.fn(),
  createSingleCaregiverPlan: vi.fn(),
  queryContactState: vi.fn(),
  recordCustomerDecision: vi.fn(),
  queryPlan: vi.fn(),
  previewWaitingLock: vi.fn(),
  applyWaitingLock: vi.fn(),
}));

vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: {
    query: mocks.queryPool,
  },
}));

vi.mock('../api/scheduling/matching_candidate_workflow_client', () => ({
  matchingCandidateWorkflowClient: {
    createSingleCaregiverPlan: mocks.createSingleCaregiverPlan,
  },
}));

vi.mock('../api/scheduling/matching_plan_communication_client', () => ({
  matchingPlanCommunicationClient: {
    queryContactState: mocks.queryContactState,
    recordCustomerDecision: mocks.recordCustomerDecision,
  },
}));

vi.mock('../api/scheduling/waiting_deposit_lock_client', () => ({
  waitingDepositLockClient: {
    queryPlan: mocks.queryPlan,
    preview: mocks.previewWaitingLock,
    apply: mocks.applyWaitingLock,
  },
}));

function pool() {
  return {
    pool_id: 9,
    case_no: 'CASE-DEPOSIT-LOCK',
    candidates: [{
      id: 17,
      staff_id: 8892,
      service_start_date: '2026-09-01',
      service_end_date: '2026-09-05',
      status: 'active',
      created_at: '2026-09-03T00:00:00Z',
      staff_name: '月嫂甲',
      willingness: 'willing',
      reason: null,
      information: { '1': null, '2': null },
    }],
  };
}

function plan() {
  return {
    plan_id: 51,
    case_no: 'CASE-DEPOSIT-LOCK',
    version: 1,
    status: 'proposed',
    result: 'created',
    segments: [{
      segment_order: 1,
      staff_id: 8892,
      assigned_start_date: '2026-09-01',
      assigned_end_date: '2026-09-05',
    }],
  };
}

function contactState(decision: 'pending' | 'accepted' | 'declined' | 'contact_requested') {
  return {
    plan: {
      id: 51,
      case_no: 'CASE-DEPOSIT-LOCK',
      communication_version: 5,
      status: decision === 'accepted' ? 'accepted' : 'proposed',
      is_active: 1,
    },
    segments: [{ segment_id: 71, willingness: 'willing' }],
    all_willing: true,
    customer_decision: decision,
    customer_profiles_status: 'manually_confirmed',
    customer_profiles_manual_confirmation: null,
  };
}

function activePlan(activeLockId: number | null) {
  return {
    planId: 51,
    status: 'accepted',
    activeLockId,
    communicationVersion: 5,
    segments: [{
      segmentId: 71,
      sequence: 1,
      staffId: 8892,
      assignedStartDate: '2026-09-01',
      assignedEndDate: '2026-09-05',
    }],
  };
}

function preview(applyAllowed: boolean) {
  return {
    case_no: 'CASE-DEPOSIT-LOCK',
    plan_id: 51,
    service_day_count: 5,
    buffer_day_count: 2,
    occupancy: [],
    conflicts: applyAllowed ? [] : [{
      staff_id: 8892,
      lock_date: '2026-09-04',
      source_type: 'active_lock',
      source_id: 99,
    }],
    apply_allowed: applyAllowed,
    preview_fingerprint: 'a'.repeat(64),
  };
}

async function openAcceptedPlan(decision: 'pending' | 'accepted' = 'accepted') {
  mocks.queryPool.mockResolvedValue(pool());
  mocks.createSingleCaregiverPlan.mockResolvedValue(plan());
  mocks.queryContactState.mockResolvedValue(contactState(decision));
  render(<OrderFormalRecommendationPanel caseNo="CASE-DEPOSIT-LOCK" />);

  fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
  expect(await screen.findByText('月嫂甲 · 月嫂 #8892')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' }));
  expect(await screen.findByText(`目前決定：${decision}`)).toBeInTheDocument();
}

describe('待辦看板 Beta 第 5 階等待訂金鎖', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('客戶 accepted 後必須先通過 owner Preview，才可用該 fingerprint Apply 並回讀 lock', async () => {
    mocks.queryPlan
      .mockResolvedValueOnce(activePlan(null))
      .mockResolvedValueOnce(activePlan(88));
    mocks.previewWaitingLock.mockResolvedValue(preview(true));
    mocks.applyWaitingLock.mockResolvedValue({
      result: 'created',
      lock_id: 88,
      plan_id: 51,
      case_no: 'CASE-DEPOSIT-LOCK',
      lock_rows: [],
    });

    await openAcceptedPlan();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '預覽方案 51 等待訂金鎖' }));
    await waitFor(() => expect(mocks.queryPlan).toHaveBeenCalledWith('CASE-DEPOSIT-LOCK'));
    await waitFor(() => expect(mocks.previewWaitingLock).toHaveBeenCalledWith('CASE-DEPOSIT-LOCK', 51));
    expect(await screen.findByText('允許套用：是')).toBeInTheDocument();

    const applyButton = screen.getByRole('button', { name: '套用方案 51 等待訂金鎖' });
    expect(applyButton).toBeEnabled();
    fireEvent.click(applyButton);

    await waitFor(() => expect(mocks.applyWaitingLock).toHaveBeenCalledWith(
      'CASE-DEPOSIT-LOCK',
      51,
      'a'.repeat(64),
    ));
    expect(await screen.findByText('等待訂金鎖已套用：Lock #88 · created')).toBeInTheDocument();
    expect(mocks.queryPlan).toHaveBeenCalledTimes(2);
  });

  it('Preview 回傳 apply_allowed=false 時顯示 owner conflict 且不能 Apply', async () => {
    mocks.queryPlan.mockResolvedValue(activePlan(null));
    mocks.previewWaitingLock.mockResolvedValue(preview(false));

    await openAcceptedPlan();
    fireEvent.click(screen.getByRole('button', { name: '預覽方案 51 等待訂金鎖' }));

    expect(await screen.findByText('允許套用：否')).toBeInTheDocument();
    expect(screen.getByText('衝突：月嫂 #8892 · 2026-09-04 · active_lock #99')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '套用方案 51 等待訂金鎖' })).toBeDisabled();
    expect(mocks.applyWaitingLock).not.toHaveBeenCalled();
  });

  it('客戶決定尚未 accepted 時不顯示訂金鎖 Preview／Apply，也不呼叫 owner lock client', async () => {
    await openAcceptedPlan('pending');

    expect(screen.queryByRole('button', { name: '預覽方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '套用方案 51 等待訂金鎖' })).not.toBeInTheDocument();
    expect(mocks.queryPlan).not.toHaveBeenCalled();
    expect(mocks.previewWaitingLock).not.toHaveBeenCalled();
    expect(mocks.applyWaitingLock).not.toHaveBeenCalled();
  });
});
