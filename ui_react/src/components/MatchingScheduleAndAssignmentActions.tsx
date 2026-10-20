import { useUnsavedDraft } from './UnsavedChanges';
import { useRef as useValidationRef } from 'react';
import { useSaveValidation } from './useSaveValidation';
/**
 * File: MatchingScheduleAndAssignmentActions.tsx
 * Description: 以人工日期表確認及排班 Preview／Apply 完成 waiting-lock conversion。
 */
import React, { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { orderMutationFlowStore, type AssignmentPlanApplyCommand, type ScheduleMutationCommand } from '../adapters/orders/order_mutation_flow_store';
import { ordersQueryClient } from '../api/orders/order_query_client';
import {
  assignmentPlanMutationClient,
} from '../api/scheduling/assignment_plan_mutation_client';
import {
  matchingScheduleConfirmationClient,
  type MatchingScheduleState,
} from '../api/scheduling/matching_schedule_confirmation_client';
import { sessionClient } from '../api/auth/session_client';
import { useStaffIdentityLabels } from './StaffIdentityProvider';
import { ApiHttpError } from '../api/shared/typed_errors';
import { serviceArrangementStatusClient, serviceArrangementBlockerLabel, type AutomaticArrangementStatus } from '../api/scheduling/service_arrangement_status_client';

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
  officialServiceDates?: readonly string[];
  contractReady?: boolean;
  depositReady?: boolean;
  onOpenDates?: () => void;
  onOpenRecommendation?: () => void;
  onAssignmentCompleted: () => Promise<void>;
  staffNames?: Readonly<Record<number, string>>;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
}

