/**
 * File: SchedulingPage.tsx
 * Description: 顯示排班甘特月曆、案件檔期排查與國定假日政策。
 */
import { ServiceStartSubstituteWorkbench } from '../components/ServiceStartSubstituteWorkbench';
import { serviceStartClient, type ServiceStartView } from '../api/scheduling/service_start_client';
import { sessionClient } from '../api/auth/session_client';
import { ManagementPageHeader } from '../components/ManagementPageHeader';
import { useUnsavedDraft, useUnsavedNavigation } from '../components/UnsavedChanges';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { subscribeStaffAvailabilityChanges } from '../api/staff_availability/staff_availability_changes';
import './SchedulingPage.css';
import { loadAllStaffDirectoryPages, staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { loadAllOrderSummaries, ordersQueryClient } from '../api/orders/order_query_client';
import { loadAllCoreStageTimelines } from '../api/orders/load_all_core_stage_timelines';
import { adaptStaffDirectoryPage, compareStaffUnionNumbers, staffDisplayLabel } from '../adapters/staff/staff_directory_adapter';
import type { StaffDirectoryCardViewModel } from '../adapters/staff/staff_directory_adapter';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import type { SchedulingCurrentAssignment } from '../api/scheduling/scheduling_current_schemas';
import { holidayClient } from '../api/scheduling/holiday_client';
import { staffMonthlyScheduleClient, type StaffMonthlySchedule } from '../api/scheduling/staff_monthly_schedule_client';
import { coordinatedServiceTime } from '../components/OrderServiceDateCalendar';
import { SchedulingCurrentError } from '../api/scheduling/scheduling_current_errors';
import { schedulingEligibilityCollisionClient } from '../api/scheduling/eligibility_collision_client';
import {
  staffAssignmentOptionsClient,
  type StaffAssignmentOption,
} from '../api/scheduling/staff_assignment_options_client';
import { SchedulingEligibilityCollisionError } from '../api/scheduling/eligibility_collision_errors';
import { ApiHttpError } from '../api/shared/typed_errors';
import {
  adaptSchedulingProjection,
  matchesSchedulingFilter,
  type SchedulingCalendarRowViewModel,
} from '../adapters/scheduling/scheduling_current_adapter';
import { adaptHistoricalAssignmentOverlays, type HistoricalAssignmentOverlay } from '../adapters/scheduling/historical_assignment_overlay_adapter';
import {
  adaptSchedulingEligibilityCollision,
  type SchedulingEligibilityCollisionViewModel,
} from '../adapters/scheduling/eligibility_collision_adapter';
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
import { candidateContactPoolClient } from '../api/scheduling/candidate_contact_pool_client';
import { Drawer } from '../components/Drawer';
import { OfficialHolidayCsvImport } from '../components/scheduling/OfficialHolidayCsvImport';
import { ServiceHandoverPage } from './ServiceHandoverPage';

type SchedulingTab = 'calendar' | 'holidays';
type StatusFilter = 'all' | 'active' | 'waiting' | 'leave';

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

export interface YearThirdSegment {
  key: string;
  year: number;
  month: number;
  thirdIndex: 0 | 1 | 2;
  columnIndex: number;
  label: '上旬' | '中旬' | '下旬';
  monthThirdLabel: string;
  rangeLabel: string;
  startDay: number;
  endDay: number;
  startDate: string;
  endDate: string;
  isActiveMonth: boolean;
  containsToday: boolean;
  todayDateStr: string;
  holidayNames: readonly string[];
}

const GANTT_THIRD_COL_WIDTH = 136;
const GANTT_TOTAL_THIRDS = 36;

/** 建立指定年份 12 個月 × 上／中／下旬三等份（共 36 欄）時間軸。 */
function buildYearThirdAxis(
  selection: MonthSelection,
  taipeiToday: string,
  monthHolidays: readonly HolidayRow[],
): YearThirdSegment[] {
  const segments: YearThirdSegment[] = [];
  for (let monthNum = 1; monthNum <= 12; monthNum += 1) {
    const finalDay = new Date(Date.UTC(selection.year, monthNum, 0)).getUTCDate();
    const defs: ReadonlyArray<{ label: '上旬' | '中旬' | '下旬'; startDay: number; endDay: number }> = [
      { label: '上旬', startDay: 1, endDay: 10 },
      { label: '中旬', startDay: 11, endDay: 20 },
      { label: '下旬', startDay: 21, endDay: finalDay },
    ];
    defs.forEach((def, idx) => {
      const thirdIndex = idx as 0 | 1 | 2;
      const startDate = isoDate(selection.year, monthNum, def.startDay);
      const endDate = isoDate(selection.year, monthNum, def.endDay);
      const isActiveMonth = monthNum === selection.month;
      const containsToday = isActiveMonth && taipeiToday >= startDate && taipeiToday <= endDate;
      const holidayNames = monthHolidays
        .filter((h) => h.holiday_date >= startDate && h.holiday_date <= endDate)
        .map((h) => `${Number(h.holiday_date.slice(8, 10))}日 ${h.holiday_name}`);
      segments.push({
        key: `${selection.year}-${monthNum}-${thirdIndex}`,
        year: selection.year,
        month: monthNum,
        thirdIndex,
        columnIndex: (monthNum - 1) * 3 + thirdIndex,
        label: def.label,
        monthThirdLabel: `${monthNum}月${def.label}`,
        rangeLabel: `${def.startDay}–${def.endDay}日`,
        startDay: def.startDay,
        endDay: def.endDay,
        startDate,
        endDate,
        isActiveMonth,
        containsToday,
        todayDateStr: containsToday ? taipeiToday : startDate,
        holidayNames,
      });
    });
  }
  return segments;
}

/** 將 YYYY-MM-DD 對應到該年度 36 欄座標軸的百分比位置。 */
function dateToYearAxisPercent(isoDateStr: string, year: number, isEnd: boolean): number {
  const yearStart = `${String(year).padStart(4, '0')}-01-01`;
  const yearEnd = `${String(year).padStart(4, '0')}-12-31`;
  if (isoDateStr < yearStart) return 0;
  if (isoDateStr > yearEnd) return 100;

  const monthNum = Number(isoDateStr.slice(5, 7));
  const day = Number(isoDateStr.slice(8, 10));
  const finalDay = new Date(Date.UTC(year, monthNum, 0)).getUTCDate();

  let thirdIndex = 0;
  let segStartDay = 1;
  let daysInSeg = 10;
  if (day <= 10) {
    thirdIndex = 0;
    segStartDay = 1;
    daysInSeg = 10;
  } else if (day <= 20) {
    thirdIndex = 1;
    segStartDay = 11;
    daysInSeg = 10;
  } else {
    thirdIndex = 2;
    segStartDay = 21;
    daysInSeg = Math.max(1, finalDay - 20);
  }

  const columnIndex = (monthNum - 1) * 3 + thirdIndex;
  const offsetDays = day - segStartDay + (isEnd ? 1 : 0);
  const clampedFraction = Math.max(0, Math.min(1, offsetDays / daysInSeg));
  return ((columnIndex + clampedFraction) / GANTT_TOTAL_THIRDS) * 100;
}

function moveMonth(selection: MonthSelection, offset: number): MonthSelection {
  const target = new Date(Date.UTC(selection.year, selection.month - 1 + offset, 1));
  return { year: target.getUTCFullYear(), month: target.getUTCMonth() + 1 };
}

function renderError(error: SchedulingCurrentError | Error): string {
  if (error instanceof SchedulingCurrentError) {
    const code = error.publicCode ?? error.code;
    const message = error.status === 504 ? '排班查詢的閘道等待後端回應逾時。'
      : error.status === 502 ? '排班查詢的閘道無法取得後端有效回應。' : error.message;
    return `${message}（錯誤代碼：${code}${error.status ? `，HTTP ${error.status}` : ''}）`;
  }
  return error.message;
}

async function loadStaffQueries<T, R>(items: readonly T[], signal: AbortSignal, query: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let nextIndex = 0;
  await Promise.all(Array.from({ length: Math.min(3, items.length) }, async () => {
    while (!signal.aborted && nextIndex < items.length) {
      const index = nextIndex++;
      results[index] = await query(items[index]);
    }
  }));
  return results;
}

function flowStateLabel(state: string): string {
  const labels: Record<string, string> = {
    idle: '尚未查詢',
    query_loading: '正在載入',
    query_ready: '資料已就緒',
    preview_loading: '正在檢查影響',
    preview_ready: '影響已確認',
    apply_pending: '正在套用變更',
    receipt_received: '變更已受理',
    requery_loading: '正在確認最新結果',
    observed: '已完成並確認',
    typed_error: '處理失敗',
    stale: '資料已變更',
    conflict: '資料有衝突',
    outcome_unknown: '結果待確認',
    observation_failed: '最新結果待確認',
  };
  return labels[state] ?? '狀態待確認';
}

function HolidayPolicyWorkspace() {
  const year = taipeiCalendarDate(new Date()).year;
  const [fromDate, setFromDate] = useState(`${year}-01-01`);
  const [toDate, setToDate] = useState(`${year}-12-31`);
  const [action, setAction] = useState<HolidayAction>('upsert');
  const [holidayDate, setHolidayDate] = useState(todayIsoDate());
  const [holidayName, setHolidayName] = useState('');
  const [reason, setReason] = useState('');
  const submittingRef = useRef(false);
  const [holidayDrawerOpen, setHolidayDrawerOpen] = useState(false);
  const [, setStoreRevision] = useState(0);

  useEffect(() => {
    const unsubscribe = holidayFlowStore.subscribe(() => setStoreRevision((value) => value + 1));
    void queryHolidayFlow({ from_date: `${year}-01-01`, to_date: `${year}-12-31` }).catch(() => undefined);
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
  const busy = ['query_loading', 'preview_loading', 'apply_pending', 'receipt_received', 'requery_loading', 'outcome_unknown', 'observation_failed']
    .includes(machine.type);

  const buildPreviewRequest = (
    overrides: Partial<HolidayPreviewRequest> = {},
  ): HolidayPreviewRequest | null => {
    const request: HolidayPreviewRequest = {
      action,
      holiday_date: holidayDate,
      holiday_name: action === 'upsert' ? holidayName.trim() || null : null,
      is_double_pay_default: false,
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
  }, [action, fromDate, holidayDate, holidayName, toDate]);

  const query = () => {
    if (!fromDate || !toDate || fromDate > toDate || busy) return;
    void queryHolidayFlow({ from_date: fromDate, to_date: toDate }).catch(() => undefined);
  };

  const handleOpenEditDrawer = (holiday: HolidayRow) => {
    setAction('upsert');
    setHolidayDate(holiday.holiday_date);
    setHolidayName(holiday.holiday_name);
    setReason('');
    setHolidayDrawerOpen(true);
  };

  const handleOpenAddDrawer = () => {
    setAction('upsert');
    setHolidayDate(todayIsoDate());
    setHolidayName('');
    setReason('');
    setHolidayDrawerOpen(true);
  };

  const apply = async () => {
    const previewRequest = buildPreviewRequest();
    if (!previewRequest || busy || submittingRef.current) return;
    submittingRef.current = true;
    try {
      await queryHolidayFlow({ from_date: previewRequest.from_date!, to_date: previewRequest.to_date! });
      setHolidayDraft(previewRequest);
      const prepared = await previewHolidayFlow(previewRequest);
      const request: HolidayApplyRequest = {
        ...previewRequest,
        is_double_pay_default: prepared.command.is_double_pay_default,
        expected_calendar_version: prepared.command.expected_calendar_version,
        preview_fingerprint: prepared.preview_fingerprint,
        reason: reason.trim(),
      };
      await applyHolidayFlow(request);
    } catch {
      // The flow store retains typed failures and the original command for safe retry.
    } finally {
      submittingRef.current = false;
    }
  };

  const error = draft?.error;
  const errorText = error ? error.message : null;
  useUnsavedDraft('國定假日', { '維護動作': action, '日期': holidayDate, '名稱': holidayName, '原因': reason }, { enabled: holidayDrawerOpen, busy, resetKey: draft?.status === 'observed' ? draft.receipt : null });


  return (
    <section className="holiday-policy-workspace" data-surface-id="scheduling.holiday-policy">
      <header className="holiday-policy-header">
        <div>
          <p className="holiday-policy-kicker">編輯政策 → 儲存 → 查看結果</p>
          <h2>🗓️ 國定假日管理</h2>
          <p>排班前的初始建議預設跳過國定假日；人工已選日期與正式排班維持原安排。</p>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            type="button"
            className="btn-primary-action"
            onClick={handleOpenAddDrawer}
            disabled={busy}
            style={{ padding: '9px 16px', fontSize: '0.88rem', borderRadius: '8px', border: 'none', fontWeight: 700, cursor: 'pointer' }}
          >
            ➕ 新增國定假日
          </button>
          <span className={`holiday-policy-state state-${machine.type}`}>{flowStateLabel(machine.type)}</span>
        </div>
      </header>

      <OfficialHolidayCsvImport disabled={busy} onImported={importYear => {
        setFromDate(`${importYear}-01-01`);
        setToDate(`${importYear}-12-31`);
      }} />

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

      {!holidayDrawerOpen && errorText && <p className="holiday-policy-notice error" role="alert">{errorText}</p>}
      {calendar && (
        <section className="holiday-policy-calendar" aria-label="國定假日日曆">
          <div className="holiday-policy-meta">
            <span>區間：{calendar.planning_horizon.from_date} ～ {calendar.planning_horizon.to_date}</span>
          </div>
          {calendar.holidays.length === 0 ? (
            <p className="holiday-policy-notice">此期間沒有國定假日資料。</p>
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
                  </div>

                  <div>
                    <button
                      type="button"
                      className="scheduling-action"
                      onClick={() => handleOpenEditDrawer(holiday)}
                      disabled={busy}
                      style={{
                        padding: '7px 16px',
                        fontSize: '0.86rem',
                        border: '1px solid',
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
                  <option value="upsert">新增或更新</option>
                  <option value="delete">刪除國定假日</option>
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

            <label style={{ display: 'grid', gap: '6px', fontSize: '0.84rem', fontWeight: 700, color: '#57423b' }}>
              變更原因與審核註記（選填）
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

          {/* 儲存控制列 */}
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button
              type="button"
              className={action === 'delete' ? 'scheduling-danger' : 'scheduling-action'}
              data-control-id="scheduling.holiday.apply"
              disabled={!buildPreviewRequest() || busy}
              onClick={() => void apply()}
              style={{ flex: 1, padding: '10px 16px', fontSize: '0.92rem', borderRadius: '8px', border: 'none', fontWeight: 700, cursor: 'pointer', boxShadow: '0 2px 8px rgba(234, 88, 12, 0.25)' }}
            >
              {busy ? '⏳ 處理中…' : action === 'delete' ? '刪除國定假日' : '儲存國定假日變更'}
            </button>
          </div>

          {calendar && !calendarMatchesHorizon && (
            <small className="holiday-policy-notice">顯示的政策屬於先前查詢區間；儲存時會查詢目前區間的最新政策。</small>
          )}

          {/* Receipt 結果提示 */}
          {draft?.receipt && (
            <section className="holiday-policy-receipt" aria-live="polite" style={{ background: '#ecfdf5', border: '1.5px solid #6ee7b7', borderRadius: '10px', padding: '14px 16px', color: '#065f46' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#047857' }}>
                  國定假日政策已更新
                </h3>
                <button
                  type="button"
                  className="scheduling-action"
                  onClick={() => setHolidayDrawerOpen(false)}
                  style={{ padding: '4px 10px', fontSize: '0.8rem', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
                >
                  關閉抽屜
                </button>
              </div>
              <p style={{ margin: 0, fontSize: '0.84rem' }}>
                {machine.type === 'observed' ? '已重新查詢並確認最新國定假日政策。' : '變更已受理，正在確認最新政策狀態。'}
              </p>
            </section>
          )}

          {errorText && <p className="holiday-policy-notice error" role="alert">{errorText}</p>}
          {machine.type === 'outcome_unknown' && (
            <button type="button" onClick={() => void retryHolidayApplyFlow().catch(() => undefined)}>
              再次確認變更結果
            </button>
          )}
          {machine.type === 'observation_failed' && (
            <button type="button" onClick={() => void retryHolidayObservationFlow().catch(() => undefined)}>
              重新查詢最新政策
            </button>
          )}
        </div>
      </Drawer>
    </section>
  );
}

export type CalendarRowState =
  | {
      kind: 'loaded';
      row: SchedulingCalendarRowViewModel;
      assignments?: readonly SchedulingCurrentAssignment[];
    }
  | { kind: 'empty' }
  | { kind: 'terms_incomplete' }
  | { kind: 'error'; message: string };

interface CalendarCaseOption {
  caseNo: string;
  label: string;
  startDate: string;
  endDate: string;
}

type CalendarCaseOptionsState =
  | { kind: 'loading' }
  | { kind: 'ready'; options: readonly CalendarCaseOption[] }
  | { kind: 'error'; message: string };



type SchedulingDiagnosticTone = 'unavailable' | 'active' | 'waiting' | 'leave';

type EligibilityCollisionState =
  | { kind: 'idle' }
  | { kind: 'loading'; caseNo: string }
  | { kind: 'ready'; data: SchedulingEligibilityCollisionViewModel }
  | { kind: 'error'; message: string };

type CaseEligibilityRowState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: SchedulingEligibilityCollisionViewModel }
  | { kind: 'error'; message: string };

type FullIntervalOutcome =
  | 'available'
  | 'hard_conflict'
  | 'reservation_conflict'
  | 'requires_review'
  | 'checking'
  | 'unknown';

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

function qualificationCheckLabel(code: string): string {
  const labels: Record<string, string> = {
    active_lifecycle: '目前接案狀態',
    service_region: '服務區域',
    cooking_requirement: '下廚需求',
    preferred_service_days: '正式服務天數',
    daily_service_hours: '每日工時',
    service_qualification: '服務資格',
  };
  return labels[code] ?? '媒合條件';
}

function collisionKindLabel(kind: SchedulingEligibilityCollisionViewModel['collisions'][number]['kind']): string {
  const labels: Record<SchedulingEligibilityCollisionViewModel['collisions'][number]['kind'], string> = {
    assignment_interval: '既有指派期間',
    official_schedule: '服務日',
    waiting_deposit_lock: '等待定金確認，檔期暫時保留',
    seven_day_buffer: '7 天排班緩衝期',
    staff_unavailability: '不可服務期間',
    historical_reservation: '歷史預定',
    legacy_schedule: '歷史排班資料',
    data_integrity: '排班資料完整性',
  };
  return labels[kind];
}

function businessSchedulingDetail(detail: string): string {
  return detail.replace(/\blineage\b/gi, '來源關聯');
}

interface SchedulingDiagnosticBadge {
  tone: SchedulingDiagnosticTone;
  text: string;
}

const LOADING_DIAGNOSTIC: SchedulingDiagnosticBadge = {
  tone: 'unavailable',
  text: '⚪ 正在載入排班',
};

const NO_OCCUPANCY_DIAGNOSTIC: SchedulingDiagnosticBadge = {
  tone: 'unavailable',
  text: '⚪ 本月無排班占用',
};
const NO_OCCUPANCY_SLOT_TEXT = '本月無排班占用';

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
    return NO_OCCUPANCY_DIAGNOSTIC;
  }
  if (state.kind === 'terms_incomplete') {
    return { tone: 'waiting', text: '🟡 ⚠️ 時段未確認 (需補齊資料)' };
  }
  if (state.kind === 'error') {
    return { tone: 'unavailable', text: '⚪ 查詢異常／無法判定' };
  }
  const row = state.row;

  // 案件完整檔期由逐人 typed eligibility 結果決定，不由月曆回傳的稀疏日期陣列反推。
  if (ghostConfig?.active && ghostConfig.startDay && ghostConfig.endDay) {
    if (ghostConfig.outcome === 'hard_conflict') return { tone: 'leave', text: '🔴 整段檔期有衝突' };
    if (ghostConfig.outcome === 'reservation_conflict') return { tone: 'waiting', text: '🟡 整段受預約／排班緩衝期影響' };
    if (ghostConfig.outcome === 'available') return { tone: 'active', text: '🟢 完整檔期可排' };
    if (ghostConfig.outcome === 'checking') return { tone: 'unavailable', text: '⚪ 正在確認整段檔期' };
    return { tone: 'unavailable', text: '⚪ 整段檔期待確認' };
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
    return { tone: 'waiting', text: '🔵 等待定金確認，檔期暫時保留' };
  }
  if (hasBuffer) {
    return { tone: 'waiting', text: '🟡 7 天排班緩衝期' };
  }
  if (hasUnknownOfficialWorkday) {
    return { tone: 'waiting', text: '⚠️ 服務狀態未知／資料待補正' };
  }
  if (hasCompletedAssignment || hasActive) {
    return { tone: 'active', text: '⚪ 服務已完成' };
  }
  return NO_OCCUPANCY_DIAGNOSTIC;
}

export interface GhostProjectionConfig {
  active: boolean;
  caseNo: string;
  year: number;
  month: number;
  startDay: number;
  endDay: number;
  fullStartDate: string;
  fullEndDate: string;
  outcome: FullIntervalOutcome;
}

function fullIntervalOutcome(state: CaseEligibilityRowState | undefined): FullIntervalOutcome {
  if (!state || state.kind === 'loading') return 'checking';
  if (state.kind === 'error') return 'unknown';
  const hardCollisions = state.data.collisions.filter((collision) => collision.severity === 'hard_block');
  const reservationKinds = new Set(['waiting_deposit_lock', 'seven_day_buffer']);
  if (hardCollisions.some((collision) => !reservationKinds.has(collision.kind))) return 'hard_conflict';
  if (hardCollisions.length > 0) return 'reservation_conflict';
  if (state.data.availability === 'blocked') return 'hard_conflict';
  if (
    state.data.availability === 'requires_review'
    || state.data.availability === 'unknown'
    || state.data.coverage.status !== 'complete'
  ) return 'requires_review';
  return 'available';
}

function visibleCaseInterval(
  option: CalendarCaseOption | undefined,
  selection: MonthSelection,
): Pick<GhostProjectionConfig, 'year' | 'month' | 'startDay' | 'endDay' | 'fullStartDate' | 'fullEndDate'> | null {
  if (!option) return null;
  const range = monthRange(selection);
  if (option.endDate < range.rangeStart || option.startDate > range.rangeEnd) return null;
  const visibleStart = option.startDate < range.rangeStart ? range.rangeStart : option.startDate;
  const visibleEnd = option.endDate > range.rangeEnd ? range.rangeEnd : option.endDate;
  return {
    year: selection.year,
    month: selection.month,
    startDay: Number(visibleStart.slice(8, 10)),
    endDay: Number(visibleEnd.slice(8, 10)),
    fullStartDate: option.startDate,
    fullEndDate: option.endDate,
  };
}

// 動態將 Server 天數投影合併為連續甘特區間條塊（支援跨月全期展示與 Ghost Projection 幽靈透視）
interface OrderSummaryInfo {
  clientName: string;
  startDate: string | null;
  endDate: string | null;
}

interface SpanEnrichmentContext {
  year: number;
  month: number;
  orderSummariesByCaseNo: Record<string, OrderSummaryInfo>;
  staffAssignments: readonly StaffAssignmentOption[];
  projectionAssignments: readonly SchedulingCurrentAssignment[];
}

interface GanttSpan {
  id: string;
  startDay: number;
  endDay: number;
  visualStartDate: string;
  visualEndDate: string;
  tone: 'active' | 'rest' | 'buffer' | 'leave' | 'waiting' | 'available' | 'unavailable' | 'conflict' | 'deposit-conflict' | 'free' | 'historical';
  icon?: string;
  clientName?: string;
  caseText: string;
  dateRangeText?: string;
  dailyTimeText?: string;
  statusLabel?: string;
  historicalCaseDates?: string;
  lane?: number;
  shift?: StaffMonthlySchedule['days'][number];
}

interface OrderServiceRange {
  start: string;
  end: string;
}

interface HistoricalCaseRanges {
  planned: OrderServiceRange | null;
  service: OrderServiceRange | null;
}

function orderServiceRange(start: string | null, end: string | null): OrderServiceRange | null {
  return start && end && start <= end ? { start, end } : null;
}

async function loadHistoricalCaseRanges(caseNo: string, signal: AbortSignal): Promise<HistoricalCaseRanges | null> {
  try {
    const order = await ordersQueryClient.getOrderDetail(caseNo, { signal });
    return {
      planned: orderServiceRange(order.start_date, order.end_date),
      service: orderServiceRange(order.actual_start_date ?? order.start_date, order.actual_end_date ?? order.end_date),
    };
  } catch {
    return null;
  }
}

function resolveOrderSpanEnrichment(
  caseNo: string | null | undefined,
  assignmentId: number | null | undefined,
  spanStartDate: string,
  spanEndDate: string,
  context?: SpanEnrichmentContext,
): {
  clientName?: string;
  fullStartDate: string;
  fullEndDate: string;
  dateRangeText: string;
  dailyTimeText?: string;
} {
  if (!context || !caseNo) {
    return {
      fullStartDate: spanStartDate,
      fullEndDate: spanEndDate,
      dateRangeText: spanStartDate === spanEndDate ? spanStartDate : `${spanStartDate} ～ ${spanEndDate}`,
    };
  }
  const optAssign = context.staffAssignments.find(
    (item) => item.case_no === caseNo && (assignmentId == null || item.id === assignmentId),
  );
  const projAssign = context.projectionAssignments.find(
    (item) => item.case_no === caseNo && (assignmentId == null || item.assignment_id === assignmentId),
  );
  const summary = context.orderSummariesByCaseNo[caseNo];
  const caseDates = assignmentId == null ? summary : undefined;

  const fullStartDate =
    (assignmentId == null ? optAssign?.actual_start_date : undefined)
    ?? optAssign?.assigned_start_date
    ?? caseDates?.startDate
    ?? projAssign?.assigned_start_date
    ?? spanStartDate;
  const fullEndDate =
    (assignmentId == null ? optAssign?.actual_end_date : undefined)
    ?? optAssign?.assigned_end_date
    ?? caseDates?.endDate
    ?? projAssign?.assigned_end_date
    ?? spanEndDate;
  const dateRangeText = fullStartDate === fullEndDate
    ? fullStartDate
    : `${fullStartDate} ～ ${fullEndDate}`;

  const firstTime = projAssign?.first_service_at?.slice(11, 16);
  const endTime = projAssign?.completion_at?.slice(11, 16);
  const dailyTimeText = firstTime && endTime
    ? (projAssign?.actual_hours === 24 && firstTime === endTime
      ? `${firstTime}–翌日${endTime} (24H)`
      : `${firstTime}–${endTime}`)
    : undefined;

  return {
    clientName: summary?.clientName,
    fullStartDate,
    fullEndDate,
    dateRangeText,
    dailyTimeText,
  };
}

function assignNonOverlappingLanes(spans: GanttSpan[]): GanttSpan[] {
  const occupiedByLane: Array<Array<{ start: string; end: string }>> = [];
  return spans.map((span) => {
    if (span.lane !== undefined) {
      while (occupiedByLane.length <= span.lane) occupiedByLane.push([]);
      occupiedByLane[span.lane].push({ start: span.visualStartDate, end: span.visualEndDate });
      return span;
    }
    let assignedLane = 0;
    while (assignedLane < occupiedByLane.length) {
      const hasOverlap = occupiedByLane[assignedLane].some(
        (slot) => span.visualStartDate <= slot.end && span.visualEndDate >= slot.start,
      );
      if (!hasOverlap) break;
      assignedLane += 1;
    }
    if (!occupiedByLane[assignedLane]) occupiedByLane[assignedLane] = [];
    occupiedByLane[assignedLane].push({ start: span.visualStartDate, end: span.visualEndDate });
    return { ...span, lane: assignedLane };
  });
}

function showHistoricalCaseRanges(spans: GanttSpan[], ranges?: ReadonlyMap<string, HistoricalCaseRanges | null>): GanttSpan[] {
  const positioned: GanttSpan[] = [];
  const completeCases = new Map<string, GanttSpan>();
  for (const span of spans) {
    if (span.tone !== 'historical') {
      positioned.push(span);
      continue;
    }
    const reservation = span.shift?.status === 'historical_reservation';
    const caseRanges = ranges?.get(span.caseText);
    const range = reservation ? caseRanges?.planned : caseRanges?.service;
    if (!range) {
      positioned.push({ ...span, historicalCaseDates: '整案日期不可用', dateRangeText: '整案日期不可用' });
      continue;
    }
    const key = `${reservation ? 'reservation' : 'assignment'}:${span.caseText}`;
    const previous = completeCases.get(key);
    if (previous) {
      if (previous.dailyTimeText !== span.dailyTimeText) previous.dailyTimeText = undefined;
      continue;
    }
    const text = range.start === range.end ? range.start : `${range.start} ～ ${range.end}`;
    completeCases.set(key, {
      ...span,
      visualStartDate: range.start,
      visualEndDate: range.end,
      historicalCaseDates: text,
      dateRangeText: text,
      lane: undefined,
    });
  }
  return assignNonOverlappingLanes([...positioned, ...completeCases.values()]);
}

function monthlyShiftSpans(
  schedule: StaffMonthlySchedule,
  context?: SpanEnrichmentContext,
): GanttSpan[] {
  const sortedDays = [...schedule.days].sort((a, b) => a.work_date.localeCompare(b.work_date));
  const spans: GanttSpan[] = [];
  const activeOrderSpans = new Map<string, GanttSpan>();
  const previous = new Map<string, GanttSpan>();
  const lanes = new Map<number, number>();
  const tones = {
    working: 'active',
    resting: 'active',
    historical_assignment: 'historical',
    historical_reservation: 'historical',
    waiting_deposit_lock: 'waiting',
    staff_unavailability: 'leave',
    buffer: 'buffer',
  } as const;
  const labels = {
    working: '排班',
    resting: '排班',
    historical_assignment: '歷史指派',
    historical_reservation: '歷史預定',
    waiting_deposit_lock: '等待訂金',
    staff_unavailability: '不可服務',
    buffer: '緩衝提醒',
  } as const;

  for (const shift of sortedDays) {
    if (shift.status === 'available') continue;
    const day = Number(shift.work_date.slice(8));
    const isHistorical = tones[shift.status] === 'historical';
    const continuation = !!shift.service_date && shift.service_date !== shift.work_date;
    const orderKey = shift.case_no || shift.assignment_id
      ? `${shift.case_no ?? ''}#${shift.assignment_id ?? ''}`
      : null;

    // 合併正式跨日續班與同案排休日，歷史續班另列。
    if (orderKey && !isHistorical && (continuation || shift.status === 'resting')) {
      const existing = activeOrderSpans.get(orderKey);
      if (existing && (existing.endDay >= day - 1)) {
        existing.endDay = Math.max(existing.endDay, day);
        if (shift.work_date > existing.visualEndDate
          && (shift.assignment_id != null || !context?.orderSummariesByCaseNo[shift.case_no ?? '']?.endDate)) {
          existing.visualEndDate = shift.work_date;
          existing.dateRangeText = existing.visualStartDate === existing.visualEndDate
            ? existing.visualStartDate
            : `${existing.visualStartDate} ～ ${existing.visualEndDate}`;
        }
        continue;
      }
    }

    const lane = lanes.get(day) ?? 0;
    lanes.set(day, lane + 1);

    const time = shift.service_hours_override
      ? `${shift.service_hours_override} 小時・${coordinatedServiceTime}`
      : shift.starts_at && shift.ends_at
      ? `${continuation ? '00:00' : shift.starts_at.slice(11, 16)}–${shift.ends_at.slice(0, 10) > shift.work_date ? '翌日' : ''}${shift.ends_at.slice(11, 16)}${continuation ? ' 續班' : ''}`
      : ['working', 'historical_assignment', 'waiting_deposit_lock'].includes(shift.status) ? '時段未確認' : '';

    const key = [shift.case_no, shift.assignment_id, shift.lock_id, shift.unavailability_block_id, shift.status, lane, time].join(':');
    const prior = previous.get(key);
    if (prior?.endDay === day - 1) {
      prior.endDay = day;
      if (shift.work_date > prior.visualEndDate
        && (isHistorical || shift.assignment_id != null || !context?.orderSummariesByCaseNo[shift.case_no ?? '']?.endDate)) {
        prior.visualEndDate = shift.work_date;
        prior.dateRangeText = prior.visualStartDate === prior.visualEndDate
          ? prior.visualStartDate
          : `${prior.visualStartDate} ～ ${prior.visualEndDate}`;
      }
      continue;
    }

    const enrichment = resolveOrderSpanEnrichment(
      shift.case_no,
      shift.assignment_id,
      shift.work_date,
      shift.work_date,
      context,
    );
    const useFullRange = shift.case_no && (shift.status === 'working' || shift.status === 'resting' || shift.status === 'waiting_deposit_lock');
    const icon = shift.status === 'working' || shift.status === 'resting'
      ? '🟢'
      : shift.status === 'waiting_deposit_lock'
        ? '🔵'
        : shift.status === 'staff_unavailability'
          ? '🟣'
          : shift.status === 'buffer'
            ? '🔒'
            : '🕘';

    const span: GanttSpan = {
      id: `${key}:${day}`,
      startDay: day,
      endDay: day,
      visualStartDate: useFullRange ? enrichment.fullStartDate : shift.work_date,
      visualEndDate: useFullRange ? enrichment.fullEndDate : shift.work_date,
      lane,
      icon,
      tone: tones[shift.status],
      clientName: enrichment.clientName ?? shift.client_name ?? undefined,
      caseText: shift.case_no || labels[shift.status],
      dateRangeText: isHistorical ? shift.work_date : enrichment.dateRangeText,
      dailyTimeText: time || enrichment.dailyTimeText,
      statusLabel: labels[shift.status],
      shift,
    };
    spans.push(span);
    previous.set(key, span);
    if (orderKey && (shift.status === 'working' || shift.status === 'resting')) {
      activeOrderSpans.set(orderKey, span);
    }
  }
  return spans;
}

function caseShiftSpans(config: GhostProjectionConfig, state: CaseEligibilityRowState | undefined, lane: number, month: string): GanttSpan[] {
  const result: GanttSpan[] = [];
  for (let day = config.startDay; day <= config.endDay; day += 1) {
    let outcome = config.outcome;
    if (state?.kind === 'ready') {
      const date = `${month}-${String(day).padStart(2, '0')}`;
      const blocked = state.data.coverage.missing_dates.includes(date)
        || state.data.collisions.some(item => item.severity === 'hard_block' && item.collision_date === date);
      const review = state.data.coverage.review_dates.includes(date);
      if (blocked) outcome = 'hard_conflict';
      else if (review || state.data.availability === 'requires_review') outcome = 'requires_review';
      else if (state.data.availability === 'available' || state.data.coverage.missing_dates.length > 0) outcome = 'available';
      else if (state.data.availability === 'blocked') outcome = 'requires_review';
    }
    const dayIso = `${month}-${String(day).padStart(2, '0')}`;
    const prior = result.at(-1);
    const span = ghostCaseSpan({ ...config, outcome }, day, day, month);
    if (prior?.tone === span.tone) {
      prior.endDay = day;
      prior.visualEndDate = dayIso;
    } else {
      result.push({
        ...span,
        lane,
        visualStartDate: dayIso,
        visualEndDate: dayIso,
        dateRangeText: `${config.fullStartDate} ～ ${config.fullEndDate}`,
        caseText: `${config.caseNo} · ${{ available: '可排', hard_conflict: '時段衝突', reservation_conflict: '時段衝突', requires_review: '時段待確認', checking: '確認中', unknown: '時段待確認' }[outcome]}`,
        statusLabel: undefined,
      });
    }
  }
  return result;
}

function ghostCaseSpan(
  config: GhostProjectionConfig,
  startDay: number,
  endDay: number,
  monthStr?: string,
): GanttSpan {
  const ym = monthStr ?? `${config.year}-${String(config.month).padStart(2, '0')}`;
  const visualStartDate = `${ym}-${String(startDay).padStart(2, '0')}`;
  const visualEndDate = `${ym}-${String(endDay).padStart(2, '0')}`;
  const common = {
    startDay,
    endDay,
    visualStartDate,
    visualEndDate,
    dateRangeText: `${config.fullStartDate} ～ ${config.fullEndDate}`,
  };
  if (config.outcome === 'hard_conflict') {
    return {
      ...common,
      id: `ghost-conflict-${startDay}-${endDay}`,
      tone: 'conflict',
      icon: '⚠️',
      caseText: '整段檔期有衝突',
      statusLabel: `案件 ${config.caseNo} 完整檔期 ${config.fullStartDate} ～ ${config.fullEndDate} 均標示衝突`,
    };
  }
  if (config.outcome === 'reservation_conflict') {
    return {
      ...common,
      id: `ghost-reservation-conflict-${startDay}-${endDay}`,
      tone: 'deposit-conflict',
      icon: '⚠️',
      caseText: '整段檔期受預約／排班緩衝期影響',
      statusLabel: `案件 ${config.caseNo} 完整檔期 ${config.fullStartDate} ～ ${config.fullEndDate} 均標示受影響`,
    };
  }
  if (config.outcome === 'available') {
    return {
      ...common,
      id: `ghost-free-${startDay}-${endDay}`,
      tone: 'free',
      icon: '✨',
      caseText: `檔期完全空閒：預估 ${endDay - startDay + 1} 日完工`,
      statusLabel: `案件 ${config.caseNo} 完整檔期可排`,
    };
  }
  return {
    ...common,
    id: `ghost-unavailable-${startDay}-${endDay}`,
    tone: 'unavailable',
    icon: '⏳',
    caseText: config.outcome === 'checking' ? '正在確認整段檔期' : '整段檔期待確認',
    statusLabel: config.outcome === 'unknown'
      ? `案件 ${config.caseNo} 完整檔期查詢失敗，未推定可排`
      : `案件 ${config.caseNo} 完整檔期尚未能判定`,
  };
}

function buildGanttSpans(
  state: CalendarRowState | undefined,
  totalDays: number,
  ghostConfig?: GhostProjectionConfig | null,
  historicalOverlays: readonly HistoricalAssignmentOverlay[] = [],
  context?: SpanEnrichmentContext,
): GanttSpan[] {
  const ymFallback = context
    ? `${String(context.year).padStart(4, '0')}-${String(context.month).padStart(2, '0')}`
    : `${taipeiCalendarDate(new Date()).year}-${String(taipeiCalendarDate(new Date()).month).padStart(2, '0')}`;
  const mapHistoricalOverlay = (overlay: HistoricalAssignmentOverlay, startDay: number, endDay: number): GanttSpan => ({
    id: `historical-${overlay.assignmentId}-${startDay}`,
    startDay,
    endDay,
    visualStartDate: startDay === Number(overlay.startDate.slice(8, 10)) && endDay === Number(overlay.endDate.slice(8, 10))
      ? overlay.startDate
      : `${ymFallback}-${String(startDay).padStart(2, '0')}`,
    visualEndDate: startDay === Number(overlay.startDate.slice(8, 10)) && endDay === Number(overlay.endDate.slice(8, 10))
      ? overlay.endDate
      : `${ymFallback}-${String(endDay).padStart(2, '0')}`,
    tone: 'historical',
    icon: '🕘',
    clientName: overlay.clientName,
    caseText: overlay.caseNo,
    dateRangeText: overlay.startDate === overlay.endDate ? overlay.startDate : `${overlay.startDate} ～ ${overlay.endDate}`,
    statusLabel: '歷史指派區間（不計入工時）',
  });

  if (state?.kind === 'empty') {
    if (ghostConfig?.active && ghostConfig.startDay && ghostConfig.endDay) {
      const start = Math.max(1, ghostConfig.startDay);
      const end = Math.min(totalDays, ghostConfig.endDay);
      return [ghostCaseSpan(ghostConfig, start, end)];
    }
    return assignNonOverlappingLanes(historicalOverlays.map((overlay) =>
      mapHistoricalOverlay(overlay, Number(overlay.startDate.slice(8, 10)), Number(overlay.endDate.slice(8, 10))),
    ));
  }

  if (!state || state.kind === 'terms_incomplete' || state.kind === 'error') {
    return assignNonOverlappingLanes(historicalOverlays.map((overlay) =>
      mapHistoricalOverlay(overlay, Number(overlay.startDate.slice(8, 10)), Number(overlay.endDate.slice(8, 10))),
    ));
  }

  const row = state.row;
  const spans: GanttSpan[] = [];
  let current: GanttSpan | null = null;
  let currentCaseNo: string | null = null;

  const finalizeCurrentSpan = (span: GanttSpan, caseNo: string | null) => {
    const enrichment = resolveOrderSpanEnrichment(
      caseNo,
      null,
      span.visualStartDate,
      span.visualEndDate,
      context,
    );
    const shouldExpandCrossMonth = caseNo !== null && (span.tone === 'active' || span.tone === 'waiting');
    spans.push({
      ...span,
      clientName: enrichment.clientName,
      dateRangeText: enrichment.dateRangeText,
      dailyTimeText: enrichment.dailyTimeText,
      visualStartDate: shouldExpandCrossMonth ? enrichment.fullStartDate : span.visualStartDate,
      visualEndDate: shouldExpandCrossMonth ? enrichment.fullEndDate : span.visualEndDate,
    });
  };

  row.days.forEach((day, index) => {
    const dayNum = index + 1;
    const isOccupied = day.occupancyKinds.length > 0;
    const primaryCaseNo = day.caseLabels.length === 1 ? day.caseLabels[0] : null;
    const isRestMergedIntoOrder = day.tone === 'rest'
      && day.caseLabels.length > 0
      && !day.occupancyKinds.includes('staff_unavailability')
      && !day.occupancyKinds.includes('assignment_buffer');

    const tone: GanttSpan['tone'] = isRestMergedIntoOrder
      ? 'active'
      : day.tone === 'rest'
        ? (day.assignmentStatuses.includes('active') ? 'rest' : 'active')
        : day.tone;
    const caseText = day.caseLabels.join('、') || (isOccupied ? day.statusLabel : NO_OCCUPANCY_SLOT_TEXT);
    const mergedOrderLabel = day.assignmentStatuses.includes('completed')
      ? '服務已結束'
      : day.assignmentStatuses.includes('active')
        ? '服務中'
        : day.assignmentStatuses.includes('planned')
          ? '已排定服務'
          : day.statusLabel;
    const statusLabel = day.caseLabels.length > 0
      ? (isRestMergedIntoOrder ? mergedOrderLabel : day.statusLabel)
      : undefined;
    const icon: string | undefined = tone === 'active'
      ? '🟢'
      : tone === 'rest'
        ? '🔴'
        : tone === 'buffer'
          ? '🔒'
          : tone === 'leave'
            ? '🚑'
            : tone === 'waiting'
              ? '🔵'
              : undefined;

    if (!current) {
      if (isOccupied) {
        current = {
          id: `span-${dayNum}`,
          startDay: dayNum,
          endDay: dayNum,
          visualStartDate: day.date,
          visualEndDate: day.date,
          tone,
          icon,
          caseText,
          statusLabel,
        };
        currentCaseNo = primaryCaseNo;
      }
    } else if (
      current.tone === tone
      && current.caseText === caseText
      && current.statusLabel === statusLabel
    ) {
      current.endDay = dayNum;
      current.visualEndDate = day.date;
    } else {
      finalizeCurrentSpan(current, currentCaseNo);
      if (isOccupied) {
        current = {
          id: `span-${dayNum}`,
          startDay: dayNum,
          endDay: dayNum,
          visualStartDate: day.date,
          visualEndDate: day.date,
          tone,
          icon,
          caseText,
          statusLabel,
        };
        currentCaseNo = primaryCaseNo;
      } else {
        current = null;
        currentCaseNo = null;
      }
    }
  });

  if (current) {
    finalizeCurrentSpan(current, currentCaseNo);
  }

  if (ghostConfig?.active && ghostConfig.startDay && ghostConfig.endDay) {
    spans.push(ghostCaseSpan(ghostConfig, ghostConfig.startDay, ghostConfig.endDay));
  }

  const canonicalDays = new Set<number>();
  spans.filter((span) => span.tone !== 'historical').forEach((span) => {
    for (let day = span.startDay; day <= span.endDay; day += 1) canonicalDays.add(day);
  });
  historicalOverlays.forEach((overlay) => {
    const startDay = Number(overlay.startDate.slice(8, 10));
    const endDay = Number(overlay.endDate.slice(8, 10));
    let segmentStart: number | null = null;
    for (let day = startDay; day <= endDay + 1; day += 1) {
      const canRender = day <= endDay && !canonicalDays.has(day);
      if (canRender && segmentStart == null) segmentStart = day;
      if (!canRender && segmentStart != null) {
        const segmentEnd = day - 1;
        spans.push(mapHistoricalOverlay(overlay, segmentStart, segmentEnd));
        segmentStart = null;
      }
    }
  });

  return assignNonOverlappingLanes(spans);
}

const SchedulingWorkbench: React.FC = () => {
  const { requestLeave } = useUnsavedNavigation();
  const [activeTab, setActiveTab] = useState<SchedulingTab>('calendar');
  const [staffList, setStaffList] = useState<StaffDirectoryCardViewModel[]>([]);
  const [directoryLoading, setDirectoryLoading] = useState<boolean>(true);
  const [directoryError, setDirectoryError] = useState<string | null>(null);
  const [directoryNextCursor, setDirectoryNextCursor] = useState<number | null>(null);
  const [directoryLoadingMore, setDirectoryLoadingMore] = useState(false);
  const [directoryNextPageError, setDirectoryNextPageError] = useState<string | null>(null);

  const [selectedStaffId, setSelectedStaffId] = useState<number | null>(null);
  const [month, setMonth] = useState<MonthSelection>(currentMonth);
  const [monthHolidays, setMonthHolidays] = useState<readonly HolidayRow[]>([]);
  const [holidayLoading, setHolidayLoading] = useState(true);
  const [holidayError, setHolidayError] = useState<string | null>(null);
  const [holidayReload, setHolidayReload] = useState(0);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [searchKeyword, setSearchKeyword] = useState<string>('');

  const [calendarRows, setCalendarRows] = useState<Record<number, CalendarRowState>>({});
  const [historicalOverlaysByStaff, setHistoricalOverlaysByStaff] = useState<Record<number, HistoricalAssignmentOverlay[]>>({});
  const [monthlyRowsByStaff, setMonthlyRowsByStaff] = useState<Record<number, StaffMonthlySchedule | undefined>>({});
  const [historicalRangesByStaff, setHistoricalRangesByStaff] = useState<Record<number, ReadonlyMap<string, HistoricalCaseRanges | null>>>({});
  const [orderSummariesByCaseNo, setOrderSummariesByCaseNo] = useState<Record<string, OrderSummaryInfo>>({});
  const [selectedShift, setSelectedShift] = useState<GanttSpan | null>(null);
  const [historicalOverlayErrors, setHistoricalOverlayErrors] = useState<Record<number, string>>({});
  const [calendarLoading, setCalendarLoading] = useState<boolean>(false);
  const [calendarError, setCalendarError] = useState<Error | null>(null);
  const [retryGeneration, setRetryGeneration] = useState<number>(0);
  const [availabilityRevision, setAvailabilityRevision] = useState(0);
  const [eligibilityCaseNo, setEligibilityCaseNo] = useState('');
  const [eligibilityState, setEligibilityState] = useState<EligibilityCollisionState>({ kind: 'idle' });
  const [collisionDrawerOpen, setCollisionDrawerOpen] = useState(false);

  // 🔮 洽談案件幽靈投影 (Ghost Projection) 狀態：預設沒有選擇案件
  const [selectedCaseNo, setSelectedCaseNo] = useState('');
  const [caseOptionsState, setCaseOptionsState] = useState<CalendarCaseOptionsState>({ kind: 'loading' });
  const [caseEligibilityRows, setCaseEligibilityRows] = useState<Record<number, CaseEligibilityRowState>>({});
  const [caseOptionsRetryGeneration, setCaseOptionsRetryGeneration] = useState(0);
  const [candidatePoolAdding, setCandidatePoolAdding] = useState<boolean>(false);
  const [candidatePoolSuccess, setCandidatePoolSuccess] = useState<string | null>(null);
  const [candidatePoolError, setCandidatePoolError] = useState<string | null>(null);

  const mountedRef = useRef(true);
  const directoryControllerRef = useRef<AbortController | null>(null);
  const directoryPendingCursorRef = useRef<number | null>(null);
  const directorySentinelRef = useRef<HTMLDivElement | null>(null);
  const calendarHeaderScrollRef = useRef<HTMLDivElement | null>(null);
  const calendarBodyScrollRef = useRef<HTMLDivElement | null>(null);
  const [pendingTodayScroll, setPendingTodayScroll] = useState(false);
  const [scrollLeftValue, setScrollLeftValue] = useState(0);
  const [scrollMetrics, setScrollMetrics] = useState<{ max: number; thumbWidth: number; clientTimelineWidth: number; measuredZeroOverflow: boolean }>({
    max: GANTT_TOTAL_THIRDS * GANTT_THIRD_COL_WIDTH,
    thumbWidth: 160,
    clientTimelineWidth: 1200,
    measuredZeroOverflow: false,
  });
  const calendarControllerRef = useRef<AbortController | null>(null);
  const caseOptionsControllerRef = useRef<AbortController | null>(null);
  const assignmentOptionsByStaffRef = useRef(new Map<number, readonly StaffAssignmentOption[]>());
  const calendarLoadedKeyRef = useRef<Map<number, string>>(new Map());
  const calendarRetryStaffIdsRef = useRef<Set<number>>(new Set());
  const eligibilityControllerRef = useRef<AbortController | null>(null);
  const caseEligibilityControllerRef = useRef<AbortController | null>(null);

  useEffect(() => subscribeStaffAvailabilityChanges(staffId => {
    if (!staffList.some(staff => staff.id === staffId)) return;
    calendarControllerRef.current?.abort();
    calendarLoadedKeyRef.current.delete(staffId);
    setCalendarRows(current => {
      const next = { ...current };
      delete next[staffId];
      return next;
    });
    setAvailabilityRevision(revision => revision + 1);
  }), [staffList]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      directoryControllerRef.current?.abort();
      directoryPendingCursorRef.current = null;
      calendarControllerRef.current?.abort();
      caseOptionsControllerRef.current?.abort();
      eligibilityControllerRef.current?.abort();
      caseEligibilityControllerRef.current?.abort();
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
    setDirectoryLoadingMore(false);
    directoryPendingCursorRef.current = null;

    try {
      const page = adaptStaffDirectoryPage(
        await loadAllStaffDirectoryPages(
          staffDirectoryClient.queryPage.bind(staffDirectoryClient),
          { pageSize: STAFF_PAGE_SIZE, lifecycleState: 'active' },
          { signal: controller.signal }
        )
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      const sortedStaff = [...page.items].sort(compareStaffUnionNumbers);
      setStaffList(sortedStaff);
      setDirectoryNextCursor(page.nextCursor);
      if (page.items.length > 0) {
        setSelectedStaffId(sortedStaff[0].id);
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

  const loadNextDirectoryPage = useCallback(async () => {
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
          { pageSize: STAFF_PAGE_SIZE, afterId: cursor, lifecycleState: 'active' },
          { signal: controller.signal }
        )
      );
      if (!mountedRef.current || controller.signal.aborted || directoryPendingCursorRef.current !== cursor) return;
      setStaffList((current) => {
        const byId = new Map(current.map((staff) => [staff.id, staff]));
        page.items.forEach((staff) => byId.set(staff.id, staff));
        return [...byId.values()].sort(compareStaffUnionNumbers);
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
  }, [directoryNextCursor]);

  useEffect(() => {
    const sentinel = directorySentinelRef.current;
    if (activeTab !== 'calendar' || !sentinel || directoryLoading || directoryLoadingMore
      || directoryNextPageError || directoryNextCursor === null) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadNextDirectoryPage();
    }, { rootMargin: '0px 0px 240px 0px' });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [activeTab, directoryLoading, directoryLoadingMore, directoryNextPageError, directoryNextCursor, loadNextDirectoryPage]);

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

  useEffect(() => {
    caseOptionsControllerRef.current?.abort();
    if (staffList.length === 0) {
      setCaseOptionsState(directoryLoading ? { kind: 'loading' } : { kind: 'ready', options: [] });
      return undefined;
    }
    const controller = new AbortController();
    caseOptionsControllerRef.current = controller;
    setCaseOptionsState({ kind: 'loading' });

    const loadOptions = async () => {
      try {
        const [summaryPage, coreStagePage] = await Promise.all([
          loadAllOrderSummaries(
            ordersQueryClient.getOrderSummaries.bind(ordersQueryClient),
            { page_size: 200, lifecycle_scope: 'unfinished' },
            { signal: controller.signal },
          ),
          loadAllCoreStageTimelines(
            { workbench_scope: 'in_progress', page_size: 200 },
            { signal: controller.signal },
          ),
          loadStaffQueries(staffList, controller.signal, async (staff) => {
            const cached = assignmentOptionsByStaffRef.current.get(staff.id);
            if (cached) return cached;
            const assignments = await staffAssignmentOptionsClient.getStaffAssignmentOptions(
              staff.id,
              { signal: controller.signal },
            );
            assignmentOptionsByStaffRef.current.set(staff.id, assignments);
            return assignments;
          }),
        ]);
        if (!mountedRef.current || controller.signal.aborted) return;
        const nextOrderSummaries: Record<string, OrderSummaryInfo> = {};
        summaryPage.items.forEach((summary) => {
          nextOrderSummaries[summary.case_no] = {
            clientName: summary.client_name,
            startDate: summary.actual_start_date ?? summary.start_date,
            endDate: summary.actual_end_date ?? summary.end_date,
          };
        });
        setOrderSummariesByCaseNo(nextOrderSummaries);
        const preDepositCaseNos = new Set(
          coreStagePage.items
            .filter((timeline) => (
              timeline.current_core_stage_ordinal !== null
              && timeline.current_core_stage_ordinal < 8
            ))
            .map((timeline) => timeline.case_no),
        );
        const options = summaryPage.items
          .filter((summary) => (
            preDepositCaseNos.has(summary.case_no)
            && summary.start_date !== null
            && summary.end_date !== null
          ))
          .map((summary) => ({
            caseNo: summary.case_no,
            label: `${summary.case_no}｜${summary.client_name}${summary.start_date ? `｜${summary.start_date}` : ''}`,
            startDate: summary.start_date!,
            endDate: summary.end_date!,
          }));
        setCaseOptionsState({ kind: 'ready', options });
      } catch (error) {
        if (!mountedRef.current || controller.signal.aborted) return;
        setCaseOptionsState({
          kind: 'error',
          message: error instanceof Error ? error.message : '排查案件選項載入失敗',
        });
      }
    };

    queueMicrotask(() => void loadOptions());
    return () => controller.abort();
  }, [caseOptionsRetryGeneration, directoryLoading, staffList]);

  useEffect(() => {
    if (activeTab !== 'calendar') return;
    if (caseOptionsState.kind !== 'ready' || !selectedCaseNo.trim()) return;
    if (caseOptionsState.options.some((option) => option.caseNo === selectedCaseNo.trim())) return;
    eligibilityControllerRef.current?.abort();
    setSelectedCaseNo('');
    setEligibilityCaseNo('');
    setEligibilityState({ kind: 'idle' });
  }, [activeTab, caseOptionsState, selectedCaseNo]);

  useEffect(() => {
    caseEligibilityControllerRef.current?.abort();
    const caseNo = selectedCaseNo.trim();
    if (!caseNo || staffList.length === 0) {
      setCaseEligibilityRows({});
      return undefined;
    }
    const controller = new AbortController();
    caseEligibilityControllerRef.current = controller;
    setCaseEligibilityRows(Object.fromEntries(
      staffList.map((staff) => [staff.id, { kind: 'loading' } satisfies CaseEligibilityRowState]),
    ));

    const loadCaseEligibility = async () => {
      const results = await loadStaffQueries(staffList, controller.signal, async (staff) => {
        try {
          const projection = await schedulingEligibilityCollisionClient.query(
            { caseNo, staffId: staff.id, asOf: todayIsoDate() },
            { signal: controller.signal },
          );
          return {
            staffId: staff.id,
            state: { kind: 'ready', data: adaptSchedulingEligibilityCollision(projection) } satisfies CaseEligibilityRowState,
          };
        } catch (error) {
          return {
            staffId: staff.id,
            state: { kind: 'error', message: eligibilityErrorMessage(error) } satisfies CaseEligibilityRowState,
          };
        }
      });
      if (!mountedRef.current || controller.signal.aborted) return;
      setCaseEligibilityRows(Object.fromEntries(results.map((result) => [result.staffId, result.state])));
    };

    queueMicrotask(() => void loadCaseEligibility());
    return () => controller.abort();
  }, [selectedCaseNo, staffList, availabilityRevision]);

  const range = useMemo(() => monthRange(month), [month]);

  useEffect(() => {
    if (activeTab !== 'calendar') return;
    const controller = new AbortController();
    setMonthHolidays([]);
    setHolidayLoading(true);
    setHolidayError(null);
    void holidayClient.query({ from_date: range.rangeStart, to_date: range.rangeEnd }, { signal: controller.signal })
      .then(calendar => { if (!controller.signal.aborted) setMonthHolidays(calendar.holidays); })
      .catch(error => { if (!controller.signal.aborted) setHolidayError(error instanceof Error ? error.message : '無法讀取國定假日。'); })
      .finally(() => { if (!controller.signal.aborted) setHolidayLoading(false); });
    return () => controller.abort();
  }, [activeTab, range, holidayReload]);

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
    const pendingStaffIds = new Set(staffToLoad.map(staff => staff.id));

    let cancelled = false;
    const controller = new AbortController();
    calendarControllerRef.current?.abort();
    calendarControllerRef.current = controller;
    setCalendarLoading(true);
    setCalendarError(null);

    const loadRows = async () => {
      const caseRequests = new Map<string, Promise<HistoricalCaseRanges | null>>();
      const loadStaffRow = async (staff: (typeof staffToLoad)[number]) => {
        // Each row needs two independent projections. Limit active rows so queued
        // browser requests do not consume their timeout before reaching the API.
        const [historical, canonical] = await Promise.allSettled([staffMonthlyScheduleClient.query(
          staff.id, month.year, month.month, { signal: controller.signal },
        ), schedulingCurrentClient.queryCurrentCalendar(
          {
            staffId: staff.id,
            rangeStart: range.rangeStart,
            rangeEnd: range.rangeEnd,
          },
          { signal: controller.signal },
        )]);
        let overlays: HistoricalAssignmentOverlay[] = [];
        let historicalError: string | null = null;
        try {
          if (historical.status === 'rejected') throw historical.reason;
          overlays = adaptHistoricalAssignmentOverlays(historical.value);
        } catch (caught) {
          historicalError = caught instanceof Error ? caught.message : '歷史指派月曆載入失敗。';
        }
        try {
          if (canonical.status === 'rejected') throw canonical.reason;
          const projection = canonical.value;
          const state: CalendarRowState = projection.days.length === 0
            ? { kind: 'empty' }
            : {
                kind: 'loaded',
                row: adaptSchedulingProjection(staff, projection),
                assignments: projection.assignments,
              };
          return { staffId: staff.id, state, overlays, historicalError, monthly: historical.status === 'fulfilled' ? historical.value : undefined, error: null };
        } catch (caught) {
          const error = caught instanceof Error ? caught : new Error('排班日曆查詢失敗');
          const state: CalendarRowState = caught instanceof SchedulingCurrentError
            && caught.publicCode === 'service_time_terms_incomplete'
            ? { kind: 'terms_incomplete' }
            : { kind: 'error', message: renderError(error) };
          return { staffId: staff.id, state, overlays, historicalError, monthly: historical.status === 'fulfilled' ? historical.value : undefined, error: state.kind === 'error' ? error : null };
        }
      };
      const results = await loadStaffQueries(staffToLoad, controller.signal, async staff => {
        const result = await loadStaffRow(staff);
        const caseNos = new Set(result.monthly?.days.flatMap(day =>
          (day.status === 'historical_assignment' || day.status === 'historical_reservation') && day.case_no ? [day.case_no] : [],
        ));
        const ranges = new Map<string, HistoricalCaseRanges | null>();
        for (const caseNo of caseNos) {
          if (controller.signal.aborted) break;
          let request = caseRequests.get(caseNo);
          if (!request) {
            request = loadHistoricalCaseRanges(caseNo, controller.signal);
            caseRequests.set(caseNo, request);
          }
          ranges.set(caseNo, await request);
        }
        if (mountedRef.current && !controller.signal.aborted && !cancelled) {
          pendingStaffIds.delete(result.staffId);
          calendarLoadedKeyRef.current.set(result.staffId, rangeKey);
          calendarRetryStaffIdsRef.current.delete(result.staffId);
          setCalendarRows(current => ({ ...current, [result.staffId]: result.state }));
          setHistoricalOverlaysByStaff(current => ({ ...current, [result.staffId]: result.overlays }));
          setMonthlyRowsByStaff(current => ({ ...current, [result.staffId]: result.monthly }));
          setHistoricalRangesByStaff(current => ({ ...current, [result.staffId]: ranges }));
          setHistoricalOverlayErrors(current => {
            const next = { ...current };
            if (result.historicalError) next[result.staffId] = result.historicalError;
            else delete next[result.staffId];
            return next;
          });
        }
        return result;
      });
      if (!mountedRef.current || controller.signal.aborted || cancelled) return;
      const failed = results.filter((result) => result.error !== null);
      if (failed.length > 0) {
        setCalendarError(new Error(
          `${failed.length} 位服務人員的排班資料載入失敗；請查看各列狀態後重試。`,
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
      // A change may interrupt other rows in this batch; they still need a fresh read.
      for (const staffId of pendingStaffIds) {
        if (calendarLoadedKeyRef.current.get(staffId) === rangeKey) calendarLoadedKeyRef.current.delete(staffId);
      }
    };
  }, [range, retryGeneration, staffList, month.year, month.month, availabilityRevision]);

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
    if (!collisionDrawerOpen || selectedStaffId === null) return;
    const caseToInspect = eligibilityCaseNo.trim() || selectedCaseNo.trim();
    if (caseToInspect) {
      void queryEligibility(caseToInspect, selectedStaffId);
    }
  }, [collisionDrawerOpen, selectedStaffId, eligibilityCaseNo, selectedCaseNo, queryEligibility, availabilityRevision]);

  // 篩選與搜尋過濾
  const filteredStaff = useMemo(() => {
    return staffList.filter((staff) => {
      const matchKeyword =
        !searchKeyword ||
        staff.displayName.toLowerCase().includes(searchKeyword.toLowerCase()) ||
        (staff.unionNo ?? '').toLowerCase().includes(searchKeyword.toLowerCase());

      if (!matchKeyword) return false;

      const state = calendarRows[staff.id];
      if (state?.kind === 'loaded' && !matchesSchedulingFilter(state.row, statusFilter)) return false;
      if (state?.kind !== 'loaded' && statusFilter !== 'all') return false;

      return true;
    });
  }, [staffList, searchKeyword, statusFilter, calendarRows]);

  const selectedStaffRow = selectedStaffId ? calendarRows[selectedStaffId] : null;
  const taipeiToday = todayIsoDate();
  const [taipeiYear, taipeiMonth, taipeiDay] = taipeiToday.split('-');

  const thirdSegments = useMemo(
    () => buildYearThirdAxis(month, taipeiToday, monthHolidays),
    [month, taipeiToday, monthHolidays],
  );

  const todayAxisPercent = useMemo(() => {
    if (month.year !== Number(taipeiYear)) return null;
    return dateToYearAxisPercent(taipeiToday, month.year, false);
  }, [month.year, taipeiYear, taipeiToday]);

  const syncScrollMetrics = useCallback(() => {
    const body = calendarBodyScrollRef.current;
    if (!body || body.scrollWidth <= 0 || body.clientWidth <= 0) return;
    const max = Math.max(0, body.scrollWidth - body.clientWidth);
    const ratio = Math.min(1, body.clientWidth / body.scrollWidth);
    setScrollMetrics({
      max,
      thumbWidth: Math.max(64, Math.round(ratio * Math.max(300, body.clientWidth - 360))),
      clientTimelineWidth: Math.max(300, body.clientWidth - 260),
      measuredZeroOverflow: max === 0,
    });
  }, []);

  useEffect(() => {
    syncScrollMetrics();
    window.addEventListener('resize', syncScrollMetrics);
    return () => window.removeEventListener('resize', syncScrollMetrics);
  }, [syncScrollMetrics, activeTab, filteredStaff.length]);

  const applyHorizontalScroll = useCallback((nextLeft: number) => {
    const body = calendarBodyScrollRef.current;
    const header = calendarHeaderScrollRef.current;
    const max = body && body.scrollWidth > body.clientWidth
      ? Math.max(0, body.scrollWidth - body.clientWidth)
      : scrollMetrics.max;
    const clamped = Math.max(0, Math.min(max, nextLeft));
    if (body) body.scrollLeft = clamped;
    if (header) header.scrollLeft = clamped;
    setScrollLeftValue(clamped);
  }, [scrollMetrics.max]);

  const scrollToMonthColumn = useCallback((targetMonth: number) => {
    const body = calendarBodyScrollRef.current;
    if (!body || body.scrollWidth <= body.clientWidth) return;
    const monthOffset = Math.max(0, (targetMonth - 1) * 3 * GANTT_THIRD_COL_WIDTH - 20);
    applyHorizontalScroll(monthOffset);
  }, [applyHorizontalScroll]);

  const stepScrollByThird = useCallback((deltaThirds: number) => {
    const current = calendarBodyScrollRef.current?.scrollLeft ?? scrollLeftValue;
    applyHorizontalScroll(current + deltaThirds * GANTT_THIRD_COL_WIDTH);
  }, [applyHorizontalScroll, scrollLeftValue]);

  const visibleMonthRange = useMemo(() => {
    const timelineWidth = GANTT_TOTAL_THIRDS * GANTT_THIRD_COL_WIDTH;
    const viewW = scrollMetrics.clientTimelineWidth;
    const startMonth = Math.max(1, Math.min(12, Math.floor((scrollLeftValue / timelineWidth) * 12) + 1));
    const endMonth = Math.max(startMonth, Math.min(12, Math.floor(((scrollLeftValue + viewW - 1) / timelineWidth) * 12) + 1));
    return {
      startMonth,
      endMonth,
      label: startMonth === endMonth ? `目前可視：${startMonth}月` : `目前可視：${startMonth}月 ～ ${endMonth}月`,
    };
  }, [scrollLeftValue, scrollMetrics.clientTimelineWidth]);

  useEffect(() => {
    if (!pendingTodayScroll) return;
    const header = calendarHeaderScrollRef.current;
    const body = calendarBodyScrollRef.current;
    const today = header?.querySelector<HTMLElement>(`[data-date="${taipeiToday}"]`);
    const staffColumn = header?.querySelector<HTMLElement>('.gantt-staff-header-cell');
    if (!header || !body || !today || !staffColumn) return;
    const staffWidth = staffColumn.getBoundingClientRect().width;
    const todayRect = today.getBoundingClientRect();
    const left = Math.max(0, todayRect.left - header.getBoundingClientRect().left
      + header.scrollLeft - staffWidth - (body.clientWidth - staffWidth - todayRect.width) / 2);
    body.scrollLeft = left;
    header.scrollLeft = body.scrollLeft;
    setScrollLeftValue(body.scrollLeft);
    setPendingTodayScroll(false);
  }, [pendingTodayScroll, month, taipeiToday, filteredStaff.length, activeTab]);

  useEffect(() => {
    if (pendingTodayScroll || activeTab !== 'calendar') return;
    scrollToMonthColumn(month.month);
  }, [month.month, month.year, activeTab, pendingTodayScroll, scrollToMonthColumn]);
  const eligibilityResult = eligibilityState.kind === 'ready'
    ? eligibilityDisplay(eligibilityState.data)
    : null;

  const activeCaseOption = caseOptionsState.kind === 'ready'
    ? caseOptionsState.options.find((option) => option.caseNo === selectedCaseNo.trim())
    : undefined;
  const visibleInterval = visibleCaseInterval(activeCaseOption, month);
  const ghostSummary = activeCaseOption
    ? `${activeCaseOption.startDate} ～ ${activeCaseOption.endDate}`
    : '';
  const isMatchingGhostMonth = visibleInterval !== null;
  const [ghostYear = 0, ghostMonth = 0, ghostStartDay = 0] = activeCaseOption?.startDate.split('-').map(Number) ?? [];
  const ghostEndDay = Number(activeCaseOption?.endDate.slice(8, 10) ?? 0);

  const handleOpenStaffGhostDrawer = (staff: StaffDirectoryCardViewModel) => {
    setSelectedStaffId(staff.id);
    const caseToInspect = selectedCaseNo.trim() || eligibilityCaseNo.trim();
    setEligibilityCaseNo(caseToInspect);
    setCandidatePoolSuccess(null);
    setCandidatePoolError(null);
    setCollisionDrawerOpen(true);
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
      setCandidatePoolSuccess(`🎉 已成功將 ${staffDisplayLabel(staffObj?.unionNo, staffObj?.displayName ?? '姓名未設定')} 加入案件 #${caseNo} 的候選人聯繫名冊！`);
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
      <ManagementPageHeader title="📅 排班日曆與調度" description="查看每月檔期；需要安排案件時，展開案件排查。" />

      {/* Sticky Tabs Bar */}
      <nav className="scheduling-tab-bar" aria-label="排班工作區">
        <button
          data-surface-id="scheduling.tab.calendar"
          className={`scheduling-tab-btn ${activeTab === 'calendar' ? 'active' : ''}`}
          aria-current={activeTab === 'calendar' ? 'page' : undefined}
          onClick={() => { if (('calendar') !== activeTab) requestLeave(() => setActiveTab('calendar')); }}
        >
          📅 排班月曆
        </button>
        <button
          data-surface-id="scheduling.tab.holidays"
          className={`scheduling-tab-btn ${activeTab === 'holidays' ? 'active' : ''}`}
          onClick={() => { if (('holidays') !== activeTab) requestLeave(() => setActiveTab('holidays')); }}
        >
          🗓️ 國定假日政策
        </button>
      </nav>

      {activeTab === 'calendar' && (
        <section
          className="gantt-hero-card"
          data-surface-id="scheduling.calendar"
          aria-label="排班甘特月曆與服務人員檔期"
        >
          {/* Top Control Bar: Month Switcher + Search + Filters */}
          <section className="gantt-matrix-header-bar" aria-label="月曆查詢控制">
            {/* Left: Year & Month Navigator & Today */}
            <div className="gantt-month-navigator">
              <div className="month-pill-group">
                <button
                  type="button"
                  className="month-nav-arrow"
                  aria-label="查看上一年"
                  onClick={() => setMonth((value) => ({ year: value.year - 1, month: value.month }))}
                >
                  ◀ {month.year - 1}年
                </button>
                <span className="current-month-display">
                  {month.year} 年 {month.month}月
                </span>
                <button
                  type="button"
                  className="month-nav-arrow"
                  aria-label="查看下一年"
                  onClick={() => setMonth((value) => ({ year: value.year + 1, month: value.month }))}
                >
                  {month.year + 1}年 ▶
                </button>
              </div>

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
                onClick={() => {
                  setMonth(currentMonth());
                  setPendingTodayScroll(true);
                }}
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
                  🟡 待派單／排班緩衝期
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

          {/* Quick Month Jump Row */}
          <div className="gantt-month-jump-row" aria-label="月份快速定位">
            <span className="gantt-month-jump-label">快速定位月份：</span>
            {Array.from({ length: 12 }, (_, index) => {
              const targetMonth = index + 1;
              const isSelected = targetMonth === month.month;
              const isInView = targetMonth >= visibleMonthRange.startMonth && targetMonth <= visibleMonthRange.endMonth;
              const isCurrentRealMonth = month.year === Number(taipeiYear) && targetMonth === Number(taipeiMonth);
              return (
                <button
                  key={targetMonth}
                  type="button"
                  className={`month-jump-pill ${isSelected ? 'active' : ''} ${isInView ? 'is-in-view' : ''} ${isCurrentRealMonth ? 'is-current-month' : ''}`}
                  onClick={() => {
                    setMonth((value) => ({ year: value.year, month: targetMonth }));
                    scrollToMonthColumn(targetMonth);
                  }}
                >
                  {targetMonth}月
                </button>
              );
            })}
          </div>

          <details className="gantt-case-checks" open={selectedCaseNo ? true : undefined}>
            <summary>案件排查<span>{selectedCaseNo ? `目前案件：${selectedCaseNo}` : '查詢可排人選與檔期衝突'}</span></summary>
          <div className="gantt-case-projection-bar">
            <div className="gantt-case-selector-row">
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
                  setEligibilityState({ kind: 'idle' });
                  const option = caseOptionsState.kind === 'ready'
                    ? caseOptionsState.options.find((item) => item.caseNo === val)
                    : undefined;
                  if (option) {
                    const [year, targetMonth] = option.startDate.split('-').map(Number);
                    if (year !== month.year || targetMonth !== month.month) {
                      setMonth({ year, month: targetMonth });
                    }
                  }
                }}
                aria-label="資格查詢案件編號"
                disabled={caseOptionsState.kind !== 'ready' || caseOptionsState.options.length === 0}
              >
                <option value="">
                  {caseOptionsState.kind === 'loading'
                    ? '正在載入合法案件…'
                    : caseOptionsState.kind === 'error'
                      ? '案件選項載入失敗'
                      : caseOptionsState.options.length === 0
                        ? '目前沒有可排查案件'
                        : '請選擇排查案件'}
                </option>
                {caseOptionsState.kind === 'ready' && caseOptionsState.options.map((option) => (
                  <option key={option.caseNo} value={option.caseNo}>{option.label}</option>
                ))}
              </select>
              {caseOptionsState.kind === 'error' && (
                <button
                  type="button"
                  className="btn-secondary-action"
                  onClick={() => {
                    assignmentOptionsByStaffRef.current.clear();
                    setCaseOptionsRetryGeneration((generation) => generation + 1);
                  }}
                >
                  重新載入案件選項
                </button>
              )}
            </div>

            {selectedCaseNo && (
              <>
                {activeCaseOption ? <div className="gantt-case-info-pill">
                  <span>📅 服務日期：</span>
                  <strong>{ghostSummary}</strong>
                  {!isMatchingGhostMonth && <span style={{ color: '#b45309', marginLeft: '6px' }}>
                    （案件服務月份與目前月曆不同）
                  </span>}
                </div> : <div className="gantt-case-info-pill">請點選月嫂列查詢服務日期與檔期衝突。</div>}

                {activeCaseOption && !isMatchingGhostMonth && (
                  <button
                    type="button"
                    className="btn-secondary-action"
                    onClick={() => setMonth({ year: ghostYear, month: ghostMonth })}
                    style={{ padding: '5px 12px', fontSize: '0.82rem', borderRadius: '8px', border: '1px solid', fontWeight: 700 }}
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
                  title="清除案件，回復純排班視圖"
                >
                  ✕ 清除案件
                </button>
              </>
            )}
          </div>
          </details>

          {/* Full Legend Bar */}
          <section className="gantt-legend-bar-rich" aria-label="排班檔期圖例">
            <div className="legend-item">
              <span className="legend-badge active" />
              <span>正式服務履約</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge buffer" />
              <span>7 天排班緩衝期</span>
            </div>
            <div className="legend-item">
              <span className="legend-badge deposit" />
              <span>等待定金確認，檔期暫時保留</span>
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
          {calendarLoading && (
            <div className="scheduling-status" role="status">正在載入排班月曆…</div>
          )}
          {selectedStaffId && selectedStaffRow?.kind === 'empty' && !calendarLoading && !calendarError && (
            <div className="scheduling-status">目前範圍沒有排班資料。</div>
          )}
          {selectedStaffId && selectedStaffRow?.kind === 'terms_incomplete' && !calendarLoading && !calendarError && (
            <div className="scheduling-status error" role="alert" style={{ background: '#fffbeb', borderColor: '#f59e0b', color: '#b45309' }}>
              ⚠️ 該服務人員所屬訂單的每日服務時段尚未完整，請至本案客戶與訂單資料補齊。
            </div>
          )}
          {holidayLoading && <p role="status">正在讀取當月國定假日…</p>}
          {holidayError && <p role="alert">國定假日標示載入失敗：{holidayError} <button type="button" onClick={() => setHolidayReload(value => value + 1)}>重新讀取假日</button></p>}
          {!holidayLoading && !holidayError && monthHolidays.length === 0 && <p className="scheduling-status">本月沒有已匯入的國定假日資料。</p>}
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
          {/* Multi-Caregiver Gantt Chart Matrix Table */}
          <>
            <p className="gantt-scroll-guidance" id="gantt-scroll-guidance">
              全年度 12 個月 × 上／中／下旬三等份（共 36 欄）；利用下方凍結左右滑軌或上方月份按鈕即可連貫瀏覽跨月檔期。
            </p>
            <div
              className="gantt-matrix-frame"
              data-surface-id="scheduling.calendar.grid"
              style={{ '--gantt-day-count': thirdSegments.length } as React.CSSProperties}
            >
              <div
                ref={calendarHeaderScrollRef}
                className="gantt-matrix-sticky-header"
                data-surface-id="scheduling.calendar.date-header"
              >
                <div className="gantt-matrix-header-inner">
                  <div className="gantt-staff-header-cell">
                    <strong>月嫂名冊 ｜ 檔期診斷</strong>
                    <small>每格約 9～11 天（上／中／下旬）</small>
                  </div>
                  <div className="gantt-timeline-header-stack">
                    <div className="gantt-months-header-row">
                      {Array.from({ length: 12 }, (_, idx) => {
                        const monthNum = idx + 1;
                        const isSelectedMonth = monthNum === month.month;
                        const isRealCurrentMonth = month.year === Number(taipeiYear) && monthNum === Number(taipeiMonth);
                        return (
                          <div
                            key={`${month.year}-m-${monthNum}`}
                            className={`gantt-month-group-col ${isSelectedMonth ? 'active-month' : ''} ${isRealCurrentMonth ? 'is-current-month' : ''}`}
                          >
                            <span>{month.year}年 {monthNum}月</span>
                            {isRealCurrentMonth ? (
                              <span className="gantt-month-group-badge">本月</span>
                            ) : isSelectedMonth ? (
                              <span className="gantt-month-group-badge selected">查詢月</span>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                    <div className="gantt-thirds-header-row">
                      {thirdSegments.map((seg) => (
                        <div
                          key={seg.key}
                          className={`gantt-day-header-col gantt-third-header-col ${seg.thirdIndex === 2 ? 'is-month-end' : ''} ${seg.isActiveMonth ? 'is-active-month' : ''} ${seg.containsToday ? 'today' : ''} ${seg.holidayNames.length > 0 ? 'holiday' : ''}`}
                          data-date={seg.todayDateStr}
                          title={`${seg.startDate} ～ ${seg.endDate}${seg.holidayNames.length > 0 ? `｜${seg.holidayNames.join('、')}` : ''}`}
                        >
                          <div className="gantt-third-title">
                            <span>{seg.monthThirdLabel}</span>
                            {seg.containsToday && <span className="gantt-today-pill">今日</span>}
                          </div>
                          <span className="gantt-third-dates">{seg.rangeLabel}</span>
                          {seg.holidayNames.length > 0 && (
                            <span className="gantt-holiday-name">{seg.holidayNames.join('、')}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div
                ref={calendarBodyScrollRef}
                className="gantt-matrix-scroll-wrapper"
                tabIndex={0}
                aria-describedby="gantt-scroll-guidance"
                onScroll={(event) => {
                  const nextLeft = event.currentTarget.scrollLeft;
                  if (calendarHeaderScrollRef.current) {
                    calendarHeaderScrollRef.current.scrollLeft = nextLeft;
                  }
                  setScrollLeftValue(nextLeft);
                  syncScrollMetrics();
                }}
              >
                <div className="gantt-matrix-table">
                {!directoryLoading && filteredStaff.length === 0 && (
                  <div className="scheduling-status">
                    {staffList.length === 0 ? '目前沒有可顯示的服務人員摘要。' : '目前範圍沒有排班資料。'}
                  </div>
                )}
                {/* Staff Rows */}
                {filteredStaff.map((staff) => {
                  const row = calendarRows[staff.id];
                  const ghostConfig: GhostProjectionConfig | null = visibleInterval
                    ? {
                        active: true,
                        caseNo: selectedCaseNo.trim(),
                        ...visibleInterval,
                        outcome: fullIntervalOutcome(caseEligibilityRows[staff.id]),
                      }
                    : null;
                  const diagnostic = getStaffDiagnosticBadge(row ?? undefined, ghostConfig);
                  const monthly = monthlyRowsByStaff[staff.id];
                  const enrichmentContext: SpanEnrichmentContext = {
                    year: month.year,
                    month: month.month,
                    orderSummariesByCaseNo,
                    staffAssignments: assignmentOptionsByStaffRef.current.get(staff.id) ?? [],
                    projectionAssignments: row?.kind === 'loaded' ? (row.assignments ?? []) : [],
                  };
                  const hasShiftRows = monthly?.days.some(day => day.starts_at || (day.status !== 'available' && day.status !== 'historical_assignment'));
                  const monthMatches = monthly?.year === month.year && monthly.month === month.month;
                  const monthlySpans = hasShiftRows && monthMatches
                    ? assignNonOverlappingLanes(monthlyShiftSpans(monthly, enrichmentContext))
                    : buildGanttSpans(row ?? undefined, range.totalDays, null, monthMatches ? historicalOverlaysByStaff[staff.id] : [], enrichmentContext);
                  const spans = showHistoricalCaseRanges(monthlySpans, historicalRangesByStaff[staff.id]);
                  if (ghostConfig) {
                    spans.push(...caseShiftSpans(
                      ghostConfig,
                      caseEligibilityRows[staff.id],
                      Math.max(-1, ...spans.map(span => span.lane ?? 0)) + 1,
                      `${month.year}-${String(month.month).padStart(2, '0')}`,
                    ));
                  }
                  const spanHeight = Math.max(60, ...spans.map(span => ((span.lane ?? 0) + 1) * 52 + 8));
                  const historicalOverlayError = historicalOverlayErrors[staff.id];

                  return (
                    <div
                      key={staff.id}
                      data-staff-id={staff.id}
                      data-case-start-day={ghostConfig?.startDay}
                      data-case-end-day={ghostConfig?.endDay}
                      data-case-outcome={ghostConfig?.outcome}
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
                          <strong>{staffDisplayLabel(staff.unionNo, staff.displayName)}</strong>
                        </div>
                        {historicalOverlayError && <small className="historical-overlay-error" role="status">歷史指派區間未載入：{historicalOverlayError}</small>}
                        <div
                          className={`staff-diagnostic-tag tag-${diagnostic.tone}`}
                          title={row?.kind === 'error' ? row.message : undefined}
                        >
                          {diagnostic.text}
                        </div>
                        {selectedCaseNo && (
                          <button
                            type="button"
                            className="btn-secondary-action"
                            aria-label={`檢查 ${staff.displayName} 的資格與檔期`}
                            onClick={(event) => {
                              event.stopPropagation();
                              handleOpenStaffGhostDrawer(staff);
                            }}
                          >
                            檢查資格與檔期
                          </button>
                        )}
                      </div>

                      {/* Right: Gantt 36-Thirds Timeline Canvas */}
                      <div className="gantt-days-timeline-cell">
                        <div className="gantt-timeline-grid-bg">
                          {thirdSegments.map((seg) => (
                            <div
                              key={seg.key}
                              className={`gantt-grid-col ${seg.thirdIndex === 2 ? 'is-month-end' : ''} ${seg.isActiveMonth ? 'active-month-col' : ''} ${seg.containsToday ? 'today-col' : ''} ${seg.holidayNames.length > 0 ? 'holiday-col' : ''}`}
                            />
                          ))}
                        </div>
                        {todayAxisPercent !== null && (
                          <div
                            className="gantt-today-vertical-line"
                            style={{ left: `${todayAxisPercent}%` }}
                            aria-hidden="true"
                          />
                        )}

                        {/* Continuous Visual Gantt Blocks */}
                        <div className="gantt-spans-layer" style={{ height: spanHeight }}>
                          {spans.map((sp) => {
                            const leftPercent = dateToYearAxisPercent(sp.visualStartDate, month.year, false);
                            const endPercent = dateToYearAxisPercent(sp.visualEndDate, month.year, true);
                            const widthPercent = Math.max(0.5, endPercent - leftPercent);
                            const titleParts = [
                              sp.clientName,
                              sp.caseText,
                              sp.dateRangeText,
                              sp.dailyTimeText,
                              sp.statusLabel ? `(${sp.statusLabel})` : null,
                            ].filter(Boolean);
                            return (
                              <button
                                type="button"
                                key={sp.id}
                                className={`gantt-span-bar span-${sp.tone} ${selectedCaseNo && sp.tone !== 'historical' ? 'span-ghost-clickable' : ''}`}
                                data-start-day={sp.startDay}
                                data-end-day={sp.endDay}
                                style={{
                                  left: `${leftPercent}%`,
                                  width: `${widthPercent}%`,
                                  top: `${(sp.lane ?? 0) * 52 + 7}px`,
                                }}
                                title={`${titleParts.join('｜')}${selectedCaseNo && sp.tone !== 'historical' ? ' — 點擊開啟詳細排查抽屜' : ''}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (sp.shift || sp.tone === 'historical') {
                                    setSelectedShift(sp);
                                  } else if (selectedCaseNo) {
                                    handleOpenStaffGhostDrawer(staff);
                                  } else {
                                    setSelectedShift(sp);
                                  }
                                }}
                              >
                                <div className="span-line-primary">
                                  {sp.icon && <span className="span-icon">{sp.icon} </span>}
                                  {sp.clientName && (
                                    <>
                                      <span className="span-client-name">{sp.clientName}</span>
                                      <span className="span-sep">｜</span>
                                    </>
                                  )}
                                  <span className="span-case-name">{sp.caseText}</span>
                                  {sp.statusLabel && (
                                    <small className="span-status-sub"> ({sp.statusLabel})</small>
                                  )}
                                </div>
                                {(sp.dateRangeText || sp.dailyTimeText) && (
                                  <div className="span-line-secondary">
                                    {sp.dateRangeText && <span className="span-date-range">📅 {sp.dateRangeText}</span>}
                                    {sp.dailyTimeText && <span className="span-daily-time">　⏰ {sp.dailyTimeText}</span>}
                                  </div>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    </div>
                  );
                })}
                </div>
              </div>

              {/* Sticky Bottom Horizontal Scroll Rail */}
              <div className="gantt-scroll-rail" data-surface-id="scheduling.calendar.scroll-rail">
                <div className="gantt-rail-meta">
                  <button
                    type="button"
                    className="gantt-rail-step-btn"
                    onClick={() => stepScrollByThird(-1)}
                    aria-label="往左捲動一旬"
                  >
                    ◀ 上一旬
                  </button>
                  <span className="gantt-rail-visible-range">
                    📍 {visibleMonthRange.label}
                  </span>
                  <button
                    type="button"
                    className="gantt-rail-step-btn"
                    onClick={() => stepScrollByThird(1)}
                    aria-label="往右捲動一旬"
                  >
                    下一旬 ▶
                  </button>
                </div>
                <div className="gantt-rail-slider-wrap">
                  <div className="gantt-rail-months-ticks" aria-hidden="true">
                    {Array.from({ length: 12 }, (_, idx) => (
                      <span key={idx + 1}>{idx + 1}月</span>
                    ))}
                  </div>
                  <input
                    type="range"
                    className="gantt-scroll-rail-slider"
                    aria-label="左右捲動排班日曆"
                    min={0}
                    max={scrollMetrics.max}
                    value={Math.min(scrollLeftValue, scrollMetrics.max)}
                    disabled={scrollMetrics.measuredZeroOverflow}
                    onChange={(event) => applyHorizontalScroll(Number(event.target.value))}
                    style={{ '--gantt-thumb-width': `${scrollMetrics.thumbWidth}px` } as React.CSSProperties}
                  />
                </div>
              </div>
            </div>
          </>
          {!directoryLoading && directoryNextCursor !== null && (
            <div ref={directorySentinelRef} className="scheduling-status" data-control-id="scheduling.staff.next-page">
              {directoryNextPageError ? (
                <div role="alert">
                  <p>更多月嫂暫時無法載入，已載入的班表仍可查看。</p>
                  <button type="button" onClick={() => void loadNextDirectoryPage()}>重試載入月嫂</button>
                </div>
              ) : (
                <p role="status">{directoryLoadingMore ? '正在載入更多月嫂…' : '向下捲動會自動載入更多月嫂。'}</p>
              )}
            </div>
          )}
        </section>
      )}

      {activeTab === 'holidays' && (
        <HolidayPolicyWorkspace />
      )}
      <Drawer isOpen={selectedShift !== null} onClose={() => setSelectedShift(null)} title="排班與訂單明細">
        {selectedShift && (
          <div className="collision-drawer-content">
            <strong>
              {selectedShift.clientName ? `${selectedShift.clientName}｜` : ''}
              {selectedShift.caseText}
              {selectedShift.statusLabel ? ` · ${selectedShift.statusLabel}` : ''}
            </strong>
            {selectedShift.historicalCaseDates ? (
              <p>📅 整案服務起訖：{selectedShift.historicalCaseDates}</p>
            ) : (
              <p>📅 服務起訖：{selectedShift.dateRangeText ?? `${selectedShift.visualStartDate} ～ ${selectedShift.visualEndDate}`}</p>
            )}
            {selectedShift.dailyTimeText && <p>⏰ 每日時段：{selectedShift.dailyTimeText}</p>}
            {selectedShift.tone !== 'historical' && selectedShift.shift && (
              <p>日曆日期 {selectedShift.shift.work_date}{selectedShift.endDay !== selectedShift.startDay ? ` 至當月 ${selectedShift.endDay} 日` : ''}</p>
            )}
            {selectedShift.tone !== 'historical' && selectedShift.shift?.service_date && (
              <p>首個服務日 {selectedShift.shift.service_date}</p>
            )}
          </div>
        )}
      </Drawer>
      {/* 🔮 洽談檔期衝突檢測 暨 媒合排查 Slide-over Drawer (Unified wide size) */}
      <Drawer
        isOpen={collisionDrawerOpen}
        onClose={() => setCollisionDrawerOpen(false)}
        title={`🔮 案件 #${eligibilityCaseNo || selectedCaseNo || '---'} ✕ 月嫂 ${staffDisplayLabel(staffList.find((s) => s.id === selectedStaffId)?.unionNo, staffList.find((s) => s.id === selectedStaffId)?.displayName ?? '姓名未設定')} 需求與檔期排查`}
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
                將 <strong>{staffDisplayLabel(staffList.find((s) => s.id === selectedStaffId)?.unionNo, staffList.find((s) => s.id === selectedStaffId)?.displayName ?? '姓名未設定')}</strong> 推薦加入案件 <strong>#{eligibilityCaseNo || selectedCaseNo}</strong> 的候選人聯繫名單。
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
                  className="scheduling-action"
                  onClick={() => {
                    setCollisionDrawerOpen(false);
                    const targetCase = eligibilityCaseNo.trim() || selectedCaseNo.trim();
                    window.location.hash = targetCase
                      ? `#order-workbench-v2?case_no=${encodeURIComponent(targetCase)}`
                      : '#order-workbench-v2';
                  }}
                  style={{ padding: '5px 12px', fontSize: '0.82rem', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 700 }}
                >
                  👉 前往「待辦看板」開啟媒合工作與 LINE 推播
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
                排查案件
              </label>
              <select
                aria-label="資格查詢案件編號"
                data-control-id="scheduling.eligibility.case-select"
                value={eligibilityCaseNo}
                onChange={(event) => {
                  eligibilityControllerRef.current?.abort();
                  setEligibilityCaseNo(event.target.value);
                  setSelectedCaseNo(event.target.value);
                  setEligibilityState({ kind: 'idle' });
                }}
                disabled={caseOptionsState.kind !== 'ready' || caseOptionsState.options.length === 0}
                style={{ width: '100%', padding: '9px 12px', borderRadius: '8px', border: '1px solid #dec0b6', fontSize: '0.9rem' }}
              >
                <option value="">請選擇正式案件</option>
                {caseOptionsState.kind === 'ready' && caseOptionsState.options.map((option) => (
                  <option key={option.caseNo} value={option.caseNo}>{option.label}</option>
                ))}
              </select>
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
                    {staffDisplayLabel(staff.unionNo, staff.displayName)}
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

              {eligibilityState.kind === 'ready' ? (
                <div style={{ overflowX: 'auto' }}>
                  <table className="matching-criteria-table">
                    <thead>
                      <tr>
                        <th style={{ width: '32%' }}>檢核項目</th>
                        <th>正式查詢結果</th>
                      </tr>
                    </thead>
                    <tbody>
                      {eligibilityState.data.qualificationChecks.map((check) => (
                        <tr key={check.code}>
                          <td>
                            <div style={{ fontWeight: 700, color: '#1e1b19', display: 'flex', alignItems: 'center', gap: '4px' }}>
                              <span>📋</span>
                              <span>{qualificationCheckLabel(check.code)}</span>
                            </div>
                            <span className={`criteria-match-pill ${check.status === 'pass' ? 'match' : check.status === 'fail' ? 'mismatch' : 'partial'}`} style={{ marginTop: '4px' }}>
                              {qualificationStatusLabel(check.status)}
                            </span>
                          </td>
                          <td style={{ fontSize: '0.84rem', color: '#4b5563', lineHeight: 1.4 }}>
                            {businessSchedulingDetail(check.detail)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div style={{ padding: '36px 16px', textAlign: 'center', color: '#8b7169', fontSize: '0.88rem', background: '#fffcfb', borderRadius: '10px', border: '1px dashed #dec0b6' }}>
                  👆 請先選取服務人員並查詢，系統不會用樣本資料推測客戶需求或月嫂條件。
                </div>
              )}
            </div>

            {/* Right Column: 🛡️ 接單資格與檔期衝突判定 */}
            <div className="collision-panel-card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 700, color: '#9a3412' }}>
                  🛡️ 檔期衝突與 7 天排班緩衝期判定
                </h3>
                {eligibilityState.kind === 'ready' && (
                  <span className="contract-status-pill active" style={{ fontSize: '0.8rem' }}>
                    已依正式資料檢查
                  </span>
                )}
              </div>

              <p style={{ margin: '0 0 14px 0', fontSize: '0.84rem', color: '#74593f', lineHeight: 1.5 }}>
                依據服務人員排班履約、請假留停、既有訂單與 7 天排班緩衝期即時檢核。
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
                            <strong>[{collisionSeverityLabel(collision.severity)}] {collisionKindLabel(collision.kind)}</strong>：{businessSchedulingDetail(collision.detail)}
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
                              <strong>{qualificationCheckLabel(check.code)} ({qualificationStatusLabel(check.status)})</strong>：{businessSchedulingDetail(check.detail)}
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
                      ⚠️ 資料待補正：請依上方「需補齊」與資格檢查的實際項目處理後重試。
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

function LegacySchedulingLink({ caseNo, request }: { caseNo: string; request?: string | null }) {
  const [state, setState] = useState<
    { kind: 'loading' | 'blocked' } | { kind: 'handover'; item: ServiceStartView }
  >({ kind: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    const requestId = Number(request);
    if (!caseNo || (request !== undefined
      && (!request || !/^[1-9][0-9]*$/.test(request) || !Number.isSafeInteger(requestId)))) {
      setState({ kind: 'blocked' });
      return;
    }

    async function resolve() {
      if (request !== undefined) {
        const item = await serviceStartClient.detail(requestId);
        if (controller.signal.aborted) return;
        if (item.request_id !== requestId || item.case_no !== caseNo) throw new Error('case mismatch');
        if (item.workflow_kind === 'handover') {
          setState({ kind: 'handover', item });
          return;
        }
      }
      const plan = await ordersQueryClient.getAssignmentPlan(caseNo, { signal: controller.signal });
      if (controller.signal.aborted) return;
      if (plan.case_no !== caseNo) throw new Error('case mismatch');
      const capability = plan.assignments.some(item => item.official_service_dates.length > 0)
        ? 'system.administration' : 'line.matching.override';
      if (!sessionClient.getUser()?.capabilities.includes(capability)) throw new Error('schedule permission missing');
      const target = new URLSearchParams({ case: caseNo, work: 'service', staffing: 'upcoming' });
      window.location.replace(`#order-workbench-v2?${target}`);
    }
    void resolve().catch(() => {
      if (!controller.signal.aborted) setState({ kind: 'blocked' });
    });
    return () => controller.abort();
  }, [caseNo, request]);

  return <main className="scheduling-gantt-page">
    <ManagementPageHeader title={state.kind === 'handover' ? '服務中換人' : '案件排班'}>
      <a href="#scheduling">返回排班月曆</a>
    </ManagementPageHeader>
    {state.kind === 'loading' && <p role="status">正在確認案件…</p>}
    {state.kind === 'blocked' && <p role="alert">無法確認案件或排班權限，請從案件工作區開啟。</p>}
    {state.kind === 'handover' && <ServiceStartSubstituteWorkbench initial={state.item} />}
  </main>;
}

export const SchedulingPage: React.FC = () => {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const update = () => setHash(window.location.hash);
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  const query = hash.split('?')[1] ?? '';
  const params = new URLSearchParams(query);
  const tab = params.get('tab');
  if (tab === 'coordination' || tab === 'leave_sub') {
    const request = tab === 'coordination' && params.getAll('request').length === 1
      ? params.get('request') : null;
    return <LegacySchedulingLink key={hash} caseNo={canonicalCaseNoFromQuery(query)}
      request={tab === 'coordination' ? request : undefined} />;
  }
  return tab === 'handover' ? <ServiceHandoverPage key={hash} /> : <SchedulingWorkbench />;
};

export default SchedulingPage;
