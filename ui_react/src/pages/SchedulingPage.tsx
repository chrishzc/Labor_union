/**
 * File: SchedulingPage.tsx
 * Description: 顯示排班甘特、請假代班與國定假日 Query、Preview、Apply、receipt 工作台。
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
import {
  adaptSchedulingProjection,
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

type SchedulingTab = 'calendar' | 'leave_sub' | 'holidays' | 'leave_inbox';
type StatusFilter = 'all' | 'active' | 'waiting' | 'leave';

interface MonthSelection {
  year: number;
  month: number;
}

const STAFF_PAGE_SIZE = 50;

function currentMonth(): MonthSelection {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

function isoDate(year: number, month: number, day: number): string {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function todayIsoDate(): string {
  const now = new Date();
  return isoDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

function monthRange(selection: MonthSelection) {
  const finalDay = new Date(Date.UTC(selection.year, selection.month, 0)).getUTCDate();
  return {
    rangeStart: isoDate(selection.year, selection.month, 1),
    rangeEnd: isoDate(selection.year, selection.month, finalDay),
    totalDays: finalDay,
  };
}

function moveMonth(selection: MonthSelection, offset: number): MonthSelection {
  const target = new Date(Date.UTC(selection.year, selection.month - 1 + offset, 1));
  return { year: target.getUTCFullYear(), month: target.getUTCMonth() + 1 };
}

function renderError(error: SchedulingCurrentError | Error): string {
  if (error instanceof SchedulingCurrentError) {
    const code = error.publicCode ?? error.code;
    const correlation = error.correlationId ? `｜Correlation: ${error.correlationId}` : '';
    return `[${code}] ${error.message}${correlation}`;
  }
  return error.message;
}

function UnavailableTab({ title, controls }: { title: string; controls: string[] }) {
  return (
    <section className="scheduling-unavailable-workspace" aria-live="polite">
      <h2>{title}</h2>
      <p>後端 typed contract 尚未在本次唯讀 page-slice 開放。</p>
      <div className="scheduling-unavailable-actions">
        {controls.map((control) => (
          <button key={control} data-control-id={control} disabled>
            未開放
          </button>
        ))}
      </div>
    </section>
  );
}

function HolidayPolicyWorkspace() {
  const year = new Date().getFullYear();
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
    if (!request || !calendar || busy) return;
    setHolidayDraft(request);
    void previewHolidayFlow(request).catch(() => undefined);
  };

  const apply = () => {
    const previewResult = draft?.preview;
    const previewRequest = draft?.previewRequest;
    if (!previewResult || !previewRequest || !reason.trim() || busy) return;
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
        <button type="button" data-control-id="scheduling.holiday.preview" disabled={!calendar || !buildPreviewRequest() || busy} onClick={preview}>
          {machine.type === 'preview_loading' ? '預覽中…' : '預覽國定假日變更'}
        </button>
        <button type="button" data-control-id="scheduling.holiday.apply" disabled={!draft?.preview || !reason.trim() || busy} onClick={apply}>
          {machine.type === 'apply_pending' || machine.type === 'requery_loading' ? '套用並觀察中…' : '套用國定假日變更'}
        </button>
      </div>

      <div className="holiday-policy-locked-controls" aria-label="未核准國定假日控制">
        {['create', 'toggle-rest', 'toggle-pay', 'delete'].map((control) => (
          <button key={control} type="button" data-control-id={`scheduling.holiday.${control}`} disabled>
            未開放
          </button>
        ))}
      </div>

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
  const busy = ['query_loading', 'preview_loading', 'apply_pending', 'receipt_received', 'requery_loading']
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
        <p className="leave-substitution-notice">此訂單沒有可處理的正式指派；若屬測試資料不完整，請補齊後再測試。</p>
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
              {schedules.length === 0 && <option value="">後端未提供正式服務日</option>}
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
        <p className="leave-substitution-notice error">後端未提供此指派的正式服務日，不能建立 Preview；請補齊測試資料後再測試。</p>
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
        <button type="button" data-control-id="scheduling.leave.extension" disabled>
          其他延長調度未開放
        </button>
        {!draft?.preview && (
          <button type="button" data-control-id="scheduling.leave.apply" disabled>
            確認套用
          </button>
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

type SchedulingDiagnosticTone = 'unavailable' | 'active' | 'waiting' | 'leave';

type EligibilityCollisionState =
  | { kind: 'idle' }
  | { kind: 'loading'; caseNo: string }
  | { kind: 'ready'; data: SchedulingEligibilityCollisionViewModel }
  | { kind: 'unavailable'; message: string };

interface SchedulingDiagnosticBadge {
  tone: SchedulingDiagnosticTone;
  text: string;
}

const UNAVAILABLE_DIAGNOSTIC: SchedulingDiagnosticBadge = {
  tone: 'unavailable',
  text: '⚪ 後端未提供接單資格／撞期判定',
};

const UNAVAILABLE_SLOT_TEXT = '後端未提供接單資格／撞期判定';
const UNAVAILABLE_SLOT_DETAIL = '此 page-slice 僅顯示 server occupancy，無法判定接單或撞期。';

// 只將 server occupancy／typed error 映射為標籤，不從空資料推導接單資格或撞期。
function getStaffDiagnosticBadge(state: CalendarRowState | undefined): SchedulingDiagnosticBadge {
  if (!state || state.kind === 'empty') {
    return UNAVAILABLE_DIAGNOSTIC;
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

  if (hasLeave) {
    return { tone: 'leave', text: '🟣 服務中請假留停 (待代班)' };
  }
  if (hasWaiting) {
    return { tone: 'waiting', text: '🔵 待定金核銷鎖定中' };
  }
  if (hasBuffer) {
    return { tone: 'waiting', text: '🟡 7天防撞期 Buffer 鎖定' };
  }
  if (hasActive) {
    return { tone: 'active', text: '🟢 正常履約中' };
  }
  return UNAVAILABLE_DIAGNOSTIC;
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
        caseText: UNAVAILABLE_SLOT_TEXT,
        statusLabel: UNAVAILABLE_SLOT_DETAIL,
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
        statusLabel: `${state.message}；${UNAVAILABLE_SLOT_DETAIL}`,
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
        caseText: UNAVAILABLE_SLOT_TEXT,
        statusLabel: UNAVAILABLE_SLOT_DETAIL,
      },
    ];
  }

  const spans: GanttSpan[] = [];
  let current: GanttSpan | null = null;

  row.days.forEach((day, index) => {
    const dayNum = index + 1;
    const isRest = day.tone === 'rest';
    const isOccupied = day.occupancyKinds.length > 0;
    const tone: GanttSpan['tone'] = day.tone === 'rest' ? 'active' : day.tone;
    const hasCase = day.caseLabels.length > 0;
    const caseText = hasCase
      ? day.caseLabels.join('、')
      : (isOccupied ? day.statusLabel : UNAVAILABLE_SLOT_TEXT);
    const statusLabel = hasCase ? (isRest ? '排休' : '服務中') : undefined;
    const icon =
      tone === 'active' ? '🟢' : tone === 'buffer' ? '🔒' : tone === 'leave' ? '🚑' : tone === 'waiting' ? '🔵' : undefined;

    if (!current) {
      if (isOccupied) {
        current = { id: `span-${dayNum}`, startDay: dayNum, endDay: dayNum, tone, icon, caseText, statusLabel };
      }
    } else if (current.tone === tone && current.caseText === caseText) {
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
  const [staffList, setStaffList] = useState<StaffDirectoryCardViewModel[]>([]);
  const [directoryLoading, setDirectoryLoading] = useState<boolean>(true);
  const [directoryError, setDirectoryError] = useState<string | null>(null);

  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [month, setMonth] = useState<MonthSelection>(currentMonth);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchKeyword, setSearchKeyword] = useState<string>('');

  const [calendarRows, setCalendarRows] = useState<Record<number, CalendarRowState>>({});
  const [calendarLoading, setCalendarLoading] = useState<boolean>(false);
  const [calendarError, setCalendarError] = useState<Error | null>(null);
  const [retryGeneration, setRetryGeneration] = useState<number>(0);
  const [eligibilityState, setEligibilityState] = useState<EligibilityCollisionState>({ kind: 'idle' });

  const mountedRef = useRef(true);
  const directoryControllerRef = useRef<AbortController | null>(null);
  const calendarControllerRef = useRef<AbortController | null>(null);
  const eligibilityControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      directoryControllerRef.current?.abort();
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

    try {
      const page = adaptStaffDirectoryPage(
        await staffDirectoryClient.queryPage(
          { pageSize: STAFF_PAGE_SIZE },
          { signal: controller.signal }
        )
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      setStaffList(page.items);
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

  // 切換月份時重置排班快取
  useEffect(() => {
    setCalendarRows({});
  }, [month]);

  // 根據 selectedStaffId 載入日曆排班資料
  useEffect(() => {
    if (!selectedStaffId || staffList.length === 0) return;

    const currentStaff = staffList.find((s) => s.id === selectedStaffId);
    if (!currentStaff) return;

    calendarControllerRef.current?.abort();
    const controller = new AbortController();
    calendarControllerRef.current = controller;
    setCalendarLoading(true);
    setCalendarError(null);

    schedulingCurrentClient
      .queryCurrentCalendar(
        {
          staffId: selectedStaffId,
          rangeStart: range.rangeStart,
          rangeEnd: range.rangeEnd,
        },
        { signal: controller.signal }
      )
      .then((projection) => {
        if (!mountedRef.current || controller.signal.aborted) return;
        if (projection.days.length === 0) {
          setCalendarRows((prev) => ({ ...prev, [selectedStaffId]: { kind: 'empty' } }));
        } else {
          const row = adaptSchedulingProjection(currentStaff, projection);
          setCalendarRows((prev) => ({ ...prev, [selectedStaffId]: { kind: 'loaded', row } }));
        }
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || controller.signal.aborted) return;
        const isTermsIncomplete =
          err instanceof SchedulingCurrentError &&
          err.publicCode === 'service_time_terms_incomplete';

        if (isTermsIncomplete) {
          setCalendarRows((prev) => ({ ...prev, [selectedStaffId]: { kind: 'terms_incomplete' } }));
        } else {
          setCalendarError(err instanceof Error ? err : new Error('排班日曆查詢失敗'));
          setCalendarRows((prev) => ({
            ...prev,
            [selectedStaffId]: { kind: 'error', message: err instanceof Error ? err.message : '查詢失敗' },
          }));
        }
      })
      .finally(() => {
        if (mountedRef.current && !controller.signal.aborted) {
          setCalendarLoading(false);
        }
      });
  }, [selectedStaffId, range, retryGeneration, staffList]);

  const selectedCaseNo = useMemo(() => {
    if (selectedStaffId === null) return null;
    const row = calendarRows[selectedStaffId];
    if (row?.kind !== 'loaded') return null;
    return row.row.days.flatMap((day) => day.caseLabels).find((caseNo) => caseNo.length > 0) ?? null;
  }, [calendarRows, selectedStaffId]);

  useEffect(() => {
    eligibilityControllerRef.current?.abort();
    setEligibilityState({ kind: 'idle' });
    if (selectedStaffId === null || selectedCaseNo === null) return;

    const controller = new AbortController();
    eligibilityControllerRef.current = controller;
    setEligibilityState({ kind: 'loading', caseNo: selectedCaseNo });
    void schedulingEligibilityCollisionClient.query(
      { caseNo: selectedCaseNo, staffId: selectedStaffId, asOf: todayIsoDate() },
      { signal: controller.signal }
    ).then((projection) => {
      if (controller.signal.aborted || !mountedRef.current) return;
      setEligibilityState({ kind: 'ready', data: adaptSchedulingEligibilityCollision(projection) });
    }).catch((error: unknown) => {
      if (controller.signal.aborted || !mountedRef.current) return;
      const message = error instanceof SchedulingEligibilityCollisionError
        ? error.message
        : '資格與檔期衝突查詢失敗。';
      setEligibilityState({ kind: 'unavailable', message: `${message}；測試資料不足時請補齊後再測試。` });
    });

    return () => controller.abort();
  }, [selectedCaseNo, selectedStaffId]);

  // 篩選與搜尋過濾
  const filteredStaff = useMemo(() => {
    return staffList.filter((staff) => {
      const matchKeyword =
        !searchKeyword ||
        staff.displayName.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        `stf-${String(staff.id).padStart(3, '0')}`.includes(searchKeyword.toLowerCase());

      if (!matchKeyword) return false;

      const diagnostic = getStaffDiagnosticBadge(calendarRows[staff.id]);
      if (statusFilter === 'active' && !diagnostic.text.includes('履約') && !diagnostic.text.includes('服務')) return false;
      if (statusFilter === 'waiting' && !diagnostic.text.includes('待定金') && !diagnostic.text.includes('Buffer') && !diagnostic.text.includes('時段未確認')) return false;
      if (statusFilter === 'leave' && !diagnostic.text.includes('假')) return false;

      return true;
    });
  }, [staffList, searchKeyword, statusFilter, calendarRows]);

  // 產生當月天數與星期清單（精確計算系統今日）
  const daysList = useMemo(() => {
    const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
    const today = new Date();
    const currentYear = today.getFullYear();
    const currentMonthNum = today.getMonth() + 1;
    const currentDayNum = today.getDate();

    const list = [];
    for (let day = 1; day <= range.totalDays; day++) {
      const dateStr = isoDate(month.year, month.month, day);
      const dateObj = new Date(Date.UTC(month.year, month.month - 1, day));
      const weekdayIdx = dateObj.getUTCDay();
      const isWeekend = weekdayIdx === 0 || weekdayIdx === 6;
      const isToday =
        month.year === currentYear &&
        month.month === currentMonthNum &&
        day === currentDayNum;

      list.push({
        dayNumber: day,
        dateStr,
        weekday: weekdays[weekdayIdx],
        isWeekend,
        isToday,
      });
    }
    return list;
  }, [month, range.totalDays]);

  const prevMonthName = `${month.month === 1 ? 12 : month.month - 1}月`;
  const nextMonthName = `${month.month === 12 ? 1 : month.month + 1}月`;
  const selectedStaffRow = selectedStaffId ? calendarRows[selectedStaffId] : null;

  return (
    <div data-surface-id="scheduling.page" className="scheduling-gantt-page">
      {/* Page Header */}
      <header className="page-header-banner scheduling-page-header">
        <div>
          <h1 className="page-title">📅 多月嫂排班日曆與調度中心</h1>
          <p className="page-subtitle">
            全景甘特檔期矩陣與 server occupancy 顯示；接單資格／撞期判定尚未開放。
          </p>
        </div>
        <button
          type="button"
          className="scheduling-precision-control"
          data-control-id="scheduling.precision.open"
          disabled
        >
          ⚙️ 訂單出勤精算工作台（未開放）
        </button>
      </header>

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
              <p>typed matching projection 已接線；選擇具 case_no 的 occupancy 後查詢。</p>
            </div>
            <select
              aria-label="洽談中訂單檔期投影"
              data-control-id="scheduling.projection.order-select"
              disabled
            >
              <option>待測試資料提供 case_no</option>
            </select>
            <button data-control-id="scheduling.projection.lock" disabled>
              預約鎖定（未開放）
            </button>
            <div data-surface-id="scheduling.eligibility-collision" aria-live="polite">
              {eligibilityState.kind === 'idle' && selectedStaffId !== null && selectedCaseNo === null && !calendarLoading && (
                <p>測試資料不完整：目前 occupancy 未提供可查詢的 case_no，未推定資格或撞期。</p>
              )}
              {eligibilityState.kind === 'loading' && (
                <p role="status">正在查詢 {eligibilityState.caseNo} 的資格與檔期衝突…</p>
              )}
              {eligibilityState.kind === 'unavailable' && (
                <p role="alert">資格／檔期查詢不可用：{eligibilityState.message}</p>
              )}
              {eligibilityState.kind === 'ready' && (
                <div>
                  <p><strong>{eligibilityState.data.caseNo}</strong>：{eligibilityState.data.eligibilityLabel}；{eligibilityState.data.availabilityLabel}。</p>
                  <p>衝突筆數：{eligibilityState.data.collisionCount}；覆蓋狀態：{eligibilityState.data.coverage.status}。</p>
                  {eligibilityState.data.dataNote && <p role="status">{eligibilityState.data.dataNote}</p>}
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
                🗓 今天 ({new Date().getMonth() + 1}/{new Date().getDate()})
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

              {/* Preserved staff selector label for test compatibility */}
              <label className="scheduling-staff-select-hidden">
                服務人員
                <select
                  data-control-id="scheduling.calendar.staff-select"
                  aria-label="服務人員"
                  value={selectedStaffId ?? ''}
                  onChange={(e) => setSelectedStaffId(Number(e.target.value))}
                >
                  {staffList.map((staff) => (
                    <option key={staff.id} value={staff.id}>{staff.displayName}</option>
                  ))}
                </select>
              </label>
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
              <span>接單資格／撞期判定未提供</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge today" />
              <span>今日 ({new Date().getMonth() + 1}/{new Date().getDate()})</span>
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
                onClick={() => setRetryGeneration((v) => v + 1)}
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
        <LeaveSubstitutionWorkspace suggestedCaseNo={selectedCaseNo} staffList={staffList} />
      )}
      {activeTab === 'holidays' && (
        <HolidayPolicyWorkspace />
      )}
      {activeTab === 'leave_inbox' && (
        <UnavailableTab
          title="請假待辦收件匣"
          controls={['scheduling.leave-inbox.accept', 'scheduling.leave-inbox.reject']}
        />
      )}
    </div>
  );
};

export default SchedulingPage;