export const MatchingScheduleAndAssignmentActions: React.FC<Props> = ({
  caseNo,
  planId,
  planSegments,
  waitingLockAcquired,
  assignmentExists,
  officialServiceDates = [],
  contractReady,
  depositReady,
  onOpenDates,
  onOpenRecommendation,
  onAssignmentCompleted,
  staffNames = {},
  onEditStateChange,
}) => {
  const staffIdentity = useStaffIdentityLabels();
  const [schedule, setSchedule] = useState<MatchingScheduleState | null>(null);
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [scheduleBusy, setScheduleBusy] = useState<string | null>(null);
  const [assignmentBusy, setAssignmentBusy] = useState(false);
  const [assignmentLocalError, setAssignmentLocalError] = useState<string | null>(null);
  const activeAssignmentScope = useRef('');
  const scheduleObservationController = useRef<AbortController | null>(null);
  const scheduleGeneration = useRef(0);
  const [scheduleNotice, setScheduleNotice] = useState<string | null>(null);
  const scheduleFlow = useSyncExternalStore(
    (listener) => orderMutationFlowStore.subscribe(listener),
    () => orderMutationFlowStore.getScheduleMutation(caseNo, planId),
  );
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
    setAssignmentBusy(false);
    setAssignmentLocalError(null);
    matchingScheduleConfirmationClient.query(caseNo, planId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setSchedule(value); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setScheduleError(message(error, '日期表確認狀態載入失敗。')); });
    return () => {
      controller.abort();
      activeAssignmentScope.current = '';
      scheduleGeneration.current += 1;
      scheduleObservationController.current?.abort();
      const saved = orderMutationFlowStore.getScheduleMutation(caseNo, planId);
      if (saved?.status === 'observing' && saved.receipt) {
        orderMutationFlowStore.setScheduleMutation(caseNo, planId, { ...saved, status: 'observation_failed', error: '尚未讀取到最新日期表，請重新讀取。' });
      }
    };
  }, [caseNo, planId]);

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
      setScheduleNotice('日期表結果已更新。');
      orderMutationFlowStore.clearScheduleMutation(command.caseNo, command.planId);
      return observed;
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
    if (generation === scheduleGeneration.current) return await observeSchedule(command);
  };

  const startSchedule = (operation: Omit<Extract<ScheduleMutationCommand, { kind: 'send' }>, 'caseNo' | 'planId' | 'identity'>
    | Omit<Extract<ScheduleMutationCommand, { kind: 'manual' }>, 'caseNo' | 'planId' | 'identity'>
    | Omit<Extract<ScheduleMutationCommand, { kind: 'recipient' }>, 'caseNo' | 'planId' | 'identity'>) => {
    if (orderMutationFlowStore.getScheduleMutation(caseNo, planId)) return;
    const actor = sessionClient.getUser()?.username.trim();
    if (!actor) { setScheduleError('請先登入。'); return; }
    return submitSchedule({ ...operation, caseNo, planId, identity: {
      idempotencyKey: `schedule-${operation.kind}-${crypto.randomUUID()}`, expectedActor: actor,
    } });
  };
  const sendSchedule = () => startSchedule({ kind: 'send' });
  // Existing accepted commands keep their original identity after a connection interruption.
  const applyAssignment = async () => {
    if (assignmentFlow?.status !== 'outcome_unknown' || assignmentBusy) return;
    const command = assignmentFlow.command;
    setAssignmentBusy(true);
    try {
      const accepted = await assignmentPlanMutationClient.apply(command.caseNo, command.segments, command.preview, command.reason, command.identity);
      orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, { status: 'receipt_received', command, acceptedJob: accepted, job: null, readbackStatus: 'not_started', error: null });
      await observeAssignment(accepted.job_id, command);
    } catch (error) {
      orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, { ...assignmentFlow, error: message(error, '尚未確認原排班結果。') });
    } finally { setAssignmentBusy(false); }
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
          throw new Error(failure ? `${failure.message}（${failure.code}）` : `排班工作 ${observed.status}。`);
        }
        if (observed.status === 'succeeded') {
          if (observed.outcome?.kind !== 'success' || observed.outcome.result_reference !== `assignment_plan:${command.caseNo}`) {
            throw new Error('排班工作回執案件 identity 不一致。');
          }
          const readback = await ordersQueryClient.getAssignmentPlan(command.caseNo);
          assertAssignmentReadback(readback, command);
          if (!isActiveAssignmentScope(activeAssignmentScope, command)) {
            orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
              status: 'observation_failed', command, acceptedJob: { job_id: jobId, status_url: '' }, job: observed, readbackStatus: 'failed', error: '案件或方案已切換；回到原案件後重新查詢排班結果。',
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
      throw new Error('排班仍在處理；請重新查詢結果。');
    } catch (error) {
      const current = orderMutationFlowStore.getAssignmentPlan(command.caseNo, command.planId);
      orderMutationFlowStore.setAssignmentPlan(command.caseNo, command.planId, {
        status: 'observation_failed', command, acceptedJob: current?.acceptedJob ?? { job_id: jobId, status_url: '' }, job: current?.job ?? null, readbackStatus: 'failed', error: message(error, '排班結果尚未完成回讀，請重新查詢原結果。'),
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
  const scheduleDisplayError = scheduleFlow?.error ?? scheduleError;

  const recoveryControls = <>
    {scheduleDisplayError && <div role="alert" className="mutation-error-banner">{scheduleDisplayError}</div>}
    {scheduleFlow?.status === 'applying' && <div role="status">日期表操作處理中…</div>}
    {scheduleFlow?.status === 'outcome_unknown' && <button type="button" className="orders-load-more-btn" onClick={() => void submitSchedule(scheduleFlow.command)}>確認日期表處理結果</button>}
    {scheduleFlow?.receipt && <button type="button" className="orders-load-more-btn" disabled={scheduleFlow.status === 'observing'} onClick={() => void observeSchedule(scheduleFlow.command)}>重新讀取日期表結果</button>}
    {scheduleNotice && <div role="status">{scheduleNotice}</div>}
  </>;
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [confirmationNote, setConfirmationNote] = useState('');
  const saveValidation = useSaveValidation();
  const saveFieldRef = useValidationRef<HTMLTextAreaElement>(null);
  const [automatic, setAutomatic] = useState<AutomaticArrangementStatus | null>(null);
  const [automaticError, setAutomaticError] = useState('');
  const observedAutomatic = useRef(false);
  const completionCallback = useRef(onAssignmentCompleted);
  completionCallback.current = onAssignmentCompleted;
  const protectedMutation = scheduleFlow !== undefined || assignmentBusy || scheduleBusy !== null;
  useEffect(() => { onEditStateChange?.({ dirty: confirmationNote.trim().length > 0, busy: protectedMutation }); }, [confirmationNote, protectedMutation, onEditStateChange]);
  useEffect(() => {
    const controller = new AbortController();
    let polling = false;
    observedAutomatic.current = assignmentExists;
    const poll = async () => {
      if (polling || orderMutationFlowStore.getScheduleMutation(caseNo, planId)) return;
      polling = true;
      try {
        const status = await serviceArrangementStatusClient.arrangement(caseNo, planId, controller.signal);
        if (controller.signal.aborted) return;
        if (!orderMutationFlowStore.getScheduleMutation(caseNo, planId)) {
          const current = await matchingScheduleConfirmationClient.query(caseNo, planId, controller.signal);
          if (!controller.signal.aborted && !orderMutationFlowStore.getScheduleMutation(caseNo, planId)) setSchedule(current);
        }
        if (status.state === 'effective' && !observedAutomatic.current) {
          const owner = await ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal });
          if (owner.case_no !== caseNo || owner.assignments.length !== status.assignment_count || owner.assignments.length === 0) throw new Error('排班結果尚未完成正式回讀。');
          if (controller.signal.aborted) return;
          await completionCallback.current();
          observedAutomatic.current = true;
        }
        if (controller.signal.aborted) return;
        setAutomatic(status); setAutomaticError('');
      } catch (error) { if (!controller.signal.aborted) setAutomaticError(message(error, '無法讀取自動排班狀態。')); }
      finally { polling = false; }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 2500);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [caseNo, planId, assignmentExists]);

  const parties = schedule?.schedule_preview.recipient_schedules ?? [];
  const snapshotDates = schedule?.schedule_preview.weeks.flatMap(week => week.service_dates) ?? [];
  const dateTableSuperseded = assignmentExists && officialServiceDates.length > 0
    && (snapshotDates.length !== officialServiceDates.length || snapshotDates.some((date, index) => date !== officialServiceDates[index]));
  const displayedDates = dateTableSuperseded ? officialServiceDates : snapshotDates;
  const confirmedParties = schedule?.recipients.filter(recipient => ['confirmed', 'manually_confirmed'].includes(recipient.confirmation_status)).length ?? 0;
  const allConditionsVerified = assignmentExists || (automatic !== null && ['ready', 'queued', 'running', 'effective'].includes(automatic.state));
  const blockerCodes = automatic?.blockers ?? [];
  const keyOf = (party: typeof parties[number]) => party.audience_type === 'customer' ? 'customer' : `caregiver:${party.segment_id}`;
  const saveConfirmation = async (key: string) => {
    if (protectedMutation || !saveValidation.validate([{ value: confirmationNote, label: '確認紀錄', ref: saveFieldRef }])) return;
    if (protectedMutation || !confirmationNote.trim() || !schedule) return;
    const reason = confirmationNote.trim();
    const generation = scheduleGeneration.current;
    setScheduleBusy('manual-confirm'); setScheduleError(null);
    try {
      let current = schedule;
      if (current.snapshot_status === 'not_sent' || current.snapshot_status === 'sent_outdated') {
        const preview = await matchingScheduleConfirmationClient.previewManual(caseNo, planId);
        if (generation !== scheduleGeneration.current) return;
        const observed = await startSchedule({ kind: 'manual', preview, reason });
        if (!observed) return;
        current = observed;
      }
      if (generation !== scheduleGeneration.current) return;
      const recipient = current.recipients.find(party => (party.audience_type === 'customer' ? 'customer' : `caregiver:${party.segment_id}`) === key);
      if (!recipient) throw new Error('確認對象與目前日期表不同，請重新核對。');
      const observed = await startSchedule({ kind: 'recipient', recipientId: recipient.recipient_snapshot_id, reason });
      if (observed && generation === scheduleGeneration.current) { setEditingKey(null); setConfirmationNote(''); }
    } catch (error) { if (generation === scheduleGeneration.current) setScheduleError(message(error, '無法保存確認紀錄。')); }
    finally { if (generation === scheduleGeneration.current) setScheduleBusy(null); }
  };
  useUnsavedDraft('手動記錄日期確認', { '確認紀錄': confirmationNote }, { baseline: { '確認紀錄': '' }, busy: protectedMutation });


  return <div className="service-arrangement-confirmation" data-surface-id="orders.matching.schedule-confirmation">
    {recoveryControls}
    {!schedule && !scheduleFlow && !scheduleError && <p role="status">正在載入日期表確認狀態…</p>}
    {schedule && <>
      <p className="service-arrangement-description">雙方確認同一份服務日期，且條件齊備後，系統會自動完成排班。</p>
      <dl className="service-date-summary-strip" aria-label="排班確認服務期間"><div><dt>服務開始</dt><dd>{displayedDates[0] ?? '尚未保存'}</dd></div><div><dt>最後服務日</dt><dd>{displayedDates.at(-1) ?? '尚未保存'}</dd></div><div><dt>服務天數</dt><dd>{displayedDates.length} 天</dd></div></dl>
      {dateTableSuperseded ? <p role="status">開始日更正已更新各段班表，請核對目前服務期間；原日期表確認保留於歷史紀錄。</p> : <><header className="service-arrangement-section-heading"><div><h3 className="visually-hidden">客戶與各段月嫂確認日期表</h3><details className="service-arrangement-date-list"><summary>查看已儲存日期表</summary><p>{snapshotDates.join('、')}</p></details></div>
        <button type="button" disabled={protectedMutation} onClick={sendSchedule}>{schedule.snapshot_status === 'sent_outdated' ? '重新寄送目前日期表' : '寄送日期表'}</button>
      </header>
      {schedule.snapshot_status === 'sent_outdated' && <p role="status">日期已變更，先前確認已失效，請重新核對並記錄目前日期表。</p>}
      {schedule.snapshot_status === 'sent_outdated' && <details><summary>核對前後日期差異</summary><p>先前日期：{schedule.outdated_schedule_preview?.weeks.flatMap(week => week.service_dates).join('、') ?? '無先前日期表'}</p><p>目前日期：{schedule.schedule_preview.weeks.flatMap(week => week.service_dates).join('、')}</p></details>}
      {parties.map(party => {
        const key = keyOf(party);
        const recipient = schedule.recipients.find(value => (value.audience_type === 'customer' ? 'customer' : `caregiver:${value.segment_id}`) === key);
        const segment = planSegments.find(value => value.segmentId === party.segment_id);
        const label = party.audience_type === 'customer' ? '客戶' : `${segment ? staffNames[segment.staffId] ?? staffIdentity.label(segment.staffId) : '月嫂'}${planSegments.length > 1 && segment ? `・第 ${segment.sequence} 段` : ''}`;
        const confirmed = recipient && ['confirmed', 'manually_confirmed'].includes(recipient.confirmation_status);
        const dates = party.weeks.flatMap(week => week.service_dates);
        return <article className="service-arrangement-party" key={key}>
          <header><div><strong>{label}</strong><p>{dates[0]} ～ {dates.at(-1)} · {dates.length} 天</p></div><div><span className={confirmed ? 'service-status-ready' : 'service-status-pending'}>{confirmed ? '已確認日期' : '尚未確認日期'}</span>{!confirmed && editingKey !== key && <button type="button" disabled={protectedMutation || confirmationNote.trim().length > 0} onClick={() => { setEditingKey(key); setConfirmationNote(''); }}>手動記錄確認</button>}</div></header>
          {recipient?.confirmation_reason && <details className="service-arrangement-confirmation-record"><summary>已確認目前日期表 · 查看確認紀錄</summary><p>確認紀錄：{recipient.confirmation_reason}</p></details>}
          {!confirmed && recipient?.delivery_status === 'blocked' && <p>尚未綁定 LINE，請聯絡對方後手動記錄確認。</p>}
          {recipient?.delivery_status === 'failed' && <p role="status">日期表寄送失敗，請重新寄送或手動記錄確認。</p>}
          {editingKey === key && <section className="service-arrangement-inline-form" aria-label={`${label}手動記錄日期確認`}><><label>確認紀錄（必填）<textarea ref={saveFieldRef} aria-required="true" aria-label={`${label}確認紀錄`} maxLength={500} disabled={protectedMutation} value={confirmationNote} onChange={event => setConfirmationNote(event.target.value)} placeholder="例如：已電話確認目前日期表，對方同意此服務安排。" /></label>{saveValidation.feedback}</><div className="order-case-action-row"><button type="button" disabled={protectedMutation} onClick={() => void saveConfirmation(key)}>儲存確認紀錄</button><button type="button" disabled={protectedMutation} onClick={() => { setEditingKey(null); setConfirmationNote(''); }}>取消</button></div></section>}
        </article>;
      })}
      <p className="service-arrangement-confirmation-count">{confirmedParties} / {parties.length} 位已確認目前日期表</p>
      </>}
      <section className="service-arrangement-automatic-status" aria-label="排班狀態"><header><h3>排班狀態</h3><span className={assignmentExists ? 'service-status-ready' : 'service-status-pending'}>{assignmentExists ? '已生效' : '尚未生效'}</span></header>
        {automatic && <div className={`service-arrangement-status-notice${assignmentExists ? ' ready' : ''}`} role="status"><strong>{assignmentExists ? '排班已生效' : schedule.gate_passed ? '雙方已確認，等待條件完成' : '等待客戶與月嫂確認'}</strong><p>{{ awaiting_confirmations: '等待客戶與所有月嫂確認目前日期表。', awaiting_conditions: '雙方確認紀錄已保留，條件齊備後自動排班。', ready: '條件已齊備，等待系統自動排班。', queued: '自動排班已排入背景工作。', running: '正在建立排班。', effective: '排班已生效，月嫂預留檔期已轉為正式班表。', failed: '自動排班尚未完成，請核對處理結果。' }[automatic.state]}</p></div>}
        <div className="service-arrangement-gates">{[
          { label: '客戶與各段月嫂確認', ready: !dateTableSuperseded && schedule.gate_passed, blocked: !dateTableSuperseded && !schedule.gate_passed },
          { label: '客戶與月嫂契約', ready: !blockerCodes.some(code => code.includes('commitment')) && (allConditionsVerified || contractReady === true), blocked: contractReady === false || blockerCodes.some(code => code.includes('contract') || code.includes('commitment')) },
          { label: '訂金付款關卡', ready: allConditionsVerified || depositReady === true, blocked: depositReady === false || blockerCodes.some(code => code.includes('deposit')) },
          { label: '月嫂檔期檢查', ready: allConditionsVerified, blocked: blockerCodes.some(code => code.includes('occupancy') || code.includes('waiting_lock')) },
        ].map(gate => <div key={gate.label}><span>{gate.label}</span><span>{gate.ready ? '✓ 已完成' : gate.blocked ? '待完成' : '待核對'}</span></div>)}</div>
        <p className="service-arrangement-lock-note">月嫂檔期：{assignmentExists ? '已轉為正式班表' : waitingLockAcquired ? '已預留，等待正式排班' : '配對及服務日期確認後自動保留'}</p>
        {automatic?.blockers.map(code => <p key={code}>{serviceArrangementBlockerLabel(code)}</p>)}
        {!assignmentExists && <div className="order-case-action-row">
          {!waitingLockAcquired && onOpenRecommendation && <button type="button" disabled={protectedMutation || editingKey !== null} onClick={onOpenRecommendation}>查看配對確認狀態</button>}
          {blockerCodes.some(code => code.includes('occupancy') || code.includes('segment_dates')) && onOpenDates && <button type="button" disabled={protectedMutation || editingKey !== null} onClick={onOpenDates}>調整服務日期</button>}
        </div>}
        {automaticError && <p role="alert">{automaticError}</p>}
        {assignmentFlow?.status === 'outcome_unknown' && <button type="button" disabled={assignmentBusy} onClick={() => void applyAssignment()}>確認原排班處理結果</button>}
        {assignmentJobId && !assignmentReadback && assignmentCommand && <button type="button" disabled={assignmentBusy} onClick={() => void observeAssignment(assignmentJobId, assignmentCommand)}>重新查詢排班結果</button>}
        {assignmentJob && !assignmentReadback && <p role="status">原排班工作：{assignmentJob.status}</p>}
        {assignmentReadback && <p role="status">排班已完成並回讀一致。</p>}
        {assignmentError && <p role="alert">{assignmentError}</p>}
      </section>
    </>}
  </div>;

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
  if (readback.case_no !== command.caseNo) throw new Error('排班回讀案件 identity 不一致。');
  if (
    readback.scheduling_version !== command.preview.scheduling_version + 1
    || readback.scheduling_generation !== command.preview.scheduling_generation
  ) throw new Error('排班回讀版本不一致。');
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
  ) throw new Error('排班回讀指派與原方案不一致。');
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
