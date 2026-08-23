/**
 * File: SchedulingPage.tsx
 * Description: 顯示完整月份排班甘特，並提供獨立資格查詢與受控調度工作台。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './SchedulingPage.css';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage } from '../adapters/staff/staff_directory_adapter';
import type { StaffDirectoryCardViewModel } from '../adapters/staff/staff_directory_adapter';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { SchedulingCurrentError } from '../api/scheduling/scheduling_current_errors';
import { schedulingEligibilityCollisionClient } from '../api/scheduling/eligibility_collision_client';
import { SchedulingEligibilityCollisionError } from '../api/scheduling/eligibility_collision_errors';
import { ApiHttpError } from '../api/shared/typed_errors';
import {
  adaptSchedulingProjection,
  matchesSchedulingFilter,
  type SchedulingCalendarRowViewModel,
} from '../adapters/scheduling/scheduling_current_adapter';
import {
  adaptSchedulingEligibilityCollision,
  type SchedulingEligibilityCollisionViewModel,
} from '../adapters/scheduling/eligibility_collision_adapter';
import {
  applyLeaveSubstitutionFlow,
  previewLeaveSubstitutionFlow,
  queryLeaveSubstitutionFlow,
  resolveLeaveSubstitutionMachineState,
  retryLeaveSubstitutionApplyFlow,
  retryLeaveSubstitutionObservationFlow,
  setLeaveSubstitutionDraft,
} from '../adapters/scheduling/leave_substitution_flow_adapter';
import { leaveSubstitutionFlowStore } from '../adapters/scheduling/leave_substitution_flow_store';
import type {
  LeaveResolutionType,
  LeaveSubstitutionApplyRequest,
  LeaveSubstitutionPreviewRequest,
} from '../api/scheduling/leave_substitution_schemas';
import {
  applyHolidayFlow,
  holidayFlowStore,
  previewHolidayFlow,
  queryHolidayFlow,
  resolveHolidayMachineState,
  retryHolidayApplyFlow,
  retryHolidayObservationFlow,
  setHolidayDraft,
  type HolidayAction,
  type HolidayApplyRequest,
  type HolidayPreviewRequest,
} from '../adapters/scheduling/holiday_flow_adapter';
import {
  staffLeaveInboxClient,
  type LeaveInboxItem,
  type LeaveInboxReviewAction,
  type LeaveInboxStatus,
} from '../api/scheduling/staff_leave_inbox_client';
import {
  waitingDepositLockClient,
  type WaitingDepositPreview,
  type WaitingDepositReceipt,
} from '../api/scheduling/waiting_deposit_lock_client';
import {
  schedulePrecisionClient,
  type SchedulePrecisionResult,
} from '../api/scheduling/schedule_precision_client';

type SchedulingTab = 'calendar' | 'leave_sub' | 'holidays' | 'leave_inbox';
type StatusFilter = 'all' | 'active' | 'waiting' | 'leave';

interface MonthSelection {
  year: number;
  month: number;
}

const STAFF_PAGE_SIZE = 20;

export function taipeiCalendarDate(at: Date): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(at);
  const value = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value);
  return { year: value('year'), month: value('month'), day: value('day') };
}

function currentMonth(): MonthSelection {
  const now = taipeiCalendarDate(new Date());
  return { year: now.year, month: now.month };
}

function isoDate(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function todayIsoDate(): string {
  const now = taipeiCalendarDate(new Date());
  return isoDate(now.year, now.month, now.day);
}

function monthRange(selection: MonthSelection) {
  const finalDay = new Date(Date.UTC(selection.year, selection.month, 0)).getUTCDate();
  return {
    rangeStart: isoDate(selection.year, selection.month, 1),
    rangeEnd: isoDate(selection.year, selection.month, finalDay),
    totalDays: finalDay,
  };
}

function monthAxis(selection: MonthSelection) {
  const { totalDays } = monthRange(selection);
  const weekdayLabels = ['日', '一', '二', '三', '四', '五', '六'];
  return Array.from({ length: totalDays }, (_, index) => {
    const dayNumber = index + 1;
    const date = new Date(Date.UTC(selection.year, selection.month - 1, dayNumber));
    return {
      dayNumber,
      dateStr: isoDate(selection.year, selection.month, dayNumber),
      weekday: weekdayLabels[date.getUTCDay()],
      isWeekend: date.getUTCDay() === 0 || date.getUTCDay() === 6,
    };
  });
}

function moveMonth(selection: MonthSelection, offset: number): MonthSelection {
  const target = new Date(Date.UTC(selection.year, selection.month - 1 + offset, 1));
  return { year: target.getUTCFullYear(), month: target.getUTCMonth() + 1 };
}

function renderError(error: SchedulingCurrentError | Error): string {
  if (error instanceof SchedulingCurrentError) {
    const code = error.publicCode ?? error.code;
    const correlation = error.correlationId ? `｜Correlation: ${error.correlationId}` : '';
    if (code === 'SCHEDULING_UNAVAILABLE') {
      return '排班日曆服務暫時無法回應，請稍後重試。';
    }
    return `[${code}] ${error.message}${correlation}`;
  }
  return error.message;
}

function StaffLeaveInboxWorkspace() {
  const [status, setStatus] = useState<LeaveInboxStatus>('pending');
  const [items, setItems] = useState<readonly LeaveInboxItem[]>([]);
  const [reasonById, setReasonById] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setItems(await staffLeaveInboxClient.list(status));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '請假待辦載入失敗。');
    } finally {
      setBusy(false);
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  const review = async (item: LeaveInboxItem, action: LeaveInboxReviewAction) => {
    if (busy) return;
    const reason = reasonById[item.id]?.trim() ?? '';
    if ((action === 'reject' || action === 'cancel') && !reason) {
      setError('退回或取消請先填寫原因。');
      return;
    }
    setBusy(true);
    setError(null);
    setReceipt(null);
    try {
      const result = await staffLeaveInboxClient.review(item, action, reason);
      setReceipt(`待辦 #${result.request_id} 已更新為 ${result.status}（版本 ${result.version}）。`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '請假待辦審核失敗。');
      setBusy(false);
    }
  };

  return (
    <section className="scheduling-workspace leave-inbox-workspace" aria-live="polite">
      <div className="scheduling-workspace-heading">
        <div><h2>請假待辦收件匣</h2><p>直接讀取後端待辦根事實；接受或退回後會重查最新版本。</p></div>
        <span className="scheduling-machine-state">{busy ? 'loading' : 'ready'}</span>
      </div>
      <div className="leave-inbox-toolbar">
        <label>狀態
          <select value={status} onChange={(event) => setStatus(event.target.value as LeaveInboxStatus)} disabled={busy}>
            <option value="pending">待審核</option><option value="accepted_for_processing">已接受處理</option>
            <option value="rejected">已退回</option><option value="cancelled">已取消</option><option value="resolved">已完成代班</option>
          </select>
        </label>
        <button type="button" onClick={() => void load()} disabled={busy}>重新整理</button>
      </div>
      {error && <p className="leave-substitution-notice error" role="alert">{error}</p>}
      {receipt && <p className="leave-substitution-notice success">{receipt}</p>}
      {!busy && items.length === 0 && <p className="leave-inbox-empty">此狀態目前沒有請假待辦。</p>}
      <div className="leave-inbox-list">{items.map((item) => (
        <article key={item.id} className="leave-inbox-card">
          <div><strong>#{item.id}｜{item.staff_name}</strong><p>{item.leave_start_date} ～ {item.leave_end_date}</p>
            <p>{item.request_reason || '未填請假說明'}</p><small>{item.request_status}｜版本 {item.aggregate_version}</small></div>
          {item.request_status === 'pending' && <div className="leave-inbox-review">
            <label>審核原因<input value={reasonById[item.id] ?? ''}
              onChange={(event) => setReasonById((current) => ({ ...current, [item.id]: event.target.value }))}
              placeholder="接受可留空；退回必填" disabled={busy} /></label>
            <div><button type="button" onClick={() => void review(item, 'accept')} disabled={busy}>接受處理</button>
              <button type="button" onClick={() => void review(item, 'reject')} disabled={busy}>退回申請</button></div>
          </div>}
        </article>
      ))}</div>
    </section>
  );
}

function holidayPreviewRequestsMatch(
  current: HolidayPreviewRequest | null,
  previewed: HolidayPreviewRequest | null,
): boolean {
  return Boolean(
    current
      && previewed
      && current.action === previewed.action
      && current.holiday_date === previewed.holiday_date
      && current.holiday_name === previewed.holiday_name
      && current.is_double_pay_default === previewed.is_double_pay_default
      && current.from_date === previewed.from_date
      && current.to_date === previewed.to_date,
  );
}

function HolidayPolicyWorkspace() {
  const year = taipeiCalendarDate(new Date()).year;
  const [fromDate, setFromDate] = useState(`${year}-01-01`);
  const [toDate, setToDate] = useState(`${year}-12-31`);
  const [action, setAction] = useState<HolidayAction>('upsert');
  const [holidayDate, setHolidayDate] = useState(todayIsoDate());
  const [holidayName, setHolidayName] = useState('');
  const [doublePay, setDoublePay] = useState(false);
  const [reason, setReason] = useState('依核准政策維護國定假日');
  const [, setStoreRevision] = useState(0);

  useEffect(() => {
    holidayFlowStore.clear();
    const unsubscribe = holidayFlowStore.subscribe(() => setStoreRevision((value) => value + 1));
    return () => {
      unsubscribe();
      holidayFlowStore.clear();
    };
  }, []);

  const draft = holidayFlowStore.get();
  const machine = resolveHolidayMachineState(draft);
  const calendar = draft?.calendar ?? null;
  const calendarMatchesHorizon = calendar?.planning_horizon.from_date === fromDate
    && calendar.planning_horizon.to_date === toDate;
  const busy = ['query_loading', 'preview_loading', 'apply_pending', 'receipt_received', 'requery_loading']
    .includes(machine.type);

  const buildPreviewRequest = (
    overrides: Partial<HolidayPreviewRequest> = {},
  ): HolidayPreviewRequest | null => {
    const request: HolidayPreviewRequest = {
      action,
      holiday_date: holidayDate,
      holiday_name: action === 'upsert' ? holidayName.trim() || null : null,
      is_double_pay_default: action === 'upsert' ? doublePay : false,
      from_date: fromDate,
      to_date: toDate,
      ...overrides,
    };
    if (!request.holiday_date || !request.from_date || !request.to_date) return null;
    if (request.from_date > request.to_date) return null;
    if (request.holiday_date < request.from_date || request.holiday_date > request.to_date) return null;
    if (request.action === 'upsert' && !request.holiday_name) return null;
    return request;
  };

  useEffect(() => {
    if (!draft?.preview) return;
    const request = buildPreviewRequest();
    if (request) setHolidayDraft(request);
  }, [action, doublePay, fromDate, holidayDate, holidayName, toDate]);

  const query = () => {
    if (!fromDate || !toDate || fromDate > toDate || busy) return;
    void queryHolidayFlow({ from_date: fromDate, to_date: toDate }).catch(() => undefined);
  };

  const preview = () => {
    const request = buildPreviewRequest();
    if (!request || !calendarMatchesHorizon || busy) return;
    setHolidayDraft(request);
    void previewHolidayFlow(request).catch(() => undefined);
  };

  const currentPreviewRequest = buildPreviewRequest();
  const previewMatchesCurrentInputs = holidayPreviewRequestsMatch(
    currentPreviewRequest,
    draft?.previewRequest ?? null,
  );
  const previewNeedsRefresh = Boolean(
    draft?.previewRequest && !draft.preview && machine.type === 'query_ready',
  );

  const apply = () => {
    const previewResult = draft?.preview;
    const previewRequest = draft?.previewRequest;
    if (!previewResult || !previewRequest || !previewMatchesCurrentInputs || !calendarMatchesHorizon || !reason.trim() || busy) return;
    const request: HolidayApplyRequest = {
      ...previewRequest,
      expected_calendar_version: previewResult.command.expected_calendar_version,
      preview_fingerprint: previewResult.preview_fingerprint,
      reason: reason.trim(),
    };
    void applyHolidayFlow(request).catch(() => undefined);
  };

  const error = draft?.error;
  const errorText = error
    ? `[${error.publicCode ?? error.code}] ${error.message}${error.correlationId ? `｜Correlation: ${error.correlationId}` : ''}`
    : null;

  return (
    <section className="holiday-policy-workspace" data-surface-id="scheduling.holiday-policy">
      <header className="holiday-policy-header">
        <div>
          <p className="holiday-policy-kicker">Query → Preview → Apply → Receipt</p>
          <h2>國定假日與預設政策</h2>
          <p>日曆版本、雙薪預設與變更結果全部採用後端根事實，前端不推導薪資或服務日。</p>
        </div>
        <span className={`holiday-policy-state state-${machine.type}`}>{machine.type}</span>
      </header>

      <div className="holiday-policy-horizon">
        <label>
          查詢起日
          <input
            aria-label="國定假日查詢起日"
            type="date"
            value={fromDate}
            disabled={busy}
            onChange={(event) => setFromDate(event.target.value)}
          />
        </label>
        <label>
          查詢迄日
          <input
            aria-label="國定假日查詢迄日"
            type="date"
            value={toDate}
            disabled={busy}
            onChange={(event) => setToDate(event.target.value)}
          />
        </label>
        <button type="button" data-control-id="scheduling.holiday.query" disabled={busy || !fromDate || !toDate || fromDate > toDate} onClick={query}>
          {machine.type === 'query_loading' ? '查詢中…' : '查詢國定假日政策'}
        </button>
      </div>

      {calendar && (
        <section className="holiday-policy-calendar" aria-label="國定假日日曆根事實">
          <div className="holiday-policy-meta">
            <span>來源：<strong>{calendar.source_identity}</strong></span>
            <span>日曆版本：<code>{calendar.calendar_version.slice(0, 12)}…</code></span>
            <span>{calendar.planning_horizon.from_date}～{calendar.planning_horizon.to_date}</span>
          </div>
          {calendar.holidays.length === 0 ? (
            <p className="holiday-policy-notice">此查詢區間沒有國定假日根事實。</p>
          ) : (
            <ul className="holiday-policy-list">
              {calendar.holidays.map((holiday) => (
                <li key={holiday.holiday_date}>
                  <time>{holiday.holiday_date}</time>
                  <strong>{holiday.holiday_name}</strong>
                  <span>{holiday.is_double_pay_default ? '預設雙薪' : '一般薪資政策'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <div className="holiday-policy-form-grid">
        <label>
          變更類型
          <select
            aria-label="國定假日變更類型"
            value={action}
            disabled={busy}
            onChange={(event) => {
              const next = event.target.value as HolidayAction;
              setAction(next);
            }}
          >
            <option value="upsert">新增或更新</option>
            <option value="delete">刪除</option>
          </select>
        </label>
        <label>
          國定假日日期
          <input
            aria-label="國定假日日期"
            type="date"
            value={holidayDate}
            disabled={busy}
            onChange={(event) => {
              setHolidayDate(event.target.value);
            }}
          />
        </label>
        <label>
          國定假日名稱
          <input
            aria-label="國定假日名稱"
            value={holidayName}
            disabled={busy || action === 'delete'}
            maxLength={100}
            onChange={(event) => {
              setHolidayName(event.target.value);
            }}
          />
        </label>
        <label className="holiday-policy-check">
          <input
            type="checkbox"
            checked={doublePay}
            disabled={busy || action === 'delete'}
            onChange={(event) => {
              setDoublePay(event.target.checked);
            }}
          />
          後端政策預設雙薪
        </label>
        <label className="holiday-policy-reason">
          套用原因
          <textarea
            aria-label="套用原因"
            value={reason}
            maxLength={500}
            disabled={busy}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
      </div>

      <div className="holiday-policy-actions">
        <button type="button" data-control-id="scheduling.holiday.preview" disabled={!calendarMatchesHorizon || !buildPreviewRequest() || busy} onClick={preview}>
          {machine.type === 'preview_loading' ? '預覽中…' : '預覽國定假日變更'}
        </button>
        <button
          type="button"
          data-control-id="scheduling.holiday.apply"
          aria-describedby={previewNeedsRefresh || !calendarMatchesHorizon ? 'scheduling-holiday-apply-guidance' : undefined}
          disabled={!draft?.preview || !previewMatchesCurrentInputs || !calendarMatchesHorizon || !reason.trim() || busy}
          onClick={apply}
        >
          {machine.type === 'apply_pending' || machine.type === 'requery_loading' ? '套用並觀察中…' : '套用國定假日變更'}
        </button>
      </div>
      {calendar && !calendarMatchesHorizon && (
        <small className="holiday-policy-notice">查詢區間已變更，請重新查詢日曆後再建立 Preview。</small>
      )}
      {(previewNeedsRefresh || !calendarMatchesHorizon) && (
        <small id="scheduling-holiday-apply-guidance" className="holiday-policy-notice">
          Preview 後的查詢區間或變更欄位已調整；請重新查詢並建立新的 Preview，才能套用。
        </small>
      )}

      {draft?.preview && (
        <section className="holiday-policy-preview" aria-label="國定假日變更預覽">
          <h3>預覽已產生</h3>
          <p>{draft.preview.command.action}｜{draft.preview.command.holiday_date}｜Preview {draft.preview.preview_fingerprint.slice(0, 12)}…</p>
          <p>排班影響：{draft.preview.schedule_impact}｜薪資影響：{draft.preview.payroll_impact}</p>
        </section>
      )}

      {draft?.receipt && (
        <section className="holiday-policy-receipt" aria-live="polite">
          <h3>已收到正式 receipt</h3>
          <p>{draft.receipt.receipt_key}｜{draft.receipt.resulting_calendar_version.slice(0, 12)}…</p>
          <p>{machine.type === 'observed' ? '已觀察最新後端日曆版本。' : 'Receipt 已保留，正在重新查詢。'}</p>
        </section>
      )}

      {errorText && <p className="holiday-policy-notice error" role="alert">{errorText}</p>}
      {machine.type === 'outcome_unknown' && (
        <button type="button" onClick={() => void retryHolidayApplyFlow().catch(() => undefined)}>
          以相同識別碼重試 Apply
        </button>
      )}
      {machine.type === 'observation_failed' && (
        <button type="button" onClick={() => void retryHolidayObservationFlow().catch(() => undefined)}>
          重試觀察後端日曆
        </button>
      )}
    </section>
  );
}

function LeaveSubstitutionWorkspace({
  suggestedCaseNo,
  staffList,
}: {
  suggestedCaseNo: string | null;
  staffList: readonly StaffDirectoryCardViewModel[];
}) {
  const [caseNo, setCaseNo] = useState(suggestedCaseNo ?? '');
  const [assignmentId, setAssignmentId] = useState<number | null>(null);
  const [scheduleId, setScheduleId] = useState<number | null>(null);
  const [resolutionType, setResolutionType] = useState<LeaveResolutionType>('substitute');
  const [substituteStaffId, setSubstituteStaffId] = useState<number | null>(null);
  const [isDoublePay, setIsDoublePay] = useState(false);
  const [reason, setReason] = useState('正式處理請假代班');
  const [confirmed, setConfirmed] = useState(false);
  const [, setStoreRevision] = useState(0);

  useEffect(
    () => leaveSubstitutionFlowStore.subscribe(() => setStoreRevision((value) => value + 1)),
    [],
  );
  useEffect(() => {
    if (!caseNo && suggestedCaseNo) setCaseNo(suggestedCaseNo);
  }, [caseNo, suggestedCaseNo]);

  const normalizedCaseNo = caseNo.trim();
  const draft = normalizedCaseNo ? leaveSubstitutionFlowStore.get(normalizedCaseNo) : undefined;
  const machine = resolveLeaveSubstitutionMachineState(draft);
  const assignments = draft?.assignments ?? [];
  const selectedAssignment = assignments.find((item) => item.assignment_id === assignmentId) ?? null;
  const schedules = selectedAssignment?.official_schedules ?? [];
  const selectedSchedule = schedules.find((item) => item.schedule_id === scheduleId) ?? null;
  const busy = ['query_loading', 'preview_loading', 'apply_pending', 'receipt_received', 'requery_loading', 'outcome_unknown', 'observation_failed']
    .includes(machine.type);

  useEffect(() => {
    if (assignments.length === 0) {
      setAssignmentId(null);
      setScheduleId(null);
      return;
    }
    if (!assignments.some((item) => item.assignment_id === assignmentId)) {
      const first = assignments[0];
      setAssignmentId(first.assignment_id);
      setScheduleId(first.official_schedules[0]?.schedule_id ?? null);
    }
  }, [assignmentId, assignments]);

  useEffect(() => {
    if (!selectedAssignment) return;
    if (!selectedAssignment.official_schedules.some((item) => item.schedule_id === scheduleId)) {
      setScheduleId(selectedAssignment.official_schedules[0]?.schedule_id ?? null);
    }
  }, [scheduleId, selectedAssignment]);

  const buildPreviewRequest = (): LeaveSubstitutionPreviewRequest | null => {
    if (!selectedAssignment || !selectedSchedule) return null;
    if (resolutionType === 'substitute' && substituteStaffId === null) return null;
    return {
      original_assignment_id: selectedAssignment.assignment_id,
      items: [{
        original_schedule_id: selectedSchedule.schedule_id,
        work_date: selectedSchedule.work_date,
        resolution_type: resolutionType,
        substitute_staff_id: resolutionType === 'substitute' ? substituteStaffId : null,
        is_double_pay: resolutionType === 'substitute' ? isDoublePay : false,
      }],
      leave_request_id: null,
      expected_leave_request_version: null,
    };
  };

  const invalidatePreview = () => {
    setConfirmed(false);
    const request = buildPreviewRequest();
    if (request && normalizedCaseNo && draft?.assignments) {
      setLeaveSubstitutionDraft(normalizedCaseNo, request);
    }
  };

  const query = () => {
    if (!normalizedCaseNo || busy) return;
    setConfirmed(false);
    void queryLeaveSubstitutionFlow(normalizedCaseNo).catch(() => undefined);
  };

  const preview = () => {
    const request = buildPreviewRequest();
    if (!request || !normalizedCaseNo || busy) return;
    setConfirmed(false);
    setLeaveSubstitutionDraft(normalizedCaseNo, request);
    void previewLeaveSubstitutionFlow(normalizedCaseNo).catch(() => undefined);
  };

  const apply = () => {
    if (!draft?.preview || !draft.previewRequest || !confirmed || !reason.trim() || busy) return;
    const request: LeaveSubstitutionApplyRequest = {
      ...draft.previewRequest,
      expected_order_version: draft.preview.order_version,
      expected_scheduling_version: draft.preview.scheduling_version,
      expected_client_finance_version: draft.preview.client_finance_version,
      expected_payroll_version: draft.preview.payroll_version,
      preview_fingerprint: draft.preview.preview_fingerprint,
      reason: reason.trim(),
    };
    void applyLeaveSubstitutionFlow(normalizedCaseNo, request).catch(() => undefined);
  };

  const error = draft?.error;
  const errorText = error
    ? `[${error.publicCode ?? error.code}] ${error.message}${error.correlationId ? `｜Correlation: ${error.correlationId}` : ''}`
    : null;

  return (
    <section className="leave-substitution-workspace" data-surface-id="scheduling.leave-substitution">
      <header className="leave-substitution-header">
        <div>
          <p className="leave-substitution-kicker">Query → Preview → Apply → Receipt</p>
          <h2>服務中請假與緊急代班調度</h2>
          <p>只使用後端提供的正式 assignment、schedule identity 與 Preview 結果，不在前端推算日期或帳務。</p>
        </div>
        <span className={`leave-substitution-state state-${machine.type}`}>{machine.type}</span>
      </header>

      <div className="leave-substitution-query-row">
        <label>
          訂單編號
          <input
            aria-label="請假代班訂單編號"
            value={caseNo}
            disabled={busy}
            onChange={(event) => setCaseNo(event.target.value)}
            placeholder="例如 CASE-001"
          />
        </label>
        <button type="button" data-control-id="scheduling.leave.query" disabled={!normalizedCaseNo || busy} onClick={query}>
          {machine.type === 'query_loading' ? '查詢中…' : '查詢正式指派'}
        </button>
      </div>

      {draft?.assignments && draft.assignments.length === 0 && (
        <p className="leave-substitution-notice">此訂單目前沒有正式指派。請先至訂單管理完成正式排班，再回此處建立代班 Preview。</p>
      )}

      {assignments.length > 0 && (
        <div className="leave-substitution-form-grid">
          <label>
            原指派
            <select
              aria-label="原服務指派"
              value={assignmentId ?? ''}
              disabled={busy}
              onChange={(event) => {
                setAssignmentId(Number(event.target.value));
                setScheduleId(null);
                invalidatePreview();
              }}
            >
              {assignments.map((assignment) => (
                <option key={assignment.assignment_id} value={assignment.assignment_id}>
                  #{assignment.assignment_id}｜人員 #{assignment.staff_id}｜{assignment.assigned_start_date}～{assignment.assigned_end_date}
                </option>
              ))}
            </select>
          </label>
          <label>
            正式服務日
            <select
              aria-label="正式服務日"
              value={scheduleId ?? ''}
              disabled={busy || schedules.length === 0}
              onChange={(event) => {
                setScheduleId(Number(event.target.value));
                invalidatePreview();
              }}
            >
              {schedules.length === 0 && <option value="">此指派目前沒有正式服務日</option>}
              {schedules.map((schedule) => (
                <option key={schedule.schedule_id} value={schedule.schedule_id}>
                  {schedule.work_date}｜Schedule #{schedule.schedule_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            處理方式
            <select
              aria-label="請假代班處理方式"
              value={resolutionType}
              disabled={busy}
              onChange={(event) => {
                const next = event.target.value as LeaveResolutionType;
                setResolutionType(next);
                if (next === 'defer_following_assignments') {
                  setSubstituteStaffId(null);
                  setIsDoublePay(false);
                }
                invalidatePreview();
              }}
            >
              <option value="substitute">安排代班</option>
              <option value="defer_following_assignments">順延後續服務</option>
            </select>
          </label>
          <label>
            代班人員
            <select
              aria-label="代班人員"
              value={substituteStaffId ?? ''}
              disabled={busy || resolutionType !== 'substitute'}
              onChange={(event) => {
                setSubstituteStaffId(event.target.value ? Number(event.target.value) : null);
                invalidatePreview();
              }}
            >
              <option value="">請選擇</option>
              {staffList.filter((staff) => staff.id !== selectedAssignment?.staff_id).map((staff) => (
                <option key={staff.id} value={staff.id}>{staff.displayName}｜#{staff.id}</option>
              ))}
            </select>
          </label>
          <label className="leave-substitution-check">
            <input
              type="checkbox"
              checked={isDoublePay}
              disabled={busy || resolutionType !== 'substitute'}
              onChange={(event) => {
                setIsDoublePay(event.target.checked);
                invalidatePreview();
              }}
            />
            此日為雙薪
          </label>
        </div>
      )}

      {selectedAssignment && schedules.length === 0 && (
        <p className="leave-substitution-notice error">此指派目前沒有正式服務日，不能建立 Preview；請先完成正式排班。</p>
      )}

      <div className="leave-substitution-actions">
        <button
          type="button"
          data-control-id="scheduling.leave.preview"
          disabled={!buildPreviewRequest() || busy}
          onClick={preview}
        >
          {machine.type === 'preview_loading' ? '預覽中…' : '建立安全預覽'}
        </button>
        {!draft?.preview && (
          <small data-control-id="scheduling.leave.apply-gate">建立安全預覽並通過檢核後，才會顯示確認套用。</small>
        )}
      </div>

      {draft?.preview && (
        <section className="leave-substitution-preview" aria-label="請假代班預覽">
          <h3>後端 Preview</h3>
          <dl>
            <div><dt>狀態</dt><dd>{draft.preview.apply_readiness.status}</dd></div>
            <div><dt>取消指派</dt><dd>{draft.preview.cancelled_assignment_ids.join('、') || '無'}</dd></div>
            <div><dt>結果日</dt><dd>{draft.preview.outcomes.map((item) => item.resulting_service_date).join('、')}</dd></div>
            <div><dt>指紋</dt><dd>{draft.preview.preview_fingerprint.slice(0, 12)}…</dd></div>
          </dl>
          {draft.preview.apply_readiness.blockers.length > 0 && (
            <p className="leave-substitution-notice error">{draft.preview.apply_readiness.blockers.join('、')}</p>
          )}
          <label>
            處理原因
            <textarea
              aria-label="請假代班處理原因"
              value={reason}
              maxLength={500}
              disabled={busy}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <label className="leave-substitution-check confirm">
            <input type="checkbox" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} />
            我已核對後端 Preview，確認執行此變更
          </label>
          <button
            type="button"
            data-control-id="scheduling.leave.apply"
            disabled={busy || !confirmed || !reason.trim() || draft.preview.apply_readiness.status !== 'ready'}
            onClick={apply}
          >
            {machine.type === 'apply_pending' || machine.type === 'requery_loading' ? '套用並確認中…' : '確認套用'}
          </button>
        </section>
      )}

      {draft?.receipt && (
        <section className="leave-substitution-receipt" aria-live="polite">
          <h3>已收到正式 Receipt</h3>
          <p>Batch：{draft.receipt.batch_key}｜Scheduling v{draft.receipt.scheduling_version}</p>
          <p>{machine.type === 'observed' ? '已重新查詢並確認最新正式指派。' : 'Receipt 已保留，正在確認最新投影。'}</p>
        </section>
      )}

      {errorText && <p className="leave-substitution-notice error" role="alert">{errorText}</p>}
      {machine.type === 'outcome_unknown' && (
        <button type="button" onClick={() => void retryLeaveSubstitutionApplyFlow(normalizedCaseNo).catch(() => undefined)}>
          以相同識別碼重試 Apply
        </button>
      )}
      {machine.type === 'observation_failed' && (
        <button type="button" onClick={() => void retryLeaveSubstitutionObservationFlow(normalizedCaseNo).catch(() => undefined)}>
          重試 Receipt 後查詢
        </button>
      )}
      {machine.type === 'stale' && <button type="button" onClick={query}>重新查詢最新資料</button>}
    </section>
  );
}

export type CalendarRowState =
  | { kind: 'loaded'; row: SchedulingCalendarRowViewModel }
  | { kind: 'empty' }
  | { kind: 'terms_incomplete' }
  | { kind: 'error'; message: string };

function WaitingDepositLockControl({ caseNo: suggestedCaseNo, onApplied }: { caseNo: string | null; onApplied: () => void }) {
  const [caseNoInput, setCaseNoInput] = useState(suggestedCaseNo ?? '');
  const [preview, setPreview] = useState<WaitingDepositPreview | null>(null);
  const [receipt, setReceipt] = useState<WaitingDepositReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (suggestedCaseNo) setCaseNoInput(suggestedCaseNo);
  }, [suggestedCaseNo]);
  useEffect(() => { setPreview(null); setReceipt(null); setError(null); }, [caseNoInput]);

  const runPreview = async () => {
    const caseNo = caseNoInput.trim();
    if (!caseNo || busy) return;
    setBusy(true); setError(null); setReceipt(null);
    try {
      const plan = await waitingDepositLockClient.queryPlan(caseNo);
      if (plan.status !== 'proposed') {
        setError(`案件目前為 ${plan.status} 方案；只有洽談中的 proposed 方案可以建立預約鎖。`);
        return;
      }
      if (plan.activeLockId !== null) {
        setError(`案件已有有效預約鎖 #${plan.activeLockId}，不會重複建立。`);
        return;
      }
      setPreview(await waitingDepositLockClient.preview(caseNo, plan.planId));
    } catch (caught) {
      setError(caught instanceof ApiHttpError ? `[${caught.code}] ${caught.message}` : caught instanceof Error ? caught.message : '預約鎖定 Preview 失敗。');
    } finally { setBusy(false); }
  };

  const apply = async () => {
    const caseNo = caseNoInput.trim();
    if (!caseNo || !preview?.apply_allowed || busy) return;
    setBusy(true); setError(null);
    try {
      const result = await waitingDepositLockClient.apply(caseNo, preview.plan_id, preview.preview_fingerprint);
      setReceipt(result); setPreview(null); onApplied();
    } catch (caught) {
      setError(caught instanceof ApiHttpError ? `[${caught.code}] ${caught.message}` : caught instanceof Error ? caught.message : '預約鎖定 Apply 失敗。');
    } finally { setBusy(false); }
  };

  return <div className="waiting-lock-control">
    <label>洽談中案件編號
      <input aria-label="洽談中案件編號" data-control-id="scheduling.projection.order-input" value={caseNoInput}
        onChange={(event) => setCaseNoInput(event.target.value)} placeholder="例如 115000015" disabled={busy} />
    </label>
    <button data-control-id="scheduling.projection.lock-preview" aria-describedby="scheduling-waiting-lock-guidance" onClick={() => void runPreview()} disabled={!caseNoInput.trim() || busy}>
      {busy ? '處理中…' : '預覽預約鎖定'}
    </button>
    <button data-control-id="scheduling.projection.lock-apply" aria-describedby="scheduling-waiting-lock-guidance" onClick={() => void apply()} disabled={!preview?.apply_allowed || busy}>
      確認套用預約鎖定
    </button>
    <small id="scheduling-waiting-lock-guidance">
      {!caseNoInput.trim()
        ? '輸入已建立有效媒合方案的洽談中案件編號後即可 Preview；Preview 通過後才能套用預約鎖。'
        : preview?.apply_allowed
          ? 'Preview 已通過，可確認套用預約鎖。'
          : '先建立 Preview；確認沒有衝突後才可套用預約鎖。'}
    </small>
    {preview && <div className="waiting-lock-preview"><strong>Preview：服務 {preview.service_day_count} 日、Buffer {preview.buffer_day_count} 日</strong>
      <span>衝突 {preview.conflicts.length} 筆；{preview.apply_allowed ? '可套用' : '有衝突，禁止套用'}</span></div>}
    {receipt && <p className="leave-substitution-notice success">預約鎖 #{receipt.lock_id} 已{receipt.result === 'created' ? '建立' : '確認既有結果'}，共 {receipt.lock_rows.length} 日。</p>}
    {error && <p className="leave-substitution-notice error" role="alert">{error}</p>}
  </div>;
}

function SchedulePrecisionWorkspace({ onClose }: { onClose: () => void }) {
  const [startDate, setStartDate] = useState(todayIsoDate());
  const [serviceDays, setServiceDays] = useState(20);
  const [serviceMode, setServiceMode] = useState<'週休1日' | '週休2日' | '連續服務'>('週休1日');
  const [result, setResult] = useState<SchedulePrecisionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const calculate = async () => {
    if (!startDate || serviceDays < 1 || busy) return;
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await schedulePrecisionClient.calculate({ actual_start_date: startDate, target_service_days: serviceDays, service_mode: serviceMode }));
    } catch (caught) {
      setError(caught instanceof ApiHttpError ? `[${caught.code}] ${caught.message}` : caught instanceof Error ? caught.message : '出勤精算失敗。');
    } finally { setBusy(false); }
  };

  return <section className="scheduling-workspace schedule-precision-workspace" aria-label="訂單出勤精算工作台">
    <div className="scheduling-workspace-heading"><div><h2>訂單出勤精算工作台</h2><p>日期、週統計與薪資預估全部採用 server calculation。</p></div>
      <button type="button" onClick={onClose}>關閉</button></div>
    <div className="schedule-precision-form">
      <label>實際起始日<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} disabled={busy} /></label>
      <label>目標服務日<input type="number" min="1" value={serviceDays} onChange={(event) => setServiceDays(Number(event.target.value))} disabled={busy} /></label>
      <label>服務模式<select value={serviceMode} onChange={(event) => setServiceMode(event.target.value as typeof serviceMode)} disabled={busy}>
        <option value="週休1日">週休1日</option><option value="週休2日">週休2日</option><option value="連續服務">連續服務</option>
      </select></label>
      <button type="button" onClick={() => void calculate()} disabled={!startDate || serviceDays < 1 || busy}>{busy ? '精算中…' : '執行出勤精算'}</button>
    </div>
    {error && <p className="leave-substitution-notice error" role="alert">{error}</p>}
    {result && <div className="schedule-precision-result">
      <strong>{result.actual_start_date} ～ {result.actual_end_date}</strong>
      <span>服務 {result.actual_work_days_count} 日｜休息 {result.rest_days_count} 日｜曆日 {result.total_calendar_days} 日</span>
      <span>{result.total_estimated_salary === null ? '未輸入薪資基數，因此不顯示薪資估算' : `預估薪資 NT$ ${result.total_estimated_salary.toLocaleString('zh-TW')}`}</span>
      <span>週統計 {result.weekly_stats.length} 週｜逐日明細 {result.day_by_day.length} 筆｜國定假日 {result.national_holidays_found.length} 筆</span>
    </div>}
  </section>;
}

type SchedulingDiagnosticTone = 'unavailable' | 'active' | 'waiting' | 'leave';

type EligibilityCollisionState =
  | { kind: 'idle' }
  | { kind: 'loading'; caseNo: string }
  | { kind: 'ready'; data: SchedulingEligibilityCollisionViewModel }
  | { kind: 'error'; message: string };

function eligibilityErrorMessage(error: unknown): string {
  if (!(error instanceof SchedulingEligibilityCollisionError)) {
    return '資格與檔期服務暫時無法回應，請稍後重試。';
  }
  if (error.code === 'SCHEDULING_ELIGIBILITY_NOT_FOUND') {
    return '找不到指定案件或服務人員，請確認案件編號與人員後重試。';
  }
  if (error.code === 'SCHEDULING_ELIGIBILITY_CONFLICT') {
    return '案件或排班版本已變更，請重新查詢最新資料。';
  }
  if (error.code === 'SCHEDULING_ELIGIBILITY_UNAUTHENTICATED') {
    return '目前沒有資格查詢權限，請確認管理員登入狀態。';
  }
  if (error.code === 'SCHEDULING_ELIGIBILITY_VALIDATION') {
    return '案件服務日期、每日時段或服務人員資格主檔尚未完整，請補齊後重試。';
  }
  return '資格與檔期服務暫時無法回應，請稍後重試。';
}

function eligibilityDisplay(data: SchedulingEligibilityCollisionViewModel) {
  const eligibility = {
    eligible: '資格符合',
    ineligible: '資格不符合',
    partial: '資格資料待補正',
    unavailable: '資格主檔待建立',
  }[data.eligibility];
  const availability = {
    available: '檔期可用',
    blocked: '檔期衝突阻擋',
    requires_review: '檔期需人工確認（資料待補正）',
    unknown: '檔期狀態未知（資料待補正）',
  }[data.availability];
  const coverage = {
    complete: '完整',
    incomplete: '不完整',
    requires_review: '需人工確認（資料待補正）',
    unavailable: '覆蓋資料待建立',
  }[data.coverage.status];
  const needsCorrection = data.partialData.length > 0
    || data.eligibility === 'partial'
    || data.eligibility === 'unavailable'
    || data.availability === 'requires_review'
    || data.availability === 'unknown'
    || data.qualificationChecks.some((check) => check.status === 'unknown')
    || data.collisions.some((collision) => collision.severity === 'requires_review')
    || data.coverage.status !== 'complete';
  return { eligibility, availability, coverage, needsCorrection };
}

function qualificationStatusLabel(status: SchedulingEligibilityCollisionViewModel['qualificationChecks'][number]['status']): string {
  if (status === 'pass') return '通過';
  if (status === 'fail') return '不通過';
  return '資料待補正（無法判定）';
}

function collisionSeverityLabel(severity: SchedulingEligibilityCollisionViewModel['collisions'][number]['severity']): string {
  return severity === 'hard_block' ? '排班阻擋' : '資料待補正（需人工確認）';
}

interface SchedulingDiagnosticBadge {
  tone: SchedulingDiagnosticTone;
  text: string;
}

const LOADING_DIAGNOSTIC: SchedulingDiagnosticBadge = {
  tone: 'unavailable',
  text: '⚪ 正在載入正式排班',
};

const NO_OCCUPANCY_DIAGNOSTIC: SchedulingDiagnosticBadge = {
  tone: 'unavailable',
  text: '⚪ 本月無排班占用',
};
const NO_OCCUPANCY_SLOT_TEXT = '本月無排班占用';
const NO_OCCUPANCY_SLOT_DETAIL = '已完成 server 查詢；接單資格與撞期請使用上方案件查詢。';

// 只將 server occupancy／typed error 映射為標籤，不從空資料推導接單資格或撞期。
function getStaffDiagnosticBadge(state: CalendarRowState | undefined): SchedulingDiagnosticBadge {
  if (!state) {
    return LOADING_DIAGNOSTIC;
  }
  if (state.kind === 'empty') {
    return { tone: 'unavailable', text: '⚪ 排班投影缺少日期' };
  }
  if (state.kind === 'terms_incomplete') {
    return { tone: 'waiting', text: '🟡 ⚠️ 時段未確認 (需補齊資料)' };
  }
  if (state.kind === 'error') {
    return { tone: 'unavailable', text: '⚪ 查詢異常／無法判定' };
  }
  const row = state.row;
  const hasLeave = row.days.some((d) => d.tone === 'leave');
  const hasBuffer = row.days.some((d) => d.tone === 'buffer');
  const hasWaiting = row.days.some((d) => d.tone === 'waiting');
  const hasActive = row.days.some((d) => d.tone === 'active');
  const hasActiveAssignment = row.assignmentStatuses.includes('active');
  const hasPlannedAssignment = row.assignmentStatuses.includes('planned');
  const hasCompletedAssignment = row.assignmentStatuses.includes('completed');
  const hasUnknownOfficialWorkday = row.assignmentStatuses.length === 0
    && row.days.some((day) => (
      day.occupancyKinds.includes('official_workday')
      && day.assignmentStatuses.length === 0
    ));

  if (hasLeave) {
    return { tone: 'leave', text: '🟣 服務中請假留停 (待代班)' };
  }
  if (hasActiveAssignment) {
    return { tone: 'active', text: '🟢 正常履約中' };
  }
  if (hasPlannedAssignment) {
    return { tone: 'active', text: '🟢 已排定待開始' };
  }
  if (hasWaiting) {
    return { tone: 'waiting', text: '🔵 待定金核銷鎖定中' };
  }
  if (hasBuffer) {
    return { tone: 'waiting', text: '🟡 7天防撞期 Buffer 鎖定' };
  }
  if (hasUnknownOfficialWorkday) {
    return { tone: 'waiting', text: '⚠️ 服務狀態未知／資料待補正' };
  }
  if (hasCompletedAssignment || hasActive) {
    return { tone: 'active', text: '⚪ 服務已完成' };
  }
  return NO_OCCUPANCY_DIAGNOSTIC;
}

// 動態將 Server 天數投影合併為連續甘特區間條塊
interface GanttSpan {
  id: string;
  startDay: number;
  endDay: number;
  tone: 'active' | 'buffer' | 'leave' | 'waiting' | 'available' | 'unavailable';
  icon?: string;
  caseText: string;
  statusLabel?: string;
}

function buildGanttSpans(
  state: CalendarRowState | undefined,
  totalDays: number
): GanttSpan[] {
  if (!state || state.kind === 'empty') {
    return [
      {
        id: 'full-unavailable',
        startDay: 1,
        endDay: totalDays,
        tone: 'unavailable',
        icon: '⚪',
        caseText: state ? '排班投影缺少日期' : '正在載入正式排班',
        statusLabel: state ? '請重試月曆查詢。' : '正在讀取 server projection。',
      },
    ];
  }

  if (state.kind === 'terms_incomplete') {
    return [
      {
        id: 'full-incomplete',
        startDay: 1,
        endDay: totalDays,
        tone: 'waiting',
        icon: '⚠️',
        caseText: '訂單時段條款不完整 (需補正)',
        statusLabel: '包含未指定每日時段之指派，請至訂單/異常中心補齊資料',
      },
    ];
  }

  if (state.kind === 'error') {
    return [
      {
        id: 'full-err',
        startDay: 1,
        endDay: totalDays,
        tone: 'unavailable',
        icon: '⚪',
        caseText: '排班資料載入異常',
        statusLabel: `${state.message}；請重試月曆查詢。`,
      },
    ];
  }

  const row = state.row;
  const hasAnyOccupancy = row.days.some((d) => d.occupancyKinds.length > 0);
  if (!hasAnyOccupancy) {
    return [
      {
        id: 'full-unavailable',
        startDay: 1,
        endDay: totalDays,
        tone: 'unavailable',
        icon: '⚪',
        caseText: NO_OCCUPANCY_SLOT_TEXT,
        statusLabel: NO_OCCUPANCY_SLOT_DETAIL,
      },
    ];
  }

  const spans: GanttSpan[] = [];
  let current: GanttSpan | null = null;

  row.days.forEach((day, index) => {
    const dayNum = index + 1;
    const isOccupied = day.occupancyKinds.length > 0;
    const unknownOfficialWorkday = row.assignmentStatuses.length === 0
      && day.occupancyKinds.includes('official_workday')
      && day.assignmentStatuses.length === 0;
    const tone: GanttSpan['tone'] = unknownOfficialWorkday
      ? 'waiting'
      : day.tone === 'rest' ? 'active' : day.tone;
    const hasCase = day.caseLabels.length > 0;
    const caseText = hasCase
      ? day.caseLabels.join('、')
      : (isOccupied ? day.statusLabel : NO_OCCUPANCY_SLOT_TEXT);
    const statusLabel = unknownOfficialWorkday
      ? '服務狀態未知／資料待補正'
      : hasCase ? day.statusLabel : undefined;
    const icon =
      unknownOfficialWorkday ? '⚠️' : tone === 'active' ? '🟢' : tone === 'buffer' ? '🔒' : tone === 'leave' ? '🚑' : tone === 'waiting' ? '🔵' : undefined;

    if (!current) {
      if (isOccupied) {
        current = { id: `span-${dayNum}`, startDay: dayNum, endDay: dayNum, tone, icon, caseText, statusLabel };
      }
    } else if (
      current.tone === tone &&
      current.caseText === caseText &&
      current.statusLabel === statusLabel
    ) {
      current.endDay = dayNum;
    } else {
      spans.push(current);
      if (isOccupied) {
        current = { id: `span-${dayNum}`, startDay: dayNum, endDay: dayNum, tone, icon, caseText, statusLabel };
      } else {
        current = null;
      }
    }
  });

  if (current) {
    spans.push(current);
  }

  return spans;
}

export const SchedulingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SchedulingTab>('calendar');
  const [precisionOpen, setPrecisionOpen] = useState(false);
  const [staffList, setStaffList] = useState<StaffDirectoryCardViewModel[]>([]);
  const [directoryLoading, setDirectoryLoading] = useState<boolean>(true);
  const [directoryError, setDirectoryError] = useState<string | null>(null);
  const [directoryNextCursor, setDirectoryNextCursor] = useState<number | null>(null);
  const [directoryLoadingMore, setDirectoryLoadingMore] = useState(false);
  const [directoryNextPageError, setDirectoryNextPageError] = useState<string | null>(null);

  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [month, setMonth] = useState<MonthSelection>(currentMonth);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchKeyword, setSearchKeyword] = useState<string>('');

  const [calendarRows, setCalendarRows] = useState<Record<number, CalendarRowState>>({});
  const [calendarLoading, setCalendarLoading] = useState<boolean>(false);
  const [calendarError, setCalendarError] = useState<Error | null>(null);
  const [retryGeneration, setRetryGeneration] = useState<number>(0);
  const [eligibilityCaseNo, setEligibilityCaseNo] = useState('');
  const [eligibilityState, setEligibilityState] = useState<EligibilityCollisionState>({ kind: 'idle' });

  const mountedRef = useRef(true);
  const directoryControllerRef = useRef<AbortController | null>(null);
  const directoryPendingCursorRef = useRef<number | null>(null);
  const calendarControllerRef = useRef<AbortController | null>(null);
  const calendarLoadedKeyRef = useRef<Map<number, string>>(new Map());
  const calendarRetryStaffIdsRef = useRef<Set<number>>(new Set());
  const eligibilityControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      directoryControllerRef.current?.abort();
      directoryPendingCursorRef.current = null;
      calendarControllerRef.current?.abort();
      eligibilityControllerRef.current?.abort();
    };
  }, []);

  // 載入服務人員名冊
  const loadDirectory = useCallback(async () => {
    directoryControllerRef.current?.abort();
    const controller = new AbortController();
    directoryControllerRef.current = controller;
    setDirectoryLoading(true);
    setDirectoryError(null);
    setDirectoryNextPageError(null);
    setDirectoryNextCursor(null);
    directoryPendingCursorRef.current = null;

    try {
      const page = adaptStaffDirectoryPage(
        await staffDirectoryClient.queryPage(
          { pageSize: STAFF_PAGE_SIZE },
          { signal: controller.signal }
        )
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      setStaffList(page.items);
      setDirectoryNextCursor(page.nextCursor);
      if (page.items.length > 0) {
        setSelectedStaffId(page.items[0].id);
      }
    } catch (error) {
      if (!mountedRef.current || controller.signal.aborted) return;
      setDirectoryError(error instanceof Error ? error.message : '服務人員摘要載入失敗');
    } finally {
      if (mountedRef.current && !controller.signal.aborted) {
        setDirectoryLoading(false);
      }
    }
  }, []);

  const loadNextDirectoryPage = async () => {
    const cursor = directoryNextCursor;
    if (cursor === null || directoryPendingCursorRef.current === cursor) return;
    directoryControllerRef.current?.abort();
    const controller = new AbortController();
    directoryControllerRef.current = controller;
    directoryPendingCursorRef.current = cursor;
    setDirectoryLoadingMore(true);
    setDirectoryNextPageError(null);
    try {
      const page = adaptStaffDirectoryPage(
        await staffDirectoryClient.queryPage(
          { pageSize: STAFF_PAGE_SIZE, afterId: cursor },
          { signal: controller.signal }
        )
      );
      if (!mountedRef.current || controller.signal.aborted || directoryPendingCursorRef.current !== cursor) return;
      setStaffList((current) => {
        const byId = new Map(current.map((staff) => [staff.id, staff]));
        page.items.forEach((staff) => byId.set(staff.id, staff));
        return [...byId.values()];
      });
      setDirectoryNextCursor(page.nextCursor);
    } catch (error) {
      if (!mountedRef.current || controller.signal.aborted || directoryPendingCursorRef.current !== cursor) return;
      setDirectoryNextPageError(error instanceof Error ? error.message : '下一頁服務人員摘要載入失敗');
    } finally {
      if (mountedRef.current && directoryPendingCursorRef.current === cursor) {
        directoryPendingCursorRef.current = null;
        setDirectoryLoadingMore(false);
      }
    }
  };

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadDirectory();
    });
    return () => {
      cancelled = true;
      directoryControllerRef.current?.abort();
    };
  }, [loadDirectory]);

  const range = useMemo(() => monthRange(month), [month]);

  const prevMonthRef = useRef<MonthSelection | null>(null);

  // 切換月份時重置排班快取
  useEffect(() => {
    if (prevMonthRef.current === null) {
      prevMonthRef.current = month;
      return;
    }
    if (prevMonthRef.current.year !== month.year || prevMonthRef.current.month !== month.month) {
      prevMonthRef.current = month;
      setCalendarRows({});
      calendarLoadedKeyRef.current.clear();
    }
  }, [month]);

  // 甘特矩陣中的每一列都必須有自己的 server projection，不能只查目前選取的人員。
  useEffect(() => {
    if (staffList.length === 0) return undefined;
    const rangeKey = `${range.rangeStart}:${range.rangeEnd}`;
    const staffToLoad = staffList.filter(
      (staff) => calendarLoadedKeyRef.current.get(staff.id) !== rangeKey
        || calendarRetryStaffIdsRef.current.has(staff.id),
    );
    if (staffToLoad.length === 0) return undefined;

    staffToLoad.forEach((staff) => calendarLoadedKeyRef.current.set(staff.id, rangeKey));

    let cancelled = false;
    const controller = new AbortController();
    calendarControllerRef.current?.abort();
    calendarControllerRef.current = controller;
    setCalendarLoading(true);
    setCalendarError(null);

    const loadRows = async () => {
      const results = await Promise.all(staffToLoad.map(async (staff) => {
        try {
          const projection = await schedulingCurrentClient.queryCurrentCalendar(
            {
              staffId: staff.id,
              rangeStart: range.rangeStart,
              rangeEnd: range.rangeEnd,
            },
            { signal: controller.signal },
          );
          const state: CalendarRowState = projection.days.length === 0
            ? { kind: 'empty' }
            : { kind: 'loaded', row: adaptSchedulingProjection(staff, projection) };
          return { staffId: staff.id, state, error: null };
        } catch (caught) {
          const error = caught instanceof Error ? caught : new Error('排班日曆查詢失敗');
          const state: CalendarRowState = caught instanceof SchedulingCurrentError
            && caught.publicCode === 'service_time_terms_incomplete'
            ? { kind: 'terms_incomplete' }
            : { kind: 'error', message: renderError(error) };
          return { staffId: staff.id, state, error: state.kind === 'error' ? error : null };
        }
      }));
      if (!mountedRef.current || controller.signal.aborted || cancelled) return;
      results.forEach((result) => calendarLoadedKeyRef.current.set(result.staffId, rangeKey));
      results.forEach((result) => calendarRetryStaffIdsRef.current.delete(result.staffId));
      setCalendarRows((current) => {
        const next = { ...current };
        results.forEach((result) => {
          next[result.staffId] = result.state;
        });
        return next;
      });
      const failed = results.filter((result) => result.error !== null);
      if (failed.length > 0) {
        setCalendarError(new Error(
          `${failed.length} 位服務人員的排班投影載入失敗；請查看各列狀態後重試。`,
        ));
      }
    };

    queueMicrotask(() => {
      if (!cancelled) {
        void loadRows().finally(() => {
          if (mountedRef.current && !controller.signal.aborted && !cancelled) {
            setCalendarLoading(false);
          }
        });
      }
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [range, retryGeneration, staffList]);

  useEffect(() => {
    eligibilityControllerRef.current?.abort();
    setEligibilityState({ kind: 'idle' });
  }, [selectedStaffId]);

  const queryEligibility = async () => {
    const caseNo = eligibilityCaseNo.trim();
    if (selectedStaffId === null || !caseNo || eligibilityState.kind === 'loading') return;
    eligibilityControllerRef.current?.abort();
    const controller = new AbortController();
    eligibilityControllerRef.current = controller;
    setEligibilityState({ kind: 'loading', caseNo });
    try {
      const projection = await schedulingEligibilityCollisionClient.query(
        { caseNo, staffId: selectedStaffId, asOf: todayIsoDate() },
        { signal: controller.signal }
      );
      if (controller.signal.aborted || !mountedRef.current) return;
      setEligibilityState({ kind: 'ready', data: adaptSchedulingEligibilityCollision(projection) });
    } catch (error) {
      if (controller.signal.aborted || !mountedRef.current) return;
      setEligibilityState({ kind: 'error', message: eligibilityErrorMessage(error) });
    }
  };

  // 篩選與搜尋過濾
  const filteredStaff = useMemo(() => {
    return staffList.filter((staff) => {
      const matchKeyword =
        !searchKeyword ||
        staff.displayName.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        `stf-${String(staff.id).padStart(3, '0')}`.includes(searchKeyword.toLowerCase());

      if (!matchKeyword) return false;

      const state = calendarRows[staff.id];
      if (state?.kind === 'loaded' && !matchesSchedulingFilter(state.row, statusFilter)) return false;
      if (state?.kind !== 'loaded' && statusFilter !== 'all') return false;

      return true;
    });
  }, [staffList, searchKeyword, statusFilter, calendarRows]);

  const selectedStaffRow = selectedStaffId ? calendarRows[selectedStaffId] : null;
  const taipeiToday = todayIsoDate();
  const [, taipeiMonth, taipeiDay] = taipeiToday.split('-');

  const daysList = useMemo(() => monthAxis(month).map((day) => ({
    ...day,
    isToday: day.dateStr === taipeiToday,
  })), [month, taipeiToday]);
  const eligibilityResult = eligibilityState.kind === 'ready'
    ? eligibilityDisplay(eligibilityState.data)
    : null;

  const prevMonthName = `${month.month === 1 ? 12 : month.month - 1}月`;
  const nextMonthName = `${month.month === 12 ? 1 : month.month + 1}月`;

  const retryFailedCalendarRows = () => {
    const failedStaffIds = staffList
      .filter((staff) => calendarRows[staff.id]?.kind === 'error')
      .map((staff) => staff.id);
    if (failedStaffIds.length === 0) return;
    calendarRetryStaffIdsRef.current = new Set(failedStaffIds);
    setRetryGeneration((current) => current + 1);
  };

  return (
    <div data-surface-id="scheduling.page" className="scheduling-gantt-page">
      {/* Page Header */}
      <header className="page-header-banner scheduling-page-header">
        <div>
          <h1 className="page-title">📅 多月嫂排班日曆與調度中心</h1>
          <p className="page-subtitle">
            全景甘特檔期矩陣、接單資格／撞期判定與預約鎖定均使用 server projection。
          </p>
        </div>
        <button
          type="button"
          className="scheduling-precision-control"
          data-control-id="scheduling.precision.open"
          onClick={() => setPrecisionOpen((current) => !current)}
        >
          ⚙️ 訂單出勤精算工作台
        </button>
      </header>
      {precisionOpen && <SchedulePrecisionWorkspace onClose={() => setPrecisionOpen(false)} />}

      {/* Sticky Tabs Bar */}
      <nav className="scheduling-tab-bar" aria-label="排班工作區">
        <button
          data-surface-id="scheduling.tab.calendar"
          className={`scheduling-tab-btn ${activeTab === 'calendar' ? 'active' : ''}`}
          aria-current={activeTab === 'calendar' ? 'page' : undefined}
          onClick={() => setActiveTab('calendar')}
        >
          📅 1. 服務人員排班甘特月曆
        </button>
        <button
          data-surface-id="scheduling.tab.leave_sub"
          className={`scheduling-tab-btn ${activeTab === 'leave_sub' ? 'active' : ''}`}
          onClick={() => setActiveTab('leave_sub')}
        >
          🚑 2. 服務中請假與代班
        </button>
        <button
          data-surface-id="scheduling.tab.holidays"
          className={`scheduling-tab-btn ${activeTab === 'holidays' ? 'active' : ''}`}
          onClick={() => setActiveTab('holidays')}
        >
          🗓️ 3. 國定假日政策
        </button>
        <button
          data-surface-id="scheduling.tab.leave_inbox"
          className={`scheduling-tab-btn ${activeTab === 'leave_inbox' ? 'active' : ''}`}
          onClick={() => setActiveTab('leave_inbox')}
        >
          📥 4. 請假待辦收件匣
        </button>
      </nav>

      {activeTab === 'calendar' && (
        <section
          className="gantt-hero-card"
          data-surface-id="scheduling.calendar"
          aria-label="排班甘特月曆與服務人員 occupancy"
        >
          {/* Projection Lock Panel */}
          <section className="gantt-projection-panel" aria-label="媒合投影狀態">
            <div>
              <strong>🔮 洽談中訂單檔期衝突預覽</strong>
              <p>輸入案件並選擇服務人員，可直接查詢尚未指派候選人的接單資格與撞期。</p>
            </div>
            <div className="waiting-lock-control" aria-label="接單資格與撞期查詢">
              <label>案件編號
                <input
                  aria-label="資格查詢案件編號"
                  data-control-id="scheduling.eligibility.case-input"
                  value={eligibilityCaseNo}
                  onChange={(event) => {
                    eligibilityControllerRef.current?.abort();
                    setEligibilityCaseNo(event.target.value);
                    setEligibilityState({ kind: 'idle' });
                  }}
                  placeholder="例如 115000003"
                />
              </label>
              <label>服務人員
                <select
                  aria-label="服務人員"
                  data-control-id="scheduling.eligibility.staff-select"
                  value={selectedStaffId ?? ''}
                  onChange={(event) => setSelectedStaffId(event.target.value ? Number(event.target.value) : null)}
                >
                  <option value="">請選擇服務人員</option>
                  {staffList.map((staff) => <option key={staff.id} value={staff.id}>{staff.displayName}｜#{staff.id}</option>)}
                </select>
              </label>
              <button
                type="button"
                data-control-id="scheduling.eligibility.query"
                aria-describedby="scheduling-eligibility-guidance"
                disabled={!eligibilityCaseNo.trim() || selectedStaffId === null || eligibilityState.kind === 'loading'}
                onClick={() => void queryEligibility()}
              >
                {eligibilityState.kind === 'loading' ? '查詢中…' : '查詢資格與撞期'}
              </button>
            </div>
            <WaitingDepositLockControl
              caseNo={eligibilityCaseNo.trim() || null}
              onApplied={() => setRetryGeneration((value) => value + 1)}
            />
            <div id="scheduling-eligibility-guidance" data-surface-id="scheduling.eligibility-collision" aria-live="polite">
              {eligibilityState.kind === 'idle' && (
                <p>輸入案件編號並選擇服務人員後，即可查詢正式資格與檔期衝突。</p>
              )}
              {eligibilityState.kind === 'loading' && (
                <p role="status">正在查詢 {eligibilityState.caseNo} 的資格與檔期衝突…</p>
              )}
              {eligibilityState.kind === 'error' && (
                <p role="alert">資格／檔期查詢失敗：{eligibilityState.message}</p>
              )}
              {eligibilityState.kind === 'ready' && eligibilityResult && (
                <div>
                  <p><strong>{eligibilityState.data.caseNo}</strong>：{eligibilityResult.eligibility}；{eligibilityResult.availability}。</p>
                  <p>衝突筆數：{eligibilityState.data.collisionCount}；覆蓋狀態：{eligibilityResult.coverage}。</p>
                  {eligibilityState.data.qualificationChecks.length > 0 && (
                    <section aria-label="資格檢查明細">
                      <h3>資格檢查</h3>
                      <ul>
                        {eligibilityState.data.qualificationChecks.map((check) => (
                          <li key={check.code}>
                            <strong>{check.code}</strong>｜<span>{qualificationStatusLabel(check.status)}</span>
                            <p>{check.detail}</p>
                            <small>{check.owner}｜{check.source_identity}</small>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {eligibilityState.data.collisions.length > 0 && (
                    <section aria-label="衝突與人工審核明細">
                      <h3>衝突與人工審核</h3>
                      <ul>
                        {eligibilityState.data.collisions.map((collision, index) => (
                          <li key={`${collision.source_identity}-${index}`}>
                            <strong>{collision.kind}</strong>｜<span>{collisionSeverityLabel(collision.severity)}</span>
                            <p>{collision.detail}</p>
                            <small>{collision.owner}｜{collision.source_identity}</small>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                  {eligibilityState.data.dataNote && <p role="status">{eligibilityState.data.dataNote}</p>}
                  {eligibilityResult.needsCorrection && <p role="status">資料待補正：請至訂單管理補齊服務日期與每日時段，並至服務人員名冊確認資格主檔後重試。</p>}
                </div>
              )}
            </div>
          </section>

          {/* Top Control Bar: Month Switcher + Search + Filters */}
          <section className="gantt-matrix-header-bar" aria-label="月曆查詢控制">
            {/* Left: Month Navigator & Today */}
            <div className="gantt-month-navigator">
              <div className="month-pill-group">
                <button
                  type="button"
                  data-control-id="scheduling.calendar.previous-month"
                  className="month-nav-arrow"
                  aria-label="查看上個月"
                  onClick={() => setMonth((value) => moveMonth(value, -1))}
                >
                  ◀ {prevMonthName}
                </button>
                <span className="current-month-display">
                  {month.year} 年 {month.month}月
                </span>
                <button
                  type="button"
                  data-control-id="scheduling.calendar.next-month"
                  className="month-nav-arrow"
                  aria-label="查看下個月"
                  onClick={() => setMonth((value) => moveMonth(value, 1))}
                >
                  {nextMonthName} ▶
                </button>
              </div>

              <button
                type="button"
                className="gantt-today-btn"
                data-control-id="scheduling.calendar.today"
                onClick={() => setMonth(currentMonth())}
              >
                🗓 今天 ({Number(taipeiMonth)}/{Number(taipeiDay)})
              </button>
            </div>

            {/* Right: Search + Filter Chips */}
            <div className="gantt-filter-controls">
              <div className="gantt-search-box">
                <span>🔍</span>
                <input
                  type="text"
                  placeholder="按月嫂姓名或編號..."
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                />
                {searchKeyword && (
                  <button type="button" onClick={() => setSearchKeyword('')}>✕</button>
                )}
              </div>

              <div className="gantt-status-pills">
                <button
                  type="button"
                  className={`gantt-pill ${statusFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('all')}
                >
                  全部月嫂 ({staffList.length})
                </button>
                <button
                  type="button"
                  className={`gantt-pill ${statusFilter === 'active' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('active')}
                >
                  🟢 正常履約中
                </button>
                <button
                  type="button"
                  className={`gantt-pill ${statusFilter === 'waiting' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('waiting')}
                >
                  🟡 待派單/Buffer
                </button>
                <button
                  type="button"
                  className={`gantt-pill ${statusFilter === 'leave' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('leave')}
                >
                  🟣 請假/留停
                </button>
              </div>

            </div>
          </section>

          {/* Full Legend Bar */}
          <section className="gantt-legend-bar-rich" aria-label="Server occupancy 圖例">
            <div className="legend-item">
              <span className="legend-badge active" />
              <span>正式服務日</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge buffer" />
              <span>7天防撞期 Buffer 鎖定</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge deposit" />
              <span>待定金核銷鎖定</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge leave" />
              <span>突發請假待代班</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge unavailable" />
              <span>接單資格／撞期判定</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge today" />
              <span>今日 ({Number(taipeiToday.slice(5, 7))}/{Number(taipeiToday.slice(8, 10))})</span>
            </div>
          </section>

          {/* Status Notifications */}
          {directoryLoading && (
            <div className="scheduling-status" role="status">正在載入服務人員摘要…</div>
          )}
          {directoryError && (
            <div className="scheduling-status error" role="alert">
              {directoryError}
              <button onClick={() => void loadDirectory()}>重試摘要查詢</button>
            </div>
          )}
          {directoryNextPageError && (
            <div className="scheduling-status error" role="alert">
              下一頁服務人員摘要載入失敗：{directoryNextPageError}
            </div>
          )}
          {!directoryLoading && directoryNextCursor !== null && (
            <button
              type="button"
              data-control-id="scheduling.staff.next-page"
              className="scheduling-load-more"
              disabled={directoryLoadingMore}
              onClick={() => void loadNextDirectoryPage()}
            >
              {directoryLoadingMore ? '正在載入更多服務人員…' : '載入更多服務人員'}
            </button>
          )}
          {calendarLoading && (
            <div className="scheduling-status" role="status">正在載入 current calendar…</div>
          )}
          {selectedStaffId && selectedStaffRow?.kind === 'empty' && !calendarLoading && !calendarError && (
            <div className="scheduling-status">目前範圍沒有 server projection。</div>
          )}
          {selectedStaffId && selectedStaffRow?.kind === 'terms_incomplete' && !calendarLoading && !calendarError && (
            <div className="scheduling-status error" role="alert" style={{ background: '#fffbeb', borderColor: '#f59e0b', color: '#b45309' }}>
              ⚠️ 該服務人員所屬訂單之每日服務時段條款不完整（service_time_terms_incomplete），已標記為待補正異常，請至訂單或異常審核中心補齊資料。
            </div>
          )}
          {calendarError && (
            <div className="scheduling-status error" role="alert">
              {renderError(calendarError)}
              <button
                data-control-id="scheduling.calendar.retry"
                onClick={retryFailedCalendarRows}
              >
                重試月曆查詢
              </button>
            </div>
          )}
          {!directoryLoading && filteredStaff.length === 0 && (
            <div className="scheduling-status">
              {staffList.length === 0 ? '目前沒有可顯示的服務人員摘要。' : '目前範圍沒有 server projection。'}
            </div>
          )}

          {/* Multi-Caregiver Gantt Chart Matrix Table */}
          {filteredStaff.length > 0 && (
            <div className="gantt-matrix-scroll-wrapper" data-surface-id="scheduling.calendar.grid">
              <div className="gantt-matrix-table">
                {/* Header Row: Days 1 ~ 31 */}
                <div className="gantt-matrix-header-row">
                  <div className="gantt-staff-header-cell">
                    <strong>月嫂名冊 ｜ Server occupancy</strong>
                  </div>
                  <div className="gantt-days-header-cells">
                    {daysList.map((d) => (
                      <div
                        key={d.dateStr}
                        className={`gantt-day-header-col ${d.isWeekend ? 'weekend' : ''} ${d.isToday ? 'today' : ''}`}
                        data-date={d.dateStr}
                      >
                        <span className="day-number">{d.dayNumber}</span>
                        <span className="weekday-text">{d.weekday}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Staff Rows */}
                {filteredStaff.map((staff) => {
                  const row = calendarRows[staff.id];
                  const diagnostic = getStaffDiagnosticBadge(row ?? undefined);
                  const staffCode = `STF-${String(staff.id).padStart(3, '0')}`;
                  const spans = buildGanttSpans(row ?? undefined, daysList.length);

                  return (
                    <div
                      key={staff.id}
                      className={`gantt-staff-matrix-row ${selectedStaffId === staff.id ? 'highlighted' : ''}`}
                      data-surface-id="scheduling.calendar.row"
                      onClick={() => setSelectedStaffId(staff.id)}
                    >
                      {/* Left: Staff Identity Card */}
                      <div className="gantt-staff-info-cell">
                        <div className="staff-name-line">
                          <span className="staff-avatar">👤</span>
                          <strong>{staff.displayName}</strong>
                          <span className="staff-code-badge">{staffCode}</span>
                        </div>
                        <div className={`staff-diagnostic-tag tag-${diagnostic.tone}`}>
                          {diagnostic.text}
                        </div>
                      </div>

                      {/* Right: Gantt Days Timeline Bar */}
                      <div className="gantt-days-timeline-cell">
                        {/* Render Days Grid */}
                        <div className="gantt-timeline-grid-bg">
                          {daysList.map((d) => (
                            <div
                              key={d.dateStr}
                              className={`gantt-grid-col ${d.isWeekend ? 'weekend-col' : ''} ${d.isToday ? 'today-col' : ''}`}
                            />
                          ))}
                        </div>

                        {/* Continuous Visual Gantt Blocks */}
                        <div className="gantt-spans-layer">
                          {spans.map((sp) => {
                            const leftPercent = ((sp.startDay - 1) / daysList.length) * 100;
                            const widthPercent =
                              (Math.max(1, sp.endDay - sp.startDay + 1) / daysList.length) * 100;
                            return (
                              <div
                                key={sp.id}
                                className={`gantt-span-bar span-${sp.tone}`}
                                style={{
                                  left: `${leftPercent}%`,
                                  width: `${widthPercent}%`,
                                }}
                                title={`${sp.caseText}${sp.statusLabel ? ` (${sp.statusLabel})` : ''}`}
                              >
                                {sp.icon && <span className="span-icon">{sp.icon} </span>}
                                <span className="span-case-name">{sp.caseText}</span>
                                {sp.statusLabel && (
                                  <small className="span-status-sub"> ({sp.statusLabel})</small>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Other Tabs */}
      {activeTab === 'leave_sub' && (
        <LeaveSubstitutionWorkspace suggestedCaseNo={eligibilityCaseNo.trim() || null} staffList={staffList} />
      )}
      {activeTab === 'holidays' && (
        <HolidayPolicyWorkspace />
      )}
      {activeTab === 'leave_inbox' && (
        <StaffLeaveInboxWorkspace />
      )}
    </div>
  );
};

export default SchedulingPage;
