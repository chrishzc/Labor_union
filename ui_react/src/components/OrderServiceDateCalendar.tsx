import { useEffect, useId, useMemo, useState, type FC } from 'react';
import { buildCalendarMonth, calendarOccupancyDetailsByDate, calendarWeekdays, shiftCalendarDate, shiftCalendarMonth, type CalendarOccupancyDetail } from '../../../line/static/service-date-calendar.js';
import '../../../line/static/service-date-calendar.css';
import { holidayClient } from '../api/scheduling/holiday_client';
import { schedulingCurrentClient, type SchedulingCurrentQuery } from '../api/scheduling/scheduling_current_client';
import { SchedulingCurrentError } from '../api/scheduling/scheduling_current_errors';

export const coordinatedServiceTime = '月嫂跟客戶自行協調';

interface Props {
  month: string;
  onMonthChange: (month: string) => void;
  selectedDates: readonly string[];
  isDateDisabled: (date: string) => boolean;
  onToggle: (date: string) => void;
  hint?: string;
  showHolidaySelectionHint?: boolean;
  showHolidays?: boolean;
  monthRange?: readonly [string, string];
  dayLabel?: (date: string) => string;
  dayDetails?: (date: string) => { holidayName?: string | null; rest?: boolean; laterSegment?: boolean; annotation?: string };
  staffSchedule?: { staffId: number; caseNo: string; actualStartDate?: string | null };
}

type StaffScheduleRequest = SchedulingCurrentQuery & { caseNo: string; actualStartDate?: string | null; firstDate: string };
type StaffScheduleResult =
  | { request: StaffScheduleRequest; status: 'loaded'; days: Map<string, CalendarOccupancyDetail[]> }
  | { request: StaffScheduleRequest; status: 'failed'; message: string };

