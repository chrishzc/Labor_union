/** Typed transport contract for current-plan national-holiday work agreements. */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { matchingPlanCommunicationClient } from '../../../../../../../api/scheduling/matching_plan_communication_client';
import { transport } from '../../../../../../../api/shared/transport';

describe('current-plan holiday-work agreement transport', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('volatile-token');
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
  });

  it('uses Preview then Apply with each participant tied to the same plan version', async () => {
    const post = vi.spyOn(transport, 'post')
      .mockResolvedValueOnce({ success: true, message: 'preview', error: null, data: {
        case_no: 'CASE-1', plan_id: 12, expected_version: 3, holiday_date: '2026-03-02',
        agreement_status: 'accepted', participant_decisions: [
          { participant_role: 'customer', segment_id: null, decision: 'accepted' },
          { participant_role: 'caregiver', segment_id: 21, decision: 'accepted' },
        ], preview_fingerprint: 'c'.repeat(64), apply_allowed: true,
      } })
      .mockResolvedValueOnce({ success: true, message: 'applied', error: null, data: {
        agreement_id: 73, plan_id: 12, holiday_date: '2026-03-02', plan_version: 3,
        agreement_status: 'accepted', participant_decisions: [
          { participant_role: 'customer', segment_id: null, decision: 'accepted' },
          { participant_role: 'caregiver', segment_id: 21, decision: 'accepted' },
        ], replayed: false,
      } });
    const decisions = [
      { participant_role: 'customer' as const, segment_id: null, decision: 'accepted' as const },
      { participant_role: 'caregiver' as const, segment_id: 21, decision: 'accepted' as const },
    ];

    const preview = await matchingPlanCommunicationClient.previewHolidayWorkAgreement(
      'CASE-1', 12, 3, '2026-03-02', decisions, '電話逐一確認雙方同意國定假日上班。',
    );
    await expect(matchingPlanCommunicationClient.applyHolidayWorkAgreement(
      preview, '電話逐一確認雙方同意國定假日上班。',
    )).resolves.toMatchObject({ agreement_id: 73, agreement_status: 'accepted' });

    expect(post).toHaveBeenNthCalledWith(
      1, '/api/v1/orders/CASE-1/matching-plans/12/holiday-work-agreements/preview',
      expect.objectContaining({ actor: 'operator-1', expected_version: 3, participant_decisions: decisions }), { token: 'volatile-token' },
    );
    expect(post).toHaveBeenNthCalledWith(
      2, '/api/v1/orders/CASE-1/matching-plans/12/holiday-work-agreements',
      expect.objectContaining({ preview_fingerprint: 'c'.repeat(64), participant_decisions: decisions }), { token: 'volatile-token' },
    );
  });
});
