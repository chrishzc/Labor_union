/**
 * File: matching_manual_communication_actions.test.tsx
 * Description: 驗證媒合資訊與客戶履歷人工證據皆須 Preview、勾選確認、Apply 與 receipt。
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  CandidateManualInformationActions,
  CustomerProfilesManualActions,
} from '../components/MatchingManualCommunicationActions';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { matchingPlanCommunicationClient } from '../api/scheduling/matching_plan_communication_client';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('MatchingManualCommunicationActions', () => {
  it('keeps candidate information Apply locked until Preview is explicitly confirmed', async () => {
    const onCommitted = vi.fn().mockResolvedValue(undefined);
    const preview = {
      case_no: 'CASE-1', pool_id: 3, candidate_id: 7, staff_id: 31, info_type: 1 as const,
      confirmation_method: 'phone' as const, reason: '電話逐項說明案況', expected_version: 4,
      actor: 'operator-1',
      current_status: null, preview_fingerprint: 'a'.repeat(64), apply_allowed: true as const,
    };
    vi.spyOn(candidateContactPoolClient, 'previewManualInformation').mockResolvedValue(preview);
    vi.spyOn(candidateContactPoolClient, 'applyManualInformation').mockResolvedValue({
      status: 'recorded', event_id: 51, pool_version: 51,
      delivery_status: 'manually_confirmed', confirmation_method: 'phone',
    });
    render(<CandidateManualInformationActions caseNo="CASE-1" candidateId={7} infoType={1} disabledReason={null} onCommitted={onCommitted} />);

    fireEvent.change(screen.getByLabelText('資訊-1 人工確認依據'), { target: { value: '電話逐項說明案況' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查人工已提供資訊的影響' }));
    await screen.findByText(/目前聯繫狀態已核對/);
    const apply = screen.getByRole('button', { name: '確認留存人工資訊證據' });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/我已核對候選人/));
    fireEvent.click(apply);

    await screen.findByText('人工確認紀錄已留存。');
    expect(onCommitted).toHaveBeenCalledTimes(1);
  });

  it('records manual customer-profile delivery without presenting it as LINE sent', async () => {
    const onCommitted = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(matchingPlanCommunicationClient, 'queryContactState').mockResolvedValue({
      plan: { id: 12, case_no: 'CASE-1', communication_version: 3, status: 'proposed', is_active: 1 },
      segments: [{ segment_id: 21, willingness: 'willing' }],
      all_willing: true,
      customer_decision: 'pending',
      customer_profiles_status: null,
      customer_profiles_manual_confirmation: null,
    });
    const preview = {
      case_no: 'CASE-1', plan_id: 12, expected_version: 3, segment_ids: [21],
      confirmation_method: 'phone' as const, reason: '電話提供履歷並確認收到',
      preview_fingerprint: 'b'.repeat(64), apply_allowed: true,
    };
    vi.spyOn(matchingPlanCommunicationClient, 'previewManualCustomerProfiles').mockResolvedValue(preview);
    vi.spyOn(matchingPlanCommunicationClient, 'applyManualCustomerProfiles').mockResolvedValue({
      case_no: 'CASE-1', plan_id: 12, communication_version: 3, event_ids: [61],
      confirmation_method: 'phone', preview_fingerprint: 'b'.repeat(64), replayed: false,
    });
    const view = render(<CustomerProfilesManualActions caseNo="CASE-1" planId={12} currentStatus={null} onCommitted={onCommitted} />);

    fireEvent.change(screen.getByLabelText('履歷人工送達依據'), { target: { value: '電話提供履歷並確認收到' } });
    fireEvent.click(screen.getByRole('button', { name: '檢查人工已送達履歷的影響' }));
    await screen.findByText(/方案 #12/);
    fireEvent.click(screen.getByLabelText(/我已核對正式方案/));
    fireEvent.click(screen.getByRole('button', { name: '確認留存人工履歷送達證據' }));

    await screen.findByText('客戶履歷人工送達紀錄已留存。');
    await waitFor(() => expect(onCommitted).toHaveBeenCalledTimes(1));
    view.rerender(<CustomerProfilesManualActions caseNo="CASE-1" planId={12} currentStatus="manually_confirmed" onCommitted={onCommitted} />);
    expect(screen.getByText('履歷傳達根事實：manually_confirmed')).toBeInTheDocument();
    expect(screen.getByText('客戶履歷人工送達紀錄已留存。')).toBeInTheDocument();
    expect(screen.queryByText(/LINE.*成功|LINE sent/i)).not.toBeInTheDocument();
  });
});
