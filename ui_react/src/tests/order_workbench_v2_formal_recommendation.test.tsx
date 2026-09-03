import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';

const mocks = vi.hoisted(() => ({
  query: vi.fn(),
  createSingleCaregiverPlan: vi.fn(),
  queryContactState: vi.fn(),
  recordCustomerDecision: vi.fn(),
}));

vi.mock('../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: {
    query: mocks.query,
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

function pool() {
  return {
    pool_id: 9,
    case_no: 'CASE-RECOMMEND',
    candidates: [
      {
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
      },
      {
        id: 18,
        staff_id: 8893,
        service_start_date: '2026-09-01',
        service_end_date: '2026-09-05',
        status: 'active',
        created_at: '2026-09-03T00:01:00Z',
        staff_name: '月嫂乙',
        willingness: 'unwilling',
        reason: '日期不合',
        information: { '1': null, '2': null },
      },
      {
        id: 19,
        staff_id: 8894,
        service_start_date: '2026-09-01',
        service_end_date: '2026-09-05',
        status: 'withdrawn',
        created_at: '2026-09-03T00:02:00Z',
        staff_name: '月嫂丙',
        willingness: 'willing',
        reason: null,
        information: { '1': null, '2': null },
      },
    ],
  };
}

function plan() {
  return {
    plan_id: 51,
    case_no: 'CASE-RECOMMEND',
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

function contactState(
  customerProfilesStatus: string | null = 'manually_confirmed',
  customerDecision: 'pending' | 'accepted' | 'declined' | 'contact_requested' = 'pending',
) {
  return {
    plan: {
      id: 51,
      case_no: 'CASE-RECOMMEND',
      communication_version: 4,
      status: customerDecision === 'accepted' ? 'accepted' : 'proposed',
      is_active: 1,
    },
    segments: [{ segment_id: 71, willingness: 'willing' }],
    all_willing: true,
    customer_decision: customerDecision,
    customer_profiles_status: customerProfilesStatus,
    customer_profiles_manual_confirmation: null,
  };
}

async function createFormalPlan() {
  fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));
  expect(await screen.findByText('月嫂甲 · 月嫂 #8892')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' }));
  expect(await screen.findByText('正式媒合方案已建立：#51 · created')).toBeInTheDocument();
  await waitFor(() => expect(mocks.queryContactState).toHaveBeenCalledWith('CASE-RECOMMEND', 51));
}

describe('待辦看板 Beta 第 5 階正式推薦媒合方案', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('只讓 active 且 willing 的 owner candidate 建立既有正式媒合方案，並獨立回讀履歷推薦送達狀態', async () => {
    mocks.query.mockResolvedValue(pool());
    mocks.createSingleCaregiverPlan.mockResolvedValue(plan());
    mocks.queryContactState.mockResolvedValue(contactState());

    render(<OrderFormalRecommendationPanel caseNo="CASE-RECOMMEND" />);
    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));

    expect(await screen.findByText('月嫂甲 · 月嫂 #8892')).toBeInTheDocument();
    expect(screen.getByText('月嫂乙 · 月嫂 #8893')).toBeInTheDocument();
    expect(screen.getByText('月嫂丙 · 月嫂 #8894')).toBeInTheDocument();
    expect(screen.getAllByText(/不可建立方案/)).toHaveLength(2);
    expect(screen.queryByRole('button', { name: '以 月嫂乙 建立正式媒合方案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '以 月嫂丙 建立正式媒合方案' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '以 月嫂甲 建立正式媒合方案' }));
    await waitFor(() => expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledWith(
      'CASE-RECOMMEND',
      { staff_id: 8892, start_date: '2026-09-01', end_date: '2026-09-05' },
    ));
    expect(await screen.findByText('正式媒合方案已建立：#51 · created')).toBeInTheDocument();
    await waitFor(() => expect(mocks.queryContactState).toHaveBeenCalledWith('CASE-RECOMMEND', 51));
    expect(await screen.findByText('manually_confirmed')).toBeInTheDocument();
    expect(screen.getByText('履歷推薦送達狀態')).toBeInTheDocument();
    expect(screen.getByText('目前決定：pending')).toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledTimes(1);
  });

  it('以目前 communication version 記錄客戶接受與原因，完成後由 owner contact-state 回讀', async () => {
    mocks.query.mockResolvedValue(pool());
    mocks.createSingleCaregiverPlan.mockResolvedValue(plan());
    mocks.queryContactState
      .mockResolvedValueOnce(contactState())
      .mockResolvedValueOnce(contactState('manually_confirmed', 'accepted'));
    mocks.recordCustomerDecision.mockResolvedValue({
      event_id: 91,
      communication_version: 5,
      source: 'manual',
      willingness: null,
      customer_decision: 'accepted',
    });

    render(<OrderFormalRecommendationPanel caseNo="CASE-RECOMMEND" />);
    await createFormalPlan();
    expect(await screen.findByText('目前決定：pending')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), {
      target: { value: '電話確認接受正式推薦。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄方案 51 客戶接受' }));

    await waitFor(() => expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(
      'CASE-RECOMMEND',
      51,
      4,
      'accepted',
      '電話確認接受正式推薦。',
    ));
    await waitFor(() => expect(mocks.queryContactState).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('目前決定：accepted')).toBeInTheDocument();
    expect(screen.queryByText('客戶拒絕正式推薦')).not.toBeInTheDocument();
  });

  it('客戶拒絕後以 owner contact-state 回讀 declined 並顯示正式阻礙', async () => {
    mocks.query.mockResolvedValue(pool());
    mocks.createSingleCaregiverPlan.mockResolvedValue(plan());
    mocks.queryContactState
      .mockResolvedValueOnce(contactState())
      .mockResolvedValueOnce(contactState('manually_confirmed', 'declined'));
    mocks.recordCustomerDecision.mockResolvedValue({
      event_id: 92,
      communication_version: 5,
      source: 'manual',
      willingness: null,
      customer_decision: 'declined',
    });

    render(<OrderFormalRecommendationPanel caseNo="CASE-RECOMMEND" />);
    await createFormalPlan();
    expect(await screen.findByText('目前決定：pending')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('方案 51 客戶決策依據'), {
      target: { value: '客戶表示目前不接受此推薦。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '記錄方案 51 客戶拒絕' }));

    await waitFor(() => expect(mocks.recordCustomerDecision).toHaveBeenCalledWith(
      'CASE-RECOMMEND',
      51,
      4,
      'declined',
      '客戶表示目前不接受此推薦。',
    ));
    expect(await screen.findByText('目前決定：declined')).toBeInTheDocument();
    expect(screen.getByText('客戶拒絕正式推薦')).toBeInTheDocument();
    expect(screen.getByText('目前正式方案受阻；請依後續 owner 流程處理。')).toBeInTheDocument();
  });

  it('owner candidate query 不可用時 fail closed，不建立方案、讀取狀態或記錄客戶決定', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    render(<OrderFormalRecommendationPanel caseNo="CASE-RECOMMEND" />);

    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));

    expect(await screen.findByText('candidate pool unavailable')).toBeInTheDocument();
    expect(screen.getByText('正式推薦候選不可用')).toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(mocks.queryContactState).not.toHaveBeenCalled();
    expect(mocks.recordCustomerDecision).not.toHaveBeenCalled();
  });
});
