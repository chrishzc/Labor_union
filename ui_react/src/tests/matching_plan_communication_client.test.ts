/**
 * File: matching_plan_communication_client.test.ts
 * Description: 驗證正式方案履歷可靠發送、人工送達證據與人工客戶決策的 typed 契約。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { sessionClient } from '../api/auth/session_client';
import { matchingPlanCommunicationClient } from '../api/scheduling/matching_plan_communication_client';
import { transport } from '../api/shared/transport';

describe('matchingPlanCommunicationClient', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('volatile-token');
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
  });

  it('records an accepted decision with the current communication version', async () => {
    const put = vi.spyOn(transport, 'put').mockResolvedValue({
      success: true,
      message: 'ok',
      data: {
        event_id: 31,
        communication_version: 4,
        source: 'manual',
        willingness: null,
        customer_decision: 'accepted',
      },
      error: null,
    });

    await expect(matchingPlanCommunicationClient.recordCustomerDecision(
      'CASE-1', 12, 3, 'accepted', '電話已確認接受方案。',
    )).resolves.toMatchObject({ event_id: 31, customer_decision: 'accepted' });
    expect(put).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/matching-plans/12/customer-decision',
      expect.objectContaining({ actor: 'operator-1', expected_version: 3, decision: 'accepted' }),
      { token: 'volatile-token' },
    );
  });

  it('fails closed when the response version regresses', async () => {
    vi.spyOn(transport, 'put').mockResolvedValue({
      success: true,
      message: 'ok',
      data: {
        event_id: 31,
        communication_version: 2,
        source: 'manual',
        willingness: null,
        customer_decision: 'accepted',
      },
      error: null,
    });

    await expect(matchingPlanCommunicationClient.recordCustomerDecision(
      'CASE-1', 12, 3, 'accepted', '電話已確認接受方案。',
    )).rejects.toThrow('版本倒退');
  });

  it('creates a typed customer-profile delivery task before a customer decision', async () => {
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: '已建立客戶月嫂小卡與確認按鈕的可靠發送任務',
      data: {
        intent_id: 41,
        line_delivery_task_id: 77,
        delivery_status: 'projected',
        notification_kind: 'customer_profiles',
      },
      error: null,
    });

    await expect(matchingPlanCommunicationClient.sendCustomerProfiles(
      'CASE-1', 12, 3, '已確認月嫂可承接，請客戶檢視履歷。',
    )).resolves.toMatchObject({ intent_id: 41, line_delivery_task_id: 77 });
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-1/matching-plans/12/resumes',
      expect.objectContaining({ actor: 'operator-1', expected_version: 3 }),
      { token: 'volatile-token' },
    );
  });

  it('uses Preview then Apply without claiming LINE delivery for manual profile evidence', async () => {
    const post = vi.spyOn(transport, 'post')
      .mockResolvedValueOnce({
        success: true,
        message: 'preview',
        data: {
          case_no: 'CASE-1',
          plan_id: 12,
          expected_version: 3,
          segment_ids: [21],
          confirmation_method: 'phone',
          reason: '電話提供履歷並逐項確認',
          preview_fingerprint: 'b'.repeat(64),
          apply_allowed: true,
        },
        error: null,
      })
      .mockResolvedValueOnce({
        success: true,
        message: 'applied',
        data: {
          case_no: 'CASE-1',
          plan_id: 12,
          communication_version: 3,
          event_ids: [91],
          confirmation_method: 'phone',
          preview_fingerprint: 'b'.repeat(64),
          replayed: false,
        },
        error: null,
      });

    const preview = await matchingPlanCommunicationClient.previewManualCustomerProfiles(
      'CASE-1', 12, 3, 'phone', '電話提供履歷並逐項確認',
    );
    await expect(matchingPlanCommunicationClient.applyManualCustomerProfiles(preview)).resolves.toMatchObject({
      event_ids: [91],
      replayed: false,
    });

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/api/v1/orders/CASE-1/matching-plans/12/resumes/manual-confirmation/preview',
      expect.objectContaining({ expected_version: 3, confirmation_method: 'phone' }),
      { token: 'volatile-token' },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/api/v1/orders/CASE-1/matching-plans/12/resumes/manual-confirmation',
      expect.objectContaining({ preview_fingerprint: 'b'.repeat(64) }),
      { token: 'volatile-token' },
    );
  });
});
