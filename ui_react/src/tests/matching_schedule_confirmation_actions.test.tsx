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
import { assignmentPlanMutationClient } from '../api/scheduling/assignment_plan_mutation_client';
import { ordersQueryClient } from '../api/orders/order_query_client';
import { orderMutationFlowStore } from '../adapters/orders/order_mutation_flow_store';

afterEach(() => {
  orderMutationFlowStore.clearAll();
  vi.restoreAllMocks();
});

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
  it('retains the accepted job after parent readback failure and retries only observation', async () => {
    vi.spyOn(matchingScheduleConfirmationClient, 'query').mockResolvedValue({ ...sent, gate_passed: true });
    vi.spyOn(assignmentPlanMutationClient, 'preview').mockResolvedValue({
      case_no: sent.case_no, order_version: 4, scheduling_version: 7, scheduling_generation: 2,
      client_finance_version: 3, payroll_version: 2, cancelled_assignment_ids: [],
      assignments: [{
        assignment_id: null, candidate_key: null, sequence: 1, staff_id: 9,
        assigned_start_date: '2026-08-03', assigned_end_date: '2026-08-05',
        official_service_dates: ['2026-08-03', '2026-08-05'], actual_hours: null, lineage_source_assignment_ids: [],
      }], buffers: [], client_finance_impact: {}, payroll_impact: {}, orders_impact: {},
      preview_fingerprint: 'a'.repeat(64),
    });
    const apply = vi.spyOn(assignmentPlanMutationClient, 'apply').mockResolvedValue({ job_id: 'job-1' } as Awaited<ReturnType<typeof assignmentPlanMutationClient.apply>>);
    const queryJob = vi.spyOn(assignmentPlanMutationClient, 'queryJob').mockResolvedValue({
      job_id: 'job-1', status: 'succeeded', command_type: 'assignment_plan_apply', attempt_count: 1, max_attempts: 3,
      outcome: { kind: 'success', schema_version: 1, result_reference: `assignment_plan:${sent.case_no}` },
    });
    vi.spyOn(ordersQueryClient, 'getAssignmentPlan').mockResolvedValue({
      case_no: sent.case_no, scheduling_version: 8, scheduling_generation: 2,
      assignments: [{
        staff_id: 9, assigned_start_date: '2026-08-03', assigned_end_date: '2026-08-05',
        official_service_dates: ['2026-08-03', '2026-08-05'],
      }],
    } as Awaited<ReturnType<typeof ordersQueryClient.getAssignmentPlan>>);
    const onCompleted = vi.fn().mockRejectedValueOnce(new Error('父頁回讀失敗')).mockResolvedValueOnce(undefined);
    render(<MatchingScheduleAndAssignmentActions caseNo={sent.case_no} planId={12}
      planSegments={[{ segmentId: 17, sequence: 1, staffId: 9, assignedStartDate: '2026-08-03', assignedEndDate: '2026-08-05' }]}
      waitingLockAcquired assignmentExists={false} onAssignmentCompleted={onCompleted} />);
    fireEvent.click(await screen.findByRole('button', { name: '檢查建立正式排班影響' }));
    fireEvent.change(await screen.findByLabelText('正式排班原因'), { target: { value: '驗收正式排班' } });
    fireEvent.click(screen.getByRole('checkbox', { name: '我已核對月嫂、日期、契約與訂金。' }));
    fireEvent.click(screen.getByRole('button', { name: '確認套用正式排班' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('父頁回讀失敗');
    expect(screen.queryByText('正式排班已完成並回讀一致。')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '確認套用正式排班' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '檢查建立正式排班影響' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: '重新查詢正式排班結果' }));
    expect(await screen.findByText('正式排班已完成並回讀一致。')).toBeInTheDocument();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(queryJob).toHaveBeenCalledTimes(2);
  });

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
    vi.spyOn(sessionClient, 'getUser').mockReturnValue({ username: 'operator-1' } as never);
    vi.spyOn(matchingScheduleConfirmationClient, 'query').mockResolvedValueOnce(notSent).mockResolvedValue(sent);
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

    await waitFor(() => expect(send).toHaveBeenCalledWith(
      'CASE-M3-RECIPIENT-001', 12,
      expect.objectContaining({
        idempotencyKey: expect.stringMatching(/^schedule-send-/),
        expectedActor: 'operator-1',
      }),
    ));
    expect((await screen.findByText('客戶')).closest('article')).toHaveTextContent('客戶｜待確認｜LINE 等待發送');
    expect(screen.getByText('月嫂區段 #17').closest('article')).toHaveTextContent('月嫂區段 #17｜待確認｜LINE 等待發送');
    expect(screen.getByText('客戶與所有月嫂皆確認後，才可建立正式排班。')).toBeInTheDocument();
  });
});
