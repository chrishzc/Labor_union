import { useEffect, useMemo, useState, type FC } from 'react';
import { buildCalendarMonth, calendarOccupancyByDate, calendarWeekdays, shiftCalendarMonth } from '../../../line/static/service-date-calendar.js';
import '../../../line/static/service-date-calendar.css';
import { holidayClient } from '../api/scheduling/holiday_client';
import { schedulingCurrentClient, type SchedulingCurrentQuery } from '../api/scheduling/scheduling_current_client';

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
  dayDetails?: (date: string) => { holidayName?: string | null; rest?: boolean; laterSegment?: boolean };
  staffSchedule?: { staffId: number; caseNo: string };
}

type StaffScheduleRequest = SchedulingCurrentQuery & { caseNo: string };
type StaffScheduleResult = { request: StaffScheduleRequest; days: Map<string, string[]> | null };

// The same case calendar is used before service and for audited corrections after completion.
export const OrderServiceDateCalendar: FC<Props> = ({ month, onMonthChange, selectedDates, isDateDisabled, onToggle, hint, showHolidaySelectionHint, showHolidays = true, monthRange, dayLabel, dayDetails, staffSchedule }) => {
  const { year, monthNumber, leadingDays, firstDate, lastDate, dates } = buildCalendarMonth(month);
  const [holidayNames, setHolidayNames] = useState<Record<string, string>>({});
  const [holidayLoading, setHolidayLoading] = useState(true);
  const [holidayError, setHolidayError] = useState<string | null>(null);
  const [holidayReload, setHolidayReload] = useState(0);
  const [scheduleResult, setScheduleResult] = useState<StaffScheduleResult | null>(null);
  const staffId = staffSchedule?.staffId;
  const caseNo = staffSchedule?.caseNo;
  const scheduleRequest = useMemo<StaffScheduleRequest | null>(() => staffId && caseNo ? {
    caseNo, staffId, rangeStart: firstDate, rangeEnd: lastDate,
  } : null, [caseNo, firstDate, lastDate, staffId]);
  const visibleSchedule = scheduleRequest === scheduleResult?.request ? scheduleResult : null;

  useEffect(() => {
    if (!scheduleRequest) return;
    const { caseNo, ...query } = scheduleRequest;
    const controller = new AbortController();
    void schedulingCurrentClient.queryCurrentCalendar(query, { signal: controller.signal }).then(projection => {
      if (controller.signal.aborted) return;
      const days = calendarOccupancyByDate(projection.days.flatMap(day => day.entries.map(entry => ({
        date: day.calendar_date, caseNo: entry.case_no, kind: entry.occupancy_kind,
      }))), caseNo);
      setScheduleResult({ request: scheduleRequest, days });
    }).catch(() => {
      if (!controller.signal.aborted) setScheduleResult({ request: scheduleRequest, days: null });
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
      {visibleSchedule?.days === null && <small role="alert">無法讀取月嫂檔期。</small>}
      <div className="calendar-days-grid" role="group" aria-label="服務日期月曆" data-surface-id="orders.date.service-date-selection">
        {calendarWeekdays.map(weekday => <span key={weekday} className="service-date-weekday" aria-hidden="true">{weekday}</span>)}
        {Array.from({ length: leadingDays }, (_, index) => <div key={`calendar-leading-${index}`} aria-hidden="true" />)}
        {dates.map(date => {
          const selected = selectedDates.includes(date);
          const details = dayDetails?.(date);
          const holidayName = showHolidays ? holidayNames[date] : undefined;
          const occupancy = visibleSchedule?.days?.get(date);
          const occupancyText = occupancy ? `，${occupancy.join('、')}` : '';
          const label = dayLabel?.(date);
          return <button key={date} data-control-id="orders.date.service-date-select" type="button" aria-label={`${label ?? `服務日期 ${date}`}${occupancyText}`} aria-pressed={selected}
            title={`${label ?? `${date}${holidayName ? ` ${holidayName}` : details?.rest ? ' 建議休假' : ''}${selected ? '（已選服務日）' : ''}`}${occupancyText}`}
            className={`calendar-date-cell${selected ? ' selected' : ''}${selected && details?.laterSegment ? ' later-segment' : ''}`}
            disabled={isDateDisabled(date)} onClick={() => onToggle(date)}>
            <time dateTime={date} title={date}>{Number(date.slice(8))}</time>
            {holidayName && <small className="service-date-holiday" aria-label={holidayName} title={holidayName}>{holidayName}</small>}
            {!holidayName && details?.rest && !selected && <small>休</small>}
            {occupancy?.map(label => <small key={label} className="service-date-occupancy">{label}</small>)}
          </button>;
        })}
      </div>
      {visibleSchedule?.days && visibleSchedule.days.size > 0 &&
        <p className="service-date-calendar-hint">檔期標示供排班參考，是否衝突依服務時段判定。</p>}
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
