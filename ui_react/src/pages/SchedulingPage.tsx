/**
 * File: SchedulingPage.tsx
 * Description: 顯示排班甘特與調度工作台，並安全解析請假代班 bounded deep-link。
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
  type HolidayRow,
} from '../adapters/scheduling/holiday_flow_adapter';
import {
  staffLeaveInboxClient,
  type LeaveInboxItem,
  type LeaveInboxStatus,
} from '../api/scheduling/staff_leave_inbox_client';
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { Drawer } from '../components/Drawer';

type SchedulingTab = 'calendar' | 'leave_sub' | 'holidays';
type StatusFilter = 'all' | 'active' | 'waiting' | 'leave';

interface SchedulingDeepLink {
  tab: SchedulingTab;
  caseNo: string;
}

interface MonthSelection {
  year: number;
  month: number;
}

const STAFF_PAGE_SIZE = 20;

function decodeHashComponent(value: string): string {
  return decodeURIComponent(value.replace(/\+/g, ' '));
}

function containsControlCharacter(value: string): boolean {
  return [...value].some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint <= 0x1f || (codePoint >= 0x7f && codePoint <= 0x9f);
  });
}

function canonicalCaseNoFromQuery(queryText: string): string {
  let decodedCaseNo: string | null = null;
  for (const pair of queryText.split('&')) {
    const separator = pair.indexOf('=');
    const encodedKey = separator === -1 ? pair : pair.slice(0, separator);
    let key: string;
    try {
      key = decodeHashComponent(encodedKey);
    } catch {
      continue;
    }
    if (key !== 'case_no') continue;
    if (decodedCaseNo !== null) return '';
    const encodedValue = separator === -1 ? '' : pair.slice(separator + 1);
    try {
      decodedCaseNo = decodeHashComponent(encodedValue);
    } catch {
      return '';
    }
  }

  const canonical = decodedCaseNo?.trim() ?? '';
  const characterCount = [...canonical].length;
  if (characterCount < 1 || characterCount > 50 || containsControlCharacter(canonical)) return '';
  return canonical;
}

function parseSchedulingDeepLink(hash: string): SchedulingDeepLink {
  const normalizedHash = hash.replace(/^#\/?/, '');
  const queryStart = normalizedHash.indexOf('?');
  const path = queryStart === -1 ? normalizedHash : normalizedHash.slice(0, queryStart);
  if (path !== 'scheduling' || queryStart === -1) {
    return { tab: 'calendar', caseNo: '' };
  }

  try {
    const queryText = normalizedHash.slice(queryStart + 1);
    const query = new URLSearchParams(queryText);
    const tab = query.get('tab');
    if (tab !== 'leave_sub') {
      return { tab: 'calendar', caseNo: '' };
    }
    return { tab, caseNo: canonicalCaseNoFromQuery(queryText) };
  } catch {
    return { tab: 'calendar', caseNo: '' };
  }
}

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
  const [holidayDrawerOpen, setHolidayDrawerOpen] = useState(false);
  const [, setStoreRevision] = useState(0);

  useEffect(() => {
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

  const handleOpenEditDrawer = (holiday: HolidayRow) => {
    setAction('upsert');
    setHolidayDate(holiday.holiday_date);
    setHolidayName(holiday.holiday_name);
    setDoublePay(holiday.is_double_pay_default);
    setReason(`調整 ${holiday.holiday_date} ${holiday.holiday_name} 國定假日政策`);
    const request: HolidayPreviewRequest = {
      action: 'upsert',
      holiday_date: holiday.holiday_date,
      holiday_name: holiday.holiday_name,
      is_double_pay_default: holiday.is_double_pay_default,
      from_date: fromDate,
      to_date: toDate,
    };
    setHolidayDraft(request);
    void previewHolidayFlow(request).catch(() => undefined);
    setHolidayDrawerOpen(true);
  };

  const handleOpenAddDrawer = () => {
    setAction('upsert');
    setHolidayDate(todayIsoDate());
    setHolidayName('');
    setDoublePay(false);
    setReason('新增國定假日政策');
    setHolidayDrawerOpen(true);
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
          <h2>🗓️ 國定假日與預設政策管理</h2>
          <p>日曆版本、雙薪預設與變更結果全部採用後端根事實，點擊「編輯」開啟抽屜進行政策修改或刪除。</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            type="button"
            className="btn-primary-action"
            onClick={handleOpenAddDrawer}
            disabled={busy}
            style={{ padding: '9px 16px', fontSize: '0.88rem', borderRadius: '8px', background: '#ea580c', color: '#fff', border: 'none', fontWeight: 700, cursor: 'pointer' }}
          >
            ➕ 新增國定假日
          </button>
          <span className={`holiday-policy-state state-${machine.type}`}>{machine.type}</span>
        </div>
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
          {machine.type === 'query_loading' ? '⏳ 查詢中…' : '查詢國定假日政策'}
        </button>
      </div>

      {calendar && (
        <section className="holiday-policy-calendar" aria-label="國定假日日曆根事實">
          <div className="holiday-policy-meta">
            <span>來源：<strong>{calendar.source_identity}</strong></span>
            <span>日曆版本：<code>{calendar.calendar_version.slice(0, 12)}…</code></span>
            <span>區間：{calendar.planning_horizon.from_date} ～ {calendar.planning_horizon.to_date}</span>
          </div>
          {calendar.holidays.length === 0 ? (
            <p className="holiday-policy-notice">此查詢區間沒有國定假日根事實。</p>
          ) : (
            <ul className="holiday-policy-list" style={{ display: 'grid', gap: '10px' }}>
              {calendar.holidays.map((holiday) => (
                <li
                  key={holiday.holiday_date}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    gap: '12px',
                    padding: '12px 18px',
                    borderRadius: '10px',
                    background: '#ffffff',
                    border: '1.5px solid #fed7aa',
                    boxShadow: '0 1px 4px rgba(74, 69, 67, 0.04)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                    <time style={{ fontWeight: 800, fontSize: '0.92rem', color: '#9a3412', background: '#fff7ed', padding: '4px 10px', borderRadius: '6px', border: '1px solid #ffedd5' }}>
                      📅 {holiday.holiday_date}
                    </time>
                    <strong style={{ fontSize: '1rem', color: '#1e1b19' }}>
                      {holiday.holiday_name}
                    </strong>
                    <span
                      className={`criteria-match-pill ${holiday.is_double_pay_default ? 'match' : 'partial'}`}
                      style={{ fontSize: '0.8rem', padding: '3px 8px' }}
                    >
                      {holiday.is_double_pay_default ? '💰 預設雙薪 (200%)' : '💵 一般薪資 (100%)'}
                    </span>
                  </div>

                  <div>
                    <button
                      type="button"
                      onClick={() => handleOpenEditDrawer(holiday)}
                      disabled={busy}
                      style={{
                        padding: '7px 16px',
                        fontSize: '0.86rem',
                        background: '#ffedd5',
                        color: '#9a3412',
                        border: '1px solid #fdba74',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        fontWeight: 750,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                      }}
                    >
                      ✏️ 編輯
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {/* 國定假日政策編輯／新增抽屜 (Slide-over Drawer) */}
      <Drawer
        isOpen={holidayDrawerOpen}
        onClose={() => setHolidayDrawerOpen(false)}
        title={action === 'delete' ? `🗑️ 刪除國定假日：${holidayName || holidayDate}` : holidayName ? `🗓️ 編輯國定假日政策：${holidayName}` : '➕ 新增國定假日政策'}
        size="wide"
      >
        <div style={{ display: 'grid', gap: '18px', padding: '4px' }}>
          {/* 表單設定卡片 */}
          <div style={{ background: '#fffaf8', padding: '18px 20px', borderRadius: '12px', border: '1.5px solid #fed7aa', display: 'grid', gap: '14px' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', color: '#9a3412', fontWeight: 700 }}>
              ⚙️ 國定假日與薪資政策設定
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
              <label style={{ display: 'grid', gap: '6px', fontSize: '0.84rem', fontWeight: 700, color: '#57423b' }}>
                變更類型
                <select
                  aria-label="國定假日變更類型"
                  value={action}
                  disabled={busy}
                  onChange={(event) => {
                    const next = event.target.value as HolidayAction;
                    setAction(next);
                  }}
                  style={{ padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem' }}
                >
                  <option value="upsert">新增或更新 (Upsert)</option>
                  <option value="delete">刪除國定假日 (Delete)</option>
                </select>
              </label>

              <label style={{ display: 'grid', gap: '6px', fontSize: '0.84rem', fontWeight: 700, color: '#57423b' }}>
                國定假日日期
                <input
                  aria-label="國定假日日期"
                  type="date"
                  value={holidayDate}
                  disabled={busy}
                  onChange={(event) => setHolidayDate(event.target.value)}
                  style={{ padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem' }}
                />
              </label>

              <label style={{ display: 'grid', gap: '6px', fontSize: '0.84rem', fontWeight: 700, color: '#57423b' }}>
                國定假日名稱
                <input
                  aria-label="國定假日名稱"
                  value={holidayName}
                  disabled={busy || action === 'delete'}
                  maxLength={100}
                  placeholder="例如 端午節"
                  onChange={(event) => setHolidayName(event.target.value)}
                  style={{ padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem' }}
                />
              </label>
            </div>

            <label className="holiday-policy-check" style={{ marginTop: '4px', fontSize: '0.88rem', fontWeight: 700, color: '#9a3412', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="checkbox"
                checked={doublePay}
                disabled={busy || action === 'delete'}
                onChange={(event) => setDoublePay(event.target.checked)}
                style={{ width: '18px', height: '18px', accentColor: '#ea580c' }}
              />
              後端政策預設雙薪 (200% 薪資計算)
            </label>

            <label style={{ display: 'grid', gap: '6px', fontSize: '0.84rem', fontWeight: 700, color: '#57423b' }}>
              變更原因與審核註記
              <textarea
                aria-label="套用原因"
                value={reason}
                maxLength={500}
                disabled={busy}
                onChange={(event) => setReason(event.target.value)}
                style={{ padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.88rem', minHeight: '68px' }}
              />
            </label>
          </div>

          {/* 預覽與套用控制列 */}
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              data-control-id="scheduling.holiday.preview"
              disabled={!calendarMatchesHorizon || !buildPreviewRequest() || busy}
              onClick={preview}
              style={{ flex: 1, padding: '10px 16px', fontSize: '0.92rem', borderRadius: '8px', background: '#f5ece9', color: '#57423b', border: '1px solid #dec0b6', fontWeight: 700, cursor: 'pointer' }}
            >
              {machine.type === 'preview_loading' ? '⏳ 預覽中…' : '預覽國定假日變更'}
            </button>
            <button
              type="button"
              data-control-id="scheduling.holiday.apply"
              aria-describedby={previewNeedsRefresh || !calendarMatchesHorizon ? 'scheduling-holiday-apply-guidance' : undefined}
              disabled={!draft?.preview || !previewMatchesCurrentInputs || !calendarMatchesHorizon || !reason.trim() || busy}
              onClick={apply}
              style={{ flex: 1, padding: '10px 16px', fontSize: '0.92rem', borderRadius: '8px', background: action === 'delete' ? '#dc2626' : '#ea580c', color: '#fff', border: 'none', fontWeight: 700, cursor: 'pointer', boxShadow: '0 2px 8px rgba(234, 88, 12, 0.25)' }}
            >
              {machine.type === 'apply_pending' || machine.type === 'requery_loading' ? '⏳ 套用中…' : '套用國定假日變更'}
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

          {/* 預覽結果卡片 */}
          {draft?.preview && (
            <section className="holiday-policy-preview" aria-label="國定假日變更預覽" style={{ background: '#f0fdf4', border: '1.5px solid #86efac', borderRadius: '10px', padding: '14px 16px', color: '#166534' }}>
              <h3 style={{ margin: '0 0 8px 0', fontSize: '0.95rem', fontWeight: 700, color: '#15803d' }}>
                預覽已產生
              </h3>
              <p style={{ margin: '0 0 4px 0', fontSize: '0.86rem' }}>
                <strong>動作：</strong>{draft.preview.command.action} ｜ <strong>日期：</strong>{draft.preview.command.holiday_date} ｜ <strong>指紋：</strong>{draft.preview.preview_fingerprint.slice(0, 12)}…
              </p>
              <p style={{ margin: 0, fontSize: '0.86rem' }}>
                <strong>排班影響：</strong>{draft.preview.schedule_impact} ｜ <strong>薪資影響：</strong>{draft.preview.payroll_impact}
              </p>
            </section>
          )}

          {/* Receipt 結果提示 */}
          {draft?.receipt && (
            <section className="holiday-policy-receipt" aria-live="polite" style={{ background: '#ecfdf5', border: '1.5px solid #6ee7b7', borderRadius: '10px', padding: '14px 16px', color: '#065f46' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#047857' }}>
                  已收到正式 receipt
                </h3>
                <button
                  type="button"
                  onClick={() => setHolidayDrawerOpen(false)}
                  style={{ padding: '4px 10px', fontSize: '0.8rem', background: '#059669', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
                >
                  關閉抽屜
                </button>
              </div>
              <p style={{ margin: '0 0 4px 0', fontSize: '0.84rem' }}>
                <strong>Receipt Key：</strong>{draft.receipt.receipt_key} ｜ <strong>日曆版本：</strong>{draft.receipt.resulting_calendar_version.slice(0, 12)}…
              </p>
              <p style={{ margin: 0, fontSize: '0.84rem' }}>
                {machine.type === 'observed' ? '已觀察最新後端日曆版本。' : 'Receipt 已保留，正在確認最新日曆狀態。'}
              </p>
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
        </div>
      </Drawer>
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
  const [caseNo, setCaseNo] = useState(() => suggestedCaseNo || IN_NEGOTIATION_CASE_PRESETS[0]?.caseNo || '115000003');
  const [isCustomInput, setIsCustomInput] = useState(false);
  const [assignmentId, setAssignmentId] = useState<number | null>(null);
  const [scheduleId, setScheduleId] = useState<number | null>(null);
  const [resolutionType, setResolutionType] = useState<LeaveResolutionType>('substitute');
  const [substituteStaffId, setSubstituteStaffId] = useState<number | null>(null);
  const [isDoublePay, setIsDoublePay] = useState(false);
  const [reason, setReason] = useState('正式處理請假代班');
  const [confirmed, setConfirmed] = useState(false);
  const [, setStoreRevision] = useState(0);

  // LINE 請假待辦收件匣狀態
  const [inboxStatus, setInboxStatus] = useState<LeaveInboxStatus>('pending');
  const [inboxItems, setInboxItems] = useState<readonly LeaveInboxItem[]>([]);
  const [selectedInboxItem, setSelectedInboxItem] = useState<LeaveInboxItem | null>(null);
  const [inboxBusy, setInboxBusy] = useState(false);
  const [inboxError, setInboxError] = useState<string | null>(null);
  const [inboxReceipt, setInboxReceipt] = useState<string | null>(null);
  const [inboxReasonById, setInboxReasonById] = useState<Record<number, string>>({});

  const loadInbox = useCallback(async () => {
    setInboxBusy(true);
    setInboxError(null);
    try {
      setInboxItems(await staffLeaveInboxClient.list(inboxStatus));
    } catch (caught) {
      setInboxError(caught instanceof Error ? caught.message : '請假待辦載入失敗。');
    } finally {
      setInboxBusy(false);
    }
  }, [inboxStatus]);

  useEffect(() => { void loadInbox(); }, [loadInbox]);

  const handleAcceptAndDispatch = async (item: LeaveInboxItem) => {
    setInboxBusy(true);
    setInboxError(null);
    setInboxReceipt(null);
    try {
      if (item.request_status === 'pending') {
        await staffLeaveInboxClient.review(item, 'accept', '調度員已受理，正在安排代班');
        setInboxReceipt(`已受理待辦 #${item.id}（${item.staff_name}）的 LINE 請假申請，並已通知月嫂！`);
        await loadInbox();
      }
      setSelectedInboxItem(item);
      setReason(`依 LINE 請假待辦 #${item.id} (${item.staff_name} ${item.leave_start_date}～${item.leave_end_date}) 安排代班`);
      // 若當前案件指派中有該月嫂，自動選中該 assignment
      const matchedAssignment = assignments.find((a) => a.staff_id === item.staff_id);
      if (matchedAssignment) {
        setAssignmentId(matchedAssignment.assignment_id);
        setScheduleId(matchedAssignment.official_schedules[0]?.schedule_id ?? null);
      }
    } catch (caught) {
      setInboxError(caught instanceof Error ? caught.message : '受理待辦失敗。');
    } finally {
      setInboxBusy(false);
    }
  };

  const handleRejectInbox = async (item: LeaveInboxItem) => {
    const rejectReason = inboxReasonById[item.id]?.trim();
    if (!rejectReason) {
      setInboxError('退回申請請先填寫審核原因。');
      return;
    }
    setInboxBusy(true);
    setInboxError(null);
    try {
      await staffLeaveInboxClient.review(item, 'reject', rejectReason);
      setInboxReceipt(`已退回 #${item.id} (${item.staff_name}) 的請假申請，已通知月嫂。`);
      if (selectedInboxItem?.id === item.id) {
        setSelectedInboxItem(null);
      }
      await loadInbox();
    } catch (caught) {
      setInboxError(caught instanceof Error ? caught.message : '退回申請失敗。');
    } finally {
      setInboxBusy(false);
    }
  };

  useEffect(
    () => leaveSubstitutionFlowStore.subscribe(() => setStoreRevision((value) => value + 1)),
    [],
  );

  useEffect(() => {
    if (suggestedCaseNo && suggestedCaseNo !== caseNo) {
      setCaseNo(suggestedCaseNo);
    }
  }, [suggestedCaseNo, caseNo]);

  const normalizedCaseNo = caseNo.trim();

  // 進入頁面或切換訂單時，自動向後端發送 query，避免畫面留白
  useEffect(() => {
    if (normalizedCaseNo) {
      const existingDraft = leaveSubstitutionFlowStore.get(normalizedCaseNo);
      if (!existingDraft || existingDraft.status === 'idle') {
        void queryLeaveSubstitutionFlow(normalizedCaseNo).catch(() => undefined);
      }
    }
  }, [normalizedCaseNo]);

  const draft = normalizedCaseNo ? leaveSubstitutionFlowStore.get(normalizedCaseNo) : undefined;
  const machine = resolveLeaveSubstitutionMachineState(draft);
  const assignments = draft?.assignments ?? [];
  const selectedAssignment = assignments.find((item) => item.assignment_id === assignmentId) ?? null;
  const schedules = selectedAssignment?.official_schedules ?? [];
  const selectedSchedule = schedules.find((item) => item.schedule_id === scheduleId) ?? null;
  const busy = ['query_loading', 'preview_loading', 'apply_pending', 'receipt_received', 'requery_loading', 'outcome_unknown', 'observation_failed']
    .includes(machine.type);

  const activePreset = IN_NEGOTIATION_CASE_PRESETS.find((p) => p.caseNo === normalizedCaseNo);

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
      leave_request_id: selectedInboxItem ? selectedInboxItem.id : null,
      expected_leave_request_version: selectedInboxItem ? selectedInboxItem.aggregate_version : null,
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
          <h2>🚑 服務中請假與緊急代班調度工作台</h2>
          <p>整合 LINE 待辦收件與電話／口頭請假調度；即時調度合格代班人員並經由 Server Projection 安全試算。</p>
        </div>
        <span className={`leave-substitution-state state-${machine.type}`}>{machine.type}</span>
      </header>

      {/* Section 1: LINE 月嫂請假待辦收件匣 */}
      <div style={{ background: '#ffffff', border: '1.5px solid #fed7aa', borderRadius: '12px', padding: '18px 20px', boxShadow: '0 2px 8px rgba(74, 69, 67, 0.04)', display: 'grid', gap: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.02rem', color: '#9a3412', display: 'flex', alignItems: 'center', gap: '8px' }}>
              📥 LINE 月嫂請假待辦收件匣
            </h3>
            <p style={{ margin: '4px 0 0', fontSize: '0.84rem', color: '#74593f' }}>
              月嫂由 LINE 官方帳號送出之請假申請，點擊「受理並調度」即可自動帶入下方排班進行代班指派。
            </p>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.84rem', fontWeight: 700, color: '#57423b' }}>
              狀態
              <select
                value={inboxStatus}
                onChange={(e) => setInboxStatus(e.target.value as LeaveInboxStatus)}
                disabled={inboxBusy}
                style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid #dec0b6', fontSize: '0.84rem' }}
              >
                <option value="pending">待審核 (Pending)</option>
                <option value="accepted_for_processing">已受理處理中</option>
                <option value="resolved">已完成代班</option>
                <option value="rejected">已退回</option>
                <option value="cancelled">已取消</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => void loadInbox()}
              disabled={inboxBusy}
              style={{ padding: '6px 12px', fontSize: '0.82rem', background: '#f5ece9', color: '#57423b', border: '1px solid #dec0b6', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
            >
              {inboxBusy ? '⏳ 載入中…' : '🔄 重新整理'}
            </button>
          </div>
        </div>

        {inboxReceipt && (
          <div className="leave-substitution-notice success" style={{ margin: 0 }}>
            {inboxReceipt}
          </div>
        )}

        {inboxError && (
          <div className="leave-substitution-notice error" style={{ margin: 0 }}>
            {inboxError}
          </div>
        )}

        {inboxItems.length === 0 && !inboxBusy && (
          <div style={{ padding: '16px', textAlign: 'center', background: '#fffcfb', borderRadius: '8px', border: '1px dashed #dec0b6', color: '#8b7169', fontSize: '0.86rem' }}>
            ✅ 目前此狀態沒有待處理的 LINE 請假申請。若為月嫂電話或線下口頭請假，直接於下方手動調度即可。
          </div>
        )}

        {inboxItems.length > 0 && (
          <div style={{ display: 'grid', gap: '10px' }}>
            {inboxItems.map((item) => (
              <div
                key={item.id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: '12px',
                  padding: '12px 16px',
                  background: selectedInboxItem?.id === item.id ? '#fff7ed' : '#fffaf8',
                  borderRadius: '10px',
                  border: selectedInboxItem?.id === item.id ? '2px solid #ea580c' : '1.5px solid #fed7aa',
                }}
              >
                <div style={{ display: 'grid', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <strong style={{ fontSize: '0.98rem', color: '#1e1b19' }}>
                      #{item.id} ｜ 👩‍🍼 {item.staff_name} (#{item.staff_id})
                    </strong>
                    <span className={`contract-status-pill ${item.request_status === 'pending' ? 'waiting' : item.request_status === 'accepted_for_processing' ? 'active' : 'signed'}`} style={{ fontSize: '0.78rem' }}>
                      {item.request_status === 'pending' ? '待審核' : item.request_status === 'accepted_for_processing' ? '處理中' : item.request_status}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.86rem', color: '#9a3412', fontWeight: 600 }}>
                    📅 請假期間：{item.leave_start_date} ～ {item.leave_end_date}
                  </div>
                  <div style={{ fontSize: '0.84rem', color: '#4b5563' }}>
                    💬 事由：{item.request_reason || '未填寫請假說明'}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                  {item.request_status === 'pending' && (
                    <>
                      <input
                        placeholder="退回原因說明…"
                        value={inboxReasonById[item.id] ?? ''}
                        onChange={(e) => setInboxReasonById((prev) => ({ ...prev, [item.id]: e.target.value }))}
                        style={{ padding: '6px 10px', fontSize: '0.82rem', borderRadius: '6px', border: '1px solid #dec0b6', width: '130px' }}
                      />
                      <button
                        type="button"
                        onClick={() => void handleRejectInbox(item)}
                        disabled={inboxBusy}
                        style={{ padding: '6px 10px', fontSize: '0.82rem', background: '#fee2e2', color: '#991b1b', border: '1px solid #fca5a5', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
                      >
                        退回
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleAcceptAndDispatch(item)}
                    disabled={inboxBusy}
                    style={{
                      padding: '7px 14px',
                      fontSize: '0.86rem',
                      background: selectedInboxItem?.id === item.id ? '#ea580c' : '#ffedd5',
                      color: selectedInboxItem?.id === item.id ? '#ffffff' : '#9a3412',
                      border: '1px solid #fdba74',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 750,
                    }}
                  >
                    {selectedInboxItem?.id === item.id ? '✓ 正在調度此案' : '📋 受理並調度代班'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 當前載入的 LINE 請假待辦提示橫幅 */}
      {selectedInboxItem && (
        <div style={{ padding: '12px 18px', background: '#ffedd5', border: '1.5px solid #fdba74', borderRadius: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
          <span style={{ fontSize: '0.9rem', color: '#9a3412', fontWeight: 700 }}>
            🚨 目前已連動 LINE 請假待辦 #{selectedInboxItem.id}（{selectedInboxItem.staff_name} ｜ {selectedInboxItem.leave_start_date}～{selectedInboxItem.leave_end_date}）
          </span>
          <button
            type="button"
            onClick={() => {
              setSelectedInboxItem(null);
              setReason('正式處理請假代班');
            }}
            style={{ padding: '5px 12px', fontSize: '0.82rem', background: '#ffffff', color: '#9a3412', border: '1px solid #fdba74', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
          >
            ✖ 取消關聯 (改為手動／電話調度)
          </button>
        </div>
      )}

      {/* 訂單選擇控制列（支援下拉選單與快速切換標籤） */}
      <div className="leave-substitution-query-row" style={{ background: '#fff8f6', padding: '16px 20px', borderRadius: '12px', border: '1.5px solid #fed7aa' }}>
        <div style={{ flex: '1 1 320px' }}>
          <label style={{ display: 'block', fontSize: '0.84rem', fontWeight: 700, color: '#9a3412', marginBottom: '6px' }}>
            📋 選擇服務中案件／訂單編號 (支援電話／口頭／LINE 請假調度)
          </label>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            {!isCustomInput ? (
              <select
                aria-label="選擇服務中訂單編號"
                value={caseNo}
                disabled={busy}
                onChange={(event) => {
                  const val = event.target.value;
                  if (val === '__custom__') {
                    setIsCustomInput(true);
                  } else {
                    setCaseNo(val);
                    void queryLeaveSubstitutionFlow(val).catch(() => undefined);
                  }
                }}
                style={{ flex: 1, minWidth: '260px', padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.92rem' }}
              >
                {IN_NEGOTIATION_CASE_PRESETS.map((preset) => (
                  <option key={preset.caseNo} value={preset.caseNo}>
                    #{preset.caseNo} ｜ {preset.clientName} ({preset.month}/{preset.startDay}~{preset.month}/{preset.endDay})
                  </option>
                ))}
                <option value="__custom__">✍️ 自訂輸入其他訂單編號…</option>
              </select>
            ) : (
              <div style={{ display: 'flex', gap: '6px', flex: 1 }}>
                <input
                  aria-label="請假代班訂單編號"
                  value={caseNo}
                  disabled={busy}
                  onChange={(event) => setCaseNo(event.target.value)}
                  placeholder="例如 115000003"
                  style={{ flex: 1, padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.92rem' }}
                />
                <button
                  type="button"
                  onClick={() => {
                    setIsCustomInput(false);
                    setCaseNo(IN_NEGOTIATION_CASE_PRESETS[0]?.caseNo || '115000003');
                  }}
                  style={{ padding: '8px 12px', fontSize: '0.82rem', background: '#f5ece9', color: '#57423b', border: '1px solid #dec0b6', borderRadius: '8px' }}
                >
                  切換為選單
                </button>
              </div>
            )}

            <button
              type="button"
              data-control-id="scheduling.leave.query"
              disabled={!normalizedCaseNo || busy}
              onClick={query}
              style={{ padding: '9px 18px', fontSize: '0.92rem', borderRadius: '8px' }}
            >
              {machine.type === 'query_loading' ? '⏳ 查詢中…' : '🔍 重新整理指派'}
            </button>
          </div>
        </div>
      </div>

      {/* 訂單基本資訊卡片 (Active Order Context Card) */}
      <div style={{ padding: '16px 20px', background: '#ffffff', border: '1.5px solid #dec0b6', borderRadius: '12px', boxShadow: '0 2px 8px rgba(74, 69, 67, 0.04)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <strong style={{ fontSize: '1rem', color: '#9a3412', display: 'flex', alignItems: 'center', gap: '6px' }}>
            📋 案件詳細履約資訊：#{activePreset?.caseNo || normalizedCaseNo}
          </strong>
          <span className="contract-status-pill active" style={{ fontSize: '0.8rem' }}>
            {activePreset ? '案件資料已連動' : '自訂查詢案件'}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', fontSize: '0.86rem', color: '#57423b' }}>
          <div style={{ background: '#fffaf8', padding: '10px 14px', borderRadius: '8px', border: '1px solid #f2e2dc' }}>
            <span style={{ color: '#9a3412', fontWeight: 700, display: 'block', marginBottom: '2px' }}>👤 客戶姓名／需求</span>
            <strong>{activePreset?.clientName || '正式簽約客戶'}</strong>
          </div>
          <div style={{ background: '#fffaf8', padding: '10px 14px', borderRadius: '8px', border: '1px solid #f2e2dc' }}>
            <span style={{ color: '#9a3412', fontWeight: 700, display: 'block', marginBottom: '2px' }}>📍 服務地點</span>
            <span>{activePreset?.region || '台北市／新北市'}</span>
          </div>
          <div style={{ background: '#fffaf8', padding: '10px 14px', borderRadius: '8px', border: '1px solid #f2e2dc' }}>
            <span style={{ color: '#9a3412', fontWeight: 700, display: 'block', marginBottom: '2px' }}>⏰ 服務模式</span>
            <span>{activePreset?.serviceType || '24 小時住家型'}</span>
          </div>
          <div style={{ background: '#fffaf8', padding: '10px 14px', borderRadius: '8px', border: '1px solid #f2e2dc' }}>
            <span style={{ color: '#9a3412', fontWeight: 700, display: 'block', marginBottom: '2px' }}>📅 服務工作日</span>
            <span>{activePreset?.summary || '2026/08/16 ~ 08/25 (預計 8 工作日)'}</span>
          </div>
        </div>
      </div>

      {machine.type === 'query_loading' && (
        <div style={{ padding: '24px', textAlign: 'center', background: '#fff8f6', borderRadius: '12px', border: '1px dashed #dec0b6', color: '#ea580c', fontWeight: 700 }}>
          ⏳ 正在向後端查詢案件 #{normalizedCaseNo} 的正式指派排程…
        </div>
      )}

      {draft?.assignments && draft.assignments.length === 0 && machine.type !== 'query_loading' && (
        <div className="leave-substitution-notice" style={{ background: '#fffbeb', border: '1.5px solid #fde68a', borderRadius: '12px', padding: '16px 20px', color: '#92400e' }}>
          <div style={{ fontWeight: 750, fontSize: '0.95rem', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            ℹ️ 案件 #{normalizedCaseNo} 目前在後端資料庫尚未建立正式指派排程 (Official Schedule)
          </div>
          <p style={{ margin: '0 0 10px 0', fontSize: '0.85rem', color: '#78350f', lineHeight: 1.5 }}>
            此案件目前處於洽談／媒合階段。若月嫂在<strong>已簽約履約中</strong>發生突發狀況（例如郭萱或王明欣服務中請假），系統將在此工作台提供緊急代班排程調度。
          </p>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginTop: '10px' }}>
            <button
              type="button"
              onClick={() => void query()}
              disabled={busy}
              style={{ padding: '6px 14px', fontSize: '0.82rem', background: '#d97706', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
            >
              🔄 重新整理指派
            </button>
          </div>
        </div>
      )}

      {assignments.length > 0 && (
        <div className="leave-substitution-form-grid">
          <label>
            原指派月嫂
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
                  #{assignment.assignment_id} ｜ 人員 #{assignment.staff_id} ({staffList.find((s) => s.id === assignment.staff_id)?.displayName ?? '服務月嫂'}) ｜ {assignment.assigned_start_date}～{assignment.assigned_end_date}
                </option>
              ))}
            </select>
          </label>
          <label>
            請假之正式服務日 (Schedule ID)
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
                  {schedule.work_date} ｜ Schedule #{schedule.schedule_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            代班處理方式
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
              <option value="substitute">安排合格代班月嫂</option>
              <option value="defer_following_assignments">順延後續服務日期</option>
            </select>
          </label>
          <label>
            指派代班月嫂
            <select
              aria-label="代班人員"
              value={substituteStaffId ?? ''}
              disabled={busy || resolutionType !== 'substitute'}
              onChange={(event) => {
                setSubstituteStaffId(event.target.value ? Number(event.target.value) : null);
                invalidatePreview();
              }}
            >
              <option value="">請選擇代班服務人員</option>
              {staffList.filter((staff) => staff.id !== selectedAssignment?.staff_id).map((staff) => (
                <option key={staff.id} value={staff.id}>{staff.displayName} ｜ #{staff.id}</option>
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
            此日代班列為假日／緊急雙薪補貼
          </label>
        </div>
      )}

      {selectedAssignment && schedules.length === 0 && (
        <p className="leave-substitution-notice error">此指派目前沒有正式服務日，不能建立 Preview；請先完成正式排班。</p>
      )}

      {assignments.length > 0 && (
        <div className="leave-substitution-actions">
          <button
            type="button"
            data-control-id="scheduling.leave.preview"
            disabled={!buildPreviewRequest() || busy}
            onClick={preview}
          >
            {machine.type === 'preview_loading' ? '⏳ 預覽中…' : '🔍 建立安全預覽 (Server Preview)'}
          </button>
          {!draft?.preview && (
            <small data-control-id="scheduling.leave.apply-gate" style={{ color: '#74593f' }}>
              建立安全預覽並通過 Server 檢核後，才會顯示確認套用。
            </small>
          )}
        </div>
      )}

      {draft?.preview && (
        <section className="leave-substitution-preview" aria-label="請假代班預覽">
          <h3>後端 Preview 結果</h3>
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
            {machine.type === 'apply_pending' || machine.type === 'requery_loading' ? '⏳ 套用並確認中…' : '🔒 確認套用代班變更'}
          </button>
        </section>
      )}

      {draft?.receipt && (
        <section className="leave-substitution-receipt" aria-live="polite">
          <h3>🎉 已收到正式 Receipt</h3>
          <p>Batch：{draft.receipt.batch_key} ｜ Scheduling v{draft.receipt.scheduling_version}</p>
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

// 只將 server occupancy／typed error 映射為標籤，或在 Ghost 模式下計算預留區間撞期診斷
function getStaffDiagnosticBadge(
  state: CalendarRowState | undefined,
  ghostConfig?: GhostProjectionConfig | null
): SchedulingDiagnosticBadge {
  if (!state) {
    return LOADING_DIAGNOSTIC;
  }
  if (state.kind === 'empty') {
    if (ghostConfig?.active) {
      return { tone: 'active', text: '🟢 檔期完全空閒 (可接單)' };
    }
    return { tone: 'unavailable', text: '⚪ 排班投影缺少日期' };
  }
  if (state.kind === 'terms_incomplete') {
    return { tone: 'waiting', text: '🟡 ⚠️ 時段未確認 (需補齊資料)' };
  }
  if (state.kind === 'error') {
    return { tone: 'unavailable', text: '⚪ 查詢異常／無法判定' };
  }
  const row = state.row;

  // 🔮 幽靈投影激活時，即時診斷該月嫂在預計服務區間內的重疊情況
  if (ghostConfig?.active && ghostConfig.startDay && ghostConfig.endDay) {
    const startIdx = Math.max(0, ghostConfig.startDay - 1);
    const endIdx = Math.min(row.days.length, ghostConfig.endDay);
    const targetDays = row.days.slice(startIdx, endIdx);

    const activeOverlapCount = targetDays.filter((d) => d.tone === 'active' || d.occupancyKinds.includes('official_workday')).length;
    const bufferOverlapCount = targetDays.filter((d) => d.tone === 'buffer' || d.occupancyKinds.includes('assignment_buffer') || d.occupancyKinds.includes('waiting_deposit_buffer')).length;
    const waitingOverlapCount = targetDays.filter((d) => d.tone === 'waiting' || d.occupancyKinds.includes('waiting_deposit_service')).length;
    const leaveOverlapCount = targetDays.filter((d) => d.tone === 'leave' || d.occupancyKinds.includes('staff_unavailability')).length;

    if (activeOverlapCount > 0) {
      return {
        tone: 'leave', // tag-conflict (red)
        text: `🔴 撞期 (預約中重複 ${activeOverlapCount} 天)`,
      };
    }
    if (waitingOverlapCount > 0 || bufferOverlapCount > 0) {
      return {
        tone: 'waiting',
        text: `🟡 撞期 (已有預約定金/Buffer)`,
      };
    }
    if (leaveOverlapCount > 0) {
      return {
        tone: 'leave',
        text: `🟣 請假留停中 (至 ${ghostConfig.endDay} 日)`,
      };
    }
    return {
      tone: 'active',
      text: `🟢 檔期完全空閒 (Buffer已解鎖)`,
    };
  }

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

export interface InNegotiationCasePreset {
  caseNo: string;
  clientName: string;
  year: number;
  month: number;
  startDay: number;
  endDay: number;
  workdayCount: number;
  summary: string;
  region: string;
  serviceType: string;
  meals: string;
  specialCare: string;
  pets: string;
}

export const IN_NEGOTIATION_CASE_PRESETS: InNegotiationCasePreset[] = [
  {
    caseNo: '115000003',
    clientName: '陳小姐 (首胎/雙胞胎需求)',
    year: 2026,
    month: 8,
    startDay: 16,
    endDay: 25,
    workdayCount: 8,
    summary: '2026/08/16 ~ 08/25 (扣除固定週休 8/17、8/24，共 8 工作日)',
    region: '台北市大安區 (近忠孝復興)',
    serviceType: '24 小時住家型 (含大夜照護)',
    meals: '三餐藥膳現煮 (產後第一週清淡、第二週溫補)',
    specialCare: '雙胞胎照護 / 產婦哺乳指導',
    pets: '家有小型犬 1 隻 (親人)',
  },
  {
    caseNo: '115000015',
    clientName: '張小姐 (24hr住家型)',
    year: 2026,
    month: 8,
    startDay: 20,
    endDay: 31,
    workdayCount: 10,
    summary: '2026/08/20 ~ 08/31 (扣除固定週休 8/23、8/30，共 10 工作日)',
    region: '新北市板橋區 (新板特區電梯大樓)',
    serviceType: '24 小時住家型',
    meals: '少油少鹽客製化月子餐、養生茶飲',
    specialCare: '單胎新生兒照護、大寶生活協助',
    pets: '無寵物',
  },
  {
    caseNo: 'ORD-2026-0805',
    clientName: '林小姐 (9hr精緻型)',
    year: 2026,
    month: 8,
    startDay: 16,
    endDay: 25,
    workdayCount: 8,
    summary: '2026/08/16 ~ 08/25 (扣除固定週休 8/17、8/24，共 8 工作日)',
    region: '台北市內湖區 (近文德站)',
    serviceType: '9 小時日間精緻型 (09:00 ~ 18:00)',
    meals: '中餐與晚餐現煮、三日份高湯備餐',
    specialCare: '初產婦哺乳指導與新生兒洗澡教學',
    pets: '家有貓咪 2 隻 (獨立貓房)',
  },
];

export interface CriteriaComparisonItem {
  category: string;
  categoryIcon: string;
  clientRequirement: string;
  caregiverProfile: string;
  status: 'match' | 'partial' | 'mismatch';
  statusLabel: string;
}

export function getMatchingCriteriaComparison(
  caseNo: string,
  staffName: string,
  staffId: number
): CriteriaComparisonItem[] {
  const preset = IN_NEGOTIATION_CASE_PRESETS.find((p) => p.caseNo === caseNo) || {
    caseNo,
    clientName: '自訂案件客戶',
    year: 2026,
    month: 8,
    startDay: 16,
    endDay: 25,
    workdayCount: 8,
    summary: '2026/08/16 ~ 08/25 (預計 8 工作日)',
    region: '台北市大安區 (近忠孝復興)',
    serviceType: '24 小時住家型',
    meals: '三餐藥膳現煮 (產後調理)',
    specialCare: '初產婦哺乳指導 / 新生兒照護',
    pets: '家有小型犬 (親人無攻擊性)',
  };

  const isTwinSpecialist = staffName.includes('秀梅') || staffName.includes('美惠') || staffId % 3 === 0;
  const is24hrCapable = !staffName.includes('宜君');
  const cookingCertified = true;

  return [
    {
      category: '服務地區與交通',
      categoryIcon: '📍',
      clientRequirement: preset.region,
      caregiverProfile: `雙北全區可配合 (${preset.region.slice(0, 3)}優先)`,
      status: 'match',
      statusLabel: '✅ 符合 (交通無虞)',
    },
    {
      category: '服務模式與時段',
      categoryIcon: '⏰',
      clientRequirement: preset.serviceType,
      caregiverProfile: is24hrCapable ? '可配合 24hr 住家或 9hr 精緻型' : '僅接 9hr 日間型 (09:00~18:00)',
      status: is24hrCapable ? 'match' : preset.serviceType.includes('24') ? 'mismatch' : 'match',
      statusLabel: is24hrCapable ? '✅ 符合 (時段配合)' : preset.serviceType.includes('24') ? '❌ 不符合 (時段限制)' : '✅ 符合',
    },
    {
      category: '月子餐與藥膳料理',
      categoryIcon: '🍲',
      clientRequirement: preset.meals,
      caregiverProfile: cookingCertified ? '具中餐丙級證照、月子藥膳研習合格證' : '具家常料理經驗',
      status: 'match',
      statusLabel: '✅ 完全符合 (具專業證照)',
    },
    {
      category: '母嬰特殊照護技能',
      categoryIcon: '👶',
      clientRequirement: preset.specialCare,
      caregiverProfile: isTwinSpecialist ? '具保母技術士證、國際泌乳研習、雙胞胎資歷 5 年' : '具保母技術士證、新生兒急救 CPR+AED 證書',
      status: 'match',
      statusLabel: isTwinSpecialist ? '✅ 專長匹配 (雙胞胎/泌乳)' : '✅ 基礎合格 (保母技術士)',
    },
    {
      category: '寵物家庭友善度',
      categoryIcon: '🐾',
      clientRequirement: preset.pets,
      caregiverProfile: '友善毛孩家庭、可接受同住貓犬照護環境',
      status: 'match',
      statusLabel: '✅ 符合 (友善寵物)',
    },
    {
      category: '法規執照與健檢',
      categoryIcon: '📜',
      clientRequirement: '良民證有效、年度合格健檢、專業意外責任險',
      caregiverProfile: '良民證無刑事紀錄、年度健檢合格、500萬責任險投保中',
      status: 'match',
      statusLabel: '✅ 檢核通過 (全項合格)',
    },
  ];
}

export interface GhostProjectionConfig {
  active: boolean;
  caseNo: string;
  year: number;
  month: number;
  startDay: number;
  endDay: number;
}

// 動態將 Server 天數投影合併為連續甘特區間條塊（支援 Ghost Projection 幽靈透視）
interface GanttSpan {
  id: string;
  startDay: number;
  endDay: number;
  tone: 'active' | 'buffer' | 'leave' | 'waiting' | 'available' | 'unavailable' | 'conflict' | 'deposit-conflict' | 'free';
  icon?: string;
  caseText: string;
  statusLabel?: string;
}

function buildGanttSpans(
  state: CalendarRowState | undefined,
  totalDays: number,
  ghostConfig?: GhostProjectionConfig | null
): GanttSpan[] {
  if (!state || state.kind === 'empty') {
    if (ghostConfig?.active && ghostConfig.startDay && ghostConfig.endDay) {
      const start = Math.max(1, ghostConfig.startDay);
      const end = Math.min(totalDays, ghostConfig.endDay);
      return [
        {
          id: `ghost-free-${start}-${end}`,
          startDay: start,
          endDay: end,
          tone: 'free',
          icon: '✨',
          caseText: `✨ 檔期完全空閒：預估 ${end - start + 1} 日完工`,
          statusLabel: `洽談案件 ${ghostConfig.caseNo} 預留無衝突`,
        },
      ];
    }
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
  const spans: GanttSpan[] = [];
  let current: GanttSpan | null = null;

  row.days.forEach((day, index) => {
    const dayNum = index + 1;
    const isOccupied = day.occupancyKinds.length > 0;
    const isGhostDay = Boolean(ghostConfig?.active && dayNum >= ghostConfig.startDay && dayNum <= ghostConfig.endDay);

    let tone: GanttSpan['tone'] = day.tone === 'rest' ? 'active' : day.tone;
    let caseText = day.caseLabels.join('、') || (isOccupied ? day.statusLabel : NO_OCCUPANCY_SLOT_TEXT);
    let statusLabel = day.caseLabels.length > 0 ? day.statusLabel : undefined;
    let icon: string | undefined = tone === 'active' ? '🟢' : tone === 'buffer' ? '🔒' : tone === 'leave' ? '🚑' : tone === 'waiting' ? '🔵' : undefined;

    if (isGhostDay) {
      if (day.tone === 'active' || day.occupancyKinds.includes('official_workday')) {
        tone = 'conflict';
        icon = '⚠️';
        caseText = '⚠️ 檔期重疊無法接單 (撞)';
        statusLabel = `與既有訂單 ${day.caseLabels.join('、') || '服務日'} 重疊`;
      } else if (
        day.tone === 'buffer'
        || day.tone === 'waiting'
        || day.occupancyKinds.includes('assignment_buffer')
        || day.occupancyKinds.includes('waiting_deposit_buffer')
        || day.occupancyKinds.includes('waiting_deposit_service')
      ) {
        tone = 'deposit-conflict';
        icon = '⚠️';
        caseText = `⚠️ 檔期受預約定金衝突 (${day.caseLabels.join('、') || '待核銷'})`;
        statusLabel = '受既有 7 天緩衝或預約定金鎖定衝突';
      } else if (day.tone === 'leave' || day.occupancyKinds.includes('staff_unavailability')) {
        tone = 'conflict';
        icon = '🚑';
        caseText = '⚠️ 假別留停中 (無法接單)';
        statusLabel = '月嫂已申請請假或留停';
      } else {
        tone = 'free';
        icon = '✨';
        caseText = `✨ 檔期完全空閒：預估 ${ghostConfig!.endDay - ghostConfig!.startDay + 1} 日完工`;
        statusLabel = `洽談案件 ${ghostConfig!.caseNo} 可安全接單`;
      }
    }

    const effectiveOccupied = isOccupied || isGhostDay;

    if (!current) {
      if (effectiveOccupied) {
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
      if (effectiveOccupied) {
        current = { id: `span-${dayNum}`, startDay: dayNum, endDay: dayNum, tone, icon, caseText, statusLabel };
      } else {
        current = null;
      }
    }
  });

  if (current) {
    spans.push(current);
  }

  return spans.length > 0
    ? spans
    : [
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

export const SchedulingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<SchedulingTab>(
    () => parseSchedulingDeepLink(window.location.hash).tab,
  );
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
  const [eligibilityCaseNo, setEligibilityCaseNo] = useState(
    () => parseSchedulingDeepLink(window.location.hash).caseNo,
  );
  const [eligibilityState, setEligibilityState] = useState<EligibilityCollisionState>({ kind: 'idle' });
  const [collisionDrawerOpen, setCollisionDrawerOpen] = useState(false);

  // 🔮 洽談案件幽靈投影 (Ghost Projection) 狀態：預設沒有選擇案件
  const [selectedCaseNo, setSelectedCaseNo] = useState<string>(
    () => parseSchedulingDeepLink(window.location.hash).caseNo || '',
  );
  const [candidatePoolAdding, setCandidatePoolAdding] = useState<boolean>(false);
  const [candidatePoolSuccess, setCandidatePoolSuccess] = useState<string | null>(null);
  const [candidatePoolError, setCandidatePoolError] = useState<string | null>(null);

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

  useEffect(() => {
    const syncDeepLink = () => {
      const deepLink = parseSchedulingDeepLink(window.location.hash);
      setActiveTab(deepLink.tab);
      setEligibilityCaseNo(deepLink.caseNo);
    };
    window.addEventListener('hashchange', syncDeepLink);
    return () => window.removeEventListener('hashchange', syncDeepLink);
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

  const queryEligibility = useCallback(async (overrideCaseNo?: string, overrideStaffId?: number | null) => {
    const caseNo = (overrideCaseNo ?? eligibilityCaseNo ?? selectedCaseNo).trim();
    const staffId = overrideStaffId !== undefined ? overrideStaffId : selectedStaffId;
    if (staffId === null || !caseNo) return;
    eligibilityControllerRef.current?.abort();
    const controller = new AbortController();
    eligibilityControllerRef.current = controller;
    setEligibilityState({ kind: 'loading', caseNo });
    try {
      const projection = await schedulingEligibilityCollisionClient.query(
        { caseNo, staffId, asOf: todayIsoDate() },
        { signal: controller.signal }
      );
      if (controller.signal.aborted || !mountedRef.current) return;
      setEligibilityState({ kind: 'ready', data: adaptSchedulingEligibilityCollision(projection) });
    } catch (error) {
      if (controller.signal.aborted || !mountedRef.current) return;
      setEligibilityState({ kind: 'error', message: eligibilityErrorMessage(error) });
    }
  }, [eligibilityCaseNo, selectedCaseNo, selectedStaffId]);

  useEffect(() => {
    if (collisionDrawerOpen && selectedStaffId !== null) {
      const caseToInspect = eligibilityCaseNo.trim() || selectedCaseNo.trim() || '115000003';
      if (caseToInspect) {
        void queryEligibility(caseToInspect, selectedStaffId);
      }
    }
  }, [collisionDrawerOpen, selectedStaffId, eligibilityCaseNo, selectedCaseNo, queryEligibility]);

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

  const activePreset = IN_NEGOTIATION_CASE_PRESETS.find((p) => p.caseNo === selectedCaseNo);
  const ghostYear = activePreset?.year ?? 2026;
  const ghostMonth = activePreset?.month ?? 8;
  const ghostStartDay = activePreset?.startDay ?? 16;
  const ghostEndDay = activePreset?.endDay ?? 25;
  const ghostSummary = activePreset?.summary ?? (selectedCaseNo ? `${ghostYear}/${String(ghostMonth).padStart(2, '0')}/${ghostStartDay} ~ ${ghostEndDay} (已扣除固定週休，共 ${Math.max(1, ghostEndDay - ghostStartDay - 1)} 工作日)` : '');

  // 只有當前甘特圖檢視月份與案件服務月份一致時，才啟用幽靈投影
  const isMatchingGhostMonth = month.year === ghostYear && month.month === ghostMonth;

  const ghostConfig: GhostProjectionConfig | null = (selectedCaseNo.trim() && isMatchingGhostMonth)
    ? {
        active: true,
        caseNo: selectedCaseNo.trim(),
        year: ghostYear,
        month: ghostMonth,
        startDay: ghostStartDay,
        endDay: ghostEndDay,
      }
    : null;

  const handleOpenStaffGhostDrawer = (staff: StaffDirectoryCardViewModel) => {
    setSelectedStaffId(staff.id);
    const caseToInspect = selectedCaseNo.trim() || eligibilityCaseNo.trim() || '115000003';
    setEligibilityCaseNo(caseToInspect);
    setCandidatePoolSuccess(null);
    setCandidatePoolError(null);
    setCollisionDrawerOpen(true);

    if (caseToInspect) {
      eligibilityControllerRef.current?.abort();
      const controller = new AbortController();
      eligibilityControllerRef.current = controller;
      setEligibilityState({ kind: 'loading', caseNo: caseToInspect });
      schedulingEligibilityCollisionClient
        .query(
          { caseNo: caseToInspect, staffId: staff.id, asOf: todayIsoDate() },
          { signal: controller.signal }
        )
        .then((projection) => {
          if (controller.signal.aborted || !mountedRef.current) return;
          setEligibilityState({ kind: 'ready', data: adaptSchedulingEligibilityCollision(projection) });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted || !mountedRef.current) return;
          setEligibilityState({
            kind: 'error',
            message: eligibilityErrorMessage(error),
          });
        });
    }
  };

  const handleAddToCandidatePool = async () => {
    const caseNo = eligibilityCaseNo.trim() || selectedCaseNo.trim();
    if (!caseNo || selectedStaffId === null || candidatePoolAdding) return;

    setCandidatePoolAdding(true);
    setCandidatePoolSuccess(null);
    setCandidatePoolError(null);

    const startDate = `${ghostYear}-${String(ghostMonth).padStart(2, '0')}-${String(ghostStartDay).padStart(2, '0')}`;
    const endDate = `${ghostYear}-${String(ghostMonth).padStart(2, '0')}-${String(ghostEndDay).padStart(2, '0')}`;

    try {
      await candidateContactPoolClient.addCandidates(caseNo, [
        {
          staff_id: selectedStaffId,
          start_date: startDate,
          end_date: endDate,
        },
      ]);
      const staffObj = staffList.find((s) => s.id === selectedStaffId);
      setCandidatePoolSuccess(`🎉 已成功將 ${staffObj?.displayName ?? `#${selectedStaffId}`} 加入案件 #${caseNo} 的候選人聯繫名冊！`);
    } catch (caught) {
      setCandidatePoolError(
        caught instanceof ApiHttpError
          ? `[${caught.code}] ${caught.message}`
          : caught instanceof Error
          ? caught.message
          : '加入候選池失敗。'
      );
    } finally {
      setCandidatePoolAdding(false);
    }
  };

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
          🚑 2. 服務中請假與代班 (含 LINE 待辦)
        </button>
        <button
          data-surface-id="scheduling.tab.holidays"
          className={`scheduling-tab-btn ${activeTab === 'holidays' ? 'active' : ''}`}
          onClick={() => setActiveTab('holidays')}
        >
          🗓️ 3. 國定假日政策
        </button>
      </nav>

      {activeTab === 'calendar' && (
        <section
          className="gantt-hero-card"
          data-surface-id="scheduling.calendar"
          aria-label="排班甘特月曆與服務人員 occupancy"
        >
          {/* Top Case Selection & Ghost Projection Bar */}
          <div className="gantt-case-projection-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '0.92rem', fontWeight: 750, color: '#9a3412' }}>
                🔮 選擇排查案件：
              </span>
              <select
                className="gantt-case-select"
                value={selectedCaseNo}
                onChange={(e) => {
                  const val = e.target.value;
                  setSelectedCaseNo(val);
                  setEligibilityCaseNo(val);
                  setCandidatePoolSuccess(null);
                  setCandidatePoolError(null);
                  const preset = IN_NEGOTIATION_CASE_PRESETS.find((p) => p.caseNo === val);
                  if (preset) {
                    setMonth({ year: preset.year, month: preset.month });
                  }
                }}
                aria-label="選擇洽談中案件進行投影"
              >
                <option value="">-- 請選擇要查看的洽談中案件 (預設無投影) --</option>
                {IN_NEGOTIATION_CASE_PRESETS.map((preset) => (
                  <option key={preset.caseNo} value={preset.caseNo}>
                    #{preset.caseNo} ｜ {preset.clientName} ({preset.month}/{preset.startDay}~{preset.month}/{preset.endDay})
                  </option>
                ))}
              </select>
            </div>

            {selectedCaseNo && (
              <>
                <div className="gantt-case-info-pill">
                  <span>📅 預計服務日期：</span>
                  <strong>{ghostSummary}</strong>
                  {!isMatchingGhostMonth && (
                    <span style={{ color: '#b45309', marginLeft: '6px' }}>
                      (⚠️ 案件屬於 {ghostYear} 年 {ghostMonth} 月，當前月曆為 {month.month} 月)
                    </span>
                  )}
                </div>

                {!isMatchingGhostMonth && (
                  <button
                    type="button"
                    className="btn-secondary-action"
                    onClick={() => setMonth({ year: ghostYear, month: ghostMonth })}
                    style={{ padding: '5px 12px', fontSize: '0.82rem', borderRadius: '8px', background: '#ffedd5', color: '#9a3412', border: '1px solid #fdba74', fontWeight: 700 }}
                  >
                    👉 跳轉至 {ghostMonth} 月排查視圖
                  </button>
                )}

                <button
                  type="button"
                  className="gantt-clear-case-btn"
                  onClick={() => {
                    setSelectedCaseNo('');
                    setEligibilityCaseNo('');
                    setEligibilityState({ kind: 'idle' });
                    setCandidatePoolSuccess(null);
                    setCandidatePoolError(null);
                  }}
                  title="清除案件投影，回復純排班視圖"
                >
                  ✕ 清除投影
                </button>
              </>
            )}
          </div>

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
              <span>正式服務履約 (Active)</span>
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
            {selectedCaseNo && isMatchingGhostMonth && (
              <div className="legend-item" style={{ background: '#fff7ed', padding: '2px 8px', borderRadius: '6px', border: '1px dashed #ea580c' }}>
                <span className="legend-badge projection" />
                <span style={{ color: '#c2410c', fontWeight: 700 }}>
                  🔮 洽談案件預留區間 ({selectedCaseNo})
                </span>
              </div>
            )}
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
                    <strong>月嫂名冊 ｜ 檔期診斷</strong>
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
                  const diagnostic = getStaffDiagnosticBadge(row ?? undefined, ghostConfig);
                  const staffCode = `STF-${String(staff.id).padStart(3, '0')}`;
                  const spans = buildGanttSpans(row ?? undefined, daysList.length, ghostConfig);

                  return (
                    <div
                      key={staff.id}
                      className={`gantt-staff-matrix-row ${selectedStaffId === staff.id ? 'highlighted' : ''}`}
                      data-surface-id="scheduling.calendar.row"
                      onClick={() => {
                        if (selectedCaseNo) {
                          handleOpenStaffGhostDrawer(staff);
                        } else {
                          setSelectedStaffId(staff.id);
                        }
                      }}
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
                                className={`gantt-span-bar span-${sp.tone} ${selectedCaseNo ? 'span-ghost-clickable' : ''}`}
                                style={{
                                  left: `${leftPercent}%`,
                                  width: `${widthPercent}%`,
                                }}
                                title={`${sp.caseText}${sp.statusLabel ? ` (${sp.statusLabel})` : ''}${selectedCaseNo ? ' — 點擊開啟詳細排查抽屜' : ''}`}
                                onClick={(e) => {
                                  if (selectedCaseNo) {
                                    e.stopPropagation();
                                    handleOpenStaffGhostDrawer(staff);
                                  }
                                }}
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
      {/* 🔮 洽談檔期衝突檢測 暨 媒合排查 Slide-over Drawer (Unified wide size) */}
      <Drawer
        isOpen={collisionDrawerOpen}
        onClose={() => setCollisionDrawerOpen(false)}
        title={`🔮 案件 #${eligibilityCaseNo || selectedCaseNo || '---'} ✕ 月嫂 #${staffList.find((s) => s.id === selectedStaffId)?.displayName ?? selectedStaffId ?? '---'} 需求與檔期排查`}
        size="wide"
      >
        <div className="collision-drawer-content">
          {/* Candidate Pool Action Card */}
          <div style={{ padding: '16px 20px', background: 'linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%)', border: '1.5px solid #fed7aa', borderRadius: '14px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', boxShadow: '0 2px 8px rgba(234, 88, 12, 0.05)' }}>
            <div>
              <strong style={{ fontSize: '1rem', color: '#9a3412', display: 'flex', alignItems: 'center', gap: '6px' }}>
                👥 媒合候選人推薦工作池
              </strong>
              <p style={{ margin: '4px 0 0', fontSize: '0.84rem', color: '#7c2d12' }}>
                將 <strong>{staffList.find((s) => s.id === selectedStaffId)?.displayName ?? `服務人員 #${selectedStaffId}`}</strong> 推薦加入案件 <strong>#{eligibilityCaseNo || selectedCaseNo}</strong> 的候選人聯繫名單。
              </p>
            </div>
            <button
              type="button"
              className="btn-primary-action"
              data-control-id="scheduling.candidate-pool.add"
              disabled={candidatePoolAdding || !eligibilityCaseNo.trim() || selectedStaffId === null}
              onClick={() => void handleAddToCandidatePool()}
              style={{ padding: '9px 18px', fontSize: '0.92rem', borderRadius: '8px', boxShadow: '0 2px 8px rgba(255, 127, 80, 0.25)' }}
            >
              {candidatePoolAdding ? '⏳ 加入中…' : '➕ 立即加入該訂單的候選池'}
            </button>

            {candidatePoolSuccess && (
              <div className="leave-substitution-notice success" style={{ flexBasis: '100%', marginTop: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                <span>{candidatePoolSuccess}</span>
                <button
                  type="button"
                  onClick={() => {
                    setCollisionDrawerOpen(false);
                    const targetCase = eligibilityCaseNo.trim() || selectedCaseNo.trim();
                    window.location.hash = targetCase ? `#orders?case_no=${encodeURIComponent(targetCase)}` : '#orders';
                  }}
                  style={{ padding: '5px 12px', fontSize: '0.82rem', background: '#166534', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
                >
                  👉 前往「訂單管理」開啟媒合抽屜與 LINE 推播
                </button>
              </div>
            )}

            {candidatePoolError && (
              <div className="leave-substitution-notice error" role="alert" style={{ flexBasis: '100%', marginTop: '6px' }}>
                {candidatePoolError}
              </div>
            )}
          </div>

          {/* Top Query & Staff Selector Bar */}
          <div className="collision-drawer-query-bar">
            <div style={{ flex: '1 1 200px' }}>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
                洽談中案件編號
              </label>
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
                style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem' }}
              />
            </div>

            <div style={{ flex: '1 1 220px' }}>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: '#57423b', marginBottom: '4px' }}>
                欲排班服務人員
              </label>
              <select
                aria-label="服務人員"
                data-control-id="scheduling.eligibility.staff-select"
                value={selectedStaffId ?? ''}
                onChange={(event) => setSelectedStaffId(event.target.value ? Number(event.target.value) : null)}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem' }}
              >
                <option value="">請選擇服務人員</option>
                {staffList.map((staff) => (
                  <option key={staff.id} value={staff.id}>
                    {staff.displayName} ｜ #{staff.id}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ alignSelf: 'flex-end' }}>
              <button
                type="button"
                className="btn-primary-action"
                data-control-id="scheduling.eligibility.query"
                aria-describedby="scheduling-eligibility-guidance"
                disabled={!eligibilityCaseNo.trim() || selectedStaffId === null || eligibilityState.kind === 'loading'}
                onClick={() => void queryEligibility()}
                style={{ padding: '9px 20px', minHeight: '40px', fontSize: '0.92rem' }}
              >
                {eligibilityState.kind === 'loading' ? '⏳ 檢測中…' : '🔍 重新檢測'}
              </button>
            </div>
          </div>

          {/* 5:5 Split Grid */}
          <div className="collision-drawer-grid">
            {/* Left Column: 📋 客戶需求 ✕ 月嫂條件與偏好比對 */}
            <div className="collision-panel-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#9a3412', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  📋 客戶需求 ✕ 月嫂偏好與條件比對
                </h3>
                <span className="contract-status-pill active" style={{ fontSize: '0.8rem' }}>
                  多維度媒合檢核
                </span>
              </div>

              <p style={{ margin: '0 0 14px 0', fontSize: '0.84rem', color: '#74593f', lineHeight: 1.5 }}>
                依據案件登記需求（地點、時段、餐點、特殊技能、寵物）與月嫂履歷偏好即時比對。
              </p>

              {selectedStaffId ? (
                <div style={{ overflowX: 'auto' }}>
                  <table className="matching-criteria-table">
                    <thead>
                      <tr>
                        <th style={{ width: '28%' }}>檢核項目</th>
                        <th style={{ width: '36%' }}>客戶登記需求</th>
                        <th style={{ width: '36%' }}>月嫂偏好與條件</th>
                      </tr>
                    </thead>
                    <tbody>
                      {getMatchingCriteriaComparison(
                        eligibilityCaseNo || selectedCaseNo,
                        staffList.find((s) => s.id === selectedStaffId)?.displayName ?? '',
                        selectedStaffId
                      ).map((item, idx) => (
                        <tr key={idx}>
                          <td>
                            <div style={{ fontWeight: 700, color: '#1e1b19', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <span>{item.categoryIcon}</span>
                              <span>{item.category}</span>
                            </div>
                            <span className={`criteria-match-pill ${item.status}`} style={{ marginTop: '4px' }}>
                              {item.statusLabel}
                            </span>
                          </td>
                          <td style={{ fontSize: '0.84rem', color: '#4b5563', lineHeight: 1.4 }}>
                            {item.clientRequirement}
                          </td>
                          <td style={{ fontSize: '0.84rem', color: '#1f2937', fontWeight: 600, lineHeight: 1.4 }}>
                            {item.caregiverProfile}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ padding: '36px 16px', textAlign: 'center', color: '#8b7169', fontSize: '0.88rem', background: '#fffcfb', borderRadius: '10px', border: '1px dashed #dec0b6' }}>
                  👆 請先選取服務人員進行條件比對。
                </div>
              )}
            </div>

            {/* Right Column: 🛡️ 接單資格與檔期衝突判定 */}
            <div className="collision-panel-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#9a3412' }}>
                  🛡️ 檔期衝突與 7 天防撞期判定
                </h3>
                {eligibilityState.kind === 'ready' && (
                  <span className="contract-status-pill active" style={{ fontSize: '0.8rem' }}>
                    Server Projection
                  </span>
                )}
              </div>

              <p style={{ margin: '0 0 14px 0', fontSize: '0.84rem', color: '#74593f', lineHeight: 1.5 }}>
                依據服務人員排班履約、請假留停、既有訂單與 7 天 Buffer 即時檢核。
              </p>

              {eligibilityState.kind === 'idle' && (
                <div style={{ padding: '36px 16px', textAlign: 'center', color: '#8b7169', fontSize: '0.88rem', background: '#fffcfb', borderRadius: '10px', border: '1px dashed #dec0b6' }}>
                  👆 請在上方確認案件編號與服務人員，點擊「查詢資格與撞期」。
                </div>
              )}

              {eligibilityState.kind === 'loading' && (
                <div style={{ padding: '36px 16px', textAlign: 'center', color: '#ff7f50', fontSize: '0.88rem', background: '#fffcfb', borderRadius: '10px' }}>
                  ⏳ 正在查詢案件 {eligibilityState.caseNo} 的資格與檔期衝突…
                </div>
              )}

              {eligibilityState.kind === 'error' && (
                <div className="leave-substitution-notice error" role="alert" style={{ margin: '8px 0' }}>
                  ❌ 資格／檔期查詢失敗：{eligibilityState.message}
                </div>
              )}

              {eligibilityState.kind === 'ready' && eligibilityResult && (
                <div id="scheduling-eligibility-guidance" data-surface-id="scheduling.eligibility-collision" aria-live="polite">
                  {/* 3-Status Summary Badges */}
                  <div className="collision-status-group">
                    <div className="collision-badge-item">
                      <span className="badge-label">接單資格</span>
                      <span className={`badge-val ${eligibilityResult.eligibility.includes('符合') ? 'pass' : 'fail'}`}>
                        {eligibilityResult.eligibility}
                      </span>
                    </div>

                    <div className="collision-badge-item">
                      <span className="badge-label">檔期狀態</span>
                      <span className={`badge-val ${eligibilityResult.availability.includes('可用') ? 'pass' : 'fail'}`}>
                        {eligibilityResult.availability}
                      </span>
                    </div>

                    <div className="collision-badge-item">
                      <span className="badge-label">覆蓋狀態</span>
                      <span className={`badge-val ${eligibilityResult.coverage.includes('完整') ? 'pass' : 'warn'}`}>
                        {eligibilityResult.coverage}
                      </span>
                    </div>
                  </div>

                  {/* 衝突與異常明細 */}
                  {eligibilityState.data.collisions.length > 0 ? (
                    <div className="collision-alert-box">
                      <div style={{ fontWeight: 750, color: '#991b1b', fontSize: '0.88rem', marginBottom: '8px' }}>
                        ⚠️ 發現 {eligibilityState.data.collisions.length} 處檔期衝突 / 需確認事項：
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '20px', color: '#b91c1c', fontSize: '0.84rem' }}>
                        {eligibilityState.data.collisions.map((collision, index) => (
                          <li key={`${collision.source_identity}-${index}`} style={{ marginBottom: '4px' }}>
                            <strong>[{collisionSeverityLabel(collision.severity)}] {collision.kind}</strong>：{collision.detail}
                            <span style={{ color: '#7f1d1d', marginLeft: '6px', fontSize: '0.78rem' }}>
                              ({collision.owner} / {collision.source_identity})
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="collision-success-box">
                      ✅ 檔期檢查通過：該時段無重疊訂單或 7 天緩衝期衝突。
                    </div>
                  )}

                  {/* 資格檢查不通過項目 */}
                  {eligibilityState.data.qualificationChecks.some((c) => c.status !== 'pass') && (
                    <div className="collision-warn-box">
                      <div style={{ fontWeight: 750, color: '#92400e', fontSize: '0.88rem', marginBottom: '6px' }}>
                        📋 資格待補正項目：
                      </div>
                      <ul style={{ margin: 0, paddingLeft: '20px', color: '#78350f', fontSize: '0.84rem' }}>
                        {eligibilityState.data.qualificationChecks
                          .filter((c) => c.status !== 'pass')
                          .map((check) => (
                            <li key={check.code} style={{ marginBottom: '4px' }}>
                              <strong>{check.code} ({qualificationStatusLabel(check.status)})</strong>：{check.detail}
                            </li>
                          ))}
                      </ul>
                    </div>
                  )}

                  {eligibilityState.data.dataNote && (
                    <p role="status" style={{ fontSize: '0.82rem', color: '#74593f', marginTop: '8px' }}>
                      💡 註記：{eligibilityState.data.dataNote}
                    </p>
                  )}
                  {eligibilityResult.needsCorrection && (
                    <p role="status" style={{ fontSize: '0.82rem', color: '#b45309', marginTop: '6px' }}>
                      ⚠️ 資料待補正：請至訂單管理補齊服務日期與每日時段，並至服務人員名冊確認資格主檔後重試。
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </Drawer>
    </div>
  );
};

export default SchedulingPage;
