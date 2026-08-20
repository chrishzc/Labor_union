/**
 * File: SchedulingPage.tsx
 * Description: 多月嫂全景排班甘特月曆與檔期診斷中心（復原高階視覺甘特時間軸，支援多人員並列、搜尋過濾、防撞期 Buffer 鎖定與請假代班標記）。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import './SchedulingPage.css';
import { staffDirectoryClient } from '../api/staff_directory/staff_directory_client';
import { adaptStaffDirectoryPage } from '../adapters/staff/staff_directory_adapter';
import type { StaffDirectoryCardViewModel } from '../adapters/staff/staff_directory_adapter';
import { schedulingCurrentClient } from '../api/scheduling/scheduling_current_client';
import { SchedulingCurrentError } from '../api/scheduling/scheduling_current_errors';
import {
  adaptSchedulingProjection,
  type SchedulingCalendarRowViewModel,
} from '../adapters/scheduling/scheduling_current_adapter';

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

export type CalendarRowState =
  | { kind: 'loaded'; row: SchedulingCalendarRowViewModel }
  | { kind: 'empty' }
  | { kind: 'terms_incomplete' }
  | { kind: 'error'; message: string };

// 產生月嫂檔期智慧診斷標籤（由真實伺服器資料驅動）
function getStaffDiagnosticBadge(state: CalendarRowState | undefined) {
  if (!state || state.kind === 'empty') {
    return { tone: 'available', text: '🟢 檔期完全空閒 (可安排接單)' };
  }
  if (state.kind === 'terms_incomplete') {
    return { tone: 'waiting', text: '🟡 ⚠️ 時段未確認 (需補齊資料)' };
  }
  if (state.kind === 'error') {
    return { tone: 'conflict', text: '🔴 查詢異常' };
  }
  const row = state.row;
  const hasConflict = row.days.some((d) => d.caseLabels.length > 1);
  const hasLeave = row.days.some((d) => d.tone === 'leave');
  const hasBuffer = row.days.some((d) => d.tone === 'buffer');
  const hasWaiting = row.days.some((d) => d.tone === 'waiting');
  const hasActive = row.days.some((d) => d.tone === 'active');

  if (hasConflict) {
    return { tone: 'conflict', text: '🔴 撞期 (預約重疊衝突)' };
  }
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
  return { tone: 'available', text: '🟢 檔期完全空閒 (可安排接單)' };
}

// 動態將 Server 天數投影合併為連續甘特區間條塊
interface GanttSpan {
  id: string;
  startDay: number;
  endDay: number;
  tone: 'active' | 'buffer' | 'conflict' | 'leave' | 'waiting' | 'available';
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
        id: 'full-free',
        startDay: 1,
        endDay: totalDays,
        tone: 'available',
        icon: '✨',
        caseText: '全月檔期完全空閒 (可安排接單)',
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
        tone: 'conflict',
        icon: '❌',
        caseText: '排班資料載入異常',
        statusLabel: state.message,
      },
    ];
  }

  const row = state.row;
  const hasAnyOccupancy = row.days.some((d) => d.tone !== 'available');
  if (!hasAnyOccupancy) {
    return [
      {
        id: 'full-free',
        startDay: 1,
        endDay: totalDays,
        tone: 'available',
        icon: '✨',
        caseText: '全月檔期完全空閒 (可安排接單)',
      },
    ];
  }

  const spans: GanttSpan[] = [];
  let current: GanttSpan | null = null;

  row.days.forEach((day, index) => {
    const dayNum = index + 1;
    const isRest = day.tone === 'rest';
    const isOccupied = day.tone !== 'available';
    const tone = isRest ? 'active' : day.tone;
    const hasCase = day.caseLabels.length > 0;
    const caseText = hasCase
      ? day.caseLabels.join('、')
      : (tone === 'available' ? '檔期空閒' : day.statusLabel);
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

  const mountedRef = useRef(true);
  const directoryControllerRef = useRef<AbortController | null>(null);
  const calendarControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      directoryControllerRef.current?.abort();
      calendarControllerRef.current?.abort();
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
    void loadDirectory();
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
          (err.code === 'service_time_terms_incomplete' || err.publicCode === 'service_time_terms_incomplete');

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
            全景甘特檔期矩陣與即時衝突診斷；防撞期 Buffer、待定金鎖定與突發代班全流程可視化。
          </p>
        </div>
        <button data-control-id="scheduling.precision.open" disabled>
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
        <main className="gantt-hero-card" data-surface-id="scheduling.calendar">
          {/* Projection Lock Panel */}
          <section className="gantt-projection-panel" aria-label="媒合投影狀態">
            <div>
              <strong>🔮 洽談中訂單檔期衝突預覽</strong>
              <p>後端 typed matching projection 尚未開放。</p>
            </div>
            <select
              aria-label="洽談中訂單檔期投影"
              data-control-id="scheduling.projection.order-select"
              disabled
            >
              <option>後端尚未提供</option>
            </select>
            <button data-control-id="scheduling.projection.lock" disabled>
              預約鎖定（未開放）
            </button>
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
              <span className="legend-badge available" />
              <span>檔期完全空閒</span>
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
        </main>
      )}

      {/* Other Tabs */}
      {activeTab === 'leave_sub' && (
        <UnavailableTab
          title="服務中請假與緊急代班調度"
          controls={['scheduling.leave.substitution', 'scheduling.leave.extension', 'scheduling.leave.apply']}
        />
      )}
      {activeTab === 'holidays' && (
        <UnavailableTab
          title="國定假日與預設政策"
          controls={['scheduling.holiday.create', 'scheduling.holiday.toggle-rest', 'scheduling.holiday.toggle-pay', 'scheduling.holiday.delete', 'scheduling.holiday.save']}
        />
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
