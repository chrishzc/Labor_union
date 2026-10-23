import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderFormalRecommendationPanel } from '../../../../../../../components/OrderFormalRecommendationPanel';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { orderMutationFlowStore } from '../../../../../../../adapters/orders/order_mutation_flow_store';

const mocks = vi.hoisted(() => ({
  queryPlan: vi.fn(),
  queryContactState: vi.fn(),
  previewCustomerConfirmation: vi.fn(),
  sendCustomerConfirmation: vi.fn(),
  recordCustomerDecision: vi.fn(),
}));

vi.mock('../../../../../../../api/scheduling/waiting_deposit_lock_client', () => ({
  waitingDepositLockClient: {
    queryPlan: mocks.queryPlan,
  },
}));
vi.mock('../../../../../../../api/scheduling/matching_plan_communication_client', () => ({
  matchingPlanCommunicationClient: {
    queryContactState: mocks.queryContactState,
    previewCustomerConfirmation: mocks.previewCustomerConfirmation,
    sendCustomerConfirmation: mocks.sendCustomerConfirmation,
    recordCustomerDecision: mocks.recordCustomerDecision,
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
const CASE_NO = 'CASE-277';
let customerProfilesStatus: string | null;
let communicationVersion: number;
let customerDecision: 'pending' | 'accepted' | 'declined';

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
    customer_decision: customerDecision,
    customer_profiles_status: customerProfilesStatus,
    customer_confirmation_status: customerProfilesStatus,
    customer_profiles_manual_confirmation: null,
  };
}

describe('issue #277 stage-5 customer recommendation ordering', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.values(mocks).forEach((mock) => mock.mockReset());
    orderMutationFlowStore.clearAll();
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-test' } as never);
    customerProfilesStatus = null;
    communicationVersion = 4;
    customerDecision = 'pending';
    mocks.queryPlan.mockImplementation(async () => activePlan());
    mocks.queryContactState.mockImplementation(async () => structuredClone(contactState()));
    mocks.previewCustomerConfirmation.mockImplementation(async (_caseNo, _planId, expectedVersion) => ({
      case_no: CASE_NO, plan_id: 51, expected_version: expectedVersion,
      order_information_1_ready: true, order_information_2_ready: true,
      weekly_service_ready: true, weekly_service_row_count: 3,
      order_information_1: [], order_information_2: [], weekly_service_rows: [],
      caregiver_resumes: [{ staff_id: 8892, staff_name: '測試月嫂', ready: true, filename: 'resume-A.pdf', version: 1, blocker: null }],
      blockers: [], send_allowed: true,
    }));
    mocks.sendCustomerConfirmation.mockImplementation(async () => {
      customerProfilesStatus = 'pending';
      communicationVersion = 5;
      return {
        intent_id: 81,
        line_delivery_task_id: null,
        delivery_status: 'pending',
        notification_kind: 'customer_profiles',
      };
    });
    mocks.recordCustomerDecision.mockImplementation(async (_caseNo, _planId, _version, decision, _reason, eventKey) => {
      customerDecision = decision;
      communicationVersion = 5;
      return {
        event_id: 91, case_no: CASE_NO, plan_id: 51, segment_id: null,
        event_key: eventKey, communication_version: communicationVersion, source: 'admin',
        willingness: null, customer_decision: decision,
      };
    });
  });

  it('可寄送完整確認資訊，建立寄送工作不代表客戶已接受', async () => {
    render(<OrderFormalRecommendationPanel caseNo={CASE_NO} />);

    const send = await screen.findByRole('button', { name: '寄送確認資訊給客戶' });
    await waitFor(() => expect(send).toBeEnabled());
    fireEvent.click(send);

    await waitFor(() => expect(mocks.sendCustomerConfirmation).toHaveBeenCalledWith(
      CASE_NO,
      51,
      4,
      '請查收正式推薦月嫂的完整確認資訊。',
      expect.stringMatching(/^orders-customer-confirmation-51-/),
    ));
    await screen.findByText('確認資訊發送工作已建立：#81（狀態：等待系統寄送）；尚不代表 LINE 已送達。');
    expect(mocks.recordCustomerDecision).not.toHaveBeenCalled();
    expect(customerDecision).toBe('pending');
  });

  it.each([
    { decision: 'accepted', inputReason: '', savedReason: '' },
    { decision: 'declined', inputReason: '', savedReason: '' },
    { decision: 'accepted', inputReason: '   ', savedReason: '' },
    { decision: 'accepted', inputReason: ' 電話確認客戶接受此推薦。 ', savedReason: '電話確認客戶接受此推薦。' },
  ] as const)('客戶回覆依據選填，未寄送 LINE 也可保存人工決定 $decision、依據「$inputReason」並正式回讀', async ({ decision, inputReason, savedReason }) => {
    const onObserved = vi.fn();
    render(<OrderFormalRecommendationPanel caseNo={CASE_NO} onObserved={onObserved} />);
    fireEvent.click(await screen.findByRole('button', { name: '手動記錄客戶決定' }));
    const reason = screen.getByLabelText('方案 51 客戶決策依據');
    expect(reason).toHaveValue('');
    expect(reason).not.toBeRequired();
    expect(reason).toHaveAttribute('maxlength', '500');
    expect(screen.getByText('客戶回覆依據（選填）')).toBeInTheDocument();
    fireEvent.change(reason, { target: { value: inputReason } });
    const save = screen.getByRole('button', { name: decision === 'accepted' ? '記錄方案 51 客戶接受' : '記錄方案 51 客戶拒絕' });
    await waitFor(() => expect(save).toBeEnabled());
    fireEvent.click(save);
    await screen.findByText('客戶決定已完成正式回讀。');
    expect(mocks.recordCustomerDecision).toHaveBeenCalledExactlyOnceWith(
      CASE_NO, 51, 4, decision, savedReason, expect.stringMatching(/^orders-formal-manual-customer-decision-51-/), 'operator-test',
    );
    expect(mocks.queryContactState).toHaveBeenCalledTimes(3);
    expect(customerDecision).toBe(decision);
    expect(onObserved).toHaveBeenCalledOnce();
    expect(mocks.sendCustomerConfirmation).not.toHaveBeenCalled();
  });
});