// The same case calendar is used before service and for audited corrections after completion.
export const OrderServiceDateCalendar: FC<Props> = ({ month, onMonthChange, selectedDates, isDateDisabled, onToggle, hint, showHolidaySelectionHint, showHolidays = true, monthRange, dayLabel, dayDetails, staffSchedule }) => {
  const { year, monthNumber, leadingDays, firstDate, lastDate, dates } = buildCalendarMonth(month);
  const [holidayNames, setHolidayNames] = useState<Record<string, string>>({});
  const [holidayLoading, setHolidayLoading] = useState(true);
  const [holidayError, setHolidayError] = useState<string | null>(null);
  const [holidayReload, setHolidayReload] = useState(0);
  const [scheduleResult, setScheduleResult] = useState<StaffScheduleResult | null>(null);
  const [activeDetail, setActiveDetail] = useState<{ request: StaffScheduleRequest; date: string } | null>(null);
  const detailId = useId();
  const staffId = staffSchedule?.staffId;
  const caseNo = staffSchedule?.caseNo;
  const actualStartDate = staffSchedule?.actualStartDate;
  const scheduleRequest = useMemo<StaffScheduleRequest | null>(() => staffId && caseNo ? {
    caseNo, staffId, actualStartDate, firstDate, rangeStart: shiftCalendarDate(firstDate, -1), rangeEnd: lastDate,
  } : null, [actualStartDate, caseNo, firstDate, lastDate, staffId]);
  const visibleSchedule = scheduleRequest === scheduleResult?.request ? scheduleResult : null;
  const occupancyDays = visibleSchedule?.status === 'loaded' ? visibleSchedule.days : undefined;
  const detailDate = activeDetail && activeDetail.request === scheduleRequest ? activeDetail.date : null;
  const detailItems = detailDate ? occupancyDays?.get(detailDate) : undefined;
  const hasOccupancy = Boolean(occupancyDays?.size);

  useEffect(() => {
    if (!scheduleRequest) return;
    const { caseNo, actualStartDate, firstDate, ...query } = scheduleRequest;
    const controller = new AbortController();
    void schedulingCurrentClient.queryCurrentCalendar(query, { signal: controller.signal }).then(projection => {
      if (controller.signal.aborted) return;
      const days = calendarOccupancyDetailsByDate(projection.days.flatMap(day => day.entries.map(entry => ({
        date: day.calendar_date, caseNo: entry.case_no, kind: entry.occupancy_kind,
        actualStartDate: entry.actual_start_date, serviceStartAt: entry.service_start_at, serviceEndAt: entry.service_end_at,
        serviceHoursOverride: entry.service_hours_override,
      }))), { caseNo, actualStartDate, firstDate, lastDate: query.rangeEnd });
      setScheduleResult({ request: scheduleRequest, status: 'loaded', days });
    }).catch((error: unknown) => {
      if (controller.signal.aborted) return;
      const hasConflict = error instanceof SchedulingCurrentError
        && error.status === 409 && error.publicCode === 'staff_occupancy_conflict';
      const message = hasConflict
        ? '月嫂檔期有衝突，請核對既有排班與不可服務時段。'
        : '無法讀取月嫂檔期。';
      setScheduleResult({ request: scheduleRequest, status: 'failed', message });
    });
    return () => controller.abort();
  }, [scheduleRequest]);

  useEffect(() => {
    if (!showHolidays) return;
    const controller = new AbortController();
    setHolidayNames({});
    setHolidayLoading(true);
    setHolidayError(null);
    void holidayClient.query({ from_date: firstDate, to_date: lastDate }, { signal: controller.signal })
      .then(calendar => {
        if (!controller.signal.aborted) setHolidayNames(Object.fromEntries(calendar.holidays.map(holiday => [holiday.holiday_date, holiday.holiday_name])));
      })
      .catch(error => {
        if (!controller.signal.aborted) setHolidayError(error instanceof Error ? error.message : '無法讀取國定假日。');
      })
      .finally(() => { if (!controller.signal.aborted) setHolidayLoading(false); });
    return () => controller.abort();
  }, [firstDate, lastDate, holidayReload, showHolidays]);

  return <div className="service-calendar-workbench-layout">
    <div className="calendar-matrix-card">
      <div className="calendar-month-header">
        <h3>{year} 年 {monthNumber} 月</h3>
        <div className="order-case-action-row">{[-1, 1].map(delta => <button type="button" key={delta} aria-label={delta < 0 ? '上一個月' : '下一個月'}
          disabled={monthRange && (delta < 0 ? month <= monthRange[0] : month >= monthRange[1])}
          onClick={() => onMonthChange(shiftCalendarMonth(month, delta))}>{delta < 0 ? '‹' : '›'}</button>)}</div>
      </div>
      {showHolidays && holidayLoading && <small role="status">正在讀取當月國定假日…</small>}
      {showHolidays && holidayError && <div role="alert">國定假日標示載入失敗：{holidayError} <button type="button" onClick={() => setHolidayReload(value => value + 1)}>重新讀取假日</button></div>}
      {scheduleRequest && !visibleSchedule && <small role="status">正在讀取月嫂檔期…</small>}
      {visibleSchedule?.status === 'failed' && <small role="alert">{visibleSchedule.message}</small>}
      {hasOccupancy && <p className="service-date-scroll-hint">可橫向捲動月曆查看各日檔期。</p>}
      {hasOccupancy && <p className="service-date-mobile-hint">點選檔期筆數查看案號與時段</p>}
      <div className={hasOccupancy ? 'service-date-calendar-scroll' : undefined}>
      <div className="calendar-days-grid" role="group" aria-label="服務日期月曆" data-surface-id="orders.date.service-date-selection">
        {calendarWeekdays.map(weekday => <span key={weekday} className="service-date-weekday" aria-hidden="true">{weekday}</span>)}
        {Array.from({ length: leadingDays }, (_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
        {dates.map(date => {
          const selected = selectedDates.includes(date);
          const details = dayDetails?.(date);
          const holidayName = showHolidays ? holidayNames[date] : undefined;
          const occupancy = occupancyDays?.get(date);
          const occupancyText = occupancy ? `，${[...new Set(occupancy.map(item => item.label))].join('、')}` : '';
          const label = dayLabel?.(date);
          const occupied = occupancy && scheduleRequest;
          const cellClass = `calendar-date-cell${selected ? ' selected' : ''}${selected && details?.laterSegment ? ' later-segment' : ''}`;
          const dateButton = <button key={date} data-control-id="orders.date.service-date-select" type="button" aria-label={`${label ?? `服務日期 ${date}`}${occupancyText}`} aria-pressed={selected}
            title={`${label ?? `${date}${holidayName ? ` ${holidayName}` : details?.rest ? ' 建議休假' : ''}${selected ? '（已選服務日）' : ''}`}${occupancyText}`}
            className={occupied ? 'service-date-select' : cellClass}
            disabled={isDateDisabled(date)} onClick={() => onToggle(date)}>
            <time dateTime={date} title={date}>{Number(date.slice(8))}</time>
            {holidayName && <small className="service-date-holiday" aria-label={holidayName} title={holidayName}>{holidayName}</small>}
            {!holidayName && details?.rest && !selected && <small>休</small>}
            {details?.annotation && <small>{details.annotation}</small>}
          </button>;
          if (!occupancy || !scheduleRequest) return dateButton;
          return <div className={`${cellClass} service-date-occupied-day`} key={date}>
            {dateButton}
            <button type="button" className="service-date-occupancy-toggle" aria-label={`查看 ${date} 檔期明細`}
              aria-expanded={detailDate === date} aria-controls={detailId}
              onClick={() => setActiveDetail(detailDate === date ? null : { request: scheduleRequest, date })}>
              <span className="service-date-occupancy-count">{occupancy.length}筆</span>
              {occupancy.slice(0, 2).map(item => <span className="service-date-occupancy" key={`${item.label}-${item.caseNo}-${item.period?.full}`}>
                <strong>{item.caseNo ?? item.label}</strong>
                {item.caseNo && <small>{item.label}{item.continues && '・跨日續班'}</small>}
                {item.period && <small>{item.period.summary}</small>}
                {item.serviceHoursOverride && <small>{item.serviceHoursOverride} 小時・{coordinatedServiceTime}</small>}
              </span>)}
              {occupancy.length > 2 && <small className="service-date-occupancy-overflow">另有 {occupancy.length - 2} 筆</small>}
            </button>
          </div>;
        })}
      </div>
      </div>
      {hasOccupancy && <div id={detailId} className="service-date-occupancy-detail" hidden={!detailItems}>
        {detailItems && <>
          <h4>{detailDate} 檔期明細</h4>
          <ul>{detailItems.map(item => <li key={`${item.label}-${item.caseNo}-${item.period?.full}`}>
            <strong>{item.caseNo ? `案件 ${item.caseNo}` : item.label}</strong>
            {item.caseNo && <span>{item.label}{item.continues && '・跨日續班'}</span>}
            {item.serviceHoursOverride ? <span>{item.serviceHoursOverride} 小時・{coordinatedServiceTime}</span>
              : item.period ? <span>{item.period.full}</span> : item.caseNo && <span>服務時段待確認</span>}
          </li>)}</ul>
        </>}
      </div>}
      {hasOccupancy && <p className="service-date-calendar-hint"><span className="service-date-desktop-hint">點選案件檔期可查看時段。</span>歷史／暫定檔期僅供參考，正式衝突由系統比對服務時段。</p>}
      {hint && <p className="service-date-calendar-hint">{hint}</p>}
      {showHolidaySelectionHint && Object.keys(holidayNames).some(date => !isDateDisabled(date)) &&
        <p className="service-date-calendar-hint">選取國定假日即確認當日服務。</p>}
    </div>
  </div>;
};

export function OrderReadOnlyServiceDateCalendar({ dates }: { dates: readonly string[] }) {
  const [viewedMonth, setViewedMonth] = useState('');
  const sortedDates = [...dates].sort();
  const firstMonth = sortedDates[0]?.slice(0, 7);
  const lastMonth = sortedDates.at(-1)?.slice(0, 7);
  if (!firstMonth || !lastMonth) return null;

  const month = viewedMonth >= firstMonth && viewedMonth <= lastMonth ? viewedMonth : firstMonth;
  return <OrderServiceDateCalendar month={month} onMonthChange={setViewedMonth}
    selectedDates={dates} monthRange={[firstMonth, lastMonth]} showHolidays={false}
    isDateDisabled={() => true} onToggle={() => {}} />;
}
