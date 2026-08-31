/**
 * File: matching_schedule_confirmation_actions.test.tsx
 * Description: 保護 M3 current 日期表 recipient 發送入口與 fresh readback。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  matchingScheduleConfirmationClient,
  type MatchingScheduleState,
} from '../api/scheduling/matching_schedule_confirmation_client';
import { sessionClient } from '../api/auth/session_client';
import { transport } from '../api/shared/transport';
import { MatchingScheduleAndAssignmentActions } from '../components/MatchingScheduleAndAssignmentActions';

afterEach(() => vi.restoreAllMocks());

const schedulePreview: MatchingScheduleState['schedule_preview'] = {
  week_grouping_policy: 'calendar_week_sunday_to_saturday_v1',
  total_service_days: 2,
  total_weeks: 1,
  weeks: [{
    week_number: 1,
    period_start: '2026-08-02',
    period_end: '2026-08-08',
    service_dates: ['2026-08-03', '2026-08-05'],
    service_day_count: 2,
  }],
  recipient_schedules: [
    {
      audience_type: 'customer',
      segment_id: null,
      total_service_days: 2,
      total_weeks: 1,
      weeks: [{
        week_number: 1,
        period_start: '2026-08-02',
        period_end: '2026-08-08',
        service_dates: ['2026-08-03', '2026-08-05'],
        service_day_count: 2,
      }],
    },
    {
      audience_type: 'caregiver',
      segment_id: 17,
      total_service_days: 2,
      total_weeks: 1,
      weeks: [{
        week_number: 1,
        period_start: '2026-08-02',
        period_end: '2026-08-08',
        service_dates: ['2026-08-03', '2026-08-05'],
        service_day_count: 2,
      }],
    },
  ],
};

const notSent: MatchingScheduleState = {
  case_no: 'CASE-M3-RECIPIENT-001',
  plan_id: 12,
  confirmed_service_date_version: 3,
  snapshot_id: null,
  snapshot_status: 'not_sent',
  schedule_preview: schedulePreview,
  outdated_schedule_preview: null,
  recipients: [],
  gate_passed: false,
};

const sent: MatchingScheduleState = {
  ...notSent,
  snapshot_id: 31,
  snapshot_status: 'sent',
  recipients: [
    {
      recipient_snapshot_id: 41,
      audience_type: 'customer',
      segment_id: null,
      delivery_status: 'queued',
      confirmation_status: 'pending',
      confirmation_source: null,
      confirmation_reason: null,
      confirmation_occurred_at_utc: null,
    },
    {
      recipient_snapshot_id: 42,
      audience_type: 'caregiver',
      segment_id: 17,
      delivery_status: 'queued',
      confirmation_status: 'pending',
      confirmation_source: null,
      confirmation_reason: null,
      confirmation_occurred_at_utc: null,
    },
  ],
};

describe('M3 日期表 recipient 確認', () => {
  it('以 authenticated typed client 建立單次 send intent 並驗證 identity readback', async () => {
    vi.spyOn(sessionClient, 'getToken').mockReturnValue('volatile-token');
    const post = vi.spyOn(transport, 'post').mockResolvedValue({
      success: true,
      message: '日期表已排入發送佇列',
      data: sent,
      error: null,
    });

    await expect(
      matchingScheduleConfirmationClient.send('CASE-M3-RECIPIENT-001', 12),
    ).resolves.toEqual(sent);
    expect(post).toHaveBeenCalledWith(
      '/api/v1/orders/CASE-M3-RECIPIENT-001/matching-plans/12/schedule-confirmation/send',
      undefined,
      {
        token: 'volatile-token',
        headers: {
          'Idempotency-Key': expect.stringMatching(
            /^matching-schedule-send-CASE-M3-RECIPIENT-001-12-/,
          ),
        },
      },
    );
  });

  it('由 current Query 明確發送後顯示 backend fresh recipient readback', async () => {
    vi.spyOn(matchingScheduleConfirmationClient, 'query').mockResolvedValue(notSent);
    const send = vi.spyOn(matchingScheduleConfirmationClient, 'send').mockResolvedValue(sent);

    render(
      <MatchingScheduleAndAssignmentActions
        caseNo="CASE-M3-RECIPIENT-001"
        planId={12}
        planSegments={[{
          segmentId: 17,
          sequence: 1,
          staffId: 9,
          assignedStartDate: '2026-08-03',
          assignedEndDate: '2026-08-05',
        }]}
        waitingLockAcquired={false}
        assignmentExists={false}
        onAssignmentCompleted={vi.fn()}
      />,
    );

    await screen.findByText(/尚未建立日期表確認快照/);
    fireEvent.click(screen.getByRole('button', { name: '透過 LINE 發送日期表' }));

    await waitFor(() => expect(send).toHaveBeenCalledWith('CASE-M3-RECIPIENT-001', 12));
    expect((await screen.findByText('客戶')).closest('article')).toHaveTextContent('客戶｜待確認｜LINE queued');
    expect(screen.getByText('月嫂區段 #17').closest('article')).toHaveTextContent('月嫂區段 #17｜待確認｜LINE queued');
    expect(screen.getByText('客戶與所有月嫂皆確認後，才可建立正式排班。')).toBeInTheDocument();
  });
});
