/**
 * File: MatchingScheduleAndAssignmentActions.tsx
 * Description: 以人工日期表確認及正式排班 Preview／Apply 完成 waiting-lock conversion。
 */
import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { orderMutationFlowStore, type AssignmentPlanApplyCommand, type ScheduleMutationCommand } from '../adapters/orders/order_mutation_flow_store';
import { ordersQueryClient } from '../api/orders/order_query_client';
import {
  assignmentPlanMutationClient,
  type AssignmentPlanPreview,
  type AssignmentPlanSegmentInput,
} from '../api/scheduling/assignment_plan_mutation_client';
import {
  matchingScheduleConfirmationClient,
  type MatchingScheduleManualPreview,
  type MatchingScheduleState,
} from '../api/scheduling/matching_schedule_confirmation_client';
import { sessionClient } from '../api/auth/session_client';
import { ApiHttpError } from '../api/shared/typed_errors';

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
  const [assignmentBusy, setAssignmentBusy] = useState(false);
  const [assignmentLocalError, setAssignmentLocalError] = useState<string | null>(null);
  const activeAssignmentScope = useRef('');
  const manualPreviewController = useRef<AbortController | null>(null);
  const scheduleObservationController = useRef<AbortController | null>(null);
  const scheduleGeneration = useRef(0);
  const [scheduleNotice, setScheduleNotice] = useState<string | null>(null);
  const scheduleFlow = useSyncExternalStore(
    (listener) => orderMutationFlowStore.subscribe(listener),
    () => orderMutationFlowStore.getScheduleMutation(caseNo, planId),
  );
  const assignmentPreviewController = useRef<AbortController | null>(null);
  const assignmentFlow = useSyncExternalStore(
    (listener) => orderMutationFlowStore.subscribe(listener),
    () => orderMutationFlowStore.getAssignmentPlan(caseNo, planId),
  );

  useEffect(() => {
    const controller = new AbortController();
    scheduleGeneration.current += 1;
    activeAssignmentScope.current = `${caseNo}:${planId}`;
    setScheduleNotice(null);
    setSchedule(null);
    setScheduleError(null);
    setScheduleBusy(null);
    setManualPreview(null);
    setManualReason('');
    setManualConfirmed(false);
    setRecipientReasons({});
    setRecipientPreviewId(null);
    setAssignmentPreview(null);
    setAssignmentReason('');
    setAssignmentConfirmed(false);
    setAssignmentBusy(false);
    setAssignmentLocalError(null);
    matchingScheduleConfirmationClient.query(caseNo, planId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setSchedule(value); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setScheduleError(message(error, '日期表確認狀態載入失敗。')); });
    return () => {
      controller.abort();
      manualPreviewController.current?.abort();
      assignmentPreviewController.current?.abort();
      activeAssignmentScope.current = '';
      scheduleGeneration.current += 1;
      scheduleObservationController.current?.abort();
      const saved = orderMutationFlowStore.getScheduleMutation(caseNo, planId);
      if (saved?.status === 'observing' && saved.receipt) {
        orderMutationFlowStore.setScheduleMutation(caseNo, planId, { ...saved, status: 'observation_failed', error: '尚未讀取到最新日期表，請重新讀取。' });
      }
    };
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
    manualPreviewController.current?.abort();
    const controller = new AbortController();
    manualPreviewController.current = controller;
    setScheduleBusy('manual-preview');
    setManualPreview(null);
    setManualConfirmed(false);
    setScheduleError(null);
    try {
      const preview = await matchingScheduleConfirmationClient.previewManual(caseNo, planId, controller.signal);
      if (!controller.signal.aborted) setManualPreview(preview);
    } catch (error) {
      if (!controller.signal.aborted) setScheduleError(message(error, '無法檢查人工日期表確認影響。'));
    } finally {
      if (!controller.signal.aborted) setScheduleBusy(null);
    }
  };

  const observeSchedule = async (command: ScheduleMutationCommand) => {
    const saved = orderMutationFlowStore.getScheduleMutation(command.caseNo, command.planId);
    if (!saved?.receipt || saved.status === 'observing') return;
    scheduleObservationController.current?.abort();
    const controller = new AbortController();
    scheduleObservationController.current = controller;
    const generation = scheduleGeneration.current;
    orderMutationFlowStore.setScheduleMutation(command.caseNo, command.planId, { ...saved, status: 'observing', error: null });
    try {
      const observed = await matchingScheduleConfirmationClient.query(command.caseNo, command.planId, controller.signal);
      if (controller.signal.aborted || generation !== scheduleGeneration.current) return;
      assertScheduleReadback(observed, saved.receipt, command);
      setSchedule(observed);
      setManualPreview(null);
      setManualConfirmed(false);
      setRecipientPreviewId(null);
      setScheduleNotice('日期表結果已更新。');
      orderMutationFlowStore.clearScheduleMutation(command.caseNo, command.planId);
    } catch (error) {
      if (controller.signal.aborted || generation !== scheduleGeneration.current) return;
      orderMutationFlowStore.setScheduleMutation(command.caseNo, command.planId, {
        ...saved, status: 'observation_failed', error: message(error, '日期表已處理，請重新讀取最新結果。'),
      });
    }
  };

  const submitSchedule = async (command: ScheduleMutationCommand) => {
    const existing = orderMutationFlowStore.getScheduleMutation(command.caseNo, command.planId);
    if (existing && existing.status !== 'outcome_unknown') return;
    const recoveringUnknown = existing?.status === 'outcome_unknown';
    const generation = scheduleGeneration.current;
    setScheduleError(null);
    setScheduleNotice(null);
    orderMutationFlowStore.setScheduleMutation(command.caseNo, command.planId, { status: 'applying', command, receipt: null, error: null });
    let receipt: MatchingScheduleState;
    try {
      receipt = command.kind === 'send'
        ? await matchingScheduleConfirmationClient.send(command.caseNo, command.planId, command.identity)
        : command.kind === 'manual'
          ? await matchingScheduleConfirmationClient.applyManual(command.caseNo, command.planId, command.preview, command.reason, command.identity)
          : await matchingScheduleConfirmationClient.confirmManual(command.recipientId, command.reason, command.identity);
    } catch (error) {
      if (!recoveringUnknown && isDefinitiveAssignmentRejection(error)) {
        orderMutationFlowStore.clearScheduleMutation(command.caseNo, command.planId);
        if (generation === scheduleGeneration.current) setScheduleError(message(error, '日期表操作未通過檢查。'));
      } else {
        orderMutationFlowStore.setScheduleMutation(command.caseNo, command.planId, {
          status: 'outcome_unknown', command, receipt: null, error: message(error, '尚未確認日期表是否已處理，請確認處理結果。'),
        });
      }
      return;
    }
    try {
      assertScheduleReceipt(receipt, command);
    } catch (error) {
      orderMutationFlowStore.setScheduleMutation(command.caseNo, command.planId, {
        status: 'observation_failed', command, receipt, error: message(error, '日期表操作結果身份不一致，請只重新讀取。'),
      });
      return;
    }
    orderMutationFlowStore.setScheduleMutation(command.caseNo, command.planId, { status: 'observation_failed', command, receipt, error: null });
    if (generation === scheduleGeneration.current) await observeSchedule(command);
  };

  const startSchedule = (operation: Omit<Extract<ScheduleMutationCommand, { kind: 'send' }>, 'caseNo' | 'planId' | 'identity'>
    | Omit<Extract<ScheduleMutationCommand, { kind: 'manual' }>, 'caseNo' | 'planId' | 'identity'>
    | Omit<Extract<ScheduleMutationCommand, { kind: 'recipient' }>, 'caseNo' | 'planId' | 'identity'>) => {
    if (orderMutationFlowStore.getScheduleMutation(caseNo, planId)) return;
    const actor = sessionClient.getUser()?.username.trim();
    if (!actor) { setScheduleError('請先登入。'); return; }
    void submitSchedule({ ...operation, caseNo, planId, identity: {
      idempotencyKey: `schedule-${operation.kind}-${crypto.randomUUID()}`, expectedActor: actor,
    } });
  };
  const sendSchedule = () => startSchedule({ kind: 'send' });
  const applyManual = () => {
    if (!manualPreview || !manualConfirmed || !manualReason.trim()) return;
    startSchedule({ kind: 'manual', preview: manualPreview, reason: manualReason.trim() });
  };
  const confirmRecipient = (recipientId: number) => {
    const reason = recipientReasons[recipientId]?.trim();
    if (!reason || recipientPreviewId !== recipientId) return;
    startSchedule({ kind: 'recipient', recipientId, reason });
  };

  const previewAssignment = async () => {
    if (assignmentFlow || assignmentBusy) return;
    assignmentPreviewController.current?.abort();
    const controller = new AbortController();
    assignmentPreviewController.current = controller;
    setAssignmentBusy(true);
    setAssignmentPreview(null);
    setAssignmentConfirmed(false);
    setAssignmentLocalError(null);
    try {
      if (assignmentSegments.some((segment) => segment.official_service_dates.length === 0)) {
        throw new Error('正式方案區段與目前日期表無法完整對應。');
      }
      const preview = await assignmentPlanMutationClient.preview(caseNo, assignmentSegments, controller.signal);
      if (!controller.signal.aborted) setAssignmentPreview(preview);
    } catch (error) {
      if (!controller.signal.aborted) setAssignmentLocalError(message(error, '無法檢查正式排班影響。'));
    } finally {
      if (!controller.signal.aborted) setAssignmentBusy(false);
    }
  };

  const applyAssignment = async () => {
    const retryCommand = assignmentFlow?.status === 'outcome_unknown' ? assignmentFlow.command : null;
    const preview = retryCommand?.preview ?? assignmentPreview;
    if (!preview || assignmentFlow?.acceptedJob || assignmentBusy) return;
    const command = retryCommand ?? {
      caseNo,
      planId,
      segments: assignmentSegments.map((segment) => ({ ...segment, official_service_dates: [...segment.official_service_dates] })),
      preview,
      reason: assignmentReason.trim(),
      identity: {
        idempotencyKey: `assignment-plan-${caseNo}-${crypto.randomUUID()}`,
        correlationId: `assignment-plan-${crypto.randomUUID()}`,
      },
    };
    setAssignmentBusy(true);
    setAssignmentLocalError(null);
    orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
      status: 'applying', command, acceptedJob: null, job: null, readbackStatus: 'not_started', error: null,
    });
    try {
      const accepted = await assignmentPlanMutationClient.apply(command.caseNo, command.segments, command.preview, command.reason, command.identity);
      orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
        status: 'receipt_received', command, acceptedJob: accepted, job: null, readbackStatus: 'not_started', error: null,
      });
      if (isActiveAssignmentScope(activeAssignmentScope, command)) {
        setAssignmentPreview(null);
        setAssignmentConfirmed(false);
      }
      await observeAssignment(accepted.job_id, command);
    } catch (error) {
      if (!retryCommand && isDefinitiveAssignmentRejection(error)) {
        orderMutationFlowStore.clearAssignmentPlan(command.caseNo, command.planId);
      } else {
        orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
          status: 'outcome_unknown', command, acceptedJob: null, job: null, readbackStatus: 'not_started', error: message(error, '無法建立正式排班。'),
        });
      }
      if (isActiveAssignmentScope(activeAssignmentScope, command)) setAssignmentLocalError(message(error, '無法建立正式排班。'));
    } finally {
      if (isActiveAssignmentScope(activeAssignmentScope, command)) setAssignmentBusy(false);
    }
  };

  const observeAssignment = async (jobId: string, command: AssignmentPlanApplyCommand) => {
    if (isActiveAssignmentScope(activeAssignmentScope, command)) {
      setAssignmentBusy(true);
      setAssignmentLocalError(null);
    }
    const prior = orderMutationFlowStore.getAssignmentPlan(command.caseNo, command.planId);
    orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
      status: 'observing', command, acceptedJob: prior?.acceptedJob ?? { job_id: jobId, status_url: '' }, job: prior?.job ?? null, readbackStatus: 'observing', error: null,
    });
    try {
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const observed = await assignmentPlanMutationClient.queryJob(jobId);
        const current = orderMutationFlowStore.getAssignmentPlan(command.caseNo, command.planId);
        orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
          status: 'observing', command, acceptedJob: current?.acceptedJob ?? { job_id: jobId, status_url: '' }, job: observed, readbackStatus: 'observing', error: null,
        });
        if (observed.status === 'failed' || observed.status === 'cancelled') {
          const failure = observed.outcome?.kind === 'failure' ? observed.outcome.error : null;
          throw new Error(failure ? `${failure.message}（${failure.code}）` : `正式排班工作 ${observed.status}。`);
        }
        if (observed.status === 'succeeded') {
          if (observed.outcome?.kind !== 'success' || observed.outcome.result_reference !== `assignment_plan:${command.caseNo}`) {
            throw new Error('正式排班工作回執案件 identity 不一致。');
          }
          const readback = await ordersQueryClient.getAssignmentPlan(command.caseNo);
          assertAssignmentReadback(readback, command);
          if (!isActiveAssignmentScope(activeAssignmentScope, command)) {
            orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
              status: 'observation_failed', command, acceptedJob: { job_id: jobId, status_url: '' }, job: observed, readbackStatus: 'failed', error: '案件或方案已切換；回到原案件後重新查詢正式排班結果。',
            });
            return;
          }
          await onAssignmentCompleted();
          orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
            status: 'observed', command, acceptedJob: { job_id: jobId, status_url: '' }, job: observed, readbackStatus: 'observed', error: null,
          });
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      throw new Error('正式排班仍在處理；請重新查詢結果。');
    } catch (error) {
      const current = orderMutationFlowStore.getAssignmentPlan(command.caseNo, command.planId);
      orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
        status: 'observation_failed', command, acceptedJob: current?.acceptedJob ?? { job_id: jobId, status_url: '' }, job: current?.job ?? null, readbackStatus: 'failed', error: message(error, '正式排班結果尚未完成回讀，請重新查詢原結果。'),
      });
    } finally {
      if (isActiveAssignmentScope(activeAssignmentScope, command)) setAssignmentBusy(false);
    }
  };

  const assignmentCommand = assignmentFlow?.command ?? null;
  const assignmentJob = assignmentFlow?.job ?? null;
  const assignmentJobId = assignmentFlow?.acceptedJob?.job_id ?? null;
  const assignmentReadback = assignmentFlow?.readbackStatus === 'observed';
  const assignmentError = assignmentFlow?.error ?? assignmentLocalError;
  const assignmentPreviewForDisplay = assignmentPreview ?? (assignmentFlow?.status === 'outcome_unknown' ? assignmentFlow.command.preview : null);
  const assignmentReasonForDisplay = assignmentFlow?.status === 'outcome_unknown' ? assignmentFlow.command.reason : assignmentReason;
  const retryingOriginalAssignment = assignmentFlow?.status === 'outcome_unknown';
  const scheduleDisplayError = scheduleFlow?.error ?? scheduleError;

  const recoveryControls = <>
    {scheduleDisplayError && <div role="alert" className="mutation-error-banner">{scheduleDisplayError}</div>}
    {scheduleFlow?.status === 'applying' && <div role="status">日期表操作處理中…</div>}
    {scheduleFlow?.status === 'outcome_unknown' && <button type="button" className="orders-load-more-btn" onClick={() => void submitSchedule(scheduleFlow.command)}>確認日期表處理結果</button>}
    {scheduleFlow?.receipt && <button type="button" className="orders-load-more-btn" disabled={scheduleFlow.status === 'observing'} onClick={() => void observeSchedule(scheduleFlow.command)}>重新讀取日期表結果</button>}
    {scheduleNotice && <div role="status">{scheduleNotice}</div>}
  </>;
  return (
    <div style={{ display: 'grid', gap: '12px', marginTop: '12px' }} data-surface-id="orders.matching.schedule-confirmation">
      {recoveryControls}
      {!schedule && !scheduleFlow && !scheduleError && <div role="status">正在載入日期表確認狀態…</div>}
      {schedule && <>
      <div style={{ fontWeight: 700 }}>📅 客戶與月嫂確認同一份服務日期表</div>
      <div style={{ fontSize: '0.82rem', color: '#57423b' }}>
        {schedule.schedule_preview.total_service_days} 個服務日｜
        {schedule.schedule_preview.weeks.flatMap((week) => week.service_dates).join('、')}
      </div>
      {schedule.snapshot_status === 'not_sent' && (
        <div style={{ display: 'grid', gap: '8px' }}>
          <div role="status">尚未建立日期表確認快照；可透過 LINE 發送目前日期版本，或以電話／現場／紙本證據人工確認。</div>
          <button type="button" className="orders-load-more-btn" disabled={scheduleFlow !== undefined || scheduleBusy !== null} onClick={() => void sendSchedule()}>
            {scheduleBusy === 'send' ? '正在排入 LINE 發送佇列…' : '透過 LINE 發送日期表'}
          </button>
          <button type="button" className="matching-action-btn-sm" disabled={scheduleFlow !== undefined || scheduleBusy !== null} onClick={() => void previewManual()}>
            {scheduleBusy === 'manual-preview' ? '正在檢查日期表影響…' : '檢查人工日期表確認影響'}
          </button>
          {manualPreview && (
            <>
              <div role="status">預覽已完成；此人工確認不會建立 LINE 發送工作。</div>
              <label>人工快照原因<input aria-label="人工日期表快照原因" maxLength={500} disabled={scheduleFlow !== undefined} value={manualReason} onChange={(event) => { setManualReason(event.target.value); setManualConfirmed(false); }} /></label>
              <label><input type="checkbox" disabled={scheduleFlow !== undefined} checked={manualConfirmed} onChange={(event) => setManualConfirmed(event.target.checked)} />我已核對日期表，確認建立人工證據快照。</label>
              <button type="button" className="orders-load-more-btn" disabled={scheduleFlow !== undefined || scheduleBusy !== null || !manualConfirmed || !manualReason.trim()} onClick={() => void applyManual()}>
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
            <strong>{label}</strong>｜{confirmed ? '已確認' : '待確認'}｜{recipient.delivery_status === 'blocked' ? '未透過 LINE（人工）' : `LINE ${{ pending: '等待發送', queued: '等待發送', sent: '已發送', failed: '發送失敗' }[recipient.delivery_status]}`}
            {recipient.confirmation_reason && <div>確認原因：{recipient.confirmation_reason}</div>}
            {!confirmed && (
              <div style={{ display: 'grid', gap: '6px', marginTop: '6px' }}>
                <input aria-label={`${label}人工確認原因`} maxLength={500} disabled={scheduleFlow !== undefined} value={recipientReasons[recipient.recipient_snapshot_id] ?? ''} onChange={(event) => { setRecipientReasons((current) => ({ ...current, [recipient.recipient_snapshot_id]: event.target.value })); setRecipientPreviewId(null); }} placeholder="輸入電話、現場或紙本確認依據" />
                <button type="button" className="matching-action-btn-sm" disabled={scheduleFlow !== undefined || !recipientReasons[recipient.recipient_snapshot_id]?.trim()} onClick={() => setRecipientPreviewId(recipient.recipient_snapshot_id)}>檢查{label}人工確認</button>
                {recipientPreviewId === recipient.recipient_snapshot_id && (
                  <button type="button" className="orders-load-more-btn" disabled={scheduleFlow !== undefined || scheduleBusy !== null} onClick={() => void confirmRecipient(recipient.recipient_snapshot_id)}>
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
          <button type="button" className="matching-action-btn-sm" disabled={assignmentBusy || assignmentFlow !== undefined || assignmentSegments.length === 0} onClick={() => void previewAssignment()}>{assignmentBusy ? '處理中…' : '檢查建立正式排班影響'}</button>
          {assignmentPreviewForDisplay && (
            <>
              <div role="status">影響檢查：將建立 {assignmentPreviewForDisplay.assignments.length} 段正式指派並轉換等待訂金鎖。</div>
              <label>正式排班原因<input aria-label="正式排班原因" maxLength={500} disabled={assignmentCommand !== null} value={assignmentReasonForDisplay} onChange={(event) => { setAssignmentReason(event.target.value); setAssignmentConfirmed(false); }} /></label>
              <label><input type="checkbox" disabled={assignmentCommand !== null} checked={retryingOriginalAssignment || assignmentConfirmed} onChange={(event) => setAssignmentConfirmed(event.target.checked)} />我已核對月嫂、日期、契約與訂金。</label>
              <button type="button" className="orders-load-more-btn" disabled={assignmentBusy || (!retryingOriginalAssignment && (!assignmentConfirmed || !assignmentReasonForDisplay.trim()))} onClick={() => void applyAssignment()}>{assignmentBusy ? '正式排班套用並回讀中…' : retryingOriginalAssignment ? '以原確認操作重新送出' : '確認套用正式排班'}</button>
            </>
          )}
          {assignmentJobId && !assignmentReadback && (
            <div role="status">{assignmentJob?.status === 'succeeded' ? '正式排班處理已完成，正在核對結果。' : '正式排班處理中。'}</div>
          )}
          {assignmentJobId && !assignmentReadback && !assignmentBusy && assignmentCommand && <button type="button" onClick={() => void observeAssignment(assignmentJobId, assignmentCommand)}>重新查詢正式排班結果</button>}
          {assignmentReadback && <div role="status" style={{ color: '#166534' }}>正式排班已完成並回讀一致。</div>}
          {assignmentError && <div role="alert" className="mutation-error-banner">{assignmentError}</div>}
        </div>
      )}
      </>}
    </div>
  );
};

function message(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function isDefinitiveAssignmentRejection(error: unknown): boolean {
  return error instanceof ApiHttpError
    && error.status >= 400
    && error.status < 500
    && error.status !== 408
    && error.status !== 429;
}

function isActiveAssignmentScope(scope: React.MutableRefObject<string>, command: AssignmentPlanApplyCommand): boolean {
  return scope.current === `${command.caseNo}:${command.planId}`;
}

function assertAssignmentReadback(
  readback: Awaited<ReturnType<typeof ordersQueryClient.getAssignmentPlan>>,
  command: AssignmentPlanApplyCommand,
): void {
  if (readback.case_no !== command.caseNo) throw new Error('正式排班回讀案件 identity 不一致。');
  if (
    readback.scheduling_version !== command.preview.scheduling_version + 1
    || readback.scheduling_generation !== command.preview.scheduling_generation
  ) throw new Error('正式排班回讀版本不一致。');
  if (
    readback.assignments.length !== command.segments.length
    || !command.segments.every((expected, index) => {
      const actual = readback.assignments[index];
      return actual !== undefined
        && actual.staff_id === expected.staff_id
        && actual.assigned_start_date === expected.assigned_start_date
        && actual.assigned_end_date === expected.assigned_end_date
        && actual.official_service_dates.length === expected.official_service_dates.length
        && actual.official_service_dates.every((date, dateIndex) => date === expected.official_service_dates[dateIndex]);
    })
  ) throw new Error('正式排班回讀指派與原方案不一致。');
}

function assertScheduleReceipt(receipt: MatchingScheduleState, command: ScheduleMutationCommand): void {
  if (receipt.case_no !== command.caseNo || receipt.plan_id !== command.planId || receipt.snapshot_id === null) {
    throw new Error('日期表操作結果案件或快照識別不一致。');
  }
  if (command.kind === 'manual' && (receipt.confirmed_service_date_version !== command.preview.confirmed_service_date_version || receipt.snapshot_status !== 'manual_ready')) {
    throw new Error('人工日期表快照版本不一致。');
  }
  if (command.kind === 'send' && receipt.snapshot_status !== 'sent') throw new Error('日期表發送結果尚未確認。');
  if (command.kind === 'recipient') {
    const recipient = receipt.recipients.find(item => item.recipient_snapshot_id === command.recipientId);
    if (!recipient || recipient.confirmation_status !== 'manually_confirmed' || recipient.confirmation_reason !== command.reason) {
      throw new Error('日期表確認對象或原因不一致。');
    }
  }
}

function assertScheduleReadback(observed: MatchingScheduleState, receipt: MatchingScheduleState, command: ScheduleMutationCommand): void {
  assertScheduleReceipt(receipt, command);
  assertScheduleReceipt(observed, command);
  if (observed.snapshot_id !== receipt.snapshot_id || observed.confirmed_service_date_version !== receipt.confirmed_service_date_version) {
    throw new Error('日期表回讀尚未觀察到原快照與版本。');
  }
}
