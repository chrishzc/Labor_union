/**
 * File: MatchingScheduleAndAssignmentActions.tsx
 * Description: 以人工日期表確認及正式排班 Preview／Apply 完成 waiting-lock conversion。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { ordersQueryClient } from '../api/orders/order_query_client';
import {
  assignmentPlanMutationClient,
  type AssignmentPlanJob,
  type AssignmentPlanPreview,
  type AssignmentPlanSegmentInput,
} from '../api/scheduling/assignment_plan_mutation_client';
import {
  matchingScheduleConfirmationClient,
  type MatchingScheduleManualPreview,
  type MatchingScheduleState,
} from '../api/scheduling/matching_schedule_confirmation_client';

interface PlanSegment {
  segmentId: number;
  sequence: number;
  staffId: number;
  assignedStartDate: string;
  assignedEndDate: string;
}

interface Props {
  caseNo: string;
  planId: number;
  planSegments: readonly PlanSegment[];
  waitingLockAcquired: boolean;
  assignmentExists: boolean;
  onAssignmentCompleted: () => Promise<void>;
}

export const MatchingScheduleAndAssignmentActions: React.FC<Props> = ({
  caseNo,
  planId,
  planSegments,
  waitingLockAcquired,
  assignmentExists,
  onAssignmentCompleted,
}) => {
  const [schedule, setSchedule] = useState<MatchingScheduleState | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [manualPreview, setManualPreview] = useState<MatchingScheduleManualPreview | null>(null);
  const [manualReason, setManualReason] = useState('');
  const [manualConfirmed, setManualConfirmed] = useState(false);
  const [scheduleBusy, setScheduleBusy] = useState<string | null>(null);
  const [recipientReasons, setRecipientReasons] = useState<Record<number, string>>({});
  const [recipientPreviewId, setRecipientPreviewId] = useState<number | null>(null);
  const [assignmentPreview, setAssignmentPreview] = useState<AssignmentPlanPreview | null>(null);
  const [assignmentReason, setAssignmentReason] = useState('');
  const [assignmentConfirmed, setAssignmentConfirmed] = useState(false);
  const [assignmentJob, setAssignmentJob] = useState<AssignmentPlanJob | null>(null);
  const [assignmentJobId, setAssignmentJobId] = useState<string | null>(null);
  const [assignmentBusy, setAssignmentBusy] = useState(false);
  const [assignmentError, setAssignmentError] = useState<string | null>(null);
  const [assignmentReadback, setAssignmentReadback] = useState(false);

  useEffect(() => {
    let active = true;
    setSchedule(null);
    setScheduleError(null);
    matchingScheduleConfirmationClient.query(caseNo, planId)
      .then((value) => { if (active) setSchedule(value); })
      .catch((error: unknown) => { if (active) setScheduleError(message(error, '日期表確認狀態載入失敗。')); });
    return () => { active = false; };
  }, [caseNo, planId]);

  const assignmentSegments = useMemo<AssignmentPlanSegmentInput[]>(() => {
    if (!schedule) return [];
    return [...planSegments]
      .sort((left, right) => left.sequence - right.sequence)
      .map((segment) => {
        const recipient = schedule.schedule_preview.recipient_schedules.find(
          (item) => item.audience_type === 'caregiver' && item.segment_id === segment.segmentId,
        );
        return {
          staff_id: segment.staffId,
          assigned_start_date: segment.assignedStartDate,
          assigned_end_date: segment.assignedEndDate,
          official_service_dates: recipient?.weeks.flatMap((week) => week.service_dates) ?? [],
        };
      });
  }, [planSegments, schedule]);

  const previewManual = async () => {
    setScheduleBusy('manual-preview');
    setScheduleError(null);
    try {
      setManualPreview(await matchingScheduleConfirmationClient.previewManual(caseNo, planId));
    } catch (error) {
      setScheduleError(message(error, '無法檢查人工日期表確認影響。'));
    } finally {
      setScheduleBusy(null);
    }
  };

  const applyManual = async () => {
    if (!manualPreview) return;
    setScheduleBusy('manual-apply');
    setScheduleError(null);
    try {
      const observed = await matchingScheduleConfirmationClient.applyManual(caseNo, planId, manualPreview, manualReason);
      setSchedule(observed);
      setManualPreview(null);
      setManualConfirmed(false);
    } catch (error) {
      setScheduleError(message(error, '無法留存人工日期表確認。'));
    } finally {
      setScheduleBusy(null);
    }
  };

  const confirmRecipient = async (recipientId: number) => {
    setScheduleBusy(`recipient-${recipientId}`);
    setScheduleError(null);
    try {
      const observed = await matchingScheduleConfirmationClient.confirmManual(recipientId, recipientReasons[recipientId] ?? '');
      if (observed.case_no !== caseNo || observed.plan_id !== planId) throw new Error('人工確認回讀 identity 不一致。');
      setSchedule(observed);
      setRecipientPreviewId(null);
    } catch (error) {
      setScheduleError(message(error, '人工日期表確認失敗。'));
    } finally {
      setScheduleBusy(null);
    }
  };

  const previewAssignment = async () => {
    setAssignmentBusy(true);
    setAssignmentError(null);
    try {
      if (assignmentSegments.some((segment) => segment.official_service_dates.length === 0)) {
        throw new Error('正式方案區段與目前日期表無法完整對應。');
      }
      setAssignmentPreview(await assignmentPlanMutationClient.preview(caseNo, assignmentSegments));
      setAssignmentConfirmed(false);
    } catch (error) {
      setAssignmentError(message(error, '無法檢查正式排班影響。'));
    } finally {
      setAssignmentBusy(false);
    }
  };

  const applyAssignment = async () => {
    if (!assignmentPreview) return;
    setAssignmentBusy(true);
    setAssignmentError(null);
    try {
      const accepted = await assignmentPlanMutationClient.apply(caseNo, assignmentSegments, assignmentPreview, assignmentReason);
      setAssignmentJobId(accepted.job_id);
      await observeAssignment(accepted.job_id);
    } catch (error) {
      setAssignmentError(message(error, '無法建立正式排班。'));
    } finally {
      setAssignmentBusy(false);
    }
  };

  const observeAssignment = async (jobId: string) => {
    setAssignmentBusy(true);
    setAssignmentError(null);
    try {
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const observed = await assignmentPlanMutationClient.queryJob(jobId);
        setAssignmentJob(observed);
        if (observed.status === 'failed' || observed.status === 'cancelled') {
          const failure = observed.outcome?.kind === 'failure' ? observed.outcome.error : null;
          throw new Error(failure ? `${failure.message}（${failure.code}）` : `正式排班工作 ${observed.status}。`);
        }
        if (observed.status === 'succeeded') {
          const readback = await ordersQueryClient.getAssignmentPlan(caseNo);
          if (readback.assignments.length !== assignmentSegments.length) throw new Error('正式排班完成後回讀分段數不一致。');
          setAssignmentReadback(true);
          await onAssignmentCompleted();
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error('正式排班仍在處理；請重新查詢結果。');
    } finally {
      setAssignmentBusy(false);
    }
  };

  if (scheduleError && !schedule) return <div role="alert" className="mutation-error-banner">{scheduleError}</div>;
  if (!schedule) return <div role="status">正在載入日期表確認狀態…</div>;

  return (
    <div style={{ display: 'grid', gap: '12px', marginTop: '12px' }} data-surface-id="orders.matching.schedule-confirmation">
      <div style={{ fontWeight: 700 }}>📅 客戶與月嫂確認同一份服務日期表</div>
      <div style={{ fontSize: '0.82rem', color: '#57423b' }}>
        {schedule.schedule_preview.total_service_days} 個服務日｜
        {schedule.schedule_preview.weeks.flatMap((week) => week.service_dates).join('、')}
      </div>
      {scheduleError && <div role="alert" className="mutation-error-banner">{scheduleError}</div>}
      {schedule.snapshot_status === 'not_sent' && (
        <div style={{ display: 'grid', gap: '8px' }}>
          <div role="status">尚未建立日期表確認快照；可等待 LINE 綁定，或以電話／現場／紙本證據人工確認。</div>
          <button type="button" className="matching-action-btn-sm" disabled={scheduleBusy !== null} onClick={() => void previewManual()}>
            {scheduleBusy === 'manual-preview' ? '正在檢查日期表影響…' : '檢查人工日期表確認影響'}
          </button>
          {manualPreview && (
            <>
              <div role="status">預覽已完成；此人工確認不會建立 LINE 發送工作。</div>
              <label>人工快照原因<input aria-label="人工日期表快照原因" maxLength={500} value={manualReason} onChange={(event) => { setManualReason(event.target.value); setManualConfirmed(false); }} /></label>
              <label><input type="checkbox" checked={manualConfirmed} onChange={(event) => setManualConfirmed(event.target.checked)} />我已核對日期表，確認建立人工證據快照。</label>
              <button type="button" className="orders-load-more-btn" disabled={scheduleBusy !== null || !manualConfirmed || !manualReason.trim()} onClick={() => void applyManual()}>
                {scheduleBusy === 'manual-apply' ? '人工快照套用中…' : '確認套用人工日期表快照'}
              </button>
            </>
          )}
        </div>
      )}
      {schedule.recipients.map((recipient) => {
        const label = recipient.audience_type === 'customer' ? '客戶' : `月嫂區段 #${recipient.segment_id}`;
        const confirmed = ['confirmed', 'manually_confirmed'].includes(recipient.confirmation_status);
        return (
          <article key={recipient.recipient_snapshot_id} style={{ border: '1px solid #dec0b6', padding: '10px', borderRadius: '8px' }}>
            <strong>{label}</strong>｜{confirmed ? '已確認' : '待確認'}｜{recipient.delivery_status === 'blocked' ? '未透過 LINE（人工）' : `LINE ${recipient.delivery_status}`}
            {recipient.confirmation_reason && <div>確認原因：{recipient.confirmation_reason}</div>}
            {!confirmed && (
              <div style={{ display: 'grid', gap: '6px', marginTop: '6px' }}>
                <input aria-label={`${label}人工確認原因`} maxLength={500} value={recipientReasons[recipient.recipient_snapshot_id] ?? ''} onChange={(event) => { setRecipientReasons((current) => ({ ...current, [recipient.recipient_snapshot_id]: event.target.value })); setRecipientPreviewId(null); }} placeholder="輸入電話、現場或紙本確認依據" />
                <button type="button" className="matching-action-btn-sm" disabled={!recipientReasons[recipient.recipient_snapshot_id]?.trim()} onClick={() => setRecipientPreviewId(recipient.recipient_snapshot_id)}>檢查{label}人工確認</button>
                {recipientPreviewId === recipient.recipient_snapshot_id && (
                  <button type="button" className="orders-load-more-btn" disabled={scheduleBusy !== null} onClick={() => void confirmRecipient(recipient.recipient_snapshot_id)}>
                    {scheduleBusy === `recipient-${recipient.recipient_snapshot_id}` ? '確認套用中…' : `確認套用${label}人工確認`}
                  </button>
                )}
              </div>
            )}
          </article>
        );
      })}
      <div role="status" style={{ color: schedule.gate_passed ? '#166534' : '#74593f' }}>
        {schedule.gate_passed ? '雙方已確認同一日期版本，可建立正式排班。' : '客戶與所有月嫂皆確認後，才可建立正式排班。'}
      </div>
      {schedule.gate_passed && waitingLockAcquired && !assignmentExists && (
        <div style={{ display: 'grid', gap: '8px', borderTop: '1px solid #dec0b6', paddingTop: '12px' }}>
          <button type="button" className="matching-action-btn-sm" disabled={assignmentBusy || assignmentSegments.length === 0} onClick={() => void previewAssignment()}>{assignmentBusy ? '處理中…' : '檢查建立正式排班影響'}</button>
          {assignmentPreview && (
            <>
              <div role="status">影響檢查：將建立 {assignmentPreview.assignments.length} 段正式指派並轉換等待訂金鎖。</div>
              <label>正式排班原因<input aria-label="正式排班原因" maxLength={500} value={assignmentReason} onChange={(event) => { setAssignmentReason(event.target.value); setAssignmentConfirmed(false); }} /></label>
              <label><input type="checkbox" checked={assignmentConfirmed} onChange={(event) => setAssignmentConfirmed(event.target.checked)} />我已核對月嫂、日期、契約與訂金。</label>
              <button type="button" className="orders-load-more-btn" disabled={assignmentBusy || !assignmentConfirmed || !assignmentReason.trim()} onClick={() => void applyAssignment()}>{assignmentBusy ? '正式排班套用並回讀中…' : '確認套用正式排班'}</button>
            </>
          )}
          {assignmentJobId && !assignmentReadback && (
            <div role="status">{assignmentJob?.status === 'succeeded' ? '正式排班處理已完成，正在核對結果。' : '正式排班處理中。'}</div>
          )}
          {assignmentJobId && assignmentJob?.status !== 'succeeded' && !assignmentBusy && <button type="button" onClick={() => void observeAssignment(assignmentJobId)}>重新查詢正式排班結果</button>}
          {assignmentReadback && <div role="status" style={{ color: '#166534' }}>正式排班已完成並回讀一致。</div>}
          {assignmentError && <div role="alert" className="mutation-error-banner">{assignmentError}</div>}
        </div>
      )}
    </div>
  );
};

function message(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
