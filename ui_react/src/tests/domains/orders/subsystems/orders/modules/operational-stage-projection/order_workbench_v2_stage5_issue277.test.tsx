import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';

const mocks = vi.hoisted(() => ({
  queryPlan: vi.fn(),
  queryContactState: vi.fn(),
  sendCustomerProfiles: vi.fn(),
}));

vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({
  waitingDepositLockClient: {
    queryPlan: mocks.queryPlan,
  },
}));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({
  matchingPlanCommunicationClient: {
    queryContactState: mocks.queryContactState,
    sendCustomerProfiles: mocks.sendCustomerProfiles,
  },
}));
vi.mock('../../../../../../../api/scheduling/candidate_contact_pool_client', () => ({
  candidateContactPoolClient: { query: vi.fn() },
}));
vi.mock('../../../../../../../api/scheduling/matching_candidate_workflow_client', () => ({
  matchingCandidateWorkflowClient: { createSingleCaregiverPlan: vi.fn() },
}));
vi.mock('../../../../../../../api/orders/order_query_client', () => ({
  ordersQueryClient: { getOrderDetail: vi.fn() },
}));
vi.mock('../../../../../../../components/MatchingManualCommunicationActions', () => ({
  CustomerProfilesManualActions: () => null,
}));
vi.mock('../../../../../../../components/HolidayWorkAgreementActions', () => ({
  HolidayWorkAgreementActions: () => null,
}));

const CASE_NO = 'CASE-277';
let customerProfilesStatus: string | null;
let communicationVersion: number;

function activePlan() {
  return {
    planId: 51,
    status: 'proposed',
    activeLockId: null,
    planVersion: 1,
    segments: [{
      segmentId: 71,
      sequence: 1,
      staffId: 8892,
      assignedStartDate: '2026-09-21',
      assignedEndDate: '2026-10-10',
    }],
  };
}

function contactState() {
  return {
    plan: {
      id: 51,
      case_no: CASE_NO,
      communication_version: communicationVersion,
      status: 'proposed',
      is_active: 1,
    },
    segments: [{
      segment_id: 71,
      willingness: 'willing',
    }],
    all_willing: true,
    customer_decision: 'pending',
    customer_profiles_status: customerProfilesStatus,
    customer_profiles_manual_confirmation: null,
  };
}

describe('issue #277 stage-5 customer recommendation ordering', () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    customerProfilesStatus = null;
    communicationVersion = 4;
    mocks.queryPlan.mockImplementation(async () => activePlan());
    mocks.queryContactState.mockImplementation(async () => structuredClone(contactState()));
    mocks.sendCustomerProfiles.mockImplementation(async () => {
      customerProfilesStatus = 'pending';
      communicationVersion = 5;
      return {
        intent_id: 81,
        line_delivery_task_id: null,
        delivery_status: 'pending',
        notification_kind: 'customer_profiles',
      };
    });
  });

  it('requires profile delivery before customer accept or decline can be recorded', async () => {
    render(<OrderFormalRecommendationPanel caseNo={CASE_NO} />);

    const send = await screen.findByRole('button', { name: '寄送履歷給客戶' });
    expect(send).toBeEnabled();
    expect(screen.queryByRole('button', { name: '記錄方案 51 客戶接受' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '記錄方案 51 客戶拒絕' })).not.toBeInTheDocument();

    fireEvent.click(send);

    await waitFor(() => expect(mocks.sendCustomerProfiles).toHaveBeenCalledWith(
      CASE_NO,
      51,
      4,
      '請查收正式推薦月嫂履歷。',
    ));
    await screen.findByText('履歷發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');

    const accept = screen.getByRole('button', { name: '記錄方案 51 客戶接受' });
    const decline = screen.getByRole('button', { name: '記錄方案 51 客戶拒絕' });
    expect(accept).toBeDisabled();
    expect(decline).toBeDisabled();
    expect(screen.getByLabelText('方案 51 客戶決策依據')).toHaveValue('');
  });
});
