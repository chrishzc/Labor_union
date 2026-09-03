import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../components/OrderFormalRecommendationPanel';

const mocks = vi.hoisted(() => ({
  query: vi.fn(),
  createSingleCaregiverPlan: vi.fn(),
  queryContactState: vi.fn(),
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

function contactState(customerProfilesStatus: string | null = 'manually_confirmed') {
  return {
    plan: {
      id: 51,
      case_no: 'CASE-RECOMMEND',
      communication_version: 4,
      status: 'proposed',
      is_active: 1,
    },
    segments: [{ segment_id: 71, willingness: 'willing' }],
    all_willing: true,
    customer_decision: 'pending',
    customer_profiles_status: customerProfilesStatus,
    customer_profiles_manual_confirmation: null,
  };
}

describe('待辦看板 Beta 第 5 階正式推薦媒合方案', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
  });

  it('只讓 active 且 willing 的 owner candidate 建立既有正式媒合方案，並獨立回讀履歷推薦送達狀態', async () => {
    mocks.query.mockResolvedValue(pool());
    mocks.createSingleCaregiverPlan.mockResolvedValue({
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
    });
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
    expect(mocks.createSingleCaregiverPlan).toHaveBeenCalledTimes(1);
  });

  it('owner candidate query 不可用時 fail closed，不建立方案或讀取履歷推薦狀態', async () => {
    mocks.query.mockRejectedValue(new Error('candidate pool unavailable'));
    render(<OrderFormalRecommendationPanel caseNo="CASE-RECOMMEND" />);

    fireEvent.click(screen.getByRole('button', { name: '讀取正式推薦候選' }));

    expect(await screen.findByText('candidate pool unavailable')).toBeInTheDocument();
    expect(screen.getByText('正式推薦候選不可用')).toBeInTheDocument();
    expect(mocks.createSingleCaregiverPlan).not.toHaveBeenCalled();
    expect(mocks.queryContactState).not.toHaveBeenCalled();
  });
});
